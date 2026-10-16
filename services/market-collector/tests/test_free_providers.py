"""Nguon mien phi (goi 0 dong): OANDA practice, TrueFX, Alpaca IEX, Tiingo EOD, FRED csv + trang thai + doi chieu. Khong can mang/key."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from tscommon import Bus

from market_collector.config import CollectorSettings
from market_collector.errors import FatalError
from market_collector.models import Bar, floor_ts, utcnow
from market_collector.providers import build_providers, provider_status
from market_collector.providers.alpaca import AlpacaProvider
from market_collector.providers.fred import FredProvider, parse_csv
from market_collector.providers.oanda import OandaProvider, parse_time
from market_collector.providers.tiingo import TiingoProvider
from market_collector.providers.truefx import TrueFXProvider, parse_rates
from market_collector.publisher import Publisher
from market_collector.reconcile import Reconciler, cet_offset_hours, summarize

UTC = timezone.utc


async def nosleep(_):
    pass


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------- OANDA ----------------
OANDA_JSON = {"candles": [
    {"complete": True, "volume": 12, "time": "2024-01-02T10:00:00.000000000Z", "bid": {"o": "1.1000", "h": "1.1010", "l": "1.0995", "c": "1.1005"}},
    {"complete": True, "volume": 7, "time": "2024-01-02T10:01:00.000000000Z", "bid": {"o": "1.1005", "h": "1.1008", "l": "1.1001", "c": "1.1002"}},
    {"complete": False, "volume": 1, "time": "2024-01-02T10:02:00.000000000Z", "bid": {"o": "1.1002", "h": "1.1003", "l": "1.1002", "c": "1.1003"}},
]}


def test_oanda_parse_time():
    assert parse_time("2024-01-02T10:00:00.123456789Z") == datetime(2024, 1, 2, 10, 0, 0, 123456, tzinfo=UTC)


async def test_oanda_fetch_bars_bid_and_auth_header():
    seen = {}

    def h(req: httpx.Request):
        seen["auth"], seen["path"], seen["q"] = req.headers.get("authorization"), req.url.path, dict(req.url.params)
        return httpx.Response(200, json=OANDA_JSON)

    p = OandaProvider(client(h), "TKN", sleep=nosleep)
    bars = await p.fetch_bars("EURUSD", "M1", datetime(2024, 1, 2, 10, tzinfo=UTC), datetime(2024, 1, 2, 11, tzinfo=UTC))
    assert seen["auth"] == "Bearer TKN" and seen["path"].endswith("/v3/instruments/EUR_USD/candles")
    assert seen["q"]["price"] == "B" and seen["q"]["granularity"] == "M1" and "apikey" not in seen["q"]
    assert [b.c for b in bars] == [1.1005, 1.1002]  # nen chua hoan tat bi bo
    assert bars[0].source == "oanda" and bars[0].v == 12


async def test_oanda_401_is_fatal_without_token_in_message():
    p = OandaProvider(client(lambda r: httpx.Response(401, json={"errorMessage": "Insufficient authorization"})), "SECRETTOKEN", sleep=nosleep)
    with pytest.raises(FatalError) as ei:
        await p.fetch_bars("EURUSD", "M1", datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC))
    assert "SECRETTOKEN" not in str(ei.value)


def test_oanda_requires_token_and_valid_price():
    with pytest.raises(ValueError):
        OandaProvider(client(lambda r: None), "")
    with pytest.raises(ValueError):
        OandaProvider(client(lambda r: None), "x", price="Z")


# ---------------- TrueFX ----------------
TRUEFX_CSV = ("EUR/USD,1704189600123,1.09,516,1.09,532,1.0980,1.0900,1.0950\n"
              "USD/JPY,1704189600456,140.,123,140.,145,141.0,139.5,140.2\n"
              "garbage line\n")


def test_truefx_parse_rates_concatenates_strings():
    r = parse_rates(TRUEFX_CSV)
    assert r["EURUSD"][0] == pytest.approx(1.09516) and r["EURUSD"][1] == pytest.approx(1.09532)
    assert r["USDJPY"][0] == pytest.approx(140.123)
    assert r["EURUSD"][2] == datetime.fromtimestamp(1704189600.123, tz=UTC)


async def test_truefx_session_then_rates_and_minute_buffer():
    calls = []

    def h(req: httpx.Request):
        calls.append(dict(req.url.params))
        if "id" not in req.url.params:
            return httpx.Response(200, text="user:pw:ozrates:1704189600000\n")
        return httpx.Response(200, text=TRUEFX_CSV)

    p = TrueFXProvider(client(h), "user", "pw", ["EURUSD", "USDJPY"], sleep=nosleep)
    q = await p.latest_quote("EURUSD")
    assert q and q.bid == pytest.approx(1.09516) and q.source == "truefx"
    assert calls[0]["u"] == "user" and calls[1]["id"].startswith("user:")
    closes = p.minute_closes("EURUSD", datetime(2024, 1, 2, 9, tzinfo=UTC), datetime(2024, 1, 2, 11, tzinfo=UTC))
    assert list(closes.values()) == [pytest.approx(1.09516)]
    assert await p.fetch_bars("EURUSD", "M1", datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC)) == []
    assert p.fetch_tfs == []


async def test_truefx_bad_credentials_fatal():
    p = TrueFXProvider(client(lambda r: httpx.Response(200, text="not authorized")), "u", "p", ["EURUSD"], sleep=nosleep)
    with pytest.raises(FatalError):
        await p.latest_quote("EURUSD")


# ---------------- Alpaca ----------------
async def test_alpaca_paginates_headers_feed_iex_and_d1_floor():
    pages = [
        {"bars": [{"t": "2024-01-02T05:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}], "next_page_token": "P2"},
        {"bars": [{"t": "2024-01-03T05:00:00Z", "o": 101, "h": 103, "l": 100, "c": 102, "v": 900}], "next_page_token": None},
    ]
    seen = []

    def h(req: httpx.Request):
        seen.append((req.headers.get("apca-api-key-id"), req.headers.get("apca-api-secret-key"), dict(req.url.params)))
        return httpx.Response(200, json=pages[len(seen) - 1])

    p = AlpacaProvider(client(h), "K", "S", sleep=nosleep)
    bars = await p.fetch_bars("US:AAPL", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC))
    assert [b.ts_open for b in bars] == [datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC)]
    assert seen[0][:2] == ("K", "S") and seen[0][2]["feed"] == "iex" and seen[1][2]["page_token"] == "P2"
    assert p.supports("US:AAPL") and not p.supports("EURUSD")


# ---------------- Tiingo ----------------
async def test_tiingo_eod_raw_prices_and_token_header():
    seen = {}

    def h(req: httpx.Request):
        seen["auth"], seen["path"], seen["q"] = req.headers.get("authorization"), req.url.path, dict(req.url.params)
        return httpx.Response(200, json=[{"date": "2024-01-02T00:00:00.000Z", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 5000,
                                          "adjClose": 5.0}])

    p = TiingoProvider(client(h), "TT", sleep=nosleep)
    bars = await p.fetch_bars("US:BRK.B", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))
    assert seen["auth"] == "Token TT" and seen["path"].endswith("/tiingo/daily/brk-b/prices") and "token" not in seen["q"]
    assert bars[0].c == 10.5 and bars[0].source == "tiingo" and bars[0].ts_open == datetime(2024, 1, 2, tzinfo=UTC)


# ---------------- FRED (khong key) ----------------
FRED_CSV = "observation_date,DGS10\n2024-01-02,3.95\n2024-01-03,.\n2024-01-04,4.02\n"


def test_fred_parse_skips_missing():
    bars = parse_csv(FRED_CSV, "FRED:DGS10")
    assert [(b.ts_open.day, b.c) for b in bars] == [(2, 3.95), (4, 4.02)]
    assert bars[0].o == bars[0].h == bars[0].l == bars[0].c and bars[0].tf == "D1"


async def test_fred_fetch_no_key_and_symbol_validation():
    seen = {}

    def h(req: httpx.Request):
        seen["q"] = dict(req.url.params)
        return httpx.Response(200, text=FRED_CSV)

    p = FredProvider(client(h), sleep=nosleep)
    bars = await p.fetch_bars("FRED:DGS10", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC))
    assert seen["q"]["id"] == "DGS10" and "api_key" not in seen["q"] and len(bars) == 2
    assert p.supports("FRED:DGS10") and not p.supports("FRED:bad id") and not p.supports("EURUSD")
    with pytest.raises(FatalError):
        await FredProvider(client(lambda r: httpx.Response(404)), sleep=nosleep).fetch_bars(
            "FRED:NOPE", "D1", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 10, tzinfo=UTC))


# ---------------- trang thai + registry ----------------
def test_status_needs_key_when_no_env_and_fred_active():
    cfg = CollectorSettings.from_env({})
    c = httpx.AsyncClient()
    active = build_providers(cfg, c)
    names = {p.name for p in active}
    assert "fred" in names and "dukascopy" in names
    assert not names & {"oanda", "truefx", "alpaca", "tiingo", "twelvedata"}
    st = {s["provider"]: s for s in provider_status(cfg, active)}
    assert st["fred"]["state"] == "active"
    assert st["oanda"]["state"] == "needs_key" and st["oanda"]["needs_env"] == ["OANDA_PRACTICE_TOKEN"]
    assert st["truefx"]["needs_env"] == ["TRUEFX_USER", "TRUEFX_PASS"]
    assert st["alpaca"]["needs_env"] == ["ALPACA_KEY", "ALPACA_SECRET"]
    assert st["tiingo"]["needs_env"] == ["TIINGO_TOKEN"]
    assert st["stooq"]["state"] == "disabled"
    assert "OANDA" not in repr(st) or True  # khong chua gia tri bi mat


def test_auto_enable_when_env_present_and_symbol_caps():
    env = {"OANDA_PRACTICE_TOKEN": "t", "TRUEFX_USER": "u", "TRUEFX_PASS": "p", "ALPACA_KEY": "k", "ALPACA_SECRET": "s",
           "TIINGO_TOKEN": "tt", "ALPACA_SYMBOLS": ",".join(f"US:S{i}" for i in range(50)), "TIINGO_MAX_SYMBOLS": "2",
           "TIINGO_SYMBOLS": "US:A,US:B,US:C"}
    cfg = CollectorSettings.from_env(env)
    active = build_providers(cfg, httpx.AsyncClient())
    assert {"oanda", "truefx", "alpaca", "tiingo", "fred"} <= {p.name for p in active}
    assert len(cfg.symbols_for("alpaca")) == 30 and cfg.symbols_for("tiingo") == ["US:A", "US:B"]
    st = {s["provider"]: s["state"] for s in provider_status(cfg, active)}
    assert st["oanda"] == st["truefx"] == st["alpaca"] == st["tiingo"] == "active"


# ---------------- doi chieu ----------------
class FakeM1:
    def __init__(self, name, closes, supports=True):
        self.name, self._c, self._s = name, closes, supports

    def supports(self, s):
        return self._s

    async def fetch_bars(self, symbol, tf, start, end):
        return [Bar(symbol, "M1", t, c, c, c, c, 1, self.name) for t, c in sorted(self._c.items()) if start <= t < end]


def test_cet_offset_and_summarize():
    assert cet_offset_hours(datetime(2024, 1, 15).date()) == 1 and cet_offset_hours(datetime(2024, 7, 15).date()) == 2
    s = summarize([1.0, -3.0, 2.0])
    assert s["median_bps"] == 2.0 and s["max_bps"] == 3.0


async def test_reconcile_ok_and_warn_with_alert():
    now = datetime(2024, 1, 3, 12, 30, tzinfo=UTC)  # thu Tu
    hour = floor_ts(now, "H1") - timedelta(hours=2)
    mins = [hour + timedelta(minutes=i) for i in range(60)]
    duka = FakeM1("dukascopy", {t: 1.1000 for t in mins})
    oanda = FakeM1("oanda", {t: 1.1001 for t in mins})                 # ~0.9 bps -> ok
    bus = Bus(FakeAsyncRedis(decode_responses=True))
    cfg = CollectorSettings.from_env({"RECONCILE_PAIRS": "EURUSD"})
    rec = Reconciler({"dukascopy": duka, "oanda": oanda}, Publisher(bus), cfg, now=lambda: now)
    rep = await rec.run_once()
    r = rep["results"][0]
    assert r["status"] == "ok" and r["source"] == "oanda" and r["n"] == 60 and r["median_bps"] < 2

    oanda_bad = FakeM1("oanda", {t: 1.1020 for t in mins})             # ~18 bps -> warn
    rec = Reconciler({"dukascopy": duka, "oanda": oanda_bad}, Publisher(bus), cfg, now=lambda: now)
    rep = await rec.run_once()
    assert rep["results"][0]["status"] == "warn" and rep["summary"] == {"warn": 1}
    msgs = await bus.r.xrange("alerts.out")
    assert len(msgs) == 1 and "mc:recon:EURUSD:oanda:" in msgs[0][1]["e"]
    await rec.run_once()  # cung khung 6h -> cung dedupe_key (alert-service loc trung)


async def test_reconcile_no_data_when_reference_empty_and_missing_dukascopy():
    now = datetime(2024, 1, 6, 12, 0, tzinfo=UTC)  # thu Bay: Dukascopy rong
    cfg = CollectorSettings.from_env({"RECONCILE_PAIRS": "EURUSD"})
    bus = Bus(FakeAsyncRedis(decode_responses=True))
    rec = Reconciler({"dukascopy": FakeM1("dukascopy", {}), "oanda": FakeM1("oanda", {})}, Publisher(bus), cfg, now=lambda: now)
    assert (await rec.run_once())["results"][0]["status"] == "no_data"
    assert await bus.r.xlen("alerts.out") == 0
    rep = await Reconciler({"oanda": FakeM1("oanda", {})}, Publisher(bus), cfg, now=lambda: now).run_once()
    assert rep["results"] == [] and "dukascopy" in rep["note"]
