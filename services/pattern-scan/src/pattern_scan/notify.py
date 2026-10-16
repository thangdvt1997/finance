"""Thông báo kèm ẢNH qua ntfy (kênh sẵn có trong stack; Telegram để sau). Nội dung đi qua scrub_sources (không tên nguồn dữ liệu).
ntfy: PUT /<topic> với thân = PNG (đính kèm), tiêu đề/nội dung qua query param (hỗ trợ UTF-8)."""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
import urllib.request
from collections import deque

from prometheus_client import Counter
from tscommon.sources import scrub_sources

log = logging.getLogger("pattern-scan.notify")
SENT = Counter("pattern_scan_notify_total", "Thông báo kịch bản", ["result"])

STATE_VI = {"forming": "ĐANG HÌNH THÀNH", "armed": "SẴN SÀNG", "triggered": "ĐÃ KÍCH HOẠT", "invalid": "ĐÃ HUỶ"}
DISCLAIMER = "Chỉ thông tin/mô phỏng (paper), không phải khuyến nghị đầu tư; hệ thống không đặt lệnh."


def _f(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "-"
    return f"{x:.5f}".rstrip("0").rstrip(".") if abs(x) < 10 else f"{x:.2f}"


def signal_text(p: dict) -> tuple[str, str]:
    lv = p.get("levels") or {}
    title = f"{p['pattern']} SELL · {p['symbol']} {p['tf']} · {STATE_VI.get(p['state'], p['state'])}"
    lines = [f"Điểm {float(p.get('score') or 0):.0f}/100"]
    if "entry" in lv:
        lines.append(f"Entry {_f(lv['entry'])} · SL {_f(lv.get('sl'))} · TP {_f(lv.get('tp_1r'))}/{_f(lv.get('tp_2r'))}/{_f(lv.get('tp_3r'))}")
    for s in p.get("steps") or []:
        lines.append(f"{'✓' if s.get('ok') else '·'} {s.get('label', '')}")
    lines.append(DISCLAIMER)
    return scrub_sources(title), scrub_sources("\n".join(lines))


def close_text(t: dict) -> tuple[str, str]:
    title = f"Paper đóng · {t['pattern']} {t['symbol']} {t['tf']} · {float(t['result_r']):+.2f}R"
    legs = ", ".join(f"{k + 1}:{lg['status']} {float(lg['r']):+.2f}R" for k, lg in enumerate(t["legs"]))
    return scrub_sources(title), scrub_sources(f"{legs}\nChi phí giả định {t['cost_r']:.2f}R. {DISCLAIMER}")


class Ntfy:
    def __init__(self, base: str, topic: str, token: str = "", click: str = "", max_per_min: int = 20, sender=None):
        self.base, self.topic, self.token, self.click = base.rstrip("/"), topic, token, click
        self.max_per_min = max_per_min
        self._sent: deque[float] = deque()
        self.sender = sender or self._http
        self.outbox: list[dict] = []   # vài tin gần nhất (debug/test)

    def _http(self, url: str, body: bytes | None, headers: dict) -> int:
        req = urllib.request.Request(url, data=body or b"", headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (URL nội bộ từ cấu hình)
            return r.status

    def _allow(self) -> bool:
        now = time.monotonic()
        while self._sent and now - self._sent[0] > 60:
            self._sent.popleft()
        if len(self._sent) >= self.max_per_min:
            return False
        self._sent.append(now)
        return True

    async def send(self, title: str, message: str, png: bytes | None = None, filename: str = "kich-ban.png", tags: str = "chart_with_downwards_trend",
                   priority: int = 3) -> bool:
        if not self._allow():
            SENT.labels("throttled").inc()
            return False
        q = {"title": title, "message": message, "tags": tags, "priority": str(priority)}
        if png:
            q["filename"] = filename
        if self.click:
            q["click"] = self.click
        url = f"{self.base}/{urllib.parse.quote(self.topic)}?{urllib.parse.urlencode(q)}"
        headers = {"Content-Type": "image/png" if png else "text/plain"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            code = await asyncio.to_thread(self.sender, url, png, headers)
            ok = 200 <= int(code) < 300
        except Exception as e:  # noqa: BLE001
            log.warning("ntfy lỗi: %s", type(e).__name__)
            ok = False
        SENT.labels("ok" if ok else "fail").inc()
        self.outbox = (self.outbox + [{"title": title, "message": message, "image": bool(png), "ok": ok}])[-20:]
        return ok
