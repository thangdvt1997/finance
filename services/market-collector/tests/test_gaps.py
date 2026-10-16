"""Gap registry + lap day, task provider khong chet am tham, validate OHLC/volume."""
import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import httpx
import pytest
from tscommon import Bus, Event

from market_collector.collector import Collector
from market_collector.config import CollectorSettings
from market_collector.errors import PartialData
from market_collector.models import Bar
from market_collector.providers.base import Provider
from market_collector.providers.dukascopy import DukascopyProvider
from market_collector.publisher import Publisher
from market_collector.quality import bar_problem, check_bars
from market_collector.state import StateStore

UTC = timezone.utc
NOW = datetime(2024, 1, 5, 12, 0, tzinfo=UTC)  # thu Sau


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def stream(bus, name):
    return [Event.model_validate_json(f["e"]).payload for _, f in await bus.r.xrange(name)]


def bar(ts, v=1.0, **kw):
    d = dict(o=1.1, h=1.2, l=1.0, c=1.1)
    d.update(kw)
    return Bar("EURUSD", "M1", ts, d["o"], d["h"], d["l"], d["c"], v, "fake")


class Partial(Provider):
    """Ngay 01-02 thieu gio 05h cho den khi `healed`."""
    name, fetch_tfs, chunk, poll_interval, has_quotes = "fake", ["M1"], timedelta(days=1), 0.01, False

    def __init__(self):
        self.healed = False
        self.calls = []

    def supports(self, s):
        return True

    async def fetch_bars(self, symbol, tf, start, end):
        self.calls.append(start)
        bars = [bar(start + timedelta(hours=1))]
        if start == datetime(2024, 1, 2, tzinfo=UTC) and not self.healed:
            raise PartialData("thieu 1 gio", bars, [start + timedelta(hours=5)])
        bars.append(bar(start + timedelta(hours=5)))
        return bars


def cfg(**kw):
    return CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], backfill_retry_base=60,
                             error_alert_after=99, **kw)


async def test_partial_chunk_does_not_block_later_days_and_gap_is_filled(bus, tmp_path):
    p, t = Partial(), [NOW]
    col = Collector([p], Publisher(bus), cfg(), StateStore(tmp_path / "s.json"), now=lambda: t[0])
    start = datetime(2024, 1, 1, tzinfo=UTC)
    n = await col.backfill("fake", "EURUSD", start, NOW, resume=True)
    # 01-01, 01-03, 01-04, 01-05: 2 nen; 01-02: 1 nen (thieu)
    assert n == 2 + 1 + 2 + 2 + 2
    assert col.state.get("fake:EURUSD:M1") == NOW  # moc resume DA di qua chunk thieu (khong ket)
    assert col.backfill_pending == {}
    day2 = datetime(2024, 1, 2, tzinfo=UTC)
    assert list(col.gaps[("fake", "EURUSD", "M1")]) == [day2]
    assert await col.fill_gaps(p) == 0  # provider van loi -> fails++ & cooldown
    info = col.gaps[("fake", "EURUSD", "M1")][day2]
    assert info["fails"] == 1 and info["next_try"] == NOW + timedelta(seconds=60)
    p.calls.clear()
    assert await col.fill_gaps(p) == 0 and p.calls == []  # dang cooldown
    p.healed = True
    t[0] = NOW + timedelta(seconds=61)
    assert await col.fill_gaps(p) == 1
    assert col.gaps == {}
    assert p.calls == [day2]  # chi tai lai dung ngay thieu


async def test_stuck_gap_raises_single_aggregated_alert(bus):
    p, t = Partial(), [NOW]
    col = Collector([p], Publisher(bus), cfg(gap_alert_after=3600), now=lambda: t[0])
    col._add_gap_days(p, "EURUSD", "M1", {datetime(2024, 1, 2, tzinfo=UTC)})
    col._add_gap_days(p, "EURUSD", "M1", {datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC)})
    await col.fill_gaps(p)
    gap_alerts = lambda al: [x for x in al if x["dedupe_key"].startswith("mc:gap")]  # noqa: E731
    assert gap_alerts(await stream(bus, "alerts.out")) == []
    t[0] = NOW + timedelta(hours=2)
    await col.fill_gaps(p)
    a = gap_alerts(await stream(bus, "alerts.out"))
    assert a and all(x["dedupe_key"] == "mc:gap:fake" for x in a)
    assert "2 ngay" in a[0]["title"] or "1 ngay" in a[0]["title"]


async def test_duka_find_missing_days_uses_cache(tmp_path):
    p = DukascopyProvider(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
                          tmp_path, rate_per_sec=1000)
    now = datetime(2024, 1, 10, 12, tzinfo=UTC)  # thu Tu
    start = datetime(2024, 1, 8, tzinfo=UTC)  # thu Hai
    for h in range(24):  # cache day du 01-08 (gio 404 = file rong cung tinh la da co)
        path = p._cache_path("EURUSD", start + timedelta(hours=h))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    days = p.find_missing_days("EURUSD", "M1", start, now)
    assert days == [datetime(2024, 1, 9, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC)]
    # cuoi tuan khong bi tinh la thieu
    assert p.find_missing_days("EURUSD", "M1", datetime(2024, 1, 6, tzinfo=UTC),
                               datetime(2024, 1, 7, 20, tzinfo=UTC)) == []
    # gio chua dong (<2h) khong bi tinh
    assert p.find_missing_days("EURUSD", "M1", datetime(2024, 1, 10, 10, tzinfo=UTC),
                               datetime(2024, 1, 10, 11, 30, tzinfo=UTC)) == []


async def test_detect_gaps_then_fill(bus):
    class P(Partial):
        def __init__(self):
            super().__init__()
            self.missing = [datetime(2024, 1, 3, tzinfo=UTC)]

        def find_missing_days(self, symbol, tf, start, end):
            return list(self.missing)

        async def fetch_bars(self, symbol, tf, start, end):
            self.calls.append(start)
            self.missing = []
            return [bar(start + timedelta(hours=1))]

    p = P()
    col = Collector([p], Publisher(bus), cfg(), now=lambda: NOW)
    assert col.detect_gaps(p) == 1
    assert col.detect_gaps(p) == 0  # khong dem lai
    assert await col.fill_gaps(p) == 1 and col.gaps == {}
    assert col.detect_gaps(p) == 0


async def test_provider_task_survives_publisher_failure(bus):
    """Redis rot giua chung (vd bi recreate) KHONG duoc giet vong lap provider; tiep tuc o chu ky sau."""
    class P(Provider):
        name, fetch_tfs, chunk, poll_interval, has_quotes = "fake", ["M1"], timedelta(days=1), 0.01, False

        def supports(self, s):
            return True

        async def fetch_bars(self, symbol, tf, start, end):
            return [bar(end - timedelta(minutes=5))]

    class FlakyPub(Publisher):
        fail = 3

        async def bars(self, bars):
            if self.fail > 0:
                self.fail -= 1
                raise ConnectionError("redis down")
            return await super().bars(bars)

    c = CollectorSettings(symbols={"fake": ["EURUSD"]}, output_tfs=["M1"], backfill_on_start=False)
    col = Collector([P()], FlakyPub(bus), c, now=lambda: NOW)
    col.start()
    for _ in range(100):
        await asyncio.sleep(0.02)
        if await bus.r.xlen("md.bars"):
            break
    alive = [t for t in col.tasks if not t.done()]
    await col.stop()
    assert await bus.r.xlen("md.bars") >= 1
    assert alive, "task provider khong duoc chet"


async def test_supervisor_restarts_crashed_loop(bus):
    class P(Provider):
        name, fetch_tfs, poll_interval, has_quotes = "fake", ["M1"], 0.01, False

        def supports(self, s):
            return True

        async def fetch_bars(self, *a):
            return []

    async def nosleep(_):
        await asyncio.sleep(0)

    c = CollectorSettings(symbols={"fake": ["EURUSD"]}, backfill_on_start=False)
    col = Collector([P()], Publisher(bus), c, now=lambda: NOW, sleep=nosleep)
    calls = []
    orig = col._provider_loop

    async def boom(provider):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("boom")
        await orig(provider)

    col._provider_loop = boom
    col.start()
    await asyncio.sleep(0.2)
    await col.stop()
    assert len(calls) == 3 and col.loop_restarts["fake"] == 2


# ---------- validate OHLC / volume ----------
def test_bar_problem_rules():
    t = NOW
    assert bar_problem(bar(t)) is None
    assert bar_problem(bar(t, o=5, h=1, l=9, c=100))[0] == "invalid_ohlc"
    assert bar_problem(bar(t, l=1.15))[0] == "invalid_ohlc"  # low > min(o,c)
    assert bar_problem(bar(t, h=1.05))[0] == "invalid_ohlc"  # high < max(o,c)
    assert bar_problem(bar(t, v=-5))[0] == "invalid_volume"
    assert bar_problem(bar(t, v=float("nan")))[0] == "invalid_volume"
    assert bar_problem(bar(t, o=0.0, l=0.0))[0] == "nonpositive"
    assert bar_problem(bar(t, c=float("inf")))[0] == "nonpositive"
    clean, issues = check_bars([bar(t), bar(t + timedelta(minutes=1), v=-1)])
    assert len(clean) == 1 and issues[0].kind == "invalid_volume"


async def test_invalid_bars_rejected_with_metric_and_single_alert(bus):
    from market_collector.publisher import BARS_REJECTED

    col = Collector([Partial()], Publisher(bus), cfg(), now=lambda: NOW)
    prov = col.providers["fake"]
    before = BARS_REJECTED.labels("fake", "invalid_volume")._value.get()
    bars = [bar(NOW - timedelta(minutes=i), v=-1) for i in range(1, 6)] + [bar(NOW - timedelta(minutes=10))]
    n = await col.process(prov, "EURUSD", "M1", bars)
    assert n == 1
    assert BARS_REJECTED.labels("fake", "invalid_volume")._value.get() - before == 5
    al = await stream(bus, "alerts.out")
    assert len(al) == 1 and "invalid_volume" in al[0]["title"] and "5 van de" in al[0]["body"]
    # chot chan cuoi o publisher
    assert await Publisher(bus).bars([bar(NOW, v=-3), bar(NOW, o=9, h=1)]) == 0
