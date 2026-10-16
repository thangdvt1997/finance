from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Query, Request
from tscommon import Bus, make_app

from . import __version__
from .client_routes import install as install_client_routes
from .evaluator import Evaluator, MarketState
from .limits_runner import LimitWatcher
from .notifications import Notifier
from .models import LIMITS, MAX_RULES_USER, Prefs, PrefsIn, PushSubIn, PushUnsubIn, RuleIn
from .runner import Runner
from .scope import CLIENT_CHANNELS, FORBIDDEN, Scope, clientize, require_user, scope_dep
from .store import Conflict, LimitReached, event_out, rule_out
from .webpush import PushError, PushService

log = logging.getLogger("alert_rules.app")

UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
GROUP = "alert-rules"


def _epoch(v, default: float) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return default


async def _supervised(factory, name: str, backoff_s: float = 3.0) -> None:
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("%s lỗi, chạy lại sau %.0fs", name, backoff_s)
            await asyncio.sleep(backoff_s)


async def _quotes_loop(bus: Bus, runner: Runner, consumer: str) -> None:
    # Group tạo ở '$': chỉ quan tâm giá từ bây giờ (không đọc lại 24h lịch sử stream).
    with contextlib.suppress(Exception):
        await bus.r.xgroup_create("md.quotes", GROUP, id="$", mkstream=True)
    async for msg_id, ev in bus.consume("md.quotes", GROUP, consumer, block_ms=2000, count=500):
        p = ev.payload
        if p.get("symbol"):
            await runner.on_quote(p["symbol"], p.get("bid"), p.get("ask"), _epoch(p.get("ts"), ev.ts.timestamp()), p.get("source"))
        await bus.ack("md.quotes", GROUP, msg_id)


async def _delivery_loop(bus: Bus, store, consumer: str) -> None:
    with contextlib.suppress(Exception):
        await bus.r.xgroup_create("alerts.delivery", GROUP, id="$", mkstream=True)
    async for msg_id, ev in bus.consume("alerts.delivery", GROUP, consumer, block_ms=2000):
        p = ev.payload
        if p.get("alert_event_id"):
            await store.set_delivered(p["alert_event_id"], bool(p.get("delivered")))
        await bus.ack("alerts.delivery", GROUP, msg_id)


async def _tick_loop(runner: Runner, interval: float) -> None:
    while True:
        try:
            await runner.tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("tick lỗi")
        await asyncio.sleep(interval)


def _store_dep(request: Request):
    return request.app.state.store


Store = Annotated[object, Depends(_store_dep)]
Sc = Annotated[Scope, Depends(scope_dep)]


async def _purge_loop(push: PushService, interval: float = 3600.0) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            n = await push.store.purge_subscriptions()
            if n:
                log.info("dọn %d đăng ký push chết", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("purge push lỗi")


def create_app(store=None, provider=None, redis=None, start_background: bool = True, tick_s: float = 5.0, push: PushService | None = None,
               clock=None, limits_tick_s: float = 30.0):
    app = make_app("alert-rules", __version__, internal_auth=True)
    app.state.store = store
    app.state.push = push
    app.state.clock = clock or time.time
    started = {"t": time.time()}

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        own_store = own_prov = own_redis = False
        if _app.state.store is None:
            from .store import PgStore
            _app.state.store = await PgStore.connect(os.environ["USERCONF_DB_RW_URL"])
            own_store = True
        prov = provider
        if prov is None and start_background:
            from .market import PgMarket
            prov = await PgMarket.connect(os.environ["DATABASE_URL"])
            own_prov = True
        r = redis
        if r is None and start_background:
            r = aioredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
            own_redis = True
        bus = Bus(r) if r is not None else None
        if _app.state.push is None:
            _app.state.push = PushService.from_env(_app.state.store)
        notifier = Notifier(_app.state.store, _app.state.push, _app.state.clock)
        runner = Runner(_app.state.store, Evaluator(prov, MarketState()), bus, push=_app.state.push, notifier=notifier)
        _app.state.runner, _app.state.notifier = runner, notifier
        _app.state.watcher = watcher = LimitWatcher(_app.state.store, prov, notifier, _app.state.clock)
        tasks = []
        if start_background and _app.state.push.enabled:
            tasks.append(asyncio.create_task(_purge_loop(_app.state.push)))
        if start_background:
            tasks.append(asyncio.create_task(_tick_loop(watcher, limits_tick_s)))
        if start_background and bus:
            cons = os.environ.get("CONSUMER_NAME", "alert-rules-1")
            tasks += [asyncio.create_task(_supervised(lambda: _quotes_loop(bus, runner, cons), "quotes")),
                      asyncio.create_task(_supervised(lambda: _delivery_loop(bus, _app.state.store, cons), "delivery")),
                      asyncio.create_task(_tick_loop(runner, tick_s))]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if own_store:
                await _app.state.store.close()
            if own_prov:
                await prov.close()
            if own_redis:
                await r.aclose()

    app.router.lifespan_context = lifespan
    from .internal_notify import router as internal_router
    app.include_router(internal_router)

    def out(row: dict, sc: Scope | None = None) -> dict:
        return rule_out(row, master=not (sc and sc.is_client))

    def push_svc(request: Request) -> PushService:
        return request.app.state.push

    @app.get("/status")
    async def status(request: Request):
        rules = await request.app.state.store.list_rules()
        return {"rules": len(rules), "active": sum(1 for r in rules if out(r)["status"] == "active"),
                "uptime_s": int(time.time() - started["t"]), "quotes_tracked": len(request.app.state.runner.ev.state.quotes)}

    # ---- Quy tắc: client CHỈ thấy/sửa/xoá quy tắc của chính mình (không khớp chủ sở hữu -> 404, như không tồn tại); master/service thấy tất cả ----
    @app.get("/rules")
    async def list_rules(store: Store, sc: Sc):
        if sc.is_client:
            await store.sweep_owner(sc.user_id, sc.accounts)     # quy tắc gắn tài khoản không còn thuộc họ -> tắt
            limits = {**LIMITS, "max_rules": MAX_RULES_USER, "channels": list(CLIENT_CHANNELS)}
        else:
            limits = LIMITS
        return {"items": [out(r, sc) for r in await store.list_rules(sc.owner)], "limits": limits}

    @app.post("/rules", status_code=201)
    async def create_rule(body: RuleIn, store: Store, request: Request, sc: Sc):
        if sc.is_client:
            body = clientize(body, sc.accounts)
        try:
            row = await store.create_rule(body, sc.owner)
        except LimitReached as e:
            raise HTTPException(422, str(e)) from None
        request.app.state.runner.invalidate()
        return out(row, sc)

    @app.post("/rules/preview")
    async def preview_new(body: RuleIn, request: Request, sc: Sc):
        if sc.is_client:
            body = clientize(body, sc.accounts)        # chặn xem số liệu tài khoản người khác qua preview
        return await request.app.state.runner.preview(None, body.spec())

    @app.post("/rules/{rid}/preview")
    async def preview_saved(rid: str, store: Store, request: Request, sc: Sc):
        _check_id(rid)
        row = await store.get_rule(rid, sc.owner)
        if not row:
            raise HTTPException(404, "không có quy tắc này")
        return await request.app.state.runner.preview(rid, row["spec"])

    @app.put("/rules/{rid}")
    async def update_rule(rid: str, body: RuleIn, store: Store, request: Request, sc: Sc):
        _check_id(rid)
        if sc.is_client:
            body = clientize(body, sc.accounts)
        row = await store.update_rule(rid, body, sc.owner)
        if not row:
            raise HTTPException(404, "không có quy tắc này")
        request.app.state.runner.invalidate()
        return out(row, sc)

    @app.delete("/rules/{rid}")
    async def delete_rule(rid: str, store: Store, request: Request, sc: Sc):
        _check_id(rid)
        if not await store.delete_rule(rid, sc.owner):
            raise HTTPException(404, "không có quy tắc này")
        request.app.state.runner.invalidate()
        request.app.state.runner.ev.forget(rid)
        return {"ok": True}

    @app.get("/rule-events")
    async def events(store: Store, sc: Sc, rule_id: Annotated[str | None, Query(pattern=UUID_RE)] = None,
                     limit: Annotated[int, Query(ge=1, le=500)] = 100):
        return {"items": [event_out(e) for e in await store.list_events(rule_id, limit, sc.owner)]}

    # ---- prefs: toàn cục (một người dùng 'admin') -> chỉ master/service ----
    @app.get("/prefs")
    async def get_prefs(store: Store, sc: Sc):
        if sc.is_client:
            raise HTTPException(403, FORBIDDEN)
        return await store.get_prefs()

    @app.put("/prefs")
    async def put_prefs(body: PrefsIn, store: Store, sc: Sc):
        if sc.is_client:
            raise HTTPException(403, FORBIDDEN)
        try:
            prefs = Prefs.model_validate(body.prefs)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"prefs không hợp lệ: {str(e)[:200]}") from None
        try:
            return await store.put_prefs(body.rev, prefs.model_dump(mode="json"))
        except Conflict:
            raise HTTPException(409, "rev") from None

    # ---- Web Push: mỗi người dùng chỉ quản lý đăng ký CỦA MÌNH (owner lấy từ header gateway, không từ body) ----
    @app.get("/push")
    async def push_info(request: Request, store: Store, sc: Sc):
        uid, ps = require_user(sc), push_svc(request)
        return {"enabled": ps.enabled, "public_key": ps.vapid_public if ps.enabled else None, "subscriptions": await store.count_subscriptions(uid)}

    @app.post("/push/subscribe", status_code=201)
    async def push_subscribe(body: PushSubIn, request: Request, sc: Sc):
        uid = require_user(sc)
        try:
            n = await push_svc(request).subscribe(uid, body.endpoint, body.keys.p256dh, body.keys.auth, body.user_agent)
        except PushError as e:
            raise HTTPException(422, str(e)) from None
        return {"ok": True, "subscriptions": n}

    @app.post("/push/unsubscribe")
    async def push_unsubscribe(body: PushUnsubIn, request: Request, sc: Sc):
        uid = require_user(sc)
        return {"ok": True, "subscriptions": await push_svc(request).unsubscribe(uid, body.endpoint)}   # luôn ok: không lộ endpoint của người khác

    @app.post("/push/test")
    async def push_test(request: Request, sc: Sc):
        uid, ps = require_user(sc), push_svc(request)
        if not ps.enabled:
            raise HTTPException(503, "Web Push chưa được bật")
        return {"sent": await ps.notify(uid)}

    install_client_routes(app)
    return app


def _check_id(rid: str) -> None:
    if not re.fullmatch(UUID_RE, rid):
        raise HTTPException(404, "id không hợp lệ")
