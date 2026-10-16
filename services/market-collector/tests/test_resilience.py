"""Dukascopy 503/404, Retry-After, backfill resume + retry, khong alert rong nham."""
import lzma
import struct
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import httpx
import pytest
from tscommon import Bus, Event

from market_collector.collector import Collector
from market_collector.config import CollectorSettings
from market_collector.errors import PartialData, ServiceUnavailable
from market_collector.models import Bar
from market_collector.providers.base import Provider, parse_retry_after
from market_collector.providers.dukascopy import DukascopyProvider
from market_collector.publisher import Publisher
from market_collector.state import StateStore

UTC = timezone.utc


def make_bi5(rows):
    raw = b"".join(struct.pack(">IIIff", *r) for r in rows)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


DATA = make_bi5([(0, 110005, 110000, 1, 1), (60_000, 110015, 110010, 1, 1)])


class Sleeps:
    def __init__(self):
        self.calls = []

    async def __call__(self, s):
        self.calls.append(s)


def prov(handler, tmp_path, sleeps=None, **kw):
    c = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DukascopyProvider(c, tmp_path, rate_per_sec=1000, sleep=sleeps or Sleeps(), **kw)


def test_parse_retry_after():
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after(None) is None and parse_retry_after("abc") is None
    future = (datetime.now(UTC) + timedelta(seconds=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert 60 < parse_retry_after(future) <= 91


async def test_503_respects_retry_after_then_ok(tmp_path):
    n, sl = [], Sleeps()
    h0 = datetime(2024, 1, 2, 10, tzinfo=UTC)

    def handler(req):
        n.append(1)
        if len(n) == 1:
            return httpx.Response(503, headers={"Retry-After": "40"})
        return httpx.Response(200, content=DATA)

    p = prov(handler, tmp_path, sl)
    bars = await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=1))
    assert len(bars) == 2 and len(n) == 2
    assert any(s >= 40 for s in sl.calls)  # ton trong Retry-After


async def test_backoff_has_jitter_and_grows(tmp_path):
    sl = Sleeps()
    p = prov(lambda r: httpx.Response(503), tmp_path, sl)
    h0 = datetime(2024, 1, 2, 10, tzinfo=UTC)
    with pytest.raises(PartialData):
        await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=1))
    delays = [s for s in sl.calls if s >= 2]
    assert len(delays) >= 4 and max(delays) > min(delays)
    assert p._pace > 0  # throttle thich ung da tang


async def test_404_is_empty_not_error_and_cached(tmp_path):
    n = []

    def handler(r):
        n.append(1)
        return httpx.Response(404)

    p = prov(handler, tmp_path)
    h0 = datetime(2024, 1, 2, 10, tzinfo=UTC)  # da dong -> cache
    assert await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=2)) == []
    k = len(n)
    assert await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=2)) == []
    assert len(n) == k  # 404 da cache


async def test_partial_keeps_cached_hours_and_resumes(tmp_path):
    """Gio 11h 503 lan dau; gio 10h da cache -> lan 2 chi tai 11h."""
    seen, fail11 = [], [True]

    def handler(req):
        seen.append(req.url.path)
        if "/11h_" in req.url.path and fail11[0]:
            return httpx.Response(503)
        return httpx.Response(200, content=DATA)

    p = prov(handler, tmp_path)
    h0 = datetime(2024, 1, 2, 10, tzinfo=UTC)
    with pytest.raises(PartialData) as ei:
        await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=2))
    assert len(ei.value.bars) == 2 and ei.value.missing == [h0 + timedelta(hours=1)]
    fail11[0] = False
    seen.clear()
    bars = await p.fetch_bars("EURUSD", "M1", h0, h0 + timedelta(hours=2))
    assert len(bars) == 4 and all("/11h_" in s for s in seen)


def test_expects_data_holidays(tmp_path):
    p = prov(lambda r: httpx.Response(404), tmp_path)
    assert not p.expects_data(datetime(2024, 12, 25, 12, tzinfo=UTC), "EURUSD")
    assert not p.expects_data(datetime(2025, 1, 1, 12, tzinfo=UTC), "EURUSD")
    assert p.expects_data(datetime(2024, 12, 24, 12, tzinfo=UTC), "EURUSD")


# ---------- Collector ----------
NOW = datetime(2024, 1, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def alerts(bus):
    return [Event.model_validate_json(f["e"]).payload for _, f in await bus.r.xrange("alerts.out")]


class Flaky(Provider):
    name, fetch_tfs, chunk, poll_interval = "fake", ["M1"], timedelta(days=1), 0.01
    has_quotes = False

    def __init__(self):
        self.fail_day = datetime(2024, 1, 2, tzinfo=UTC)
        self.calls = []

    def supports(self, s):
        return True

    async def fetch_bars(self, symbol, tf, start, end):
        self.calls.append(start)
        if start == self.fail_day:
            raise ServiceUnavailable("fake: HTTP 503")
        return [Bar(symbol, "M1", start + timedelta(hours=1), 1.1, 1.2, 1.0, 1.1, 1.0, "fake")]


async def test_backfill_progresses_resumes_and_retries(bus, tmp_path):
    p = Flaky()
    t = [NOW]
    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], backfill_retry_base=60,
                            error_alert_after=3)
    col = Collector([p], Publisher(bus), cfg, StateStore(tmp_path / "s.json"), now=lambda: t[0])
    start = datetime(2024, 1, 1, tzinfo=UTC)
    n = await col.backfill("fake", "EURUSD", start, NOW, resume=True)
    assert n == 1  # chi ngay 01-01 xong
    assert col.state.get("fake:EURUSD:M1") == datetime(2024, 1, 2, tzinfo=UTC)
    assert "fake:EURUSD" in col.backfill_pending
    assert await alerts(bus) == []  # 1 lan 503 -> khong alert
    assert await col.retry_pending_backfills("fake") == 0  # chua den han cooldown
    t[0] = NOW + timedelta(minutes=2)
    p.fail_day = None
    p.calls.clear()
    n = await col.retry_pending_backfills("fake")
    assert n >= 1 and col.backfill_pending == {}
    assert datetime(2024, 1, 1, tzinfo=UTC) not in p.calls  # resume, khong lam lai ngay da xong


class Down(Provider):
    name, fetch_tfs, poll_interval, has_quotes = "fake", ["M1"], 0.01, False

    def supports(self, s):
        return True

    async def fetch_bars(self, *a):
        raise ServiceUnavailable("fake: HTTP 503")


async def test_transient_errors_alert_only_after_threshold(bus):
    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], error_alert_after=3)
    col = Collector([Down()], Publisher(bus), cfg, now=lambda: NOW)
    for _ in range(2):
        await col.poll_once(col.providers["fake"], "EURUSD")
    assert await alerts(bus) == []
    await col.poll_once(col.providers["fake"], "EURUSD")
    a = await alerts(bus)
    assert len(a) == 1 and a[0]["dedupe_key"] == "mc:error:fake:EURUSD:M1"


async def test_503_is_not_counted_as_empty(bus):
    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], empty_alert_after=2, error_alert_after=99)
    col = Collector([Down()], Publisher(bus), cfg, now=lambda: NOW)
    for _ in range(5):
        await col.poll_once(col.providers["fake"], "EURUSD")
    assert all("rong" not in a["title"] for a in await alerts(bus))
    assert not col._empty


async def test_poll_publishes_partial_when_only_latest_hour_missing(bus):
    class P(Provider):
        name, fetch_tfs, poll_interval, has_quotes = "fake", ["M1"], 0.01, False

        def supports(self, s):
            return True

        async def fetch_bars(self, symbol, tf, start, end):
            bars = [Bar(symbol, "M1", NOW - timedelta(hours=3), 1.1, 1.2, 1.0, 1.1, 1.0, "fake")]
            raise PartialData("thieu", bars, [NOW.replace(minute=0)])

    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"])
    col = Collector([P()], Publisher(bus), cfg, now=lambda: NOW)
    assert await col.poll_once(col.providers["fake"], "EURUSD") == 1


async def test_poll_partial_does_not_publish_aggregates_containing_missing_hour(bus):
    """QA vong 4: 503 tam thoi o gio 11 -> khong phat H1/H4 chua gio 11 (truoc day ghi de H4 08:00 day du bang ban thieu)."""
    from tscommon.bus import STREAMS
    t0 = NOW.replace(hour=8, minute=0, second=0, microsecond=0)
    miss = t0 + timedelta(hours=3)

    class P(Provider):
        name, fetch_tfs, poll_interval, has_quotes = "fake", ["M1"], 0.01, False

        def supports(self, s):
            return True

        async def fetch_bars(self, symbol, tf, start, end):
            bars = [Bar(symbol, "M1", t0 + timedelta(minutes=i), 1.1, 1.2, 1.0, 1.1, 1.0, "fake") for i in range(0, 180)]
            raise PartialData("thieu", bars, [miss])

    cfg = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1", "H1", "H4"])
    col = Collector([P()], Publisher(bus), cfg, now=lambda: miss + timedelta(minutes=50))
    await col.poll_once(col.providers["fake"], "EURUSD")
    import json
    msgs = await bus.r.xrange(STREAMS["bars"])
    tfs = [json.loads(f["e"])["payload"]["tf"] for _, f in msgs]
    assert tfs.count("M1") == 180 and tfs.count("H1") == 3 and tfs.count("H4") == 0
