"""Phân tích 1 symbol × 1 khung: chỉ báo (TA-Lib) -> trạng thái/điểm -> snapshot tóm tắt + chi tiết (có chuỗi vẽ biểu đồ)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import compute, epoch, last, pivots, series_list
from .states import DISCLAIMER, evaluate

SERIES_KEYS = ["ema20", "ema50", "ema200", "bb_upper", "bb_mid", "bb_lower", "rsi", "macd", "macd_signal", "macd_hist",
               "stoch_k", "stoch_d", "adx", "atr"]


@dataclass
class Analysis:
    symbol: str
    tf: str
    df: pd.DataFrame
    ind: dict[str, np.ndarray]
    ev: dict
    summary: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)


def _r(x: float | None, nd: int = 6) -> float | None:
    return None if x is None else round(float(x), nd)


def analyze(symbol: str, tf: str, df: pd.DataFrame, series_points: int = 160) -> Analysis | None:
    if len(df) < 30:
        return None
    ind = compute(df)
    ev = evaluate(ind)
    v = ev["values"]
    c = v["close"]
    ts = df.index[-1]
    e200 = v["ema200"]
    summary = {
        "symbol": symbol, "tf": tf, "bar_ts": ts.isoformat(), "bars": int(len(df)), "close": _r(c),
        "heat": ev["heat"], "bias": ev["bias"], "trend": ev["trend"], "momentum": ev["momentum"],
        "volatility": ev["volatility"], "squeeze": ev["squeeze"], "atr_percentile": ev["atr_percentile"],
        "rsi": _r(v["rsi"], 2), "adx": _r(v["adx"], 2), "atr_pct": _r(v["atr_pct"], 4), "macd_hist": _r(v["macd_hist"], 8),
        "stoch_k": _r(v["stoch_k"], 2), "bb_pctb": _r(v["bb_pctb"], 3),
        "ema200_dist_pct": _r((c - e200) / e200 * 100, 3) if e200 else None,
        "states": ev["states"], "disclaimer": DISCLAIMER,
    }
    prev = df.iloc[-1]
    n = min(series_points, len(df))
    detail = {
        **summary,
        "indicators": {k: _r(val, 8) for k, val in v.items() if k not in {"close", "atr_pct"}},
        "pivot": {k: _r(x, 8) for k, x in pivots(float(prev["h"]), float(prev["l"]), float(prev["c"])).items()},
        "pivot_note": "Pivot cổ điển tính từ H/L/C của nến gần nhất",
        "series": {"t": epoch(df.index, n), **{k: series_list(ind[k], n, 8) for k in SERIES_KEYS}},
    }
    return Analysis(symbol, tf, df, ind, ev, summary, detail)
