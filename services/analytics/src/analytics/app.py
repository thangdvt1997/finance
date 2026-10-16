from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from tscommon import Bus, make_app

from . import __version__
from .config import AnalyticsSettings, load_yaml
from .repo import NullStore
from .runner import Runner, loop

log = logging.getLogger("analytics")


def create_app(settings: AnalyticsSettings | None = None, runner: Runner | None = None) -> FastAPI:
    settings = settings or AnalyticsSettings()
    app = make_app("analytics", __version__, internal_auth=True)
    app.state.runner = runner

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()
        task = None
        closers = []
        if _app.state.runner is None and settings.enabled:
            from .repo import PgBarSource, PgSnapshotStore
            cfg = load_yaml(settings.config_path)
            source = await PgBarSource.connect(settings.read_url)
            closers.append(source.close)
            if settings.write_url:
                store = await PgSnapshotStore.connect(settings.write_url)
                closers.append(store.close)
            else:
                log.warning("ANALYTICS_DB_RW_URL trống: chỉ phát sự kiện/cảnh báo, KHÔNG lưu analytics_snapshots")
                store = NullStore()
            bus = Bus.from_url(settings.redis_url)
            closers.append(bus.r.aclose)
            _app.state.runner = Runner(cfg, source, store, bus)
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

    return app
