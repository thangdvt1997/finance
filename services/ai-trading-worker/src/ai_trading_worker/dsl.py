"""Detector khai báo (YAML) chạy VECTOR HOÁ trên nến đã đóng. Mọi luật tại nến i chỉ dùng dữ liệu <= i (không look-ahead; có test cắt cụt).
Vào lệnh (mô phỏng) ở GIÁ MỞ của nến i+1. Không thực thi mã người dùng: chỉ các luật có biên trong ai_trading.scenario_schema."""
from __future__ import annotations

import numpy as np
import pandas as pd

WARMUP = 60


def _sh(x: np.ndarray, k: int) -> np.ndarray:
    """x dịch về sau k nến (giá trị của nến i-k tại vị trí i); k nến đầu = NaN."""
    if k == 0:
        return x
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:-k]
    return out


def _rule_mask(r: dict, o, h, l, c, atr, ts) -> np.ndarray:
    k = r["rule"]
    with np.errstate(invalid="ignore", divide="ignore"):
        if k == "move_atr":
            end, start = _sh(c, r["ago"]), _sh(c, r["ago"] + r["bars"])
            diff = (start - end) if r["dir"] == "down" else (end - start)
            return diff / atr >= r["min"]
        if k == "bear_body":
            return (o - c) / atr >= r["min_atr"]
        if k == "bear_engulf":
            o1, c1 = _sh(o, 1), _sh(c, 1)
            return (c < o) & (o >= np.maximum(o1, c1)) & (c <= np.minimum(o1, c1)) & ((o - c) > np.abs(o1 - c1))
        if k == "upper_wick":
            rng = h - l
            return (rng > 0) & ((h - np.maximum(o, c)) / np.where(rng > 0, rng, np.nan) >= r["min_ratio"])
        if k == "break_low":
            return c < pd.Series(l).shift(1).rolling(r["bars"]).min().to_numpy()
        if k == "ma":
            s = pd.Series(c)
            ma = (s.ewm(span=r["period"], adjust=False).mean() if r["kind"] == "ema" else s.rolling(r["period"]).mean()).to_numpy()
            ok = np.arange(len(c)) >= r["period"]
            return ok & ((c > ma) if r["side"] == "above" else (c < ma))
        if k == "rsi":
            d = pd.Series(c).diff()
            up = d.clip(lower=0).ewm(alpha=1 / r["period"], adjust=False).mean()
            dn = (-d.clip(upper=0)).ewm(alpha=1 / r["period"], adjust=False).mean()
            rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(100.0).to_numpy()
            ok = np.arange(len(c)) >= r["period"]
            return ok & ((rsi >= r["value"]) if r["op"] == ">=" else (rsi <= r["value"]))
        if k == "hours":
            hr = pd.DatetimeIndex(ts).hour.to_numpy()
            return ((hr >= r["from"]) & (hr < r["to"])) if r["from"] < r["to"] else ((hr >= r["from"]) | (hr < r["to"] % 24))
    raise ValueError("luật không hỗ trợ")


def signal_mask(sc: dict, b) -> np.ndarray:
    """Mảng bool theo nến: True = luật thoả trên nến ĐÃ ĐÓNG i (trước cooldown). `b` = pattern_research.backtest.Bars."""
    n = len(b.c)
    m = np.ones(n, dtype=bool)
    for r in sc["detector"]["rules"]:
        m &= np.nan_to_num(_rule_mask(r, b.o, b.h, b.l, b.c, b.atr, b.ts), nan=0).astype(bool)
    m &= b.atr > 0
    m[:WARMUP] = False
    m[n - 1:] = False                  # nến cuối: chưa có nến kế tiếp để vào lệnh
    return m


def signal_indices(sc: dict, b) -> np.ndarray:
    idx = np.flatnonzero(signal_mask(sc, b))
    cd = int(sc["detector"].get("cooldown_bars", 0))
    if cd <= 0 or len(idx) == 0:
        return idx
    keep, last = [], -10**9
    for i in idx:
        if i - last > cd:
            keep.append(int(i))
            last = int(i)
    return np.asarray(keep, dtype=int)


def sl_price(sc: dict, b, i: int, sl_param: float) -> float:
    s = sc["levels"]["sl"]
    if s["type"] == "swing_high":
        lo = max(0, i - s["bars"] + 1)
        return float(b.h[lo:i + 1].max() + sl_param * b.atr[i])
    return float(b.c[i] + sl_param * b.atr[i])
