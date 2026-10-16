from __future__ import annotations

import asyncio
import contextlib
import logging
import re

from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge
from tscommon import Bus, make_app

from . import __version__
from .alerts import AlertEmitter
from .config import Settings, load_config
from .fleet import FleetConfig, FleetEngine, budget_conditions
from .service import RiskService, summary

log = logging.getLogger("risk-monitor")
ID_RE = re.compile(r"^[\w.:\-]{1,64}$")

G_LEVEL = Gauge("risk_margin_level_pct", "Mức margin (%)", ["account"])
G_LEV = Gauge("risk_leverage_gross", "Đòn bẩy hiệu dụng gross", ["account"])
G_DD = Gauge("risk_dd_from_peak_pct", "Drawdown từ đỉnh (%)", ["account"])
G_ES = Gauge("risk_es975_1d_pct", "ES 97,5% 1 ngày (% equity)", ["account"])
G_BUD = Gauge("risk_budget_status", "0 ok, 1 warn, 2 crit", ["account"])


async def cycle(svc: RiskService, emitter: AlertEmitter | None, cfg: dict, fleet: FleetEngine | None = None) -> dict:
    n_alerts, n = 0, 0
    conds: list[dict] = []
    acfg = cfg.get("alerts", {})
    for a in await svc.accounts():
        try:
            rep = await svc.report(a["account_id"], use_cache=False)
        except Exception:  # noqa: BLE001
            log.exception("tính rủi ro %s lỗi", a["account_id"])
            continue
        if not rep:
            continue
        n += 1
        s = summary(rep)
        for g, k in ((G_LEVEL, "margin_level"), (G_LEV, "leverage_effective"), (G_DD, "dd_from_peak_pct"), (G_ES, "es975_1d_pct")):
            if s.get(k) is not None:
                g.labels(a["account_id"]).set(s[k])
        G_BUD.labels(a["account_id"]).set({"ok": 0, "warn": 1, "crit": 2}.get(s["budget_status"], 0))
        eligible = (acfg.get("enabled", True) and a["kind"] in acfg.get("kinds", ["mt"]) and not s["stale"]
                    and not (a["kind"] == "paper" and acfg.get("paper_meaningful_only", True) and not s.get("meaningful")))
        if emitter and eligible:
            n_alerts += await emitter.process(a["account_id"], rep["budget"]["items"])
        if fleet is not None and a["kind"] == "mt" and not s["stale"]:
            conds += budget_conditions(a["account_id"], rep["budget"]["items"])
    out = {"accounts": n, "alerts": n_alerts}
    if fleet is not None and fleet.enabled:
        try:
            out["fleet"] = await fleet.run(svc.src, conds)
        except Exception:  # noqa: BLE001  (không để engine luật làm hỏng chu kỳ ngân sách)
            log.exception("engine luật đội tài khoản lỗi")
    return out


def create_app(settings: Settings | None = None, service: RiskService | None = None) -> FastAPI:
    settings = settings or Settings()
    app = make_app("risk-monitor", __version__, internal_auth=True)
    app.state.svc = service
    app.state.last = {}
    app.state.fleet = None

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()
        task, closers, emitter = None, [], None
        cfg = load_config(settings.config_path)
        if _app.state.svc is None and settings.enabled:
            from .sources import PgRedisSource
            src = await PgRedisSource.connect(settings.database_url, settings.redis_url)
            closers.append(src.close)
            _app.state.svc = RiskService(src, cfg)
            bus = Bus.from_url(settings.redis_url)
            closers.append(bus.r.aclose)
            emitter = AlertEmitter(bus.r, bus, cfg)
            _app.state.fleet = FleetEngine(FleetConfig.from_env(cfg), bus.r, bus)
        svc = _app.state.svc
        if svc is not None and settings.enabled:
            async def loop():
                while not stop.is_set():
                    try:
                        _app.state.last = await cycle(svc, emitter, svc.cfg, _app.state.fleet)
                    except Exception:  # noqa: BLE001
                        log.exception("chu kỳ rủi ro lỗi")
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=float(svc.cfg.get("interval_seconds", 60)))
            task = asyncio.create_task(loop())
        try:
            yield
        finally:
            stop.set()
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            for c in closers:
                with contextlib.suppress(Exception):
                    await c()

    app.router.lifespan_context = lifespan

    def _svc() -> RiskService:
        if app.state.svc is None:
            raise HTTPException(503, "risk-monitor tắt (ENABLED=false)")
        return app.state.svc

    @app.get("/risk/accounts", tags=["risk"], summary="Tóm tắt rủi ro mọi tài khoản (MT + paper), READ-ONLY")
    async def accounts():
        from datetime import datetime, timezone
        return {"generated_at": datetime.now(timezone.utc).isoformat(), "read_only": True, "accounts": await _svc().summaries()}

    @app.get("/risk/accounts/{account_id}", tags=["risk"], summary="Báo cáo rủi ro đầy đủ 1 tài khoản")
    async def account(account_id: str):
        if not ID_RE.match(account_id):
            raise HTTPException(422, "account_id không hợp lệ")
        rep = await _svc().report(account_id)
        if rep is None:
            raise HTTPException(404, "không có tài khoản")
        return rep

    @app.get("/risk/config", tags=["risk"], summary="Ngưỡng ngân sách rủi ro + danh sách kịch bản (chỉ đọc)")
    async def config():
        c = _svc().cfg
        return {"budget": c["budget"], "mt": c["mt"], "scenarios": [{k: s.get(k) for k in ("id", "name", "type", "start", "end")} for s in c["scenarios"]],
                "var": c["var"], "read_only": True}

    @app.get("/risk/rules/status", tags=["risk"], summary="Kết quả đánh giá mẫu luật đội tài khoản gần nhất (chỉ đọc)")
    async def rules_status():
        f = app.state.fleet
        if f is None:
            return {"read_only": True, "engine": "off", "assignments": 0, "results": []}
        return f.status()

    @app.get("/status", tags=["ops"], summary="Chu kỳ gần nhất")
    async def status():
        return app.state.last or {"status": "chưa chạy chu kỳ nào"}

    return app
