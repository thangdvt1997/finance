import json
import lzma
import struct
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from market_collector.config import CollectorSettings
from market_collector.errors import FatalError, RateLimited
from market_collector.providers import build_providers
from market_collector.providers.dukascopy import DukascopyProvider, decode_bi5, price_scale, ticks_to_m1
from market_collector.providers.frankfurter import FrankfurterProvider
from market_collector.providers.twelvedata import TwelveDataProvider, to_td_symbol
from market_collector.providers.vnstock_provider import VnstockProvider
from market_collector.providers.yahoo import YahooProvider
from market_collector.ratelimit import RateLimiter

UTC = timezone.utc


async def nosleep(_):
    pass


def make_bi5(rows):
    raw = b"".join(struct.pack(">IIIff", ms, ask, bid, av, bv) for ms, ask, bid, av, bv in rows)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------- Dukascopy ----------------
def test_decode_bi5_and_scale():
    hour = datetime(2024, 1, 2, 10, tzinfo=UTC)
    data = make_bi5([(0, 110005, 110000, 1.5, 2.0), (30_000, 110015, 110010, 1.0, 1.0), (61_000, 110025, 110020, 1.0, 1.0)])
    ticks = decode_bi5(data, hour, 1e5)
    assert len(ticks) == 3
    assert ticks[0].bid == pytest.approx(1.10000) and ticks[0].ask == pytest.approx(1.10005)
    assert ticks[2].ts == hour + timedelta(seconds=61)
    bars = ticks_to_m1(ticks, "EURUSD")
    assert [b.ts_open.minute for b in bars] == [0, 1]
    assert bars[0].o == pytest.approx(1.10000) and bars[0].c == pytest.approx(1.10010)
    assert bars[0].h == pytest.approx(1.10010) and bars[0].v == 5.5
    assert decode_bi5(b"", hour, 1e5) == []
    assert price_scale("USDJPY") == 1e3 and price_scale("XAUUSD") == 1e3 and price_scale("EURUSD") == 1e5


async def test_dukascopy_fetch_cache_and_url(tmp_path):
    seen = []
    hour_data = make_bi5([(0, 110005, 110000, 1, 1), (60_000, 110015, 110010, 1, 1)])

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        if "/10h_ticks" in req.url.path:
            return httpx.Response(200, content=hour_data)
        return httpx.Response(200, content=b"")  # gio khong co du lieu

    p = DukascopyProvider(client(handler), tmp_path, rate_per_sec=1000, sleep=nosleep)
    start = datetime(2024, 1, 2, 10, tzinfo=UTC)  # thu Ba
    bars = await p.fetch_bars("EURUSD", "M1", start, start + timedelta(hours=2))
    assert len(bars) == 2 and bars[0].source == "dukascopy"
    assert any("/EURUSD/2024/00/02/10h_ticks.bi5" in u for u in seen)  # thang 0-based
    n = len(seen)
    again = await p.fetch_bars("EURUSD", "M5", start, start + timedelta(hours=2))
    assert len(seen) == n  # lan 2 doc tu cache dia, khong goi mang
    assert len(again) == 1 and again[0].tf == "M5"


async def test_dukascopy_skips_saturday_and_supports(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.url.path)
        return httpx.Response(404)

    p = DukascopyProvider(client(handler), tmp_path, rate_per_sec=1000, sleep=nosleep)
    sat = datetime(2024, 1, 6, tzinfo=UTC)
    assert await p.fetch_bars("EURUSD", "M1", sat, sat + timedelta(days=1)) == []
    assert seen == []
    assert p.supports("EURUSD") and not p.supports("VN:VNM")
    assert not p.expects_data(sat, "EURUSD") and p.expects_data(datetime(2024, 1, 2, 10, tzinfo=UTC), "EURUSD")


async def test_dukascopy_retries_5xx_then_ok(tmp_path):
    n = []
    data = make_bi5([(0, 110005, 110000, 1, 1)])

    def handler(req):
        n.append(1)
        return httpx.Response(503) if len(n) < 3 else httpx.Response(200, content=data)

    p = DukascopyProvider(client(handler), tmp_path, rate_per_sec=1000, sleep=nosleep)
    h = datetime(2024, 1, 2, 10, tzinfo=UTC)
    bars = await p.fetch_bars("EURUSD", "M1", h, h + timedelta(hours=1))
    assert len(bars) == 1 and len(n) == 3


# ---------------- Frankfurter ----------------
async def test_frankfurter_bars_and_quote():
    def handler(req: httpx.Request):
        if req.url.path.endswith("/latest"):
            return httpx.Response(200, json={"base": "EUR", "date": "2024-01-05", "rates": {"USD": 1.0950}})
        assert req.url.params["base"] == "EUR" and req.url.params["symbols"] == "USD"
        assert "2024-01-01..2024-01-05" in req.url.path
        return httpx.Response(200, json={"rates": {"2024-01-02": {"USD": 1.09}, "2024-01-03": {"USD": 1.095}}})

    p = FrankfurterProvider(client(handler), sleep=nosleep)
    s = datetime(2024, 1, 1, tzinfo=UTC)
    bars = await p.fetch_bars("EURUSD", "D1", s, datetime(2024, 1, 6, tzinfo=UTC))
    assert [b.c for b in bars] == [1.09, 1.095] and bars[0].ts_open == datetime(2024, 1, 2, tzinfo=UTC)
    assert bars[0].o == bars[0].h == bars[0].l == bars[0].c
    q = await p.latest_quote("EURUSD")
    assert q.bid == q.ask == 1.095
    assert p.supports("EURUSD") and not p.supports("XAUUSD") and not p.supports("VN:VNM")
    with pytest.raises(FatalError):
        await p.fetch_bars("EURUSD", "H1", s, s + timedelta(days=1))


# ---------------- Twelve Data ----------------
def test_td_symbol_map():
    assert to_td_symbol("EURUSD") == "EUR/USD" and to_td_symbol("XAUUSD") == "XAU/USD" and to_td_symbol("US:AAPL") == "AAPL"


async def test_twelvedata_bars_ok():
    def handler(req: httpx.Request):
        assert req.url.params["symbol"] == "EUR/USD" and req.url.params["interval"] == "1h"
        return httpx.Response(200, json={"status": "ok", "values": [
            {"datetime": "2024-01-02 11:00:00", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15", "volume": "10"},
            {"datetime": "2024-01-02 10:00:00", "open": "1.0", "high": "1.1", "low": "0.9", "close": "1.05"},
        ]})

    p = TwelveDataProvider(client(handler), "KEY", sleep=nosleep)
    s = datetime(2024, 1, 2, tzinfo=UTC)
    bars = await p.fetch_bars("EURUSD", "H1", s, s + timedelta(days=1))
    assert [b.ts_open.hour for b in bars] == [10, 11] and bars[1].v == 10.0 and bars[0].v == 0.0


async def test_twelvedata_errors_and_key_not_leaked():
    def h429(req):
        return httpx.Response(200, json={"code": 429, "status": "error", "message": "run out of credits KEY"})

    p = TwelveDataProvider(client(h429), "KEY", sleep=nosleep, attempts=2)
    s = datetime(2024, 1, 2, tzinfo=UTC)
    with pytest.raises(RateLimited) as ei:
        await p.fetch_bars("EURUSD", "H1", s, s + timedelta(days=1))
    assert "KEY" not in str(ei.value)

    def h401(req):
        return httpx.Response(200, json={"code": 401, "status": "error", "message": "bad apikey"})

    with pytest.raises(FatalError):
        await TwelveDataProvider(client(h401), "KEY", sleep=nosleep).fetch_bars("EURUSD", "H1", s, s + timedelta(days=1))

    def boom(req):
        raise httpx.ConnectError("fail", request=req)

    from market_collector.errors import RetryableError
    with pytest.raises(RetryableError) as ei2:
        await TwelveDataProvider(client(boom), "KEY", sleep=nosleep, attempts=2).fetch_bars("EURUSD", "H1", s, s + timedelta(days=1))
    assert "KEY" not in str(ei2.value)


def test_twelvedata_requires_key():
    with pytest.raises(ValueError):
        TwelveDataProvider(httpx.AsyncClient(), "")


# ---------------- vnstock ----------------
async def test_vnstock_fixture_and_tz():
    calls = []

    def fetcher(sym, s, e, interval):
        calls.append((sym, s, e, interval))
        return [{"time": "2024-01-02", "open": 60.1, "high": 61.0, "low": 59.9, "close": 60.5, "volume": 1000},
                {"time": "2024-01-03", "open": 60.5, "high": 62.0, "low": 60.0, "close": 61.8, "volume": 2000}]

    p = VnstockProvider(fetcher=fetcher)
    s = datetime(2024, 1, 1, tzinfo=UTC)
    bars = await p.fetch_bars("VN:VNM", "D1", s, datetime(2024, 1, 5, tzinfo=UTC))
    assert calls[0][0] == "VNM" and calls[0][3] == "1D"
    assert bars[0].symbol == "VN:VNM" and bars[0].ts_open == datetime(2024, 1, 2, tzinfo=UTC)  # D1: ngay -> 00:00 UTC
    assert bars[1].c == 61800.0 and bars[1].o == 60500.0 and bars[1].v == 2000  # nghin dong -> VND that
    assert bars[0].o == 60100.0 and bars[0].l == 59900.0
    assert p.supports("VN:VNM") and not p.supports("EURUSD")


def test_vnstock_rate_limit_config():
    assert VnstockProvider(fetcher=lambda *a: []).limiter.max_calls == 20
    assert VnstockProvider(api_key="k", fetcher=lambda *a: []).limiter.max_calls == 60


async def test_vnstock_accepts_dataframe_like():
    class DF:
        def to_dict(self, orient):
            assert orient == "records"
            return [{"time": datetime(2024, 1, 2), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3}]

    p = VnstockProvider(fetcher=lambda *a: DF())
    bars = await p.fetch_bars("VN:FPT", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))
    assert len(bars) == 1


async def test_vnstock_prices_normalized_to_vnd_no_float_noise():
    rows = [{"time": "2026-10-09", "open": 57.9, "high": 58.0, "low": 57.3, "close": 57.7, "volume": 1860200}]
    p = VnstockProvider(fetcher=lambda *a: rows)
    b = (await p.fetch_bars("VN:VNM", "D1", datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)))[0]
    assert (b.o, b.h, b.l, b.c) == (57900.0, 58000.0, 57300.0, 57700.0) and b.v == 1860200
    # nguon da tra VND day du -> dat price_multiplier=1
    p1 = VnstockProvider(fetcher=lambda *a: [{**rows[0], "close": 57700}], price_multiplier=1.0)
    b1 = (await p1.fetch_bars("VN:VNM", "D1", datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)))[0]
    assert b1.c == 57700.0


# ---------------- Yahoo (skeleton) ----------------
async def test_yahoo_with_fake_fetcher():
    rows = [{"Date": datetime(2024, 1, 2), "Open": 1, "High": 2, "Low": 1, "Close": 1.5, "Volume": 5}]
    p = YahooProvider(fetcher=lambda *a: rows)
    bars = await p.fetch_bars("EURUSD", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))
    assert len(bars) == 1 and bars[0].source == "yahoo"


# ---------------- Registry ----------------
def test_registry_flags(tmp_path):
    base = {"CACHE_DIR": str(tmp_path)}
    # thieu key twelvedata -> tat; stooq/yahoo bi chan mac dinh
    s = CollectorSettings.from_env({**base, "PROVIDERS": "dukascopy,frankfurter,twelvedata,stooq,yahoo"})
    names = [p.name for p in build_providers(s, httpx.AsyncClient())]
    assert names == ["dukascopy", "frankfurter"]
    # co key -> bat; risky chi bat khi co co ALLOW
    s2 = CollectorSettings.from_env({**base, "PROVIDERS": "twelvedata,stooq", "TWELVEDATA_API_KEY": "k",
                                     "ALLOW_RISKY_PROVIDERS": "true"})
    assert [p.name for p in build_providers(s2, httpx.AsyncClient())] == ["twelvedata", "stooq"]


def test_settings_defaults_and_parsing():
    s = CollectorSettings.from_env({"OUTPUT_TFS": "m1,h1,bogus", "DUKASCOPY_SYMBOLS": "eur/usd,xauusd",
                                    "BACKFILL_DAYS": "3", "VNSTOCK_API_KEY": "abc"})
    assert s.output_tfs == ["M1", "H1"] and s.symbols_for("dukascopy") == ["EURUSD", "XAUUSD"]
    assert s.backfill_days == 3 and s.vnstock_key == "abc" and s.symbols_for("twelvedata") == []


async def test_vnstock_d1_vnstock4_0700_stamp_and_intraday_tz():
    rows = [{"time": datetime(2024, 1, 2, 7, 0), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3}]
    p = VnstockProvider(fetcher=lambda *a: rows)
    bars = await p.fetch_bars("VN:VNM", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))
    assert bars[0].ts_open == datetime(2024, 1, 2, tzinfo=UTC)
    rows = [{"time": datetime(2024, 1, 2, 9, 0), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 3}]
    p = VnstockProvider(fetcher=lambda *a: rows, tfs=["H1"])
    bars = await p.fetch_bars("VN:VNM", "H1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))
    assert bars[0].ts_open == datetime(2024, 1, 2, 2, tzinfo=UTC)  # 09:00 VN


def test_vnstock_unavailable_disables_cleanly(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "vnstock", None)  # import -> ImportError
    assert VnstockProvider.available() is False
    s = CollectorSettings(providers=["vnstock"], symbols={"vnstock": ["VN:VNM"]})
    assert build_providers(s, httpx.AsyncClient()) == []
