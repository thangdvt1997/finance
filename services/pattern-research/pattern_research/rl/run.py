"""Walk-forward RL prototype. python -m pattern_research.rl.run [out.json]
Mo rong cua so train -> du doan khoi val ke tiep (3 khoi); chi dung split train/val."""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

from . import algos
from .env import load_dev, make_features, simulate

SYMS = ["EURUSD", "XAUUSD", "US500"]
SEEDS = list(range(10))
EMBARGO = pd.Timedelta(days=5)
NBLK = 3
HPY = 24 * 252


def sharpe(r):  # Sharpe theo nen (H1) -> thuong nien
    s = r.std()
    return float(r.mean() / s * np.sqrt(HPY)) if s > 0 else 0.0


def dsr(r, n_trials, sr_var):
    """Deflated Sharpe (Bailey-Lopez de Prado): xac suat SR that > nguong ky vong cua max n_trials thu."""
    T = len(r); sr = r.mean() / (r.std() + 1e-18)
    g3, g4 = stats.skew(r), stats.kurtosis(r, fisher=False)
    emc = 0.5772156649
    sr0 = np.sqrt(sr_var) * ((1 - emc) * stats.norm.ppf(1 - 1 / n_trials) + emc * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    den = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    return float(stats.norm.cdf((sr - sr0) * np.sqrt(T - 1) / den))


def main(out):
    t0 = time.time(); res = {"symbols": {}, "cfg": {"seeds": len(SEEDS), "blocks": NBLK}}
    for sym in SYMS:
        df = load_dev(sym); df.attrs["symbol"] = sym
        X, nxt, cost = make_features(df)
        idx = df.index; val = np.where(df.split.to_numpy() == "val")[0]
        cuts = np.array_split(val, NBLK)
        rec = {"bars": len(df), "val_bars": len(val), "val_from": str(idx[val[0]]), "val_to": str(idx[val[-1]]), "runs": []}
        # nen so sanh (cung cac khoi val, cung chi phi)
        oos_idx = np.concatenate(cuts)
        bh = nxt[oos_idx] - 0  # mua giu, 1 lan vao
        bh = bh.copy(); bh[0] -= cost[oos_idx[0]]
        rec["buy_hold"] = {"sharpe": sharpe(bh), "ret_pct": float(bh.sum() * 100)}
        rnd = []
        for s in range(200):
            rg = np.random.default_rng(1000 + s)
            pos = np.concatenate([rg.choice([0, 1, -1], len(c)) for c in cuts]).astype(float)
            r = np.concatenate([simulate(pos[o:o + len(c)], nxt[c], cost[c]) for o, c in
                                zip(np.cumsum([0] + [len(c) for c in cuts[:-1]]), cuts)])
            rnd.append((sharpe(r), float(r.sum() * 100)))
        rec["random"] = {"sharpe_mean": float(np.mean([a for a, _ in rnd])), "sharpe_p95": float(np.percentile([a for a, _ in rnd], 95)),
                         "ret_mean_pct": float(np.mean([b for _, b in rnd]))}
        for name, fit, act in (("ES", algos.es_fit, algos.es_act), ("Q", algos.q_fit, algos.q_act)):
            for seed in SEEDS:
                parts, insamp, turn = [], [], 0.0
                for c in cuts:
                    cut_t = idx[c[0]] - EMBARGO
                    tr = np.where(idx < cut_t)[0]
                    m = fit(X[tr], nxt[tr], cost[tr], seed)
                    pin = act(m, X[tr]); insamp.append(simulate(pin, nxt[tr], cost[tr]))
                    pos = act(m, X[c]); parts.append(simulate(pos, nxt[c], cost[c]))
                    turn += float(np.abs(np.diff(pos)).sum())
                r = np.concatenate(parts)
                rec["runs"].append({"algo": name, "seed": seed, "sharpe": sharpe(r), "ret_pct": float(r.sum() * 100),
                                    "is_sharpe": sharpe(insamp[-1]), "turnover_per_bar": turn / len(r), "r": r.tolist()})
        res["symbols"][sym] = rec
        print(sym, "done", round(time.time() - t0), "s", flush=True)
    runs = [(s, x) for s, v in res["symbols"].items() for x in v["runs"]]
    n_trials = len(runs)
    sr_h = np.array([np.mean(x["r"]) / (np.std(x["r"]) + 1e-18) for _, x in runs])
    res["n_trials"] = n_trials
    for s, v in res["symbols"].items():
        for algo in ("ES", "Q"):
            rr = [x for x in v["runs"] if x["algo"] == algo]
            sh = np.array([x["sharpe"] for x in rr]); rt = np.array([x["ret_pct"] for x in rr])
            v[algo] = {"sharpe_mean": float(sh.mean()), "sharpe_median": float(np.median(sh)), "sharpe_min": float(sh.min()),
                       "sharpe_max": float(sh.max()), "ret_mean_pct": float(rt.mean()), "n_pos": int((sh > 0).sum()),
                       "is_sharpe_mean": float(np.mean([x["is_sharpe"] for x in rr])),
                       "turn_mean": float(np.mean([x["turnover_per_bar"] for x in rr])),
                       "dsr_median": float(np.median([dsr(np.array(x["r"]), n_trials, sr_h.var()) for x in rr])),
                       "frac_beat_bh": float(np.mean(sh > v["buy_hold"]["sharpe"])), "frac_beat_rnd_p95": float(np.mean(sh > v["random"]["sharpe_p95"]))}
        for x in v["runs"]:
            x.pop("r")
    json.dump(res, open(out, "w"), indent=1)
    print("xong", round(time.time() - t0), "s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rl_result.json")
