"""Dac trung cho tung lenh ung vien — CHI dung du lieu nen <= nen tin hieu (sig_i), khong nhin tuong lai."""
from __future__ import annotations

import numpy as np
import pandas as pd

TF_MIN = {"M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}
ASSET = {"EURUSD": "fx", "GBPUSD": "fx", "USDJPY": "fx", "XAUUSD": "metal", "US500": "idx", "US30": "idx",
         "USTEC": "idx", "BTCUSD": "crypto", "ETHUSD": "crypto", "XAUUSD_GC": "metal", "US500_SPY": "idx"}
FEATURES = ["atr_rel", "vol_ratio", "vol_rank", "compress10", "atr_fast_slow", "dist_sup", "dist_res", "vol_z",
            "trend50", "ret10", "hour_sin", "hour_cos", "dow", "sess_asia", "sess_london", "sess_ny", "log_tf",
            "score", "sl_atr", "kb1", "kb2", "kb3", "kb4", "a_fx", "a_metal", "a_idx", "a_crypto"]


def bar_features(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """df: cot ts_open,o,h,l,c,v (da sap xep, index vi tri). Tra DataFrame dac trung cung index (gia tri tai i chi dung <= i)."""
    h, l, c = df["h"], df["l"], df["c"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr = atr.replace(0, np.nan)
    out = pd.DataFrame(index=df.index)
    out["atr_rel"] = atr / c
    out["vol_ratio"] = atr / atr.shift(1).rolling(100, min_periods=30).mean()
    lo, hi = atr.rolling(250, min_periods=60).min(), atr.rolling(250, min_periods=60).max()
    out["vol_rank"] = (atr - lo) / (hi - lo).replace(0, np.nan)
    out["compress10"] = (h.rolling(10).max() - l.rolling(10).min()) / atr
    out["atr_fast_slow"] = tr.ewm(alpha=1 / 5, adjust=False).mean() / tr.ewm(alpha=1 / 50, adjust=False).mean()
    out["dist_sup"] = (c - l.shift(1).rolling(50, min_periods=20).min()) / atr
    out["dist_res"] = (h.shift(1).rolling(50, min_periods=20).max() - c) / atr
    v = df["v"].astype(float) if "v" in df else pd.Series(0.0, index=df.index)
    vm, vs = v.rolling(50, min_periods=20).mean(), v.rolling(50, min_periods=20).std()
    out["vol_z"] = ((v - vm) / vs.replace(0, np.nan)).where(v > 0)
    out["trend50"] = (c - c.rolling(50, min_periods=20).mean()) / atr
    out["ret10"] = (c - c.shift(10)) / atr
    return out.replace([np.inf, -np.inf], np.nan)


def trade_features(tr: pd.DataFrame, bf: pd.DataFrame, tf: str, symbol: str) -> pd.DataFrame:
    """tr: cac lenh cua 1 chuoi (cot sig_i, entry_ts, pattern, score, sl_atr). bf: bar_features cua chuoi."""
    x = bf.iloc[tr["sig_i"].to_numpy()].reset_index(drop=True).copy()
    ts = pd.to_datetime(tr["entry_ts"]).reset_index(drop=True)
    hr = ts.dt.hour + ts.dt.minute / 60
    daily = tf == "D1"
    x["hour_sin"] = 0.0 if daily else np.sin(2 * np.pi * hr / 24)
    x["hour_cos"] = 0.0 if daily else np.cos(2 * np.pi * hr / 24)
    x["dow"] = ts.dt.dayofweek.astype(float)
    x["sess_asia"] = ((hr < 7) & ~daily).astype(float)
    x["sess_london"] = ((hr >= 7) & (hr < 13) & ~daily).astype(float)
    x["sess_ny"] = ((hr >= 13) & (hr < 21) & ~daily).astype(float)
    x["log_tf"] = np.log(TF_MIN[tf])
    x["score"] = tr["score"].to_numpy()
    x["sl_atr"] = tr["sl_atr"].to_numpy()
    for k in (1, 2, 3, 4):
        x[f"kb{k}"] = (tr["pattern"].to_numpy() == f"KB-{k}").astype(float)
    a = ASSET[symbol]
    for k in ("fx", "metal", "idx", "crypto"):
        x[f"a_{k}"] = float(a == k)
    x.index = tr.index
    return x[FEATURES]
