import asyncio
import json
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import httpx
import pytest
from tscommon import Bus, Event

from market_collector.app import create_app
from market_collector.collector import Collector
from market_collector.config import CollectorSettings
from market_collector.models import Bar
from market_collector.providers.base import Provider
from market_collector.publisher import Publisher
from market_collector.state import StateStore

UTC = timezone.utc
NOW = datetime(2024, 1, 3, 12, 0, tzinfo=UTC)  # thu Tu


class FakeProvider(Provider):
    name = "fake"
    fetch_tfs = ["M1"]
    chunk = timedelta(days=1)
    lookback = timedelta(hours=2)
    poll_interval = 0.01
    has_quotes = False

    def __init__(self, bars_fn=None, fail=False):
        self.bars_fn, self.fail, self.calls = bars_fn, fail, []

    def supports(self, symbol):
        return True

    async def fetch_bars(self, symbol, tf, start, end):
        self.calls.append((symbol, tf, start, end))
        if self.fail:
            raise RuntimeError("provider down")
        return self.bars_fn(symbol, tf, start, end) if self.bars_fn else []


def gen(symbol, tf, start, end):
    out, t = [], start
    while t < end:
        p = 1.1 + (t - start).total_seconds() / 6e5
        out.append(Bar(symbol, "M1", t, p, p + 1e-4, p - 1e-4, p, 1.0, "fake"))
        t += timedelta(minutes=1)
    return out


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def read(bus, stream):
    res = await bus.r.xrange(stream)
    return [Event.model_validate_json(f["e"]) for _, f in res]


def mk(bus, provider, **cfg):
    s = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1", "M5", "H1"], **cfg)
    return Collector([provider], Publisher(bus), s, now=lambda: NOW), s


async def test_backfill_publishes_resampled_bars(bus):
    col, _ = mk(bus, FakeProvider(gen))
    n = await col.backfill("fake", "EURUSD", datetime(2024, 1, 2, 10, 0, tzinfo=UTC), datetime(2024, 1, 2, 11, 0, tzinfo=UTC))
    # start duoc cat ve 00:00 UTC => chunk 1 ngay; cua so [00:00,11:00) => 660 M1 + 132 M5 + 11 H1
    assert n == 660 + 132 + 11
    evs = await read(bus, "md.bars")
    assert len(evs) == n and evs[0].type == "bar" and evs[0].source == "market-collector"
    tfs = {e.payload["tf"] for e in evs}
    assert tfs == {"M1", "M5", "H1"}
    p = evs[0].payload
    assert set(p) == {"symbol", "tf", "ts_open", "o", "h", "l", "c", "v", "source"} and p["source"] == "fake"
    assert datetime.fromisoformat(p["ts_open"]).tzinfo is not None


async def test_backfill_resume_state(bus, tmp_path):
    prov = FakeProvider(gen)
    st = StateStore(tmp_path / "st.json")
    col, s = mk(bus, prov)
    col.state = st
    start = datetime(2024, 1, 1, tzinfo=UTC)
    await col.backfill("fake", "EURUSD", start, NOW, resume=True)
    assert len(prov.calls) == 3  # 3 chunk ngay (01,02,03)
    assert StateStore(tmp_path / "st.json").get("fake:EURUSD:M1") == NOW
    prov.calls.clear()
    await col.backfill("fake", "EURUSD", start, NOW + timedelta(hours=1), resume=True)
    assert len(prov.calls) == 1 and prov.calls[0][2] == datetime(2024, 1, 3, tzinfo=UTC)  # chi lam phan con lai


async def test_backfill_error_alerts_and_keeps_state(bus, tmp_path):
    col, _ = mk(bus, FakeProvider(fail=True))
    col.state = StateStore(tmp_path / "s.json")
    n = await col.backfill("fake", "EURUSD", datetime(2024, 1, 1, tzinfo=UTC), NOW, resume=True)
    assert n == 0 and col.state.get("fake:EURUSD:M1") is None
    alerts = await read(bus, "alerts.out")
    assert len(alerts) == 1 and alerts[0].payload["level"] == "warn"
    assert alerts[0].payload["dedupe_key"] == "mc:error:fake:EURUSD:M1"


async def test_quality_alert_and_bad_bars_dropped(bus):
    def bad(symbol, tf, s, e):
        t = datetime(2024, 1, 3, 10, 0, tzinfo=UTC)
        return [Bar("EURUSD", "M1", t, 1.1, 1.2, 1.0, 1.1, 1, "fake"),
                Bar("EURUSD", "M1", t + timedelta(minutes=1), 1.1, 1.0, 1.2, 1.1, 1, "fake"),  # OHLC sai
                Bar("EURUSD", "M1", t + timedelta(minutes=2), 1.1, 1.2, 1.0, 1.1, 1, "fake")]

    col, _ = mk(bus, FakeProvider(bad))
    await col.poll_once(col.providers["fake"], "EURUSD")
    bars = await read(bus, "md.bars")
    assert {e.payload["tf"] for e in bars} == {"M1", "M5", "H1"}
    assert sum(1 for e in bars if e.payload["tf"] == "M1") == 2
    al = await read(bus, "alerts.out")
    assert [a.payload["title"].endswith("invalid_ohlc") for a in al] == [True]
    assert al[0].payload["dedupe_key"] == "mc:quality:fake:EURUSD:M1:invalid_ohlc"


async def test_empty_alert_after_threshold_only_when_market_open(bus):
    col, _ = mk(bus, FakeProvider(lambda *a: []), empty_alert_after=3)
    prov = col.providers["fake"]
    for _ in range(5):
        await col.poll_once(prov, "EURUSD")
    al = await read(bus, "alerts.out")
    assert len(al) == 1 and al[0].payload["dedupe_key"] == "mc:empty:fake:EURUSD:M1"  # dung 1 lan, khong spam

    # cuoi tuan (thi truong dong) -> khong dem
    sat = datetime(2024, 1, 6, 12, tzinfo=UTC)
    col2 = Collector([FakeProvider(lambda *a: [])], Publisher(bus), CollectorSettings(symbols={"fake": ["EURUSD"]}, empty_alert_after=1),
                     now=lambda: sat)
    await col2.poll_once(col2.providers["fake"], "EURUSD")
    assert len(await read(bus, "alerts.out")) == 1


async def test_empty_counter_resets_on_data(bus):
    state = {"empty": True}
    col, _ = mk(bus, FakeProvider(lambda s, t, a, b: [] if state["empty"] else gen(s, t, NOW - timedelta(minutes=5), NOW)),
                empty_alert_after=3)
    prov = col.providers["fake"]
    await col.poll_once(prov, "EURUSD"); await col.poll_once(prov, "EURUSD")
    state["empty"] = False
    await col.poll_once(prov, "EURUSD")
    state["empty"] = True
    await col.poll_once(prov, "EURUSD"); await col.poll_once(prov, "EURUSD")
    assert await read(bus, "alerts.out") == []


async def test_scheduler_runs_backfill_then_polls(bus):
    prov = FakeProvider(gen)
    s = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], backfill_days=1, backfill_on_start=True)
    col = Collector([prov], Publisher(bus), s, now=lambda: NOW)
    col.start()
    for _ in range(100):
        await asyncio.sleep(0.02)
        if len(prov.calls) >= 4:
            break
    await col.stop()
    assert len(prov.calls) >= 4  # backfill (>=2 chunk) + >=2 poll
    assert len(await read(bus, "md.bars")) > 0


# ---------------- HTTP ----------------
async def test_http_endpoints_and_backfill_auth(bus):
    prov = FakeProvider(gen)
    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], backfill_token="s3cret")
    col = Collector([prov], Publisher(bus), cfg, now=lambda: NOW)
    app = create_app(cfg, collector=col, run_scheduler=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/healthz")).json()["status"] == "ok"
            assert b"mc_bars_published_total" in (await c.get("/metrics")).content
            body = {"provider": "fake", "symbol": "eur/usd", "start": "2024-01-03T00:00:00Z", "end": "2024-01-03T01:00:00Z"}
            assert (await c.post("/backfill", json=body)).status_code == 401
            assert (await c.post("/backfill", json=body, headers={"X-Backfill-Token": "bad"})).status_code == 401
            bad = dict(body, provider="nope")
            assert (await c.post("/backfill", json=bad, headers={"X-Backfill-Token": "s3cret"})).status_code == 404
            r = await c.post("/backfill", json=body, headers={"X-Backfill-Token": "s3cret"})
            assert r.status_code == 202
            job = r.json()["job_id"]
            for _ in range(100):
                st = (await c.get("/status")).json()["jobs"][job]
                if st["state"] != "running":
                    break
                await asyncio.sleep(0.02)
            assert st["state"] == "done" and st["symbol"] == "EURUSD" and st["bars"] == 60
    assert len(await read(bus, "md.bars")) == 60


async def test_backfill_disabled_without_token(bus):
    cfg = CollectorSettings(symbols={}, backfill_token="")
    col = Collector([FakeProvider()], Publisher(bus), cfg)
    app = create_app(cfg, collector=col, run_scheduler=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/backfill", json={"provider": "fake", "symbol": "EURUSD", "start": "2024-01-01T00:00:00Z"},
                             headers={"X-Backfill-Token": ""})
            assert r.status_code == 503
