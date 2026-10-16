from __future__ import annotations

import asyncio
import contextlib
import logging
import time

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from tscommon import Bus, make_app, make_event

from . import __version__
from .commands import poll_once
from .config import DEFAULT_ROUTES, DEFAULT_RULES, AlertSettings, load_yaml
from .engine import DELIVERY_STREAM, AlertEngine, AppriseChannel, LogChannel, Router, TelegramChannel, consume_loop
from .recovery import recover_loop
from .rules import RuleEngine
from .telegram import TelegramClient

log = logging.getLogger("alert.app")


def build(settings: AlertSettings, redis, http_client: httpx.AsyncClient | None = None):
    tg = None
    channels = {"log": LogChannel()}
    if settings.telegram_enabled:
        tg = TelegramClient(settings.telegram_token, settings.telegram_chat_id, settings.telegram_api_base, http_client)
        channels["telegram"] = TelegramChannel(tg)
    else:
        log.warning("Thiếu TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID: dùng kênh log")
    if settings.apprise_url_list:
        ap = AppriseChannel(settings.apprise_url_list)
        if ap.configured:
            channels["apprise"] = ap
        else:
            log.warning("APPRISE_URLS không có URL hợp lệ: bỏ kênh apprise")
    routes = load_yaml(settings.routes_file, DEFAULT_ROUTES)["routes"]
    engine = AlertEngine(redis, settings, channels, Router(routes))
    rules = RuleEngine(redis, load_yaml(settings.rules_file, DEFAULT_RULES)["rules"], engine_stats=engine.stats)
    return engine, rules, tg


async def _rules_consumer(bus: Bus, rules: RuleEngine, group: str, consumer: str) -> None:
    async for msg_id, ev in bus.consume("md.bars", group + "-rules", consumer, block_ms=2000):
        await rules.on_bar(ev.payload)
        await bus.ack("md.bars", group + "-rules", msg_id)


def _alert_handler(engine: AlertEngine):
    async def handle(_msg_id, ev) -> None:
        await engine.handle(ev.payload, ev.ts, event_id=ev.id)
    return handle


def _rules_handler(rules: RuleEngine):
    async def handle(_msg_id, ev) -> None:
        await rules.on_bar(ev.payload)
    return handle


async def _rules_ticker(engine: AlertEngine, rules: RuleEngine, interval: float = 30) -> None:
    while True:
        for a in await rules.evaluate():
            await engine.handle(a)
        await asyncio.sleep(interval)


async def _digest_ticker(engine: AlertEngine, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await engine.flush_digest()


async def _telegram_poller(tg: TelegramClient, engine: AlertEngine) -> None:
    offset = None
    while True:
        try:
            offset = await poll_once(tg, engine, offset)
        except Exception:  # noqa: BLE001
            log.exception("telegram poll lỗi")
            await asyncio.sleep(5)


SEVERITY = {"critical": "crit", "crit": "crit", "page": "crit", "warning": "warn", "warn": "warn", "info": "info"}


def alertmanager_to_alerts(body: dict) -> list[dict]:
    """Payload webhook của Alertmanager (v4) -> danh sách payload `alert` theo CONTRACTS."""
    out = []
    for a in body.get("alerts") or []:
        labels, ann = a.get("labels") or {}, a.get("annotations") or {}
        resolved = a.get("status") == "resolved"
        name = labels.get("alertname", "alert")
        level = "info" if resolved else SEVERITY.get(str(labels.get("severity", "warning")).lower(), "warn")
        title = ann.get("summary") or name
        text = ann.get("description") or ""
        tags = ["prometheus", name] + ([labels["service"]] if labels.get("service") else [])
        out.append({"level": level, "title": f"{'ĐÃ HẾT: ' if resolved else ''}{title}",
                    "body": text, "tags": tags,
                    "dedupe_key": f"am:{a.get('fingerprint') or name}:{'resolved' if resolved else 'firing'}"})
    return out


async def _supervised(factory, name: str, backoff_s: float = 2.0) -> None:
    """Chạy lại coroutine khi Redis đứt/recreate (ConnectionError...) thay vì để task chết im lặng trong khi /healthz vẫn OK."""
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logging.getLogger("alert.supervisor").exception("%s lỗi, chạy lại sau %.0fs", name, backoff_s)
            await asyncio.sleep(backoff_s)


def create_app(settings: AlertSettings | None = None, redis=None, start_background: bool = True):
    settings = settings or AlertSettings()
    app = make_app("alert-service", __version__)
    # X-Internal-Token cho mọi đường trừ /webhook/alertmanager (Alertmanager/Gatus không gửi được header tuỳ biến; đường này có Bearer WEBHOOK_TOKEN tuỳ chọn)
    from tscommon.internal_auth import EXEMPT_PATHS, install_internal_auth
    install_internal_auth(app, "alert-service", exempt=EXEMPT_PATHS | {"/webhook/alertmanager"})
    state = {"last_event": None, "started": time.time()}

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        r = redis or aioredis.from_url(settings.redis_url, decode_responses=True)
        engine, rules, tg = build(settings, r)
        _app.state.engine = engine
        _app.state.bus = Bus(r)
        inflight: set = set()

        async def emit_delivery(body: dict) -> None:
            await _app.state.bus.publish(DELIVERY_STREAM, make_event("alert_delivered", "alert-service", body))

        engine.on_delivery = emit_delivery
        tasks = []
        if start_background:
            bus = Bus(r)

            async def touch():
                state["last_event"] = time.time()

            tasks = [
                asyncio.create_task(_supervised(lambda: consume_loop(bus, engine, settings.group, settings.consumer,
                                                                     on_event=touch, inflight=inflight), "consume_loop")),
                asyncio.create_task(_supervised(lambda: _rules_consumer(bus, rules, settings.group, settings.consumer),
                                                "rules_consumer")),
                asyncio.create_task(recover_loop(
                    bus, "alerts.out", settings.group, settings.consumer, _alert_handler(engine),
                    interval_s=settings.reclaim_interval_s, min_idle_ms=settings.reclaim_min_idle_ms,
                    max_deliveries=settings.max_deliveries, skip=inflight)),
                asyncio.create_task(recover_loop(
                    bus, "md.bars", settings.group + "-rules", settings.consumer, _rules_handler(rules),
                    interval_s=settings.reclaim_interval_s, min_idle_ms=settings.reclaim_min_idle_ms,
                    max_deliveries=settings.max_deliveries)),
                asyncio.create_task(_rules_ticker(engine, rules)),
                asyncio.create_task(_digest_ticker(engine, settings.digest_interval_s)),
            ]
            if tg:
                tasks.append(asyncio.create_task(_telegram_poller(tg, engine)))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.aclose()
            if tg:
                await tg.aclose()
            if redis is None:
                await r.aclose()

    app.router.lifespan_context = lifespan

    @app.get("/status")
    async def status():
        eng: AlertEngine = app.state.engine
        return {"stats": await eng.stats(), "telegram": settings.telegram_enabled, "apprise": settings.apprise_url_list != [], "last_event": state["last_event"],
                "queue": eng.dispatcher.snapshot(), "rate_limit_per_min": eng.effective_rate_limit()}

    @app.post("/webhook/alertmanager")
    async def alertmanager_webhook(request: Request):
        """Alertmanager -> alerts.out (đi qua dedupe/rate-limit/Telegram như mọi alert). Token tuỳ chọn."""
        if settings.webhook_token:
            if request.headers.get("authorization", "") != f"Bearer {settings.webhook_token}":
                raise HTTPException(401, "unauthorized")
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, "invalid json") from e
        alerts = alertmanager_to_alerts(body if isinstance(body, dict) else {})
        for p in alerts:
            await app.state.bus.publish("alerts.out", make_event("alert", "alertmanager", p))
        return {"accepted": len(alerts)}

    return app
