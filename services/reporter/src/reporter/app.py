from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from tscommon import Bus, make_app

from . import __version__
from .account_reports import build_router as account_router
from .account_service import AccountReporter
from .config import Settings
from .scheduler import loop, next_runs
from .service import Reporter
from .store import MEDIA, valid_name

log = logging.getLogger("reporter")


def create_app(cfg: Settings | None = None, reporter: Reporter | None = None, run_scheduler: bool = True,
               account_reporter: AccountReporter | None = None) -> FastAPI:
    cfg = cfg or Settings.from_env()
    app = make_app("reporter", __version__, internal_auth=True)
    app.state.reporter = reporter
    app.state.account_reporter = account_reporter

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()
        task = acc_task = None
        bus = None
        if _app.state.reporter is None:
            bus = Bus.from_url(cfg.redis_url) if cfg.redis_url else None
            _app.state.reporter = Reporter(cfg, bus=bus)
        rep = _app.state.reporter
        if _app.state.account_reporter is None:
            _app.state.account_reporter = AccountReporter(cfg)
        if run_scheduler and cfg.enabled:
            acc_task = asyncio.create_task(_app.state.account_reporter.loop(stop))
        if run_scheduler and cfg.enabled:
            task = asyncio.create_task(loop(cfg, rep.generate, rep.exists, stop, rep.clock))
        try:
            yield
        finally:
            stop.set()
            for t in (acc_task,):
                if t:
                    t.cancel()
                    await asyncio.gather(t, return_exceptions=True)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if bus is not None:
                with contextlib.suppress(Exception):
                    await bus.r.aclose()

    app.router.lifespan_context = lifespan
    app.include_router(account_router(lambda: app.state.account_reporter))   # báo cáo theo tài khoản (account_reports.py)

    @app.get("/reports", tags=["reports"], summary="Danh sách báo cáo (mới nhất trước)")
    async def list_reports():
        rep: Reporter = app.state.reporter
        return {"read_only": True, "items": rep.store.items(), "next_runs": next_runs(rep.clock(), cfg)}

    @app.get("/reports/{kind}/{name}", tags=["reports"], summary="Tải file báo cáo: {YYYY-MM-DD}.html|pdf")
    async def get_report(kind: str, name: str):
        period, _, ext = name.rpartition(".")
        if not valid_name(kind, period, ext):
            raise HTTPException(404, "không tìm thấy báo cáo")
        p = app.state.reporter.store.path(kind, period, ext)
        if not p.is_file():
            raise HTTPException(404, "không tìm thấy báo cáo")
        return FileResponse(p, media_type=MEDIA[ext], filename=f"{kind}-{period}.{ext}" if ext == "pdf" else None,
                            content_disposition_type="attachment" if ext == "pdf" else "inline",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/generate", tags=["internal"], summary="Sinh báo cáo ngay (CHỈ nội bộ, không expose qua gateway)")
    async def generate(kind: str = Query(pattern="^(daily|weekly)$"), force: int = 0,
                       period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return await app.state.reporter.generate(kind, period, force=bool(force))

    return app
