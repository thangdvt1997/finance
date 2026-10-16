"""Giai doan 2: kiem dinh thong ke + hinh. Doc ket qua run_multiasset.py. python analyze_multiasset.py"""
import json, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm
from ma_engine import *
FIG.mkdir(parents=True, exist_ok=True)
R, rf = pd.read_parquet(DATA / "excess_returns.parquet"), pd.read_parquet(DATA / "rf.parquet")["rf"]
RET = pd.read_parquet(DATA / "ma_returns.parquet"); trials = pd.read_csv(OUT / "ma_trials.csv")
ctx = Ctx(R, rf, CORE); I = ctx.I
P = "Ensemble|M"; LF = "Ens|M|long-flat"; BM = "60/40 (SPX/UST10)"
prim = RET[P].dropna(); bm = RET[BM].reindex(prim.index)
res = {}
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)

# ---------- 0. sanity engine ----------
sigs = {"Ensemble": sum([sig_tsmom(I, 252, 21), sig_multi(I), sig_ma(I, 200), sig_donch(I, 200, 100)]) / 4}
san = {}
r0 = run(ctx, sigs["Ensemble"], lag=0)["net"]; san["tin hieu that nhung lag0 (nhin truoc 1 ngay)"] = sharpe_d(r0)
Sor = np.sign(I.shift(-21) / I - 1).where(I.shift(-21).notna()); san["ORACLE nhin truoc 21 ngay (engine phai phat hien: rat cao)"] = sharpe_d(run(ctx, Sor, lag=2)["net"])
Sor2 = np.sign(I.shift(-1) / I - 1).where(I.shift(-1).notna()); san["oracle nhin truoc 1 ngay nhung lag2 (phai ~0 do da tre 2 phien)"] = sharpe_d(run(ctx, Sor2, lag=2)["net"])
try:
    import quantstats as qs
    x = RET[P].dropna(); san["quantstats Sharpe (doi chieu)"] = float(qs.stats.sharpe(x)); san["engine Sharpe"] = sharpe_d(x)
    san["quantstats MaxDD(excess)"] = float(qs.stats.max_drawdown(x)); 
except Exception as e: san["quantstats"] = "not installed: " + repr(e)[:80]
rng = np.random.default_rng(1)
rs = []
for k in range(20):
    S = pd.DataFrame(np.sign(rng.standard_normal(I.shape)), index=I.index, columns=I.columns).where(I.notna())
    rs.append(sharpe_d(run(ctx, S)["net"]))
san["tin hieu ngau nhien (20 lan): mean Sharpe"] = float(np.mean(rs)); san["tin hieu ngau nhien: max |Sharpe|"] = float(np.max(np.abs(rs)))
res["sanity"] = san; print(san)

# ---------- 1. cua so thoi gian ----------
wins = {"1990-2026": ("1990-01-01", "2026-12-31"), "2000-2026": ("2000-01-01", "2026-12-31"), "2012-2026 (du 35 TS)": ("2012-01-01", "2026-12-31"),
        "1990-1999": ("1990-01-01", "1999-12-31"), "2000-2009": ("2000-01-01", "2009-12-31"), "2010-2019": ("2010-01-01", "2019-12-31"), "2020-2026": ("2020-01-01", "2026-12-31")}
show = [P, LF, "Ens|M|naive-vol(khong can bang lop)", "TSMOM12-1|M", "MA200|M", "Donchian200/100|M", "Ensemble|W", BM, "RiskParity long-only", "SPX buy&hold"]
rows = []
for w, (a, b) in wins.items():
    for k in show:
        x = RET[k].loc[a:b].dropna()
        s = summarize(x, ctx, k)
        if s: rows.append(dict(window=w, cfg=k, Sharpe=s["Sharpe"], Vol=s["Vol"], TotalCAGR=s["TotalCAGR"], MaxDD=s["MaxDD"], Skew=s["Skew"]))
W = pd.DataFrame(rows); W.to_csv(OUT / "ma_windows.csv", index=False)
print(W.pivot(index="cfg", columns="window", values="Sharpe").round(2).to_string())

# ---------- 2. bootstrap, PSR, DSR ----------
ci, pz = block_bootstrap_sharpe(prim); res["boot_sharpe"] = dict(sharpe=sharpe_d(prim), lo=float(ci[0]), hi=float(ci[1]), p_le0=pz)
ci_b, _ = block_bootstrap_sharpe(bm.dropna()); res["boot_sharpe_6040"] = dict(sharpe=sharpe_d(bm), lo=float(ci_b[0]), hi=float(ci_b[1]))
lf = RET[LF].dropna(); ci_l, pl = block_bootstrap_sharpe(lf); res["boot_sharpe_longflat"] = dict(sharpe=sharpe_d(lf), lo=float(ci_l[0]), hi=float(ci_l[1]), p_le0=pl)


def paired_boot(a, b, B=3000, block=21, seed=3):
    d = pd.concat([a, b], axis=1).dropna().values; T = len(d); r = np.random.default_rng(seed); nb = int(np.ceil(T / block))
    st = r.integers(0, T, size=(B, nb)); ix = ((st[:, :, None] + np.arange(block)[None, None, :]) % T).reshape(B, -1)[:, :T]
    x = d[ix]; sh = x.mean(1) / x.std(1, ddof=1) * np.sqrt(ANN); diff = sh[:, 0] - sh[:, 1]
    return float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5)), float((diff <= 0).mean())


res["paired_boot_vs_6040"] = dict(zip(["lo", "hi", "p_le0"], paired_boot(prim, bm)))
res["paired_boot_longflat_vs_6040"] = dict(zip(["lo", "hi", "p_le0"], paired_boot(lf, bm)))
nt = len(trials); res["n_trials"] = nt
for nm, x in (("primary", prim), ("longflat", lf)):
    d, sr0 = deflated_sharpe(x, trials["sharpe_daily"].values, nt); res[f"DSR_{nm}"] = dict(DSR=d, SR0_ann=sr0, PSR0=psr0(x))
    d2, sr02 = deflated_sharpe(x, trials["sharpe_daily"].values, 200); res[f"DSR_{nm}_n200"] = dict(DSR=d2, SR0_ann=sr02)
res["trial_sharpe_ann_dist"] = dict(mean=float(trials.sharpe_daily.mean() * np.sqrt(ANN)), max=float(trials.sharpe_daily.max() * np.sqrt(ANN)), min=float(trials.sharpe_daily.min() * np.sqrt(ANN)))
print({k: v for k, v in res.items() if k != "sanity"})

# ---------- 3. walk-forward co chon cau hinh (14 cau hinh E1; chon theo Sharpe 5 nam truoc) ----------
main_cfgs = [c for c in RET.columns if c.endswith("|M") or c.endswith("|W")]
main_cfgs = [c for c in main_cfgs if c not in ("RiskParity long-only|M",) and "long-only" not in c and not c.startswith("Ens|")]
Mx = RET[main_cfgs]; wf = []; sel = {}
yrs = sorted(set(Mx.index.year))
for y in yrs:
    if y < 1996: continue
    tr = Mx.loc[f"{y-5}-01-01":f"{y-1}-12-31"]; best = (tr.mean() / tr.std()).idxmax(); sel[y] = best
    wf.append(Mx.loc[str(y), best])
wf = pd.concat(wf); ens_eq = Mx.loc[wf.index[0]:].mean(axis=1)
res["walkforward"] = dict(selected_Sharpe=sharpe_d(wf), equal_mix_Sharpe=sharpe_d(ens_eq), fixed_primary_same_period=sharpe_d(prim.loc[wf.index[0]:]),
                          sixty40_same_period=sharpe_d(bm.loc[wf.index[0]:]), start=str(wf.index[0].date()),
                          n_selected_distinct=len(set(sel.values())), selection_changes=int(sum(1 for a, b in zip(list(sel.values())[1:], list(sel.values())[:-1]) if a != b)))
# train->test chia doi: tham so co dinh nen chi bao cao 2 nua
half = prim.index[len(prim) // 2]; res["split_halves"] = dict(first=sharpe_d(prim[:half]), second=sharpe_d(prim[half:]), split=str(half.date()),
                                                              sixty40_first=sharpe_d(bm[:half]), sixty40_second=sharpe_d(bm[half:]))
print(res["walkforward"], res["split_halves"])

# ---------- 4. dong gop theo lop / tai san, leave-one-out ----------
C = pd.read_parquet(DATA / "ma_primary_contrib.parquet"); Wt = pd.read_parquet(DATA / "ma_primary_weights.parquet")
cls = pd.Series({c: ASSETS[c][0] for c in C.columns})
cc = C.T.groupby(cls).sum().T
ann_c = cc.mean() * ANN; tot_gross = C.sum(axis=1).mean() * ANN
share = ann_c / ann_c.sum()
assets_c = (C.mean() * ANN).sort_values(ascending=False)
res["contrib_class_ann"] = ann_c.round(4).to_dict(); res["contrib_class_share"] = share.round(3).to_dict()
res["contrib_asset_ann_top"] = assets_c.head(8).round(4).to_dict(); res["contrib_asset_ann_bottom"] = assets_c.tail(5).round(4).to_dict()
res["gross_pnl_ann_total"] = float(tot_gross)
# bond long-bias
for c in ("bond", "eq", "metal", "energy", "agri", "fx"):
    cols = [k for k in Wt.columns if ASSETS[k][0] == c]; res.setdefault("avg_net_exposure_by_class", {})[c] = float(Wt[cols].sum(axis=1).mean())
res["avg_gross"] = float(Wt.abs().sum(axis=1).mean()); res["max_gross"] = float(Wt.abs().sum(axis=1).max())
# bond sub-period
for a, b in (("1990-01-01", "2019-12-31"), ("2020-01-01", "2026-12-31"), ("1990-01-01", "2000-12-31")):
    res.setdefault("contrib_class_by_period", {})[f"{a[:4]}-{b[:4]}"] = (cc.loc[a:b].mean() * ANN).round(4).to_dict()
# LOCO + LOAO
S_all = sigs["Ensemble"]
loco = {}


def sub_run(excl):
    cols = [c for c in CORE if c not in excl]; cx = Ctx(R, rf, cols); r = run(cx, S_all[cols], freq="M"); return sharpe_d(r["net"]), summarize(r["net"], cx)["TotalCAGR"], summarize(r["net"], cx)["MaxDD"]


loco["ALL"] = sub_run([])
for c in CLASSES: loco[f"ex-{c}"] = sub_run([k for k in CORE if ASSETS[k][0] == c])
loco["ex-GOLD"] = sub_run(["GOLD"]); loco["ex-bond+GOLD"] = sub_run([k for k in CORE if ASSETS[k][0] == "bond"] + ["GOLD"])
loco["only eq+bond"] = sub_run([k for k in CORE if ASSETS[k][0] not in ("eq", "bond")])
loco["only commodities+fx"] = sub_run([k for k in CORE if ASSETS[k][0] in ("eq", "bond")])
loao = {c: sub_run([c])[0] for c in CORE}
res["LOCO"] = {k: dict(Sharpe=v[0], TotalCAGR=v[1], MaxDD=v[2]) for k, v in loco.items()}; res["LOAO_sharpe_min"] = min(loao.items(), key=lambda x: x[1]); res["LOAO_sharpe_max"] = max(loao.items(), key=lambda x: x[1])
res["LOAO_range"] = [float(min(loao.values())), float(max(loao.values()))]
pd.Series(loao).to_csv(OUT / "ma_loao.csv"); pd.DataFrame(res["LOCO"]).T.to_csv(OUT / "ma_loco.csv")
print(pd.DataFrame(res["LOCO"]).T.round(3).to_string()); print(res["LOAO_range"], res["LOAO_sharpe_min"], res["LOAO_sharpe_max"])

# ---------- 5. placebo dich thoi gian (pha vi tri tin hieu so voi gia that) ----------
pl = []
for sd in range(300):
    Ss = ST.shifted_signal(S_all, 1000 + sd, 252)
    pl.append(sharpe_d(run(ctx, Ss, freq="M")["net"]))
pl = np.array(pl); res["placebo"] = dict(mean=float(pl.mean()), sd=float(pl.std()), p95=float(np.percentile(pl, 95)), p99=float(np.percentile(pl, 99)), p_ge_observed=float((pl >= sharpe_d(prim)).mean()), n=len(pl))
pl_lf = []
for sd in range(300):
    Ss = ST.shifted_signal(S_all, 5000 + sd, 252)
    pl_lf.append(sharpe_d(run(ctx, Ss, freq="M", long_only=True)["net"]))
pl_lf = np.array(pl_lf); res["placebo_longflat"] = dict(mean=float(pl_lf.mean()), sd=float(pl_lf.std()), p95=float(np.percentile(pl_lf, 95)), p_ge_observed=float((pl_lf >= sharpe_d(lf)).mean()))
print(res["placebo"], res["placebo_longflat"])

# ---------- 6. quan he voi 60/40, duoi, khung hoang ----------
mo = lambda x: (1 + x).resample("ME").prod() - 1
pm, bmm, spm = mo(prim), mo(bm), mo(RET["SPX buy&hold"].reindex(prim.index))
res["corr_6040_daily"] = float(prim.corr(bm)); res["corr_6040_monthly"] = float(pm.corr(bmm)); res["corr_spx_monthly"] = float(pm.corr(spm))
res["corr_6040_longflat_monthly"] = float(mo(lf).corr(bmm))
Xo = sm.add_constant(bmm); fit = sm.OLS(pm, Xo).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
res["alpha_vs_6040"] = dict(alpha_ann=float(fit.params["const"] * 12), t=float(fit.tvalues["const"]), beta=float(fit.params.iloc[1]), t_beta=float(fit.tvalues.iloc[1]))
Xq = sm.add_constant(pd.DataFrame({"spx": spm, "spx2": spm ** 2})); fq = sm.OLS(pm, Xq).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
res["convexity_spx"] = dict(beta=float(fq.params["spx"]), t_beta=float(fq.tvalues["spx"]), gamma=float(fq.params["spx2"]), t_gamma=float(fq.tvalues["spx2"]), alpha_ann=float(fq.params["const"] * 12))
q10 = bmm.quantile(0.10); w = bmm <= q10
res["tail_6040_worst10pct_months"] = dict(n=int(w.sum()), strat_mean=float(pm[w].mean()), sixty40_mean=float(bmm[w].mean()), strat_pos_frac=float((pm[w] > 0).mean()))
w5 = spm <= spm.quantile(0.10); res["tail_spx_worst10pct_months"] = dict(n=int(w5.sum()), strat_mean=float(pm[w5].mean()), spx_mean=float(spm[w5].mean()), strat_pos_frac=float((pm[w5] > 0).mean()))
res["tail_longflat"] = dict(strat_mean=float(mo(lf)[w].mean()))
# episodes: 60/40 drawdown <= -10% (nien dai peak-trough)
eq = (1 + bm).cumprod(); dd = eq / eq.cummax() - 1; eps = []; i = 0; idx = eq.index
inep = False
for k in range(len(dd)):
    if dd.iloc[k] < 0 and not inep: inep = True; pk = k - 1 if k > 0 else 0; lo = k; lo_v = dd.iloc[k]
    if inep:
        if dd.iloc[k] < lo_v: lo = k; lo_v = dd.iloc[k]
        if dd.iloc[k] == 0 or k == len(dd) - 1:
            if lo_v <= -0.10: eps.append((idx[pk], idx[lo], lo_v))
            inep = False
rows = []
for a, b, v in eps:
    rows.append(dict(peak=str(a.date()), trough=str(b.date()), dd_6040=v, strat_ret=float((1 + prim.loc[a:b]).prod() - 1), longflat_ret=float((1 + lf.loc[a:b]).prod() - 1), spx_ret=float((1 + RET["SPX buy&hold"].loc[a:b]).prod() - 1)))
EP = pd.DataFrame(rows); EP.to_csv(OUT / "ma_crisis_episodes.csv", index=False); print(EP.round(3).to_string())
# nam su kien
ev = {}
for y in (2008, 2013, 2015, 2018, 2020, 2022, 2023, 2025):
    f = lambda x: float((1 + x.loc[str(y)]).prod() - 1)
    ev[y] = dict(strat=f(prim), longflat=f(lf), sixty40=f(bm), spx=f(RET["SPX buy&hold"]), naive=f(RET["Ens|M|naive-vol(khong can bang lop)"]))
res["events"] = ev; EV = pd.DataFrame(ev).T; EV.to_csv(OUT / "ma_events.csv"); print(EV.round(3).to_string())
yr = pd.DataFrame({"strat": (1 + prim).groupby(prim.index.year).prod() - 1, "longflat": (1 + lf).groupby(lf.index.year).prod() - 1, "6040": (1 + bm).groupby(bm.index.year).prod() - 1})
yr.to_csv(OUT / "ma_yearly.csv")
res["pct_years_strat_gt_6040"] = float((yr.strat > yr["6040"]).mean()); res["pct_years_neg_strat"] = float((yr.strat < 0).mean()); res["pct_years_neg_6040"] = float((yr["6040"] < 0).mean())
# ket hop 60/40 + x% trend (huu ich nhat khi dung nhu lop phu tro)
comb = {}
for wgt in (0.0, 0.2, 0.3, 0.5):
    x = (1 - wgt) * RET["60/40 vol-matched 10%"].reindex(prim.index) + wgt * prim
    comb[wgt] = dict(Sharpe=sharpe_d(x), Vol=float(x.std() * np.sqrt(ANN)), MaxDD=summarize(x, ctx)["MaxDD"], TotalCAGR=summarize(x, ctx)["TotalCAGR"])
res["blend_6040_vm_plus_trend"] = comb

# ---------- 7. crypto mo rong + ban dang tai san it ----------
colsx = CORE + ["BTC", "ETH"]; cx = Ctx(R, rf, colsx)
Sx = sum([sig_tsmom(cx.I, 252, 21), sig_multi(cx.I), sig_ma(cx.I, 200), sig_donch(cx.I, 200, 100)]) / 4
rx = run(cx, Sx, freq="M"); res["with_crypto"] = dict(Sharpe=sharpe_d(rx["net"]), since2018_with=sharpe_d(rx["net"].loc["2018":]), since2018_without=sharpe_d(prim.loc["2018":]))
res["in_sample_universe_counts"] = {str(y): int(I.loc[f"{y}-12-31":].iloc[0].notna().sum()) for y in (1990, 2000, 2005, 2010, 2012, 2020)}
json.dump(res, open(OUT / "ma_analysis.json", "w"), indent=1, default=str)

# ---------- hinh ----------
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.25})
def curve(x): return (1 + x).cumprod()
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw=dict(height_ratios=[3, 1.3]))
sty = [(P, "Trend ensemble L/S (thang, 10% vol)", "C0"), (LF, "Trend ensemble long-flat", "C2"), ("60/40 vol-matched 10%", "60/40 vol-matched 10%", "C3"), ("RiskParity long-only", "Risk parity long-only", "C1"), ("SPX buy&hold", "S&P 500 (excess)", "0.5")]
for k, lab, col in sty:
    x = RET[k].reindex(prim.index).fillna(0); e = curve(x); ax[0].plot(e.index, e, label=lab, color=col, lw=1.3); ax[1].plot(e.index, e / e.cummax() - 1, color=col, lw=0.9)
ax[0].set_yscale("log"); ax[0].set_ylabel("Von (excess so voi tien mat, log)"); ax[0].legend(); ax[1].set_ylabel("Drawdown"); ax[0].set_title("Trend cham da tai san vs 60/40 (sau chi phi, 1990-2026)")
fig.tight_layout(); fig.savefig(FIG / "ma_fig1_equity_dd.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(figsize=(11, 4)); xx = np.arange(len(yr)); ax.bar(xx - 0.27, yr.strat, 0.27, label="Trend L/S"); ax.bar(xx, yr.longflat, 0.27, label="Trend long-flat"); ax.bar(xx + 0.27, yr["6040"], 0.27, label="60/40 (khong ep vol)")
ax.set_xticks(xx[::2]); ax.set_xticklabels(yr.index[::2], rotation=60); ax.legend(); ax.set_title("Loi suat excess theo nam"); fig.tight_layout(); fig.savefig(FIG / "ma_fig2_yearly.png", dpi=130); plt.close(fig)
S3 = pd.read_csv(OUT / "ma_sensitivity.csv")
fig, ax = plt.subplots(figsize=(10, 6)); s3 = S3[S3.family.isin(["TSMOM", "MA", "Donchian"])]; ax.barh(s3.label, s3.Sharpe, color=["C0" if f == "TSMOM" else "C1" if f == "MA" else "C2" for f in s3.family]); ax.axvline(sharpe_d(bm), color="r", ls="--", label="60/40"); ax.axvline(0, color="k", lw=0.5)
ax.legend(); ax.set_title("Do nhay tham so (Sharpe sau chi phi, 1990-2026)"); ax.invert_yaxis(); fig.tight_layout(); fig.savefig(FIG / "ma_fig3_sensitivity.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(1, 2, figsize=(11, 4)); ax[0].hist(pl, bins=30, color="0.6"); ax[0].axvline(sharpe_d(prim), color="C0", label="Trend L/S that"); ax[0].set_title("Placebo dich tin hieu (L/S), 300 lan"); ax[0].legend()
ax[1].hist(pl_lf, bins=30, color="0.6"); ax[1].axvline(sharpe_d(lf), color="C2", label="Long-flat that"); ax[1].set_title("Placebo dich tin hieu (long-flat)"); ax[1].legend(); fig.tight_layout(); fig.savefig(FIG / "ma_fig4_placebo.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(figsize=(10, 4.5)); (cc.cumsum()).plot(ax=ax); ax.set_title("Dong gop luy ke (cong don, truoc chi phi) theo lop tai san - Trend L/S"); fig.tight_layout(); fig.savefig(FIG / "ma_fig5_contrib.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 4)); L = pd.DataFrame(res["LOCO"]).T; ax.bar(L.index, L.Sharpe); ax.axhline(sharpe_d(bm), color="r", ls="--", label="60/40"); ax.set_title("Leave-one-class-out: Sharpe"); plt.xticks(rotation=45); ax.legend(); fig.tight_layout(); fig.savefig(FIG / "ma_fig6_loco.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(1, 2, figsize=(11, 4)); ax[0].scatter(spm * 100, pm * 100, s=8, alpha=0.6); xs = np.linspace(spm.min(), spm.max(), 50); ax[0].plot(xs * 100, (fq.params["const"] + fq.params["spx"] * xs + fq.params["spx2"] * xs ** 2) * 100, "r")
ax[0].set_xlabel("S&P excess thang %"); ax[0].set_ylabel("Trend thang %"); ax[0].set_title("Dang cuoi (smile?) cua trend vs co phieu")
rc = prim.rolling(756).corr(bm); ax[1].plot(rc.index, rc); ax[1].axhline(0, color="k", lw=0.5); ax[1].set_title("Tuong quan 3 nam voi 60/40 (ngay)"); fig.tight_layout(); fig.savefig(FIG / "ma_fig7_tail_corr.png", dpi=130); plt.close(fig)
rs = prim.rolling(1260).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN), raw=True); rb = bm.rolling(1260).apply(lambda x: x.mean() / x.std() * np.sqrt(ANN), raw=True)
fig, ax = plt.subplots(figsize=(10, 3.8)); ax.plot(rs, label="Trend L/S"); ax.plot(rb, label="60/40"); ax.axhline(0, color="k", lw=0.5); ax.legend(); ax.set_title("Sharpe cuon 5 nam"); fig.tight_layout(); fig.savefig(FIG / "ma_fig8_rolling_sharpe.png", dpi=130); plt.close(fig)
print(json.dumps({k: v for k, v in res.items() if k not in ("sanity",)}, indent=1, default=str)[:12000])
