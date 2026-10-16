"""Lịch chạy: hàm thuần `due()` (inject đồng hồ để test) + vòng lặp asyncio. Idempotent theo kỳ, chạy bù khi khởi động muộn."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import Settings

log = logging.getLogger("reporter.scheduler")


def last_slot(kind: str, now: datetime, cfg: Settings) -> tuple[str, datetime]:
    """(period, thời điểm theo lịch gần nhất <= now). period = ngày (giờ VN) của thời điểm lịch."""
    tz = ZoneInfo(cfg.tz)
    loc = now.astimezone(tz)
    if kind == "daily":
        h, m = cfg.daily_at
        d = loc.date()
        slot = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
        if slot > loc:
            d = d - timedelta(days=1)
            slot = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
    else:
        h, m = cfg.weekly_at
        d = loc.date() - timedelta(days=(loc.weekday() - cfg.weekly_dow) % 7)
        slot = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
        if slot > loc:
            d = d - timedelta(days=7)
            slot = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
    return d.isoformat(), slot


def due(now: datetime, cfg: Settings, exists) -> list[tuple[str, str]]:
    """Các (kind, period) cần sinh tại thời điểm `now`; `exists(kind, period)` -> bool. Ngày chạy bù: kỳ gần nhất chưa có file."""
    out = []
    for kind in ("daily", "weekly"):
        period, _ = last_slot(kind, now, cfg)
        if not exists(kind, period):
            out.append((kind, period))
    return out


def next_runs(now: datetime, cfg: Settings) -> dict:
    tz = ZoneInfo(cfg.tz)
    res = {}
    for kind in ("daily", "weekly"):
        _, slot = last_slot(kind, now, cfg)
        step = timedelta(days=1 if kind == "daily" else 7)
        nxt = (slot.replace(tzinfo=None) + step).replace(tzinfo=tz)
        res[kind] = nxt.isoformat()
    return res


async def loop(cfg: Settings, generate, exists, stop: asyncio.Event, clock=lambda: datetime.now(timezone.utc)) -> None:
    """generate(kind, period) là coroutine. Lỗi một báo cáo không dừng vòng lặp; thử lại tối thiểu mỗi 30 phút."""
    last_try: dict[tuple[str, str], datetime] = {}
    while not stop.is_set():
        now = clock()
        for kind, period in due(now, cfg, exists):
            t = last_try.get((kind, period))
            if t and now - t < timedelta(minutes=30):
                continue
            last_try[(kind, period)] = now
            try:
                await generate(kind, period)
            except Exception:  # noqa: BLE001
                log.exception("sinh báo cáo %s %s lỗi", kind, period)
        try:
            await asyncio.wait_for(stop.wait(), timeout=cfg.tick_seconds)
        except asyncio.TimeoutError:
            pass
