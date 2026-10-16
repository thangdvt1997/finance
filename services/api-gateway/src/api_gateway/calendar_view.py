"""Hien thi lich: an hang cua nguon chinh thuc (BLS/FOMC/ECB/BoE/BoJ) khi da co hang Fair Economy CUNG NHOM ban phat hanh
(`extra.group`, do news-collector gan) trong +-60 phut: hang FF chi tiet hon (forecast/previous/actual theo tung chi so).
Ham thuan, khong I/O."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

OFFICIAL = {"bls", "fed", "ecb", "boe", "boj"}
DETAIL = {"faireconomy", "fmp"}
WINDOW = timedelta(minutes=60)


def _group(r: dict[str, Any]) -> str | None:
    ex = r.get("extra")
    return ex.get("group") if isinstance(ex, dict) else None


def hide_superseded(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detail = {}
    for r in rows:
        g = _group(r)
        if g and r.get("source") in DETAIL:
            detail.setdefault(g, []).append(r["ts"])
    if not detail:
        return rows
    out = []
    for r in rows:
        g = _group(r)
        if g and r.get("source") in OFFICIAL and any(abs(t - r["ts"]) <= WINDOW for t in detail.get(g, ())):
            continue
        out.append(r)
    return out
