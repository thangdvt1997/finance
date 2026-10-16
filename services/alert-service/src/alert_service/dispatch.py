"""Gửi thông báo đồng thời có giới hạn: hàng đợi ưu tiên (crit > warn > info), timeout ngắn theo kênh,
circuit breaker cho kênh chậm/lỗi (kênh `log` luôn chạy), metric độ dài hàng đợi/độ trễ."""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from prometheus_client import Counter, Gauge, Histogram
from tscommon.sources import scrub_sources

log = logging.getLogger("alert.dispatch")

PRIORITY = {"crit": 0, "warn": 1, "info": 2}
ALWAYS_ON = "log"  # kênh không bao giờ bị breaker/timeout chặn

QUEUE_LEN = Gauge("alert_queue_length", "Số thông báo đang chờ gửi (chưa có worker)")
INFLIGHT = Gauge("alert_sending_inflight", "Số thông báo đang được gửi")
QUEUE_WAIT = Histogram("alert_queue_wait_seconds", "Thời gian chờ trong hàng đợi trước khi gửi", ["level"],
                       buckets=(0.01, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300))
SEND_SECONDS = Histogram("alert_send_seconds", "Thời gian gửi tới một kênh", ["channel"],
                         buckets=(0.01, 0.1, 0.5, 1, 2, 4, 6, 8, 12, 20))
BREAKER_OPEN = Gauge("alert_breaker_open", "1 nếu circuit breaker của kênh đang mở", ["channel"])
SEND_RESULT = Counter("alert_send_total", "Kết quả gửi theo kênh", ["channel", "result"])  # ok|fail|timeout|skipped


class CircuitBreaker:
    """closed -> (N lỗi liên tiếp) -> open [cooldown, nhân đôi tới max] -> half-open (1 lần thử) -> closed/open."""

    def __init__(self, threshold: int = 5, cooldown_s: float = 60.0, max_cooldown_s: float = 600.0,
                 clock: Callable[[], float] = time.monotonic):
        self.threshold, self.base_cooldown, self.max_cooldown, self.clock = threshold, cooldown_s, max_cooldown_s, clock
        self.cooldown = cooldown_s
        self.failures = 0
        self.state = "closed"
        self.open_until = 0.0
        self._probing = False

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open" and self.clock() >= self.open_until:
            self.state, self._probing = "half_open", False
        if self.state == "half_open" and not self._probing:
            self._probing = True  # chỉ cho 1 request thử
            return True
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self.failures, self.state, self._probing, self.cooldown = 0, "closed", False, self.base_cooldown
            return
        self.failures += 1
        if self.state == "half_open":
            self.cooldown = min(self.cooldown * 2, self.max_cooldown)
        if self.state == "half_open" or self.failures >= self.threshold:
            self.state, self._probing = "open", False
            self.open_until = self.clock() + self.cooldown


@dataclass(order=True)
class _Job:
    prio: int
    seq: int
    level: str = field(compare=False)
    text: str = field(compare=False)
    names: list = field(compare=False)
    fut: asyncio.Future = field(compare=False)
    enq: float = field(compare=False, default=0.0)


class Dispatcher:
    def __init__(self, channels: dict[str, Any], concurrency: int = 4, timeout_s: float = 8.0,
                 breaker_threshold: int = 5, breaker_cooldown_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self.channels = channels
        self.concurrency = max(1, concurrency)
        self.timeout_s = timeout_s
        self.clock = clock
        self._br_args = (breaker_threshold, breaker_cooldown_s)
        self.breakers: dict[str, CircuitBreaker] = {}
        self._q: asyncio.PriorityQueue[_Job] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._workers: list[asyncio.Task] = []
        self._active = 0
        self.avg_latency_s: float | None = None  # EWMA thời gian gửi 1 thông báo (không tính chờ hàng đợi)

    # ---- trạng thái ----
    def backlog(self) -> int:
        """Số thông báo chưa gửi xong (đang chờ + đang gửi)."""
        return self._q.qsize() + self._active

    def capacity_per_min(self) -> float:
        """Thông lượng tối đa ước lượng theo độ trễ thực đo được (inf nếu chưa có số liệu)."""
        if not self.avg_latency_s or self.avg_latency_s <= 0:
            return float("inf")
        return self.concurrency * 60.0 / self.avg_latency_s

    def snapshot(self) -> dict:
        cap = self.capacity_per_min()
        return {"queued": self._q.qsize(), "sending": self._active,
                "avg_latency_s": round(self.avg_latency_s, 3) if self.avg_latency_s else None,
                "capacity_per_min": None if cap == float("inf") else round(cap, 1),
                "breakers": {n: b.state for n, b in self.breakers.items()}}

    # ---- gửi ----
    def _ensure_workers(self) -> None:
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]

    async def send(self, level: str, text: str, names: list[str]) -> bool:
        """Xếp hàng theo ưu tiên và chờ kết quả (True nếu có ít nhất 1 kênh gửi được)."""
        self._ensure_workers()
        text = scrub_sources(text)  # diem phat cuoi: khong kenh nao (ntfy/Apprise/Telegram) nhan ten nguon
        fut = asyncio.get_running_loop().create_future()
        job = _Job(PRIORITY.get(level, 2), next(self._seq), level, text, list(names), fut, self.clock())
        await self._q.put(job)
        QUEUE_LEN.set(self._q.qsize())
        return await fut

    async def _worker(self) -> None:
        while True:
            job = await self._q.get()
            QUEUE_LEN.set(self._q.qsize())
            if job.fut.done():  # người gọi đã huỷ
                continue
            self._active += 1
            INFLIGHT.set(self._active)
            QUEUE_WAIT.labels(job.level).observe(max(0.0, self.clock() - job.enq))
            t0 = self.clock()
            try:
                ok = await self._run(job)
                dt = self.clock() - t0
                self.avg_latency_s = dt if self.avg_latency_s is None else 0.8 * self.avg_latency_s + 0.2 * dt
                if not job.fut.done():
                    job.fut.set_result(ok)
            except Exception as e:  # noqa: BLE001
                log.exception("dispatch lỗi")
                if not job.fut.done():
                    job.fut.set_exception(e)
            finally:
                self._active -= 1
                INFLIGHT.set(self._active)

    async def _send_one(self, name: str, ch: Any, text: str) -> bool:
        br = None
        if name != ALWAYS_ON:  # tạo breaker lười (kênh có thể được thêm sau khi dựng engine)
            br = self.breakers.setdefault(name, CircuitBreaker(*self._br_args, clock=self.clock))
        if br is not None and not br.allow():
            SEND_RESULT.labels(name, "skipped").inc()
            return False
        t0 = time.perf_counter()
        try:
            if name == ALWAYS_ON:
                ok = bool(await ch.send(text))
            else:
                ok = bool(await asyncio.wait_for(ch.send(text), self.timeout_s))
            result = "ok" if ok else "fail"
        except asyncio.TimeoutError:
            ok, result = False, "timeout"
            log.warning("kênh %s quá %.1fs -> timeout", name, self.timeout_s)
        except Exception:  # noqa: BLE001
            ok, result = False, "fail"
            log.exception("channel %s lỗi", name)
        SEND_SECONDS.labels(name).observe(time.perf_counter() - t0)
        SEND_RESULT.labels(name, result).inc()
        if br is not None:
            br.record(ok)
            BREAKER_OPEN.labels(name).set(0 if br.state == "closed" else 1)
        return ok

    async def _run(self, job: _Job) -> bool:
        pairs = [(n, self.channels[n]) for n in job.names if n in self.channels]
        if not pairs and ALWAYS_ON in self.channels:
            pairs = [(ALWAYS_ON, self.channels[ALWAYS_ON])]
        results = await asyncio.gather(*(self._send_one(n, c, job.text) for n, c in pairs))
        ok_any = any(results)
        if not ok_any and ALWAYS_ON in self.channels and ALWAYS_ON not in {n for n, _ in pairs}:
            # mọi kênh ngoài lỗi/bị breaker chặn -> vẫn ghi log để không mất dấu (kết quả vẫn là thất bại)
            await self._send_one(ALWAYS_ON, self.channels[ALWAYS_ON], job.text)
        return ok_any

    async def aclose(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
