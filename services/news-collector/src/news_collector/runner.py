"""Chay cac Source theo chu ky, dedupe (Redis SET NX), publish len bus, metrics."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from prometheus_client import Counter, Gauge
from tscommon.bus import STREAMS, Bus
from tscommon.events import make_event
from tscommon.risk_windows import load_config as load_risk_config, risk_alerts

from .alerts import upcoming_high
from .calendar_book import CalendarBook, load_enrich_config
from .models import Emit
from .sources.base import Context, Source

log = logging.getLogger("news_collector.runner")
PUBLISHED = Counter("nc_items_published_total", "Items published", ["source", "stream"])
DUPLICATES = Counter("nc_items_duplicate_total", "Items dropped as duplicates", ["source"])
ERRORS = Counter("nc_fetch_errors_total", "Fetch errors", ["source"])
LAST_OK = Gauge("nc_last_success_timestamp", "Unix ts of last successful fetch", ["source"])


class Runner:
    def __init__(self, bus: Bus, ctx: Context, sources: list[Source], alert_window_min: float = 30,
                 alert_check_interval: float = 60, dedupe_ttl: int = 30 * 86400, service_name: str = "news-collector",
                 risk_enabled: bool = True, risk_config: dict | None = None):
        self.bus, self.ctx, self.sources = bus, ctx, sources
        self.book = CalendarBook(load_enrich_config(ctx.config_dir))
        ctx.book = self.book
        self.risk_enabled = risk_enabled
        self.risk_cfg = risk_config or (load_risk_config() if risk_enabled else None)
        self.alert_window_min, self.alert_check_interval = alert_window_min, alert_check_interval
        self.dedupe_ttl, self.service_name = dedupe_ttl, service_name
        self.calendar_cache: dict[tuple[str, str], dict] = {}
        self.status: dict[str, dict] = {s.name: {"last_ok": None, "last_error": None, "published": 0} for s in sources}
        self._tasks: list[asyncio.Task] = []

    async def _is_new(self, key: str) -> bool:
        return bool(await self.bus.r.set(f"nc:seen:{key}", "1", nx=True, ex=self.dedupe_ttl))

    async def _publish_one(self, source_name: str, e: Emit) -> int:
        if e.stream == "calendar":
            self.calendar_cache[(e.payload["source"], e.payload["event_id"])] = e.payload  # luon cap nhat cache de canh bao dung
            self.book.mark_published(e.payload)
        if not await self._is_new(e.dedupe_key):
            DUPLICATES.labels(source_name).inc()
            return 0
        await self.bus.publish(STREAMS[e.stream], make_event(e.type, self.service_name, e.payload))
        PUBLISHED.labels(source_name, STREAMS[e.stream]).inc()
        return 1

    async def publish(self, source_name: str, emits: list[Emit]) -> int:
        n = 0
        for e in emits:
            if e.stream == "calendar":  # lam giau (forecast/previous tu nguon khac, actual tu API, surprise, group) truoc khi phat
                m = self.book.ingest(e.payload)
                e = Emit(e.stream, e.type, m, f"cal:{m['source']}:{m['event_id']}:{self.book.digest(m)}")
            n += await self._publish_one(source_name, e)
        return n

    async def flush_calendar(self) -> int:
        """Phat lai cac hang lich da doi sau khi lam giau (vd vua co actual tu API). Idempotent nho digest."""
        self.book.prune(self.ctx.now())
        n = 0
        for m in self.book.dirty():
            n += await self._publish_one("cal_enrich", Emit("calendar", "calendar", m,
                                                            f"cal:{m['source']}:{m['event_id']}:{self.book.digest(m)}"))
        return n

    async def run_once(self, source: Source) -> int:
        st = self.status[source.name]
        try:
            emits = await source.fetch(self.ctx)
            n = await self.publish(source.name, emits)
        except Exception as ex:
            ERRORS.labels(source.name).inc()
            st["last_error"] = f"{type(ex).__name__}: {ex}"
            log.exception("source %s loi", source.name)
            return 0
        try:
            n += await self.flush_calendar()
        except Exception:
            log.exception("flush_calendar loi")
        now = self.ctx.now()
        st.update(last_ok=now.isoformat(), published=st["published"] + n)
        LAST_OK.labels(source.name).set(now.timestamp())
        return n

    async def check_alerts(self) -> int:
        now = self.ctx.now()
        for k in [k for k, v in self.calendar_cache.items() if datetime.fromisoformat(v["ts"]) < now]:
            del self.calendar_cache[k]
        if not self.calendar_cache:
            return 0
        return await self.publish("alerts", upcoming_high(list(self.calendar_cache.values()), now, self.alert_window_min))

    async def check_risk(self) -> int:
        """Alert cua so rui ro tin (pre T-30 / enter / exit) tu so lich da lam giau. Dedupe theo khoa pha."""
        now = self.ctx.now()
        evs = [self.book.merged(k) for k, p in self.book.raw.items()
               if p.get("impact") == "high" and now - timedelta(hours=3) <= datetime.fromisoformat(p["ts"]) <= now + timedelta(hours=2)]
        emits = [Emit("alerts", "alert", {"level": a["level"], "title": a["title"], "body": a["body"], "tags": a["tags"],
                                         "dedupe_key": a["dedupe_key"]}, f"alert:{a['dedupe_key']}")
                 for a in risk_alerts(evs, now, self.risk_cfg)]
        return await self.publish("risk", emits)

    async def _loop(self, source: Source) -> None:
        while True:
            await self.run_once(source)
            await asyncio.sleep(source.interval)

    async def _alert_loop(self) -> None:
        while True:
            try:
                if self.risk_enabled:
                    await self.check_risk()
                else:
                    await self.check_alerts()
            except Exception:
                log.exception("alert check loi")
            await asyncio.sleep(self.alert_check_interval)

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._loop(s), name=f"src-{s.name}") for s in self.sources]
        self._tasks.append(asyncio.create_task(self._alert_loop(), name="alerts"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
