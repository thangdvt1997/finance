"""Vòng xử lý: news.items -> (hàng đợi giới hạn) -> lô -> suy luận trong thread -> news.enriched (+ alert đảo chiều).

- Hàng đợi có giới hạn => backpressure: reader dừng đọc khi processor chưa kịp (backfill hàng nghìn tin không nghẹt RAM).
- At-least-once: chỉ ack sau khi đã publish; idempotent theo url+model_version (khoá Redis SET NX, TTL dedupe_ttl).
- Khởi động: xử lý lại message pending của chính consumer; định kỳ XAUTOCLAIM message mồ côi (Bus.reclaim).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from tscommon.bus import STREAMS, Bus
from tscommon.events import Event, make_event

from . import metrics as M
from .aggregate import Reversal, SymbolAggregator
from .enrich import Enricher, valid_payload
from .settings import NlpSettings

log = logging.getLogger("nlp.worker")

IN_STREAM = STREAMS["news"]
OUT_STREAM = STREAMS["news_enriched"]
ALERT_STREAM = STREAMS["alerts"]
SERVICE = "nlp"


def _epoch(v) -> float | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class NlpWorker:
    def __init__(self, cfg: NlpSettings, bus: Bus, enricher_factory: Callable[[], Enricher], clock=time.time):
        self.cfg, self.bus, self.clock = cfg, bus, clock
        self._factory = enricher_factory
        self.enricher: Enricher | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=cfg.queue_max)
        self.agg = SymbolAggregator(cfg.alert_min_delta, cfg.alert_min_n_1h, cfg.alert_min_n_24h,
                                    cfg.alert_cooldown_s, cfg.alert_fresh_s)
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()
        self.processed = 0
        self.ready = False

    # ------------------------------------------------------------ vòng đời
    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self._boot(), name="nlp-boot")]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)

    async def _boot(self) -> None:
        try:
            self.enricher = await asyncio.to_thread(self._factory)
            self._publish_model_gauges()
            self.ready = True
            self._tasks += [asyncio.create_task(self._reader(), name="nlp-reader"),
                            asyncio.create_task(self._processor(), name="nlp-processor"),
                            asyncio.create_task(self._housekeeping(), name="nlp-house"),
                            asyncio.create_task(self._model_retry(), name="nlp-retry")]
        except Exception:  # noqa: BLE001
            log.exception("khởi động thất bại")
            M.ERRORS.labels("boot").inc()

    def _publish_model_gauges(self) -> None:
        M.MODEL_LOADED.clear()
        for lang, ver in self.enricher.engine.loaded.items():
            M.MODEL_LOADED.labels(lang, ver).set(1)

    async def _model_retry(self) -> None:
        """Nếu có model cấu hình mà chưa nạp được (mạng/volume) -> thử lại định kỳ, hoán đổi nóng."""
        wanted = {"en": self.cfg.model_en, "vi": self.cfg.model_vi}
        while not self._stop.is_set():
            await asyncio.sleep(self.cfg.model_retry_s)
            eng = self.enricher.engine
            missing = [lg for lg, n in wanted.items() if n not in ("lexicon", "none", "") and lg not in eng.loaded]
            if not missing:
                continue
            try:
                new = await asyncio.to_thread(self._factory)
                self.enricher = new
                self._publish_model_gauges()
                log.info("nạp lại model: %s", new.engine.loaded)
            except Exception:  # noqa: BLE001
                log.exception("nạp lại model thất bại")

    # ------------------------------------------------------------ đọc
    def _parse(self, fields: dict) -> Event | None:
        try:
            return Event.model_validate_json(fields["e"])
        except Exception:  # noqa: BLE001
            return None

    async def _enqueue(self, msg_id: str, fields: dict) -> None:
        ev = self._parse(fields)
        if ev is None or not valid_payload(ev.payload):
            M.SKIPPED.labels("invalid").inc()
            await self.bus.dead_letter(IN_STREAM, self.cfg.group, msg_id, fields, "nlp: payload không hợp lệ")
            return
        if (ev.payload.get("source") or "") in self.cfg.skip_sources:
            M.SKIPPED.labels("skip_source").inc()
            await self.bus.ack(IN_STREAM, self.cfg.group, msg_id)
            return
        await self.queue.put((msg_id, ev))
        M.QUEUE_DEPTH.set(self.queue.qsize())

    async def _reader(self) -> None:
        b, c = self.bus, self.cfg
        await b.ensure_group(IN_STREAM, c.group)
        for mid, f in await b.pending_own(IN_STREAM, c.group, c.consumer, count=c.batch):
            await self._enqueue(mid, f)
        last_reclaim = 0.0
        while not self._stop.is_set():
            try:
                if self.clock() - last_reclaim > 30:
                    last_reclaim = self.clock()
                    for mid, ev, _n in await b.reclaim(IN_STREAM, c.group, c.consumer, c.reclaim_idle_ms, count=c.batch):
                        await self._enqueue(mid, {"e": ev.model_dump_json()})
                res = await b.r.xreadgroup(c.group, c.consumer, {IN_STREAM: ">"}, count=c.batch,
                                           block=c.read_block_ms or None)
                for _s, msgs in res or []:
                    for mid, f in msgs:
                        await self._enqueue(mid, f)
                if not res:
                    await asyncio.sleep(0.05 if not c.read_block_ms else 0)   # read_block_ms=0: thăm dò (dùng trong test)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  (Redis tạm lỗi) -> thử lại
                log.exception("reader lỗi")
                M.ERRORS.labels("read").inc()
                await asyncio.sleep(2)

    # ------------------------------------------------------------ xử lý
    async def _drain_batch(self) -> list[tuple[str, Event]]:
        first = await self.queue.get()
        batch = [first]
        while len(batch) < self.cfg.batch:
            try:
                batch.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        M.QUEUE_DEPTH.set(self.queue.qsize())
        return batch

    def _dedupe_key(self, version: str, url: str) -> str:
        return f"nlp:done:{version}:{hashlib.sha1(url.encode()).hexdigest()}"

    async def process_batch(self, batch: list[tuple[str, Event]]) -> int:
        """Xử lý một lô đã lấy; trả số tin được phát. Tách riêng để test không cần chạy vòng lặp."""
        enr = self.enricher
        todo: list[tuple[str, Event]] = []
        in_batch: set[str] = set()
        for mid, ev in batch:
            key = self._dedupe_key(enr.version_for(ev.payload), ev.payload["url"])
            if key in in_batch or await self.bus.r.exists(key):
                M.SKIPPED.labels("duplicate").inc()
                await self.bus.ack(IN_STREAM, self.cfg.group, mid)
            else:
                in_batch.add(key)
                todo.append((mid, ev))
        if not todo:
            return 0
        M.BATCH_SIZE.observe(len(todo))
        t0 = time.perf_counter()
        try:
            results = await asyncio.to_thread(enr.enrich_batch, [ev.payload for _, ev in todo])
        except Exception:  # noqa: BLE001  (lỗi cả lô) -> thử từng tin, tin hỏng -> dlq, không chặn cả lô
            log.exception("lô lỗi, chuyển sang xử lý từng tin")
            M.ERRORS.labels("batch").inc()
            results = []
            for mid, ev in todo:
                try:
                    results.append((await asyncio.to_thread(enr.enrich_batch, [ev.payload]))[0])
                except Exception as e:  # noqa: BLE001
                    results.append(None)
                    await self.bus.dead_letter(IN_STREAM, self.cfg.group, mid, {"e": ev.model_dump_json()}, f"nlp: {e}")
                    M.ERRORS.labels("item").inc()
        dt = time.perf_counter() - t0
        M.INFER_SECONDS.labels(results[0]["model_version"] if results and results[0] else "?").observe(dt)
        n = 0
        for (mid, ev), out in zip(todo, results):
            if out is None:
                continue
            await self.bus.publish(OUT_STREAM, make_event("news_enriched", SERVICE, out, trace_id=ev.trace_id or ev.id))
            await self.bus.r.set(self._dedupe_key(out["model_version"], out["url"]), "1", ex=self.cfg.dedupe_ttl)
            await self.bus.ack(IN_STREAM, self.cfg.group, mid)
            M.ITEMS.labels(out["lang"], out["model_version"], out["label"]).inc()
            await self._aggregate(out)
            n += 1
        self.processed += n
        if n:
            M.LAST_ITEM_TS.set(self.clock())
        return n

    async def _processor(self) -> None:
        while not self._stop.is_set():
            batch = await self._drain_batch()
            try:
                await self.process_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  (Redis lỗi khi publish/ack) -> message vẫn pending, sẽ được reclaim
                log.exception("process_batch lỗi")
                M.ERRORS.labels("process").inc()
                await asyncio.sleep(1)

    # ------------------------------------------------------------ tổng hợp + cảnh báo
    async def _aggregate(self, out: dict) -> None:
        now = self.clock()
        ts = min(_epoch(out.get("published_at")) or now, now)
        w = out["confidence"] * (0.5 + out["importance_score"])
        for sym in out["symbols"]:
            self.agg.add(sym, ts, out["sentiment"], w)
        if not self.cfg.alert_enabled:
            return
        for sym in out["symbols"]:
            rev = self.agg.check_reversal(sym, now, ts)
            if rev:
                await self._alert(rev)

    async def _alert(self, rev: Reversal) -> None:
        arrow = "dương" if rev.direction == "up" else "âm"
        payload = {
            "level": "crit" if abs(rev.current - rev.baseline) >= 1.2 else "warn",
            "title": f"Sentiment {rev.symbol} đảo chiều sang {arrow}",
            "body": (f"{rev.symbol}: trung bình 1h = {rev.current:+.2f} (n={rev.n_current}) so với nền 24h trước đó = "
                     f"{rev.baseline:+.2f} (n={rev.n_baseline}). Chỉ là chỉ báo tin tức tự động, không phải tín hiệu giao dịch."),
            "tags": ["nlp", "sentiment", "reversal", rev.symbol.lower()],
            "dedupe_key": rev.dedupe_key,
        }
        await self.bus.publish(ALERT_STREAM, make_event("alert", SERVICE, payload))
        M.ALERTS.labels(rev.direction).inc()
        log.warning("đảo chiều sentiment %s %s: %+.2f -> %+.2f", rev.symbol, rev.direction, rev.baseline, rev.current)

    async def _housekeeping(self) -> None:
        """Mỗi 30s: dọn cửa sổ, cập nhật gauge theo symbol (xoá gauge symbol đã hết dữ liệu), đo lag."""
        seen: set[str] = set()
        while not self._stop.is_set():
            await asyncio.sleep(30)
            try:
                now = self.clock()
                self.agg.prune(now)
                snap = self.agg.snapshot(now)
                for sym, d in snap.items():
                    for win, v in d.items():
                        if v["mean"] is not None:
                            M.SYMBOL_SENT.labels(sym, win).set(v["mean"])
                        M.SYMBOL_N.labels(sym, win).set(v["n"])
                for sym in seen - set(snap):
                    for win in ("1h", "24h"):
                        for g in (M.SYMBOL_SENT, M.SYMBOL_N):
                            try:
                                g.remove(sym, win)
                            except KeyError:
                                pass
                seen = set(snap)
                for g in await self.bus.r.xinfo_groups(IN_STREAM):
                    if g.get("name") == self.cfg.group:
                        M.LAG.set(int(g.get("lag") or 0) + int(g.get("pending") or 0))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.debug("housekeeping lỗi", exc_info=True)
