from __future__ import annotations

from datetime import datetime, timezone

LEVEL_VI = {"info": "THÔNG TIN", "warn": "CẢNH BÁO", "crit": "NGHIÊM TRỌNG"}
LEVEL_MARK = {"info": "[i]", "warn": "[!]", "crit": "[!!!]"}


def _fmt_ts(ts: datetime | None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_alert(payload: dict, ts: datetime | None = None) -> str:
    level = payload.get("level", "info")
    lines = [f"{LEVEL_MARK.get(level, '[i]')} {LEVEL_VI.get(level, level.upper())}: {payload.get('title', '(không tiêu đề)')}"]
    body = (payload.get("body") or "").strip()
    if body:
        lines.append(body[:1500])
    tags = payload.get("tags") or []
    footer = _fmt_ts(ts)
    if tags:
        footer += " | " + " ".join(f"#{t}" for t in tags)
    lines.append(footer)
    return "\n".join(lines)


def format_digest(items: list[dict]) -> str:
    """Gom nhóm khi bão cảnh báo: đếm theo mức, liệt kê tiêu đề phổ biến."""
    by_level: dict[str, int] = {}
    by_title: dict[str, int] = {}
    for it in items:
        by_level[it.get("level", "info")] = by_level.get(it.get("level", "info"), 0) + 1
        t = it.get("title", "?")
        by_title[t] = by_title.get(t, 0) + 1
    head = f"[i] GOM NHÓM: {len(items)} cảnh báo bị giới hạn tốc độ"
    lv = ", ".join(f"{LEVEL_VI.get(k, k)}={v}" for k, v in sorted(by_level.items(), reverse=True))
    top = sorted(by_title.items(), key=lambda kv: -kv[1])[:8]
    rows = [f"- {t} (x{n})" for t, n in top]
    more = len(by_title) - len(top)
    if more > 0:
        rows.append(f"- ... và {more} loại khác")
    return "\n".join([head, lv, *rows])
