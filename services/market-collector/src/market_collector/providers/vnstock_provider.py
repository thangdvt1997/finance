"""vnstock (co phieu VN). LUU Y LICENSE: xem README (vnstock 4.x: license rieng, mien phi ca nhan/hoc tap/nghien cuu).

CACH CAI (vnstock KHONG con tren PyPI chinh thuc cho Python 3.12; ban moi phat hanh qua index rieng cua tac gia):
    pip install -U --extra-index-url https://vnstocks.com/api/simple vnstock vnai
(`vnstock3` tren PyPI dung o 3.2.1 / API cu `Vnstock().stock(...).quote.history` -- van duoc ho tro neu da cai.)
Provider tu TAT GON neu khong import duoc `vnstock` (xem `available()`), cac provider khac van chay.

API that (vnstock 4.0.9, da kiem tra): `Market().equity("VNM").ohlcv(start="YYYY-MM-DD", end="YYYY-MM-DD", interval="1D"|"1H"|"1m"...)`
-> DataFrame cot time, open, high, low, close, volume. Nguon mac dinh `kbs`.
Thu vien dong bo -> chay trong thread. `fetcher(symbol, start_date, end_date, interval) -> DataFrame|list[dict]` inject duoc de test.
DON VI GIA: nguon tra NGHIN dong (VNM 57.7 = 57.700 VND; doi chieu CafeF/Vietstock 10-2026: VNM ~57.200-58.000 d).
Provider CHUAN HOA ve VND that (nhan `PRICE_MULTIPLIER`=1000) -> moi nen co phieu VN trong `md.bars` deu o don vi VND
(xem CONTRACTS.md). Volume giu nguyen (so co phieu).
Thoi gian intraday la gio dia phuong (UTC+7, naive) -> doi sang UTC. Nen D1: lay NGAY lam ts_open = 00:00 UTC cua ngay do
(vnstock 4 tra moc 07:00 cho nen ngay -> khong dung gio, tranh lech bucket D1 voi nguon khac).
Telemetry cua vnstock mac dinh bat -> ta dat VNSTOCK_TELEMETRY=off (khong gui so lieu do luong ra ngoai).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..models import Bar, ensure_utc
from ..ratelimit import RateLimiter
from ..symbols import strip_prefix
from .base import Provider

VN_TZ = timezone(timedelta(hours=7))
# vnstock tra gia theo nghin dong -> x1000 = VND that (hop dong: gia VN luon la VND)
PRICE_MULTIPLIER = 1000.0
INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1H", "D1": "1D"}


def _import_vnstock():
    os.environ.setdefault("VNSTOCK_TELEMETRY", "off")
    import vnstock  # lazy
    return vnstock


def _default_fetcher(api_key: str = "", source: str = "VCI") -> Callable[[str, str, str, str], Any]:
    state = {"key_set": False}

    def fetch(symbol: str, start: str, end: str, interval: str):
        vs = _import_vnstock()
        if hasattr(vs, "Market"):  # vnstock >= 4
            if api_key and not state["key_set"]:
                try:
                    vs.change_api_key(api_key)
                except Exception:  # noqa: BLE001 - key sai/khong hop le -> chay guest
                    pass
                state["key_set"] = True
            return vs.Market().equity(symbol).ohlcv(start=start, end=end, interval=interval)
        # vnstock3 / vnstock 3.x
        return vs.Vnstock().stock(symbol=symbol, source=source).quote.history(start=start, end=end, interval=interval)
    return fetch


def _vnd(x: Any, mult: float) -> float:
    return round(float(x) * mult, 4)  # round: tranh nhieu float kieu 57700.00000000001


def _records(data: Any) -> list[dict]:
    if data is None:
        return []
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return list(data)


class VnstockProvider(Provider):
    name = "vnstock"
    fetch_tfs = ["D1"]
    chunk = timedelta(days=365)
    lookback = timedelta(days=7)

    def __init__(self, *, api_key: str = "", fetcher: Callable | None = None, poll_interval: float = 900.0,
                 limiter: RateLimiter | None = None, tfs: list[str] | None = None,
                 price_multiplier: float = PRICE_MULTIPLIER):
        # 20 req/phut khong key (guest), 60 neu co VNSTOCK_API_KEY
        self.limiter = limiter or RateLimiter(60 if api_key else 20, 60.0)
        self._fetcher = fetcher or _default_fetcher(api_key)
        self.poll_interval = poll_interval
        self.fetch_tfs = tfs or ["D1"]
        self.api_key = api_key
        self.price_multiplier = price_multiplier

    @staticmethod
    def available() -> bool:
        try:
            vs = _import_vnstock()
            return hasattr(vs, "Market") or hasattr(vs, "Vnstock")
        except Exception:  # noqa: BLE001 - ImportError hoac loi khoi tao
            return False

    def supports(self, symbol: str) -> bool:
        return symbol.startswith("VN:")

    def expects_data(self, now: datetime, symbol: str) -> bool:
        return now.weekday() < 5

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        if tf not in INTERVALS:
            return []
        await self.limiter.acquire()
        s_local = ensure_utc(start).astimezone(VN_TZ).date().isoformat()
        e_local = ensure_utc(end).astimezone(VN_TZ).date().isoformat()
        data = await asyncio.to_thread(self._fetcher, strip_prefix(symbol), s_local, e_local, INTERVALS[tf])
        bars = []
        for row in _records(data):
            t = row["time"]
            if hasattr(t, "to_pydatetime"):
                t = t.to_pydatetime()
            if isinstance(t, str):
                t = datetime.fromisoformat(t)
            if not isinstance(t, datetime):  # datetime.date
                t = datetime(t.year, t.month, t.day)
            ts = t.replace(tzinfo=VN_TZ) if t.tzinfo is None else t
            if tf == "D1":  # nen ngay: ts_open = 00:00 UTC cua ngay (theo gio VN)
                d = ts.astimezone(VN_TZ).date()
                ts = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
            if not (ensure_utc(start) <= ts < ensure_utc(end)):
                continue
            m = self.price_multiplier
            bars.append(Bar(symbol, tf, ts, _vnd(row["open"], m), _vnd(row["high"], m), _vnd(row["low"], m),
                            _vnd(row["close"], m), float(row.get("volume") or 0), self.name))
        return sorted(bars, key=lambda b: b.ts_open)
