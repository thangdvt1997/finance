"""Gia D1 + quy tac vao/thoat KHONG look-ahead + che do thi truong (tinh chi tu D1 DA DONG truoc thoi diem quan sat).

Vao lenh gia dinh = gia MO cua nen D1 dau tien co ts_open > observed_at. Thoat = gia DONG cua nen thu k (k=1/5/21) tinh tu nen vao (nen vao la nen 1).
Nen chua du => 'pending'. Chi dung nen o/sau nen vao cho entry/exit; che do thi truong chi dung nen DA DONG truoc observed_at.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from .config import HORIZONS, MAX_ENTRY_GAP_DAYS, UTC

DAY = 86400
# Ma noi bo khong co gia D1 truc tiep -> thay the bang ETF/ma co gia (ghi trong methodology; huong gia thuong cung chieu).
# DXY KHONG co proxy (US:UUP chi co vai nen D1) => khong cham duoc, hien "pending/chua co gia".
PROXY = {"BTCUSD": "CRYPTO:BTCUSDT", "ETHUSD": "CRYPTO:ETHUSDT", "US:SPX": "US:SPY", "US:NDX": "US:QQQ", "XAGUSD": "US:SLV", "USOIL": "US:USO"}


@dataclass
class Series:
    ts: list[int]            # epoch giay mo nen, tang dan
    o: list[float]
    c: list[float]
    _vol: Optional[np.ndarray] = None

    def logret(self) -> np.ndarray:
        if self._vol is None:
            c = np.asarray(self.c, dtype=float)
            r = np.zeros_like(c)
            with np.errstate(divide="ignore", invalid="ignore"):
                r[1:] = np.log(c[1:] / c[:-1])
            self._vol = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
        return self._vol


@dataclass
class Fill:
    entry_ts: datetime
    entry_px: float
    exit_ts: datetime
    exit_px: float
    ret_log: float


def epoch(dt: datetime) -> int:
    return int(dt.timestamp())


class PriceBook:
    def __init__(self, series: Optional[dict[str, Series]] = None):
        self.series: dict[str, Series] = series or {}

    @staticmethod
    def build(rows: dict[str, list[tuple[datetime, float, float]]]) -> "PriceBook":
        out = {}
        for k, lst in rows.items():
            lst = sorted((t, o, c) for t, o, c in lst if c and c > 0)
            if lst:
                out[k] = Series([epoch(t) for t, _, _ in lst], [float(o) if o and o > 0 else float(c) for _, o, c in lst], [float(c) for _, _, c in lst])
        return PriceBook(out)

    def key(self, symbol: str) -> Optional[str]:
        if symbol in self.series:
            return symbol
        p = PROXY.get(symbol)
        return p if p and p in self.series else None

    def has(self, symbol: str) -> bool:
        return self.key(symbol) is not None

    def fill(self, symbol: str, observed_at: datetime, horizon: str) -> Optional[Fill] | str:
        """Fill | 'pending' (chua du nen) | None (khong co gia / gia loi thoi)."""
        k = self.key(symbol)
        if k is None:
            return None
        s = self.series[k]
        i = bisect_right(s.ts, epoch(observed_at))           # nen dau tien co ts_open > observed_at
        if i >= len(s.ts):
            return "pending"
        if s.ts[i] - epoch(observed_at) > MAX_ENTRY_GAP_DAYS * DAY:
            return None                                       # khoang trong du lieu gia
        j = i + HORIZONS[horizon] - 1
        if j >= len(s.ts):
            return "pending"
        if s.ts[j] - s.ts[i] > (HORIZONS[horizon] * 3 + 6) * DAY:
            return None                                       # nen thoat qua xa (thieu du lieu)
        e, x = s.o[i], s.c[j]
        if not (e > 0 and x > 0):
            return None
        return Fill(datetime.fromtimestamp(s.ts[i], UTC), e, datetime.fromtimestamp(s.ts[j], UTC), x, math.log(x / e))

    def regime(self, symbol: str, observed_at: datetime) -> Optional[str]:
        """trend|range|high_vol|low_vol tu cac nen D1 DA DONG (ts_open + 1 ngay <= observed_at). Thieu du lieu => None."""
        k = self.key(symbol)
        if k is None:
            return None
        s = self.series[k]
        n = bisect_right(s.ts, epoch(observed_at) - DAY)      # cac nen co ts_open <= observed-1d  => da dong
        if n < 60:
            return None
        r = s.logret()[:n]
        w = 20
        cur = float(np.std(r[n - w:n], ddof=1))
        lo = max(w, n - 250)
        hist = np.array([np.std(r[t - w:t], ddof=1) for t in range(lo, n)])
        if cur <= 0 or len(hist) < 30:
            return None
        pct = float((hist < cur).mean())
        if pct >= 0.75:
            return "high_vol"
        if pct <= 0.25:
            return "low_vol"
        t = float(np.sum(r[n - w:n])) / (cur * math.sqrt(w))
        return "trend" if abs(t) >= 1.0 else "range"


def min_date(views_observed: list[datetime], pad_days: int = 400) -> Optional[datetime]:
    return (min(views_observed) - timedelta(days=pad_days)) if views_observed else None
