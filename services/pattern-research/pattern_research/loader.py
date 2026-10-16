"""Loader dung chung cho du lieu mau hinh nen (Parquet).

    from pattern_research.loader import load, symbols, split_bounds
    df = load("XAUUSD", "H1", split="train")             # cot: ts_open,o,h,l,c,v,n_m1,split,in_split ; index = ts_open (UTC)
    df = load("EURUSD", "M15", split="val", warmup=200)  # them 200 nen truoc doan val (in_split=False) de khoi dong chi bao
    df = load("BTCUSD", "D1", split="test", allow_test=True)  # TEST KHOA: bat buoc allow_test, moi lan mo ghi test_access.log
min_fill=0.5 loc nen co < 50% so phut M1 mong doi (nen thieu du lieu). Warmup khong bao gio lan sang tap test.
"""
from __future__ import annotations

import getpass
import json
import os
import time
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get("PATTERN_DATA", "/root/trading-system/data/research/patterns"))
MINUTES = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6, "M10": 10, "M12": 12, "M15": 15, "M20": 20, "M30": 30,
           "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360, "H8": 480, "H12": 720, "D1": 1440, "W1": 10080, "MN1": 43200}
SPLITS = ("train", "val", "test")


def manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text())


def split_bounds() -> dict:
    return json.loads((ROOT / "splits.json").read_text())


def symbols() -> list[str]:
    return sorted({f["symbol"] for f in manifest()["files"]})


def _utc(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def load(symbol: str, tf: str, split: str | None = None, start=None, end=None,
         min_fill: float = 0.0, warmup: int = 0, allow_test: bool = False) -> pd.DataFrame:
    if split is not None and split not in SPLITS:
        raise ValueError(f"split phai thuoc {SPLITS}")
    if split == "test":
        if not allow_test:
            raise PermissionError("Tap TEST bi khoa: chi mo 1 lan o buoc bao cao cuoi (allow_test=True).")
        with open(ROOT / "test_access.log", "a") as f:
            f.write(f"{time.strftime('%F %T')} {getpass.getuser()} {symbol} {tf}\n")
    df = pd.read_parquet(ROOT / "bars" / f"{symbol}_{tf}.parquet")
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    df["split"] = df["split"].astype(str)
    if min_fill > 0 and tf != "M1":
        df = df[df.n_m1 >= min_fill * MINUTES[tf]]
    df = df.reset_index(drop=True)
    m = pd.Series(True, index=df.index)
    if split:
        m &= df.split == split
    if start is not None:
        m &= df.ts_open >= _utc(start)
    if end is not None:
        m &= df.ts_open < _utc(end)
    if warmup and m.any():
        first = int(m.to_numpy().argmax())
        keep = m.copy()
        keep.iloc[max(0, first - warmup):first] = True
        if split != "test":
            keep &= df.split != "test"
        out = df[keep].copy()
        out["in_split"] = m[keep].to_numpy()
    else:
        out = df[m].copy()
        out["in_split"] = True
    out.index = pd.DatetimeIndex(out["ts_open"])
    out.index.name = None
    return out
