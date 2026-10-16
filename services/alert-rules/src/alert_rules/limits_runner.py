"""Vòng nhắc giới hạn: ~30 giây/lần áp giới hạn nới lỏng đã đủ 24 giờ + đánh giá tiến độ; vượt 70/90/100% -> thông báo kind `limit` (+ Web Push chung).
CHỈ NHẮC: không chặn lệnh, không phát alerts.out toàn cục. Mỗi ngưỡng 1 lần/chu kỳ (ngày|tháng, giờ VN)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .limits import LABELS, SPEC, THRESHOLDS, crossed, cycle_of, progress_for

log = logging.getLogger("alert_rules.limits_runner")


def _fmt(v, unit) -> str:
    return "-" if v is None else (f"{v:.0f}" if unit == "orders" else f"{v:.2f}%")


class LimitWatcher:
    def __init__(self, store, provider, notifier, clock=time.time):
        self.store, self.prov, self.notifier, self.clock = store, provider, notifier, clock
        self._purged_at = 0.0

    async def metrics(self, account_id: str, now: datetime) -> dict | None:
        fn = getattr(self.prov, "limit_metrics", None)
        if fn is None:
            return None
        try:
            return await fn(account_id, now)
        except Exception:  # noqa: BLE001
            log.exception("đọc số liệu giới hạn lỗi")
            return None

    async def tick(self) -> int:
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        for m in await self.store.limits_apply_due(now):
            await self.notifier.send(m["owner"], "limit", "info", "Thay đổi giới hạn đã có hiệu lực",
                                     f"{LABELS[m['key']].capitalize()}: " + ("đã được xoá." if m["new"] is None else f"giá trị mới {m['new']:g} đã có hiệu lực."),
                                     m["account_id"], push=False)
        by_acc: dict[str, list[dict]] = {}
        for r in await self.store.limits_active():
            by_acc.setdefault(r["account_id"], []).append(r)
        sent = 0
        for acc, rows in by_acc.items():
            m = await self.metrics(acc, now)
            for r in rows:
                key = r["key"]
                prog = progress_for(key, r["value"], m, now)
                t = crossed(prog)
                if not t:
                    continue
                cyc = cycle_of(key, now)
                new = [th for th in THRESHOLDS if th <= t and await self.store.limit_alert_claim(r["owner_user_id"], acc, key, cyc, th, now)]
                if not new:
                    continue
                th = max(new)
                unit = SPEC[key][2]
                goal = key == "monthly_target_pct"
                sev = "info" if goal else ("warn" if th < 90 else "danger")
                if goal:
                    title = "Đã đạt mục tiêu tháng" if th >= 100 else f"Mục tiêu tháng đạt {th}%"
                else:
                    title = f"Giới hạn {LABELS[key]}: " + ("đã chạm" if th >= 100 else f"đạt {th}%")
                body = f"Tài khoản {acc}: hiện {_fmt(prog['current'], unit)} / giới hạn {_fmt(r['value'], unit)}."
                await self.notifier.send(r["owner_user_id"], "limit", sev, title, body, acc)
                sent += 1
        if self.clock() - self._purged_at > 3600:
            self._purged_at = self.clock()
            try:
                await self.store.notif_purge(now - timedelta(days=90))
                await self.store.limit_alert_purge(now - timedelta(days=40))
            except Exception:  # noqa: BLE001
                log.exception("dọn thông báo lỗi")
        return sent
