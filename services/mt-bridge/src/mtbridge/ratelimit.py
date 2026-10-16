"""Gioi han toc do (token bucket) trong RAM, khoa theo tai khoan/IP. Bo nho bi chan: tu don khoa nguoi hoa khi vuot max_keys."""
from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    def __init__(self, rate_per_s: float, burst: float, *, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000):
        self.rate, self.burst, self.clock, self.max_keys = float(rate_per_s), float(burst), clock, max_keys
        self._b: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._last_gc = 0.0

    def allow(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """(duoc phep?, retry_after_s)."""
        if self.rate <= 0:
            return True, 0.0
        now = self.clock()
        if len(self._b) > self.max_keys or now - self._last_gc > 60:
            self._gc(now)
        tokens, last = self._b.get(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens >= cost:
            self._b[key] = (tokens - cost, now)
            return True, 0.0
        self._b[key] = (tokens, now)
        return False, (cost - tokens) / self.rate

    def has(self, key: str, cost: float = 1.0) -> bool:
        """Chi doc (khong tru): con du token khong?"""
        if self.rate <= 0:
            return True
        now = self.clock()
        tokens, last = self._b.get(key, (self.burst, now))
        return min(self.burst, tokens + (now - last) * self.rate) >= cost

    def _gc(self, now: float) -> None:
        self._last_gc = now
        full_after = self.burst / self.rate if self.rate > 0 else 0
        self._b = {k: v for k, v in self._b.items() if now - v[1] < full_after}
