"""Bảo vệ đường giá: đo p95 trễ MT5->bridge từ /metrics của mt-bridge (delta giữa 2 lần cào). Module heal/backfill gọi ctx.guard.ok()."""
from __future__ import annotations

import logging
import re
import time

import httpx

log = logging.getLogger("data_keeper.guard")
_RX = re.compile(r'mtbridge_feed_latency_seconds_bucket\{class="fx",le="([^"]+)"\} (\S+)')


def p95_from(prev: dict, cur: dict) -> float | None:
    d = {k: cur[k] - prev.get(k, 0.0) for k in cur}
    if not d:
        return None
    ks = sorted(d)
    tot = d[ks[-1]]
    if tot < 50:
        return None
    tgt, pk, pv = 0.95 * tot, 0.0, 0.0
    for k in ks:
        if d[k] >= tgt:
            if k == float("inf"):
                return pk
            return pk + (k - pk) * (tgt - pv) / max(d[k] - pv, 1e-9)
        pk, pv = k, d[k]
    return None


class LatencyGuard:
    def __init__(self, url: str, p95_max: float):
        self.url, self.p95_max = url, p95_max
        self._prev: dict | None = None
        self.p95: float | None = None
        self.checked_at = 0.0

    async def refresh(self) -> float | None:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                t = (await c.get(self.url)).text
            cur = {float(m.group(1)): float(m.group(2)) for m in _RX.finditer(t)}
            if self._prev is not None and cur:
                self.p95 = p95_from(self._prev, cur)
            if cur:
                self._prev = cur
            self.checked_at = time.time()
        except Exception as e:  # noqa: BLE001
            log.warning("guard: không cào được bridge metrics: %s", e)
        return self.p95

    def ok(self) -> bool:
        """True nếu p95 chưa xấu (hoặc chưa đo được: coi là ổn nhưng module nên thận trọng)."""
        return self.p95 is None or self.p95 <= self.p95_max
