"""crypto_ccxt: nen dong 24/7, phan trang, du phong san, quote, gap H1, symbol, chat luong (khong lich cuoi tuan FX). Khong can mang (san gia)."""
from datetime import datetime, timedelta, timezone

import pytest
import fakeredis.aioredis
from tscommon import Bus, Event

from market_collector.collector import Collector
from market_collector.config import CollectorSettings
from market_collector.errors import RetryableError
from market_collector.models import TF_SECONDS, Bar, floor_ts
from market_collector.providers.crypto_ccxt import CryptoCcxtProvider, default_symbols, to_ccxt
from market_collector.publisher import Publisher
from market_collector.quality import check_bars
from market_collector.symbols import normalize_symbol, parse_symbol_list

UTC = timezone.utc
NOW = datetime(2026, 10, 11, 12, 34, 20, tzinfo=UTC)          # Chu nhat (FX dong cua)
TFS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
BTC, ETH = "CRYPTO:BTCUSDT", "CRYPTO:ETHUSDT"


class FakeExchange:
    """Gia lap ccxt async: chuoi nen tang deu moi `step` ms; tra ca nen DANG HINH THANH (nhu san that)."""

    def __init__(self, name, markets, *, limit=300, fail=False, break_tickers=False):
        self.name, self.limit, self.fail, self.break_tickers = name, limit, fail, break_tickers
        self.markets = {m: {"active": True} for m in markets}
        self.calls: list[tuple] = []
        self.closed = False

    async def load_markets(self):
        if self.fail == "load":
            raise ConnectionError("blocked")

    async def fetch_ohlcv(self, sym, tf, since=None, limit=None):
        self.calls.append((sym, tf, since, limit))
        if self.fail:
            raise ConnectionError("down")
        step = TFS[tf] * 1000
        now_ms = int(NOW.timestamp() * 1000)
        t = (since // step + (1 if since % step else 0)) * step
        out = []
        while t <= now_ms and len(out) < min(limit or self.limit, self.limit):   # gom ca nen dang hinh thanh
            out.append([t, 100.0, 101.0, 99.0, 100.5, 7.0])
            t += step
        return out

    async def fetch_tickers(self, syms):
        if self.fail or self.break_tickers:
            raise ConnectionError("down")
        return {s: {"bid": 100.0 + i, "ask": 100.5 + i, "last": 100.2 + i} for i, s in enumerate(syms) if s in self.markets}

    async def close(self):
        self.closed = True


def provider(exchanges=None, symbols=(BTC, ETH), **kw):
    ex = exchanges or {"okx": FakeExchange("okx", ["BTC/USDT", "ETH/USDT"], limit=300),
                       "kucoin": FakeExchange("kucoin", ["BTC/USDT", "ETH/USDT", "TON/USDT"], limit=1500)}
    p = CryptoCcxtProvider(list(ex), list(symbols), factory=lambda n: ex[n], now=lambda: NOW, **kw)
    return p, ex


def test_symbol_conventions():
    assert to_ccxt("CRYPTO:BTCUSDT") == "BTC/USDT" and to_ccxt("BTCUSDT") is None and to_ccxt("CRYPTO:BTCUSD") is None
    assert normalize_symbol("crypto:btc/usdt") == "CRYPTO:BTCUSDT"
    assert parse_symbol_list("crypto:eth-usdt, CRYPTO:SOLUSDT") == ["CRYPTO:ETHUSDT", "CRYPTO:SOLUSDT"]
    assert len(default_symbols().split(",")) >= 25
    s = CollectorSettings.from_env({})
    assert "crypto_ccxt" in s.providers and len(s.symbols_for("crypto_ccxt")) >= 25 and "CRYPTO:BTCUSDT" in s.symbols_for("crypto_ccxt")


def test_supports_is_not_fx():
    from market_collector.symbols import is_fx_pair
    p, _ = provider()
    assert p.supports("CRYPTO:BTCUSDT") and not p.supports("EURUSD") and not p.supports("US:SPY")
    assert not is_fx_pair("CRYPTO:BTCUSDT")   # oanda/dukascopy khong nhan nham


async def test_fetch_bars_closed_only_paged_and_sorted():
    p, ex = provider()
    start = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
    bars = await p.fetch_bars(BTC, "M1", start, NOW)
    assert bars[0].ts_open == start and bars[0].source == "crypto_ccxt" and bars[0].symbol == BTC
    assert bars[-1].ts_open == datetime(2026, 10, 11, 12, 33, tzinfo=UTC)         # nen 12:34 dang hinh thanh -> bo
    assert [b.ts_open for b in bars] == sorted({b.ts_open for b in bars})
    assert len(bars) == int((bars[-1].ts_open - start).total_seconds() // 60) + 1   # khong thieu giua cac trang (okx limit 300)
    assert len(ex["okx"].calls) >= 8 and not ex["kucoin"].calls                    # phan trang 300 nen/trang, san 1 du


async def test_gap_free_across_weekend_for_24x7_quality():
    p, _ = provider()
    bars = await p.fetch_bars(BTC, "H1", datetime(2026, 10, 8, tzinfo=UTC), NOW)    # qua T7/CN
    clean, issues = check_bars(bars, ignore_weekend=not p.trades_weekends)
    assert len(clean) == len(bars) and not [i for i in issues if i.kind == "gap"]
    # nen FX: khoang trong cuoi tuan duoc mien, crypto thi KHONG
    hole = [Bar(BTC, "H1", datetime(2026, 10, 9, 22, tzinfo=UTC) + timedelta(hours=k), 1, 1, 1, 1, 0, "x") for k in (0, 1, 2, 3, 4, 5, 6)]
    hole = hole[:3] + [Bar(BTC, "H1", datetime(2026, 10, 12, 1, tzinfo=UTC), 1, 1, 1, 1, 0, "x")]
    assert not [i for i in check_bars(hole, ignore_weekend=True)[1] if i.kind == "gap"]
    assert [i for i in check_bars(hole, ignore_weekend=False)[1] if i.kind == "gap"]


async def test_failover_to_next_exchange_and_symbol_only_on_second():
    ex = {"okx": FakeExchange("okx", ["BTC/USDT"], fail=True), "kucoin": FakeExchange("kucoin", ["BTC/USDT", "TON/USDT"])}
    p, _ = provider(ex, symbols=(BTC, "CRYPTO:TONUSDT"))
    bars = await p.fetch_bars(BTC, "H1", NOW - timedelta(hours=5), NOW)
    assert len(bars) == 4 and p.last_exchange[BTC] == "kucoin"       # 08..11h (12h dang hinh thanh)
    ton = await p.fetch_bars("CRYPTO:TONUSDT", "H1", NOW - timedelta(hours=3), NOW)
    assert len(ton) == 2 and p.last_exchange["CRYPTO:TONUSDT"] == "kucoin" and not [c for c in ex["okx"].calls if c[0] == "TON/USDT"]


async def test_all_exchanges_down_raises_retryable():
    ex = {"okx": FakeExchange("okx", ["BTC/USDT"], fail=True), "kucoin": FakeExchange("kucoin", ["BTC/USDT"], fail=True)}
    p, _ = provider(ex, symbols=(BTC,))
    with pytest.raises(RetryableError):
        await p.fetch_bars(BTC, "M1", NOW - timedelta(hours=1), NOW)


async def test_exchange_blocked_at_load_is_skipped():
    ex = {"binance": FakeExchange("binance", ["BTC/USDT"], fail="load"), "kucoin": FakeExchange("kucoin", ["BTC/USDT"])}
    p, _ = provider(ex, symbols=(BTC,))
    assert len(await p.fetch_bars(BTC, "H1", NOW - timedelta(hours=2), NOW)) == 1 and p.last_exchange[BTC] == "kucoin"


def test_plan_chunks_and_poll_schedule():
    p, _ = provider()
    assert all(p.chunk_for(tf) % timedelta(days=1) == timedelta(0) for tf in p.fetch_tfs)
    assert p.backfill_start("D1", NOW - timedelta(days=7), NOW) <= NOW - timedelta(days=2000)
    assert p.backfill_start("M1", NOW - timedelta(days=7), NOW) == NOW - timedelta(days=3)   # ke hoach rieng, khong theo BACKFILL_DAYS
    assert p.poll_tfs(BTC, NOW) == p.fetch_tfs
    assert p.poll_tfs(BTC, NOW + timedelta(seconds=60)) == ["M1"]
    assert p.poll_tfs(ETH, NOW) == p.fetch_tfs                                              # lich theo (symbol, tf)
    assert "H1" in p.poll_tfs(BTC, NOW + timedelta(seconds=600))
    assert p.expects_data(datetime(2026, 10, 10, 3, tzinfo=UTC), BTC)                      # T7 van mong doi du lieu


async def test_poll_starts_at_last_seen_and_overlaps_one_bar():
    p, _ = provider()
    assert p.poll_start(BTC, "M1", NOW) == datetime(2026, 10, 11, 12, 29, tzinfo=UTC)
    bars = await p.fetch_bars(BTC, "M1", NOW - timedelta(minutes=10), NOW)
    assert p.poll_start(BTC, "M1", NOW) == bars[-1].ts_open
    again = await p.fetch_bars(BTC, "M1", p.poll_start(BTC, "M1", NOW), NOW)
    assert [b.ts_open for b in again] == [bars[-1].ts_open]       # luon co >= 1 nen khi san con song


async def test_quotes_one_call_per_exchange_and_fallback():
    ex = {"okx": FakeExchange("okx", ["BTC/USDT", "ETH/USDT"], break_tickers=True),
          "kucoin": FakeExchange("kucoin", ["BTC/USDT", "ETH/USDT"])}
    p, _ = provider(ex)
    qs = await p.latest_quotes()
    assert {q.symbol for q in qs} == {BTC, ETH} and all(q.source == "crypto_ccxt" and q.bid < q.ask for q in qs)
    assert p.quote_stream_interval == 15.0
    ex2 = {"okx": FakeExchange("okx", ["BTC/USDT"], break_tickers=True), "kucoin": FakeExchange("kucoin", ["BTC/USDT"], break_tickers=True)}
    p2, _ = provider(ex2, symbols=(BTC,))
    with pytest.raises(RetryableError):
        await p2.latest_quotes()


async def test_h1_gap_detection_refills_and_remembers_empty_hours():
    p, ex = provider()
    s = floor_ts(NOW, "H1") - timedelta(days=2)
    bars = await p.fetch_bars(BTC, "H1", s, NOW)
    assert p.find_missing_days(BTC, "H1", s, NOW) == []
    p._seen_h1[BTC].discard(bars[10].ts_open)                       # mat 1 gio
    miss = p.find_missing_days(BTC, "H1", s, NOW)
    assert miss == [floor_ts(bars[10].ts_open, "D1")]
    # tai lai nguyen ngay: san van tra gio do -> het thieu
    day = miss[0]
    await p.fetch_bars(BTC, "H1", day, day + timedelta(days=1))
    assert p.find_missing_days(BTC, "H1", s, NOW) == []
    # gio san that su khong co nen: tai lai ma van thieu -> nho, khong bao lai
    p._seen_h1[BTC].discard(bars[20].ts_open)
    orig = ex["okx"].fetch_ohlcv

    async def holey(sym, tf, since=None, limit=None):
        return [r for r in await orig(sym, tf, since, limit) if r[0] != int(bars[20].ts_open.timestamp() * 1000)]
    ex["okx"].fetch_ohlcv = holey
    d20 = floor_ts(bars[20].ts_open, "D1")
    assert p.find_missing_days(BTC, "H1", s, NOW) == [d20]
    await p.fetch_bars(BTC, "H1", d20, d20 + timedelta(days=1))
    assert p.find_missing_days(BTC, "H1", s, NOW) == []


async def test_collector_backfill_plan_depth_and_publish_on_sunday():
    """Collector that: backfill theo ke hoach tung tf, nen ra md.bars (khong bi chan boi 'cuoi tuan'), quote vong rieng."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(redis)
    p, ex = provider(symbols=(BTC,), depth={"M1": 1, "M5": 1, "M15": 1, "H1": 2, "H4": 3, "D1": 10})
    cfg = CollectorSettings.from_env({"PROVIDERS": "crypto_ccxt", "CRYPTO_SYMBOLS": ""})
    cfg.symbols["crypto_ccxt"] = [BTC]
    col = Collector([p], Publisher(bus), cfg, now=lambda: NOW)
    n = await col.backfill("crypto_ccxt", BTC, NOW - timedelta(days=7), NOW, plan=True)
    assert n > 0
    tfs = {}
    for _, f in await redis.xrange("md.bars"):
        pl = Event.model_validate_json(f["e"]).payload
        tfs.setdefault(pl["tf"], []).append(pl["ts_open"])
    assert set(tfs) == {"M1", "M5", "M15", "H1", "H4", "D1"}
    assert min(tfs["D1"]) <= "2026-10-02" and min(tfs["M1"]) >= "2026-10-10"       # D1 sau hon M1
    # backfill thu cong (plan=False) giu dung cua so nguoi dung yeu cau
    n2 = await col.backfill("crypto_ccxt", BTC, NOW - timedelta(days=1), NOW, tfs=["D1"])
    assert n2 <= 2
    # poll_once dung hook poll_tfs/poll_start
    assert await col.poll_once(p, BTC) > 0
    await col.stop()
    assert ex["okx"].closed


async def test_quote_loop_publishes_only_changes():
    import asyncio
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    p, ex = provider(symbols=(BTC, ETH), quote_interval=0.01)
    cfg = CollectorSettings.from_env({"PROVIDERS": "crypto_ccxt"})
    col = Collector([p], Publisher(Bus(redis)), cfg, now=lambda: NOW)
    t = asyncio.create_task(col._quote_loop(p))
    await asyncio.sleep(0.15)
    col._stop.set()
    await asyncio.wait_for(t, 2)
    got = [Event.model_validate_json(f["e"]).payload["symbol"] for _, f in await redis.xrange("md.quotes")]
    assert sorted(got) == [BTC, ETH]            # gia khong doi -> khong phat lai


async def test_m1_is_not_resampled_into_partial_higher_tf():
    """Loi da gap: M1 bi collector resample thanh M5..D1 DANG HINH THANH (poll cua so 5 phut) -> ghi de nen goc."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    p, _ = provider(symbols=(BTC,))
    cfg = CollectorSettings.from_env({"PROVIDERS": "crypto_ccxt"})
    col = Collector([p], Publisher(Bus(redis)), cfg, now=lambda: NOW)
    bars = await p.fetch_bars(BTC, "M1", NOW - timedelta(minutes=10), NOW)
    n = await col.process(p, BTC, "M1", bars)
    evs = [Event.model_validate_json(f["e"]).payload for _, f in await redis.xrange("md.bars")]
    assert n == len(bars) == len(evs) and {e["tf"] for e in evs} == {"M1"}
    assert p.resample_m1 is False


async def test_rewind_after_failed_publish_refetches_same_bars():
    # Redis loi luc phat -> collector goi rewind -> lan poll sau phai lay lai tu moc cu (khong de khe M1)
    p, _ = provider()
    start = p.poll_start(BTC, "M1", NOW)
    bars = await p.fetch_bars(BTC, "M1", start, NOW)
    assert p.poll_start(BTC, "M1", NOW) == bars[-1].ts_open
    p.rewind(BTC, "M1", start)
    assert p.poll_start(BTC, "M1", NOW) == start
    again = await p.fetch_bars(BTC, "M1", p.poll_start(BTC, "M1", NOW), NOW)
    assert [b.ts_open for b in again][-1] == bars[-1].ts_open and len(again) == len(bars)
