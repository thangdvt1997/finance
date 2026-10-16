"""Frankfurter (ECB reference rates, EOD, khong can key, mien phi). Don gian + du phong.

GET {base}/{from}..{to}?base=EUR&symbols=USD  -> {"rates": {"2024-01-02": {"USD": 1.09}}}
Nen D1: o=h=l=c=ty gia tham chieu, v=0. ECB chi cong bo ngay lam viec (~16:00 CET).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, Quote, ensure_utc, utcnow
from ..ratelimit import RateLimiter
from ..symbols import is_fx_pair, split_pair
from .base import HttpProvider

BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterProvider(HttpProvider):
    name = "frankfurter"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=90)
    lookback = timedelta(days=7)
    poll_interval = 3600.0
    has_quotes = True

    def __init__(self, client: httpx.AsyncClient, *, base_url: str = BASE_URL, rate_per_min: int = 30,
                 poll_interval: float = 3600.0, **kw):
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval

    def supports(self, symbol: str) -> bool:
        return is_fx_pair(symbol) and not symbol.startswith(("XAU", "XAG", "XPT", "XPD"))

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf != "D1":
            raise FatalError("frankfurter chi co D1")
        base, quote = split_pair(symbol)
        s, e = ensure_utc(start).date(), (ensure_utc(end) - timedelta(seconds=1)).date()
        r = await self._request(f"{self.base_url}/{s.isoformat()}..{e.isoformat()}", {"base": base, "symbols": quote})
        if r.status_code in (404, 422):  # khong co du lieu / ky han khong hop le
            return []
        if r.status_code != 200:
            raise FatalError(f"frankfurter: HTTP {r.status_code}")
        rates = r.json().get("rates", {})
        bars = []
        for day in sorted(rates):
            px = rates[day].get(quote)
            if px is None:
                continue
            ts = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            if ensure_utc(start) <= ts < ensure_utc(end):
                bars.append(Bar(symbol, "D1", ts, px, px, px, px, 0.0, self.name))
        return bars

    async def latest_quote(self, symbol: str) -> Quote | None:
        base, quote = split_pair(symbol)
        r = await self._request(f"{self.base_url}/latest", {"base": base, "symbols": quote})
        if r.status_code != 200:
            return None
        j = r.json()
        px = j.get("rates", {}).get(quote)
        if px is None:
            return None
        ts = datetime.fromisoformat(j.get("date", utcnow().date().isoformat())).replace(tzinfo=timezone.utc)
        return Quote(symbol, px, px, ts, self.name)
