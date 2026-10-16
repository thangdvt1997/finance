"""Backtest TRUNG THỰC cho kịch bản người dùng nạp (khung pattern-research): snapshot sha, walk-forward theo năm (tham số chọn chỉ bằng
lệnh ĐÃ ĐÓNG trước đầu fold), embargo, chi phí thật (spread MT5 + trượt + phí), baseline vào lệnh ngẫu nhiên, bootstrap CI, DSR (trừ số lần
thử trong họ), PBO (CSCV) và TEST KHOÁ RIÊNG mỗi kịch bản: chỉ mở khi có job final_test (người dùng xác nhận), đúng 1 lần, ghi nhật ký.
Chỉ nghiên cứu/paper — không có đường đặt lệnh."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from ai_trading.scenario_schema import grid_of
from ai_trading.scenario_store import Store, atomic_write, now
from pattern_research.backtest import (Bars, deflated_sharpe, p_value_vs_random, pbo_cscv, random_baseline, simulate_sell, summarize)

from .dsl import signal_indices, sl_price

DATA = Path(os.getenv("PATTERN_DATA", "/data/patterns"))
STATE = os.getenv("AI_STATE_DIR", "/state")
MAX_HOLD_DEFAULT = 100
MIN_IS_TRADES = 30
N_SEEDS = int(os.getenv("AI_BT_SEEDS", "100"))
BASE_CAP = 600                       # số lệnh tối đa dùng để dựng baseline ngẫu nhiên (đủ để so trung bình)
MAX_SIGNALS = 40000
MIN_TEST_TRADES = 30
# Ngày bắt đầu dùng được theo QC dữ liệu (xem bt_run.py); mã khác: mặc định 2010 (thận trọng, tránh phần nến tổng hợp thời đầu)
START = {("EURUSD", "*"): "2001-01-01", ("GBPUSD", "*"): "2001-01-01", ("USDJPY", "*"): "2001-01-01",
         ("XAUUSD", "intraday"): "2009-01-01", ("XAUUSD", "*"): "2007-01-01"}
DEFAULT_START = "2010-01-01"
FILL_MIN = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}


class JobError(Exception):
    pass


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return str(x)
    return x


def split_bounds() -> dict:
    sp = json.loads((DATA / "splits.json").read_text())
    f = lambda v: pd.Timestamp(v).tz_convert("UTC").tz_localize(None)  # noqa: E731
    return {"test": f(sp["test"][0]), "val": f(sp["val"][0]), "train_end": f(sp["train"][1])}


def start_of(sym: str, tf: str) -> pd.Timestamp:
    intr = tf in ("M1", "M5", "M15", "M30")
    s = (START.get((sym, "intraday")) if intr else None) or START.get((sym, "*")) or DEFAULT_START
    return pd.Timestamp(s)


def load_series(sym: str, tf: str, test_start: pd.Timestamp, upto_test: bool) -> pd.DataFrame | None:
    p = DATA / "mt5" / "bars" / f"{sym}_{tf}.parquet"
    if not p.is_file():
        return None
    df = pd.read_parquet(p)
    df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True).dt.tz_localize(None)
    df = df.sort_values("ts_open").drop_duplicates("ts_open")
    df = df[df.ts_open >= start_of(sym, tf)]
    if "n_m1" in df and tf in FILL_MIN:
        df = df[df.n_m1 >= 0.5 * FILL_MIN[tf]]
    if upto_test:
        df = df[df.ts_open < test_start]
    return df.reset_index(drop=True)


def df_sha(df: pd.DataFrame) -> str:
    h = pd.util.hash_pandas_object(df[["ts_open", "o", "h", "l", "c"]], index=False).to_numpy().tobytes()
    return hashlib.sha256(h).hexdigest()[:16]


def to_bars(sym: str, tf: str, df: pd.DataFrame) -> Bars:
    sp = df["spread"].to_numpy() if "spread" in df else None
    return Bars.from_arrays(sym, tf, df.ts_open.to_numpy(), df.o, df.h, df.l, df.c, sp)


class Job:
    """Ghi tiến trình job (file JSON nguyên tử) + cập nhật result.json của kịch bản."""

    def __init__(self, store: Store, jid: str):
        self.store, self.jid = store, jid
        self.j = store.job(jid) or {}

    def upd(self, **kw) -> None:
        self.j.update(kw)
        atomic_write(self.store.jdir / f"{self.jid}.json", json.dumps(clean(self.j)).encode())

    def progress(self, stage: str, frac: float, msg: str = "") -> None:
        self.upd(stage=stage, progress=round(frac, 3), message=msg or stage)


def save_result(store: Store, sid: str, key: str, value: dict) -> dict:
    d = store.path(sid)
    res = store.result(sid)
    res[key] = clean(value)
    res["verdict"] = verdict(res)
    res["updated_at"] = now()
    atomic_write(d / "result.json", json.dumps(clean(res)).encode())
    return res


def verdict(res: dict) -> str:
    te, dev = res.get("test") or {}, res.get("dev") or {}
    if te.get("status") == "done" and te.get("summary"):
        s = te["summary"]
        if s.get("n", 0) < MIN_TEST_TRADES or s.get("exp_r") is None:
            return "unproven"
        if s["exp_r"] <= 0:
            return "no_edge"
        ci, p = s.get("ci95") or [None, None], te.get("p_vs_random")
        dsr = (te.get("dsr") or {}).get("dsr")
        pbo = (dev.get("pbo") or {}).get("pbo")
        if ci[0] is not None and ci[0] > 0 and p is not None and p < 0.05 and dsr is not None and dsr >= 0.95 and (pbo is None or pbo < 0.5):
            return "edge"
        return "unproven"
    pooled = (dev.get("oos") or {}).get("pooled")
    if pooled and pooled.get("n", 0) >= MIN_TEST_TRADES and pooled.get("exp_r") is not None and pooled["exp_r"] <= 0:
        return "no_edge"
    return "unproven"


# ------------------------------------------------------------------------------------------------ mô phỏng
def detect_all(sc: dict, series: dict, job: Job | None = None, lo=0.0, hi=1.0) -> dict:
    sigs, total = {}, 0
    for n, (k, (b, _df)) in enumerate(series.items()):
        idx = signal_indices(sc, b)
        total += len(idx)
        if total > MAX_SIGNALS:
            raise JobError(f"Luật quá lỏng: > {MAX_SIGNALS} tín hiệu trên dữ liệu dev. Siết điều kiện rồi nạp lại với id mới.")
        sigs[k] = idx
        if job:
            job.progress("detect", lo + (hi - lo) * (n + 1) / len(series), f"Phát hiện {k}: {len(idx)} tín hiệu")
    return sigs


def sim_config(sc: dict, series: dict, sigs: dict, cfg: dict, zero_cost: bool = False, min_ts=None) -> pd.DataFrame:
    rows = []
    mh = sc["levels"]["max_hold"]
    for k, (b, _df) in series.items():
        last_exit = -1
        for i in sigs[k]:
            e = int(i) + 1
            if e <= last_exit or (min_ts is not None and b.ts[i] < np.datetime64(min_ts)):
                continue
            sl = sl_price(sc, b, int(i), cfg["sl_param"])
            tr = simulate_sell(b, e, sl, cfg["tp_r"], mh, zero_cost=zero_cost)
            if tr is None:
                continue
            last_exit = tr.exit_i
            rows.append({"key": k, "symbol": b.symbol, "tf": b.tf, "sig_i": int(i), "entry_i": e, "exit_i": tr.exit_i,
                         "entry_ts": b.ts[e], "exit_ts": b.ts[tr.exit_i], "r": tr.r, "r_gross": tr.r_gross, "outcome": tr.outcome,
                         "sl_atr": (sl - b.o[e]) / b.atr[e - 1], "tp_r": cfg["tp_r"]})
    df = pd.DataFrame(rows)
    if len(df):
        df["entry_ts"] = pd.to_datetime(df.entry_ts)
        df["exit_ts"] = pd.to_datetime(df.exit_ts)
    return df


def evaluate(tr: pd.DataFrame, series: dict, mh: int, n_trials: int) -> dict:
    """Thống kê gộp + baseline vào lệnh ngẫu nhiên (cùng mã/khung, cùng khoảng thời gian, cùng phân bố SL/ATR, TP, hold, chi phí)."""
    if not len(tr):
        return {"pooled": {"n": 0}}
    mats = []
    for (k, tp), g in tr.groupby(["key", "tp_r"]):
        b = series[k][0]
        lo = int(np.searchsorted(b.ts, np.datetime64(g.entry_ts.min())))
        hi = int(np.searchsorted(b.ts, np.datetime64(g.entry_ts.max()))) + 1
        sl = g.sl_atr.to_numpy()
        if len(sl) > BASE_CAP:
            sl = np.random.default_rng(1).choice(sl, BASE_CAP, replace=False)
        mats.append(random_baseline(b, sl, lo, max(hi, lo + 2), float(tp), mh, N_SEEDS, seed=zlib.crc32(k.encode())))
    allm = np.concatenate(mats, axis=1)
    pooled = summarize(tr.r.to_numpy(), tr.r_gross.to_numpy())
    p, rnd = p_value_vs_random(float(tr.r.mean()), allm)
    pooled["first"], pooled["last"] = str(tr.entry_ts.min())[:10], str(tr.entry_ts.max())[:10]
    byy = {str(y): {"n": int(len(g)), "exp_r": round(float(g.r.mean()), 4)} for y, g in tr.groupby(tr.entry_ts.dt.year)}
    return {"pooled": pooled, "p_vs_random": p, "random_exp_r": rnd, "dsr": deflated_sharpe(tr.r.to_numpy(), n_trials), "by_year": byy,
            "by_series": {k: summarize(g.r.to_numpy()) for k, g in tr.groupby("key")}, "outcomes": tr.outcome.value_counts().to_dict()}


def write_ledger(path: Path, tr: pd.DataFrame, extra_cols=()) -> None:
    cols = ["key", "symbol", "tf", "entry_ts", "exit_ts", "r", "r_gross", "outcome", "tp_r", *extra_cols]
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for _, r in tr.iterrows():
            w.writerow([round(r[c], 5) if isinstance(r[c], float) else str(r[c]) for c in cols])
    os.replace(tmp, path)


def load_all(sc: dict, upto_test: bool, bounds: dict) -> tuple[dict, dict]:
    series, info = {}, {}
    for sym in sc["symbols"]:
        for tf in sc["tfs"]:
            df = load_series(sym, tf, bounds["test"], upto_test)
            if df is None or len(df) < 500:
                info[f"{sym}:{tf}"] = {"status": "no_data", "n_bars": 0 if df is None else len(df)}
                continue
            series[f"{sym}:{tf}"] = (to_bars(sym, tf, df), df)
            info[f"{sym}:{tf}"] = {"status": "ok", "n_bars": len(df), "first": str(df.ts_open.iloc[0])[:10], "last": str(df.ts_open.iloc[-1])[:10]}
    if not series:
        raise JobError("Không có dữ liệu cho mã/khung đã chọn (kiểm tra symbols/tfs).")
    return series, info


def snapshot_sha(series: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(series):
        h.update(f"{k}:{df_sha(series[k][1])};".encode())
    return h.hexdigest()[:16]


def parse_ts(s: str) -> np.datetime64:
    return np.datetime64(pd.Timestamp(s.replace("Z", "").replace("+00:00", "")).to_datetime64())


# ------------------------------------------------------------------------------------------------ job 1: detector + golden
def run_detector_test(store: Store, job: Job, sid: str) -> None:
    sc = store.scenario(sid)
    bounds = split_bounds()
    job.progress("load", 0.05, "Nạp dữ liệu dev (không chạm tập test)")
    series, info = load_all(sc, True, bounds)
    sigs = detect_all(sc, series, job, 0.1, 0.8)
    per, years = {}, {}
    for k, idx in sigs.items():
        b = series[k][0]
        per[k] = {"n_signals": int(len(idx)), "n_bars": info[k]["n_bars"],
                  "per_1000_bars": round(1000 * len(idx) / max(1, info[k]["n_bars"]), 2),
                  "examples": [str(b.ts[i])[:16] for i in list(idx[:3]) + list(idx[-3:])]}
        for i in idx:
            years[str(b.ts[i])[:4]] = years.get(str(b.ts[i])[:4], 0) + 1
    golden = []
    for g in sc.get("golden", []):
        k = f"{g['symbol']}:{g['tf']}"
        t = parse_ts(g["bar_ts"])
        if pd.Timestamp(t) >= bounds["test"]:
            golden.append({**g, "status": "rejected", "detail": "bar_ts nằm trong vùng test khoá: không được dùng làm golden"})
            continue
        if k not in series:
            ser = load_series(g["symbol"], g["tf"], bounds["test"], True)
            if ser is None or len(ser) < 500:
                golden.append({**g, "status": "no_data", "detail": "không có dữ liệu cho mã/khung này"})
                continue
            b = to_bars(g["symbol"], g["tf"], ser)
            idx = signal_indices(sc, b)
        else:
            b, idx = series[k][0], sigs[k]
        pos = int(np.searchsorted(b.ts, t))
        if pos >= len(b.ts) or b.ts[pos] != t:
            golden.append({**g, "status": "no_data", "detail": "không có nến đúng thời điểm này"})
            continue
        near = [int(i) - pos for i in idx if abs(int(i) - pos) <= 1]
        fired = bool(near)
        ok = fired == g["expect"]
        golden.append({**g, "status": "pass" if ok else "fail", "fired": fired, "offset_bars": near[0] if near else None,
                       "detail": ("detector kích hoạt" + (f" lệch {near[0]} nến" if near and near[0] else "")) if fired else "detector không kích hoạt trong ±1 nến"})
    res = {"status": "done", "finished_at": now(), "by_series": per, "by_year": dict(sorted(years.items())), "series_info": info, "golden": golden,
           "golden_pass": sum(1 for g in golden if g["status"] == "pass"), "golden_total": len(golden),
           "dev_only": True, "note": "Chỉ chạy trên dữ liệu dev (trước ngày test khoá). Số tín hiệu KHÔNG phải bằng chứng có lãi."}
    save_result(store, sid, "detector", res)
    job.upd(status="done", stage="done", progress=1.0, finished_at=now(),
            message=f"Xong: {sum(v['n_signals'] for v in per.values())} tín hiệu dev; golden {res['golden_pass']}/{res['golden_total']} đạt.")


# ------------------------------------------------------------------------------------------------ job 4: quét ví dụ (AI Training Class)
def run_scan_examples(store: Store, job: Job, sid: str) -> None:
    """Quét lịch sử DEV (không chạm test khoá) tìm lần xuất hiện theo luật kịch bản; chọn 6-10 ví dụ rải đều theo thời gian (có hạt giống cố định
    theo job) và vẽ ảnh nến PNG. Kết quả ghi vào /state/scenarios/<sid>/scan/<job>/. Không phải bằng chứng thống kê."""
    from .candle_png import render
    sc = store.scenario(sid)
    prm = job.j.get("params") or {}
    limit = min(10, max(6, int(prm.get("limit", 8))))
    bounds = split_bounds()
    if prm.get("symbol"):
        sc = {**sc, "symbols": [s for s in sc["symbols"] if s == prm["symbol"]] or sc["symbols"]}
    if prm.get("tf"):
        sc = {**sc, "tfs": [t for t in sc["tfs"] if t == prm["tf"]] or sc["tfs"]}
    job.progress("load", 0.1, "Nạp dữ liệu dev (không chạm tập test)")
    series, info = load_all(sc, True, bounds)
    sigs = detect_all(sc, series, job, 0.15, 0.6)
    pool = [(k, int(i)) for k, idx in sigs.items() for i in idx]
    total = len(pool)
    out_dir = store.path(sid) / "scan" / job.jid
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    if pool:
        rng = np.random.default_rng(int(job.jid[:8], 16))
        pool.sort(key=lambda t: (str(series[t[0]][0].ts[t[1]]), t[0]))
        edges = np.linspace(0, len(pool), min(limit, len(pool)) + 1).astype(int)
        picks = [pool[int(rng.integers(edges[j], max(edges[j] + 1, edges[j + 1])))] for j in range(len(edges) - 1)]
        sl_vals = sc["levels"]["sl"]["values"]
        for n_i, (k, i) in enumerate(picks):
            b = series[k][0]
            lo, hi = max(0, i - 40), min(len(b.c), i + 21)
            slp = sl_price(sc, b, i, sl_vals[len(sl_vals) // 2])
            entry = float(b.o[i + 1]) if i + 1 < len(b.o) else float(b.c[i])
            png = render(b.o[lo:hi], b.h[lo:hi], b.l[lo:hi], b.c[lo:hi], i - lo, {"entry": entry, "sl": slp})
            name = f"ex{n_i + 1}.png"
            atomic_write(out_dir / name, png)
            sym, tf = k.split(":")
            items.append({"n": n_i + 1, "symbol": sym, "tf": tf, "ts": str(b.ts[i])[:16], "entry": round(entry, 6), "sl": round(slp, 6), "image": name})
            job.progress("render", 0.6 + 0.35 * (n_i + 1) / len(picks), f"Vẽ ảnh {n_i + 1}/{len(picks)}")
    res = {"status": "done", "finished_at": now(), "total_hits": total, "examples": items, "series_info": info, "dev_only": True,
           "note": "Chỉ dữ liệu dev. Số lần xuất hiện KHÔNG phải bằng chứng có lãi."}
    atomic_write(out_dir / "scan.json", json.dumps(clean(res)).encode())
    job.upd(status="done", stage="done", progress=1.0, finished_at=now(), message=f"Xong: {total} lần xuất hiện, {len(items)} ví dụ.", result_dir=f"scenarios/{sid}/scan/{job.jid}")


# ------------------------------------------------------------------------------------------------ job 2: backtest dev (walk-forward)
def folds(b: dict) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    f = [(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"), str(y)) for y in range(2008, 2025)]
    f.append((pd.Timestamp("2025-01-01"), b["train_end"], "2025H1"))
    f.append((b["val"], b["test"] - pd.Timedelta(days=5), "VAL"))
    return f


def choose(tr_by_p: dict, cutoff: pd.Timestamp, default_gi: int = 0) -> tuple[int, dict]:
    best, best_v, info = None, -1e9, {}
    for gi, df in tr_by_p.items():
        if not len(df):
            continue
        is_ = df[df.exit_ts < cutoff]                       # chỉ lệnh ĐÃ ĐÓNG trước đầu fold (embargo theo exit)
        info[gi] = (len(is_), float(is_.r.mean()) if len(is_) else None)
        if len(is_) >= MIN_IS_TRADES and is_.r.mean() > best_v:
            best, best_v = gi, float(is_.r.mean())
    return (default_gi if best is None else best), info


def family_trials(store: Store, sc: dict, grid: list) -> int:
    return max(1, len(grid) * store.family_size(sc.get("family", sc["id"])))


def run_backtest(store: Store, job: Job, sid: str) -> None:
    sc = store.scenario(sid)
    bounds = split_bounds()
    grid = grid_of(sc)
    job.progress("load", 0.03, "Nạp dữ liệu dev + chụp snapshot")
    series, info = load_all(sc, True, bounds)
    sha = snapshot_sha(series)
    sigs = detect_all(sc, series, job, 0.05, 0.3)
    tr_by_p = {}
    for gi, cfg in enumerate(grid):
        job.progress("simulate", 0.3 + 0.3 * gi / len(grid), f"Mô phỏng cấu hình {gi + 1}/{len(grid)}")
        tr_by_p[gi] = sim_config(sc, series, sigs, cfg)
    job.progress("walk-forward", 0.62, "Walk-forward theo năm")
    oos, fold_log = [], []
    for a, z, name in folds(bounds):
        gi, inf = choose(tr_by_p, a)
        df = tr_by_p[gi]
        part = df[(df.entry_ts >= a) & (df.entry_ts < z)] if len(df) else df
        fold_log.append({"fold": name, "from": str(a)[:10], "to": str(z)[:10], "chosen": grid[gi], "is_n": inf.get(gi, (0,))[0],
                         "is_exp_r": inf.get(gi, (0, None))[1], "oos_n": int(len(part)), "oos_exp_r": float(part.r.mean()) if len(part) else None})
        if len(part):
            oos.append(part.assign(fold=name))
    oos_df = pd.concat(oos) if oos else pd.DataFrame()
    final_gi, final_info = choose(tr_by_p, bounds["test"])
    ntr = family_trials(store, sc, grid)
    job.progress("evaluate", 0.75, "Baseline ngẫu nhiên + DSR + PBO")
    ev = evaluate(oos_df, series, sc["levels"]["max_hold"], ntr) if len(oos_df) else {"pooled": {"n": 0}}
    # PBO trên lưới (CSCV) theo quý
    pbo = {"pbo": None, "note": "lưới chỉ 1 cấu hình: không tính PBO"}
    cols = {gi: df.groupby(pd.Grouper(key="entry_ts", freq="QS")).r.mean() for gi, df in tr_by_p.items() if len(df)}
    if len(cols) >= 2:
        m = pd.DataFrame(cols).dropna(how="all")
        m = m[m.index >= pd.Timestamp("2008-01-01")].fillna(0.0)
        pbo = {**pbo_cscv(m.to_numpy(), 16), "blocks": int(len(m)), "configs": int(m.shape[1]), "note": "xác suất quá khớp (CSCV)"}
    gross = None
    if len(oos_df):
        gl = []
        for fl in fold_log:
            if fl["oos_n"]:
                g = sim_config(sc, series, sigs, fl["chosen"], zero_cost=True)
                a, z = pd.Timestamp(fl["from"]), pd.Timestamp(fl["to"])
                gl.append(g[(g.entry_ts >= a) & (g.entry_ts < z)])
        gg = pd.concat(gl) if gl else pd.DataFrame()
        gross = float(gg.r.mean()) if len(gg) else None
    grid_full = [{"params": grid[gi], "n": int(len(df)), "exp_r": float(df.r.mean()) if len(df) else None} for gi, df in tr_by_p.items()]
    d = store.path(sid)
    if len(oos_df):
        write_ledger(d / "ledger_dev.csv", oos_df, ("fold",))
    dev = {"status": "done", "finished_at": now(), "snapshot_sha": sha, "series_info": info, "grid": grid, "grid_dev_full": grid_full,
           "folds": fold_log, "final_params": grid[final_gi], "final_is": final_info.get(final_gi), "n_trials": ntr,
           "oos": ev, "oos_gross_exp_r": gross, "pbo": pbo, "dsr": ev.get("dsr"), "start_note": f"Dữ liệu dev: ts < {str(bounds['test'])[:10]} (test khoá không bị chạm).",
           "costs": "spread MT5 theo nến (tối thiểu theo mã) + trượt + phí; SL tính theo ASK; cùng nến chạm SL và TP -> tính SL",
           "tp_note": "Tham số (TP, SL) chọn bằng walk-forward; nếu fold chưa đủ 30 lệnh IS dùng cấu hình đầu lưới."}
    save_result(store, sid, "dev", dev)
    p = ev.get("pooled", {})
    job.upd(status="done", stage="done", progress=1.0, finished_at=now(),
            message=f"Xong walk-forward: n={p.get('n', 0)}, kỳ vọng {p.get('exp_r')} R/lệnh; test khoá CHƯA mở.")


# ------------------------------------------------------------------------------------------------ job 3: test khoá (1 lần)
def run_final_test(store: Store, job: Job, sid: str, jid: str) -> None:
    sc = store.scenario(sid)
    res = store.result(sid)
    dev = res.get("dev") or {}
    if dev.get("status") != "done":
        raise JobError("Chưa có kết quả backtest dev.")
    d = store.path(sid)
    marker = d / "test_opened.json"
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o664)    # CHỈ MỘT LẦN: trùng -> FileExistsError
    except FileExistsError:
        raise JobError("Test khoá của kịch bản này đã được mở trước đó (chỉ 1 lần).") from None
    with os.fdopen(fd, "w") as f:
        json.dump({"opened_at": now(), "job_id": jid, "params": dev["final_params"], "dev_snapshot_sha": dev.get("snapshot_sha"),
                   "confirmed_by": "master (xác nhận tường minh qua API)"}, f)
    with open(d / "test_access.log", "a") as f:
        f.write(f"{time.strftime('%F %T')} job={jid} MO TAP TEST KHOA params={json.dumps(dev['final_params'])}\n")
    try:
        bounds = split_bounds()
        job.progress("load", 0.05, "Mở test khoá: nạp dữ liệu đầy đủ")
        series, info = load_all(sc, False, bounds)
        # dữ liệu dev phải đúng như lúc chạy dev (chụp snapshot): so sha phần dev
        dev_only = {k: (b, df[df.ts_open < bounds["test"]].reset_index(drop=True)) for k, (b, df) in series.items()}
        if snapshot_sha(dev_only) != dev.get("snapshot_sha"):
            # nhật ký đã ghi; không cho đánh giá với dữ liệu dev đã đổi (kết quả dev không còn khớp)
            raise JobError("Dữ liệu dev đã thay đổi so với lúc chạy backtest dev (snapshot sha khác): không đánh giá để tránh kết quả không tái lập. Test khoá vẫn tính là đã mở.")
        sigs = detect_all(sc, series, job, 0.1, 0.4)
        cfg = dev["final_params"]
        job.progress("simulate", 0.5, "Mô phỏng 1 cấu hình đã chốt trên tập test")
        tr = sim_config(sc, series, sigs, cfg, min_ts=bounds["test"])
        tr = tr[tr.entry_ts >= bounds["test"]] if len(tr) else tr
        job.progress("evaluate", 0.8, "Baseline ngẫu nhiên + DSR")
        ev = evaluate(tr, series, sc["levels"]["max_hold"], dev.get("n_trials") or 1)
        g = sim_config(sc, series, sigs, cfg, zero_cost=True, min_ts=bounds["test"])
        g = g[g.entry_ts >= bounds["test"]] if len(g) else g
        if len(tr):
            write_ledger(d / "ledger_test.csv", tr)
        out = {"status": "done", "finished_at": now(), "params": cfg, "test_start": str(bounds["test"])[:10], "summary": ev.get("pooled"),
               "p_vs_random": ev.get("p_vs_random"), "random_exp_r": ev.get("random_exp_r"), "dsr": ev.get("dsr"), "by_series": ev.get("by_series"),
               "gross_exp_r": float(g.r.mean()) if len(g) else None, "test_sha": snapshot_sha({k: (b, df[df.ts_open >= bounds["test"]]) for k, (b, df) in series.items()}),
               "note": "Test khoá đã mở đúng 1 lần cho id này; không lặp lại. Mẫu nhỏ -> CI rộng."}
        save_result(store, sid, "test", out)
        s = ev.get("pooled", {})
        job.upd(status="done", stage="done", progress=1.0, finished_at=now(),
                message=f"Test khoá xong: n={s.get('n', 0)}, kỳ vọng {s.get('exp_r')} R/lệnh, p so với ngẫu nhiên {ev.get('p_vs_random')}.")
    except JobError as e:
        save_result(store, sid, "test", {"status": "failed", "error": str(e)[:300], "finished_at": now(), "note": "Test khoá đã bị tính là đã mở (không chạy lại)."})
        raise


def run_job(jid: str) -> int:
    store = Store(STATE)
    job = Job(store, jid)
    j = job.j
    try:
        sid, typ = j["scenario_id"], j["type"]
        sc = store.scenario(sid)
        if not sc:
            raise JobError("Không đọc được kịch bản.")
        job.upd(status="running", stage="start", started_at=now(), progress=0.01)
        {"detector_test": lambda: run_detector_test(store, job, sid), "backtest": lambda: run_backtest(store, job, sid),
         "final_test": lambda: run_final_test(store, job, sid, jid), "scan_examples": lambda: run_scan_examples(store, job, sid)}[typ]()
        return 0
    except JobError as e:
        job.upd(status="failed", stage="failed", finished_at=now(), error=str(e)[:300], message=str(e)[:300])
        return 1
    except Exception as e:  # noqa: BLE001
        job.upd(status="failed", stage="failed", finished_at=now(), error=type(e).__name__, message=f"Lỗi nội bộ: {type(e).__name__}")
        raise
