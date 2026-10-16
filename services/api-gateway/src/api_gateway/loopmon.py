"""Giám sát vòng sự kiện asyncio của gateway (R3-11).

- `gateway_event_loop_lag_seconds` (histogram): độ trễ của một nhịp `asyncio.sleep(interval)` so với dự kiến = thời gian loop bị chặn.
- Watchdog (thread nền) thấy nhịp trễ > LOOPMON_STALL_S -> chụp stack của thread chạy loop và log WARNING MỘT lần cho mỗi lần đứng
  (giới hạn tần suất) => chỉ ra đúng đoạn mã đồng bộ đang chặn (rt hub, cache, route...).
Tắt: LOOPMON_ENABLED=0.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import threading
import time
import traceback

from prometheus_client import Counter, Histogram

log = logging.getLogger("gateway.loopmon")

M_LAG = Histogram("gateway_event_loop_lag_seconds", "Độ trễ nhịp vòng sự kiện asyncio (thời gian loop bị chặn)",
                  buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
M_STALLS = Counter("gateway_event_loop_stalls_total", "Số lần vòng sự kiện bị chặn quá ngưỡng LOOPMON_STALL_S")


def _f(name: str, d: float) -> float:
    try:
        return float(os.getenv(name, d))
    except ValueError:
        return d


class LoopMonitor:
    def __init__(self, interval: float | None = None, stall_s: float | None = None, max_dumps_per_min: int = 6):
        self.interval = interval if interval is not None else _f("LOOPMON_INTERVAL_S", 0.1)
        self.stall_s = stall_s if stall_s is not None else _f("LOOPMON_STALL_S", 0.3)
        self.max_dumps = max_dumps_per_min
        self.beat = time.monotonic()
        self._task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._loop_tid: int | None = None
        self._dumps: list[float] = []

    async def _tick(self) -> None:
        while True:
            t0 = time.monotonic()
            self.beat = t0
            await asyncio.sleep(self.interval)
            M_LAG.observe(max(0.0, time.monotonic() - t0 - self.interval))

    def _watch(self) -> None:
        stalled = False
        while not self._stop.wait(0.05):
            late = time.monotonic() - self.beat - self.interval
            if late <= self.stall_s:
                stalled = False
                continue
            if stalled:
                continue
            stalled = True
            M_STALLS.inc()
            now = time.monotonic()
            self._dumps = [t for t in self._dumps if now - t < 60]
            if len(self._dumps) >= self.max_dumps:
                continue
            self._dumps.append(now)
            fr = sys._current_frames().get(self._loop_tid) if self._loop_tid else None
            stack = "".join(traceback.format_stack(fr, limit=25)) if fr is not None else "(không lấy được stack)"
            log.warning("event loop bị chặn >%.2fs — stack thread loop:\n%s", late, stack)

    def start(self) -> None:
        self._loop_tid = threading.get_ident()
        self.beat = time.monotonic()
        self._task = asyncio.get_running_loop().create_task(self._tick(), name="loopmon")
        self._thread = threading.Thread(target=self._watch, name="loopmon-watchdog", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


def enabled() -> bool:
    return os.getenv("LOOPMON_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
