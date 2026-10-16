"""briefing: BẢN TIN thị trường tiếng Việt do LLM cục bộ tóm tắt, có trích dẫn, hậu kiểm tất định. READ-ONLY về giao dịch.

API nội bộ (chỉ api-gateway gọi): GET /briefing/latest | /briefing/list | /briefing/{id}.
Vận hành: POST /internal/run?edition=morning|close&scope=vn|intl|all (header X-Admin-Token), GET /internal/status.
Lịch chạy trong service (giờ VN): BRIEFING_SCHEDULE="06:15=morning,16:30=close". Phát stream `briefing.items` + alert (ntfy); ghi bảng `briefings` (ts_briefing)."""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from prometheus_client import Counter, Gauge, Histogram
from tscommon import make_app, make_event

from . import __version__
from .config import Settings, settings
from .analyst import Analyst
from .llm import LLM
from .pipeline import EDITIONS, SCOPES, generate, to_text
from .source import Source
from .store import Store, jsonable

log = logging.getLogger("briefing")
ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
BR_TOTAL = Counter("briefing_runs_total", "Số bản tin đã sinh", ["scope", "edition", "status"])
BR_DUR = Histogram("briefing_run_seconds", "Thời gian sinh 1 bản tin", buckets=(5, 15, 30, 60, 120, 240, 480, 900, 1800))
BR_LAST = Gauge("briefing_last_success_timestamp", "Thời điểm bản tin gần nhất sinh xong", ["scope", "edition"])
BR_DROP = Counter("briefing_points_dropped_total", "Ý bị hậu kiểm loại", ["reason"])
BR_ERR = Counter("briefing_run_errors_total", "Lần chạy lỗi (không lưu được)", ["scope", "edition"])
STREAM = "briefing.items"


def parse_schedule(spec: str) -> list[tuple[int, int, str]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        hm, _, ed = part.partition("=")
        h, m = hm.split(":")
        if ed not in EDITIONS:
            raise ValueError(f"edition không hợp lệ: {ed}")
        out.append((int(h), int(m), ed))
    return sorted(out)


def next_fire(now: datetime, sched: list[tuple[int, int, str]], tz: ZoneInfo) -> tuple[datetime, str]:
    loc = now.astimezone(tz)
    cands = []
    for d in (0, 1):
        for h, m, ed in sched:
            t = (loc + timedelta(days=d)).replace(hour=h, minute=m, second=0, microsecond=0)
            if t > loc:
                cands.append((t, ed))
    t, ed = min(cands)
    return t.astimezone(timezone.utc), ed


def out(row: dict) -> dict:
    return jsonable(row)


class Runner:
    def __init__(self, cfg: Settings, src: Source, store: Store, llm: LLM | None, bus=None):
        self.cfg, self.src, self.store, self.llm, self.bus = cfg, src, store, llm, bus
        self.lock = asyncio.Lock()
        self.last: dict[str, dict] = {}
        self.running: dict | None = None

    async def run_one(self, scope: str, edition: str, now: datetime | None = None) -> dict:
        async with self.lock:
            self.running = {"scope": scope, "edition": edition, "since": datetime.now(timezone.utc).isoformat()}
            t0 = time.monotonic()
            try:
                b = await generate(self.cfg, self.src, self.llm, scope, edition, now)
                await self.store.insert(b)
                BR_TOTAL.labels(scope, edition, b["status"]).inc()
                for d in b["quality"].get("dropped", []):
                    BR_DROP.labels(str(d.get("reason", ""))[:24].split(":")[0]).inc()
                BR_LAST.labels(scope, edition).set(time.time())
                await self.publish(b)
                self.last[f"{scope}:{edition}"] = {"id": b["id"], "status": b["status"], "at": b["generated_at"].isoformat(), "secs": round(time.monotonic() - t0, 1)}
                return b
            except Exception:
                BR_ERR.labels(scope, edition).inc()
                raise
            finally:
                BR_DUR.observe(time.monotonic() - t0)
                self.running = None

    async def publish(self, b: dict) -> None:
        if self.bus is None:
            return
        try:
            n_cites = sum(len(p["cites"]) for p in b["body"]["points"])
            payload = {"briefing_id": b["id"], "edition": b["edition"], "scope": b["scope"], "for_date": b["for_date"].isoformat(), "title": b["title"],
                       "headline": b["headline"], "status": b["status"], "model": b["model"], "generated_at": b["generated_at"].isoformat(),
                       "n_points": len(b["body"]["points"]), "n_citations": n_cites, "path": f"/bao-cao/ban-tin?id={b['id']}"}
            await self.bus.publish(STREAM, make_event("briefing", "briefing", payload))
            if self.cfg.notify:
                body = to_text(b) + "\n(Tạo bởi AI, tham khảo, không phải khuyến nghị đầu tư)"
                await self.bus.publish("alerts.out", make_event("alert", "briefing", {
                    "level": "info", "title": b["title"], "body": body[:900], "tags": ["briefing", b["scope"], b["edition"], "ch:ntfy"],
                    "dedupe_key": f"briefing:{b['id']}"}))
        except Exception:  # noqa: BLE001  (thông báo lỗi không được làm hỏng bản tin đã lưu)
            log.exception("publish lỗi")

    async def run_many(self, scopes: list[str], edition: str, now: datetime | None = None) -> list[dict]:
        res = []
        for sc in scopes:
            try:
                res.append(await self.run_one(sc, edition, now))
            except Exception:  # noqa: BLE001
                log.exception("chạy %s/%s lỗi", sc, edition)
        return res


async def scheduler(app: FastAPI) -> None:
    cfg: Settings = app.state.cfg
    runner: Runner = app.state.runner
    tz = ZoneInfo(cfg.tz)
    sched = parse_schedule(cfg.schedule)
    scopes = [s for s in cfg.scopes.split(",") if s in SCOPES]
    while True:
        when, ed = next_fire(datetime.now(timezone.utc), sched, tz)
        app.state.next_run = {"at": when.isoformat(), "edition": ed}
        await asyncio.sleep(max(1.0, (when - datetime.now(timezone.utc)).total_seconds()))
        loc = datetime.now(timezone.utc).astimezone(tz)
        use = [s for s in scopes if not (s == "vn" and ed == "close" and loc.weekday() >= 5)]  # thị trường VN nghỉ cuối tuần
        await runner.run_many(use, ed)


def create_app(cfg: Settings | None = None, src: Source | None = None, store: Store | None = None, llm: LLM | None = None, bus=None, start_scheduler: bool | None = None) -> FastAPI:
    cfg = cfg or settings()
    app = make_app("briefing", __version__, internal_auth=True)
    app.state.cfg = cfg
    app.state.runner = Runner(cfg, src, store, llm, bus) if src is not None and store is not None else None
    app.state.next_run = None
    app.state.tasks = []
    app.state.jobs: dict[str, dict] = {}
    do_sched = cfg.scheduler_enabled if start_scheduler is None else start_scheduler

    @app.on_event("startup")
    async def _startup():
        if app.state.runner is None:  # chạy thật: dựng kết nối từ cấu hình
            from redis import asyncio as aioredis
            from tscommon import Bus

            from .llm import LlamaCppLLM
            from .source import PgSource
            from .store import PgStore
            s = await PgSource.connect(cfg.database_url)
            st = await PgStore.connect(cfg.db_rw_url)
            bus = Bus(aioredis.from_url(cfg.redis_url, decode_responses=True)) if cfg.redis_url else None
            app.state.runner = Runner(cfg, s, st, LlamaCppLLM(cfg.llm_url, cfg.llm_timeout_s) if cfg.llm_enabled else None, bus)
        if do_sched:
            app.state.tasks.append(asyncio.create_task(scheduler(app)))

    @app.on_event("shutdown")
    async def _shutdown():
        for t in app.state.tasks:
            t.cancel()
        r: Runner | None = app.state.runner
        if r:
            with contextlib.suppress(Exception):
                await r.store.close()
                await r.src.close()

    def runner() -> Runner:
        r = app.state.runner
        if r is None:
            raise HTTPException(503, "chưa sẵn sàng")
        return r

    async def analyst_extra(symbol: str) -> dict | None:
        """Ngữ cảnh có cấu trúc (regime/đồng thuận/kịch bản) từ service ai-trading — chỉ GET nội bộ."""
        import httpx
        from tscommon.internal_auth import internal_headers
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=3)) as c:
            r = await c.get(f"{cfg.ai_url}/ai/analyst-context", params={"symbol": symbol}, headers=internal_headers())
            r.raise_for_status()
            return r.json()

    def analyst() -> Analyst:
        a = getattr(app.state, "analyst", None)
        if a is None:
            r = runner()
            a = app.state.analyst = Analyst(r.src, r.llm, analyst_extra, cfg, cfg.analyst_ttl_s, cfg.analyst_timeout_s, busy=lambda: r.running is not None)
        return a

    @app.get("/analyst", tags=["analyst"])
    async def analyst_ep(symbol: str = Query(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9:_.\-]{0,23}$"), wait: bool = False):
        """AI analyst (chỉ đọc, chỉ master qua gateway): tóm tắt bối cảnh + giải thích kịch bản; hậu kiểm tất định; cache."""
        return await analyst().get(symbol, wait=wait)

    @app.get("/briefing/latest")
    async def latest(edition: str | None = Query(None, pattern="^(morning|close)$"), scope: str | None = Query(None, pattern="^(vn|intl)$")):
        r = runner()
        if edition or scope:
            rows = await r.store.latest(edition, scope, 1)
            if not rows:
                raise HTTPException(404, "chưa có bản tin")
            return out(rows[0])
        items = []
        for sc in SCOPES:
            for ed in EDITIONS:
                rows = await r.store.latest(ed, sc, 1)
                if rows:
                    items.append(out(rows[0]))
        items.sort(key=lambda x: x["generated_at"], reverse=True)
        return {"items": items}

    @app.get("/briefing/list")
    async def blist(limit: int = Query(30, ge=1, le=200), edition: str | None = Query(None, pattern="^(morning|close)$"),
                    scope: str | None = Query(None, pattern="^(vn|intl)$")):
        return {"items": [out(x) for x in await runner().store.list(limit, edition, scope)]}

    @app.get("/briefing/{bid}")
    async def one(bid: str):
        if not ID_RE.match(bid):
            raise HTTPException(422, "id không hợp lệ")
        row = await runner().store.get(bid)
        if not row:
            raise HTTPException(404, "không tìm thấy")
        return out(row)

    def admin(tok: str | None):
        if not cfg.admin_token:
            raise HTTPException(503, "BRIEFING_ADMIN_TOKEN chưa đặt")
        if not tok or not hmac.compare_digest(tok, cfg.admin_token):
            raise HTTPException(403, "sai token")

    @app.post("/internal/run", status_code=202)
    async def run(edition: str = Query(..., pattern="^(morning|close)$"), scope: str = Query("all", pattern="^(vn|intl|all)$"),
                  wait: bool = False, x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        r = runner()
        if r.lock.locked():
            raise HTTPException(409, "đang có một lần chạy khác")
        scopes = list(SCOPES) if scope == "all" else [scope]
        if wait:
            res = await r.run_many(scopes, edition)
            return {"done": True, "ids": [b["id"] for b in res], "statuses": [b["status"] for b in res]}
        job = f"{int(time.time())}"
        app.state.jobs[job] = {"edition": edition, "scopes": scopes, "state": "running"}

        async def go():
            res = await r.run_many(scopes, edition)
            app.state.jobs[job].update(state="done", ids=[b["id"] for b in res], statuses=[b["status"] for b in res])
        app.state.tasks.append(asyncio.create_task(go()))
        return {"job": job, "state": "running"}

    @app.get("/internal/status")
    async def status(x_admin_token: str | None = Header(None)):
        admin(x_admin_token)
        r = runner()
        return {"next_run": app.state.next_run, "running": r.running, "last": r.last, "jobs": app.state.jobs, "llm_enabled": cfg.llm_enabled, "model": cfg.llm_model}

    return app
