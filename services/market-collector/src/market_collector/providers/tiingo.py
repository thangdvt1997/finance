"""Tiingo Starter (mien phi): nen EOD (D1) co phieu/ETF My. CAN TIINGO_TOKEN; thieu => tu tat.

Gioi han Starter: 50 req/GIO, 1000 req/NGAY, 500 ma khac nhau/THANG -> RateLimiter 40/gio, poll 6h, toi da TIINGO_MAX_SYMBOLS ma.
Gia THO (open/high/low/close, chua dieu chinh co tuc/chia tach) de khop Alpaca. Token qua header Authorization.
Dieu khoan Tiingo: chi dung noi bo (internal use), khong phan phoi lai.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc, floor_ts, utcnow
from ..ratelimit import RateLimiter
from .base import HttpProvider

BASE_URL = "https://api.tiingo.com"


def parse_eod(rows: list, symbol: str, source: str = "tiingo") -> list[Bar]:
    out = []
    for r in rows or []:
        ts = floor_ts(datetime.fromisoformat(str(r["date"]).replace("Z", "+00:00")).astimezone(timezone.utc), "D1")
        out.append(Bar(symbol, "D1", ts, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                       float(r.get("volume") or 0), source))
    return sorted(out, key=lambda b: b.ts_open)


class TiingoProvider(HttpProvider):
    name = "tiingo"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=365)
    lookback = timedelta(days=7)
    has_quotes = False

    def __init__(self, client: httpx.AsyncClient, token: str, *, base_url: str = BASE_URL, rate_per_hour: int = 40,
                 poll_interval: float = 21600.0, **kw):
        if not token:
            raise ValueError("TIINGO_TOKEN trong")
        super().__init__(client, RateLimiter(rate_per_hour, 3600.0), **kw)
        self._headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        self.base_url, self.poll_interval = base_url.rstrip("/"), poll_interval

    def supports(self, symbol: str) -> bool:
        return symbol.startswith("US:") and len(symbol) > 3

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf != "D1":
            raise FatalError("tiingo (EOD) chi co D1")
        start, end = ensure_utc(start), min(ensure_utc(end), utcnow())
        if start >= end:
            return []
        ticker = symbol[3:].replace(".", "-").lower()
        params = {"startDate": start.date().isoformat(), "endDate": end.date().isoformat(), "format": "json"}
        r = await self._request(f"{self.base_url}/tiingo/daily/{ticker}/prices", params, self._headers)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise FatalError(f"tiingo: HTTP {r.status_code}")
        j = r.json()
        if not isinstance(j, list):
            raise FatalError(f"tiingo: phan hoi la: {str(j)[:100]}")
        return [b for b in parse_eod(j, symbol, self.name) if floor_ts(start, "D1") <= b.ts_open < end]
