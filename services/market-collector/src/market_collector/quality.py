from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from .models import TF_SECONDS, Bar, ensure_utc

# So nen toi thieu bi thieu lien tiep moi coi la "gap" (tranh bao dong gia tao khi thanh khoan thap/ngay le)
DEFAULT_MIN_GAP_BARS = {"M1": 30, "M5": 12, "M15": 8, "H1": 6, "H4": 6, "D1": 10}


@dataclass(frozen=True)
class Issue:
    kind: str  # duplicate | invalid_ohlc | invalid_volume | nonpositive | gap | outlier
    detail: str
    ts: object = None


def bar_problem(b: Bar) -> tuple[str, str] | None:
    """Kiem tra 1 nen: tra (kind, chi_tiet) neu khong hop le, None neu OK.
    Quy tac: gia huu han > 0; low <= min(o,c); high >= max(o,c); high >= low; volume huu han va >= 0."""
    vals = (b.o, b.h, b.l, b.c)
    if any(not math.isfinite(x) for x in vals) or any(x <= 0 for x in vals):
        return "nonpositive", f"gia khong hop le {vals}"
    if b.h < max(b.o, b.c) - 1e-12 or b.l > min(b.o, b.c) + 1e-12 or b.h < b.l:
        return "invalid_ohlc", f"OHLC mau thuan o={b.o} h={b.h} l={b.l} c={b.c}"
    if not math.isfinite(b.v) or b.v < 0:
        return "invalid_volume", f"volume khong hop le v={b.v}"
    return None


def _weekend_explained(prev, cur) -> bool:
    """Khoang (prev,cur) chua tron thu Bay va <= 3 ngay -> nghi cuoi tuan, khong bao gap."""
    if cur - prev > timedelta(hours=72):
        return False
    d = prev.replace(hour=0, minute=0, second=0, microsecond=0)
    while d <= cur:
        if d.weekday() == 5:
            return True
        d += timedelta(days=1)
    return False


def check_bars(bars: Iterable[Bar], *, min_gap_bars: int | None = None, ignore_weekend: bool = True,
               max_jump_pct: float = 10.0) -> tuple[list[Bar], list[Issue]]:
    """Kiem tra chat luong 1 chuoi nen cung (symbol, tf, source).

    Tra ve (nen_sach, issues). Nen sach: da bo trung + bo nen OHLC sai/gia <= 0.
    Gap va outlier chi bao (nen van duoc giu)."""
    items = list(bars)
    issues: list[Issue] = []
    if not items:
        return [], issues
    tf = items[0].tf

    counts = Counter(ensure_utc(b.ts_open) for b in items)
    for ts, n in counts.items():
        if n > 1:
            issues.append(Issue("duplicate", f"{n} nen trung ts_open", ts))
    uniq: dict = {}
    for b in items:
        uniq[ensure_utc(b.ts_open)] = b
    ordered = [uniq[k] for k in sorted(uniq)]

    clean: list[Bar] = []
    for b in ordered:
        prob = bar_problem(b)
        if prob:
            issues.append(Issue(prob[0], prob[1], b.ts_open))
            continue
        clean.append(b)

    sec = TF_SECONDS[tf]
    thr = min_gap_bars if min_gap_bars is not None else DEFAULT_MIN_GAP_BARS.get(tf, 10)
    for prev, cur in zip(clean, clean[1:]):
        p, c = ensure_utc(prev.ts_open), ensure_utc(cur.ts_open)
        missing = int((c - p).total_seconds() // sec) - 1
        if missing >= thr and not (ignore_weekend and _weekend_explained(p, c)):
            issues.append(Issue("gap", f"thieu {missing} nen {tf} giua {p.isoformat()} va {c.isoformat()}", c))
        if prev.c > 0 and abs(cur.o / prev.c - 1) * 100 > max_jump_pct or \
           prev.c > 0 and abs(cur.c / prev.c - 1) * 100 > max_jump_pct:
            issues.append(Issue("outlier", f"nhay gia > {max_jump_pct}% ({prev.c} -> {cur.c})", c))
    return clean, issues
