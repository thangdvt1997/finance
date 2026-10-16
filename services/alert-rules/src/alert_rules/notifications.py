"""Trung tâm thông báo của client: ghi thông báo theo chủ sở hữu + Web Push CHUNG (không số dư/tên tài khoản/tên nguồn), tôn trọng cài đặt notif.<kind>.{app,push}."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

log = logging.getLogger("alert_rules.notifications")

KINDS = ("rule", "limit", "report", "briefing", "support", "system")
SEVERITIES = ("info", "warn", "danger")
ALWAYS_APP = ("support", "system")          # không tắt được thông báo trong ứng dụng (phản hồi quản trị, thông báo hệ thống)
LEVEL_SEVERITY = {"info": "info", "warn": "warn", "crit": "danger"}
LINK_RE = re.compile(r"^(/c/)?#/[A-Za-z0-9_\-/?=&.]{0,120}$")


def pref_flag(data: dict | None, kind: str, ch: str) -> bool:
    n = ((data or {}).get("notif") or {}).get(kind)
    if isinstance(n, dict) and n.get(ch) is False:
        return False
    return True


class Notifier:
    def __init__(self, store, push=None, clock=time.time):
        self.store, self.push, self.clock = store, push, clock

    async def send(self, owner: str, kind: str, severity: str, title: str, body: str = "", account_id: str | None = None,
                   link: str | None = None, dedupe_key: str | None = None, push: bool = True) -> int | None:
        """Ghi thông báo (nếu người dùng không tắt `app` cho loại này) và gửi Web Push chung (nếu không tắt `push`). Không bao giờ ném lỗi."""
        try:
            prefs = (await self.store.cprefs_get(owner))["data"]
            app_on = kind in ALWAYS_APP or pref_flag(prefs, kind, "app")
            push_on = push and pref_flag(prefs, kind, "push")
            nid = None
            if app_on:
                ts = datetime.fromtimestamp(self.clock(), timezone.utc)
                nid = await self.store.notif_add(owner, kind, severity, title[:200], body[:2000], account_id, link, ts, dedupe_key)
                if nid is None:                        # trùng dedupe_key: đã thông báo rồi, không push lại
                    return None
            if push_on and self.push is not None:
                await self.push.notify(owner)
            return nid
        except Exception:  # noqa: BLE001
            log.exception("gửi thông báo lỗi")
            return None


def clean_link(link: str | None) -> str | None:
    return link if link and LINK_RE.match(link) else None
