from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol

from prometheus_client import Counter
from tscommon.sources import scrub_sources, scrub_tags

from .config import LEVELS, AlertSettings
from .dispatch import Dispatcher
from .templates import format_alert, format_digest

log = logging.getLogger("alert.engine")

ALERTS_IN = Counter("alerts_in_total", "Cảnh báo nhận vào", ["level"])
ALERTS_DIVERTED = Counter("alerts_diverted_total", "Tin non-crit gom vào digest vì backlog gửi lớn")
ALERTS_OUT = Counter("alerts_out_total", "Kết quả xử lý cảnh báo", ["channel", "result"])

RECENT_KEY = "alerts:recent"
BUFFER_KEY = "alerts:digest_buffer"
STATS_KEY = "alerts:stats"


class Channel(Protocol):
    name: str

    async def send(self, text: str) -> bool: ...


class LogChannel:
    name = "log"

    async def send(self, text: str) -> bool:
        log.warning("ALERT\n%s", text)
        return True


class TelegramChannel:
    name = "telegram"

    def __init__(self, client):
        self.client = client

    async def send(self, text: str) -> bool:
        return await self.client.send(text)


class AppriseChannel:
    """Kênh đa dịch vụ qua thư viện Apprise (Telegram/ntfy/Slack/Discord/email... theo URL cấu hình).

    `notifier` có thể tiêm vào (test); mặc định tạo apprise.Apprise() từ danh sách URL. URL sai bị bỏ qua + log
    (không in URL vì có thể chứa token)."""
    name = "apprise"

    def __init__(self, urls: list[str], notifier=None):
        if notifier is None:
            import apprise  # import trễ: service vẫn chạy nếu chưa cài apprise và không dùng kênh này
            notifier = apprise.Apprise()
            for u in urls:
                if not notifier.add(u):
                    log.error("APPRISE_URLS: một URL không hợp lệ đã bị bỏ qua")
        self.notifier = notifier

    @property
    def configured(self) -> bool:
        return len(self.notifier) > 0

    async def send(self, text: str) -> bool:
        if not self.configured:
            return False
        return bool(await self.notifier.async_notify(body=scrub_sources(text)[:4000], title="trading-system"))


class Router:
    """Chọn kênh theo luật đầu tiên khớp: min_level và tags_any (tuỳ chọn)."""

    def __init__(self, routes: list[dict]):
        self.routes = routes

    # Cảnh báo do người dùng đặt (alert-rules) chọn kênh bằng tag `ch:<tên>`; ntfy đi qua kênh apprise (APPRISE_URLS=ntfy://...).
    USER_CHANNELS = {"ntfy": "apprise", "apprise": "apprise", "log": "log", "telegram": "telegram"}

    def resolve(self, level: str, tags: list[str]) -> list[str]:
        chosen = [self.USER_CHANNELS[t[3:]] for t in tags if t.startswith("ch:") and t[3:] in self.USER_CHANNELS]
        if chosen:
            return list(dict.fromkeys(chosen))
        lv = LEVELS.get(level, 0)
        for r in self.routes:
            if lv < LEVELS.get(r.get("min_level", "info"), 0):
                continue
            want = r.get("tags_any")
            if want and not set(want) & set(tags):
                continue
            return list(r.get("channels", ["log"]))
        return ["log"]


DELIVERY_STREAM = "alerts.delivery"


def scrub_payload(payload: dict) -> dict:
    """Bo ten nguon du lieu khoi title/body/tags cua alert truoc khi gui/luu (docs/UI_NO_SOURCES.md)."""
    out = dict(payload)
    for k in ("title", "body"):
        if isinstance(out.get(k), str):
            out[k] = scrub_sources(out[k])
    if isinstance(out.get("tags"), list):
        out["tags"] = scrub_tags(out["tags"])
    return out


class AlertEngine:
    def __init__(self, redis, settings: AlertSettings, channels: dict[str, Channel], router: Router,
                 clock: Callable[[], float] = time.time,
                 on_delivery: Callable[[dict], Awaitable[None]] | None = None,
                 dispatcher: Dispatcher | None = None):
        self.r = redis
        # on_delivery: phát sự kiện alert_delivered (storage-writer cập nhật alerts.delivered). Lỗi không chặn gửi.
        self.on_delivery = on_delivery
        self.s = settings
        self.channels = channels
        self.router = router
        self.clock = clock
        self.dispatcher = dispatcher or Dispatcher(
            channels, concurrency=settings.send_concurrency, timeout_s=settings.send_timeout_s,
            breaker_threshold=settings.breaker_threshold, breaker_cooldown_s=settings.breaker_cooldown_s)

    # ---- các bước ----
    async def _is_duplicate(self, key: str | None) -> bool:
        if not key or self.s.dedupe_window_s <= 0:
            return False
        # cảnh báo chất lượng dữ liệu (gap/outlier... lặp theo mã) chỉ báo 1 lần/6h thay vì mỗi cửa sổ dedupe
        win = max(self.s.dedupe_window_s, 21600) if key.startswith("mc:quality:") else self.s.dedupe_window_s
        ok = await self.r.set(f"alerts:dedupe:{key}", "1", nx=True, ex=win)
        return not ok

    async def _rate_allowed(self, level: str) -> bool:
        if level == "crit":  # crit không bị giới hạn tốc độ
            return True
        bucket = int(self.clock() // 60)
        k = f"alerts:rl:{bucket}"
        n = await self.r.incr(k)
        if n == 1:
            await self.r.expire(k, 120)
        return n <= self.effective_rate_limit()

    def effective_rate_limit(self) -> int:
        """Giới hạn tin non-crit/phút = min(cấu hình, 80% thông lượng thật đo được của kênh gửi).
        Kênh chậm -> tự hạ để không dồn backlog (phần dư vào digest)."""
        cap = self.dispatcher.capacity_per_min()
        if cap == float("inf"):
            return self.s.rate_limit_per_min
        return max(1, min(self.s.rate_limit_per_min, int(cap * 0.8)))

    async def _remember(self, payload: dict, outcome: str) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "outcome": outcome,
               "level": payload.get("level"), "title": payload.get("title"), "tags": payload.get("tags", [])}
        await self.r.lpush(RECENT_KEY, json.dumps(rec, ensure_ascii=False))
        await self.r.ltrim(RECENT_KEY, 0, 199)
        await self.r.hincrby(STATS_KEY, outcome, 1)

    async def _deliver(self, text: str, level: str, tags: list[str]) -> bool:
        """Đưa vào hàng đợi ưu tiên của dispatcher (crit trước), gửi song song có timeout + circuit breaker."""
        return await self.dispatcher.send(level, text, self.router.resolve(level, tags))

    async def _buffer(self, payload: dict, ts: datetime | None, event_id: str | None) -> None:
        buffered = {**payload, "_event_id": event_id, "_ts": (ts.isoformat() if ts else None)}
        await self.r.rpush(BUFFER_KEY, json.dumps(buffered, ensure_ascii=False))
        await self.r.ltrim(BUFFER_KEY, -1000, -1)
        await self._remember(payload, "grouped")

    async def _notify_delivery(self, event_id: str | None, payload: dict, ts: datetime | None,
                               delivered: bool, outcome: str) -> None:
        if not (self.on_delivery and event_id):
            return
        body = {"alert_event_id": event_id, "delivered": delivered, "outcome": outcome,
                "ts": (ts or datetime.now(timezone.utc)).isoformat(),
                "level": payload.get("level", "info"), "title": payload.get("title") or "(no title)",
                "body": payload.get("body"), "tags": list(payload.get("tags") or []),
                "dedupe_key": payload.get("dedupe_key")}
        try:
            await self.on_delivery(body)
        except Exception:  # noqa: BLE001
            log.exception("phát alert_delivered lỗi event=%s", event_id)

    async def handle(self, payload: dict, ts: datetime | None = None, event_id: str | None = None) -> str:
        """Trả về outcome: sent | failed | deduped | grouped. event_id (nếu có) -> phát alert_delivered."""
        level = payload.get("level", "info")
        if level not in LEVELS:
            level = "info"
            payload = {**payload, "level": level}
        ALERTS_IN.labels(level).inc()
        payload = scrub_payload(payload)  # ten nguon KHONG duoc xuat hien o bat ky noi dung nao nguoi dung thay
        if await self._is_duplicate(payload.get("dedupe_key")):
            await self._remember(payload, "deduped")
            return "deduped"
        if level != "crit" and self.dispatcher.backlog() >= self.s.backlog_digest_threshold:
            ALERTS_DIVERTED.inc()  # backlog gửi lớn: gom non-crit vào digest, nhường chỗ cho crit
            await self._buffer(payload, ts, event_id)
            return "grouped"
        if not await self._rate_allowed(level):
            await self._buffer(payload, ts, event_id)
            return "grouped"
        ok = await self._deliver(format_alert(payload, ts), level, payload.get("tags") or [])
        outcome = "sent" if ok else "failed"
        await self._remember(payload, outcome)
        await self._notify_delivery(event_id, payload, ts, ok, outcome)
        return outcome

    async def flush_digest(self) -> int:
        """Gửi 1 tin gom nhóm cho các cảnh báo bị giới hạn tốc độ. Trả về số cảnh báo đã gom."""
        raw = await self.r.lrange(BUFFER_KEY, 0, -1)
        if not raw:
            return 0
        items = [json.loads(x) for x in raw]
        level = "warn" if any(i.get("level") == "warn" for i in items) else "info"
        ok = await self._deliver(format_digest(items), level, ["digest"])
        if ok:
            await self.r.ltrim(BUFFER_KEY, len(raw), -1)
            for i in items:
                t = i.get("_ts")
                await self._notify_delivery(i.get("_event_id"), i, datetime.fromisoformat(t) if t else None,
                                            True, "digest")
        return len(items) if ok else 0

    async def aclose(self) -> None:
        await self.dispatcher.aclose()

    async def recent(self, n: int = 10) -> list[dict]:
        raw = await self.r.lrange(RECENT_KEY, 0, max(0, n - 1))
        return [json.loads(x) for x in raw]

    async def stats(self) -> dict[str, int]:
        raw = await self.r.hgetall(STATS_KEY)
        return {k: int(v) for k, v in raw.items()}


async def consume_loop(bus, engine: AlertEngine, group: str, consumer: str, stream: str = "alerts.out",
                       on_event: Callable[[], Awaitable[None]] | None = None, max_inflight: int | None = None,
                       inflight: set | None = None) -> None:
    """Đọc alerts.out và xử lý ĐỒNG THỜI (tối đa max_inflight) để hàng đợi ưu tiên của dispatcher có tác dụng.
    Ack sau khi xử lý xong; lỗi -> không ack (giao lại / XAUTOCLAIM). `inflight` = tập msg_id đang xử lý
    (để reclaim không nhặt trùng tin của chính tiến trình này)."""
    ids = inflight if inflight is not None else set()
    sem = asyncio.Semaphore(max_inflight or engine.s.max_inflight)
    tasks: set[asyncio.Task] = set()

    async def work(msg_id: str, ev) -> None:
        try:
            try:
                await engine.handle(ev.payload, ev.ts, event_id=ev.id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("xử lý alert lỗi id=%s", msg_id)
                return  # không ack -> sẽ được giao lại
            await bus.ack(stream, group, msg_id)
            if on_event:
                await on_event()
        finally:
            ids.discard(msg_id)
            sem.release()

    try:
        async for msg_id, ev in bus.consume(stream, group, consumer, block_ms=2000):
            await sem.acquire()
            ids.add(msg_id)
            t = asyncio.create_task(work(msg_id, ev))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
    finally:
        for t in list(tasks):
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
