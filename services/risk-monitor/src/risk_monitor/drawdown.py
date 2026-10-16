"""Drawdown & P&L theo ngày/tuần từ chuỗi equity (thuần tính toán). Ngày/tuần theo UTC (tuần bắt đầu thứ Hai 00:00 UTC).
Giới hạn: không loại nạp/rút tiền (equity nhảy do nạp/rút sẽ bị tính là lãi/lỗ)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

Point = tuple[datetime, float]


def _dd_stats(vals: list[Point], start_equity: float | None) -> dict:
    """P&L so với equity đầu kỳ + drawdown tối đa trong kỳ (đỉnh chạy bắt đầu từ equity đầu kỳ)."""
    if not vals:
        return {"start_equity": start_equity, "pnl": None, "pnl_pct": None, "max_dd_pct": None, "max_dd": None, "points": 0}
    base = start_equity if start_equity else vals[0][1]
    peak, worst, worst_abs = base, 0.0, 0.0
    for _, e in vals:
        peak = max(peak, e)
        if peak > 0:
            dd = (e - peak) / peak
            if dd < worst:
                worst, worst_abs = dd, e - peak
    last = vals[-1][1]
    return {"start_equity": base, "pnl": last - base, "pnl_pct": ((last - base) / base * 100.0 if base else None),
            "max_dd_pct": worst * 100.0, "max_dd": worst_abs, "points": len(vals)}


def _downsample(pts: list[Point], n: int) -> list[Point]:
    if len(pts) <= n:
        return pts
    step = len(pts) / n
    out = [pts[int(i * step)] for i in range(n)]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def drawdown_report(series: list[Point], now: datetime | None = None, underwater_points: int = 240) -> dict:
    """series: [(ts UTC, equity)] tăng dần theo ts."""
    now = now or datetime.now(timezone.utc)
    s = sorted((p for p in series if p[1] is not None), key=lambda p: p[0])
    if not s:
        return {"available": False}
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = day0 - timedelta(days=day0.weekday())

    def before(t0: datetime) -> float | None:
        prev = [e for ts, e in s if ts < t0]
        return prev[-1] if prev else None

    def period(t0: datetime) -> dict:
        vals = [p for p in s if p[0] >= t0]
        if vals:
            return {**_dd_stats(vals, before(t0)), "basis": "period"}
        # chuỗi thưa (paper: 1 điểm/ngày) hoặc tài khoản im lặng: dùng quan sát gần nhất so với quan sát liền trước
        prev = s[-2][1] if len(s) > 1 else None
        return {**_dd_stats(s[-1:], prev), "basis": "last_observation"}

    day = period(day0)
    week = period(week0)
    # đỉnh/đáy toàn bộ cửa sổ + đáy sau đỉnh gần nhất
    peak, peak_ts = s[0][1], s[0][0]
    max_dd, mdd_peak_ts, mdd_trough_ts, cur_peak, cur_peak_ts = 0.0, s[0][0], s[0][0], s[0][1], s[0][0]
    uw: list[Point] = []
    for ts, e in s:
        if e > cur_peak:
            cur_peak, cur_peak_ts = e, ts
        dd = (e - cur_peak) / cur_peak if cur_peak > 0 else 0.0
        uw.append((ts, dd * 100.0))
        if dd < max_dd:
            max_dd, mdd_peak_ts, mdd_trough_ts = dd, cur_peak_ts, ts
        if e > peak:
            peak, peak_ts = e, ts
    last_ts, last = s[-1]
    trough_e = min(e for _, e in s)
    trough_ts = next(ts for ts, e in s if e == trough_e)
    cur_dd = (last - cur_peak) / cur_peak * 100.0 if cur_peak > 0 else 0.0
    return {
        "available": True,
        "as_of": last_ts.isoformat(),
        "window_start": s[0][0].isoformat(),
        "equity": last,
        "peak": {"equity": peak, "ts": peak_ts.isoformat()},
        "trough": {"equity": trough_e, "ts": trough_ts.isoformat()},
        "dd_from_peak_pct": cur_dd,
        "days_since_peak": (last_ts - cur_peak_ts).total_seconds() / 86400.0,
        "max_dd_pct": max_dd * 100.0,
        "max_dd_peak_ts": mdd_peak_ts.isoformat(), "max_dd_trough_ts": mdd_trough_ts.isoformat(),
        "day": day, "week": week,
        "underwater": [{"t": int(ts.timestamp()), "dd": round(d, 4)} for ts, d in _downsample(uw, underwater_points)],
    }
