"""Quy trình sinh một báo cáo: thu thập -> dựng -> HTML -> PDF -> lưu -> thông báo. Có khoá chống chạy trùng và số liệu Prometheus."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge

from . import notify
from .build import build
from .collect import Gateway, collect
from .config import Settings
from .render import render_html, render_pdf
from .scheduler import last_slot
from .store import Store

log = logging.getLogger("reporter")
GEN = Counter("reporter_reports_total", "Báo cáo đã sinh", ["kind", "result"])
LAST = Gauge("reporter_last_report_timestamp_seconds", "Thời điểm báo cáo cuối thành công", ["kind"])
SEC_FAIL = Gauge("reporter_sections_failed", "Số mục thiếu dữ liệu ở báo cáo cuối", ["kind"])


class Reporter:
    def __init__(self, cfg: Settings, store: Store | None = None, gateway: Gateway | None = None, bus=None, pdf=render_pdf,
                 clock=lambda: datetime.now(timezone.utc)):
        self.cfg = cfg
        self.store = store or Store(cfg.reports_dir, cfg.keep_daily, cfg.keep_weekly)
        self.gw = gateway
        self.bus = bus
        self.pdf = pdf
        self.clock = clock
        self._lock = asyncio.Lock()

    def exists(self, kind: str, period: str) -> bool:
        return self.store.exists(kind, period)

    def default_period(self, kind: str) -> str:
        return last_slot(kind, self.clock(), self.cfg)[0]

    async def generate(self, kind: str, period: str | None = None, force: bool = False) -> dict:
        period = period or self.default_period(kind)
        async with self._lock:
            if not force and self.exists(kind, period):
                return {**(self.store.find(kind, period) or {}), "skipped": True}
            t0 = time.time()
            now = self.clock()
            gw = self.gw or Gateway(self.cfg)
            try:
                raw = await collect(self.cfg, kind, now, gw)
            finally:
                if self.gw is None:
                    await gw.aclose()
            ctx = build(kind, period, raw, self.cfg, now)
            html = render_html(ctx)
            try:
                pdf = await asyncio.to_thread(self.pdf, html)
            except Exception:  # noqa: BLE001  (vẫn lưu HTML, đánh dấu degraded)
                log.exception("tạo PDF lỗi")
                pdf = None
                ctx["fail"] = ctx["fail"] + ["pdf"]
            entry = self.store.save(kind, period, html, pdf, ctx["ok"], ctx["fail"], now)
            GEN.labels(kind, entry["status"]).inc()
            LAST.labels(kind).set(time.time())
            SEC_FAIL.labels(kind).set(len(ctx["fail"]))
            log.info("báo cáo %s %s xong (%s) trong %.1fs, mục thiếu: %s", kind, period, entry["status"], time.time() - t0, ctx["fail"])
            if self.bus is not None:
                try:
                    await notify.publish(self.bus, notify.alert_payload(kind, period, ctx["summary"], self.cfg.base_url, entry["status"] != "ok"))
                except Exception:  # noqa: BLE001
                    log.exception("không phát được thông báo alerts.out")
            return entry
