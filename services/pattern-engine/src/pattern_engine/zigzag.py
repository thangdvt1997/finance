"""ZigZag thích nghi ATR, cập nhật TRỰC TUYẾN theo từng nến đã đóng (không nhìn tương lai).

- Ngưỡng đảo chiều = k × ATR tại nến hiện tại.
- Pivot đã xác nhận là append-only (không bao giờ đổi/xoá = không repaint). Pivot chỉ được xác nhận TRỄ (khi giá đã đảo >= ngưỡng).
- `provisional` = cực trị đang chạy của nhịp hiện tại (chưa xác nhận) — các mẫu hình dùng nó như điểm tạm, nhưng nó có thể bị cập nhật ở nến sau.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pivot:
    i: int          # chỉ số nến của cực trị
    price: float
    kind: str       # 'H' | 'L'
    conf_i: int     # nến mà tại đó pivot được xác nhận (-1 = tạm thời)

    @property
    def is_high(self) -> bool:
        return self.kind == "H"


class ZigZag:
    def __init__(self, k: float):
        self.k = float(k)
        self.pivots: list[Pivot] = []
        self.dir = 0          # 0 chưa rõ, +1 đang theo dõi đỉnh, -1 đang theo dõi đáy
        self.ext_i = 0
        self.ext_p = 0.0
        self._hi_i = self._lo_i = 0
        self._hi_p = float("-inf")
        self._lo_p = float("inf")

    def update(self, i: int, o: float, h: float, l: float, c: float, atr: float) -> Pivot | None:
        thr = self.k * atr
        new: Pivot | None = None
        if self.dir == 0:
            if h > self._hi_p:
                self._hi_p, self._hi_i = h, i
            if l < self._lo_p:
                self._lo_p, self._lo_i = l, i
            if h - self._lo_p >= thr and self._lo_i != i:
                new = Pivot(self._lo_i, self._lo_p, "L", i); self.dir = 1; self.ext_i, self.ext_p = i, h
            elif self._hi_p - l >= thr and self._hi_i != i:
                new = Pivot(self._hi_i, self._hi_p, "H", i); self.dir = -1; self.ext_i, self.ext_p = i, l
        elif self.dir == 1:
            if h > self.ext_p:
                self.ext_i, self.ext_p = i, h
                # nến vừa tạo đỉnh mới vừa rơi >= ngưỡng: nến giảm coi như đỉnh trước, đáy sau
                if c < o and h - l >= thr:
                    new = Pivot(i, h, "H", i); self.dir = -1; self.ext_i, self.ext_p = i, l
            elif self.ext_p - l >= thr:
                new = Pivot(self.ext_i, self.ext_p, "H", i); self.dir = -1; self.ext_i, self.ext_p = i, l
        else:
            if l < self.ext_p:
                self.ext_i, self.ext_p = i, l
                if c > o and h - l >= thr:
                    new = Pivot(i, l, "L", i); self.dir = 1; self.ext_i, self.ext_p = i, h
            elif h - self.ext_p >= thr:
                new = Pivot(self.ext_i, self.ext_p, "L", i); self.dir = 1; self.ext_i, self.ext_p = i, h
        if new:
            self.pivots.append(new)
        return new

    def provisional(self) -> Pivot | None:
        if self.dir == 0:
            return None
        return Pivot(self.ext_i, self.ext_p, "H" if self.dir == 1 else "L", -1)

    VIEW_KEEP = 256   # mọi mẫu hình chỉ nhìn <= ~30 pivot gần nhất; giới hạn để chuỗi dài (backtest nhiều năm) không thành O(n^2)

    def view(self) -> list[Pivot]:
        """pivot đã xác nhận (tối đa VIEW_KEEP gần nhất) + cực trị tạm thời (luôn xen kẽ H/L)."""
        p = self.provisional()
        base = self.pivots[-self.VIEW_KEEP:]
        return base + [p] if p else list(base)
