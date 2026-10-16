"""Yahoo Finance chart API (v8) -- nen D1 THO (open/high/low/close chua dieu chinh co tuc; chia tach da duoc Yahoo dieu chinh)
cho ETF/co phieu My (`US:SPY`), co phieu VN (`VN:FPT` <- FPT.VN, VND) va vang (`XAUUSD` <- futures GC=F). MAC DINH TAT.

CANH BAO ToS: API khong chinh thuc, Yahoo chi cho muc dich ca nhan/phi thuong mai -> CHI dung ca nhan, khong phan phoi lai.
Bat: PROVIDERS co `yahoo_daily` VA ALLOW_RISKY_PROVIDERS=true. TAT khan cap: bo `yahoo_daily` khoi PROVIDERS hoac dat
ALLOW_RISKY_PROVIDERS=false (khong can sua code). Dung cho BACKFILL lich su + cap nhat hang ngay SAU GIO DONG CUA My
(`YAHOO_DAILY_AT_UTC`, mac dinh 22:30 UTC). Moi nen D1 co source='yahoo_daily' (ca lich su lan hang ngay -> khong co moc noi).

Quy tac ts_open: ngay giao dich cuc bo cua san (ts + gmtoffset) @ 00:00 UTC. Nen cua NGAY HIEN TAI (UTC) bi bo (chua dong cua).
Uu tien nguon khi nhieu nguon cung (symbol, tf, ts_open): xem docs/DATA_SOURCE_PRIORITY.md (truy van doc DISTINCT ON ... ORDER BY source).
"""
from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc, utcnow
from ..ratelimit import RateLimiter
from ..symbols import strip_prefix
from .base import HttpProvider

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
# Ten he thong -> ma Yahoo (ngoai le; mac dinh 'US:XXX' -> 'XXX')
TICKER_MAP = {"XAUUSD": "GC=F", "XAGUSD": "SI=F"}
UA = "Mozilla/5.0 (compatible; trading-system-market-collector/0.1; personal-use)"


def to_ticker(symbol: str) -> str | None:
    if symbol in TICKER_MAP:
        return TICKER_MAP[symbol]
    if symbol.startswith("VN:") and len(symbol) > 3:      # VN:FPT -> FPT.VN (Yahoo tra gia VND that, khop vnstock)
        return strip_prefix(symbol) + ".VN"
    if symbol.startswith("US:") and len(symbol) > 3:
        return strip_prefix(symbol).replace(".", "-")
    return None


def parse_chart(j: dict, symbol: str, source: str = "yahoo_daily", *, before: datetime | None = None) -> list[Bar]:
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        return []
    r = res[0]
    off = int((r.get("meta") or {}).get("gmtoffset") or 0)
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    ts = r.get("timestamp") or []
    o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    seen: dict[datetime, Bar] = {}
    for i, t in enumerate(ts):
        try:
            vals = (o[i], h[i], l[i], c[i])
        except IndexError:
            continue
        if any(x is None or not math.isfinite(float(x)) for x in vals):
            continue
        day = datetime.fromtimestamp(int(t) + off, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if before is not None and day >= before:
            continue
        vol = v[i] if i < len(v) and v[i] is not None else 0.0
        seen[day] = Bar(symbol, "D1", day, float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3]), float(vol), source)
    return [seen[k] for k in sorted(seen)]


class YahooDailyProvider(HttpProvider):
    name = "yahoo_daily"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=3650)       # boi so cua 1 ngay; ~3 request cho 27 nam lich su
    lookback = timedelta(days=10)
    poll_interval = 86400.0
    has_quotes = False

    def __init__(self, client: httpx.AsyncClient, *, base_url: str = BASE_URL, rate_per_min: int = 10,
                 at_utc: str = "22:30", **kw):
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self.base_url = base_url.rstrip("/")
        hh, _, mm = at_utc.partition(":")
        self.at = time(int(hh), int(mm or 0), tzinfo=timezone.utc)
        self._headers = {"User-Agent": UA, "Accept": "application/json"}

    def supports(self, symbol: str) -> bool:
        return to_ticker(symbol) is not None

    def next_poll_delay(self, now: datetime) -> float:
        """Poll 1 lan/ngay luc `at` UTC (sau gio dong cua My ca khi DST)."""
        now = ensure_utc(now)
        nxt = datetime.combine(now.date(), self.at)
        if nxt <= now + timedelta(seconds=30):
            nxt += timedelta(days=1)
        return (nxt - now).total_seconds()

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf != "D1":
            raise FatalError("yahoo_daily chi co D1")
        tk = to_ticker(symbol)
        if tk is None:
            raise FatalError(f"yahoo_daily khong ho tro {symbol}")
        s = ensure_utc(start)
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        e = min(ensure_utc(end), today)            # khong lay nen ngay hien tai (chua dong)
        if s >= e:
            return []
        params = {"period1": int((s - timedelta(days=1)).timestamp()), "period2": int((e + timedelta(days=1)).timestamp()),
                  "interval": "1d", "includePrePost": "false", "events": "div,splits"}
        r = await self._request(f"{self.base_url}/{tk}", params, self._headers)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise FatalError(f"yahoo_daily: HTTP {r.status_code}")
        try:
            j = r.json()
        except ValueError:
            raise FatalError("yahoo_daily: phan hoi khong phai JSON") from None
        return [b for b in parse_chart(j, symbol, self.name, before=today) if s <= b.ts_open < e]
