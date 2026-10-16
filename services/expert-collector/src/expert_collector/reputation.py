"""Ham thuan: diem uy tin, phat hien martingale/grid, phat hien xoa lich su."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Thresholds:
    min_months: float = 6
    max_drawdown_pct: float = 40
    min_gain_pct: float = 0
    min_followers: int = 0
    min_score: float = 50
    reject_martingale: bool = True


@dataclass
class ReputationResult:
    score: float
    qualified: bool
    reasons: list[str]


def detect_martingale(trades: list[dict], mult: float = 1.8, min_hits: int = 3) -> bool:
    """trades: lenh da dong theo thu tu thoi gian, moi dong {volume, profit}.
    Martingale: sau lenh lo, lenh ke tiep co volume >= mult * volume lenh lo, lap >= min_hits lan."""
    hits = 0
    for prev, cur in zip(trades, trades[1:]):
        try:
            if float(prev["profit"]) < 0 and float(prev["volume"]) > 0 and float(cur["volume"]) >= mult * float(prev["volume"]):
                hits += 1
        except (KeyError, TypeError, ValueError):
            continue
    return hits >= min_hits


def detect_grid(open_positions: list[dict], min_legs: int = 5, max_cv: float = 0.25) -> bool:
    """Grid: >= min_legs lenh CUNG symbol, CUNG chieu, gia vao cach deu (he so bien thien khoang cach <= max_cv)."""
    groups: dict[tuple[str, str], list[float]] = {}
    for p in open_positions:
        if p.get("entry") is None:
            continue
        groups.setdefault((p["symbol"], p["side"]), []).append(float(p["entry"]))
    for prices in groups.values():
        if len(prices) < min_legs:
            continue
        prices.sort()
        gaps = [b - a for a, b in zip(prices, prices[1:]) if b - a > 0]
        if len(gaps) < min_legs - 1:
            continue
        mean = sum(gaps) / len(gaps)
        var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
        if mean > 0 and math.sqrt(var) / mean <= max_cv:
            return True
    return False


def detect_history_wipe(history: list[dict], current: dict, month_drop: float = 2.0, trade_drop_ratio: float = 0.7) -> bool:
    """history: cac snapshot reputation cu. Nghi 'xoa lich su' neu so thang hoat dong giam >= month_drop
    so voi muc cao nhat tung thay, hoac so lenh giam xuong < ratio * muc cao nhat."""
    max_m = max((float(h.get("months_active") or 0) for h in history), default=0)
    max_t = max((float(h.get("trades") or 0) for h in history), default=0)
    cur_m = float(current.get("months_active") or 0)
    cur_t = current.get("trades")
    if max_m - cur_m >= month_drop:
        return True
    if cur_t is not None and max_t > 0 and float(cur_t) < trade_drop_ratio * max_t:
        return True
    return False


def reputation_score(rep: dict[str, Any], th: Thresholds, *, martingale: bool = False, grid: bool = False,
                     history_wiped: bool = False) -> ReputationResult:
    reasons: list[str] = []
    months = float(rep.get("months_active") or 0)
    dd = rep.get("max_drawdown_pct")
    gain = float(rep.get("gain_pct") or 0)
    followers = int(rep.get("followers") or 0)

    if months < th.min_months:
        reasons.append(f"months_active {months:g} < {th.min_months:g}")
    if dd is None:
        reasons.append("drawdown unknown")
    elif float(dd) > th.max_drawdown_pct:
        reasons.append(f"drawdown {float(dd):g}% > {th.max_drawdown_pct:g}%")
    if gain < th.min_gain_pct:
        reasons.append(f"gain {gain:g}% < {th.min_gain_pct:g}%")
    if followers < th.min_followers:
        reasons.append(f"followers {followers} < {th.min_followers}")
    if th.reject_martingale and martingale:
        reasons.append("martingale detected")
    if th.reject_martingale and grid:
        reasons.append("grid detected")
    if history_wiped:
        reasons.append("history_wiped")

    dd_v = float(dd) if dd is not None else th.max_drawdown_pct
    s_months = min(months / 24, 1) * 25
    s_dd = max(0.0, 1 - dd_v / th.max_drawdown_pct) * 30 if th.max_drawdown_pct > 0 else 0.0
    s_gain = min(max(gain, 0) / 100, 1) * 20
    s_fol = min(math.log10(followers + 1) / 3, 1) * 15
    s_ratio = min((max(gain, 0) / max(dd_v, 1)) / 5, 1) * 10
    score = round(s_months + s_dd + s_gain + s_fol + s_ratio, 2)
    if martingale or grid or history_wiped:
        score = round(score * 0.5, 2)
    if score < th.min_score:
        reasons.append(f"score {score:g} < {th.min_score:g}")
    return ReputationResult(score=score, qualified=not reasons, reasons=reasons)


def opinion_score(rep: dict[str, Any], min_credibility: float = 40.0) -> ReputationResult:
    """Nguon Y KIEN (kind='opinion'): diem = uy tin khoi tao cau hinh (0-100) trong danh muc, KHONG phai thanh tich giao dich."""
    cred = float(rep.get("credibility") or 0)
    reasons = [] if cred >= min_credibility else [f"credibility {cred:g} < {min_credibility:g}"]
    return ReputationResult(score=round(cred, 2), qualified=not reasons, reasons=reasons)
