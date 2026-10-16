"""Hien vat backtest Kich ban Sell: SO LENH day du + HINH ANH (nen den, cung phong cach pattern-render) + goi nho cho repo.

    python -m pattern_research.bt_artifacts ledger     # so lenh (dev/val/test) + checksum; KHONG chay lai detect/test
    python -m pattern_research.bt_artifacts charts     # bieu do (a)-(g), baseline ngau nhien tai dung seed
    python -m pattern_research.bt_artifacts examples   # (h) 20 thang + 20 thua + 10 te nhat moi KB
    python -m pattern_research.bt_artifacts golden     # (i) 3 anh golden so voi anh mau plan1/
    python -m pattern_research.bt_artifacts package    # ban nho (<=150KB/anh) -> docs/research/pattern_sell/

QUAN TRONG - tap TEST khoa: ledger doc LAI test_trades.parquet (da luu luc mo test 15:07) + bar dong bang trong snapshot de bo sung
cot (spread, slip, MAE, MFE...). KHONG chay lai phat hien/danh gia de chon lai; chi kiem tra tai dung (simulate_sell cung tham so
da dang ky) khop sai so 1e-9 va tong khop test_report.json (n, exp_r). Ket qua: $PATTERN_DATA/backtest/final/{ledger,charts,examples}.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import bt_run as B
from .backtest import deflated_sharpe, p_value_vs_random, random_baseline, simulate_sell, slip_comm

OUT = B.OUT / "final"
LEDGER, CHARTS, EXAMPLES = OUT / "ledger", OUT / "charts", OUT / "examples"
COLS = ["id", "kb", "symbol", "tf", "signal_time", "entry_time", "entry_price", "sl", "tp", "exit_time", "exit_price", "exit_reason",
        "spread", "slip", "R_gross", "R_net", "mae_r", "mfe_r", "bars_held", "score", "split", "params_hash", "snapshot_sha"]
EXTRA = ["fold", "tp_r", "min_score", "setup_id", "risk", "comm"]     # cot bo sung (khong gom ten nguon du lieu)
SPLIT_ORDER = ["dev", "val", "test"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def params_hash(tp_r: float, min_score: float) -> str:
    s = json.dumps({"tp_r": float(tp_r), "min_score": float(min_score), "max_hold": B.MAX_HOLD, "overrides": {}}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:12]


@lru_cache(maxsize=8)
def _bars(k: str, mode: str):
    x = next(x for x in B.series_list() if B.key(x) == k)
    return x, B.to_bars(x, B.load_df(x, mode))


def enrich(tr: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, int]:
    """Them spread/slip/MAE/MFE/bars_held tu bar dong bang; kiem tra tai dung R (tra ve so lenh lech)."""
    rows, bad = [], 0
    for k, g in tr.groupby("key", sort=True):
        x, b = _bars(k, mode)
        for t in g.itertuples():
            e, j = int(t.entry_i), int(t.exit_i)
            assert b.ts[e] == np.datetime64(t.entry_ts), f"lech chi so nen {k} {t.entry_ts}"
            assert b.ts[j] == np.datetime64(t.exit_ts), f"lech nen thoat {k} {t.exit_ts}"
            risk = t.sl - t.entry
            sp = b.spread[e:j + 1]
            mae = float((b.h[e:j + 1] + sp).max() - t.entry) / risk
            mfe = float(t.entry - (b.l[e:j + 1] + sp).min()) / risk
            slip, comm = slip_comm(x["symbol"], b.o[e])
            tpr = float(t.tp_r_used)
            re = simulate_sell(b, e, float(t.sl), tpr, B.MAX_HOLD)
            if re is None or abs(re.r - t.r) > 1e-9 or abs(re.r_gross - t.r_gross) > 1e-9 or re.exit_i != j or re.outcome != t.outcome:
                bad += 1
            rows.append({"idx": t.Index, "signal_time": b.ts[int(t.sig_i)], "spread": float(b.spread[e]), "slip": float(slip),
                         "comm": float(comm), "mae_r": round(mae, 4), "mfe_r": round(mfe, 4), "bars_held": j - e + 1,
                         "risk": float(risk)})
    return tr.join(pd.DataFrame(rows).set_index("idx")), bad


def cmd_ledger() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    LEDGER.mkdir(exist_ok=True)
    manifest = B.SNAP / "manifest.json"
    snap_sha = sha256_file(manifest)
    wf = json.loads((B.OUT / "wf_report.json").read_text())
    tf_ = json.loads((B.OUT / "test_report.json").read_text())
    ms_by_fold = {f["fold"]: f["chosen"]["min_score"] for f in wf["folds"]}
    ptest = tf_["params"]
    test_p = B.OUT / "test_trades.parquet"
    sha_test_before = sha256_file(test_p)
    dev = pd.read_parquet(B.OUT / "wf_oos_trades.parquet").reset_index(drop=True)
    dev["min_score"] = dev.fold.map(ms_by_fold)
    dev["split"] = np.where(dev.fold == "VAL", "val", "dev")
    te = pd.read_parquet(test_p).reset_index(drop=True)
    te = te.assign(fold="TEST", tp_r_used=ptest["tp_r"], min_score=ptest["min_score"], split="test")
    assert len(te) == tf_["n_trades"] == 433, len(te)
    log = []
    parts = []
    for name, df, mode in (("dev+val", dev, "dev"), ("test", te, "final")):
        e, bad = enrich(df, mode)
        log.append(f"{name}: {len(e)} lenh, tai dung R lech {bad}")
        assert bad == 0, f"{name}: {bad} lenh khong tai dung duoc"
        parts.append(e)
    al = pd.concat(parts, ignore_index=True)
    al = al.sort_values(["split", "entry_ts", "key", "sig_i"], key=lambda s: s.map({v: i for i, v in enumerate(SPLIT_ORDER)}) if s.name == "split" else s).reset_index(drop=True)
    al["id"] = [f"{s[0].upper()}{i:06d}" for s, i in zip(al.split, al.groupby("split").cumcount() + 1)]
    ph = {(float(a), float(b)): params_hash(a, b) for a, b in set(zip(al.tp_r_used, al.min_score))}
    out = pd.DataFrame({
        "id": al.id, "kb": al.pattern, "symbol": al.symbol, "tf": al.tf, "signal_time": al.signal_time, "entry_time": al.entry_ts,
        "entry_price": al.entry, "sl": al.sl, "tp": al.tp, "exit_time": al.exit_ts, "exit_price": al.exit, "exit_reason": al.outcome,
        "spread": al.spread, "slip": al.slip, "R_gross": al.r_gross.round(6), "R_net": al.r.round(6), "mae_r": al.mae_r, "mfe_r": al.mfe_r,
        "bars_held": al.bars_held, "score": al.score, "split": al.split,
        "params_hash": [ph[(float(a), float(b))] for a, b in zip(al.tp_r_used, al.min_score)], "snapshot_sha": snap_sha,
        "fold": al.fold, "tp_r": al.tp_r_used, "min_score": al.min_score, "setup_id": al.setup_id, "risk": al.risk, "comm": al.comm})
    # khop tong da bao cao
    t = out[out.split == "test"]
    assert abs(t.R_net.mean() - tf_["test"]["pooled"]["exp_r"]) < 6e-5, (t.R_net.mean(), tf_["test"]["pooled"]["exp_r"])
    d = out[out.split != "test"]
    assert len(d) == wf["oos"]["pooled"]["n"], (len(d), wf["oos"]["pooled"]["n"])
    assert abs(d.R_net.mean() - wf["oos"]["pooled"]["exp_r"]) < 6e-5
    sums = []
    for sp in SPLIT_ORDER:
        f = LEDGER / f"ledger_{sp}.csv.gz"
        if sp == "test" and f.exists():
            sys.exit("ledger_test.csv.gz da ton tai va bi khoa (khong sua sau khi mo)")
        out[out.split == sp].to_csv(f, index=False, compression={"method": "gzip", "mtime": 0})
        sums.append(f)
    out.to_csv(LEDGER / "ledger_all.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    out.to_parquet(LEDGER / "ledger_all.parquet")
    sums += [LEDGER / "ledger_all.csv.gz", LEDGER / "ledger_all.parquet"]
    (LEDGER / "SHA256SUMS").write_text("".join(f"{sha256_file(f)}  {f.name}\n" for f in sums))
    os.chmod(LEDGER / "ledger_test.csv.gz", 0o444)
    sha_test_after = sha256_file(test_p)
    assert sha_test_before == sha_test_after
    info = {"generated": time.strftime("%F %T"), "snapshot_manifest_sha256": snap_sha, "test_trades_parquet_sha256": sha_test_after,
            "n_by_split": out.split.value_counts().to_dict(), "checks": log,
            "test": {"n": int(len(t)), "exp_r": round(float(t.R_net.mean()), 4)},
            "dev_val": {"n": int(len(d)), "exp_r": round(float(d.R_net.mean()), 4)}}
    (LEDGER / "ledger_info.json").write_text(json.dumps(info, indent=1))
    B.log_test_access("bt_artifacts ledger: TAI TAO cot bo sung (spread/slip/MAE/MFE) cho 433 lenh test tu test_trades.parquet "
                      f"(sha256 {sha_test_after[:16]}, khong doi) + bar snapshot (manifest {snap_sha[:16]}); KHONG chay lai detect/test; "
                      f"tai dung R khop 1e-9, n=433, exp_r={t.R_net.mean():.4f}")
    print(json.dumps(info, indent=1))


# ------------------------------------------------------------------------------------------------ bieu do
BG, FG, GRID_C = "#000000", "#e8e8e8", "#303030"
PAL = ["#00e5ff", "#ffd400", "#ff5a5a", "#7CFC00", "#ff9f1c", "#c77dff", "#4dabf7", "#f783ac", "#a9e34b", "#66d9e8", "#ffa94d", "#b197fc"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": FG, "axes.labelcolor": FG,
                         "xtick.color": FG, "ytick.color": FG, "axes.edgecolor": "#666", "grid.color": GRID_C, "axes.grid": True,
                         "legend.facecolor": "#101010", "legend.edgecolor": "#444", "font.size": 10})
    return plt


def save_png(fig, path: Path, max_kb: int = 150, dpi: int = 110) -> None:
    from PIL import Image
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    _plt().close(fig)
    im = Image.open(buf).convert("RGB")
    im.save(path, optimize=True)
    if path.stat().st_size > max_kb * 1024:           # luong tu hoa bang mau de nen manh hon
        im.quantize(64, dither=Image.Dither.NONE).save(path, optimize=True)
    if path.stat().st_size > max_kb * 1024:
        w, h = im.size
        im.resize((int(w * .8), int(h * .8)), Image.LANCZOS).quantize(48).save(path, optimize=True)


def load_ledger() -> pd.DataFrame:
    d = pd.read_parquet(LEDGER / "ledger_all.parquet")
    for c in ("entry_time", "exit_time", "signal_time"):
        d[c] = pd.to_datetime(d[c])
    return d.sort_values("entry_time").reset_index(drop=True)


def _equity(ax, d: pd.DataFrame, by: str | None, title: str, top: int = 12) -> None:
    ax.set_title(title)
    if by is None:
        r = d.sort_values("entry_time")
        ax.plot(r.entry_time, r.R_net.cumsum(), color=PAL[0], lw=1.2, label=f"tổng (n={len(r)})")
    else:
        for i, (k, g) in enumerate(sorted(d.groupby(by), key=lambda kv: -len(kv[1]))[:top]):
            g = g.sort_values("entry_time")
            ax.plot(g.entry_time, g.R_net.cumsum(), color=PAL[i % len(PAL)], lw=1.0, label=f"{k} (n={len(g)}, {g.R_net.sum():+.0f}R)")
    for t0, c in ((B.VAL_START, "#888"), (B.TEST_START, "#ff5a5a")):
        ax.axvline(t0, color=c, ls="--", lw=.8)
    ax.axhline(0, color="#666", lw=.6)
    ax.set_ylabel("R tích luỹ (net)")
    ax.legend(fontsize=8, loc="best")


def _heat(ax, d: pd.DataFrame, row: str, title: str) -> None:
    tfs = [t for t in ("M5", "M15", "H1", "H4", "D1") if t in set(d.tf)]
    rows = sorted(d[row].unique())
    z = np.full((len(rows), len(tfs)), np.nan)
    n = np.zeros_like(z)
    for i, r in enumerate(rows):
        for j, t in enumerate(tfs):
            g = d[(d[row] == r) & (d.tf == t)]
            n[i, j] = len(g)
            if len(g) >= 5:
                z[i, j] = g.R_net.mean()
    im = ax.imshow(z, cmap="RdYlGn", vmin=-0.6, vmax=0.6, aspect="auto")
    ax.set_xticks(range(len(tfs)), tfs)
    ax.set_yticks(range(len(rows)), rows)
    ax.grid(False)
    for i in range(len(rows)):
        for j in range(len(tfs)):
            if n[i, j]:
                ax.text(j, i, "n=%d\n%s" % (n[i, j], "" if np.isnan(z[i, j]) else f"{z[i, j]:+.2f}"), ha="center", va="center", fontsize=8, color="#000" if not np.isnan(z[i, j]) else "#999")
    ax.set_title(title + " — kỳ vọng R/lệnh (ô n<5 để trống)")
    return im


def baseline_worker(args):
    x, mode, groups = args
    b = B.to_bars(x, B.load_df(x, mode))
    out = []
    for tp, lo_ts, hi_ts, sl_atr in groups:
        lo = int(np.searchsorted(b.ts, np.datetime64(lo_ts)))
        hi = int(np.searchsorted(b.ts, np.datetime64(hi_ts))) + 1
        out.append(random_baseline(b, np.asarray(sl_atr), lo, max(hi, lo + 2), float(tp), B.MAX_HOLD, B.N_SEEDS, seed=zlib.crc32(B.key(x).encode())))
    return out


def baseline_means(tr: pd.DataFrame, mode: str, workers: int = 12) -> tuple[np.ndarray, float, float]:
    """Tai dung DUNG cach evaluate(): trung binh R ngau nhien (300 seed) gop moi chuoi."""
    xs = {B.key(x): x for x in B.series_list()}
    jobs = []
    for k, g in tr.groupby("key"):
        jobs.append((xs[k], mode, [(tp, gg.entry_ts.min(), gg.entry_ts.max(), gg.sl_atr.to_numpy()) for tp, gg in g.groupby("tp_r_used")]))
    jobs.sort(key=lambda j: -len(j[2]))
    parts = []
    with ProcessPoolExecutor(workers) as ex:
        for r in ex.map(baseline_worker, jobs):
            parts += r
    rm = np.concatenate(parts, axis=1)
    means = np.nanmean(rm, axis=1)
    p, mu = p_value_vs_random(float(tr.r.mean()), rm)
    return means, p, mu


def cmd_charts(workers: int = 12) -> None:
    plt = _plt()
    CHARTS.mkdir(parents=True, exist_ok=True)
    d = load_ledger()
    d["year"] = d.entry_time.dt.year
    wf = json.loads((B.OUT / "wf_report.json").read_text())
    tj = json.loads((B.OUT / "test_report.json").read_text())

    def fig_(w=12, h=6, **kw):
        return plt.subplots(figsize=(w, h), **kw)

    f, ax = fig_()
    _equity(ax, d, None, "Đường vốn tích luỹ theo R — tổng (walk-forward ngoài mẫu + VAL + TEST khoá)")
    save_png(f, CHARTS / "a1_equity_total.png")
    for col, name, ttl in (("kb", "a2_equity_by_kb", "theo kịch bản"), ("tf", "a3_equity_by_tf", "theo khung"), ("symbol", "a4_equity_by_symbol", "theo mã")):
        f, ax = fig_()
        _equity(ax, d, col, f"Đường vốn tích luỹ theo R — {ttl}")
        save_png(f, CHARTS / f"{name}.png")
    # (b) drawdown
    f, ax = fig_(12, 5)
    for sp, c in (("dev+val", PAL[0]),):
        eq = d.R_net.cumsum()
        dd = eq.cummax().clip(lower=0) - eq
        ax.fill_between(d.entry_time, -dd, color="#ff5a5a", alpha=.5)
        ax.plot(d.entry_time, -dd, color="#ff5a5a", lw=.8)
    for t0, c in ((B.VAL_START, "#888"), (B.TEST_START, "#ffd400")):
        ax.axvline(t0, color=c, ls="--", lw=.8)
    ax.set_title(f"Drawdown (R) — tối đa {dd.max():.0f}R; vạch vàng = bắt đầu TEST khoá")
    ax.set_ylabel("R dưới đỉnh vốn")
    save_png(f, CHARTS / "b_drawdown.png")
    # (c) phan phoi R, MAE/MFE
    f, axs = plt.subplots(1, 3, figsize=(15, 4.8))
    for sp, c in (("dev", PAL[0]), ("val", PAL[1]), ("test", PAL[2])):
        axs[0].hist(d[d.split == sp].R_net.clip(-3, 4), bins=np.arange(-3, 4.05, .1), color=c, alpha=.55, density=True, label=f"{sp} (n={(d.split == sp).sum()})")
    axs[0].set_title("Phân phối R net (cắt −3..4)")
    axs[0].legend()
    axs[1].hist(d.mae_r.clip(0, 3), bins=60, color=PAL[2])
    axs[1].set_title("MAE (R, bất lợi tối đa)")
    axs[2].hist(d.mfe_r.clip(0, 5), bins=60, color=PAL[3])
    axs[2].set_title("MFE (R, thuận lợi tối đa)")
    save_png(f, CHARTS / "c_dist_r_mae_mfe.png")
    # (d) heatmap
    f, ax = fig_(9, 5)
    im = _heat(ax, d, "kb", "KB × khung")
    f.colorbar(im, ax=ax)
    save_png(f, CHARTS / "d1_heat_kb_tf.png")
    f, ax = fig_(10, 6.5)
    im = _heat(ax, d, "symbol", "Mã × khung")
    f.colorbar(im, ax=ax)
    save_png(f, CHARTS / "d2_heat_symbol_tf.png")
    # (e) theo nam, phien
    f, axs = plt.subplots(1, 2, figsize=(15, 5))
    y = d.groupby("year").R_net.agg(["mean", "size"])
    axs[0].bar(y.index, y["mean"], color=np.where(y["mean"] > 0, PAL[3], PAL[2]))
    for xx, (m, n) in y.iterrows():
        axs[0].text(xx, m, f"{int(n)}", ha="center", va="bottom" if m > 0 else "top", fontsize=7)
    axs[0].set_title("Kỳ vọng R/lệnh theo năm (số = n lệnh; 2026 gồm cả TEST)")
    sess = pd.cut(d.entry_time.dt.hour, [-1, 6, 12, 20, 23], labels=["Á 00-07", "Âu 07-13", "Mỹ 13-21", "khuya 21-24"])
    s = d.groupby(sess, observed=True).R_net.agg(["mean", "size"])
    axs[1].bar(range(len(s)), s["mean"], color=np.where(s["mean"] > 0, PAL[3], PAL[2]))
    axs[1].set_xticks(range(len(s)), [f"{i}\nn={int(n)}" for i, n in zip(s.index, s["size"])])
    axs[1].set_title("Kỳ vọng R/lệnh theo phiên (giờ UTC của nến vào lệnh)")
    save_png(f, CHARTS / "e_by_year_session.png")
    # (f) baseline ngau nhien
    tr_dev = pd.read_parquet(B.OUT / "wf_oos_trades.parquet")
    tr_te = pd.read_parquet(B.OUT / "test_trades.parquet").assign(tp_r_used=tj["params"]["tp_r"])
    f, axs = plt.subplots(1, 2, figsize=(14, 4.8))
    chk = []
    for ax, (nm, tr, mode, rep) in zip(axs, (("walk-forward OOS + VAL", tr_dev, "dev", wf["oos"]["pooled"]), ("TEST khoá", tr_te, "final", tj["test"]["pooled"]))):
        means, p, mu = baseline_means(tr, mode, workers)
        chk.append({"set": nm, "p": p, "p_report": rep["p_vs_random"], "random_mean": mu, "random_report": rep["random_exp_r"]})
        assert abs(p - rep["p_vs_random"]) < 1e-3 and abs(mu - rep["random_exp_r"]) < 1e-3, chk[-1]
        ax.hist(means, bins=40, color="#555")
        ax.axvline(float(tr.r.mean()), color=PAL[2], lw=2, label=f"kịch bản thật {tr.r.mean():+.3f}R")
        ax.axvline(mu, color=PAL[1], ls="--", label=f"ngẫu nhiên TB {mu:+.3f}R")
        ax.set_title(f"{nm}: n={len(tr)}, p={p:.3f}")
        ax.set_xlabel("R trung bình / lệnh trong 300 lần rút ngẫu nhiên")
        ax.legend()
    (CHARTS / "f_baseline_check.json").write_text(json.dumps(chk, indent=1))
    save_png(f, CHARTS / "f_baseline_random.png")
    # (g) PBO / DSR
    f, axs = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [1.4, 1]})
    gd = wf["grid_dev_full"]
    lab = [f"tp {g['params']['tp_r']:g}R\nscore≥{g['params']['min_score']:g}" for g in gd]
    axs[0].bar(range(len(gd)), [g["exp_r"] for g in gd], color=[PAL[3] if g["exp_r"] > 0 else PAL[2] for g in gd])
    axs[0].set_xticks(range(len(gd)), lab, fontsize=8)
    axs[0].set_title("Lưới tham số (8 cấu hình, toàn dev): kỳ vọng R/lệnh")
    ds, dt = wf["oos"]["pooled"]["deflated_sharpe"], tj["test"]["pooled"]["deflated_sharpe"]
    pbo = wf["pbo"]
    txt = (f"PBO (CSCV, 16 nhóm, {pbo['n_combos']} tổ hợp)\n  = {pbo['pbo']:.2f}   (>0.5 = chọn tham số tốt nhất trong mẫu\n  thường kém hơn trung vị ngoài mẫu)\n\n"
           f"Deflated Sharpe, {len(gd)} thử nghiệm\n  walk-forward OOS: SR/lệnh {ds['sr']}, DSR {ds['dsr']}\n  TEST khoá:        SR/lệnh {dt['sr']}, DSR {dt['dsr']}\n\n"
           "DSR gần 0 = không có bằng chứng hiệu quả\nsau khi trừ chọn lọc tham số.")
    axs[1].axis("off")
    axs[1].text(0.0, 0.95, txt, va="top", family="monospace", fontsize=10)
    save_png(f, CHARTS / "g_pbo_dsr.png")
    (CHARTS / "SHA256SUMS").write_text("".join(f"{sha256_file(p)}  {p.name}\n" for p in sorted(CHARTS.glob("*.png"))))
    print("charts:", len(list(CHARTS.glob("*.png"))), chk)


# ------------------------------------------------------------------------------------------------ (h) vi du
def _cached_loader():
    @lru_cache(maxsize=6)
    def ld(path, tf, src, symbol, mode):
        return B._orig_load_df({"path": path, "tf": tf, "src": src, "symbol": symbol}, mode)
    B._orig_load_df = B.load_df
    B.load_df = lambda x, mode: ld(x["path"], x["tf"], x["src"], x["symbol"], mode)


def pick_examples(d: pd.DataFrame, kb: str, rng) -> pd.DataFrame:
    g = d[d.kb == kb]
    worst = g.nsmallest(10, "R_net").assign(pick="te-nhat")
    rest = g.drop(worst.index)
    w = rest[rest.exit_reason == "tp"]
    lo = rest[(rest.exit_reason == "sl")]
    ws = w.iloc[rng.permutation(len(w))[:20]].assign(pick="thang")
    ls = lo.iloc[rng.permutation(len(lo))[:20]].assign(pick="thua")
    return pd.concat([ws.sort_values("entry_time"), ls.sort_values("entry_time"), worst])


def cmd_examples() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    _cached_loader()
    d = load_ledger()
    sigs = B.load_signals("final")
    xs = {}
    for x in B.series_list():
        xs.setdefault((x["symbol"], x["tf"]), []).append(x)
    rng = np.random.default_rng(20261014)
    manifest = []
    for kb in sorted(d.kb.unique()):
        sel = pick_examples(d, kb, rng)
        for _, r in sel.iterrows():
            # tim lai chuoi + tin hieu theo setup_id (khop bar_ts) de lay points chuan cua engine
            k = None
            for x in xs[(r.symbol, r.tf)]:
                sg = next((s for s in sigs.get(B.key(x), {"signals": []})["signals"] if s["setup_id"] == r.setup_id and s["pattern"] == kb), None)
                if sg:
                    k = x
                    break
            if k is None:
                print("khong thay tin hieu", r.id)
                continue
            df = B.load_df(k, "final")
            ent = np.searchsorted(df.ts_open.to_numpy(), np.datetime64(r.entry_time))
            ex = np.searchsorted(df.ts_open.to_numpy(), np.datetime64(r.exit_time))
            t = pd.Series({"sig_i": sg["i"], "exit_i": ex, "entry": r.entry_price, "sl": r.sl, "tp": r.tp, "exit": r.exit_price,
                           "outcome": r.exit_reason, "r": r.R_net, "pattern": kb, "symbol": r.symbol, "tf": r.tf, "entry_i": ent})
            fn = f"{kb}_{r.pick}_{r.id}_{r.symbol}_{r.tf}.png"
            try:
                B._render(k, "final", t, sg, EXAMPLES / fn)
            except Exception as e:  # noqa: BLE001
                print("loi ve", r.id, type(e).__name__, str(e)[:120])
                continue
            manifest.append({"file": fn, "id": r.id, "kb": kb, "pick": r.pick, "split": r.split, "symbol": r.symbol, "tf": r.tf,
                             "entry_time": str(r.entry_time), "R_net": float(r.R_net), "exit_reason": r.exit_reason, "n_points": len(sg.get("points") or [])})
    (EXAMPLES / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("examples:", len(manifest), pd.DataFrame(manifest).groupby(["kb", "pick"]).size().to_dict())


# ------------------------------------------------------------------------------------------------ (i) golden
GOLD = [("KB-2", "golden-kb-2-202610020000", "image1.png", "Mau 1 - nem (KB-2)"),
        ("KB-1", "golden-kb-1-202610051130", "image2.png", "Mau 2 - hoi vuot dinh (KB-1)"),
        ("KB-3", "golden-kb-3-202609272345", "image3.png", "Mau 3 - vai-dau-vai (KB-3)")]


def cmd_golden(ref_dir: str, ex_dir: str) -> None:
    from PIL import Image, ImageDraw
    CHARTS.mkdir(parents=True, exist_ok=True)
    for kb, name, ref, cap in GOLD:
        a = Image.open(Path(ref_dir) / ref).convert("RGB")
        b = Image.open(Path(ex_dir) / f"{name}.png").convert("RGB")
        h = 700
        a = a.resize((int(a.width * h / a.height), h), Image.LANCZOS)
        b = b.resize((int(b.width * h / b.height), h), Image.LANCZOS)
        W = a.width + b.width + 30
        im = Image.new("RGB", (W, h + 50), (0, 0, 0))
        im.paste(a, (10, 40))
        im.paste(b, (a.width + 20, 40))
        dr = ImageDraw.Draw(im)
        dr.text((12, 12), f"{cap}: user sample image (left)", fill=(255, 255, 255))
        dr.text((a.width + 22, 12), "engine render from points (right)", fill=(255, 212, 0))
        fn = CHARTS / f"i_golden_{kb.lower()}.png"
        im.save(fn, optimize=True)
        if fn.stat().st_size > 150 * 1024:
            im.quantize(128).save(fn, optimize=True)
        print(fn, fn.stat().st_size // 1024, "KB")


# ------------------------------------------------------------------------------------------------ goi nho cho repo
def cmd_package(repo: str, per_kb: tuple[int, int, int] = (4, 4, 3)) -> None:
    dst = Path(repo) / "docs/research/pattern_sell"
    (dst / "charts").mkdir(parents=True, exist_ok=True)
    (dst / "examples").mkdir(exist_ok=True)
    (dst / "ledger").mkdir(exist_ok=True)
    for p in sorted(CHARTS.glob("*.png")):
        assert p.stat().st_size <= 150 * 1024, p
        shutil.copy2(p, dst / "charts" / p.name)
    man = json.loads((EXAMPLES / "manifest.json").read_text())
    n = 0
    for kb in sorted({m["kb"] for m in man}):
        for pick, k in zip(("thang", "thua", "te-nhat"), per_kb):
            for m in [m for m in man if m["kb"] == kb and m["pick"] == pick][:k]:
                shutil.copy2(EXAMPLES / m["file"], dst / "examples" / m["file"])
                n += 1
    d = load_ledger()
    g = d.groupby(["split", "kb", "tf", "symbol"]).R_net.agg(n="size", exp_r="mean", sum_r="sum", win=lambda s: (s > 0).mean()).round(4).reset_index()
    g.to_csv(dst / "ledger/ledger_summary.csv", index=False)
    shutil.copy2(LEDGER / "ledger_test.csv.gz", dst / "ledger/ledger_test.csv.gz")
    shutil.copy2(LEDGER / "SHA256SUMS", dst / "ledger/SHA256SUMS")
    shutil.copy2(LEDGER / "ledger_info.json", dst / "ledger/ledger_info.json")
    tot = sum(p.stat().st_size for p in (dst).rglob("*") if p.is_file())
    print("package:", n, "vi du,", len(list((dst / "charts").glob("*.png"))), "bieu do,", tot // 1024, "KB ->", dst)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ledger", "charts", "examples", "golden", "package"])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--ref-dir", default="/ref")
    ap.add_argument("--ex-dir", default="/ex")
    ap.add_argument("--repo", default="/repo")
    a = ap.parse_args(argv)
    {"ledger": cmd_ledger, "charts": lambda: cmd_charts(a.workers), "examples": cmd_examples,
     "golden": lambda: cmd_golden(a.ref_dir, a.ex_dir), "package": lambda: cmd_package(a.repo)}[a.cmd]()


if __name__ == "__main__":
    main()
