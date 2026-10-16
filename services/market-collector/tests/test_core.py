from datetime import datetime, timedelta, timezone

import pytest

from market_collector.errors import FatalError, RateLimited, RetryableError
from market_collector.models import Bar, floor_ts
from market_collector.quality import check_bars
from market_collector.ratelimit import RateLimiter
from market_collector.resample import resample
from market_collector.retry import retry_async
from market_collector.symbols import normalize_symbol, parse_symbol_list

UTC = timezone.utc


def m1(ts, o, h, l, c, v=1.0, sym="EURUSD", src="t"):
    return Bar(sym, "M1", ts, o, h, l, c, v, src)


def series(start, n, price=1.1):
    return [m1(start + timedelta(minutes=i), price + i * 1e-4, price + i * 1e-4 + 5e-5, price + i * 1e-4 - 5e-5,
               price + i * 1e-4 + 1e-5) for i in range(n)]


def test_normalize_symbol():
    assert normalize_symbol("eur/usd") == "EURUSD"
    assert normalize_symbol("EURUSD=X") == "EURUSD"
    assert normalize_symbol("vn:vnm") == "VN:VNM"
    assert normalize_symbol(" xau-usd ") == "XAUUSD"
    assert parse_symbol_list("eurusd, EUR/USD ,vn:fpt,") == ["EURUSD", "VN:FPT"]


def test_floor_ts_alignment():
    t = datetime(2024, 1, 2, 7, 33, 20, tzinfo=UTC)
    assert floor_ts(t, "H4") == datetime(2024, 1, 2, 4, tzinfo=UTC)
    assert floor_ts(t, "D1") == datetime(2024, 1, 2, tzinfo=UTC)
    assert floor_ts(t, "M15") == datetime(2024, 1, 2, 7, 30, tzinfo=UTC)


def test_resample_m5_ohlcv():
    t0 = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    bars = series(t0, 10)
    out = resample(bars, "M5")
    assert [b.ts_open for b in out] == [t0, t0 + timedelta(minutes=5)]
    first = out[0]
    assert first.o == bars[0].o and first.c == bars[4].c
    assert first.h == max(b.h for b in bars[:5]) and first.l == min(b.l for b in bars[:5])
    assert first.v == 5.0 and first.tf == "M5"


def test_resample_h4_d1_and_partial_and_unsorted_dups():
    t0 = datetime(2024, 1, 2, 3, 58, tzinfo=UTC)  # bucket H4 04:00 bi cat doi o dau
    bars = series(t0, 6)
    shuffled = [bars[3], bars[0], bars[5], bars[1], bars[2], bars[4], bars[2]]  # co trung
    h4 = resample(shuffled, "H4")
    assert [b.ts_open.hour for b in h4] == [0, 4]
    assert h4[0].v == 2 and h4[1].v == 4
    d1 = resample(shuffled, "D1")
    assert len(d1) == 1 and d1[0].v == 6 and d1[0].o == bars[0].o and d1[0].c == bars[5].c


def test_resample_multi_symbol_and_errors():
    t0 = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)
    a, b = series(t0, 5), [Bar("GBPUSD", "M1", x.ts_open, 1, 2, 0.5, 1.5, 1, "t") for x in series(t0, 5)]
    out = resample(a + b, "M5")
    assert {x.symbol for x in out} == {"EURUSD", "GBPUSD"} and len(out) == 2
    assert resample([], "M5") == []
    h1 = resample(series(t0, 120), "H1")
    with pytest.raises(ValueError):
        resample(h1, "M5")
    with pytest.raises(ValueError):
        resample(h1 + series(t0, 2), "H4")


def test_quality_dupe_invalid_gap_outlier():
    t0 = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)  # thu Ba
    bars = series(t0, 3)
    bars.append(bars[1])  # trung
    bars.append(m1(t0 + timedelta(minutes=3), 1.1, 1.0, 1.2, 1.1))  # h < l
    bars.append(m1(t0 + timedelta(minutes=4), -1, 1, 1, 1))  # gia am
    bars.append(m1(t0 + timedelta(minutes=60), 1.1, 1.11, 1.09, 1.1))  # gap 55 nen
    bars.append(m1(t0 + timedelta(minutes=61), 1.5, 1.6, 1.5, 1.55))  # nhay ~40%
    clean, issues = check_bars(bars)
    kinds = {i.kind for i in issues}
    assert kinds == {"duplicate", "invalid_ohlc", "nonpositive", "gap", "outlier"}
    assert len(clean) == 5 and len({b.ts_open for b in clean}) == 5


def test_quality_weekend_gap_ignored_and_clean_ok():
    fri = datetime(2024, 1, 5, 21, 55, tzinfo=UTC)
    mon = datetime(2024, 1, 7, 22, 0, tzinfo=UTC)
    bars = series(fri, 5) + series(mon, 5)
    _, issues = check_bars(bars)
    assert issues == []
    _, issues2 = check_bars(bars, ignore_weekend=False)
    assert [i.kind for i in issues2] == ["gap"]


async def test_ratelimiter_sliding_window():
    now = [0.0]
    slept = []

    async def fake_sleep(s):
        slept.append(s)
        now[0] += s

    rl = RateLimiter(3, 10.0, clock=lambda: now[0], sleep=fake_sleep)
    for _ in range(3):
        await rl.acquire()
    assert slept == []
    await rl.acquire()  # cai thu 4 phai doi het cua so
    assert slept and abs(sum(slept) - 10.0) < 0.01


async def test_retry_backoff_and_retry_after():
    calls, delays = [], []

    async def sleep(d):
        delays.append(d)

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RetryableError("x")
        if len(calls) == 2:
            raise RateLimited("429", retry_after=20)
        return "ok"

    assert await retry_async(flaky, sleep=sleep, jitter=0) == "ok"
    assert delays == [1.0, 20]


async def test_retry_gives_up_and_fatal_not_retried():
    n = []

    async def always():
        n.append(1)
        raise RetryableError("down")

    async def nosleep(d):
        pass

    with pytest.raises(RetryableError):
        await retry_async(always, attempts=3, sleep=nosleep)
    assert len(n) == 3

    m = []

    async def fatal():
        m.append(1)
        raise FatalError("bad key")

    with pytest.raises(FatalError):
        await retry_async(fatal, sleep=nosleep)
    assert len(m) == 1
