"""Stooq (CSV D1) -- MAC DINH TAT: ToS khong cho phep ro rang viec thu thap tu dong/redistribute.
Chi bat khi: PROVIDERS co 'stooq' VA ALLOW_RISKY_PROVIDERS=true. Khung toi thieu, chua kiem chung."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc
from ..ratelimit import RateLimiter
from ..symbols import is_fx_pair, strip_prefix
from .base import HttpProvider


class StooqProvider(HttpProvider):
    name = "stooq"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=365)
    lookback = timedelta(days=7)

    def __init__(self, client: httpx.AsyncClient, *, base_url: str = "https://stooq.com", poll_interval: float = 3600.0, **kw):
        super().__init__(client, RateLimiter(10, 60.0), **kw)
        self.base_url, self.poll_interval = base_url.rstrip("/"), poll_interval

    def supports(self, symbol: str) -> bool:
        return is_fx_pair(symbol) or symbol.startswith("US:")

    @staticmethod
    def _code(symbol: str) -> str:
        return symbol.lower() if is_fx_pair(symbol) else strip_prefix(symbol).lower() + ".us"

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf != "D1":
            raise FatalError("stooq chi D1")
        s, e = ensure_utc(start), ensure_utc(end)
        r = await self._request(f"{self.base_url}/q/d/l/", {"s": self._code(symbol), "i": "d",
                                "d1": s.strftime("%Y%m%d"), "d2": e.strftime("%Y%m%d")})
        if r.status_code != 200 or not r.text.startswith("Date"):
            return []
        bars = []
        for row in csv.DictReader(io.StringIO(r.text)):
            ts = datetime.fromisoformat(row["Date"]).replace(tzinfo=timezone.utc)
            if s <= ts < e:
                bars.append(Bar(symbol, "D1", ts, float(row["Open"]), float(row["High"]), float(row["Low"]),
                                float(row["Close"]), float(row.get("Volume") or 0), self.name))
        return bars
