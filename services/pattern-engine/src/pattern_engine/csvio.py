"""Đọc nến từ CSV (ts_open_utc,o,h,l,c,v) — dùng cho fixture/golden test và công cụ replay."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .series import Bar


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_csv(path: str | Path) -> list[Bar]:
    out: list[Bar] = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Bar(parse_ts(r["ts_open_utc"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r.get("v") or 0)))
    return out
