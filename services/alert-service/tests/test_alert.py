import asyncio
import json
from datetime import datetime, timezone

import fakeredis.aioredis as fr
import httpx
import pytest
from tscommon import Bus, make_event

from alert_service.app import build, create_app
from alert_service.commands import handle_command, poll_once
from alert_service.config import AlertSettings
from alert_service.engine import AlertEngine, LogChannel, Router, consume_loop
from alert_service.rules import RuleEngine


class Rec:
    name = "telegram"

    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)
        return True


@pytest.fixture
async def redis():
    r = fr.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


def mk(redis, **kw):
    s = AlertSettings(**kw)
    rec = Rec()
    eng = AlertEngine(redis, s, {"log": LogChannel(), "telegram": rec},
                      Router([{"min_level": "info", "channels": ["telegram"]}]))
    return eng, rec


async def test_dedupe(redis):
    eng, rec = mk(redis, dedupe_window_s=60)
    a = {"level": "warn", "title": "X", "dedupe_key": "k1"}
    assert await eng.handle(a) == "sent"
    assert await eng.handle(a) == "deduped"
    assert await eng.handle({**a, "dedupe_key": "k2"}) == "sent"
    assert len(rec.sent) == 2
    assert "CẢNH BÁO" in rec.sent[0]


async def test_rate_limit_and_digest(redis):
    eng, rec = mk(redis, rate_limit_per_min=2)
    res = [await eng.handle({"level": "info", "title": f"t{i % 2}"}) for i in range(5)]
    assert res == ["sent", "sent", "grouped", "grouped", "grouped"]
    assert await eng.handle({"level": "crit", "title": "boom"}) == "sent"  # crit bỏ qua rate limit
    n = await eng.flush_digest()
    assert n == 3
    assert "GOM NHÓM: 3" in rec.sent[-1]
    assert await eng.flush_digest() == 0


async def test_router_levels_and_fallback(redis):
    router = Router([{"min_level": "crit", "channels": ["telegram", "log"]},
                     {"min_level": "warn", "tags_any": ["x"], "channels": ["telegram"]},
                     {"min_level": "info", "channels": ["log"]}])
    assert router.resolve("crit", []) == ["telegram", "log"]
    assert router.resolve("warn", ["x"]) == ["telegram"]
    assert router.resolve("warn", ["y"]) == ["log"]
    # kênh telegram thiếu -> rơi về log
    s = AlertSettings()
    eng = AlertEngine(redis, s, {"log": LogChannel()}, router)
    assert await eng.handle({"level": "crit", "title": "z"}) == "sent"


async def test_silence_rule_and_heartbeat(redis):
    now = [datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)]  # thứ Hai
    rules = [{"name": "r", "type": "stream_silence", "symbols": ["EURUSD"], "max_silence_minutes": 15},
             {"name": "hb", "type": "heartbeat", "at": "01:00"}]
    re = RuleEngine(redis, rules, clock=lambda: now[0])
    out = await re.evaluate()
    assert not [a for a in out if "silence" in a["dedupe_key"]]
    assert any("heartbeat" in a["dedupe_key"] for a in out)
    now[0] = datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc)
    out = await re.evaluate()
    assert any(a["dedupe_key"] == "silence:r:EURUSD" for a in out)
    assert not [a for a in out if "heartbeat" in a["dedupe_key"]]  # heartbeat đã bắn ở lượt đầu
    await re.on_bar({"symbol": "EURUSD", "tf": "M1"})
    out = await re.evaluate()
    assert not any("silence" in a["dedupe_key"] for a in out)
    # cuối tuần không báo
    now[0] = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    assert not [a for a in await re.evaluate() if "silence" in a["dedupe_key"]]


async def test_heartbeat_once_per_day(redis):
    now = datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc)
    re = RuleEngine(redis, [{"name": "hb", "type": "heartbeat", "at": "01:00"}], clock=lambda: now)
    assert len(await re.evaluate()) == 1
    assert len(await re.evaluate()) == 0


async def test_commands_read_only(redis):
    eng, _ = mk(redis)
    await eng.handle({"level": "warn", "title": "Hello"})
    assert "Hello" in await handle_command("/last_alerts 3", eng)
    assert "Tổng xử lý: 1" in await handle_command("/status", eng)
    assert "không được hỗ trợ" in await handle_command("/buy EURUSD", eng)


async def test_telegram_mock_and_poll(redis):
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        calls.append((req.url.path, body))
        if req.url.path.endswith("getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [
                {"update_id": 5, "message": {"text": "/status", "chat": {"id": 42}}},
                {"update_id": 6, "message": {"text": "/status", "chat": {"id": 999}}},  # chat lạ -> bỏ qua
            ]})
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    s = AlertSettings(telegram_token="T", telegram_chat_id="42")
    eng, _, tg = build(s, redis, client)
    assert await eng.handle({"level": "crit", "title": "Down"}) == "sent"
    sends = [c for c in calls if c[0].endswith("sendMessage")]
    assert sends and sends[0][1]["chat_id"] == "42" and "NGHIÊM TRỌNG" in sends[0][1]["text"]
    off = await poll_once(tg, eng, None)
    assert off == 7
    assert len([c for c in calls if c[0].endswith("sendMessage")]) == 2  # 1 alert + 1 reply
    await client.aclose()


async def test_telegram_failure_marks_failed(redis):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    eng, _, _ = build(AlertSettings(telegram_token="T", telegram_chat_id="1"), redis, client)
    assert await eng.handle({"level": "warn", "title": "x"}) == "failed"


class PollBus(Bus):
    """fakeredis treo event loop với XREADGROUP BLOCK -> test dùng polling không block."""

    async def consume(self, stream, group, consumer, block_ms=5000, count=100):
        from tscommon import Event
        await self.ensure_group(stream, group)
        while True:
            res = await self.r.xreadgroup(group, consumer, {stream: ">"}, count=count)
            for _s, msgs in res or []:
                for mid, f in msgs:
                    yield mid, Event.model_validate_json(f["e"])
            await asyncio.sleep(0.02)


async def test_consume_loop_end_to_end(redis):
    eng, rec = mk(redis)
    bus = PollBus(redis)
    await bus.publish("alerts.out", make_event("alert", "t", {"level": "warn", "title": "E2E", "dedupe_key": "a"}))
    await bus.publish("alerts.out", make_event("alert", "t", {"level": "warn", "title": "E2E", "dedupe_key": "a"}))
    task = asyncio.create_task(consume_loop(bus, eng, "alert-service", "c1"))
    for _ in range(50):
        await asyncio.sleep(0.05)
        if (await eng.stats()).get("deduped"):
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(rec.sent) == 1
    assert (await redis.xpending("alerts.out", "alert-service"))["pending"] == 0


async def test_health_metrics(redis):
    app = create_app(AlertSettings(), redis, start_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/healthz")).json()["status"] == "ok"
        assert "alerts_in_total" in (await c.get("/metrics")).text


async def test_delivery_event_emitted(redis):
    eng, rec = mk(redis, rate_limit_per_min=1)
    got = []

    async def cb(body):
        got.append(body)

    eng.on_delivery = cb
    assert await eng.handle({"level": "warn", "title": "A"}, event_id="e1") == "sent"
    assert await eng.handle({"level": "warn", "title": "B"}, event_id="e2") == "grouped"
    assert await eng.handle({"level": "warn", "title": "C"}) == "grouped"  # không có event_id -> không phát
    assert [(g["alert_event_id"], g["delivered"]) for g in got] == [("e1", True)]
    await eng.flush_digest()
    assert [(g["alert_event_id"], g["outcome"]) for g in got] == [("e1", "sent"), ("e2", "digest")]


async def test_delivery_failed_and_callback_error_ignored(redis):
    class Bad:
        name = "telegram"

        async def send(self, text):
            return False

    s = AlertSettings()
    eng = AlertEngine(redis, s, {"log": LogChannel(), "telegram": Bad()},
                      Router([{"min_level": "info", "channels": ["telegram"]}]))
    seen = []

    async def cb(body):
        seen.append(body)
        raise RuntimeError("bus down")

    eng.on_delivery = cb
    assert await eng.handle({"level": "info", "title": "x"}, event_id="e9") == "failed"
    assert seen[0]["delivered"] is False


async def test_consume_loop_passes_event_id(redis):
    eng, _ = mk(redis)
    got = []

    async def cb(body):
        got.append(body["alert_event_id"])

    eng.on_delivery = cb
    bus = Bus(redis)
    ev = make_event("alert", "t", {"level": "warn", "title": "hello"})
    await bus.publish("alerts.out", ev)
    async for mid, e in bus.consume("alerts.out", "g", "c", block_ms=0):
        await eng.handle(e.payload, e.ts, event_id=e.id)
    assert got == [ev.id]


async def test_webhook_alertmanager_publishes_to_stream(redis):
    app = create_app(AlertSettings(webhook_token="tok"), redis=redis, start_background=False)
    payload = {"alerts": [
        {"status": "firing", "fingerprint": "f1", "labels": {"alertname": "ServiceDown", "severity": "critical", "service": "api-gateway"},
         "annotations": {"summary": "api-gateway down", "description": "d"}},
        {"status": "resolved", "fingerprint": "f2", "labels": {"alertname": "Lag"}, "annotations": {}},
    ]}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.post("/webhook/alertmanager", json=payload)).status_code == 401
            r = await c.post("/webhook/alertmanager", json=payload, headers={"Authorization": "Bearer tok"})
            assert r.json() == {"accepted": 2}
    msgs = await redis.xrange("alerts.out")
    evs = [json.loads(f["e"]) for _, f in msgs]
    assert evs[0]["payload"]["level"] == "crit" and "api-gateway" in evs[0]["payload"]["tags"]
    assert evs[1]["payload"]["level"] == "info" and evs[1]["payload"]["title"].startswith("ĐÃ HẾT")


# ---- Apprise (kênh đa dịch vụ; test không cần mạng) ----
class FakeApprise:
    def __init__(self, n=1, ok=True):
        self.n, self.ok, self.calls = n, ok, []

    def __len__(self):
        return self.n

    async def async_notify(self, body, title=""):
        self.calls.append((title, body))
        return self.ok


async def test_apprise_channel_sends_and_reports_failure():
    from alert_service.engine import AppriseChannel
    fa = FakeApprise()
    assert await AppriseChannel([], notifier=fa).send("xin chào") is True
    assert fa.calls and "xin chào" in fa.calls[0][1]
    assert await AppriseChannel([], notifier=FakeApprise(ok=False)).send("x") is False
    assert await AppriseChannel([], notifier=FakeApprise(n=0)).send("x") is False  # chưa có URL hợp lệ


def test_apprise_urls_parsing_and_validation():
    from alert_service.engine import AppriseChannel
    s = AlertSettings(apprise_urls="ntfy://ntfy:80/tradingsys-alerts, tgram://123456:ABCdef/42\nnot-a-url")
    assert len(s.apprise_url_list) == 3
    ch = AppriseChannel(s.apprise_url_list)  # URL hợp lệ được nạp, URL sai bị bỏ (không gọi mạng)
    assert ch.configured and len(ch.notifier) == 2
    assert not AppriseChannel(["rác"]).configured


async def test_build_registers_apprise_and_router_uses_both(redis):
    s = AlertSettings(telegram_token="T", telegram_chat_id="1", apprise_urls="ntfy://ntfy:80/t")
    calls = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (calls.append(r), httpx.Response(200, json={"ok": True}))[1]))
    eng, _, _ = build(s, redis, client)
    assert set(eng.channels) == {"log", "telegram", "apprise"}
    fa = FakeApprise()
    eng.channels["apprise"].notifier = fa
    eng.router = Router([{"min_level": "info", "channels": ["telegram", "apprise"]}])
    assert await eng.handle({"level": "warn", "title": "Hai kênh"}) == "sent"
    assert len(calls) == 1 and len(fa.calls) == 1  # telegram (mock HTTP) + apprise (giả)
    await client.aclose()


async def test_apprise_backup_when_telegram_fails(redis):
    s = AlertSettings(telegram_token="T", telegram_chat_id="1", apprise_urls="ntfy://ntfy:80/t")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    eng, _, _ = build(s, redis, client)
    eng.channels["apprise"].notifier = FakeApprise()
    eng.router = Router([{"min_level": "info", "channels": ["telegram", "apprise"]}])
    assert await eng.handle({"level": "crit", "title": "Telegram chết"}) == "sent"  # ntfy/apprise là kênh dự phòng
    await client.aclose()


async def test_missing_channels_fall_back_to_log_only_once(redis):
    eng, rec = mk(redis)
    eng.router = Router([{"min_level": "info", "channels": ["apprise", "slack"]}])  # không kênh nào được cấu hình
    assert await eng.handle({"level": "warn", "title": "x"}) == "sent"  # rơi về log, không lỗi
    assert rec.sent == []


async def test_commands_still_read_only_with_apprise(redis):
    eng, _ = mk(redis)
    assert "không được hỗ trợ" in await handle_command("/sell EURUSD", eng)


# ---------- dispatcher: đồng thời, ưu tiên, timeout, breaker, backlog ----------
from alert_service.dispatch import CircuitBreaker, Dispatcher  # noqa: E402
from alert_service.recovery import recover_once  # noqa: E402


class Slow:
    def __init__(self, name="telegram", delay=0.05, ok=True):
        self.name, self.delay, self.ok, self.sent, self.calls = name, delay, ok, [], 0

    async def send(self, text):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.ok:
            self.sent.append(text)
        return self.ok


def mk_slow(redis, ch, **kw):
    kw.setdefault("rate_limit_per_min", 10_000)
    kw.setdefault("backlog_digest_threshold", 10_000)
    s = AlertSettings(**kw)
    return AlertEngine(redis, s, {"log": LogChannel(), "telegram": ch},
                       Router([{"min_level": "info", "channels": ["telegram"]}]))


async def test_concurrent_sends_not_serial(redis):
    ch = Slow(delay=0.1)
    eng = mk_slow(redis, ch, send_concurrency=4)
    t0 = asyncio.get_running_loop().time()
    res = await asyncio.gather(*(eng.handle({"level": "warn", "title": f"t{i}"}) for i in range(8)))
    dt = asyncio.get_running_loop().time() - t0
    assert res == ["sent"] * 8
    assert dt < 0.6  # nối tiếp sẽ >= 0.8s
    await eng.aclose()


async def test_crit_jumps_ahead_of_info_backlog(redis):
    ch = Slow(delay=0.03)
    eng = mk_slow(redis, ch, send_concurrency=1)
    infos = [asyncio.create_task(eng.handle({"level": "info", "title": f"i{i}"})) for i in range(20)]
    await asyncio.sleep(0.01)
    crit = asyncio.create_task(eng.handle({"level": "crit", "title": "CRIT"}))
    await asyncio.gather(crit, *infos)
    order = [t.split("\n")[0] for t in ch.sent]
    pos = next(i for i, t in enumerate(order) if "CRIT" in t)
    assert pos <= 2, order  # chỉ chờ tin đang gửi dở, vượt qua ~19 tin info đang xếp hàng
    await eng.aclose()


async def test_timeout_falls_back_to_log_and_reports_failed(redis):
    ch = Slow(delay=5)
    eng = mk_slow(redis, ch, send_timeout_s=0.05)
    t0 = asyncio.get_running_loop().time()
    assert await eng.handle({"level": "warn", "title": "x"}) == "failed"
    assert asyncio.get_running_loop().time() - t0 < 1
    await eng.aclose()


def test_circuit_breaker_states():
    now = [0.0]
    b = CircuitBreaker(threshold=3, cooldown_s=10, max_cooldown_s=40, clock=lambda: now[0])
    for _ in range(3):
        assert b.allow()
        b.record(False)
    assert b.state == "open" and not b.allow()
    now[0] = 10
    assert b.allow() and b.state == "half_open"
    assert not b.allow()  # chỉ 1 request thử
    b.record(False)  # thử hỏng -> mở lại, cooldown nhân đôi
    assert b.state == "open" and b.open_until == 30
    now[0] = 30
    assert b.allow()
    b.record(True)
    assert b.state == "closed" and b.failures == 0 and b.allow()


async def test_breaker_skips_dead_channel_but_log_still_runs(redis):
    now = [0.0]
    ch = Slow(delay=0, ok=False)
    eng = mk_slow(redis, ch, breaker_threshold=3, breaker_cooldown_s=30)
    eng.dispatcher.clock = lambda: now[0]
    for b in eng.dispatcher.breakers.values():
        b.clock = eng.dispatcher.clock
    for _ in range(3):
        assert await eng.handle({"level": "warn", "title": "x"}) == "failed"
    assert ch.calls == 3
    for _ in range(5):  # breaker mở: không gọi kênh chết nữa, trả lỗi ngay
        assert await eng.handle({"level": "warn", "title": "y"}) == "failed"
    assert ch.calls == 3 and eng.dispatcher.snapshot()["breakers"]["telegram"] == "open"
    ch.ok = True
    now[0] = 31  # hết cooldown -> half-open thử 1 lần, thành công -> đóng
    assert await eng.handle({"level": "warn", "title": "z"}) == "sent"
    assert eng.dispatcher.snapshot()["breakers"]["telegram"] == "closed"
    await eng.aclose()


async def test_backlog_diverts_noncrit_to_digest_but_crit_goes(redis):
    ch = Slow(delay=0.05)
    eng = mk_slow(redis, ch, send_concurrency=1, backlog_digest_threshold=3)
    tasks = []
    for i in range(12):
        tasks.append(asyncio.create_task(eng.handle({"level": "info", "title": f"i{i}"})))
        await asyncio.sleep(0)  # cho từng task kịp xếp hàng
        await asyncio.sleep(0)
    crit = await asyncio.create_task(eng.handle({"level": "crit", "title": "C"}))
    res = await asyncio.gather(*tasks)
    assert crit == "sent"
    assert res.count("grouped") >= 6 and res.count("sent") >= 3
    assert await eng.flush_digest() == res.count("grouped")
    await eng.aclose()


async def test_rate_limit_adapts_to_measured_throughput(redis):
    ch = Slow(delay=0.2)
    eng = mk_slow(redis, ch, send_concurrency=2, rate_limit_per_min=100)
    assert eng.effective_rate_limit() == 100  # chưa có số đo
    await eng.handle({"level": "warn", "title": "a"})
    # ~0.2s/tin, 2 luồng => ~600/phút... đủ nhanh nên vẫn giữ cấu hình
    assert eng.effective_rate_limit() == 100
    eng.dispatcher.avg_latency_s = 5.5  # kênh ntfy chậm như QA: 2*60/5.5 = ~21.8/phút -> 80% = 17
    assert eng.effective_rate_limit() == 17
    await eng.aclose()


async def test_orphan_alerts_reclaimed_and_sent_once(redis):
    """Consumer cũ nhận 100 alert rồi chết; consumer mới (tên khác) reclaim và gửi đủ 100, ack hết."""
    ch = Slow(delay=0)
    eng = mk_slow(redis, ch, send_concurrency=4)
    bus = Bus(redis)
    for i in range(100):
        await bus.publish("alerts.out", make_event("alert", "t", {"level": "warn", "title": f"a{i}", "dedupe_key": f"k{i}"}))
    assert len(await bus.consume_once("alerts.out", "alert-service", "old-container", count=100)) == 100

    async def handler(_mid, ev):
        assert await eng.handle(ev.payload, ev.ts, event_id=ev.id) == "sent"

    assert await recover_once(bus, "alerts.out", "alert-service", "new-container", handler, min_idle_ms=0) == 100
    assert len(ch.sent) == 100
    assert (await redis.xpending("alerts.out", "alert-service"))["pending"] == 0
    assert await recover_once(bus, "alerts.out", "alert-service", "new-container", handler, min_idle_ms=0) == 0
    await eng.aclose()


async def test_recover_skips_inflight_and_keeps_failed_pending(redis):
    bus = Bus(redis)
    for i in range(2):
        await bus.publish("alerts.out", make_event("alert", "t", {"level": "info", "title": f"b{i}"}))
    got = await bus.consume_once("alerts.out", "g", "c-old", count=10)
    skip = {got[0][0]}
    seen = []

    async def handler(mid, ev):
        seen.append(mid)
        raise RuntimeError("boom")

    assert await recover_once(bus, "alerts.out", "g", "c-new", handler, min_idle_ms=0, skip=skip) == 0
    assert seen == [got[1][0]]  # tin đang xử lý bị bỏ qua; tin lỗi không ack
    assert (await redis.xpending("alerts.out", "g"))["pending"] == 2


def test_consumer_name_is_stable_not_hostname(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "abc123")
    monkeypatch.delenv("CONSUMER_NAME", raising=False)
    assert AlertSettings().consumer == "alert-1"


async def test_status_exposes_queue_and_metrics(redis):
    app = create_app(AlertSettings(), redis, start_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            st = (await c.get("/status")).json()
            assert "queue" in st and st["queue"]["queued"] == 0
            m = (await c.get("/metrics")).text
            assert "alert_queue_length" in m and "alert_send_seconds" in m


def test_default_routes_risk_window_to_ntfy_and_log():
    from alert_service.config import DEFAULT_ROUTES
    router = Router(DEFAULT_ROUTES["routes"])
    assert router.resolve("warn", ["risk-window", "usd", "pre"]) == ["apprise", "log"]
    assert router.resolve("info", ["risk-window", "usd", "exit"]) == ["apprise", "log"]
    assert router.resolve("crit", ["risk-window"]) == ["telegram", "apprise", "log"]  # crit van uu tien
    assert router.resolve("warn", ["calendar"]) == ["telegram", "apprise"]


def test_default_routes_quality_log_only_and_long_dedupe():
    from alert_service.config import DEFAULT_ROUTES
    router = Router(DEFAULT_ROUTES["routes"])
    assert router.resolve("info", ["market-collector", "quality", "x", "EURUSD"]) == ["log"]
    assert router.resolve("crit", ["quality"]) == ["telegram", "apprise", "log"]


async def test_quality_alert_dedupe_window_6h(redis):
    eng, rec = mk(redis, rate_limit_per_min=100)
    p = {"level": "info", "title": "q", "body": "b", "tags": ["quality"], "dedupe_key": "mc:quality:x:EURUSD:M1:gap"}
    assert await eng.handle(p, event_id="e1") != "deduped"
    assert await redis.ttl("alerts:dedupe:mc:quality:x:EURUSD:M1:gap") > 3600


def test_router_user_channel_tags_override_routes():
    r = Router([{"min_level": "info", "channels": ["telegram"]}])
    assert r.resolve("warn", ["user-rule", "ch:ntfy", "ch:log"]) == ["apprise", "log"]
    assert r.resolve("warn", ["user-rule", "ch:bogus"]) == ["telegram"]
    assert r.resolve("info", ["x"]) == ["telegram"]


# ---- UI_NO_SOURCES: khong gui ten nguon ra ngoai ----
BANNED = ("dukascopy", "yahoo", "frankfurter", "cafef", "reuters", "forexfactory")


async def test_alert_service_scrubs_source_names_before_sending(redis):
    eng, rec = mk(redis, rate_limit_per_min=100)
    p = {"level": "warn", "title": "dukascopy lỗi lấy dữ liệu GBPUSD M1",
         "body": "3 lần lỗi liên tiếp. Nguồn: dukascopy. Xem https://www.reuters.com/x",
         "tags": ["market-collector", "fetch-error", "dukascopy"], "dedupe_key": "mc:error:dukascopy:GBPUSD"}
    assert await eng.handle(p, event_id="e1") == "sent"
    text = rec.sent[0].lower()
    assert "dữ liệu giá gbpusd m1: lỗi cập nhật" in text
    assert not any(b in text for b in BANNED)
    recent = await eng.recent(1)
    assert not any(b in json.dumps(recent).lower() for b in BANNED)


async def test_delivery_event_and_digest_have_no_source_names(redis):
    got = []

    async def on_delivery(body):
        got.append(body)

    s = AlertSettings(rate_limit_per_min=1)
    rec = Rec()
    eng = AlertEngine(redis, s, {"log": LogChannel(), "telegram": rec}, Router([{"min_level": "info", "channels": ["telegram"]}]),
                      on_delivery=on_delivery)
    await eng.handle({"level": "info", "title": "a yahoo_daily"}, event_id="e1")
    await eng.handle({"level": "info", "title": "b Vietstock rss", "body": "Nguồn: vietstock_cophieu", "tags": ["vietstock_cophieu", "x"]}, event_id="e2")
    await eng.flush_digest()
    blob = json.dumps(got).lower() + "\n".join(rec.sent).lower()
    assert "yahoo" not in blob and "vietstock" not in blob
    assert got and all("vietstock" not in json.dumps(g).lower() for g in got)


async def test_dispatcher_last_line_scrub():
    from alert_service.dispatch import Dispatcher
    rec = Rec()
    d = Dispatcher({"telegram": rec, "log": LogChannel()})
    assert await d.send("warn", "Lỗi từ Dukascopy", ["telegram"])
    await d.aclose()
    assert "dukascopy" not in rec.sent[0].lower()
