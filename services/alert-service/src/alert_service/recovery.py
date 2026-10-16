"""Nhặt lại message mồ côi (consumer chết/recreate) bằng XAUTOCLAIM (tscommon.Bus.reclaim)."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Container

log = logging.getLogger("alert.recovery")


async def recover_once(bus, stream: str, group: str, consumer: str,
                       handler: Callable[[str, object], Awaitable[None]], *, min_idle_ms: int = 60_000,
                       max_deliveries: int = 5, skip: Container[str] = (), include_own: bool = False,
                       prune_idle_ms: int = 3_600_000) -> int:
    """Xử lý lại message pending: (tuỳ chọn) của chính mình + của consumer khác idle >= min_idle_ms.
    handler(msg_id, event) thành công -> ack; lỗi -> để nguyên (lần sau thử lại, quá max_deliveries -> dlq)."""
    from tscommon import Event
    todo: list[tuple[str, object]] = []
    if include_own:
        for msg_id, fields in await bus.pending_own(stream, group, consumer):
            try:
                todo.append((msg_id, Event.model_validate_json(fields["e"])))
            except Exception as e:  # noqa: BLE001
                await bus.dead_letter(stream, group, msg_id, fields, f"decode: {e}")
    todo += [(m, ev) for m, ev, _n in await bus.reclaim(stream, group, consumer, min_idle_ms=min_idle_ms,
                                                       max_deliveries=max_deliveries)]
    n = 0
    for msg_id, ev in todo:
        if msg_id in skip:  # đang được xử lý bởi chính tiến trình này
            continue
        try:
            await handler(msg_id, ev)
        except Exception:  # noqa: BLE001
            log.exception("recover %s/%s lỗi", stream, msg_id)
            continue
        await bus.ack(stream, group, msg_id)
        n += 1
    if n:
        log.warning("recover: đã xử lý lại %d message mồ côi của %s/%s", n, stream, group)
    try:
        await bus.prune_idle_consumers(stream, group, prune_idle_ms)
    except Exception:  # noqa: BLE001
        pass
    return n


async def recover_loop(bus, stream: str, group: str, consumer: str, handler, *, interval_s: float = 30.0,
                       min_idle_ms: int = 60_000, max_deliveries: int = 5, skip: Container[str] = ()) -> None:
    first = True
    while True:
        try:
            await recover_once(bus, stream, group, consumer, handler, min_idle_ms=min_idle_ms,
                               max_deliveries=max_deliveries, skip=skip, include_own=first)
            first = False
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("recover loop lỗi")
        await asyncio.sleep(interval_s)
