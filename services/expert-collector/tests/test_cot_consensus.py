"""COT (expert.positions 'CFTC:<ma>' tu news-collector) tham gia dong thuan co trong so track-record; pair_direction=-1 dao dau."""
import json
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest
from tscommon import Bus, make_event
from tscommon.bus import STREAMS

from expert_collector.collector import Collector
from expert_collector.config import ECConfig

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def put_cot(bus, code, symbol, net, pair_dir=1, as_of="2026-10-06T00:00:00+00:00"):
    await bus.publish(STREAMS["expert_positions"], make_event("expert_position", "news-collector", {
        "expert_id": f"CFTC:{code}", "source": "cftc", "symbol": symbol, "net_volume": net, "avg_price": None, "as_of": as_of,
        "raw": {"pair_direction": pair_dir}}))


async def stream(bus, name):
    return [json.loads(f["e"]) for _, f in await bus.r.xrange(name)]


def make(bus):
    cfg = ECConfig(consensus_min_experts=1, consensus_min_ratio=0.5)
    return Collector([], bus, cfg, now=lambda: NOW)


async def test_cot_inverts_jpy_and_registers_expert(bus):
    await put_cot(bus, "097741", "USDJPY", 20000, pair_dir=-1)   # long JPY futures -> SELL USDJPY
    await put_cot(bus, "099741", "EURUSD", 15000, pair_dir=1)    # long EUR futures -> BUY EURUSD
    await put_cot(bus, "088691", "XAUUSD", -5000, pair_dir=1)
    c = make(bus)
    await c._ingest_cot()
    assert json.loads(await bus.r.hget("ec:stances:CFTC:097741", "USDJPY"))["side"] == "sell"
    assert json.loads(await bus.r.hget("ec:stances:CFTC:099741", "EURUSD"))["side"] == "buy"
    assert json.loads(await bus.r.hget("ec:stances:CFTC:088691", "XAUUSD"))["side"] == "sell"
    rec = json.loads(await bus.r.hget("ec:experts", "CFTC:097741"))
    assert rec["tracked"] is True and rec["source"] == "cftc" and "tham khao" in rec["reputation"]["note"].lower()


async def test_cot_stale_report_dropped(bus):
    await put_cot(bus, "099741", "EURUSD", 15000, as_of="2026-09-20T00:00:00+00:00")
    c = make(bus)
    await c._ingest_cot()
    assert await bus.r.hgetall("ec:stances:CFTC:099741") == {}


async def test_cot_weight_changes_consensus(bus):
    await put_cot(bus, "099741", "EURUSD", 15000)
    c = make(bus)
    await c._check_consensus()
    alerts = await stream(bus, "alerts.out")
    assert len(alerts) == 1 and "COT" in alerts[0]["payload"]["body"] and "1.00/1.00" in alerts[0]["payload"]["body"]  # khong co track-record -> w=1.0
    # co trong so thap tu track-record (0.4): tong trong so 0.4 < min_weight(1) -> KHONG dong thuan
    r = bus.r
    await r.delete("ec:seen:alert:consensus:EURUSD:buy:2026-10-12")
    await r.hset("tr:weights", "CFTC:099741", json.dumps({"w": 0.4, "score": 0.4, "n": 30, "status": "rated", "hit": 0.4, "beats": False}))
    c2 = make(bus)
    await c2._check_consensus()
    assert len(await stream(bus, "alerts.out")) == 1  # van chi 1 alert cu, khong them
    assert c2.tw._snap["CFTC:099741"]["weight"] == 0.4


async def test_cot_weight_ge_one_alerts_with_weight_text(bus):
    await put_cot(bus, "099741", "EURUSD", 15000)
    await bus.r.hset("tr:weights", "CFTC:099741", json.dumps({"w": 1.8, "score": 0.9, "n": 40, "status": "rated", "hit": 0.64, "beats": True}))
    c = make(bus)
    await c._check_consensus()
    body = (await stream(bus, "alerts.out"))[0]["payload"]["body"]
    assert "1.80/1.80" in body and "Chi tham khao" in body


async def test_cot_state_survives_stream_trim(bus):
    await put_cot(bus, "099741", "EURUSD", 15000)
    c = make(bus)
    await c._ingest_cot()
    await bus.r.delete(STREAMS["expert_positions"])   # stream bi cat theo thoi gian
    await bus.r.delete("ec:stances:CFTC:099741")
    await c._ingest_cot()
    assert json.loads(await bus.r.hget("ec:stances:CFTC:099741", "EURUSD"))["side"] == "buy"
