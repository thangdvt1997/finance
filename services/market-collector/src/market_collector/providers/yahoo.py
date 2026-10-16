"""Yahoo Finance qua yfinance -- MAC DINH TAT: ToS Yahoo chi cho muc dich ca nhan, API khong chinh thuc.
Chi bat khi: PROVIDERS co 'yahoo' VA ALLOW_RISKY_PROVIDERS=true. Khung toi thieu, chua kiem chung.
`fetcher(ticker, start, end, interval) -> DataFrame|list[dict]` inject duoc de test."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..models import Bar, ensure_utc
from ..ratelimit import RateLimiter
from ..symbols import is_fx_pair, strip_prefix
from .base import Provider

INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "D1": "1d"}


def to_yahoo(symbol: str) -> str:
    if is_fx_pair(symbol):
        return f"{symbol}=X" if not symbol.startswith("XAU") else "GC=F"
    return strip_prefix(symbol)


def _default_fetcher(ticker: str, start: str, end: str, interval: str):
    import yfinance as yf  # lazy
    return yf.Ticker(ticker).history(start=start, end=end, interval=interval, auto_adjust=False)


class YahooProvider(Provider):
    name = "yahoo"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=30)
    lookback = timedelta(days=7)

    def __init__(self, *, fetcher: Callable[..., Any] | None = None, poll_interval: float = 900.0):
        self._fetcher = fetcher or _default_fetcher
        self.limiter = RateLimiter(10, 60.0)
        self.poll_interval = poll_interval

    def supports(self, symbol: str) -> bool:
        return True

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in INTERVALS:
            return []
        await self.limiter.acquire()
        s, e = ensure_utc(start), ensure_utc(end)
        data = await asyncio.to_thread(self._fetcher, to_yahoo(symbol), s.date().isoformat(), e.date().isoformat(), INTERVALS[tf])
        if data is None:
            return []
        rows = data.reset_index().to_dict("records") if hasattr(data, "reset_index") else list(data)
        bars = []
        for r in rows:
            t = r.get("Date") or r.get("Datetime") or r.get("time")
            if hasattr(t, "to_pydatetime"):
                t = t.to_pydatetime()
            ts = (t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc))
            if s <= ts < e:
                bars.append(Bar(symbol, tf, ts, float(r["Open"]), float(r["High"]), float(r["Low"]),
                                float(r["Close"]), float(r.get("Volume") or 0), self.name))
        return sorted(bars, key=lambda b: b.ts_open)
