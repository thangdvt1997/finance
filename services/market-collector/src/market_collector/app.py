from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from tscommon import Bus, make_app

from . import __version__
from .collector import Collector
from .config import CollectorSettings
from .models import ensure_utc, utcnow
from .providers import build_providers, make_http_client, provider_status
from .reconcile import Reconciler
from .publisher import Publisher
from prometheus_client import Gauge
from .state import StateStore
from .symbols import normalize_symbol

log = logging.getLogger("market_collector")
ROLE_STATE = Gauge("mc_provider_state", "Trang thai nguon: 1=active, 0.5=can key, 0=tat", ["provider"])


class BackfillRequest(BaseModel):
    provider: str
    symbol: str
    start: datetime
    end: datetime | None = None
    tfs: list[str] | None = None


def create_app(settings: CollectorSettings | None = None, *, bus: Bus | None = None,
               collector: Collector | None = None, run_scheduler: bool = True) -> FastAPI:
    cfg = settings or CollectorSettings.from_env()
    holder: dict = {"collector": collector, "recon": None}
    jobs: dict[str, dict] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = None
        if holder["collector"] is None:
            client = make_http_client(cfg)
            b = bus or Bus.from_url(cfg.redis_url)
            holder["collector"] = Collector(build_providers(cfg, client), Publisher(b), cfg, StateStore(cfg.state_file))
        c = holder["collector"]
        holder["recon"] = Reconciler(c.providers, c.pub, cfg)
        for it in provider_status(cfg, list(c.providers.values())):  # metric trang thai + log 1 dong cho nguon can key
            ROLE_STATE.labels(it["provider"]).set({"active": 1, "needs_key": 0.5}.get(it["state"], 0))
            if it["state"] == "needs_key":
                log.info("nguon %s dang tat: thieu %s (xem docs/FREE_STACK.md)", it["provider"], ",".join(it["needs_env"]))
        if run_scheduler:
            c.start()
            if cfg.reconcile_enabled and cfg.reconcile_interval > 0:
                t = asyncio.create_task(_recon_loop(holder["recon"], c), name="reconcile")
                c.tasks.add(t)
                t.add_done_callback(c.tasks.discard)
        yield
        await holder["collector"].stop()
        if client:
            await client.aclose()

    async def _recon_loop(rec: Reconciler, c: Collector) -> None:
        await asyncio.sleep(60)  # cho backfill/poll dau tien
        while not c._stop.is_set():
            try:
                await rec.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("doi chieu loi: %s", e)
            await asyncio.sleep(cfg.reconcile_interval)

    app = make_app(cfg.service_name, __version__, internal_auth=True)
    app.router.lifespan_context = lifespan

    def _col() -> Collector:
        c = holder["collector"]
        if c is None:
            raise HTTPException(503, "collector chua khoi dong")
        return c

    @app.get("/status")
    async def status():
        c = _col()
        return {"providers": list(c.providers), "jobs": jobs,
                "last_ok": {k: v.isoformat() for k, v in c.last_ok.items()},
                "last_cycle": {k: v.isoformat() for k, v in c.last_cycle.items()},
                "loop_restarts": dict(c.loop_restarts),
                "tasks_alive": sorted(t.get_name() for t in c.tasks if not t.done() and t.get_name().startswith("provider-")),
                "gaps": {f"{p}:{s}:{tf}": sorted(d.date().isoformat() for d in r)
                         for (p, s, tf), r in c.gaps.items()}}

    @app.get("/providers")
    async def providers():
        """Trang thai bat/tat tung nguon: active | needs_key (thieu env) | disabled | risky_off | unavailable."""
        c = _col()
        items = provider_status(cfg, list(c.providers.values()))
        for it in items:
            p = it["provider"]
            it["last_cycle"] = c.last_cycle[p].isoformat() if p in c.last_cycle else None
            oks = [v for k, v in c.last_ok.items() if k.startswith(p + ":")]
            it["last_ok"] = max(oks).isoformat() if oks else None
            ROLE_STATE.labels(p).set({"active": 1, "needs_key": 0.5}.get(it["state"], 0))
        return {"providers": items, "free_pack": True}

    @app.get("/reconcile")
    async def reconcile(run: bool = False):
        """Ket qua doi chieu nguon gan nhat (Dukascopy vs OANDA/TrueFX/Frankfurter). `?run=true` chay ngay."""
        _col()
        rec = holder["recon"]
        if run and cfg.reconcile_enabled:
            await rec.run_once()
        return rec.last_report

    @app.post("/backfill", status_code=202)
    async def backfill(req: BackfillRequest, x_backfill_token: str | None = Header(default=None)):
        if not cfg.backfill_token:
            raise HTTPException(503, "BACKFILL_TOKEN chua cau hinh -> endpoint tat")
        if not x_backfill_token or not hmac.compare_digest(x_backfill_token, cfg.backfill_token):
            raise HTTPException(401, "token khong hop le")
        c = _col()
        if req.provider not in c.providers:
            raise HTTPException(404, f"provider khong bat: {req.provider}")
        start = ensure_utc(req.start)
        end = ensure_utc(req.end) if req.end else utcnow()
        if end <= start or end - start > timedelta(days=3650):
            raise HTTPException(422, "khoang thoi gian khong hop le (toi da 10 nam)")
        symbol = normalize_symbol(req.symbol)
        if not c.providers[req.provider].supports(symbol):
            raise HTTPException(422, f"{req.provider} khong ho tro {symbol}")
        job_id = uuid.uuid4().hex[:12]
        jobs[job_id] = {"state": "running", "provider": req.provider, "symbol": symbol}

        async def run():
            try:
                jobs[job_id]["bars"] = await c.backfill(req.provider, symbol, start, end, req.tfs)
                jobs[job_id]["state"] = "done"
            except Exception as e:  # noqa: BLE001
                jobs[job_id].update(state="error", error=str(e)[:200])

        t = asyncio.create_task(run())
        c.tasks.add(t)
        t.add_done_callback(c.tasks.discard)
        return {"job_id": job_id, "state": "running"}

    return app
