"""Chuỗi nến ĐÃ ĐÓNG thêm dần (append-only) + ATR Wilder + tổng cộng dồn. Mọi đại lượng tại nến i chỉ phụ thuộc nến <= i."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}


@dataclass(frozen=True, slots=True)
class Bar:
    ts: datetime  # ts_open (UTC)
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0

    def valid(self) -> bool:
        vals = (self.o, self.h, self.l, self.c)
        return all(math.isfinite(x) and x > 0 for x in vals) and self.l <= min(self.o, self.c) and self.h >= max(self.o, self.c)


class Series:
    def __init__(self, atr_period: int = 14, long_body_atr: float = 1.5):
        self.p = int(atr_period)
        self.long_body_atr = float(long_body_atr)
        self.ts: list[datetime] = []
        self.o: list[float] = []
        self.h: list[float] = []
        self.l: list[float] = []
        self.c: list[float] = []
        self.v: list[float] = []
        self.atr: list[float] = []
        self.cum_green: list[int] = [0]     # số nến xanh trong [0, j)
        self.cum_longred: list[int] = [0]   # số nến đỏ thân dài trong [0, j)
        self.cum_gbody: list[float] = [0.0]  # tổng thân nến xanh trong [0, j)
        self.cum_rbody: list[float] = [0.0]  # tổng thân nến đỏ trong [0, j)

    def __len__(self) -> int:
        return len(self.ts)

    def atr_ref(self, j: int) -> float:
        """ATR đã biết TRƯỚC khi nến j mở (ATR đến nến j-1) -> chuẩn hoá thân/nến j không bị chính nó làm phồng."""
        a = self.atr[j - 1] if j >= 1 else self.atr[0]
        return max(a, 1e-12)

    def append(self, b: Bar) -> int:
        i = len(self.ts)
        tr = b.h - b.l if i == 0 else max(b.h - b.l, abs(b.h - self.c[-1]), abs(b.l - self.c[-1]))
        if i == 0:
            a = tr
        elif i < self.p:
            a = (self.atr[-1] * i + tr) / (i + 1)
        else:
            a = (self.atr[-1] * (self.p - 1) + tr) / self.p
        self.ts.append(b.ts); self.o.append(b.o); self.h.append(b.h); self.l.append(b.l); self.c.append(b.c); self.v.append(b.v)
        self.atr.append(a)
        body = abs(b.c - b.o)
        green = 1 if b.c > b.o else 0
        longred = 1 if (b.c < b.o and i >= 1 and body >= self.long_body_atr * self.atr_ref(i)) else 0
        self.cum_green.append(self.cum_green[-1] + green)
        self.cum_longred.append(self.cum_longred[-1] + longred)
        self.cum_gbody.append(self.cum_gbody[-1] + (body if green else 0.0))
        self.cum_rbody.append(self.cum_rbody[-1] + (body if b.c < b.o else 0.0))
        return i

    # ------------------------------------------------------------------ tiện ích nến
    def body(self, j: int) -> float:
        return abs(self.c[j] - self.o[j])

    def is_red(self, j: int) -> bool:
        return self.c[j] < self.o[j]

    def hi(self, a: int, b: int) -> float:
        """max high trên [a, b] (đóng hai đầu)."""
        return max(self.h[a:b + 1])

    def lo(self, a: int, b: int) -> float:
        return min(self.l[a:b + 1])

    def green_count(self, a: int, b: int) -> int:
        """số nến xanh trong [a, b]."""
        return self.cum_green[b + 1] - self.cum_green[a]

    def longred_count(self, a: int, b: int) -> int:
        return self.cum_longred[b + 1] - self.cum_longred[a]

    def green_body_share(self, a: int, b: int) -> float:
        """tỷ trọng thân nến xanh trong tổng thân nến (xanh+đỏ) trên [a, b] — đo mức 'nến xanh cản' có trọng số."""
        g = self.cum_gbody[b + 1] - self.cum_gbody[a]
        r = self.cum_rbody[b + 1] - self.cum_rbody[a]
        return g / (g + r) if g + r > 0 else 0.0
