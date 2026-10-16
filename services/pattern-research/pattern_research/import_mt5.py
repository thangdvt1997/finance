"""Nhap lich su nen NATIVE xuat tu terminal MT5 (script MTAgentExport) -> Parquet + manifest (cung dinh dang build.py).
Nguon NOI BO 'mt5_demo' (khong hien thi ten nguon o UI). Du lieu CHI o VPS: <OUT>/mt5/ (khong dua vao git).
Chay (container python:3.12-slim, mount du lieu + ma):  python -m pattern_research.import_mt5 SYM [SYM ...]
Dau vao : <OUT>/mt5/raw/<SYM>_<TF>.bin  (MqlRates 60 byte: time i8, o,h,l,c f8, tick_vol i8, spread i4, real_vol i8; gio SERVER dang epoch)
Dau ra  : <OUT>/mt5/bars/<SYM>_<TF>.parquet, manifest.json, qc_mt5.json, compare_native_vs_m1.json, tz_check.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(os.environ.get("PATTERN_DATA", "/root/trading-system/data/research/patterns"))
BASE = OUT / "mt5"
DT = np.dtype([("time", "<i8"), ("o", "<f8"), ("h", "<f8"), ("l", "<f8"), ("c", "<f8"),
               ("tv", "<i8"), ("spread", "<i4"), ("rv", "<i8")])
assert DT.itemsize == 60
TFMIN = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M6": 6, "M10": 10, "M12": 12, "M15": 15, "M20": 20, "M30": 30,
         "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360, "H8": 480, "H12": 720, "D1": 1440, "W1": 10080, "MN1": 43200}
TFS = list(TFMIN)
SRC = "mt5_demo"


def read_bin(p: Path) -> pd.DataFrame:
    a = np.fromfile(p, dtype=DT)
    df = pd.DataFrame(a).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    ok = (df.o > 0) & (df.h >= df.l) & (df.h >= df.o) & (df.h >= df.c) & (df.l <= df.o) & (df.l <= df.c)
    return df[ok].reset_index(drop=True)


def wall(s: pd.Series) -> pd.Series:  # epoch server -> gio "tuong" (naive)
    return pd.to_datetime(s, unit="s")


def to_utc(w: pd.Series, rule: str) -> pd.Series:
    """gio server (naive) -> UTC. rule 'us' = GMT+2 mua dong / GMT+3 mua he theo lich DST My (kieu NY-close);
    'eu' = Europe/Athens."""
    if rule == "eu":
        return w.dt.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    guess = (w - pd.Timedelta(hours=2)).dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    dst = guess.dt.tz_localize(None).sub(guess.dt.tz_convert("UTC").dt.tz_localize(None)).dt.total_seconds() > -5 * 3600
    off = pd.to_timedelta(np.where(dst, 3, 2), unit="h")
    return (w - off).dt.tz_localize("UTC")


def detect_rule(m1w: pd.Series) -> dict:
    """Chon quy tac gio dung nhat: gio New York cua nen M1 dau tien sau khoang trong >40h phai on dinh nhat qua cac tuan (DST)."""
    gap = m1w.diff().dt.total_seconds().div(3600)
    opens = m1w[gap > 40].reset_index(drop=True)
    res = {}
    for rule in ("us", "eu"):
        if len(opens) == 0:
            res[rule] = float("nan")
            continue
        ny = to_utc(opens, rule).dt.tz_convert("America/New_York")
        hm = (ny.dt.hour * 60 + ny.dt.minute)
        res[rule] = round(float((hm == hm.mode().iloc[0]).mean()), 4)  # do on dinh gio New York cua phien mo cua tuan
        res[rule + "_open_ny_hhmm"] = int(hm.mode().iloc[0])
    res["weeks"] = int(len(opens))
    res["chosen"] = "eu" if (res["eu"] == res["eu"] and res["eu"] > (res["us"] if res["us"] == res["us"] else -1)) else "us"
    return res


def floor_wall(w: pd.Series, tf: str) -> pd.Series:
    m = TFMIN[tf]
    if tf == "MN1":
        return w.dt.to_period("M").dt.start_time
    if tf == "W1":  # tuan MT5 bat dau Chu nhat 00:00 gio server
        d = w.dt.normalize()
        return d - pd.to_timedelta((d.dt.weekday + 1) % 7, unit="D")
    if m >= 1440:
        return w.dt.normalize()
    return w.dt.floor(f"{m}min")


def resample_m1(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    g = m1.groupby(floor_wall(m1["w"], tf), sort=True)
    r = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                      "tv": g.tv.sum(), "n_m1": g.o.size()})
    r.index.name = "w"
    return r.reset_index()


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def _load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def main(symbols: list[str]):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pattern_research.build import label_split
    sp = json.loads((OUT / "splits.json").read_text())
    (BASE / "bars").mkdir(parents=True, exist_ok=True)
    (BASE / "splits.json").write_text(json.dumps(sp, indent=1))
    mp, cmp_p, qc_p, tz_p = (BASE / n for n in ("manifest.json", "compare_native_vs_m1.json", "qc_mt5.json", "tz_check.json"))
    man = _load(mp, {"files": []})
    man["built_utc"] = datetime.now(timezone.utc).isoformat()
    man["source"] = SRC
    cmp, qc, tzc = _load(cmp_p, {}), _load(qc_p, {}), _load(tz_p, {})
    for sym in symbols:
        m1p = BASE / "raw" / f"{sym}_M1.bin"
        m1 = None
        if m1p.exists():
            m1 = read_bin(m1p)
            m1["w"] = wall(m1["time"])
            tzc[sym] = detect_rule(m1["w"].iloc[-300000:])  # ~1 nam gan nhat
            rule = tzc[sym]["chosen"]
        else:
            rule = next((v["chosen"] for v in tzc.values()), "us")
        # Mui gio la thuoc tinh cua SERVER (chung moi ma). MetaQuotes-Demo = EET (Europe/Athens, DST chau Au): kiem chung
        # 2026-10-14 bang dinh tick-volume luc mo cua co phieu My 9:30 NY tren US500 M1: 16:30 gio server tuan thuong,
        # 15:30 trong cac tuan lech DST My/Au (3/2025, 3/2026, cuoi 10/2025) -> server theo DST chau Au.
        # detect_rule tren FX bi thien lech: FX mo tuan o gio SERVER co dinh nen 'us' trong co ve on dinh (ao giac);
        # chi so (mo theo gio CME/NY) cho 'eu' 100%. Ghi de bang MT5_TZ_RULE=us|eu|auto.
        forced = os.environ.get("MT5_TZ_RULE", "eu")
        if forced in ("us", "eu"):
            rule = forced
        tzc.setdefault(sym, {})["applied"] = rule
        print(sym, "tz rule", rule, tzc.get(sym), flush=True)
        for tf in TFS:
            p = BASE / "raw" / f"{sym}_{tf}.bin"
            if not p.exists():
                continue
            nat = read_bin(p)
            if nat.empty:
                continue
            nat["w"] = wall(nat["time"])
            rs = resample_m1(m1, tf) if (m1 is not None and tf != "M1") else None
            out = pd.DataFrame({"ts_open": to_utc(nat["w"], rule), "o": nat.o, "h": nat.h, "l": nat.l, "c": nat.c,
                                "v": nat.tv.astype("float64"), "spread": nat.spread.astype("int32")})
            if tf == "M1":
                out["n_m1"] = 1
            elif rs is not None:
                nm = nat[["w"]].merge(rs[["w", "n_m1"]], on="w", how="left")["n_m1"]
                out["n_m1"] = nm.fillna(TFMIN[tf]).to_numpy()  # ngoai pham vi M1: gia dinh day du
            else:
                out["n_m1"] = TFMIN[tf]
            out = out.dropna(subset=["ts_open"]).reset_index(drop=True)
            out["n_m1"] = out["n_m1"].astype("int32")
            out["split"] = label_split(out["ts_open"], sp)
            q = {"rows": len(out), "from": out.ts_open.iloc[0].isoformat(), "to": out.ts_open.iloc[-1].isoformat(),
                 "dup_ts": int(out.ts_open.duplicated().sum()), "flat_pct": round(float((out.h == out.l).mean() * 100), 3),
                 "zero_vol_pct": round(float((out.v == 0).mean() * 100), 3)}
            if tf in ("M1", "M5", "M15", "H1"):
                step = out.ts_open.diff().dt.total_seconds().div(60)
                q["gaps_gt_3x_tf_non_weekend"] = int(((step > 3 * TFMIN[tf]) & (step < 40 * 60)).sum())
            qc[f"{sym}_{tf}"] = q
            if rs is not None:
                lo = m1["w"].iloc[0]
                n2 = nat[nat.w >= lo + pd.Timedelta(minutes=TFMIN[tf])].merge(rs, on="w", how="left", suffixes=("", "_r"))
                has = n2.o_r.notna()
                tol = 1e-6
                same = has & ((n2.o - n2.o_r).abs() < tol) & ((n2.h - n2.h_r).abs() < tol) & \
                    ((n2.l - n2.l_r).abs() < tol) & ((n2.c - n2.c_r).abs() < tol)
                full = has & (n2.n_m1 >= TFMIN[tf] * 0.9)
                cmp[f"{sym}_{tf}"] = {
                    "native_bars_compared": int(len(n2)), "no_m1_counterpart": int((~has).sum()),
                    "ohlc_equal": int(same.sum()), "ohlc_mismatch": int((has & ~same).sum()),
                    "mismatch_pct": round(float((has & ~same).sum() / max(has.sum(), 1) * 100), 3),
                    "mismatch_pct_full_bars": round(float((full & ~same).sum() / max(full.sum(), 1) * 100), 3),
                    "tickvol_equal_pct": round(float(((n2.tv - n2.tv_r).abs() < 1)[has].mean() * 100), 2)}
            fp = BASE / "bars" / f"{sym}_{tf}.parquet"
            out.to_parquet(fp, index=False)
            man["files"] = [f for f in man["files"] if not (f["symbol"] == sym and f["tf"] == tf)]
            man["files"].append({
                "symbol": sym, "tf": tf, "source": SRC, "from": q["from"], "to": q["to"], "bars": len(out),
                "partial_bar_pct": round(float((out.n_m1 < 0.5 * TFMIN[tf]).mean() * 100), 2), "missing_m1_pct": None,
                "split_bars": {k: int(v) for k, v in out.split.value_counts().items()},
                "session": "NY17:00" if tf in ("H4", "D1", "W1", "MN1") else "UTC", "sha": sha(fp)})
            print("built", sym, tf, len(out), q["from"][:10], flush=True)
        for pth, obj in ((mp, man), (cmp_p, cmp), (qc_p, qc), (tz_p, tzc)):
            pth.write_text(json.dumps(obj, indent=1))
        del m1


if __name__ == "__main__":
    main(sys.argv[1:])
