"""yahoo_daily: parse chart JSON (ngay cuc bo, bo nen ngay hien tai), map symbol, lich poll, co ToS. Khong can mang."""
from datetime import datetime, timedelta, timezone

import httpx

from market_collector.config import CollectorSettings
from market_collector.models import utcnow
from market_collector.providers import build_providers, provider_status
from market_collector.providers.yahoo_daily import YahooDailyProvider, parse_chart, to_ticker

UTC = timezone.utc


async def nosleep(_):
    pass


def chart(ts, off=-14400):
    n = len(ts)
    return {"chart": {"result": [{"meta": {"gmtoffset": off}, "timestamp": ts, "indicators": {"quote": [{
        "open": [10.0 + i for i in range(n)], "high": [11.0 + i for i in range(n)], "low": [9.0 + i for i in range(n)],
        "close": [10.5 + i for i in range(n)], "volume": [100 + i for i in range(n)]}]}}]}}


def test_symbol_map():
    assert to_ticker("US:SPY") == "SPY" and to_ticker("US:BRK.B") == "BRK-B" and to_ticker("XAUUSD") == "GC=F"
    assert to_ticker("VN:VNM") == "VNM.VN" and to_ticker("EURUSD") is None


def test_parse_local_date_skips_null_and_current_day():
    # 2024-01-02 14:30 UTC (open NYSE), 2024-01-03 14:30 (gia None -> bo), 2024-01-04 14:30
    t = [int(datetime(2024, 1, d, 14, 30, tzinfo=UTC).timestamp()) for d in (2, 3, 4)]
    j = chart(t)
    j["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None
    bars = parse_chart(j, "US:SPY", before=datetime(2024, 1, 4, tzinfo=UTC))
    assert [b.ts_open for b in bars] == [datetime(2024, 1, 2, tzinfo=UTC)]
    assert bars[0].source == "yahoo_daily" and bars[0].tf == "D1" and bars[0].c == 10.5 and bars[0].v == 100


def test_parse_asia_local_date_uses_gmtoffset():
    # 2024-01-02 23:30 UTC la ngay 2024-01-03 o UTC+9
    t = [int(datetime(2024, 1, 2, 23, 30, tzinfo=UTC).timestamp())]
    bars = parse_chart(chart(t, off=32400), "US:X")
    assert bars[0].ts_open == datetime(2024, 1, 3, tzinfo=UTC)


async def test_fetch_excludes_today_and_sends_ua():
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    t = [int((today - timedelta(days=2) + timedelta(hours=14)).timestamp()), int((today + timedelta(hours=14)).timestamp())]
    seen = {}

    def h(req: httpx.Request):
        seen["ua"], seen["path"] = req.headers.get("user-agent"), req.url.path
        return httpx.Response(200, json=chart(t, off=0))

    p = YahooDailyProvider(httpx.AsyncClient(transport=httpx.MockTransport(h)), sleep=nosleep)
    bars = await p.fetch_bars("US:SPY", "D1", today - timedelta(days=5), today + timedelta(days=1))
    assert seen["path"].endswith("/SPY") and "Mozilla" in seen["ua"]
    assert [b.ts_open for b in bars] == [today - timedelta(days=2)]      # nen hom nay bi bo


async def test_404_empty_and_429_retries_then_ok():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}) if calls["n"] == 1 else httpx.Response(404)

    p = YahooDailyProvider(httpx.AsyncClient(transport=httpx.MockTransport(h)), sleep=nosleep)
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    assert await p.fetch_bars("US:SPY", "D1", today - timedelta(days=9), today) == [] and calls["n"] == 2


def test_next_poll_delay_daily_at_2230():
    p = YahooDailyProvider(httpx.AsyncClient(), at_utc="22:30")
    assert p.next_poll_delay(datetime(2024, 1, 2, 22, 0, tzinfo=UTC)) == 1800
    assert p.next_poll_delay(datetime(2024, 1, 2, 22, 31, tzinfo=UTC)) == 86400 - 60


def test_risky_flag_gates_provider():
    s = CollectorSettings.from_env({"PROVIDERS": "yahoo_daily"})
    assert build_providers(s, httpx.AsyncClient()) == []
    assert provider_status(s)[-1]["state"] == "risky_off"
    s2 = CollectorSettings.from_env({"PROVIDERS": "yahoo_daily", "ALLOW_RISKY_PROVIDERS": "true"})
    ps = build_providers(s2, httpx.AsyncClient())
    assert [p.name for p in ps] == ["yahoo_daily"] and ps[0].supports("XAUUSD")
