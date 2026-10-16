"""Thông báo báo cáo mới lên Redis stream alerts.out (alert-service gửi ntfy/Apprise/Telegram). Không có mã đặt lệnh."""
from __future__ import annotations

from tscommon import STREAMS, Bus, make_event

SOURCE = "reporter"


def alert_payload(kind: str, period: str, summary: list[str], base_url: str, degraded: bool) -> dict:
    vi = "ngày" if kind == "daily" else "tuần"
    link = f"{base_url}/#/bao-cao" if base_url else "#/bao-cao"
    body = "\n".join(summary[:3]) + f"\nXem: {link}"
    return {"level": "info", "title": f"Báo cáo {vi} {period} đã sẵn sàng" + (" (thiếu một số mục)" if degraded else ""), "body": body,
            "tags": ["report", kind], "dedupe_key": f"report:{kind}:{period}"}


async def publish(bus: Bus, payload: dict) -> str:
    return await bus.publish(STREAMS["alerts"], make_event("alert", SOURCE, payload))
