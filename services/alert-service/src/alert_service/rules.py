from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

log = logging.getLogger("alert.rules")

LAST_BAR_KEY = "rules:last_bar"  # hash symbol -> epoch seconds nhận bar gần nhất


class RuleEngine:
    """Đánh giá luật cảnh báo cấu hình YAML. Luật:
    - stream_silence: không có md.bars mới > max_silence_minutes cho symbol theo dõi.
    - heartbeat: tin 'hệ thống còn sống' mỗi ngày lúc HH:MM UTC.
    evaluate() trả về list payload alert; caller đưa vào AlertEngine.handle (dedupe áp dụng như thường).
    """

    def __init__(self, redis, rules: list[dict], engine_stats: Callable | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.r = redis
        self.rules = rules
        self.clock = clock
        self.engine_stats = engine_stats
        self.started = clock()

    async def on_bar(self, payload: dict) -> None:
        sym = payload.get("symbol")
        if not sym:
            return
        tf = payload.get("tf")
        for rule in self.rules:
            if rule.get("type") == "stream_silence" and sym in rule.get("symbols", []) \
                    and rule.get("tf") in (None, tf):
                await self.r.hset(f"{LAST_BAR_KEY}:{rule['name']}", sym, str(self.clock().timestamp()))

    async def evaluate(self) -> list[dict]:
        now = self.clock()
        out: list[dict] = []
        for rule in self.rules:
            t = rule.get("type")
            try:
                if t == "stream_silence":
                    out += await self._silence(rule, now)
                elif t == "heartbeat":
                    out += await self._heartbeat(rule, now)
            except Exception:  # noqa: BLE001
                log.exception("luật %s lỗi", rule.get("name"))
        return out

    async def _silence(self, rule: dict, now: datetime) -> list[dict]:
        weekdays = rule.get("weekdays", [0, 1, 2, 3, 4])  # thị trường đóng cuối tuần (UTC)
        if now.weekday() not in weekdays:
            return []
        limit = timedelta(minutes=float(rule.get("max_silence_minutes", 15)))
        seen = await self.r.hgetall(f"{LAST_BAR_KEY}:{rule['name']}")
        alerts = []
        for sym in rule.get("symbols", []):
            last = datetime.fromtimestamp(float(seen[sym]), timezone.utc) if sym in seen else self.started
            gap = now - last
            if gap > limit:
                mins = int(gap.total_seconds() // 60)
                alerts.append({
                    "level": rule.get("level", "warn"),
                    "title": f"Dữ liệu im lặng: {sym}",
                    "body": f"Không có nến mới cho {sym} trong {mins} phút (ngưỡng {int(limit.total_seconds() // 60)} phút).",
                    "tags": ["rule", "data-silence", sym],
                    "dedupe_key": f"silence:{rule['name']}:{sym}",
                })
        return alerts

    async def _heartbeat(self, rule: dict, now: datetime) -> list[dict]:
        hh, mm = (int(x) for x in rule.get("at", "01:00").split(":"))
        if (now.hour, now.minute) < (hh, mm):
            return []
        day = now.strftime("%Y-%m-%d")
        if not await self.r.set(f"rules:heartbeat:{rule['name']}:{day}", "1", nx=True, ex=172800):
            return []
        stats = await self.engine_stats() if self.engine_stats else {}
        body = "Hệ thống còn sống. " + (", ".join(f"{k}={v}" for k, v in sorted(stats.items())) or "chưa có cảnh báo nào.")
        return [{"level": rule.get("level", "info"), "title": f"Heartbeat hằng ngày {day}", "body": body,
                 "tags": ["rule", "heartbeat"], "dedupe_key": f"heartbeat:{rule['name']}:{day}"}]
