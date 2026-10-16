import asyncio
import logging

import fakeredis.aioredis
import pytest

from tscommon import STREAMS, Bus, make_event, setup_logging


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


def test_streams_has_news_enriched():
    assert STREAMS["news_enriched"] == "news.enriched"


def test_streams_has_expert_profiles():
    assert STREAMS["expert_profiles"] == "expert.profiles"


async def test_consume_nonblocking_terminates(bus):
    for i in range(3):
        await bus.publish("t.s", make_event("x", "src", {"i": i}))
    got = []

    async def run():
        async for mid, ev in bus.consume("t.s", "g", "c", block_ms=0):
            got.append(ev.payload["i"])
            await bus.ack("t.s", "g", mid)

    await asyncio.wait_for(run(), 5)  # không treo
    assert got == [0, 1, 2]
    await asyncio.wait_for(run(), 5)  # đã ack hết -> kết thúc ngay, rỗng
    assert got == [0, 1, 2]


async def test_consume_nonblocking_batches_with_count(bus):
    for i in range(5):
        await bus.publish("t.b", make_event("x", "src", {"i": i}))
    got = [ev.payload["i"] async for _m, ev in bus.consume("t.b", "g", "c", block_ms=None, count=2)]
    assert got == [0, 1, 2, 3, 4]


async def test_consume_once(bus):
    assert await bus.consume_once("t.o", "g", "c") == []
    await bus.publish("t.o", make_event("x", "src", {"a": 1}))
    items = await bus.consume_once("t.o", "g", "c")
    assert len(items) == 1 and items[0][1].payload == {"a": 1}
    assert await bus.consume_once("t.o", "g", "c") == []


def test_setup_logging_quiets_httpx_and_probe_access():
    setup_logging("INFO")
    assert logging.getLogger("httpx").level == logging.WARNING
    f = logging.getLogger("uvicorn.access").filters[0]
    mk = lambda m: logging.LogRecord("uvicorn.access", logging.INFO, "", 0, m, None, None)  # noqa: E731
    assert not f.filter(mk('127.0.0.1:1 - "GET /healthz HTTP/1.1" 200'))
    assert not f.filter(mk('1.2.3.4:5 - "GET /metrics HTTP/1.1" 200'))
    assert f.filter(mk('1.2.3.4:5 - "GET /v1/bars HTTP/1.1" 200'))


async def test_reclaim_orphans_from_dead_consumer(bus):
    for i in range(100):
        await bus.publish("t.r", make_event("x", "src", {"i": i}))
    got_a = await bus.consume_once("t.r", "g", "A", count=100)  # A nhận 100 rồi "chết" không ack
    assert len(got_a) == 100
    assert await bus.consume_once("t.r", "g", "B", count=100) == []  # B không thấy tin mới
    rec = await bus.reclaim("t.r", "g", "B", min_idle_ms=0, count=1000)
    assert sorted(ev.payload["i"] for _, ev, _ in rec) == list(range(100))
    assert all(n == 2 for _, _, n in rec)  # đã giao 2 lần (A rồi B)
    for mid, _, _ in rec:
        await bus.ack("t.r", "g", mid)
    assert (await bus.r.xpending("t.r", "g"))["pending"] == 0
    assert await bus.reclaim("t.r", "g", "B", min_idle_ms=0) == []


async def test_reclaim_respects_min_idle(bus):
    await bus.publish("t.i", make_event("x", "src", {}))
    await bus.consume_once("t.i", "g", "A")
    assert await bus.reclaim("t.i", "g", "B", min_idle_ms=60_000) == []


async def test_reclaim_poison_goes_to_dlq_after_max_deliveries(bus):
    await bus.publish("t.p", make_event("x", "src", {}))
    await bus.consume_once("t.p", "g", "A")
    for _ in range(2):  # lần 2,3 vẫn trả về (không ack = xử lý lỗi)
        assert len(await bus.reclaim("t.p", "g", "B", min_idle_ms=0, max_deliveries=3)) == 1
    assert await bus.reclaim("t.p", "g", "B", min_idle_ms=0, max_deliveries=3) == []  # lần 4 > 3 -> dlq
    dl = await bus.r.xrange("dlq")
    assert len(dl) == 1 and dl[0][1]["reason"].startswith("max_deliveries")
    assert dl[0][1]["stream"] == "t.p"
    assert (await bus.r.xpending("t.p", "g"))["pending"] == 0


async def test_reclaim_undecodable_goes_to_dlq(bus):
    await bus.ensure_group("t.d", "g")
    await bus.r.xadd("t.d", {"e": "{not json"})
    await bus.r.xreadgroup("g", "A", {"t.d": ">"})
    assert await bus.reclaim("t.d", "g", "B", min_idle_ms=0) == []
    assert len(await bus.r.xrange("dlq")) == 1


async def test_pending_own_and_prune(bus):
    for i in range(5):
        await bus.publish("t.o", make_event("x", "src", {"i": i}))
    await bus.consume_once("t.o", "g", "A", count=5)
    assert len(await bus.pending_own("t.o", "g", "A")) == 5
    assert await bus.pending_own("t.o", "g", "Z") == []
    await bus.consume_once("t.o", "g", "dead")  # consumer rác không pending
    assert await bus.prune_idle_consumers("t.o", "g", idle_ms=0) >= 1
    assert len(await bus.pending_own("t.o", "g", "A")) == 5  # consumer có pending không bị xoá


async def test_consume_poison_goes_to_dlq_and_batch_continues(bus):
    """QA-RS: tin hỏng giữa lô không được làm sập consume() / mất các tin sau nó."""
    await bus.publish("t.p", make_event("x", "src", {"i": 1}))
    await bus.r.xadd("t.p", {"e": "{not json"})
    await bus.publish("t.p", make_event("x", "src", {"i": 2}))
    got = []
    async for mid, ev in bus.consume("t.p", "g", "c", block_ms=None):
        got.append(ev.payload["i"])
        await bus.ack("t.p", "g", mid)
    assert got == [1, 2]
    assert await bus.r.xlen("dlq") == 1
