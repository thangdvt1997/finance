"""Alpaca Market Data (goi Free: feed IEX, co phieu + ETF My). CAN ALPACA_KEY + ALPACA_SECRET; thieu => tu tat.

Free: 200 goi/phut, chi feed `iex` (SIP can goi tra phi) -> ta luon dat feed=iex (khong bi chan 15 phut cua SIP).
Symbol noi bo `US:AAPL` -> `AAPL`. Nen D1 ts_open chuan hoa ve 00:00 UTC cua ngay giao dich (Alpaca tra 04:00/05:00Z).
Khoa di qua header APCA-API-KEY-ID / APCA-API-SECRET-KEY, khong vao URL/log.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc, floor_ts, utcnow
from ..ratelimit import RateLimiter
from .base import HttpProvider

BASE_URL = "https://data.alpaca.markets"
TIMEFRAMES = {"M1": "1Min", "M5": "5Min", "M15": "15Min", "H1": "1Hour", "H4": "4Hour", "D1": "1Day"}


def parse_bars(j: dict, symbol: str, tf: str, source: str = "alpaca") -> list[Bar]:
    out = []
    for b in j.get("bars") or []:
        ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(timezone.utc)
        if tf == "D1":
            ts = floor_ts(ts, "D1")
        out.append(Bar(symbol, tf, ts, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"]), float(b.get("v") or 0), source))
    return out


class AlpacaProvider(HttpProvider):
    name = "alpaca"
    chunk = timedelta(days=30)
    lookback = timedelta(days=3)
    has_quotes = False

    def __init__(self, client: httpx.AsyncClient, key: str, secret: str, *, tfs: list[str] | None = None,
                 base_url: str = BASE_URL, feed: str = "iex", rate_per_min: int = 150, poll_interval: float = 900.0, **kw):
        if not key or not secret:
            raise ValueError("ALPACA_KEY/ALPACA_SECRET trong")
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}
        self.fetch_tfs = [t for t in (tfs or ["H1", "D1"]) if t in TIMEFRAMES]
        self.base_url, self.feed, self.poll_interval = base_url.rstrip("/"), feed, poll_interval

    def supports(self, symbol: str) -> bool:
        return symbol.startswith("US:") and len(symbol) > 3

    def expects_data(self, now: datetime, symbol: str) -> bool:
        return now.weekday() < 5

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in TIMEFRAMES:
            raise FatalError(f"tf khong ho tro: {tf}")
        start, end = ensure_utc(start), min(ensure_utc(end), utcnow())
        if start >= end:
            return []
        ticker = symbol[3:].replace("-", ".")
        params = {"timeframe": TIMEFRAMES[tf], "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": self.feed, "limit": 10000,
                  "adjustment": "raw", "sort": "asc"}
        bars: list[Bar] = []
        for _ in range(20):  # toi da 20 trang / lan
            r = await self._request(f"{self.base_url}/v2/stocks/{ticker}/bars", params, self._headers)
            if r.status_code in (404, 422):
                break
            if r.status_code != 200:
                raise FatalError(f"alpaca: HTTP {r.status_code}")
            j = r.json()
            bars.extend(parse_bars(j, symbol, tf, self.name))
            tok = j.get("next_page_token")
            if not tok:
                break
            params = {**params, "page_token": tok}
        lo = floor_ts(start, "D1") if tf == "D1" else start
        return [b for b in bars if lo <= b.ts_open < end]
