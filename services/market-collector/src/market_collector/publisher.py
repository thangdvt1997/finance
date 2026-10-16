from __future__ import annotations

from typing import Iterable

from prometheus_client import Counter, Gauge
from tscommon import STREAMS, Bus, make_event

from .models import Bar, Quote
from .quality import bar_problem

SOURCE = "market-collector"

BARS_PUBLISHED = Counter("mc_bars_published_total", "Nen da phat len md.bars", ["provider", "tf"])
QUOTES_PUBLISHED = Counter("mc_quotes_published_total", "Quote da phat", ["provider"])
ALERTS_PUBLISHED = Counter("mc_alerts_published_total", "Alert da phat", ["level"])
FETCH_ERRORS = Counter("mc_fetch_errors_total", "Loi fetch", ["provider"])
FETCH_EMPTY = Counter("mc_fetch_empty_total", "Lan fetch tra rong", ["provider"])
QUALITY_ISSUES = Counter("mc_quality_issues_total", "Van de chat luong du lieu", ["provider", "kind"])
BARS_REJECTED = Counter("mc_bars_rejected_total", "Nen bi loai truoc khi phat (OHLC/volume khong hop le)", ["provider", "reason"])
GAP_DAYS = Gauge("mc_gap_days", "So ngay con thieu du lieu dang cho lap day", ["provider"])
GAP_FILLED = Counter("mc_gap_filled_total", "So ngay thieu da duoc lap day", ["provider"])
LOOP_ERRORS = Counter("mc_loop_errors_total", "Loi khong mong doi trong vong lap provider (da tu phuc hoi)", ["provider"])
LOOP_ALIVE = Gauge("mc_provider_loop_alive", "1 neu task provider dang chay", ["provider"])
BACKFILL_RUNNING = Gauge("mc_backfill_running", "So backfill dang chay")


class Publisher:
    def __init__(self, bus: Bus):
        self.bus = bus

    async def bars(self, bars: Iterable[Bar]) -> int:
        n = 0
        for b in bars:
            prob = bar_problem(b)  # chot chan cuoi: khong bao gio phat nen phi ly
            if prob:
                BARS_REJECTED.labels(b.source, prob[0]).inc()
                continue
            await self.bus.publish(STREAMS["bars"], make_event("bar", SOURCE, b.to_payload()))
            BARS_PUBLISHED.labels(b.source, b.tf).inc()
            n += 1
        return n

    async def quote(self, q: Quote) -> None:
        await self.bus.publish(STREAMS["quotes"], make_event("quote", SOURCE, q.to_payload()))
        QUOTES_PUBLISHED.labels(q.source).inc()

    async def alert(self, level: str, title: str, body: str, tags: list[str], dedupe_key: str) -> None:
        await self.bus.publish(STREAMS["alerts"], make_event(
            "alert", SOURCE, {"level": level, "title": title, "body": body, "tags": tags, "dedupe_key": dedupe_key}))
        ALERTS_PUBLISHED.labels(level).inc()
