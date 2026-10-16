"""OANDA v20 (tai khoan PRACTICE mien phi): nen M1..D qua REST. CAN OANDA_PRACTICE_TOKEN; thieu token => provider tu tat.

Dung gia BID (price=B) de so sanh cung loai voi Dukascopy (BID). Toi da 5000 nen/lan goi; chunk 1 ngay M1 = 1440 nen.
Gioi han OANDA ~120 req/s; ta tu gioi han 60 req/phut. Token KHONG bao gio vao log/loi (di qua header Authorization).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..errors import FatalError
from ..models import Bar, ensure_utc, utcnow
from ..ratelimit import RateLimiter
from ..symbols import is_fx_pair
from .base import HttpProvider

PRACTICE_URL = "https://api-fxpractice.oanda.com"
GRANULARITY = {"M1": "M1", "M5": "M5", "M15": "M15", "H1": "H1", "H4": "H4", "D1": "D"}
_PRICE_KEY = {"B": "bid", "A": "ask", "M": "mid"}


def to_instrument(symbol: str) -> str:
    return f"{symbol[:3]}_{symbol[3:]}"


def parse_time(s: str) -> datetime:
    """'2024-01-02T10:00:00.000000000Z' (ns) -> datetime UTC."""
    s = s.strip().rstrip("Z")
    head, _, frac = s.partition(".")
    return datetime.fromisoformat(head).replace(tzinfo=timezone.utc) + timedelta(microseconds=int((frac + "000000")[:6]))


def parse_candles(j: dict, symbol: str, tf: str, price: str, source: str = "oanda") -> list[Bar]:
    key = _PRICE_KEY[price]
    out = []
    for c in j.get("candles") or []:
        if not c.get("complete", True):
            continue  # nen dang hinh thanh -> bo (se lay o vong sau)
        p = c.get(key)
        if not p:
            continue
        out.append(Bar(symbol, tf, parse_time(c["time"]), float(p["o"]), float(p["h"]), float(p["l"]), float(p["c"]),
                       float(c.get("volume") or 0), source))
    return sorted(out, key=lambda b: b.ts_open)


class OandaProvider(HttpProvider):
    name = "oanda"
    fetch_tfs = ["M1"]
    chunk = timedelta(days=1)
    lookback = timedelta(hours=3)
    has_quotes = False

    def __init__(self, client: httpx.AsyncClient, token: str, *, base_url: str = PRACTICE_URL, price: str = "B",
                 rate_per_min: int = 60, poll_interval: float = 120.0, **kw):
        if not token:
            raise ValueError("OANDA_PRACTICE_TOKEN trong")
        price = (price or "B").upper()
        if price not in _PRICE_KEY:
            raise ValueError("OANDA_PRICE phai la B|A|M")
        super().__init__(client, RateLimiter(rate_per_min, 60.0), **kw)
        self._headers = {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}
        self.base_url, self.price, self.poll_interval = base_url.rstrip("/"), price, poll_interval

    def supports(self, symbol: str) -> bool:
        return is_fx_pair(symbol)

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in GRANULARITY:
            raise FatalError(f"tf khong ho tro: {tf}")
        start, end = ensure_utc(start), min(ensure_utc(end), utcnow())
        if start >= end:
            return []
        params = {"granularity": GRANULARITY[tf], "price": self.price,
                  "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
        r = await self._request(f"{self.base_url}/v3/instruments/{to_instrument(symbol)}/candles", params, self._headers)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            msg = ""
            try:
                msg = str(r.json().get("errorMessage", ""))[:150]
            except ValueError:
                pass
            raise FatalError(f"oanda: HTTP {r.status_code} {msg}".strip())
        return [b for b in parse_candles(r.json(), symbol, tf, self.price, self.name) if start <= b.ts_open < end]
