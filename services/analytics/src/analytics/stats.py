"""Thống kê chéo symbol: tương quan lăn 30 ngày, thống kê theo phiên (Tokyo/London/NY) và biên độ theo giờ."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _clean(x: float | None, nd: int = 3) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def correlation(frames: dict[str, pd.DataFrame], window: int = 30, max_symbols: int = 40) -> dict | None:
    """Pearson trên log-return D1 của `window` ngày gần nhất + cửa sổ liền trước (để phát hiện đổi chiều)."""
    cols = {}
    for sym, df in frames.items():
        if len(df) >= window + 5:
            s = df["c"].copy()
            s.index = s.index.normalize()
            cols[sym] = s[~s.index.duplicated(keep="last")]
    if len(cols) < 2:
        return None
    # ưu tiên symbol có nhiều dữ liệu nhất nếu vượt giới hạn
    syms = sorted(cols, key=lambda k: (-len(cols[k]), k))[:max_symbols]
    syms.sort()
    closes = pd.DataFrame({s: cols[s] for s in syms}).sort_index()
    # crypto giao dich 24/7 (co nen T7/CN) con co phieu/FX thi khong: bo hang T7/CN thua (<90% symbol co nen) de log-return T6->T2 cua crypto la 3 ngay,
    # cung khung voi tai san khac (khong thi diff() quanh hang NaN cuoi tuan lam mat return thu Hai cua co phieu)
    closes = closes[~((closes.index.dayofweek >= 5) & (closes.notna().mean(axis=1) < 0.9))]
    rets = np.log(closes).diff()
    rets = rets.dropna(how="all")
    mp = max(10, int(window * 0.6))
    now = rets.iloc[-window:].corr(min_periods=mp)
    prev = rets.iloc[-2 * window:-window].corr(min_periods=mp) if len(rets) >= window + mp else None

    def mat(m: pd.DataFrame | None) -> list[list[float | None]] | None:
        if m is None:
            return None
        return [[_clean(m.loc[a, b]) if a != b else 1.0 for b in syms] for a in syms]

    return {"symbols": syms, "window": window, "matrix": mat(now), "matrix_prev": mat(prev),
            "as_of": closes.index[-1].isoformat(), "method": "Pearson trên log-return D1"}


def correlation_flips(corr: dict, min_abs_delta: float) -> list[dict]:
    """Cặp mà tương quan hiện tại và cửa sổ trước khác dấu và lệch >= ngưỡng."""
    out = []
    if not corr or not corr.get("matrix_prev"):
        return out
    s, m, p = corr["symbols"], corr["matrix"], corr["matrix_prev"]
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            a, b = m[i][j], p[i][j]
            if a is None or b is None:
                continue
            if a * b < 0 and abs(a - b) >= min_abs_delta:
                out.append({"a": s[i], "b": s[j], "now": a, "prev": b, "delta": _clean(a - b)})
    return sorted(out, key=lambda x: -abs(x["delta"]))


def sessions(symbol: str, h1: pd.DataFrame, windows: dict[str, list[int]], days: int = 30) -> dict | None:
    """Thống kê H1 trong `days` ngày: biên độ trung bình theo phiên (UTC) và theo giờ."""
    if len(h1) < 24:
        return None
    df = h1[h1.index >= h1.index[-1] - pd.Timedelta(days=days)].copy()
    if df.empty:
        return None
    df["hour"] = df.index.hour
    df["day"] = df.index.normalize()
    df["rng"] = (df["h"] - df["l"]) / df["o"] * 100.0
    out: dict = {}
    for name, (a, b) in windows.items():
        sel = df[(df["hour"] >= a) & (df["hour"] < b)]
        if sel.empty:
            out[name] = {"start_utc": a, "end_utc": b, "days": 0, "avg_range_pct": None, "avg_return_pct": None, "avg_abs_return_pct": None}
            continue
        g = sel.groupby("day")
        rng = (g["h"].max() - g["l"].min()) / g["o"].first() * 100.0
        ret = (g["c"].last() - g["o"].first()) / g["o"].first() * 100.0
        out[name] = {"start_utc": a, "end_utc": b, "days": int(len(rng)), "avg_range_pct": _clean(rng.mean(), 4),
                     "avg_return_pct": _clean(ret.mean(), 4), "avg_abs_return_pct": _clean(ret.abs().mean(), 4)}
    hourly = df.groupby("hour")["rng"].agg(["mean", "count"])
    return {"symbol": symbol, "days_window": days, "bars": int(len(df)), "sessions": out,
            "hourly": [{"hour": h, "avg_range_pct": _clean(hourly.loc[h, "mean"], 4) if h in hourly.index else None,
                        "n": int(hourly.loc[h, "count"]) if h in hourly.index else 0} for h in range(24)],
            "note": "Giờ UTC; phiên cố định theo cấu hình (không chỉnh DST). Thống kê quá khứ, không dự báo."}
