"""Twelve Data (free tier: ~8 req/phut, 800 req/ngay; CAN TWELVEDATA_API_KEY, thieu key => provider tu tat)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError, RateLimited, RetryableError
from ..models import TF_SECONDS, Bar, Quote, ensure_utc, utcnow
from ..ratelimit import RateLimiter
from ..symbols import is_fx_pair, strip_prefix
from .base import HttpProvider

BASE_URL = "https://api.twelvedata.com"
INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h", "D1": "1day"}


def to_td_symbol(symbol: str) -> str:
    if is_fx_pair(symbol):
        return f"{symbol[:3]}/{symbol[3:]}"
    return strip_prefix(symbol)


class TwelveDataProvider(HttpProvider):
    name = "twelvedata"
    chunk = timedelta(days=7)
    lookback = timedelta(days=2)
    has_quotes = True

    def __init__(self, client: httpx.AsyncClient, api_key: str, *, tfs: list[str] | None = None,
                 base_url: str = BASE_URL, rate_per_min: int = 8, poll_interval: float = 300.0, **kw):
        if not api_key:
            raise ValueError("TWELVEDATA_API_KEY trong")
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self._key = api_key
        self.fetch_tfs = tfs or ["H1", "D1"]
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval

    def supports(self, symbol: str) -> bool:
        return True

    def _check(self, j: dict) -> None:
        if j.get("status") == "error":
            code = int(j.get("code", 0) or 0)
            msg = str(j.get("message", ""))[:200].replace(self._key, "***")
            if code == 429:
                raise RateLimited(f"twelvedata: {msg}", 30.0)
            if code in (400, 401, 403, 404):
                if code == 400 and "no data" in msg.lower():
                    return
                raise FatalError(f"twelvedata {code}: {msg}")
            raise RetryableError(f"twelvedata {code}: {msg}")

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in INTERVALS:
            raise FatalError(f"tf khong ho tro: {tf}")
        params = {"symbol": to_td_symbol(symbol), "interval": INTERVALS[tf], "timezone": "UTC", "order": "ASC",
                  "outputsize": 5000, "format": "JSON", "apikey": self._key,
                  "start_date": ensure_utc(start).strftime("%Y-%m-%d %H:%M:%S"),
                  "end_date": ensure_utc(end).strftime("%Y-%m-%d %H:%M:%S")}
        r = await self._request(f"{self.base_url}/time_series", params)
        j = r.json()
        self._check(j)
        bars = []
        for row in j.get("values") or []:
            raw = row["datetime"]
            ts = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            if not (ensure_utc(start) <= ts < ensure_utc(end)):
                continue
            bars.append(Bar(symbol, tf, ts, float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), float(row.get("volume") or 0), self.name))
        return sorted(bars, key=lambda b: b.ts_open)

    async def latest_quote(self, symbol: str) -> Quote | None:
        r = await self._request(f"{self.base_url}/price", {"symbol": to_td_symbol(symbol), "apikey": self._key})
        j = r.json()
        self._check(j)
        if "price" not in j:
            return None
        px = float(j["price"])
        return Quote(symbol, px, px, utcnow(), self.name)
