from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Query
from tscommon import Bus, make_app

from . import __version__
from .config import Settings, load_yaml
from .repo import MemoryStore
from .runner import Runner, loop
from .specs import load_specs

log = logging.getLogger("pattern-engine")
STATES = ("forming", "armed", "triggered", "invalid")


def create_app(settings: Settings | None = None, runner: Runner | None = None, store=None) -> FastAPI:
    settings = settings or Settings()
    app = make_app("pattern-engine", __version__, internal_auth=True)
    app.state.runner = runner
    app.state.store = store if store is not None else (runner.store if runner else MemoryStore())

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()
        task = None
        closers = []
        if _app.state.runner is None and settings.enabled:
            from .repo import PgBarSource, PgSignalStore
            cfg = load_yaml(settings.config_path)
            source = await PgBarSource.connect(settings.read_url)
            closers.append(source.close)
            if settings.write_url:
                st = await PgSignalStore.connect(settings.write_url)
                closers.append(st.close)
            else:
                log.warning("PATTERN_DB_RW_URL trống: chỉ phát sự kiện, KHÔNG lưu pattern_signals (RAM)")
                st = MemoryStore()
            bus = Bus.from_url(settings.redis_url)
            closers.append(bus.r.aclose)
            _app.state.store = st
            _app.state.runner = Runner(cfg, source, st, bus)
        if _app.state.runner is not None and settings.enabled:
            task = asyncio.create_task(loop(_app.state.runner, int(_app.state.runner.cfg["interval_seconds"]), stop))
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

    @app.get("/status", tags=["ops"], summary="Kết quả chu kỳ gần nhất")
    async def status():
        r = app.state.runner
        return r.last if r else {"status": "tắt (ENABLED=false)"}

    @app.get("/patterns", tags=["patterns"], summary="Tín hiệu kịch bản gần nhất (gateway lọc theo vai trò)")
    async def patterns(symbol: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9:._\-]{1,32}$")] = None,
                       tf: Annotated[str | None, Query(pattern=r"^(M1|M5|M15|M30|H1|H4|D1)$")] = None,
                       pattern: Annotated[str | None, Query(pattern=r"^KB-[0-9]{1,2}$")] = None,
                       state: Annotated[str | None, Query(description="forming|armed|triggered|invalid, phân tách bằng dấu phẩy")] = None,
                       since: datetime | None = None,
                       limit: Annotated[int, Query(ge=1, le=500)] = 100):
        states = [s for s in (state or "").split(",") if s in STATES] or None
        rows = await app.state.store.recent(symbol=symbol, tf=tf, pattern=pattern, states=states, since=since, limit=limit)
        return {"items": [_ser(r) for r in rows],
                "disclaimer": "Tín hiệu kỹ thuật chỉ để tham khảo/paper, không phải khuyến nghị đầu tư."}

    @app.get("/patterns/spec", tags=["patterns"], summary="Định nghĩa các kịch bản (tên, bước, tham số)")
    async def spec():
        sp = app.state.runner.specs if app.state.runner else load_specs()
        return {"items": [{"id": k, "name": v["name"], "side": v["side"], "summary": " ".join(str(v["summary"]).split()),
                           "steps": [{"id": int(i), "label": lb} for i, lb in sorted(v["steps"].items())],
                           "invalidation": v.get("invalidation", []),
                           "params": {a: b for a, b in v["params"].items() if not a.startswith("_")}} for k, v in sp.items()]}

    return app


def _ser(r: dict) -> dict:
    d = dict(r)
    for k in ("bar_ts", "ts", "created_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    d["score"] = float(d["score"])
    return d
