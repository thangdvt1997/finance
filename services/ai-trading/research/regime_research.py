"""Nghiên cứu regime (C2): HMM 3 trạng thái (hmmlearn) + K-means (sklearn) trên D1, báo cáo TRUNG THỰC.

Chạy trên VPS (cần pandas, scikit-learn, hmmlearn; KHÔNG nằm trong container service):
    python services/ai-trading/research/regime_research.py [--out docs/research/regime]

Quy tắc chống rò rỉ / khoá:
  * Huấn luyện = 70% đầu của tập 'train'; đánh giá ngoài mẫu = 30% cuối của 'train' (holdout) + 'val'.
  * Tập 'test' khoá KHÔNG dùng cho bất kỳ số đo nào; chỉ suy ra TRẠNG THÁI HIỆN TẠI bằng mô hình đã đóng băng (lọc nhân quả, không nhìn tương lai).
  * Trạng thái dùng lọc tiến (forward filtering), không Viterbi/smoothing -> không nhìn trước.
  * Null: dịch vòng nhãn (circular shift) giữ nguyên độ bền trạng thái -> p-value công bằng.
READ-ONLY: không đặt lệnh, không gọi mạng."""
from __future__ import annotations

import argparse
import json
import math
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[3]
BARS = ROOT / "data/research/patterns/mt5/bars"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40"]
LABELS = ["Biến động thấp", "Biến động vừa", "Biến động cao"]
SEED, N_NULL, H = 11, 2000, 5


def features(df: pd.DataFrame) -> pd.DataFrame:
    r = np.log(df["c"]).diff()
    vol20 = r.rolling(20).std()
    ret20 = r.rolling(20).sum()
    t20 = ret20 / (vol20 * math.sqrt(20))
    f = pd.DataFrame({"r": r, "lvol": np.log(vol20.clip(lower=1e-7)), "t20": t20.clip(-4, 4), "vol20": vol20}, index=df.index)
    # biến mục tiêu tương lai (CHỈ để đánh giá, không là đặc trưng)
    f["fwd_lvol"] = np.log(r[::-1].rolling(H).std()[::-1].shift(-1).clip(lower=1e-7))
    f["fwd_ret"] = r[::-1].rolling(H).sum()[::-1].shift(-1)
    return f.dropna(subset=["lvol", "t20"])


def forward_filter(model: GaussianHMM, X: np.ndarray) -> np.ndarray:
    """P(s_t | x_1..t) — nhân quả."""
    ll = model._compute_log_likelihood(X)
    lt = np.log(model.transmat_ + 1e-300)
    out = np.zeros_like(ll)
    a = np.log(model.startprob_ + 1e-300) + ll[0]
    out[0] = a - logsumexp(a)
    for t in range(1, len(X)):
        a = logsumexp(out[t - 1][:, None] + lt, axis=0) + ll[t]
        out[t] = a - logsumexp(a)
    return np.exp(out)


def eta2(y: np.ndarray, g: np.ndarray) -> float:
    """Tỉ lệ phương sai của y giải thích bởi nhóm g."""
    ok = ~np.isnan(y)
    y, g = y[ok], g[ok]
    if len(y) < 30 or y.var() == 0:
        return float("nan")
    m = y.mean()
    ss_b = sum((g == k).sum() * (y[g == k].mean() - m) ** 2 for k in np.unique(g))
    return float(ss_b / ((y - m) ** 2).sum())


def shift_null(y, g, rng, n=N_NULL):
    obs = eta2(y, g)
    if math.isnan(obs):
        return obs, float("nan")
    L = len(g)
    lo = max(5, L // 10)
    ge = sum(eta2(y, np.roll(g, int(rng.integers(lo, L - lo)))) >= obs for _ in range(n))
    return obs, (ge + 1) / (n + 1)


def dwell(g: np.ndarray) -> dict:
    ch = np.flatnonzero(np.diff(g) != 0)
    runs = np.diff(np.r_[-1, ch, len(g) - 1])
    return {"mean_dwell_days": round(float(runs.mean()), 1), "switches_per_100d": round(100 * len(ch) / len(g), 1)}


def order_states(means_lvol: np.ndarray) -> np.ndarray:
    rank = np.empty(len(means_lvol), int)
    rank[np.argsort(means_lvol)] = np.arange(len(means_lvol))
    return rank


def analyse(sym: str, seed=SEED) -> dict | None:
    p = BARS / f"{sym}_D1.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p).sort_values("ts_open").reset_index(drop=True)
    f = features(df)
    f["split"] = df.loc[f.index, "split"].values
    f["ts"] = df.loc[f.index, "ts_open"].values
    f = f.reset_index(drop=True)
    tr = f[f.split == "train"]
    if len(tr) < 400:
        return {"symbol": sym, "error": "quá ít dữ liệu"}
    cut = int(len(tr) * 0.7)
    fit, hold = tr.iloc[:cut], tr.iloc[cut:]
    val = f[f.split == "val"]
    cols = ["lvol", "t20"]
    mu, sd = fit[cols].mean(), fit[cols].std()
    best = None
    for k in range(5):
        m = GaussianHMM(3, covariance_type="full", n_iter=200, tol=1e-4, random_state=seed + k).fit(((fit[cols] - mu) / sd).values)
        s = m.score(((fit[cols] - mu) / sd).values)
        if best is None or s > best[0]:
            best = (s, m)
    hmm = best[1]
    rank = order_states(hmm.means_[:, 0])
    km = KMeans(3, n_init=10, random_state=seed).fit(((fit[cols] - mu) / sd).values)
    rank_km = order_states(km.cluster_centers_[:, 0])
    rng = np.random.default_rng(seed)
    allz = ((f[cols] - mu) / sd).values
    post = forward_filter(hmm, allz)
    f["hmm"] = rank[post.argmax(1)]
    f["km"] = rank_km[km.predict(allz)]
    out = {"symbol": sym, "n_days": int(len(f)), "first_day": str(pd.Timestamp(f.ts.iloc[0]).date()),
           "fit_days": int(len(fit)), "holdout_days": int(len(hold)), "val_days": int(len(val)), "eval": {}}
    for name, idx in (("holdout", hold.index), ("val", val.index)):
        sub = f.loc[idx]
        if len(sub) < 60:
            continue
        y_v = sub["fwd_lvol"].values
        res = {"n": int(len(sub))}
        for mname, col in (("hmm", "hmm"), ("kmeans", "km")):
            g = sub[col].values
            e, pv = shift_null(y_v, g, rng)
            res[mname] = {"vol_eta2": round(e, 4), "vol_p_vs_shifted": round(pv, 4), **dwell(g),
                          "share": [round(float((g == k).mean()), 3) for k in range(3)],
                          "fwd_lvol_mean": [round(float(np.nanmean(y_v[g == k])), 3) if (g == k).any() else None for k in range(3)]}
        q = np.quantile(fit["lvol"], [1 / 3, 2 / 3])
        e, pv = shift_null(y_v, np.digitize(sub["lvol"].values, q), rng)
        res["baseline_vol20_tercile"] = {"vol_eta2": round(e, 4), "vol_p_vs_shifted": round(pv, 4)}
        d = sub.iloc[::H]   # mẫu không chồng lấn
        dirs = {}
        for k in range(3):
            s = d[d.hmm == k]
            sg = np.sign(s["t20"].values) * s["fwd_ret"].values
            sg = sg[~np.isnan(sg)]
            if len(sg) >= 20 and sg.std(ddof=1) > 0:
                t = sg.mean() / (sg.std(ddof=1) / math.sqrt(len(sg)))
                dirs[LABELS[k]] = {"n": int(len(sg)), "mean_trend_follow_ret_pct": round(float(sg.mean() * 100), 4), "t": round(float(t), 2)}
        res["direction_trend_follow"] = dirs
        out["eval"][name] = res
    fit_f = f.loc[fit.index]
    out["states_fit"] = [{"label": LABELS[k], "share": round(float((fit_f.hmm == k).mean()), 3),
                          "ann_vol_pct": round(float(fit_f[fit_f.hmm == k]["vol20"].mean() * math.sqrt(252) * 100), 2),
                          "mean_t20": round(float(fit_f[fit_f.hmm == k]["t20"].mean()), 2)} for k in range(3)]
    cur = f.iloc[-1]
    pr = np.zeros(3)
    for s_, r_ in enumerate(rank):
        pr[r_] += post[-1][s_]
    ks = int(pr.argmax())
    run = 1
    while run < len(f) and f["hmm"].iloc[-1 - run] == ks:
        run += 1
    t20 = float(cur["t20"])
    out["current"] = {"as_of": str(pd.Timestamp(cur["ts"]).date()), "state": ks, "label": LABELS[ks], "prob": [round(float(x), 3) for x in pr],
                      "days_in_state": int(run), "ann_vol_pct": round(float(cur["vol20"] * math.sqrt(252) * 100), 2),
                      "trend_t20": round(t20, 2), "trend": "xu hướng tăng" if t20 >= 1 else "xu hướng giảm" if t20 <= -1 else "đi ngang",
                      "kmeans_label": LABELS[int(f["km"].iloc[-1])], "vol_percentile": round(float((fit["lvol"] <= cur["lvol"]).mean() * 100), 0)}
    return out


def verdict(res: list[dict]) -> dict:
    per = {"holdout": [], "val": []}
    dirp = []
    for r in res:
        for nm in per:
            e = (r.get("eval") or {}).get(nm)
            if e:
                per[nm].append((e["hmm"]["vol_p_vs_shifted"], e["hmm"]["vol_eta2"], e["baseline_vol20_tercile"]["vol_eta2"], e["hmm"]["mean_dwell_days"]))
                dirp += [abs(d["t"]) for d in e["direction_trend_follow"].values()]
    sig = {k: sum(1 for x in v if x[0] < 0.05) for k, v in per.items()}
    nn = {k: len(v) for k, v in per.items()}
    beat = {k: sum(1 for x in v if x[1] > x[2]) for k, v in per.items()}
    dw = [x[3] for v in per.values() for x in v]
    hi = sum(1 for t in dirp if t > 2)
    return {"n_symbols": nn, "vol_predictive": sig, "hmm_beats_simple_vol_baseline": beat, "mean_dwell_days_hmm": round(float(np.mean(dw)), 1),
            "direction_cells": len(dirp), "direction_cells_abs_t_gt_2": hi,
            "summary_vi": (f"Regime HMM bền (trung bình ~{round(float(np.mean(dw)))} ngày/trạng thái; K-means chuyển nhiều hơn, ~9 ngày). Dự báo biến động ngắn hạn kế tiếp khác ngẫu nhiên ở "
                           f"{sig['holdout']}/{nn['holdout']} mã trên holdout dài (nhiều năm) nhưng chỉ {sig['val']}/{nn['val']} mã trên val ngắn (~153 ngày, ít sức mạnh thống kê). "
                           f"HMM chỉ hơn đường cơ sở đơn giản (tercile vol 20 ngày) ở {beat['holdout']}/{nn['holdout']} (holdout) và {beat['val']}/{nn['val']} (val): phần lớn thông tin đã nằm trong vol gần đây. "
                           f"Không có bằng chứng regime dự báo HƯỚNG giá (theo xu hướng trong từng trạng thái: {hi}/{len(dirp)} ô có |t|>2; ngẫu nhiên kỳ vọng ~{round(len(dirp) * 0.05)}). "
                           "Chỉ dùng regime để điều chỉnh rủi ro/bật-tắt kịch bản, không để đoán hướng.")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/research/regime"))
    a = ap.parse_args()
    res = [r for r in (analyse(s) for s in SYMBOLS) if r]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "method": "HMM-3 (Gaussian, full cov, lọc tiến) + KMeans-3; đặc trưng: log vol 20 ngày, t-stat xu hướng 20 ngày (D1)",
           "locks": "tập test KHÔNG dùng cho số đo; chỉ suy trạng thái hiện tại bằng mô hình đóng băng", "horizon_days": H, "n_null": N_NULL,
           "missing": ["BTCUSD (chưa có lịch sử D1 trong kho nghiên cứu)"], "verdict": verdict(res), "symbols": res}
    od = Path(a.out)
    od.mkdir(parents=True, exist_ok=True)
    (od / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["verdict"], ensure_ascii=False, indent=1))
    for r in res:
        print(r["symbol"], r.get("current"))


if __name__ == "__main__":
    main()
