"""data-keeper: vòng lặp nền + HTTP (/healthz, /metrics). Nạp module lỏng: module thiếu/lỗi import -> bỏ qua có log.

HỢP ĐỒNG MODULE (mỗi agent chỉ sở hữu file của mình):
  inventory.build_matrix(db) -> dict                       (A1; được gọi mỗi DK_INVENTORY_INTERVAL_S)
  heal.heal_cycle(ctx, matrix) -> list[action]             (A2)
  backfill.backfill_cycle(ctx, matrix)                     (A3)
  histload.histload_cycle(ctx, matrix)  [tuỳ chọn]         (A4)
  llm.report_cycle(ctx, matrix) [tuỳ chọn]                 (A5)
  api.build_router(ctx) -> APIRouter  (hoặc api.register(app, ctx)) [tuỳ chọn]   (A5; /v1/data/health, /v1/data/recheck)
  Mọi module có thể có SCHEMA_SQL (str, CREATE ... IF NOT EXISTS trong schema dk) -> chạy bằng role ts_dk lúc khởi động.
ctx: .settings .db(.ro .rw) .guard(.ok() .p95) .matrix(mới nhất) .summary .state(dict tự do) .log.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from tscommon import setup_logging

from .config import get_settings
from .db import DB
from .guard import LatencyGuard

log = logging.getLogger("data_keeper")
G_LOADED = Gauge("dk_module_loaded", "1 neu module nap duoc", ["module"])
G_ENABLED = Gauge("dk_enabled", "Co DATA_KEEPER_ENABLED")
C_ERR = Counter("dk_cycle_errors_total", "Loi trong chu ky", ["stage"])
G_P95 = Gauge("dk_guard_feed_p95_seconds", "p95 tre feed fx do boi guard (cua so giua 2 lan cao)")
G_CYCLE = Gauge("dk_cycle_last_timestamp", "epoch giay chu ky hoan tat cuoi")


class Ctx:
    def __init__(self, settings, db, guard):
        self.settings, self.db, self.guard = settings, db, guard
        self.matrix: dict = {}
        self.summary: dict = {}
        self.state: dict = {}
        self.log = log
        self.mods: dict = {}
        self.enabled = settings.enabled
        self.queue_len = 0               # backfill cập nhật
        self.recheck = asyncio.Event()   # api.POST /v1/data/recheck đặt cờ này để chạy ngay


def load_modules(names) -> dict:
    mods = {}
    for n in names:
        try:
            mods[n] = importlib.import_module(f"data_keeper.{n}")
            G_LOADED.labels(n).set(1)
        except ModuleNotFoundError as e:
            if e.name == f"data_keeper.{n}":
                log.info("module %s chua co -> bo qua", n)
            else:
                log.error("module %s loi import phu thuoc: %s", n, e)
                C_ERR.labels(f"import:{n}").inc()
            G_LOADED.labels(n).set(0)
        except Exception as e:  # noqa: BLE001
            log.exception("module %s loi khi nap: %s", n, e)
            C_ERR.labels(f"import:{n}").inc()
            G_LOADED.labels(n).set(0)
    return mods


async def _call(ctx, stage, fn, *a):
    try:
        return await asyncio.wait_for(fn(*a), ctx.settings.cycle_timeout_s)
    except Exception as e:  # noqa: BLE001  (một module lỗi không được làm sập vòng lặp)
        C_ERR.labels(stage).inc()
        log.exception("stage %s loi: %s", stage, e)
        return None


async def cycle(ctx: Ctx) -> None:
    m = ctx.mods
    await ctx.guard.refresh()
    if ctx.guard.p95 is not None:
        G_P95.set(ctx.guard.p95)
    inv = m.get("inventory")
    if inv is None or ctx.db.ro is None:
        return
    ru = m.get("rollup")   # va lo khung cao do mt-bridge restart TRUOC kiem ke (nen kiem ke thay nen da va)
    if ru and hasattr(ru, "rollup_cycle") and ctx.guard.ok():
        await _call(ctx, "rollup", ru.rollup_cycle, ctx, None)
    matrix = await _call(ctx, "inventory", inv.build_matrix, ctx.db)
    if matrix is None:
        return
    ctx.matrix, ctx.summary = matrix, getattr(inv, "SUMMARY", {})
    for name, fn in (("heal", "heal_cycle"), ("backfill", "backfill_cycle"), ("histload", "histload_cycle"), ("llm", "report_cycle")):
        mod = m.get(name)
        if mod and hasattr(mod, fn):
            await _call(ctx, name, getattr(mod, fn), ctx, matrix)
    G_CYCLE.set(time.time())


async def loop(ctx: Ctx) -> None:
    s = ctx.settings
    await asyncio.sleep(s.first_delay_s)
    while True:
        t = time.monotonic()
        await cycle(ctx)
        left = max(5.0, s.interval_s - (time.monotonic() - t))
        try:
            await asyncio.wait_for(ctx.recheck.wait(), left)
        except asyncio.TimeoutError:
            pass
        ctx.recheck.clear()


def create_app(ctx_holder: dict) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        s = get_settings()
        G_ENABLED.set(1 if s.enabled else 0)
        task = None
        if s.enabled:
            try:
                os.nice(s.nice)
            except OSError:
                pass
            db = await DB.connect(s)
            ctx = Ctx(s, db, LatencyGuard(s.bridge_metrics_url, s.p95_max_s))
            ctx.mods = load_modules(s.modules)
            for mod in ctx.mods.values():
                if getattr(mod, "SCHEMA_SQL", None):
                    db.schemas.append(mod.SCHEMA_SQL)
            try:
                await db.ensure_schema()
            except Exception as e:  # noqa: BLE001
                log.error("ensure_schema loi: %s", e)
                C_ERR.labels("schema").inc()
            ctx_holder["ctx"] = ctx
            api = ctx.mods.get("api")
            if api and hasattr(api, "build_router"):
                app.include_router(api.build_router(ctx))
            elif api and hasattr(api, "register"):
                api.register(app, ctx)
            task = asyncio.create_task(loop(ctx))
        else:
            log.warning("DATA_KEEPER_ENABLED=false: khong chay vong lap")
        yield
        if task:
            task.cancel()
            await ctx_holder["ctx"].db.close()

    app = FastAPI(title="data-keeper", lifespan=lifespan)
    from tscommon.internal_auth import install_internal_auth
    install_internal_auth(app, "data-keeper")   # X-Internal-Token (INTERNAL_AUTH_MODE off|log|enforce), miễn /healthz /metrics

    @app.get("/healthz")
    async def healthz():
        ctx = ctx_holder.get("ctx")
        return {"ok": True, "enabled": get_settings().enabled, "modules": sorted(ctx.mods) if ctx else [],
                "summary_at": (ctx.summary or {}).get("at") if ctx else None}

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def main() -> None:
    setup_logging()
    uvicorn.run(create_app({}), host="0.0.0.0", port=get_settings().port, log_level="warning")  # noqa: S104


if __name__ == "__main__":
    main()
