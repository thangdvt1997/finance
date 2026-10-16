"""Kiem tra tin hieu momentum THUAN (khong chi phi, khong rang buoc khop lenh): IC xep hang + chenh lech top-N vs universe theo thang, nhieu lookback/universe/giai doan."""
import json, numpy as np, pandas as pd
from scipy import stats
from vn_common import *
from vn_engine import *
from vn_strats import *
df = load_raw(); P = Panel(df)
me = period_ends(P.dates, "M", START)
nxt = np.r_[me[1:], P.T - 1]
LAG = 3     # vao lenh tre 3 phien (T+2 + dat lenh) de gan thuc te
out = {}
def fwd(i, i2, lag): return P.ACf[min(i2 + lag, P.T - 1)] / P.ACf[min(i + lag, P.T - 1)] - 1
def nw_t(x, lags=3):
    x = np.asarray(x, float); m = x.mean(); e = x - m; n = len(x); v = (e @ e) / n
    for l in range(1, lags + 1): v += 2 * (1 - l / (lags + 1)) * (e[l:] @ e[:-l]) / n
    return m / np.sqrt(v / n)
for lb in [3, 6, 9, 12]:
    for sk in [0, 1]:
        S = P.mom({3: 63, 6: 126, 9: 189, 12: 252}[lb], {0: 0, 1: 21}[sk])
        for uni in [30, 100, 300]:
            ics, spr, spr_q, top_ex = [], [], [], []
            for i, i2 in zip(me, nxt):
                m = (P.rank_tv[i] <= uni) & np.isfinite(S[i])
                fr = fwd(i, i2, LAG)
                m &= np.isfinite(fr)
                if m.sum() < 15: continue
                s, f = S[i][m], fr[m]
                ics.append(stats.spearmanr(s, f)[0])
                o = np.argsort(-s); n15 = min(15, len(o) // 3)
                spr.append(f[o[:n15]].mean() - f.mean())
                q = max(len(o) // 5, 3); spr_q.append(f[o[:q]].mean() - f[o[-q:]].mean())
            out[f"M{lb}-{sk}|U{uni}"] = dict(n=len(ics), IC=float(np.mean(ics)), IC_t=float(nw_t(ics)), top15_minus_univ_mo=float(np.mean(spr)), t_top=float(nw_t(spr)),
                                             Q1_minus_Q5_mo=float(np.mean(spr_q)), t_q=float(nw_t(spr_q)))
# giai doan (12-1, U100)
S = P.mom(252, 21); per = {}
for nm, (a, b) in {"2014-17": ("2014-01-01", "2017-12-31"), "2018-19": ("2018-01-01", "2019-12-31"), "2020": ("2020-01-01", "2020-12-31"), "2021": ("2021-01-01", "2021-12-31"),
                   "2022": ("2022-01-01", "2022-12-31"), "2023-26": ("2023-01-01", "2026-12-31")}.items():
    ics, spr = [], []
    for i, i2 in zip(me, nxt):
        if not (pd.Timestamp(a) <= P.dates[i] <= pd.Timestamp(b)): continue
        m = (P.rank_tv[i] <= 100) & np.isfinite(S[i]); fr = fwd(i, i2, LAG); m &= np.isfinite(fr)
        if m.sum() < 15: continue
        ics.append(stats.spearmanr(S[i][m], fr[m])[0]); o = np.argsort(-S[i][m]); spr.append(fr[m][o[:15]].mean() - fr[m].mean())
    per[nm] = dict(n=len(ics), IC=float(np.mean(ics)) if ics else np.nan, top15_minus_univ_mo=float(np.mean(spr)) if spr else np.nan)
out["periods_M12-1_U100"] = per
json.dump(out, open(OUT / "vn_signal_test.json", "w"), indent=1)
for k, v in out.items():
    if k.startswith("M"): print(k, {a: round(b, 4) for a, b in v.items()})
print(per)
