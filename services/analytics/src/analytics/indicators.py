"""Chỉ báo kỹ thuật chuẩn bằng TA-Lib (BSD, thư viện C kinh điển) — KHÔNG tự cài lại công thức.

Chỉ phần ghép dữ liệu/Pivot là mã của dự án. Mọi mảng trả về cùng độ dài với DataFrame đầu vào (NaN ở đoạn khởi động).
"""
from __future__ import annotations

from datetime import timezone

import numpy as np
import pandas as pd
import talib

TF_FREQ = {"H1": "1h", "H4": "4h", "D1": "1D"}
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Danh sách nến (ts_open,o,h,l,c,v) -> DataFrame index UTC tăng dần, bỏ trùng ts_open, bỏ nến không hợp lệ."""
    if not rows:
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows)
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    df = df.drop_duplicates("ts_open", keep="last").set_index("ts_open").sort_index()
    for c in ("o", "h", "l", "c"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["v"] = pd.to_numeric(df.get("v", 0), errors="coerce").fillna(0.0)
    df = df.dropna(subset=["o", "h", "l", "c"])
    df = df[(df[["o", "h", "l", "c"]] > 0).all(axis=1)]
    return df[["o", "h", "l", "c", "v"]].astype(float)


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến thấp hơn lên H4/D1 (mốc UTC). Dùng khi DB chưa có khung đó."""
    if df.empty:
        return df
    r = df.resample(TF_FREQ[tf], label="left", closed="left")
    out = pd.DataFrame({"o": r["o"].first(), "h": r["h"].max(), "l": r["l"].min(), "c": r["c"].last(), "v": r["v"].sum()})
    return out.dropna(subset=["o", "h", "l", "c"])


def compute(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """RSI14, MACD(12,26,9), ATR14, Bollinger(20,2), EMA20/50/200, ADX14(+DI/-DI), Stochastic(14,3,3)."""
    o = df["o"].to_numpy(float)
    h = df["h"].to_numpy(float)
    l = df["l"].to_numpy(float)  # noqa: E741
    c = df["c"].to_numpy(float)
    macd, sig, hist = talib.MACD(c, 12, 26, 9)
    up, mid, lo = talib.BBANDS(c, 20, 2.0, 2.0, 0)
    k, d = talib.STOCH(h, l, c, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    atr = talib.ATR(h, l, c, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct = atr / c * 100.0
        bb_width = (up - lo) / mid
        pctb = (c - lo) / (up - lo)
    return {
        "open": o, "high": h, "low": l, "close": c,
        "rsi": talib.RSI(c, 14), "macd": macd, "macd_signal": sig, "macd_hist": hist,
        "atr": atr, "atr_pct": atr_pct,
        "bb_upper": up, "bb_mid": mid, "bb_lower": lo, "bb_width": bb_width, "bb_pctb": pctb,
        "ema20": talib.EMA(c, 20), "ema50": talib.EMA(c, 50), "ema200": talib.EMA(c, 200),
        "adx": talib.ADX(h, l, c, 14), "plus_di": talib.PLUS_DI(h, l, c, 14), "minus_di": talib.MINUS_DI(h, l, c, 14),
        "stoch_k": k, "stoch_d": d,
    }


def pivots(h: float, l: float, c: float) -> dict[str, float]:  # noqa: E741
    """Pivot cổ điển từ H/L/C của một nến: P=(H+L+C)/3, R1=2P-L, S1=2P-H, R2=P+(H-L), S2=P-(H-L)."""
    p = (h + l + c) / 3.0
    return {"p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + (h - l), "s2": p - (h - l)}


def last(a: np.ndarray, i: int = -1) -> float | None:
    if a is None or len(a) < abs(i):
        return None
    v = a[i]
    return None if v is None or not np.isfinite(v) else float(v)


def percentile_rank(a: np.ndarray, value: float | None, window: int | None = None) -> float | None:
    """Phân vị (0..100) của `value` trong các giá trị hữu hạn của `a` (tuỳ chọn: `window` giá trị cuối)."""
    if value is None:
        return None
    x = a[np.isfinite(a)]
    if window:
        x = x[-window:]
    if len(x) < 30:
        return None
    return float((x <= value).sum() / len(x) * 100.0)


def series_list(a: np.ndarray, n: int, nd: int = 6) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a[-n:]]


def epoch(index: pd.DatetimeIndex, n: int) -> list[int]:
    return [int(t.tz_convert(timezone.utc).timestamp()) for t in index[-n:]]
