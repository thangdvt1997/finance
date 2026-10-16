"""Giai doan 1: chay cac cau hinh (tham so co dinh theo van lieu) + luoi do nhay, luu chuoi loi suat va bang. python run_multiasset.py"""
import sys, json, time, numpy as np, pandas as pd
from ma_engine import *
OUT.mkdir(parents=True, exist_ok=True)
t0 = time.time()
R, rf = pd.read_parquet(DATA / "excess_returns.parquet"), pd.read_parquet(DATA / "rf.parquet")["rf"]
ctx = Ctx(R, rf, CORE)
I = ctx.I
START = "1990-01-01"
trials = []          # (ten, sharpe_daily) cho Deflated Sharpe: MOI cau hinh da chay va bao cao
RET = {}


def go(name, S, count=True, **kw):
    r = run(ctx, S, start=START, **kw); net = r["net"]
    s = summarize(net, ctx, name)
    s.update(AvgGross=r["gross"].mean(), Turnover_yr=r["turnover"].mean() * ANN, CostDrag_yr=r["cost"].mean() * ANN)
    if count: trials.append((name, net.mean() / net.std()))
    return net, s, r


# ------------- E1: cau hinh chinh (pre-registered) -------------
sig = {
    "TSMOM12-1": sig_tsmom(I, 252, 21), "TSMOM-1/3/12": sig_multi(I, (21, 63, 252)), "TSMOM12": sig_tsmom(I, 252, 0),
    "MA200": sig_ma(I, 200), "MA100/200": sig_macross(I, 100, 200), "Donchian200/100": sig_donch(I, 200, 100),
}
sig["Ensemble"] = sum([sig["TSMOM12-1"], sig["TSMOM-1/3/12"], sig["MA200"], sig["Donchian200/100"]]) / 4
rows = []; runs = {}
for fq in ("M", "W"):
    for k, S in sig.items():
        nm = f"{k}|{fq}"; net, s, r = go(nm, S, freq=fq); rows.append(s); RET[nm] = net; runs[nm] = r
E1 = pd.DataFrame(rows)
rows = []
PRIMARY = "Ensemble|M"
# bien the thuc thi cua chien luoc chinh
for nm, kw in {"Ens|M|naive-vol(khong can bang lop)": dict(scheme="naive"), "Ens|M|long-flat": dict(long_only=True),
               "Ens|M|cost x0": dict(cost_mult=0.0, fric=0.0), "Ens|M|cost x2": dict(cost_mult=2.0, fric=0.006),
               "Ens|M|cost x3": dict(cost_mult=3.0, fric=0.009), "Ens|M|no-lag(lag1)": dict(lag=1),
               "Ens|M|lev cap 1.5": dict(lmax=1.5, gross_cap=3.0), "Ens|M|lev cap 1.0 (gross 2)": dict(lmax=1.0, gross_cap=2.0)}.items():
    net, s, r = go(nm, sig["Ensemble"], freq="M", **kw); rows.append(s); RET[nm] = net
E2 = pd.DataFrame(rows)

# ------------- benchmark -------------
a = ctx.Rz
spx = a["SPX"].loc[START:]; b10 = a["UST10"].loc[START:]
RET["SPX buy&hold"] = spx
RET["60/40 (SPX/UST10)"] = 0.6 * spx + 0.4 * b10
bm = RET["60/40 (SPX/UST10)"]; RET["60/40 vol-matched 10%"] = bm * (0.10 / (bm.std() * np.sqrt(ANN)))
# risk parity long-only (can bang rui ro theo lop, khong FX), vol muc tieu 10%
S1 = pd.DataFrame(1.0, index=I.index, columns=I.columns).where(I.notna())
S1[[c for c in S1.columns if ASSETS[c][0] == "fx"]] = np.nan
net, s, r = go("RiskParity long-only (khong FX)|M", S1, count=False, freq="M"); RET["RiskParity long-only"] = net
B = pd.DataFrame([summarize(RET[k], ctx, k) for k in ["SPX buy&hold", "60/40 (SPX/UST10)", "60/40 vol-matched 10%", "RiskParity long-only"]])

# ------------- E3: luoi do nhay (thang, class-balanced) -------------
rows = []


def sens(fam, par, S, **kw):
    net, s, r = go(f"{fam}:{par}", S, freq="M", **kw); s["family"] = fam; s["param"] = str(par); rows.append(s); return net


for lb in (63, 126, 189, 252, 378):
    for sk in (0, 21):
        sens("TSMOM", f"lb{lb}/skip{sk}", sig_tsmom(I, lb, sk))
for sl in (50, 100, 150, 200, 250, 300): sens("MA", f"slow{sl}", sig_ma(I, sl))
for n in (50, 100, 150, 200, 250): sens("Donchian", f"in{n}/out{n//2}", sig_donch(I, n, n // 2))
for tg in (0.06, 0.08, 0.12, 0.15): sens("Ensemble-vol", f"target{tg:.0%}", sig["Ensemble"], target=tg)
for lm in (2.0, 4.0, 6.0): sens("Ensemble-levcap", f"lmax{lm}", sig["Ensemble"], lmax=lm, gross_cap=12.0, asset_cap=5.0)
for ac in (1.0, 2.0): sens("Ensemble-assetcap", f"asset_cap{ac}", sig["Ensemble"], asset_cap=ac)
E3 = pd.DataFrame(rows)

# ------------- luu -------------
E1.to_csv(OUT / "ma_main_configs.csv", index=False); E2.to_csv(OUT / "ma_exec_variants.csv", index=False)
B.to_csv(OUT / "ma_benchmarks.csv", index=False); E3.to_csv(OUT / "ma_sensitivity.csv", index=False)
pd.DataFrame(trials, columns=["config", "sharpe_daily"]).to_csv(OUT / "ma_trials.csv", index=False)
pd.DataFrame(RET).to_parquet(DATA / "ma_returns.parquet")
pr = runs[PRIMARY]; pr["W"].to_parquet(DATA / "ma_primary_weights.parquet"); pr["contrib"].to_parquet(DATA / "ma_primary_contrib.parquet")
pr["gross"].to_frame("gross").to_parquet(DATA / "ma_primary_gross.parquet")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
cols = ["label", "Sharpe", "Vol", "TotalCAGR", "MaxDD", "Skew", "AvgGross", "Turnover_yr", "CostDrag_yr", "start"]
print(E1[cols].round(3).to_string()); print(E2[cols].round(3).to_string()); print(B[["label", "Sharpe", "Vol", "TotalCAGR", "MaxDD", "Skew"]].round(3).to_string())
print(E3[["label", "Sharpe", "TotalCAGR", "MaxDD"]].round(3).to_string()); print("trials", len(trials), "t=%.0fs" % (time.time() - t0))
