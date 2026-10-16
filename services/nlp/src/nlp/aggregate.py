"""Tổng hợp sentiment theo symbol theo cửa sổ 1h/24h + phát hiện đảo chiều mạnh. Thuần bộ nhớ, thread-safe không cần (1 loop)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

H1, H24 = 3600.0, 86400.0


@dataclass
class Window:
    mean: float | None
    n: int


@dataclass
class Reversal:
    symbol: str
    direction: str          # up (âm -> dương) | down (dương -> âm)
    current: float          # trung bình 1h gần nhất
    baseline: float         # trung bình (24h trừ 1h gần nhất)
    n_current: int
    n_baseline: int
    ts: float = 0.0

    @property
    def dedupe_key(self) -> str:
        hour = datetime.fromtimestamp(self.ts, timezone.utc).strftime("%Y%m%d%H")
        return f"nlp:flip:{self.symbol}:{self.direction}:{hour}"


@dataclass
class SymbolAggregator:
    min_delta: float = 0.5
    min_n_1h: int = 3
    min_n_24h: int = 6
    cooldown_s: float = 6 * 3600
    fresh_s: float = 2 * 3600
    min_abs: float = 0.15                       # hai phía phải đủ lệch khỏi 0 mới tính là "đổi dấu"
    data: dict[str, deque] = field(default_factory=dict)
    last_alert: dict[str, float] = field(default_factory=dict)

    def add(self, symbol: str, ts: float, score: float, weight: float = 1.0) -> None:
        self.data.setdefault(symbol, deque()).append((ts, score, max(weight, 1e-3)))

    def prune(self, now: float) -> None:
        for sym in list(self.data):
            dq = self.data[sym]
            # tin không nhất thiết đến đúng thứ tự thời gian (backfill): lọc đầy đủ, không chỉ popleft
            if dq and min(t for t, _, _ in dq) < now - H24:
                self.data[sym] = deque(x for x in dq if x[0] >= now - H24)
            if not self.data[sym]:
                del self.data[sym]
                self.last_alert.pop(sym, None)

    @staticmethod
    def _mean(items: list[tuple[float, float, float]]) -> Window:
        if not items:
            return Window(None, 0)
        w = sum(i[2] for i in items)
        return Window(sum(i[1] * i[2] for i in items) / w, len(items))

    def windows(self, symbol: str, now: float) -> tuple[Window, Window]:
        dq = self.data.get(symbol, ())
        w1 = self._mean([x for x in dq if now - H1 <= x[0] <= now + 60])
        w24 = self._mean([x for x in dq if now - H24 <= x[0] <= now + 60])
        return w1, w24

    def check_reversal(self, symbol: str, now: float, newest_ts: float) -> Reversal | None:
        """Đảo chiều: trung bình 1h gần nhất ngược dấu với nền (24h trừ 1h), chênh >= min_delta, đủ mẫu, tin còn mới."""
        if now - newest_ts > self.fresh_s:
            return None                       # đang backfill tin cũ -> không báo
        dq = self.data.get(symbol)
        if not dq:
            return None
        cur = self._mean([x for x in dq if now - H1 <= x[0] <= now + 60])
        base = self._mean([x for x in dq if now - H24 <= x[0] < now - H1])
        if cur.n < self.min_n_1h or base.n < self.min_n_24h or cur.mean is None or base.mean is None:
            return None
        if abs(cur.mean) < self.min_abs or abs(base.mean) < self.min_abs or cur.mean * base.mean >= 0:
            return None
        if abs(cur.mean - base.mean) < self.min_delta:
            return None
        if now - self.last_alert.get(symbol, 0.0) < self.cooldown_s:
            return None
        self.last_alert[symbol] = now
        return Reversal(symbol, "up" if cur.mean > 0 else "down", cur.mean, base.mean, cur.n, base.n, now)

    def snapshot(self, now: float) -> dict[str, dict]:
        out = {}
        for sym in self.data:
            w1, w24 = self.windows(sym, now)
            out[sym] = {"1h": {"mean": w1.mean, "n": w1.n}, "24h": {"mean": w24.mean, "n": w24.n}}
        return out
