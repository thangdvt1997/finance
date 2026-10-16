from __future__ import annotations

import logging
import os
import time
from typing import AsyncIterator

import redis.asyncio as aioredis

from .events import Event

STREAMS = {
    "quotes": "md.quotes",
    "bars": "md.bars",
    "news": "news.items",
    "news_enriched": "news.enriched",
    "calendar": "calendar.events",
    "expert_signals": "expert.signals",
    "expert_positions": "expert.positions",
    "expert_profiles": "expert.profiles",
    "account": "account.snapshots",
    "deals": "account.deals",
    "alerts": "alerts.out",
    "briefing": "briefing.items",
    "patterns": "pattern.signals",
}


log = logging.getLogger("tscommon.bus")

DLQ_STREAM = "dlq"


class Bus:
    """Redis Streams wrapper. Một field `e` chứa JSON của Event.

    Trim: MẶC ĐỊNH theo THỜI GIAN (XADD MINID ~ now - retention_s, BUS_RETENTION_S, mặc định 24h) thay vì độ dài, để một đợt
    backfill/burst không đẩy tin CHƯA tiêu thụ ra khỏi stream (R-3). `maxlen` chỉ còn là chế độ cũ khi truyền tường minh."""

    def __init__(self, client: aioredis.Redis, maxlen: int | None = None, retention_s: float | None = None):
        self.r = client
        self.maxlen = maxlen
        self.retention_s = float(os.getenv("BUS_RETENTION_S", "86400")) if retention_s is None else retention_s
        # Giữ riêng theo stream (vd md.quotes ~290 B/tin x 100+ tin/s: 24h = ~2,9 GiB, sát maxmemory noeviction).
        # Mặc định md.quotes 4h (consumer lag ~0, lịch sử nằm ở DB); ghi đè bằng BUS_RETENTION_OVERRIDES="stream=giây,..."
        self.retention_by_stream: dict[str, float] = {"md.quotes": 4 * 3600.0}
        for part in os.getenv("BUS_RETENTION_OVERRIDES", "").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    self.retention_by_stream[k.strip()] = float(v)
                except ValueError:
                    pass

    @classmethod
    def from_url(cls, url: str) -> "Bus":
        return cls(aioredis.from_url(url, decode_responses=True))

    async def publish(self, stream: str, event: Event) -> str:
        if self.maxlen:
            return await self.r.xadd(stream, {"e": event.model_dump_json()}, maxlen=self.maxlen, approximate=True)
        keep = self.retention_by_stream.get(stream, self.retention_s)
        minid = f"{int((time.time() - keep) * 1000)}-0"
        return await self.r.xadd(stream, {"e": event.model_dump_json()}, minid=minid, approximate=True)

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self.r.xgroup_create(stream, group, id="0", mkstream=True)
        except aioredis.ResponseError as e:  # BUSYGROUP
            if "BUSYGROUP" not in str(e):
                raise

    async def consume(
        self, stream: str, group: str, consumer: str, block_ms: int | None = 5000, count: int = 100
    ) -> AsyncIterator[tuple[str, Event]]:
        """Yield (msg_id, Event). Caller phải gọi ack() sau khi xử lý xong (at-least-once).

        block_ms > 0: block chờ tin mới, generator chạy vô hạn (dùng trong service).
        block_ms = 0 hoặc None: KHÔNG block — đọc hết tin hiện có rồi kết thúc (dùng trong test với fakeredis,
        không bị treo). Lưu ý: Redis hiểu BLOCK 0 là chờ vô hạn nên ở đây 0 được dịch thành "không block".
        """
        await self.ensure_group(stream, group)
        blocking = bool(block_ms)
        while True:
            res = await self.r.xreadgroup(group, consumer, {stream: ">"}, count=count,
                                          block=block_ms if blocking else None)
            n = 0
            for _stream, msgs in res or []:
                for msg_id, fields in msgs:
                    n += 1
                    try:
                        ev = Event.model_validate_json(fields["e"])
                    except Exception as exc:  # poison: dlq + ack, không làm sập generator/mất lô còn lại
                        log.error("message %s/%s không parse được -> dlq", stream, msg_id)
                        await self.dead_letter(stream, group, msg_id, fields, f"invalid_event: {type(exc).__name__}")
                        continue
                    yield msg_id, ev
            if not blocking and n == 0:
                return

    async def consume_once(
        self, stream: str, group: str, consumer: str, count: int = 100
    ) -> list[tuple[str, Event]]:
        """Một lượt đọc không block: trả list (msg_id, Event) (rỗng nếu không có tin mới)."""
        await self.ensure_group(stream, group)
        res = await self.r.xreadgroup(group, consumer, {stream: ">"}, count=count)
        return [(mid, Event.model_validate_json(f["e"])) for _s, msgs in res or [] for mid, f in msgs]

    async def ack(self, stream: str, group: str, msg_id: str) -> None:
        await self.r.xack(stream, group, msg_id)

    # ---- phục hồi message mồ côi (consumer chết/recreate) ----
    async def pending_own(self, stream: str, group: str, consumer: str, count: int = 100) -> list[tuple[str, dict]]:
        """Đọc lại message ĐÃ giao cho chính consumer này nhưng chưa ack (dùng khi khởi động). Trả (msg_id, fields)."""
        await self.ensure_group(stream, group)
        out: list[tuple[str, dict]] = []
        last = "0"
        while True:
            res = await self.r.xreadgroup(group, consumer, {stream: last}, count=count)
            batch = [(mid, f) for _s, msgs in res or [] for mid, f in msgs]
            if not batch:
                return out
            out.extend(batch)
            last = batch[-1][0]

    async def _deliveries(self, stream: str, group: str, msg_id: str) -> int:
        rows = await self.r.xpending_range(stream, group, min=msg_id, max=msg_id, count=1)
        if not rows:
            return 1
        row = rows[0]
        return int(row.get("times_delivered", 1) if isinstance(row, dict) else row[3])

    async def dead_letter(self, stream: str, group: str, msg_id: str, fields: dict, reason: str,
                          dlq_stream: str = DLQ_STREAM) -> None:
        """Đẩy message vào dlq (cùng định dạng storage-writer) rồi ack để khỏi kẹt PEL."""
        await self.r.xadd(dlq_stream, {"stream": stream, "msg_id": msg_id, "reason": reason[:500],
                                       "e": fields.get("e", ""), "ts": str(time.time())},
                          maxlen=50_000, approximate=True)
        await self.r.xack(stream, group, msg_id)

    async def claim_stale(
        self, stream: str, group: str, consumer: str, min_idle_ms: int = 60_000, count: int = 100,
        max_deliveries: int = 5, dlq_stream: str = DLQ_STREAM,
    ) -> list[tuple[str, dict, int]]:
        """XAUTOCLAIM: nhận về `consumer` các message pending của consumer KHÁC (đã chết) idle >= min_idle_ms.

        Trả [(msg_id, fields, số_lần_giao)]. Message đã giao > max_deliveries lần (poison/kẹt) -> dlq + ack,
        không trả về. Message đã bị trim khỏi stream -> Redis tự gỡ khỏi PEL. Caller xử lý rồi ack().
        """
        await self.ensure_group(stream, group)
        out: list[tuple[str, dict, int]] = []
        cursor = "0-0"
        while len(out) < count:
            res = await self.r.xautoclaim(stream, group, consumer, min_idle_time=min_idle_ms,
                                          start_id=cursor, count=count)
            cursor, msgs = res[0], res[1]
            for msg_id, fields in msgs:
                if not fields:  # message đã bị xoá
                    await self.r.xack(stream, group, msg_id)
                    continue
                n = await self._deliveries(stream, group, msg_id)
                if n > max_deliveries:
                    log.error("message %s/%s giao %d lần > %d -> dlq", stream, msg_id, n, max_deliveries)
                    await self.dead_letter(stream, group, msg_id, fields, f"max_deliveries: {n}", dlq_stream)
                    continue
                out.append((msg_id, fields, n))
            if cursor in ("0-0", b"0-0", "0") or not msgs:
                break
        return out

    async def reclaim(
        self, stream: str, group: str, consumer: str, min_idle_ms: int = 60_000, count: int = 100,
        max_deliveries: int = 5, dlq_stream: str = DLQ_STREAM,
    ) -> list[tuple[str, Event, int]]:
        """Như claim_stale nhưng parse Event; message không parse được -> dlq + ack."""
        out: list[tuple[str, Event, int]] = []
        for msg_id, fields, n in await self.claim_stale(stream, group, consumer, min_idle_ms, count,
                                                        max_deliveries, dlq_stream):
            try:
                out.append((msg_id, Event.model_validate_json(fields["e"]), n))
            except Exception as e:  # noqa: BLE001
                await self.dead_letter(stream, group, msg_id, fields, f"decode: {e}", dlq_stream)
        return out

    async def prune_idle_consumers(self, stream: str, group: str, idle_ms: int = 3_600_000) -> int:
        """Xoá consumer rác (không còn pending, idle lâu) — nên gọi SAU reclaim. Trả số consumer đã xoá."""
        n = 0
        for c in await self.r.xinfo_consumers(stream, group):
            if int(c.get("pending", 0)) == 0 and int(c.get("idle", 0)) >= idle_ms:
                await self.r.xgroup_delconsumer(stream, group, c["name"])
                n += 1
        return n
