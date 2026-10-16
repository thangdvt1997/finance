"""TrueFX (Integral) - gia FX real-time top-of-book, mien phi nhung CAN dang ky tai khoan (TRUEFX_USER/TRUEFX_PASS).
Thieu thong tin dang nhap => provider tu tat. Chi phat QUOTE (md.quotes) + giu bo dem phut de DOI CHIEU Dukascopy.

API (tai lieu TrueFX web rates): GET http://webrates.truefx.com/rates/connect.html?u=..&p=..&q=ozrates&c=EUR/USD,..&f=csv
CSV moi dong: SYMBOL,ts_ms,bid_big,bid_pts,ask_big,ask_pts,high,low,open  (gia = big + pts, noi CHUOI: '1.13'+'516' = 1.13516,
'109.'+'123' = 109.123). Giao thuc la HTTP (khong TLS) do TrueFX thiet ke -> mat khau di qua chuoi truy van khong ma hoa:
dung tai khoan RIENG chi cho muc dich nay. Phan hoi dang 'user:pass:qualifier:ts' = ma phien -> dung lai qua tham so id=.
CHUA kiem chung voi tai khoan that (phat trien khong co tai khoan); fixture test la MAU THEO TAI LIEU.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError, RetryableError
from ..models import Bar, Quote, ensure_utc, floor_ts, utcnow
from ..ratelimit import RateLimiter
from .base import HttpProvider

BASE_URL = "http://webrates.truefx.com/rates/connect.html"
SUPPORTED = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
             "AUDJPY", "EURCHF", "EURAUD", "GBPCHF", "CADJPY", "CHFJPY", "NZDJPY", "EURCAD"}
KEEP_MINUTES = 240


def parse_rates(text: str) -> dict[str, tuple[float, float, datetime]]:
    """-> {EURUSD: (bid, ask, ts)}; bo qua dong khong hop le."""
    out: dict[str, tuple[float, float, datetime]] = {}
    for line in text.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 6 or "/" not in f[0]:
            continue
        try:
            sym = f[0].replace("/", "").upper()
            ts = datetime.fromtimestamp(int(f[1]) / 1000, tz=timezone.utc)
            bid, ask = float(f[2] + f[3]), float(f[4] + f[5])
        except (ValueError, OverflowError):
            continue
        if bid > 0 and ask > 0:
            out[sym] = (bid, ask, ts)
    return out


class TrueFXProvider(HttpProvider):
    name = "truefx"
    fetch_tfs: list[str] = []   # chi quote; khong co nen (nguon doi chieu)
    has_quotes = True

    def __init__(self, client: httpx.AsyncClient, user: str, password: str, symbols: list[str], *,
                 base_url: str = BASE_URL, poll_interval: float = 30.0, rate_per_min: int = 6, clock=utcnow, **kw):
        if not user or not password:
            raise ValueError("TRUEFX_USER/TRUEFX_PASS trong")
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self._user, self._pass = user, password
        self.symbols = [s for s in symbols if s in SUPPORTED]
        self.base_url, self.poll_interval, self._clock = base_url, poll_interval, clock
        self._sid: str | None = None
        self._snap: dict[str, tuple[float, float, datetime]] = {}
        self._snap_at = 0.0
        self.minute_bid: dict[tuple[str, datetime], float] = {}  # (symbol, phut) -> bid cuoi cung trong phut

    def supports(self, symbol: str) -> bool:
        return symbol in SUPPORTED

    def _params(self) -> dict:
        pairs = ",".join(f"{s[:3]}/{s[3:]}" for s in self.symbols)
        if self._sid:
            return {"id": self._sid, "f": "csv", "c": pairs}
        return {"u": self._user, "p": self._pass, "q": "ozrates", "c": pairs, "f": "csv", "s": "y"}

    async def _snapshot(self) -> dict[str, tuple[float, float, datetime]]:
        if self._snap and time.monotonic() - self._snap_at < self.poll_interval / 2:
            return self._snap
        rates: dict = {}
        for _ in range(2):
            r = await self._request(self.base_url, self._params())
            if r.status_code != 200:
                self._sid = None
                raise RetryableError(f"truefx: HTTP {r.status_code}")
            text = r.text.strip()
            rates = parse_rates(text)
            if rates:
                break
            # khong co dong gia: hoac la ma phien (user:pass:q:ts) hoac chua xac thuc
            first = text.splitlines()[0].strip() if text else ""
            if first.count(":") == 3 and "/" not in first and not self._sid:
                self._sid = first
                continue
            self._sid = None
            raise FatalError("truefx: khong nhan duoc gia (kiem tra TRUEFX_USER/TRUEFX_PASS, tai khoan da kich hoat?)")
        if not rates:
            self._sid = None
            raise RetryableError("truefx: khong lay duoc gia sau khi lay ma phien")
        self._snap, self._snap_at = rates, time.monotonic()
        for sym, (bid, _ask, ts) in rates.items():
            self.minute_bid[(sym, floor_ts(ts, "M1"))] = bid
        if len(self.minute_bid) > 4000:
            cutoff = self._clock() - timedelta(minutes=KEEP_MINUTES)
            self.minute_bid = {k: v for k, v in self.minute_bid.items() if k[1] >= cutoff}
        return rates

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        return []

    async def latest_quote(self, symbol: str) -> Quote | None:
        s = (await self._snapshot()).get(symbol)
        return Quote(symbol, s[0], s[1], s[2], self.name) if s else None

    def expects_data(self, now: datetime, symbol: str) -> bool:
        wd, h = now.weekday(), now.hour
        return not (wd == 5 or (wd == 4 and h >= 22) or (wd == 6 and h < 21))

    def minute_closes(self, symbol: str, start: datetime, end: datetime) -> dict[datetime, float]:
        s, e = ensure_utc(start), ensure_utc(end)
        return {m: v for (sym, m), v in self.minute_bid.items() if sym == symbol and s <= m < e}
