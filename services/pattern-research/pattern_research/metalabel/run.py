"""C1 meta-labeling. Chay: nice python -m pattern_research.metalabel.run [--out DIR]
Chi doc wf_oos_trades.parquet (dev+val, lenh walk-forward) + nen dev (< TEST_START). KHONG mo tap TEST."""
from __future__ import annotations

import argparse
import json
import os
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest import bootstrap_ci, deflated_sharpe, max_drawdown, pbo_cscv
from .. import bt_run
from .cv import kfold_blocks, purged_masks, wf_chunks
from .features import FEATURES, bar_features, trade_features

warnings.filterwarnings("ignore")
EMBARGO = pd.Timedelta(days=5)
QS = (0.5, 0.25, 0.10)             # ti le lenh giu lai (xep hang theo diem mo hinh trong tung khoi)
MODELS = ("logit", "gbm")
SEED = 11


def load_trades() -> pd.DataFrame:
    tr = pd.read_parquet(bt_run.OUT / "wf_oos_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr["entry_ts"])
    tr["exit_ts"] = pd.to_datetime(tr["exit_ts"])
    assert tr["entry_ts"].max() < bt_run.TEST_START and tr["exit_ts"].max() < bt_run.TEST_START + EMBARGO * 0 + pd.Timedelta(days=1), "co lenh cham tap TEST"
    return tr.sort_values("entry_ts").reset_index(drop=True)


def build_features(tr: pd.DataFrame) -> pd.DataFrame:
    series = {s["src"] + ":" + s["symbol"] + ":" + s["tf"]: s for s in bt_run.series_list()}
    parts = []
    for key, g in tr.groupby("key"):
        x = dict(series[key])
        x["path"] = str(bt_run.DATA / x["path"].removeprefix("/data/"))     # manifest ghi duong dan trong container
        df = bt_run.load_df(x, "dev")                # mode dev: cat nen >= TEST_START, khong ghi test_access
        assert (df.ts_open.iloc[g["entry_i"].to_numpy()].to_numpy() == g["entry_ts"].to_numpy()).all(), key
        parts.append(trade_features(g, bar_features(df, x["tf"]), x["tf"], x["symbol"]))
    return pd.concat(parts).loc[tr.index]


def make_model(name: str):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if name == "logit":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.05, max_iter=300))
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=100, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, n_jobs=2, random_state=SEED, verbose=-1)


def fit_predict(name, Xtr, ytr, Xte):
    m = make_model(name)
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, s)) if len(set(y)) > 1 else float("nan")


def oof_kfold(tr, X, y, k=8):
    """Purged K-fold + embargo: diem OOF cho moi lenh."""
    out = {m: np.full(len(tr), np.nan) for m in MODELS}
    for lo, hi in kfold_blocks(tr["entry_ts"], k):
        trm, tem = purged_masks(tr["entry_ts"], tr["exit_ts"], lo, hi, EMBARGO)
        for m in MODELS:
            out[m][tem.to_numpy()] = fit_predict(m, X[trm], y[trm], X[tem])
    return out


def oof_wf(tr, X, y, chunks, min_train=400):
    """Walk-forward: khoi danh gia = nam; train = lenh DA DONG truoc (khoi - embargo). Tra diem + chi so khoi."""
    out = {m: np.full(len(tr), np.nan) for m in MODELS}
    cid = np.full(len(tr), -1)
    for ci, (lo, hi, name) in enumerate(chunks):
        te = ((tr["entry_ts"] >= lo) & (tr["entry_ts"] < hi)).to_numpy()
        trm = (tr["exit_ts"] < lo - EMBARGO).to_numpy()
        if te.sum() < 20 or trm.sum() < min_train:
            continue
        cid[te] = ci
        for m in MODELS:
            out[m][te] = fit_predict(m, X[trm], y[trm], X[te])
    return out, cid


def select(score, cid, q):
    """Chon top-q theo diem TRONG tung khoi (khong dung nhan)."""
    sel = np.zeros(len(score), bool)
    for c in np.unique(cid[cid >= 0]):
        idx = np.where(cid == c)[0]
        k = max(1, int(round(q * len(idx))))
        sel[idx[np.argsort(-score[idx])[:k]]] = True
    return sel


def perm_null(r, cid, q, n=2000, seed=SEED):
    rng = np.random.default_rng(seed)
    groups = [np.where(cid == c)[0] for c in np.unique(cid[cid >= 0])]
    ks = [max(1, int(round(q * len(g)))) for g in groups]
    res = np.empty(n)
    for i in range(n):
        res[i] = np.concatenate([rng.choice(g, k, replace=False) for g, k in zip(groups, ks)]).size and \
            np.mean(np.concatenate([r[rng.choice(g, k, replace=False)] for g, k in zip(groups, ks)]))
    return res


def stat(r, rg=None):
    r = np.asarray(r, float)
    lo, hi = bootstrap_ci(r) if len(r) > 5 else (float("nan"),) * 2
    d = {"n": int(len(r)), "exp_r": round(float(r.mean()), 4), "ci95": [round(lo, 4), round(hi, 4)],
         "win": round(float((r > 0).mean()), 4), "sum_r": round(float(r.sum()), 1),
         "pf": round(float(r[r > 0].sum() / -r[r <= 0].sum()), 3) if (r <= 0).any() and r[r <= 0].sum() < 0 else None,
         "maxdd_r": round(max_drawdown(r), 1)}
    if rg is not None:
        d["exp_r_gross"] = round(float(np.mean(rg)), 4)
    return d


def svg_bars(rows, path, title):
    """rows: [(nhan, gia_tri, lo, hi, mau)] -> SVG ngang don gian."""
    W, H, L = 640, 40 + 26 * len(rows), 210
    vals = [v for _, v, lo, hi, _ in rows] + [lo for *_, lo, hi, _ in rows] + [hi for *_, hi, _ in rows]
    mn, mx = min(vals + [0]) - 0.03, max(vals + [0]) + 0.03
    X = lambda v: L + (v - mn) / (mx - mn) * (W - L - 20)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#fff"/><text x="8" y="18" font-weight="bold">{title}</text>',
         f'<line x1="{X(0):.1f}" y1="26" x2="{X(0):.1f}" y2="{H - 6}" stroke="#444" stroke-dasharray="3"/>']
    for i, (lab, v, lo, hi, col) in enumerate(rows):
        y = 40 + 26 * i
        s.append(f'<text x="8" y="{y + 12}">{lab}</text>')
        s.append(f'<rect x="{min(X(0), X(v)):.1f}" y="{y}" width="{abs(X(v) - X(0)):.1f}" height="16" fill="{col}"/>')
        s.append(f'<line x1="{X(lo):.1f}" y1="{y + 8}" x2="{X(hi):.1f}" y2="{y + 8}" stroke="#000"/>')
        s.append(f'<text x="{W - 4}" y="{y + 12}" text-anchor="end">{v:+.3f}</text>')
    s.append("</svg>")
    Path(path).write_text("\n".join(s))


def svg_curves(curves, path, title):
    W, H, L, B = 640, 280, 46, 24
    allv = np.concatenate([c for _, c, _ in curves])
    mn, mx = min(allv.min(), 0), allv.max()
    n = max(len(c) for _, c, _ in curves)
    X = lambda i, m: L + i / max(m - 1, 1) * (W - L - 10)
    Y = lambda v: 28 + (mx - v) / (mx - mn + 1e-9) * (H - 28 - B)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#fff"/><text x="8" y="16" font-weight="bold">{title}</text>',
         f'<line x1="{L}" y1="{Y(0):.1f}" x2="{W - 10}" y2="{Y(0):.1f}" stroke="#999"/>',
         f'<text x="4" y="{Y(mx) + 4:.0f}">{mx:.0f}</text><text x="4" y="{Y(mn) + 4:.0f}">{mn:.0f}</text>']
    for k, (lab, c, col) in enumerate(curves):
        pts = " ".join(f"{X(i, len(c)):.1f},{Y(v):.1f}" for i, v in enumerate(c[:: max(1, len(c) // 300)]))
        s.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.6" points="{pts}"/>')
        s.append(f'<text x="{L + 8 + 190 * k}" y="{H - 6}" fill="{col}">{lab}</text>')
    s.append("</svg>")
    Path(path).write_text("\n".join(s))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/trading-system/docs/research/meta_labeling")
    ap.add_argument("--perm", type=int, default=2000)
    a = ap.parse_args(argv)
    t0 = time.time()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tr = load_trades()
    X = build_features(tr)
    Xv = X.to_numpy(float)
    y = (tr["r"] > 0).to_numpy().astype(int)
    r = tr["r"].to_numpy()
    rg = tr["r_gross"].to_numpy()
    cost = rg - r
    res = {"generated": time.strftime("%F %T"), "n_trades": int(len(tr)), "features": FEATURES, "base_win": round(float(y.mean()), 4),
           "base": stat(r, rg), "test_locked": "KHONG mo (chi dung wf_oos_trades dev+val + nen < TEST_START)"}
    # --- 1) Purged K-fold (OOF, khong phai OOS thuan: train co du lieu tuong lai cua khoi)
    oof = oof_kfold(tr, Xv, y)
    cv = {}
    for m in MODELS:
        cv[m] = {"auc": round(auc(y, oof[m]), 4)}
        for q in QS:
            sel = select(oof[m], np.zeros(len(tr), int), q)
            cv[m][f"top{int(q * 100)}"] = stat(r[sel], rg[sel])
    res["purged_kfold"] = cv
    # --- 2) Walk-forward ngoai mau
    chunks = wf_chunks(2012, bt_run.VAL_START, bt_run.TEST_START)
    sc, cid = oof_wf(tr, Xv, y, chunks)
    ev = cid >= 0
    res["wf_eval_n"] = int(ev.sum())
    res["wf_all"] = stat(r[ev], rg[ev])
    res["wf_chunks"] = [c[2] for c in chunks]
    wf, cfg_R, nulls = {}, {}, {}
    rng = np.random.default_rng(SEED)
    for m in MODELS:
        wf[m] = {"auc": round(auc(y[ev], sc[m][ev]), 4)}
        lo_, hi_ = [], []
        for _ in range(300):                       # CI bootstrap AUC
            b = rng.integers(0, ev.sum(), ev.sum())
            lo_.append(auc(y[ev][b], sc[m][ev][b]))
        wf[m]["auc_ci95"] = [round(float(np.nanpercentile(lo_, 2.5)), 4), round(float(np.nanpercentile(lo_, 97.5)), 4)]
        for q in QS:
            sel = select(sc[m], cid, q)
            d = stat(r[sel], rg[sel])
            d["exp_r_cost_x2"] = round(float((r[sel] - cost[sel]).mean()), 4)
            nl = perm_null(r, cid, q, a.perm)
            d["random_same_size_mean"] = round(float(nl.mean()), 4)
            d["p_vs_random"] = round(float((np.sum(nl >= r[sel].mean()) + 1) / (len(nl) + 1)), 4)
            d["dsr"] = deflated_sharpe(r[sel], len(MODELS) * len(QS))
            d["by_chunk"] = {chunks[c][2]: round(float(r[sel & (cid == c)].mean()), 3) for c in np.unique(cid[ev]) if (sel & (cid == c)).any()}
            wf[m][f"top{int(q * 100)}"] = d
            cfg_R[(m, q)] = (sel, d)
    res["walk_forward"] = wf
    # --- 3) PBO (CSCV) tren cau hinh model x q, khoi = quy
    qtr = tr["entry_ts"].dt.to_period("Q").astype(str).to_numpy()
    uq = sorted(set(qtr[ev]))
    M = np.full((len(uq), len(cfg_R)), np.nan)
    for j, (k, (sel, _)) in enumerate(cfg_R.items()):
        for i, u in enumerate(uq):
            mk = sel & (qtr == u)
            if mk.any():
                M[i, j] = r[mk].mean()
    M[np.isnan(M)] = 0.0
    res["pbo"] = pbo_cscv(M, 16)
    res["n_trials"] = len(cfg_R)
    # --- 4) Theo val rieng (khoi VAL trong WF)
    vi = [i for i, c in enumerate(chunks) if c[2] == "VAL"][0]
    res["val_only"] = {"all": stat(r[cid == vi], rg[cid == vi])}
    for (m, q), (sel, _) in cfg_R.items():
        mk = sel & (cid == vi)
        res["val_only"][f"{m}_top{int(q * 100)}"] = stat(r[mk], rg[mk]) if mk.sum() > 5 else {"n": int(mk.sum())}
    # --- 5) Do quan trong dac trung (GBM tren toan bo, chi mo ta)
    g = make_model("gbm")
    g.fit(Xv, y)
    imp = sorted(zip(FEATURES, g.booster_.feature_importance("gain")), key=lambda t: -t[1])[:8]
    tot = sum(v for _, v in imp) or 1
    res["gbm_importance_top8_in_sample"] = {k: round(float(v / tot), 3) for k, v in imp}
    # --- ve hinh
    rows = [("Lay tat ca (WF 2012+)", res["wf_all"]["exp_r"], *res["wf_all"]["ci95"], "#888")]
    for m in MODELS:
        for q in QS:
            d = wf[m][f"top{int(q * 100)}"]
            rows.append((f"{m} top{int(q * 100)}%", d["exp_r"], *d["ci95"], "#2a7" if d["exp_r"] > 0 else "#c44"))
    svg_bars(rows, out / "exp_r.svg", "R trung binh/lenh sau chi phi, walk-forward 2012+ (thanh = CI95)")
    order = np.where(ev)[0]
    curves = [("Lay tat ca", np.cumsum(r[order]), "#888")]
    for (m, q), col in (((("logit", 0.5)), "#c70"), ((("gbm", 0.25)), "#27c")):
        curves.append((f"{m} top{int(q * 100)}%", np.cumsum(r[select(sc[m], cid, q)]), col))
    svg_curves(curves, out / "equity.svg", "Tong R tich luy (theo thu tu lenh; moi duong dung so lenh khac nhau)")
    res["runtime_s"] = round(time.time() - t0, 1)
    (out / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("base", "wf_all", "pbo")}, ensure_ascii=False))
    for m in MODELS:
        print(m, wf[m]["auc"], {q: (wf[m][q]["exp_r"], wf[m][q]["p_vs_random"], wf[m][q]["n"]) for q in wf[m] if q.startswith("top")})


if __name__ == "__main__":
    main()
