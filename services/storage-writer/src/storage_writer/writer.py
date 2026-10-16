from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from prometheus_client import Counter, Gauge, Histogram
from pydantic import ValidationError
from tscommon.bus import Bus
from tscommon.events import Event

from .db import DB
from .mapping import MAPPERS, InvalidBar, MappingError, map_event

log = logging.getLogger("storage_writer")

GROUP = "storage-writer"
DLQ_STREAM = "dlq"
STREAMS = list(MAPPERS.keys())

EVENTS = Counter("sw_events_total", "Events xử lý", ["stream", "result"])  # result: ok|dlq
ERRORS = Counter("sw_errors_total", "Lỗi", ["stream", "kind"])  # kind: mapping|decode|db|redis
LAG = Gauge("sw_stream_lag", "Số message chưa xử lý (lag) của group", ["stream"])
PENDING = Gauge("sw_stream_pending", "Số message đã giao nhưng chưa ack", ["stream"])
INVALID = Counter("sw_invalid_total", "Bản ghi vô lý bị đẩy vào dlq", ["stream", "reason"])
RECLAIMED = Counter("sw_reclaimed_total", "Message mồ côi được XAUTOCLAIM xử lý lại", ["stream"])
WRITE_SECONDS = Histogram("sw_write_seconds", "Thời gian ghi DB mỗi event", ["stream"])
STREAM_LEN = Gauge("sw_stream_len", "XLEN của stream", ["stream"])
LAG_AGE = Gauge("sw_stream_lag_age_seconds", "Tuổi của message cuối đã giao cho group khi còn lag (>= nửa BUS_RETENTION_S => nguy cơ bị trim chưa xử lý)", ["stream"])
DB_DOWN = Gauge("sw_db_down", "1 = DB không khả dụng: writer TẠM DỪNG, tin giữ nguyên trong PEL (không DLQ)")
BATCHES = Counter("sw_batches_total", "Lô ghi gộp 1 transaction", ["stream", "result"])  # result: ok|fallback


class DBUnavailable(Exception):
    """DB tạm thời không dùng được: KHÔNG ack, KHÔNG dead-letter; writer chờ DB hồi phục rồi xử lý lại từ PEL."""


def is_data_error(e: Exception) -> bool:
    """Lỗi do DỮ LIỆU (sqlstate lớp 22 data exception / 23 integrity) -> mới là poison hợp lệ để vào DLQ."""
    code = getattr(e, "sqlstate", None)
    return isinstance(code, str) and code[:2] in ("22", "23")


class StorageWriter:
    def __init__(self, redis: Any, db: DB, consumer: str = "sw-1", max_retries: int = 3,
                 retry_base_s: float = 0.2, block_ms: int = 2000, batch: int = 100,
                 reclaim_min_idle_ms: int = 60_000, reclaim_interval_s: float = 30.0, max_deliveries: int = 5):
        self.r = redis
        self.db = db
        self.consumer = consumer
        self.max_retries = max_retries
        self.retry_base_s = retry_base_s
        self.block_ms = block_ms
        self.batch = batch
        self.bus = Bus(redis)
        self.reclaim_min_idle_ms = reclaim_min_idle_ms
        self.reclaim_interval_s = reclaim_interval_s
        self.max_deliveries = max_deliveries
        self.db_wait_cap_s = 0.0  # test: chặn trần thời gian chờ
        self._stop = False

    async def setup(self) -> None:
        for s in STREAMS:
            try:
                await self.r.xgroup_create(s, GROUP, id="0", mkstream=True)
            except Exception as e:  # BUSYGROUP
                if "BUSYGROUP" not in str(e):
                    raise

    async def _dead_letter(self, stream: str, msg_id: str, fields: dict, reason: str) -> None:
        await self.r.xadd(DLQ_STREAM, {
            "stream": stream, "msg_id": msg_id, "reason": reason[:500],
            "e": fields.get("e", ""), "ts": str(time.time()),
        }, maxlen=50_000, approximate=True)

    async def handle(self, stream: str, msg_id: str, fields: dict, stmts: list | None = None) -> str:
        """Xử lý 1 message; luôn ack ở cuối (ok hoặc đã vào DLQ). Trả 'ok'|'dlq'.
        stmts: câu lệnh đã map sẵn (từ _process_batch) - KHÔNG map lại: map_quote có trạng thái throttle, map lần 2 sẽ nuốt mất quote."""
        try:
            if stmts is None:
                ev = Event.model_validate_json(fields["e"])
                stmts = map_event(stream, ev)
        except (KeyError, ValidationError, ValueError, MappingError) as e:
            kind = "mapping" if isinstance(e, MappingError) else "decode"
            ERRORS.labels(stream, kind).inc()
            if isinstance(e, InvalidBar):
                INVALID.labels(stream, e.code).inc()
            await self._dead_letter(stream, msg_id, fields, f"{kind}: {e}")
            await self.r.xack(stream, GROUP, msg_id)
            EVENTS.labels(stream, "dlq").inc()
            return "dlq"

        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with WRITE_SECONDS.labels(stream).time():
                    await self.db.execute_many(stmts)
                await self.r.xack(stream, GROUP, msg_id)
                EVENTS.labels(stream, "ok").inc()
                return "ok"
            except Exception as e:  # lỗi DB tạm thời -> retry backoff
                last = e
                ERRORS.labels(stream, "db").inc()
                log.warning("db error %s/%s attempt %d: %s", stream, msg_id, attempt + 1, e)
                if attempt + 1 < self.max_retries:
                    await asyncio.sleep(self.retry_base_s * (2 ** attempt))
        # Hết retry. Phân loại: lỗi dữ liệu -> DLQ; còn lại -> nếu DB vẫn sống thì message này là poison (DLQ, có replay);
        # nếu DB không trả lời -> GIỮ trong PEL và dừng writer (không biến sự kiện hợp lệ thành DLQ vì sự cố DB tạm thời).
        if last is not None and is_data_error(last):
            reason = f"db-data: {last}"
        elif await self._db_alive():
            reason = f"db-poison: {last}"
        else:
            DB_DOWN.set(1)
            raise DBUnavailable(str(last))
        await self._dead_letter(stream, msg_id, fields, reason)
        await self.r.xack(stream, GROUP, msg_id)
        EVENTS.labels(stream, "dlq").inc()
        return "dlq"

    async def _db_alive(self) -> bool:
        ping = getattr(self.db, "ping", None)
        if ping is None:
            return False  # không kiểm tra được -> coi là tạm thời (an toàn: không mất tin)
        try:
            await asyncio.wait_for(ping(), 5)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def wait_db(self, max_backoff_s: float = 30.0) -> None:
        """Chờ DB hồi phục (backoff 1,2,4..30s). Tin giữ nguyên trong PEL; sau đó _drain_pending xử lý lại."""
        delay = 1.0
        while not self._stop:
            await asyncio.sleep(min(delay, self.db_wait_cap_s) if self.db_wait_cap_s else delay)
            if getattr(self.db, "ping", None) is None or await self._db_alive():
                break
            delay = min(delay * 2, max_backoff_s)
        DB_DOWN.set(0)
        log.warning("thử lại message pending sau sự cố DB")

    async def _process_batch(self, stream: str, msgs: list) -> None:
        """Gộp cả lô vào MỘT transaction (nhanh hơn nhiều lần). Lỗi bất kỳ -> quay về xử lý từng message (retry/DLQ như cũ)."""
        by_id = dict(msgs)
        good: list = []
        rest: list = []
        for msg_id, fields in msgs:
            try:
                good.append((msg_id, map_event(stream, Event.model_validate_json(fields["e"]))))
            except Exception:  # noqa: BLE001 - để handle() phân loại + DLQ đúng lý do
                rest.append(msg_id)
        if len(good) > 1:
            stmts = [st for _, sts in good for st in sts]
            try:
                t0 = time.perf_counter()
                await self.db.execute_many(stmts)
                WRITE_SECONDS.labels(stream).observe((time.perf_counter() - t0) / len(good))
                await self.r.xack(stream, GROUP, *[m for m, _ in good])
                EVENTS.labels(stream, "ok").inc(len(good))
                BATCHES.labels(stream, "ok").inc()
                good = []
            except Exception as e:  # noqa: BLE001
                BATCHES.labels(stream, "fallback").inc()
                log.warning("lô %s (%d tin) lỗi, xử lý từng tin: %s", stream, len(good), e)
        for msg_id, sts in good:
            await self.handle(stream, msg_id, by_id[msg_id], sts)
        for msg_id in rest:
            await self.handle(stream, msg_id, by_id[msg_id])

    async def poll_once(self, pending: bool = False) -> int:
        """Đọc 1 lượt. pending=True: đọc lại message đã giao chưa ack (recover sau crash)."""
        start = "0" if pending else ">"
        res = await self.r.xreadgroup(
            GROUP, self.consumer, {s: start for s in STREAMS}, count=self.batch,
            block=None if pending else self.block_ms,
        )
        n = 0
        for stream, msgs in res or []:
            await self._process_batch(stream, list(msgs))
            n += len(msgs)
        return n

    async def reclaim_once(self) -> int:
        """XAUTOCLAIM message pending của consumer khác (đã chết/recreate) idle >= min_idle rồi xử lý + ack.

        Idempotent (upsert) nên xử lý lại an toàn. Message giao > max_deliveries -> dlq."""
        n = 0
        for stream in STREAMS:
            claimed = await self.bus.claim_stale(stream, GROUP, self.consumer, self.reclaim_min_idle_ms,
                                                 self.batch, self.max_deliveries, DLQ_STREAM)
            for msg_id, fields, _deliveries in claimed:
                await self.handle(stream, msg_id, fields)
                RECLAIMED.labels(stream).inc()
                n += 1
        return n

    async def update_lag(self) -> None:
        for s in STREAMS:
            try:
                for g in await self.r.xinfo_groups(s):
                    name = g.get("name")
                    if isinstance(name, bytes):
                        name = name.decode()
                    if name == GROUP:
                        lag = g.get("lag") or 0
                        LAG.labels(s).set(lag)
                        PENDING.labels(s).set(g.get("pending") or 0)
                        last = g.get("last-delivered-id") or "0-0"
                        last = last.decode() if isinstance(last, bytes) else str(last)
                        try:
                            age = max(0.0, time.time() - int(last.split("-")[0]) / 1000) if lag else 0.0
                        except ValueError:
                            age = 0.0
                        LAG_AGE.labels(s).set(age)
                        STREAM_LEN.labels(s).set(await self.r.xlen(s))
            except Exception:  # stream chưa tồn tại / server cũ không có lag
                pass

    async def run(self) -> None:
        await self.setup()
        log.info("storage-writer san sang: group=%s consumer=%s streams=%s", GROUP, self.consumer, ",".join(STREAMS))
        await self._drain_pending()
        try:
            while await self.reclaim_once():  # nhặt message mồ côi từ consumer cũ ngay khi khởi động
                pass
        except DBUnavailable:
            await self._drain_pending()
        except Exception as e:  # noqa: BLE001
            log.error("reclaim lúc khởi động lỗi: %s", e)
        last_lag = 0.0
        last_reclaim = time.monotonic()
        last_prune = time.monotonic()
        while not self._stop:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except DBUnavailable as e:
                ERRORS.labels("-", "db").inc()
                log.error("DB không khả dụng, tạm dừng ghi (tin giữ trong PEL): %s", e)
                await self._drain_pending()
            except Exception as e:
                ERRORS.labels("-", "redis").inc()
                log.error("poll error: %s", e)
                await asyncio.sleep(1)
            if time.monotonic() - last_reclaim > self.reclaim_interval_s:
                last_reclaim = time.monotonic()
                try:
                    await self.reclaim_once()
                    if time.monotonic() - last_prune > 3600:  # dọn consumer rác (idle >1h, không pending)
                        last_prune = time.monotonic()
                        for st in STREAMS:
                            await self.bus.prune_idle_consumers(st, GROUP)
                except asyncio.CancelledError:
                    raise
                except DBUnavailable:
                    await self._drain_pending()
                except Exception as e:  # noqa: BLE001
                    ERRORS.labels("-", "redis").inc()
                    log.error("reclaim lỗi: %s", e)
            if time.monotonic() - last_lag > 5:
                await self.update_lag()
                last_lag = time.monotonic()

    async def _drain_pending(self) -> None:
        """Đọc lại PEL của chính consumer này cho tới khi hết; nếu DB đang chết thì chờ hồi phục rồi thử lại (không mất tin)."""
        while not self._stop:
            try:
                while await self.poll_once(pending=True):
                    pass
                DB_DOWN.set(0)
                return
            except DBUnavailable:
                await self.wait_db()

    def stop(self) -> None:
        self._stop = True
