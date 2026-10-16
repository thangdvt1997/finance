"""Phát cảnh báo ngưỡng rủi ro lên alerts.out khi TRẠNG THÁI ĐỔI (ok->warn->crit), không lặp mỗi chu kỳ."""
from __future__ import annotations

from tscommon.events import make_event

import re

# Tài khoản thử/QA (mt5:99xxxxxx, qa-*): vẫn đánh giá rủi ro trên API nhưng KHÔNG phát cảnh báo ra alerts.out/ntfy.
TEST_ACCOUNT_RE = re.compile(r"^(mt[45]:99\d{6}|qa-.*)$")


def is_test_account(account_id: str) -> bool:
    return bool(TEST_ACCOUNT_RE.match(account_id or ""))


LEVELS = {"ok": 0, "warn": 1, "crit": 2}
HASH = "risk:alert_state"


def transitions(account_id: str, items: list[dict], prev: dict[str, str], min_level: str = "warn") -> tuple[list[dict], dict[str, str]]:
    """Trả (payload alert, state mới). Leo thang hoặc hồi phục (về ok sau khi đã cảnh báo) mới phát."""
    out, new = [], {}
    floor = LEVELS.get(min_level, 1)
    for it in items:
        if it["status"] not in LEVELS:
            continue
        key, cur = it["key"], it["status"]
        was = prev.get(key, "ok")
        new[key] = cur
        if cur == was:
            continue
        label = f"{it['label']}: {it['value']:.2f}{it['unit']} / hạn mức {it['limit']:g}{it['unit']}" if it["value"] is not None else it["label"]
        if LEVELS[cur] > LEVELS[was] and LEVELS[cur] >= floor:
            lvl = "crit" if cur == "crit" else "warn"
            out.append({"level": lvl, "title": f"[{account_id}] Rủi ro {'VƯỢT' if cur == 'crit' else 'gần'} hạn mức: {it['label']}",
                        "body": label + ". Chỉ cảnh báo (READ-ONLY), không tự động hành động.",
                        "tags": ["risk-monitor", f"account:{account_id}", it["key"]], "dedupe_key": f"risk:{account_id}:{key}:{cur}"})
        elif cur == "ok" and LEVELS[was] >= floor:
            out.append({"level": "info", "title": f"[{account_id}] Rủi ro đã về trong hạn mức: {it['label']}", "body": label,
                        "tags": ["risk-monitor", f"account:{account_id}", it["key"]], "dedupe_key": f"risk:{account_id}:{key}:ok"})
    return out, new


class AlertEmitter:
    def __init__(self, redis, bus, cfg: dict):
        self.r, self.bus, self.cfg = redis, bus, cfg

    async def process(self, account_id: str, items: list[dict]) -> int:
        if is_test_account(account_id):
            return 0
        raw = await self.r.hget(HASH, account_id)
        import json
        prev = json.loads(raw) if raw else {}
        alerts, new = transitions(account_id, items, prev, self.cfg.get("alerts", {}).get("min_level", "warn"))
        for a in alerts:
            await self.bus.publish("alerts.out", make_event("alert", "risk-monitor", a))
        await self.r.hset(HASH, account_id, json.dumps(new))
        return len(alerts)
