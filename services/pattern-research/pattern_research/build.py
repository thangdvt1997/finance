"""M1 sach -> M5/M15/H1/H4/D1 (dung phien) + QC + manifest + split theo thoi gian.
Chay: python -m pattern_research.build   (doc OUT/m1/*.parquet, ghi OUT/bars, manifest.json, qc.json, splits.json)"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

OUT = Path(os.environ.get("PATTERN_OUT", "/out"))
TFS = {"M5": ("5min", 5), "M15": ("15min", 15), "H1": ("1h", 60), "H4": ("4h", 240), "D1": ("1D", 1440)}
KIND = {"XAUUSD": "fx", "EURUSD": "fx", "GBPUSD": "fx", "USDJPY": "fx", "US500": "fx",
        "BTCUSD": "crypto", "ETHUSD": "crypto"}
EMBARGO_DAYS = 5
SPLIT_START = pd.Timestamp("2023-10-01", tz="UTC")


def clean_m1(df: pd.DataFrame):
    n0 = len(df)
    df = df.copy()
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    for k in "ohlcv":
        df[k] = pd.to_numeric(df[k], errors="coerce")
    q = {"rows_raw": n0}
    nan = df[["o", "h", "l", "c"]].isna().any(axis=1) | df["ts_open"].isna()
    q["drop_nan"] = int(nan.sum())
    df = df[~nan]
    dup = df.duplicated("ts_open", keep="last")
    q["drop_duplicate_ts"] = int(dup.sum())
    df = df[~dup]
    bad = (df[["o", "h", "l", "c"]] <= 0).any(axis=1) | (df.h < df[["o", "c", "l"]].max(axis=1) - 1e-12) | \
          (df.l > df[["o", "c", "h"]].min(axis=1) + 1e-12)
    q["drop_bad_ohlc"] = int(bad.sum())
    df = df[~bad]
    df = df.sort_values("ts_open").reset_index(drop=True)
    ret = (df.c / df.c.shift(1) - 1).abs()
    q["extreme_move_m1_gt_5pct"] = int((ret > 0.05).sum())  # chi gan co, khong xoa
    q["flat_bar_pct"] = round(float(((df.o == df.h) & (df.h == df.l) & (df.l == df.c)).mean() * 100), 3)
    q["zero_volume_pct"] = round(float((df.v.fillna(0) <= 0).mean() * 100), 3)
    q["rows_clean"] = len(df)
    return df, q


def resample(m1: pd.DataFrame, tf: str, kind: str) -> pd.DataFrame:
    freq, _ = TFS[tf]
    ts = m1["ts_open"]
    if kind == "fx" and tf in ("H4", "D1"):
        # ngay giao dich dong luc 17:00 New York (21/22h UTC theo DST)
        loc = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
        shifted = loc + pd.Timedelta(hours=7)
        # nen sau 17:00 NY thu Sau (Yahoo con 1 nen H1 du): gop vao nen thu Sau, tranh nen D1 "ma" 1 gio
        late_fri = (loc.dt.weekday == 4) & (loc.dt.hour >= 17)
        shifted = shifted.where(~late_fri, shifted - pd.Timedelta(hours=2))
        key = shifted.dt.floor(freq)
        a = m1.assign(k=key).groupby("k", sort=True).agg(
            o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"),
            n_m1=("o", "size"), first_ts=("ts_open", "min"))
        lab = (a.index - pd.Timedelta(hours=7)).tz_localize(
            "America/New_York", ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")
        a["ts_open"] = pd.Series(lab, index=a.index).fillna(a["first_ts"])
        a = a.drop(columns="first_ts").reset_index(drop=True)
    else:
        a = m1.assign(k=ts.dt.floor(freq)).groupby("k", sort=True).agg(
            o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"),
            n_m1=("o", "size")).reset_index().rename(columns={"k": "ts_open"})
    a["n_m1"] = a["n_m1"].astype("int16")
    return a[["ts_open", "o", "h", "l", "c", "v", "n_m1"]]


def gap_report(m1: pd.DataFrame, kind: str):
    t = m1["ts_open"]
    d = t.diff().dt.total_seconds().div(60)
    idx = d[d > 5.5].index
    cats = {"weekend_closure": 0, "le65min": 0, "le1day": 0, "gt1day": 0}
    top = []
    for i in idx:
        s, e, mins = t[i - 1], t[i], float(d[i])
        if kind == "fx" and s.weekday() == 4 and s.hour >= 19 and e.weekday() in (6, 0) and mins < 3500:
            cats["weekend_closure"] += 1
            continue
        cats["le65min" if mins <= 65 else "le1day" if mins <= 1440 else "gt1day"] += 1
        top.append((mins, s.isoformat(), e.isoformat()))
    top.sort(reverse=True)
    span = pd.date_range(t.iloc[0].floor("min"), t.iloc[-1].floor("min"), freq="min")
    if kind == "fx":
        wd, hr = span.weekday, span.hour
        open_mask = ~(((wd == 4) & (hr >= 22)) | (wd == 5) | ((wd == 6) & (hr < 21)))
        span = span[open_mask]
    present = int(t.dt.floor("min").isin(span).sum())
    exp = len(span)
    return {"gap_events": cats, "top_gaps_min": [{"min": a, "from": b, "to": c} for a, b, c in top[:8]],
            "expected_minutes": exp, "missing_pct_m1": round(100 * (1 - present / exp), 3)}


def compute_split(end: pd.Timestamp):
    span = end - SPLIT_START
    t1 = (SPLIT_START + span * 0.6).normalize()
    t2 = (SPLIT_START + span * 0.8).normalize()
    emb = pd.Timedelta(days=EMBARGO_DAYS)
    return {"start": SPLIT_START.isoformat(), "end": end.isoformat(), "embargo_days": EMBARGO_DAYS,
            "train": [None, t1.isoformat()], "val": [(t1 + emb).isoformat(), t2.isoformat()],
            "test": [(t2 + emb).isoformat(), None],
            "note": "train<T1 | embargo | val | embargo | test; ranh gioi chung cho moi ma/khung; test KHOA - chi mo 1 lan cuoi"}


def label_split(ts: pd.Series, sp: dict) -> pd.Series:
    t1, v0, t2, s0 = (pd.Timestamp(sp["train"][1]), pd.Timestamp(sp["val"][0]),
                      pd.Timestamp(sp["val"][1]), pd.Timestamp(sp["test"][0]))
    out = pd.Series("embargo", index=ts.index, dtype="object")
    out[ts < t1] = "train"
    out[(ts >= v0) & (ts < t2)] = "val"
    out[ts >= s0] = "test"
    return out.astype("category")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def yahoo_base(s: str, iv: str):
    p = OUT / "raw" / "yahoo" / f"{s}_{iv}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
    step = pd.Timedelta(iv.replace("m", "min") if iv.endswith("m") else iv)
    df = df[df.ts_open + step <= pd.Timestamp.now(tz="UTC")]  # bo nen dang chay
    df = df.assign(v=df["v"].fillna(0))
    return df


def main():
    (OUT / "bars").mkdir(parents=True, exist_ok=True)
    cleaned, qc, mode = {}, {}, {}
    for s in KIND:
        f = OUT / "m1" / f"{s}.parquet"
        if f.exists():
            df, q = clean_m1(pd.read_parquet(f))
            if (df.ts_open.iloc[-1] - df.ts_open.iloc[0]).days >= 365:
                cleaned[s], qc[s], mode[s] = df, q, "m1"
                q["m1_from"], q["m1_to"] = df.ts_open.iloc[0].isoformat(), df.ts_open.iloc[-1].isoformat()
                q.update(gap_report(df, KIND[s]))
                print("clean m1", s, q["rows_clean"], flush=True)
                continue
            print("m1 qua ngan, dung yahoo cho", s, len(df), flush=True)
        h1 = yahoo_base(s, "1h")
        if h1 is None:
            continue
        df, q = clean_m1(h1)
        cleaned[s], qc[s], mode[s] = df, q, "yahoo"
        q["m1_from"], q["m1_to"] = df.ts_open.iloc[0].isoformat(), df.ts_open.iloc[-1].isoformat()
        q["note"] = "nguon Yahoo: H1 ~730 ngay; M5/M15 chi ~60-80 ngay; khong co M1; proxy (vang=GC=F, US500=ES=F)"
        d = df.ts_open.diff().dt.total_seconds().div(3600)
        q["gap_events"] = {"gt3h_non_weekend": int(((d > 3) & (df.ts_open.dt.weekday != 6) & (df.ts_open.shift(1).dt.weekday != 4)).sum())}
        q["missing_pct_m1"] = None
        print("clean yahoo-h1", s, len(df), flush=True)
    end_cands = [df.ts_open.iloc[-1] for s, df in cleaned.items() if KIND.get(s) == "fx"]
    end = (min(end_cands) if end_cands else max(df.ts_open.iloc[-1] for df in cleaned.values())).normalize()
    sp = compute_split(end)
    (OUT / "splits.json").write_text(json.dumps(sp, indent=1))
    manifest = {"built_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    for s, base in cleaned.items():
        kind = KIND[s]
        outs = {}
        if mode[s] == "m1":
            for tf in TFS:
                outs[tf] = resample(base, tf, kind)
            outs["M1"] = base.assign(n_m1=1)[["ts_open", "o", "h", "l", "c", "v", "n_m1"]]
        else:
            for tf in ("H1", "H4", "D1"):
                r = resample(base, tf, kind) if tf != "H1" else base.assign(n_m1=1)[["ts_open", "o", "h", "l", "c", "v", "n_m1"]].copy()
                r["n_m1"] = (r["n_m1"] * 60).astype("int16")  # xap xi: so phut = so nen H1 * 60
                outs[tf] = r
            for tf, iv in (("M15", "15m"), ("M5", "5m")):
                y = yahoo_base(s, iv)
                if y is not None:
                    y, _ = clean_m1(y)
                    outs[tf] = y.assign(n_m1=1 * (5 if tf == "M5" else 15))[["ts_open", "o", "h", "l", "c", "v", "n_m1"]]
        for tf, r in outs.items():
            r = r.copy()
            r["n_m1"] = r["n_m1"].astype("int16")
            r["split"] = label_split(r["ts_open"], sp)
            p = OUT / "bars" / f"{s}_{tf}.parquet"
            r.to_parquet(p, index=False)
            mins = {"M1": 1, **{k: v[1] for k, v in TFS.items()}}[tf]
            manifest["files"].append({
                "symbol": s, "tf": tf, "source": mode[s], "from": r.ts_open.iloc[0].isoformat(),
                "to": r.ts_open.iloc[-1].isoformat(), "bars": len(r),
                "partial_bar_pct": round(float((r.n_m1 < 0.5 * mins).mean() * 100), 2),
                "missing_m1_pct": qc[s].get("missing_pct_m1"),
                "split_bars": {k: int(v) for k, v in r.split.value_counts().items()},
                "session": "NY17:00" if kind == "fx" and tf in ("H4", "D1") else "UTC", "sha": sha(p)})
        print("built", s, mode[s], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (OUT / "qc.json").write_text(json.dumps(qc, indent=1))


if __name__ == "__main__":
    main()
