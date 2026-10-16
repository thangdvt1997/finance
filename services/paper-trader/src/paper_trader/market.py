"""Khung dữ liệu thị trường cho engine. CHỈ chứa bar ĐÃ ĐÓNG (ts_open + tf <= now) -> chống look-ahead ngay từ nguồn."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .models import TF_DELTA, Bar, utc


def frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    """rows: {ts_open,o,h,l,c,v}; loại trùng ts_open (giữ dòng đầu), sắp tăng dần, index UTC."""
    if not rows:
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows)
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    df = df.drop_duplicates("ts_open", keep="first").set_index("ts_open").sort_index()
    for c in ("o", "h", "l", "c"):
        df[c] = df[c].astype(float)
    df["v"] = df["v"].astype(float) if "v" in df else 0.0
    return df[["o", "h", "l", "c", "v"]]


def resample_h1(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp H1 -> D1/H4 theo UTC khi nguồn không có sẵn khung đó."""
    rule = {"D1": "1D", "H4": "4h"}[tf]
    r = df.resample(rule, label="left", closed="left")
    out = pd.DataFrame({"o": r["o"].first(), "h": r["h"].max(), "l": r["l"].min(), "c": r["c"].last(), "v": r["v"].sum()})
    return out.dropna(subset=["o", "c"])


class MarketView:
    def __init__(self, frames: dict[str, pd.DataFrame], tf: str, now: datetime):
        self.tf, self.td, self.now = tf, TF_DELTA[tf], utc(now)
        lim = self.now - self.td
        self.frames = {s: df[df.index <= lim] for s, df in frames.items() if df is not None}

    def bar_at(self, sym: str, T: datetime) -> Bar | None:
        df = self.frames.get(sym)
        if df is None or df.empty:
            return None
        ts = pd.Timestamp(utc(T))
        if ts not in df.index:
            return None
        r = df.loc[ts]
        return Bar(ts.to_pydatetime(), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))

    def close_at(self, sym: str, T: datetime) -> float | None:
        """Giá đóng cửa của bar gần nhất có ts_open <= T."""
        df = self.frames.get(sym)
        if df is None or df.empty:
            return None
        v = df["c"].asof(pd.Timestamp(utc(T)))
        return None if pd.isna(v) else float(v)

    def open_at(self, sym: str, T: datetime) -> float | None:
        b = self.bar_at(sym, T)
        return b.o if b else self.close_at(sym, T)

    def history(self, symbols, T: datetime) -> dict[str, pd.DataFrame]:
        ts = pd.Timestamp(utc(T))
        return {s: self.frames[s].loc[:ts].copy() for s in symbols if s in self.frames and not self.frames[s].empty}

    def step_times(self, after_close: datetime | None, symbols) -> list[datetime]:
        idx: set[pd.Timestamp] = set()
        for s in symbols:
            df = self.frames.get(s)
            if df is not None and not df.empty:
                idx.update(df.index)
        out = sorted(t.to_pydatetime() for t in idx)
        if after_close is not None:
            out = [t for t in out if t + self.td > utc(after_close)]
        return out

    def latest_close_ts(self, symbols) -> datetime | None:
        ts = self.step_times(None, symbols)
        return ts[-1] + self.td if ts else None
