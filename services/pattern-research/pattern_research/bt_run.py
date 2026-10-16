"""Chay backtest Kich ban Sell: phat hien -> walk-forward (dev) -> TEST KHOA (1 lan) -> bao cao JSON + thu vien vi du.

    python -m pattern_research.bt_run detect  --mode dev   [--workers 12]   # chi nen ts < test_start (khong cham test)
    python -m pattern_research.bt_run wf                                     # walk-forward tren dev + chon tham so cuoi
    python -m pattern_research.bt_run detect  --mode final                   # MO TEST: ghi test_access.log
    python -m pattern_research.bt_run test                                   # danh gia test 1 lan voi tham so da chot
    python -m pattern_research.bt_run examples                               # thu vien vi du + anh PNG
Ket qua: $PATTERN_DATA/backtest/ (KHONG dua vao git). Moi tin hieu chi la nghien cuu/paper.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Bars, deflated_sharpe, p_value_vs_random, pbo_cscv, random_baseline, simulate_sell, summarize

DATA = Path(os.environ.get("PATTERN_DATA", "/root/trading-system/data/research/patterns"))
OUT = DATA / "backtest"
SPLITS = json.loads((DATA / "splits.json").read_text())
TEST_START = pd.Timestamp(SPLITS["test"][0]).tz_convert("UTC").tz_localize(None)
VAL_START = pd.Timestamp(SPLITS["val"][0]).tz_convert("UTC").tz_localize(None)
TRAIN_END = pd.Timestamp(SPLITS["train"][1]).tz_convert("UTC").tz_localize(None)

GRID = [{"tp_r": t, "min_score": s} for t in (1.0, 1.5, 2.0, 3.0) for s in (0.0, 80.0)]
DEFAULT = {"tp_r": 2.0, "min_score": 0.0}
MAX_HOLD = 100          # nen; co dinh, KHONG toi uu (tranh them bac tu do)
MIN_IS_TRADES = 30
N_SEEDS = 300


SNAP = OUT / "snapshot"
# Ngay bat dau dung duoc theo QC (docs/handoff/MT5_status.md): FX MT5 truoc 2001 la nen tong hop/thua; vang 2004-2008 thua o M1-M30.
START = {("mt5", "EURUSD"): "2001-01-01", ("mt5", "GBPUSD"): "2001-01-01", ("mt5", "USDJPY"): "2001-01-01",
         ("mt5", "XAUUSD", "intraday"): "2009-01-01", ("mt5", "XAUUSD"): "2007-01-01"}


FILL_MIN = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}     # so phut M1 mong doi / nen (D1 bo qua: phien FX/chi so < 1440 phut)


def start_of(x: dict):
    intr = x["tf"] in ("M1", "M5", "M15", "M30")
    s = START.get((x["src"], x["symbol"], "intraday")) if intr else None
    s = s or START.get((x["src"], x["symbol"]))
    return pd.Timestamp(s) if s else None


def series_list() -> list[dict]:
    """Dung ban CHUP (snapshot) neu da co -> du lieu dong bang trong suot dev + test (MT5 dang duoc nhap lai)."""
    if (SNAP / "manifest.json").exists():
        return json.loads((SNAP / "manifest.json").read_text())["series"]
    return source_series()


def cmd_snapshot() -> None:
    import hashlib
    import shutil
    if (SNAP / "manifest.json").exists():
        sys.exit("snapshot da ton tai - khong ghi de (xoa thu cong neu that su can)")
    SNAP.mkdir(parents=True, exist_ok=True)
    out = []
    for x in source_series():
        dst = SNAP / f"{x['src']}_{x['symbol']}_{x['tf']}.parquet"
        shutil.copy2(x["path"], dst)
        y = {**x, "orig_path": x["path"], "path": str(dst),
             "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()[:16]}
        out.append(y)
        print(key(y), y["sha256"], flush=True)
    (SNAP / "manifest.json").write_text(json.dumps({"created": time.strftime("%F %T"), "series": out}, indent=1))


def source_series() -> list[dict]:
    """(nguon, symbol, tf, duong dan). MT5 (gia CFD broker, co spread) uu tien hon proxy Yahoo cung symbol."""
    out = []
    mt5 = DATA / "mt5" / "bars"
    mt5_syms = sorted({p.name.rsplit("_", 1)[0] for p in mt5.glob("*_M15.parquet")}) if mt5.is_dir() else []
    for s in mt5_syms:
        for tf in ("M5", "M15", "H1", "H4", "D1"):
            p = mt5 / f"{s}_{tf}.parquet"
            if p.exists():
                out.append({"src": "mt5", "symbol": s, "tf": tf, "path": str(p)})
    for s in ("BTCUSD", "ETHUSD"):
        for tf in ("M5", "M15", "H1", "H4", "D1"):
            out.append({"src": "binance", "symbol": s, "tf": tf, "path": str(DATA / "bars" / f"{s}_{tf}.parquet")})
    for s in ("EURUSD", "GBPUSD", "USDJPY", "US500", "XAUUSD"):          # proxy Yahoo chi khi chua co MT5
        if s in mt5_syms:
            continue
        for tf in ("M5", "M15", "H1", "H4", "D1"):
            out.append({"src": "yahoo", "symbol": s, "tf": tf, "path": str(DATA / "bars" / f"{s}_{tf}.parquet")})
    for s in ("US500_SPY", "XAUUSD_GC"):
        out.append({"src": "yahoo_d1", "symbol": s, "tf": "D1", "path": str(DATA / "bars" / f"{s}_D1.parquet")})
    return [x for x in out if Path(x["path"]).exists()]


def key(x: dict) -> str:
    return f"{x['src']}:{x['symbol']}:{x['tf']}"


def log_test_access(what: str) -> None:
    with open(DATA / "test_access.log", "a") as f:
        try:
            who = getpass.getuser()
        except (KeyError, OSError):          # container chay --user uid khong co trong /etc/passwd
            who = f"uid{os.getuid()}"
        f.write(f"{time.strftime('%F %T')} {who} {what}\n")


def load_df(x: dict, mode: str) -> pd.DataFrame:
    df = pd.read_parquet(x["path"], columns=None)
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True).dt.tz_localize(None)
    df = df.sort_values("ts_open").drop_duplicates("ts_open").reset_index(drop=True)
    st = start_of(x)
    if st is not None:
        df = df[df.ts_open >= st].reset_index(drop=True)
    if "n_m1" in df and x["tf"] in FILL_MIN:      # QC: bo nen thieu du lieu (< 50% so phut M1 mong doi)
        df = df[df.n_m1 >= 0.5 * FILL_MIN[x["tf"]]].reset_index(drop=True)
    if mode.startswith("dev"):
        df = df[df.ts_open < TEST_START].reset_index(drop=True)
    return df


def to_bars(x: dict, df: pd.DataFrame, zero_cost: bool = False) -> Bars:
    sp = df["spread"].to_numpy() if (x["src"] == "mt5" and "spread" in df) else None
    return Bars.from_arrays(x["symbol"], x["tf"], df.ts_open.to_numpy(), df.o, df.h, df.l, df.c, sp, zero_cost)


# ------------------------------------------------------------------------------------------------ phat hien
def _detect_one(args) -> dict:
    x, mode, overrides = args
    from pattern_engine.detector import Detector
    from pattern_engine.series import Bar
    from pattern_engine.specs import load_specs
    t0 = time.time()
    df = load_df(x, mode)
    if len(df) < 200:
        return {"key": key(x), "n_bars": len(df), "signals": [], "counts": {}, "sec": 0}
    det = Detector(x["symbol"], x["tf"], load_specs(overrides=overrides))
    sigs, counts = [], {}
    idx_of = {}
    ts = df.ts_open.dt.to_pydatetime()
    for i, (t, o, h, l, c) in enumerate(zip(ts, df.o.to_numpy(), df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy())):
        t = t.replace(tzinfo=__import__("datetime").timezone.utc)
        idx_of[t] = i
        for s in det.feed(Bar(t, float(o), float(h), float(l), float(c))):
            counts[f"{s.pattern}:{s.state}"] = counts.get(f"{s.pattern}:{s.state}", 0) + 1
            if s.state == "triggered":
                sigs.append({"pattern": s.pattern, "i": i, "bar_ts": s.bar_ts.isoformat(), "score": s.score,
                             "setup_id": s.setup_id, "levels": {k: float(v) for k, v in s.levels.items()},
                             "steps": [{"id": st["id"], "ok": st["ok"], "detail": st["detail"]} for st in s.steps],
                             "points": list(getattr(s, "points", []) or [])})
    return {"key": key(x), "n_bars": len(df), "first": str(df.ts_open.iloc[0]), "last": str(df.ts_open.iloc[-1]),
            "signals": sigs, "counts": counts, "sec": round(time.time() - t0, 1)}


def cmd_detect(mode: str, workers: int, only: str | None, tag: str = "", overrides: dict | None = None,
               tfs: str | None = None) -> None:
    sl = series_list()
    if only:
        sl = [x for x in sl if only in key(x)]
    if tfs:
        sl = [x for x in sl if x["tf"] in tfs.split(",")]
    if mode == "final":
        log_test_access("bt_run detect final (MO TAP TEST): " + ",".join(key(x) for x in sl))
    if tag:
        if mode != "dev":
            sys.exit("--tag chi dung cho dev (do nhay tham so)")
        mode = f"dev_{tag}"
    d = OUT / mode / "signals"
    d.mkdir(parents=True, exist_ok=True)
    (OUT / mode / "overrides.json").write_text(json.dumps(overrides or {}))
    sl.sort(key=lambda x: -Path(x["path"]).stat().st_size)
    with ProcessPoolExecutor(workers) as ex:
        for r in ex.map(_detect_one, [(x, mode, overrides) for x in sl]):
            (d / (r["key"].replace(":", "_") + ".json")).write_text(json.dumps(r))
            print(r["key"], r["n_bars"], "bars", len(r["signals"]), "trig", r["sec"], "s", flush=True)


# ------------------------------------------------------------------------------------------------ mo phong
def trades_for(x: dict, b: Bars, sigs: list[dict], p: dict, zero_cost: bool = False) -> list[dict]:
    out = []
    for s in sigs:
        if s["score"] < p["min_score"]:
            continue
        e = s["i"] + 1
        tr = simulate_sell(b, e, s["levels"]["sl"], p["tp_r"], MAX_HOLD, zero_cost=zero_cost)
        if tr is None:
            continue
        out.append({"key": key(x), "symbol": x["symbol"], "tf": x["tf"], "src": x["src"], "pattern": s["pattern"],
                     "sig_i": s["i"], "entry_i": e, "exit_i": tr.exit_i, "entry_ts": str(b.ts[e]), "exit_ts": str(b.ts[tr.exit_i]),
                     "r": tr.r, "r_gross": tr.r_gross, "outcome": tr.outcome, "score": s["score"], "sl_atr": (s["levels"]["sl"] - b.o[e]) / b.atr[e - 1],
                     "entry": tr.entry, "sl": tr.sl, "tp": tr.tp, "exit": tr.exit, "setup_id": s["setup_id"]})
    return out


def load_signals(mode: str) -> dict[str, dict]:
    d = OUT / mode / "signals"
    return {json.loads(p.read_text())["key"]: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}


def all_trades(mode: str, p: dict, zero_cost: bool = False, cache: dict | None = None) -> pd.DataFrame:
    sigs = load_signals(mode)
    rows = []
    for x in series_list():
        k = key(x)
        if k not in sigs or not sigs[k]["signals"]:
            continue
        ck = (k, zero_cost)
        if cache is not None and ck in cache:
            b = cache[ck]
        else:
            b = to_bars(x, load_df(x, mode), zero_cost)
            if cache is not None:
                cache[ck] = b
        rows += trades_for(x, b, sigs[k]["signals"], p, zero_cost)
    df = pd.DataFrame(rows)
    if len(df):
        df["entry_ts"] = pd.to_datetime(df.entry_ts)
        df["exit_ts"] = pd.to_datetime(df.exit_ts)
    return df


# ------------------------------------------------------------------------------------------------ walk-forward
def folds() -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    f = [(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"), str(y)) for y in range(2008, 2025)]
    f.append((pd.Timestamp("2025-01-01"), TRAIN_END, "2025H1(train-cuoi)"))
    f.append((VAL_START, TEST_START - pd.Timedelta(days=5), "VAL"))
    return f


def choose(tr_by_p: dict[int, pd.DataFrame], cutoff: pd.Timestamp) -> tuple[int, dict]:
    """Chon tham so co R trung binh (gop moi ma/khung) cao nhat tren cac lenh DA DONG truoc cutoff (embargo theo exit)."""
    best, best_v, info = None, -1e9, {}
    for gi, df in tr_by_p.items():
        if not len(df):
            continue
        is_ = df[df.exit_ts < cutoff]
        info[gi] = (len(is_), float(is_.r.mean()) if len(is_) else None)
        if len(is_) >= MIN_IS_TRADES and is_.r.mean() > best_v:
            best, best_v = gi, float(is_.r.mean())
    if best is None:
        best = GRID.index(DEFAULT)
    return best, info


def cmd_wf() -> None:
    cache: dict = {}
    tr_by_p = {gi: all_trades("dev", p, cache=cache) for gi, p in enumerate(GRID)}
    oos = []
    fold_log = []
    for a, z, name in folds():
        gi, info = choose(tr_by_p, a)
        df = tr_by_p[gi]
        part = df[(df.entry_ts >= a) & (df.entry_ts < z)] if len(df) else df
        fold_log.append({"fold": name, "from": str(a), "to": str(z), "chosen": GRID[gi], "is_n": info.get(gi, (0,))[0],
                         "is_exp": info.get(gi, (0, None))[1], "oos_n": len(part),
                         "oos_exp": round(float(part.r.mean()), 4) if len(part) else None})
        if len(part):
            oos.append(part.assign(fold=name, tp_r_used=GRID[gi]["tp_r"]))
        print(fold_log[-1], flush=True)
    oos_df = pd.concat(oos) if oos else pd.DataFrame()
    final_gi, final_info = choose(tr_by_p, TEST_START)
    # grid toan bo dev (chi de minh bach, KHONG dung de chon)
    grid_dev = [{"params": GRID[gi], "n": int(len(df)), "exp_r": round(float(df.r.mean()), 4) if len(df) else None}
                for gi, df in tr_by_p.items()]
    rep = {"generated": time.strftime("%F %T"), "max_hold": MAX_HOLD, "grid": GRID, "folds": fold_log,
           "final_params": GRID[final_gi], "final_is": final_info.get(final_gi), "grid_dev_full": grid_dev}
    rep["oos"] = evaluate(oos_df, "dev", cache, n_trials=len(GRID)) if len(oos_df) else {}
    rep["pbo"] = _pbo(tr_by_p)
    # mo hinh gross (khong chi phi) cung tham so theo fold -> do muc chi phi an mon
    rep["oos_gross_exp_r"] = None
    if len(oos_df):
        g = []
        for name, part in oos_df.groupby("fold"):
            fl = next(f for f in fold_log if f["fold"] == name)
            gdf = all_trades("dev", fl["chosen"], zero_cost=True, cache=cache)
            a = pd.Timestamp(fl["from"]); z = pd.Timestamp(fl["to"])
            g.append(gdf[(gdf.entry_ts >= a) & (gdf.entry_ts < z)])
        gg = pd.concat(g)
        rep["oos_gross_exp_r"] = round(float(gg.r.mean()), 4) if len(gg) else None
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "wf_report.json").write_text(json.dumps(rep, indent=1, default=str))
    oos_df.to_parquet(OUT / "wf_oos_trades.parquet") if len(oos_df) else None
    print(json.dumps({"final_params": rep["final_params"], "oos_pooled": rep["oos"].get("pooled")}, default=str))


def _pbo(tr_by_p: dict[int, pd.DataFrame], block: str = "QS") -> dict:
    """PBO (CSCV) cua luoi tham so tren toan dev: R trung binh moi cau hinh theo quy (khoi thoi gian)."""
    cols = {}
    for gi, df in tr_by_p.items():
        if len(df):
            cols[gi] = df.groupby(pd.Grouper(key="entry_ts", freq=block)).r.mean()
    m = pd.DataFrame(cols).dropna(how="all")
    m = m[m.index >= pd.Timestamp("2008-01-01")].fillna(0.0)
    return {**pbo_cscv(m.to_numpy(), 16), "blocks": int(len(m)), "configs": int(m.shape[1])}


# ------------------------------------------------------------------------------------------------ danh gia (+ baseline)
def evaluate(tr: pd.DataFrame, mode: str, cache: dict, n_trials: int, params_by_trade: pd.Series | None = None,
             tp_r: float | None = None) -> dict:
    """Thong ke theo ma x khung, theo KB, gop; baseline ngau nhien cung dieu kien (theo tung ma/khung + giai doan)."""
    xs = {key(x): x for x in series_list()}
    rand_cols = []          # (pattern, mang [seeds])
    by_series = {}
    for k, g in tr.groupby("key"):
        x = xs[k]
        b = cache.get((k, False)) or to_bars(x, load_df(x, mode))
        cache[(k, False)] = b
        # baseline: cung khoang thoi gian (tu lenh dau den lenh cuoi cua nhom fold/giai doan), cung SL/ATR, cung TP & hold
        rmat_parts = []
        if "tp_r_used" not in g:
            g = g.assign(tp_r_used=tp_r)
        for fold_tp, gg in g.groupby("tp_r_used"):
            lo = int(np.searchsorted(b.ts, np.datetime64(gg.entry_ts.min())))
            hi = int(np.searchsorted(b.ts, np.datetime64(gg.entry_ts.max()))) + 1
            rm = random_baseline(b, gg.sl_atr.to_numpy(), lo, max(hi, lo + 2), float(fold_tp), MAX_HOLD, N_SEEDS,
                                 seed=zlib.crc32(k.encode()))
            rmat_parts.append((gg.pattern.to_numpy(), rm))
        pats = np.concatenate([p for p, _ in rmat_parts])
        rm = np.concatenate([m for _, m in rmat_parts], axis=1)
        rand_cols.append((pats, rm))
        s = summarize(g.r.to_numpy(), g.r_gross.to_numpy() if "r_gross" in g else None)
        s["p_vs_random"], s["random_exp_r"] = p_value_vs_random(float(g.r.mean()), rm)
        s["first"], s["last"] = str(g.entry_ts.min())[:10], str(g.entry_ts.max())[:10]
        s["by_kb"] = {pk: summarize(gp.r.to_numpy())["exp_r"] for pk, gp in g.groupby("pattern")}
        s["n_by_kb"] = {pk: int(len(gp)) for pk, gp in g.groupby("pattern")}
        by_series[k] = s
    out = {"by_series": by_series}
    allp = np.concatenate([p for p, _ in rand_cols]) if rand_cols else np.array([])
    allm = np.concatenate([m for _, m in rand_cols], axis=1) if rand_cols else np.zeros((0, 0))
    pooled = summarize(tr.r.to_numpy(), tr.r_gross.to_numpy() if "r_gross" in tr else None)
    pooled["p_vs_random"], pooled["random_exp_r"] = p_value_vs_random(float(tr.r.mean()), allm)
    pooled["deflated_sharpe"] = deflated_sharpe(tr.r.to_numpy(), n_trials)
    out["pooled"] = pooled
    out["by_kb"] = {}
    order = np.concatenate([g.pattern.to_numpy() for _, g in tr.groupby("key")])
    rr = np.concatenate([g.r.to_numpy() for _, g in tr.groupby("key")])
    for pk in sorted(set(order)):
        m = order == pk
        s = summarize(rr[m])
        s["p_vs_random"], s["random_exp_r"] = p_value_vs_random(float(rr[m].mean()), allm[:, allp == pk])
        out["by_kb"][pk] = s
    gr = lambda g: g.r_gross.to_numpy() if "r_gross" in g else None  # noqa: E731
    out["by_tf"] = {tf: summarize(g.r.to_numpy(), gr(g)) for tf, g in tr.groupby("tf")}
    out["by_symbol"] = {sy: summarize(g.r.to_numpy(), gr(g)) for sy, g in tr.groupby("symbol")}
    out["by_kb_tf"] = {f"{a}|{b}": summarize(g.r.to_numpy(), gr(g)) for (a, b), g in tr.groupby(["pattern", "tf"])}
    sess = pd.cut(pd.to_datetime(tr.entry_ts).dt.hour, [-1, 6, 12, 20, 23], labels=["A 00-07", "AU 07-13", "MY 13-21", "khuya 21-24"])
    out["by_session_utc"] = {str(k): summarize(g.r.to_numpy()) for k, g in tr.groupby(sess, observed=True)}
    out["by_year"] = {str(k): summarize(g.r.to_numpy())["exp_r"] for k, g in tr.groupby(pd.to_datetime(tr.entry_ts).dt.year)}
    out["by_outcome"] = tr.outcome.value_counts().to_dict()
    return out


SENS_TFS = ("M15", "H1", "H4", "D1")


def cmd_sens() -> None:
    """Do nhay: so tin hieu + R trung binh (dev, tham so mac dinh tp 2R) cua cac bien the tham so detector (dev_<tag>)."""
    rep = {}
    for d in sorted(OUT.glob("dev*")):
        if not (d / "signals").is_dir():
            continue
        mode = d.name
        ov = json.loads((d / "overrides.json").read_text()) if (d / "overrides.json").exists() else {}
        sig = load_signals(mode)
        keys = set(sig)
        tr = all_trades(mode, DEFAULT)
        tr = tr[tr.tf.isin(SENS_TFS)] if len(tr) else tr
        rep[mode] = {"overrides": ov, "series": len(keys), "n_signals": sum(len(v["signals"]) for k, v in sig.items() if k.split(":")[-1] in SENS_TFS),
                     "pooled": summarize(tr.r.to_numpy()) if len(tr) else {"n": 0},
                     "by_kb": {k: summarize(g.r.to_numpy()) for k, g in tr.groupby("pattern")} if len(tr) else {}}
        print(mode, rep[mode]["n_signals"], rep[mode]["pooled"].get("exp_r"), flush=True)
    (OUT / "sens_report.json").write_text(json.dumps(rep, indent=1, default=str))


def cmd_test() -> None:
    wf = json.loads((OUT / "wf_report.json").read_text())
    p = wf["final_params"]
    done = OUT / "test_report.json"
    if done.exists():
        sys.exit("TEST da chay 1 lan (test_report.json ton tai) - khong chay lai de tranh toi uu tren test.")
    log_test_access(f"bt_run test (danh gia 1 lan) params={p}")
    cache: dict = {}
    tr = all_trades("final", p, cache=cache)
    dev_part = tr[tr.entry_ts < TEST_START]
    tr = tr[tr.entry_ts >= TEST_START].copy()
    rep = {"generated": time.strftime("%F %T"), "params": p, "max_hold": MAX_HOLD, "test_start": str(TEST_START),
           "n_trades": int(len(tr))}
    # kiem tra nhan qua: tin hieu dev phai la tien to cua tin hieu final (detector khong look-ahead)
    rep["causality_check"] = _prefix_check()
    rep["test"] = evaluate(tr, "final", cache, n_trials=len(GRID), tp_r=p["tp_r"]) if len(tr) else {}
    g = all_trades("final", p, zero_cost=True, cache=cache)
    g = g[g.entry_ts >= TEST_START]
    rep["test_gross_exp_r"] = round(float(g.r.mean()), 4) if len(g) else None
    rep["dev_trades_same_params"] = int(len(dev_part))
    done.write_text(json.dumps(rep, indent=1, default=str))
    tr.to_parquet(OUT / "test_trades.parquet")
    print(json.dumps(rep["test"].get("pooled"), default=str))


def _prefix_check() -> dict:
    dev, fin = load_signals("dev"), load_signals("final")
    bad, n = [], 0
    for k, d in dev.items():
        f = fin.get(k)
        if not f:
            continue
        a = [(s["pattern"], s["bar_ts"], s["setup_id"]) for s in d["signals"]]
        bb = [(s["pattern"], s["bar_ts"], s["setup_id"]) for s in f["signals"] if pd.Timestamp(s["bar_ts"]).tz_localize(None) < TEST_START][: len(a)]
        n += 1
        if a != bb[: len(a)] or len(bb) < len(a):
            bad.append(k)
    return {"series_checked": n, "mismatch": bad}


# ------------------------------------------------------------------------------------------------ thu vien vi du
KB_NAME = {"KB-1": "hồi-vượt đỉnh-2 đỉnh giảm", "KB-2": "nêm/tam giác", "KB-3": "vai-đầu-vai", "KB-4": "tiếp diễn sau phá đáy"}
KIND_VI = {"thang": "thắng", "thua": "thua", "dien-hinh": "điển hình", "test": "giai đoạn kiểm tra khoá"}


def cmd_examples(per_kb: int = 3, render: bool = True) -> None:
    """Chon vi du moi KB (thang / thua / dien hinh tu walk-forward OOS + 1 lenh tap test neu co) -> PNG + JSON.
    Uu tien du lieu broker CFD (src mt5). Tin hieu lay tu lan detect `final` (co `points`; trung tien to voi dev)."""
    parts = []
    if (OUT / "wf_oos_trades.parquet").exists():
        parts.append(pd.read_parquet(OUT / "wf_oos_trades.parquet").assign(period="dev-oos"))
    if (OUT / "test_trades.parquet").exists():
        parts.append(pd.read_parquet(OUT / "test_trades.parquet").assign(period="test"))
    tr = pd.concat(parts, ignore_index=True)
    tr = tr[tr.src == "mt5"] if (tr.src == "mt5").any() else tr
    mode = "final" if (OUT / "final" / "signals").exists() else "dev"
    sigs = load_signals(mode)
    xs = {key(x): x for x in series_list()}
    ex_dir = OUT / "examples"
    ex_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    picks = []
    for pk, g in tr.groupby("pattern"):
        dv = g[(g.period == "dev-oos") & g.tf.isin(["M15", "H1", "H4"])]
        dv = dv if len(dv) >= 3 else g[g.period == "dev-oos"]
        rows = []
        if len(dv):
            w = dv[dv.outcome == "tp"]
            lo = dv[dv.outcome == "sl"]
            if len(w):
                rows.append(w.iloc[[rng.integers(len(w))]].assign(kind="thang"))
            if len(lo):
                rows.append(lo.iloc[[rng.integers(len(lo))]].assign(kind="thua"))
            med = dv.iloc[(dv.r - dv.r.median()).abs().argsort()[:1]]
            rows.append(med.assign(kind="dien-hinh"))
        te = g[g.period == "test"]
        if len(te):
            rows.append(te.iloc[[-1]].assign(kind="test"))
        if rows:
            picks.append(pd.concat(rows).drop_duplicates(["key", "sig_i"]).head(per_kb + 1))
    sel = pd.concat(picks)
    lines = []
    for _, t in sel.iterrows():
        sg = next(s for s in sigs[t.key]["signals"] if s["i"] == t.sig_i and s["pattern"] == t.pattern)
        bts = pd.Timestamp(sg["bar_ts"])
        ex_id = f"bt-{t.pattern.lower()}-{t.symbol.lower()}-{t.tf.lower()}-{bts.strftime('%Y%m%d%H%M')}"
        title = f"{t.pattern} · {t.symbol} {t.tf} (backtest, {KIND_VI[t.kind]} {t.r:+.2f}R)"
        note = (f"Mô phỏng lịch sử ({'tập kiểm tra khoá' if t.period == 'test' else 'ngoài mẫu walk-forward'}): "
                f"Sell ở giá mở nến sau tín hiệu, SL theo cấu trúc, TP {abs(t.entry - t.tp) / abs(t.sl - t.entry):.1f}R, "
                f"đã trừ chi phí; thoát {OUTCOME_VI.get(t.outcome, t.outcome)} sau {int(t.exit_i - t.entry_i) + 1} nến. "
                f"{KB_NAME.get(t.pattern, '')}. Không phải khuyến nghị.")
        rec = {"kind": "backtest", "pattern": t.pattern, "title": title, "symbol": t.symbol, "tf": t.tf,
               "ts": bts.isoformat(), "note": note, "period": t.period, "pick": t.kind,
               "result": {"outcome": t.outcome, "r": round(float(t.r), 3), "entry_ts": str(t.entry_ts), "exit_ts": str(t.exit_ts),
                          "entry": round(float(t.entry), 6), "sl": round(float(t.sl), 6), "tp": round(float(t.tp), 6),
                          "exit": round(float(t.exit), 6)},
               "score": sg["score"], "levels": {k: round(v, 6) for k, v in sg["levels"].items()},
               "steps": sg["steps"], "points": sg.get("points") or []}
        if render:
            try:
                _render(xs[t.key], mode, t, sg, ex_dir / f"{ex_id}.png")
            except Exception as e:  # noqa: BLE001
                print("render loi", ex_id, type(e).__name__, str(e)[:200], flush=True)
                continue
        (ex_dir / f"{ex_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        lines.append(ex_id)
    print(len(lines), "vi du ->", ex_dir, *lines, sep="\n")


OUTCOME_VI = {"tp": "chốt lời (TP)", "sl": "cắt lỗ (SL)", "time": "hết thời gian giữ", "end": "hết dữ liệu"}


def _render(x: dict, mode: str, t, sg: dict, path: Path) -> Path:
    from pattern_render import render_signal
    df = load_df(x, mode)
    i, ei = int(t.sig_i), int(t.exit_i)
    pts = sg.get("points") or []
    pos = [pd.Timestamp(p["t"]).tz_convert(None) for p in pts]
    first_i = i - 120
    if pos:
        first_i = int(np.searchsorted(df.ts_open.to_numpy(), np.datetime64(min(pos)))) - 25
    start = max(0, first_i)
    end = min(len(df), max(ei, i) + 12)
    if end - start > 450:
        start = end - 450
    w = df.iloc[start:end]
    iso = lambda k: df.ts_open.iloc[k].isoformat() + "Z"  # noqa: E731
    candles = [{"t": r.ts_open.isoformat() + "Z", "o": r.o, "h": r.h, "l": r.l, "c": r.c} for r in w.itertuples()]
    ann = {"title": {"symbol": x["symbol"].split("_")[0], "tf": x["tf"], "scenario": f"{t.pattern} SELL (backtest)",
                     "time": df.ts_open.iloc[i].strftime("%Y-%m-%d %H:%M UTC")},
           "legs": [], "labels": [], "lines": [],
           "arrows": [{"from": {"i": i - start + 3, "p": float(min(w.h.max(), df.h.iloc[i] + 0.12 * (w.h.max() - w.l.min())))},
                       "to": {"i": i - start, "p": float(df.h.iloc[i])}, "label": "SELL"}],
           "levels": [{"kind": "entry", "price": float(t.entry), "label": "Entry"}, {"kind": "sl", "price": float(t.sl), "label": "SL"},
                      {"kind": "tp", "price": float(t.tp), "label": "TP"}],
           "watermark": "backtest - mo phong, khong phai khuyen nghi"}
    ann["labels"].append({"at": {"t": iso(ei), "p": float(t.exit)}, "text": f"thoat {t.outcome} {t.r:+.2f}R"})
    on_leg = t.pattern != "KB-3"
    pl = [(p["t"], float(p["p"]), p.get("label", "")) for p in pts if pd.Timestamp(p["t"]).tz_convert(None) >= df.ts_open.iloc[start]]
    for a, b in zip(pl, pl[1:]):
        ann["legs"].append({"from": {"t": a[0], "p": a[1]}, "to": {"t": b[0], "p": b[1]}, "arrow": False,
                            **({"label": b[2]} if on_leg and b[2] else {})})
    if not on_leg:
        ann["labels"] += [{"at": {"t": a, "p": p}, "text": lb} for a, p, lb in pl if lb]
    lv = sg["levels"]
    for k in ("neckline", "support", "box_low"):
        if k in lv:
            t0 = next((a for a, _, lb in pl if lb == "(2)"), candles[0]["t"]) if k == "support" else candles[0]["t"]
            ann["lines"].append({"kind": "horizontal", "from": {"t": t0, "p": lv[k]}, "to": {"t": iso(i), "p": lv[k]},
                                 "label": {"neckline": "neckline", "support": "canh duoi", "box_low": "box"}[k]})
    render_signal(candles, ann, out_path=str(path), size=(1600, 800), max_kb=150)
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["detect", "wf", "test", "examples", "list", "sens", "snapshot"])
    ap.add_argument("--mode", default="dev", choices=["dev", "final"])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--only", default=None)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--overrides", default=None, help='JSON, vd {"common":{"lead_long_body_atr":1.5}}')
    ap.add_argument("--tfs", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for x in series_list():
            print(key(x), x["path"])
    elif a.cmd == "detect":
        cmd_detect(a.mode, a.workers, a.only, a.tag, json.loads(a.overrides) if a.overrides else None, a.tfs)
    elif a.cmd == "wf":
        cmd_wf()
    elif a.cmd == "test":
        cmd_test()
    elif a.cmd == "snapshot":
        cmd_snapshot()
    elif a.cmd == "sens":
        cmd_sens()
    elif a.cmd == "examples":
        cmd_examples(render=not a.no_render)


if __name__ == "__main__":
    main()
