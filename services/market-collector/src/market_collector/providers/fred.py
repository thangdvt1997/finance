"""FRED (St. Louis Fed) - chuoi vi mo qua `fredgraph.csv` (KHONG can API key, mien phi). Phat nen D1 (o=h=l=c=gia tri, v=0)
voi symbol `FRED:<SERIES>` (vd FRED:DGS10 = lai suat TP My 10 nam). Gia tri thieu ('.') bi bo. Mac dinh chi chuoi ngay > 0.
Poll 6h (du lieu FRED cap nhat toi da 1 lan/ngay). Chuoi mac dinh la du lieu cong khai (lai suat, ty gia, lam phat ky vong).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc, utcnow
from ..ratelimit import RateLimiter
from .base import HttpProvider

BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_SERIES = re.compile(r"[A-Z0-9_]{1,40}")


def parse_csv(text: str, symbol: str, source: str = "fred") -> list[Bar]:
    out = []
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    for row in rows[1:]:
        if len(row) < 2 or row[1].strip() in ("", "."):
            continue
        try:
            ts = datetime.fromisoformat(row[0].strip()).replace(tzinfo=timezone.utc)
            v = float(row[1])
        except ValueError:
            continue
        out.append(Bar(symbol, "D1", ts, v, v, v, v, 0.0, source))
    return sorted(out, key=lambda b: b.ts_open)


class FredProvider(HttpProvider):
    name = "fred"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=365)
    lookback = timedelta(days=14)
    has_quotes = False

    def __init__(self, client: httpx.AsyncClient, *, base_url: str = BASE_URL, rate_per_min: int = 20,
                 poll_interval: float = 21600.0, **kw):
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self.base_url, self.poll_interval = base_url, poll_interval

    def supports(self, symbol: str) -> bool:
        return symbol.startswith("FRED:") and bool(_SERIES.fullmatch(symbol[5:]))

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf != "D1":
            raise FatalError("fred chi co D1")
        start, end = ensure_utc(start), min(ensure_utc(end), utcnow() + timedelta(days=1))
        if start >= end:
            return []
        params = {"id": symbol[5:], "cosd": start.date().isoformat(), "coed": (end - timedelta(seconds=1)).date().isoformat()}
        r = await self._request(self.base_url, params)
        if r.status_code in (400, 404):
            raise FatalError(f"fred: khong co chuoi {symbol[5:]} (HTTP {r.status_code})")
        if r.status_code != 200:
            raise FatalError(f"fred: HTTP {r.status_code}")
        return [b for b in parse_csv(r.text, symbol, self.name) if start <= b.ts_open < end]
