"""Crypto qua ccxt (OSS) -- CHI du lieu cong khai, KHONG can API key. Nguon san: xem PROVIDER_INFO / docs/FREE_STACK.md.

Symbol he thong: `CRYPTO:<BASE>USDT` (vd `CRYPTO:BTCUSDT` <-> ccxt `BTC/USDT`). Moi symbol co danh sach san theo thu tu uu tien
(`CRYPTO_EXCHANGES`, mac dinh okx,kucoin,gate,bitfinex): dung san DAU TIEN co cap do; loi/het han -> thu san ke tiep (nguon `source`
luon la `crypto_ccxt` de khoa upsert (symbol, tf, ts_open, source) khong bi tach theo san). Binance bi chan (HTTP 451) tu VPS; Bybit 403.

- Nen goc tu san cho M1/M5/M15/H1/H4/D1 (ts UTC), CHI nen DA DONG (nen dang hinh thanh bi bo) -> khong phat nen do dang.
- Lich su khi khoi dong (resume theo state): D1 ~6 nam, H4 ~1.5 nam, H1 ~180 ngay, M15 30 ngay, M5 14 ngay, M1 3 ngay (CRYPTO_BACKFILL_*).
- Cap nhat dinh ky: M1 moi vong (60s), cac tf cao thua hon; moi poll lay lai dung nen dong cuoi (de co tin hieu "san con song").
- Quote gan real-time: 1 lan `fetch_tickers` / nhom san moi `CRYPTO_QUOTE_INTERVAL` (15s), chi phat khi bid/ask doi (md.quotes).
- Crypto giao dich 24/7: `trades_weekends=True` (gap detector khong mien tru cuoi tuan), `expects_data` luon True.
- Gap detector: H1 theo doi gio da thay (bo nho) -> ngay thieu gio duoc tai lai; gio san that su khong co nen (da tai lai ma van thieu) duoc nho
  va khong bao lai.
- Rate limit: `enableRateLimit` cua ccxt (dung chuan tung san) + so request/lan nho (poll chi 1 request/symbol/tf, tf cao thua).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Callable

from ..errors import FatalError, RetryableError
from ..models import TF_SECONDS, Bar, Quote, ensure_utc, floor_ts, utcnow
from .base import Provider

log = logging.getLogger("market_collector.crypto")

CCXT_TF = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
# gioi han nen/lan cua tung san (an toan; ccxt tu cat neu thap hon)
PAGE_LIMIT = {"okx": 300, "kucoin": 1500, "gate": 1000, "bitfinex": 1000, "binanceus": 1000, "htx": 1000, "kraken": 720,
              "bitstamp": 1000, "coinbaseexchange": 300, "mexc": 500, "bitget": 200}
# khoang cach toi thieu giua 2 request (ms) neu NGHIEM hon mac dinh cua ccxt (Bitfinex public ~30 req/phut/IP; vuot -> 429 + khoa tam thoi)
MIN_INTERVAL_MS = {"bitfinex": 2200, "kraken": 1500}
# do sau backfill khi khoi dong (ngay)
DEFAULT_DEPTH = {"M1": 3, "M5": 14, "M15": 30, "H1": 180, "H4": 540, "D1": 2190}
# chunk backfill (ngay; boi so cua 1 ngay)
CHUNK_DAYS = {"M1": 1, "M5": 3, "M15": 10, "H1": 30, "H4": 120, "D1": 1100}
# chu ky poll toi thieu moi tf (giay) va so nen lay khi chua co moc
POLL_EVERY = {"M1": 60, "M5": 120, "M15": 300, "H1": 600, "H4": 1200, "D1": 1800}
POLL_BARS = {"M1": 5, "M5": 4, "M15": 4, "H1": 3, "H4": 3, "D1": 3}
# poll khong lay lui qua moc nay (neu ngung lau hon -> backfill khi khoi dong / gap detector)
MAX_LAG = {"M1": timedelta(days=1), "M5": timedelta(days=2), "M15": timedelta(days=3), "H1": timedelta(days=30),
           "H4": timedelta(days=60), "D1": timedelta(days=400)}
SEEN_KEEP = timedelta(days=14)
MAX_PAGES = 400

DEFAULT_BASES = ("BTC ETH BNB SOL XRP ADA DOGE TON AVAX LINK DOT LTC TRX BCH ATOM NEAR UNI XLM ETC APT ARB OP SUI INJ AAVE FIL HBAR SHIB ICP")


def to_ccxt(symbol: str) -> str | None:
    """CRYPTO:BTCUSDT -> BTC/USDT (None neu khong phai cap /USDT)."""
    if not symbol.startswith("CRYPTO:") or not symbol.endswith("USDT"):
        return None
    base = symbol[7:-4]
    return f"{base}/USDT" if base.isalnum() else None


def default_symbols() -> str:
    return ",".join(f"CRYPTO:{b}USDT" for b in DEFAULT_BASES.split())


def _default_factory(name: str) -> Any:  # pragma: no cover - can mang/ccxt that
    import ccxt.async_support as ccxt
    opts = {"enableRateLimit": True, "timeout": 15000}
    if name in MIN_INTERVAL_MS:
        opts["rateLimit"] = MIN_INTERVAL_MS[name]
    return getattr(ccxt, name)(opts)


class CryptoCcxtProvider(Provider):
    name = "crypto_ccxt"
    fetch_tfs = ["M1", "M5", "M15", "H1", "H4", "D1"]
    chunk = timedelta(days=1)
    lookback = timedelta(hours=2)
    poll_interval = 60.0
    has_quotes = False              # quote chay o vong rieng (quote_stream_interval)
    trades_weekends = True
    resample_m1 = False             # nen goc cua san cho TUNG tf (khong resample tu M1: tranh nen do dang + lech UTC cua san)

    def __init__(self, exchanges: list[str], symbols: list[str], *, quote_interval: float = 15.0,
                 depth: dict[str, int] | None = None, poll_interval: float = 60.0,
                 factory: Callable[[str], Any] = _default_factory, now: Callable[[], datetime] = utcnow):
        if not exchanges:
            raise ValueError("CRYPTO_EXCHANGES rong")
        self.exchange_names = list(exchanges)
        self.symbols = [s for s in symbols if to_ccxt(s)]
        self.quote_stream_interval = max(0.0, quote_interval)
        self.depth = {**DEFAULT_DEPTH, **(depth or {})}
        self.poll_interval = poll_interval
        self._factory, self._now = factory, now
        self._ex: dict[str, Any] = {}
        self._markets_ok: dict[str, bool] = {}
        self._retry_load: dict[str, datetime] = {}
        self._last_seen: dict[tuple[str, str], datetime] = {}
        self._last_poll: dict[tuple[str, str], datetime] = {}
        self._seen_h1: dict[str, set[datetime]] = {}
        self._known_empty: dict[str, set[datetime]] = {}
        self.last_exchange: dict[str, str] = {}      # symbol -> san da phuc vu gan nhat (hien o /status)

    # ---------------------------------------------------------------- san + thi truong
    def _exchange(self, name: str) -> Any:
        if name not in self._ex:
            self._ex[name] = self._factory(name)
        return self._ex[name]

    async def _load(self, name: str) -> bool:
        """Nap danh sach thi truong cua san (1 lan; that bai -> thu lai sau 5 phut)."""
        if self._markets_ok.get(name):
            return True
        now = self._now()
        if (t := self._retry_load.get(name)) and now < t:
            return False
        try:
            await self._exchange(name).load_markets()
            self._markets_ok[name] = True
            return True
        except Exception as e:  # noqa: BLE001
            self._retry_load[name] = now + timedelta(minutes=5)
            log.warning("crypto: san %s khong nap duoc thi truong (%s) -> thu lai sau 5 phut", name, type(e).__name__)
            return False

    async def _exchanges_for(self, symbol: str) -> list[str]:
        """San (theo uu tien) co niem yet symbol."""
        cc = to_ccxt(symbol)
        out = []
        for n in self.exchange_names:
            if await self._load(n):
                m = getattr(self._exchange(n), "markets", None) or {}
                if cc in m and m[cc].get("active") is not False:
                    out.append(n)
        return out

    def supports(self, symbol: str) -> bool:
        return to_ccxt(symbol) is not None

    def expects_data(self, now: datetime, symbol: str) -> bool:
        return True                 # 24/7

    # ---------------------------------------------------------------- lich su / poll
    def chunk_for(self, tf: str) -> timedelta:
        return timedelta(days=CHUNK_DAYS[tf])

    def backfill_start(self, tf: str, default: datetime, now: datetime) -> datetime:
        return ensure_utc(now) - timedelta(days=self.depth[tf])     # ke hoach rieng cua provider (thay cua so chung BACKFILL_DAYS)

    def poll_tfs(self, symbol: str, now: datetime) -> list[str]:
        due = []
        for tf in self.fetch_tfs:
            last = self._last_poll.get((symbol, tf))
            if last is None or (now - last).total_seconds() >= POLL_EVERY[tf] - 10:
                self._last_poll[(symbol, tf)] = now
                due.append(tf)
        return due

    def poll_start(self, symbol: str, tf: str, now: datetime) -> datetime | None:
        now = ensure_utc(now)
        ls = self._last_seen.get((symbol, tf))
        floor_back = floor_ts(now - POLL_BARS[tf] * timedelta(seconds=TF_SECONDS[tf]), tf)
        if ls is None:
            return floor_back
        return max(ls, now - MAX_LAG[tf])   # nen dong cuoi da thay -> luon co >=1 nen khi san con song

    def rewind(self, symbol: str, tf: str, to: datetime) -> None:
        if (cur := self._last_seen.get((symbol, tf))) is not None and cur > to:
            self._last_seen[(symbol, tf)] = ensure_utc(to)

    # ---------------------------------------------------------------- nen
    async def _paged(self, ex: Any, name: str, cc: str, tf: str, start: datetime, end: datetime) -> list[list]:
        step = TF_SECONDS[tf] * 1000
        s_ms, e_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        lim = PAGE_LIMIT.get(name, 500)
        rows: dict[int, list] = {}
        since, prev_last = s_ms, None
        for _ in range(MAX_PAGES):
            chunk = await ex.fetch_ohlcv(cc, CCXT_TF[tf], since=since, limit=lim)
            if not chunk:
                break
            for r in chunk:
                if s_ms <= r[0] < e_ms:
                    rows[int(r[0])] = r
            last = int(chunk[-1][0])
            if prev_last is not None and last <= prev_last:
                break
            prev_last = last
            if last + step >= e_ms:
                break
            since = last + step
        return [rows[k] for k in sorted(rows)]

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in CCXT_TF:
            raise FatalError(f"crypto_ccxt: tf khong ho tro {tf}")
        cc = to_ccxt(symbol)
        if cc is None:
            raise FatalError(f"crypto_ccxt khong ho tro {symbol}")
        now = ensure_utc(self._now())
        step = timedelta(seconds=TF_SECONDS[tf])
        closed_edge = floor_ts(now, tf)                    # nen co ts_open >= moc nay dang hinh thanh
        s, e = ensure_utc(start), min(ensure_utc(end), closed_edge)
        if s >= e:
            return []
        names = await self._exchanges_for(symbol)
        if not names:
            raise RetryableError(f"crypto_ccxt: khong san nao co {cc} (san: {','.join(self.exchange_names)})")
        errors: list[str] = []
        for n in names:
            try:
                rows = await self._paged(self._exchange(n), n, cc, tf, s, e)
            except Exception as ex_:  # noqa: BLE001  (RateLimitExceeded, NetworkError, ExchangeError...)
                errors.append(f"{n}:{type(ex_).__name__}")
                continue
            self.last_exchange[symbol] = n
            bars = self._to_bars(symbol, tf, rows, s, e)
            if bars:
                self._note(symbol, tf, bars, s, e, closed_edge, step)
            return bars
        raise RetryableError(f"crypto_ccxt {symbol} {tf}: moi san deu loi ({', '.join(errors)})")

    def _to_bars(self, symbol: str, tf: str, rows: list[list], s: datetime, e: datetime) -> list[Bar]:
        out = []
        for r in rows:
            try:
                o, h, l, c = (float(r[i]) for i in (1, 2, 3, 4))
                v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c, v)):
                continue
            ts = datetime.fromtimestamp(r[0] / 1000, tz=s.tzinfo)
            if s <= ts < e:
                out.append(Bar(symbol, tf, ts, o, h, l, c, v, self.name))
        return out

    def _note(self, symbol: str, tf: str, bars: list[Bar], s: datetime, e: datetime, closed_edge: datetime, step: timedelta) -> None:
        last = bars[-1].ts_open
        if (prev := self._last_seen.get((symbol, tf))) is None or last > prev:
            self._last_seen[(symbol, tf)] = last
        if tf != "H1":
            return
        seen = self._seen_h1.setdefault(symbol, set())
        seen.update(b.ts_open for b in bars)
        cut = closed_edge - SEEN_KEEP
        seen.difference_update({t for t in seen if t < cut})
        if e - s <= timedelta(days=1, hours=1):         # tai lai nguyen ngay ma san van khong co gio nay -> nho (gio that su khong co nen)
            ke = self._known_empty.setdefault(symbol, set())
            t = floor_ts(s, "H1")
            while t < e:
                if t not in seen:
                    ke.add(t)
                t += step

    def find_missing_days(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[datetime]:
        """H1: ngay (UTC) co gio da dong khong thay (tu gio dau tien da thay) va chua duoc xac nhan la 'khong co nen'."""
        if tf != "H1" or not (seen := self._seen_h1.get(symbol)):
            return []
        first = min(seen)
        edge = floor_ts(ensure_utc(end), "H1") - timedelta(hours=2)       # bo 2 gio gan nhat (san co the tre)
        ke = self._known_empty.get(symbol, set())
        days: set[datetime] = set()
        t = max(floor_ts(ensure_utc(start), "H1"), first)
        while t <= edge:
            if t not in seen and t not in ke:
                days.add(floor_ts(t, "D1"))
            t += timedelta(hours=1)
        return sorted(days)

    # ---------------------------------------------------------------- quote
    async def latest_quotes(self) -> list[Quote]:
        """1 lan fetch_tickers / san (nhom theo san uu tien dau tien co cap do); san loi -> thu san ke tiep cho nhom do."""
        pending: dict[str, str] = {}                     # ccxt symbol -> system symbol
        for s in self.symbols:
            pending[to_ccxt(s)] = s
        homes: dict[str, list[str]] = {cc: await self._exchanges_for(sym) for cc, sym in pending.items()}
        quotes: list[Quote] = []
        now = ensure_utc(self._now())
        tried: dict[str, int] = {cc: 0 for cc in pending}
        errs: list[str] = []
        for _ in range(len(self.exchange_names)):
            groups: dict[str, list[str]] = {}
            for cc in list(pending):
                hs = homes.get(cc, [])
                if tried[cc] < len(hs):
                    groups.setdefault(hs[tried[cc]], []).append(cc)
            if not groups:
                break
            for n, ccs in groups.items():
                try:
                    tk = await self._exchange(n).fetch_tickers(ccs)
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{n}:{type(e).__name__}")
                    for cc in ccs:
                        tried[cc] += 1
                    continue
                for cc in ccs:
                    t = tk.get(cc) or {}
                    bid, ask, last = t.get("bid"), t.get("ask"), t.get("last")
                    bid = bid if bid else last
                    ask = ask if ask else last
                    if bid and ask and bid > 0 and ask > 0 and math.isfinite(bid) and math.isfinite(ask):
                        quotes.append(Quote(pending.pop(cc), float(bid), float(ask), now, self.name))
                    else:
                        tried[cc] += 1
        if not quotes and errs:
            raise RetryableError("crypto_ccxt quote: " + ", ".join(errs))
        return quotes

    async def aclose(self) -> None:
        for ex in self._ex.values():
            try:
                await ex.close()
            except Exception:  # noqa: BLE001
                pass
