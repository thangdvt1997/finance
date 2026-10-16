"""Thong ke kiem dinh + hinh cho backtest co phieu VN: doc $ROUT/vn_*.parquet do run_vn.py ghi.
Xuat: $ROUT/vn_analysis.json, vn_*.csv, hinh $RFIG/vn_fig*.png."""
import json, warnings
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from vn_common import *
from engine import metrics, deflated_sharpe, psr0
warnings.filterwarnings("ignore")

T0 = pd.Timestamp("2014-03-03")
R = pd.read_parquet(OUT / "vn_grid_returns.parquet"); G = pd.read_csv(OUT / "vn_grid.csv", index_col=0)
B = pd.read_parquet(OUT / "vn_bench_returns.parquet"); BT = pd.read_csv(OUT / "vn_bench.csv", index_col=0)
S = pd.read_parquet(OUT / "vn_sens_returns.parquet"); ST_ = pd.read_csv(OUT / "vn_sens.csv", index_col=0)
PL = pd.read_parquet(OUT / "vn_placebo_returns.parquet")
vni = pd.read_parquet(OUT / "vn_vni_chain.parquet")["vni_chain"]
PRIM = "M12-1|U100|N15|M|ew|none"; DEF = "M12-1|U100|N15|M|ew|M"; DEFD = "M12-1|U100|N15|M|ew|D"
RFD = RF / ANN
out = {}


def sl(r, a=None, b=None):
    r = r.dropna(); r = r.loc[(a or T0):b] if (a or b) else r.loc[T0:]
    return r


def shp(r, rf=RF):
    r = r.dropna()
    return float((r.mean() - rf / ANN) / r.std() * np.sqrt(ANN)) if len(r) > 30 and r.std() > 0 else np.nan


def cagr(r):
    r = r.dropna(); yrs = (r.index[-1] - r.index[0]).days / 365.25
    return float((1 + r).prod() ** (1 / yrs) - 1) if yrs > 0.2 else np.nan


def mdd(r):
    nav = (1 + r.dropna()).cumprod(); return float((nav / nav.cummax() - 1).min())


def boot_idx(T, B_=2000, block=21, seed=7):
    rng = np.random.default_rng(seed); nb = int(np.ceil(T / block)); st = rng.integers(0, T, size=(B_, nb))
    return ((st[:, :, None] + np.arange(block)[None, None, :]) % T).reshape(B_, -1)[:, :T]


def boot_sharpe(r, B_=2000):
    r = r.dropna(); x = r.values[boot_idx(len(r), B_)]; sh = (x.mean(1) - RFD) / x.std(1, ddof=1) * np.sqrt(ANN)
    return [float(np.percentile(sh, 2.5)), float(np.percentile(sh, 97.5))], float((sh <= 0).mean())


def boot_diff(r1, r2, B_=2000):
    j = pd.concat([r1, r2], axis=1).dropna(); a, b = j.iloc[:, 0].values, j.iloc[:, 1].values
    ix = boot_idx(len(j), B_); xa, xb = a[ix], b[ix]
    f = lambda x: (x.mean(1) - RFD) / x.std(1, ddof=1) * np.sqrt(ANN)
    d = f(xa) - f(xb); act = (xa - xb).mean(1) * ANN
    obs = shp(j.iloc[:, 0]) - shp(j.iloc[:, 1])
    return dict(dSharpe=float(obs), ci=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))], p_le0=float((d <= 0).mean()),
                active_ann=float((a - b).mean() * ANN), active_ci=[float(np.percentile(act, 2.5)), float(np.percentile(act, 97.5))],
                IR=float((a - b).mean() / (a - b).std() * np.sqrt(ANN)), n=len(j))


def nw_ols(y, x, lags=3):
    X = np.c_[np.ones(len(x)), x]; b = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ b; n = len(y)
    Xe = X * e[:, None]; Sg = Xe.T @ Xe / n
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1); G_ = Xe[l:].T @ Xe[:-l] / n; Sg += w * (G_ + G_.T)
    Q = np.linalg.inv(X.T @ X / n); V = Q @ Sg @ Q / n
    return b, np.sqrt(np.diag(V))


# ============ A. bang tong hop ============
series = {"Momentum 12-1 (CHINH)": R[PRIM], "Momentum + MA200 thang (PHONG THU)": R[DEF], "Momentum + MA200 ngay": R[DEFD],
          "VN-Index (giá, không cổ tức)": B["VNINDEX_BH"], "E1VFVN30 (ETF)": B["ETF_BH"], "Top-100 đều, hàng tháng": B["EW100_M"], "Top-100 đều, hàng quý": B["EW100_Q"],
          "Top-30 đều, hàng quý (VN30 xấp xỉ)": B["EW30_Q"], "E1VFVN30 + MA200 tháng": B["ETF_MA200_M"], "E1VFVN30 + MA200 ngày": B["ETF_MA200_D"],
          "VN-Index + MA200 tháng (không phí)": B["VNI_MA200_M"], "VN-Index + MA200 ngày (không phí)": B["VNI_MA200_D"], "Tiền mặt (4,5%)": B["CASH"]}
rows = []
for k, r in series.items():
    r = sl(r)
    ci, p0 = boot_sharpe(r) if k != "Tiền mặt (4,5%)" else ([np.nan, np.nan], np.nan)
    rows.append(dict(name=k, start=str(r.index[0].date()), Sharpe=shp(r), ci_lo=ci[0], ci_hi=ci[1], CAGR=cagr(r), Vol=float(r.std() * np.sqrt(ANN)), MaxDD=mdd(r),
                     Calmar=cagr(r) / abs(mdd(r)) if mdd(r) < 0 else np.nan, PctLossYrs=float(((1 + r).groupby(r.index.year).prod() - 1).iloc[1:-1].lt(0).mean())))
head = pd.DataFrame(rows).set_index("name"); head.to_csv(OUT / "vn_headline.csv"); out["headline"] = head.round(4).to_dict("index")
extra = {k: dict(TurnoverYr=float(G.loc[k, "TurnoverYr"]), CostYr=float(G.loc[k, "CostYr"]), Expo=float(G.loc[k, "Expo"]), NHeld=float(G.loc[k, "NHeld"])) for k in [PRIM, DEF, DEFD]}
out["trading_stats"] = extra
# cung cua so voi ETF (2015-01 -> nay)
common = {}
A2 = pd.Timestamp("2015-01-02")
for k in ["Momentum 12-1 (CHINH)", "Momentum + MA200 thang (PHONG THU)", "VN-Index (giá, không cổ tức)", "E1VFVN30 (ETF)", "Top-100 đều, hàng tháng", "Top-30 đều, hàng quý (VN30 xấp xỉ)", "E1VFVN30 + MA200 tháng"]:
    r = sl(series[k], A2); common[k] = dict(Sharpe=shp(r), CAGR=cagr(r), MaxDD=mdd(r), Vol=float(r.std() * np.sqrt(ANN)))
out["common_2015"] = common

# ============ B. theo giai doan + nam ============
periods = {"2014-17": ("2014-03-03", "2017-12-31"), "2018-19": ("2018-01-01", "2019-12-31"), "2020 (COVID)": ("2020-01-01", "2020-12-31"), "2021 (bong bóng)": ("2021-01-01", "2021-12-31"),
           "2022 (sập)": ("2022-01-01", "2022-12-31"), "2023-26": ("2023-01-01", "2026-10-09")}
pk = {"CHÍNH": R[PRIM], "PHÒNG THỦ": R[DEF], "VN-Index": B["VNINDEX_BH"], "ETF": B["ETF_BH"], "Top-100 đều": B["EW100_M"], "Top-30 đều": B["EW30_Q"]}
per = {}
for pn, (a, b) in periods.items():
    per[pn] = {}
    for k, r in pk.items():
        x = r.dropna().loc[a:b]
        per[pn][k] = dict(ret=float((1 + x).prod() - 1) if len(x) else np.nan, sharpe=shp(x) if len(x) > 60 else np.nan, maxdd=mdd(x) if len(x) > 20 else np.nan, n=len(x))
out["periods"] = per
yr = pd.DataFrame({k: (1 + sl(r)).groupby(sl(r).index.year).prod() - 1 for k, r in pk.items()}); yr.to_csv(OUT / "vn_yearly.csv"); out["yearly"] = yr.round(4).to_dict("index")
half = {}
for k, r in {"CHÍNH": R[PRIM], "PHÒNG THỦ": R[DEF], "Top-100 đều": B["EW100_M"], "VN-Index": B["VNINDEX_BH"]}.items():
    x = sl(r); mid = x.index[len(x) // 2]
    half[k] = dict(first=shp(x.loc[:mid]), second=shp(x.loc[mid:]), mid=str(mid.date()))
out["halves"] = half

# ============ C. so voi benchmark (paired bootstrap) ============
out["paired"] = {
    "CHÍNH vs Top-100 đều (cùng universe: giá trị của chọn momentum)": boot_diff(sl(R[PRIM]), sl(B["EW100_M"])),
    "CHÍNH vs VN-Index": boot_diff(sl(R[PRIM]), sl(B["VNINDEX_BH"])),
    "CHÍNH vs E1VFVN30 (từ 2015)": boot_diff(sl(R[PRIM], A2), sl(B["ETF_BH"], A2)),
    "PHÒNG THỦ vs CHÍNH": boot_diff(sl(R[DEF]), sl(R[PRIM])),
    "PHÒNG THỦ vs Top-100 đều": boot_diff(sl(R[DEF]), sl(B["EW100_M"])),
    "PHÒNG THỦ vs VN-Index MA200 tháng (không phí)": boot_diff(sl(R[DEF]), sl(B["VNI_MA200_M"])),
    "PHÒNG THỦ vs E1VFVN30": boot_diff(sl(R[DEF], A2), sl(B["ETF_BH"], A2)),
    "Top-100 đều vs VN-Index": boot_diff(sl(B["EW100_M"]), sl(B["VNINDEX_BH"])),
    "E1VFVN30+MA200 vs E1VFVN30": boot_diff(sl(B["ETF_MA200_M"], A2), sl(B["ETF_BH"], A2)),
}

# ============ D. DSR ============
trials = pd.concat([R.loc[T0:], S.loc[T0:], B.loc[T0:]], axis=1)
tr_sh = ((trials.mean() - RFD) / trials.std()).replace([np.inf, -np.inf], np.nan).dropna()      # Sharpe NGAY cua tung lan thu
n_grid, n_all = R.shape[1], trials.shape[1]
dsr = {}
for nm, r in [("CHÍNH", R[PRIM]), ("PHÒNG THỦ", R[DEF]), ("Momentum + MA200 ngày", R[DEFD])]:
    x = sl(r) - RFD
    d_all, sr0_all = deflated_sharpe(x, tr_sh.values, n_all); d_grid, sr0_grid = deflated_sharpe(x, R.loc[T0:].sub(RFD).mean().div(R.loc[T0:].std()).dropna().values, n_grid)
    dsr[nm] = dict(DSR_all=d_all, SR0_all_ann=sr0_all, DSR_grid=d_grid, SR0_grid_ann=sr0_grid, PSR0=psr0(x), n_all=int(n_all), n_grid=int(n_grid))
out["dsr"] = dsr
out["grid_stats"] = dict(n=int(n_grid), sharpe_median=float(G.Sharpe.median()), share_pos=float((G.Sharpe > 0).mean()), sharpe_min=float(G.Sharpe.min()), sharpe_max=float(G.Sharpe.max()),
                         prim_pct_rank=float((G.Sharpe < G.loc[PRIM, "Sharpe"]).mean()), ew100_sharpe=float(head.loc["Top-100 đều, hàng tháng", "Sharpe"]),
                         share_beating_ew100=float((G.Sharpe > head.loc["Top-100 đều, hàng tháng", "Sharpe"]).mean()))
G2 = G.copy(); G2["filt"] = [k.split("|")[-1] for k in G2.index]
out["grid_by_filter"] = G2.groupby("filt").agg(n=("Sharpe", "size"), med=("Sharpe", "median"), p10=("Sharpe", lambda s: s.quantile(.1)), p90=("Sharpe", lambda s: s.quantile(.9)),
                                               share_pos=("Sharpe", lambda s: (s > 0).mean()), medCAGR=("CAGR", "median"), medDD=("MaxDD", "median")).round(3).to_dict("index")

# ============ E. do nhay tham so (heatmap) ============
def heat(filt, uni=100, freq="M", w="ew"):
    h = {}
    for lb in [3, 6, 9, 12]:
        for sk in [0, 1]:
            for N in [10, 15, 20, 30]:
                k = f"M{lb}-{sk}|U{uni}|N{N}|{freq}|{w}|{filt}"
                if k in G.index: h[(f"{lb}-{sk}", N)] = G.loc[k, "Sharpe"]
    return pd.Series(h).unstack()
H = {f: heat(f) for f in ["none", "M", "D"]}
out["heat"] = {f: h.round(3).to_dict() for f, h in H.items()}
fig, ax = plt.subplots(1, 3, figsize=(14, 3.8))
for a, (f, h) in zip(ax, H.items()):
    im = a.imshow(h.values, cmap="RdYlGn", vmin=-0.3, vmax=1.0, aspect="auto"); a.set_xticks(range(h.shape[1])); a.set_xticklabels(h.columns); a.set_yticks(range(h.shape[0])); a.set_yticklabels(h.index)
    for i in range(h.shape[0]):
        for j in range(h.shape[1]): a.text(j, i, f"{h.values[i, j]:.2f}", ha="center", va="center", fontsize=7)
    a.set_title({"none": "Không lọc", "M": "Lọc MA200 (tháng)", "D": "Lọc MA200 (ngày)"}[f] + " — Sharpe", fontsize=10); a.set_xlabel("N cổ phiếu"); a.set_ylabel("lookback-skip (tháng)")
fig.suptitle("Độ nhạy tham số (universe top-100, rebalance tháng, tỷ trọng đều)", fontsize=11); fig.tight_layout(); fig.savefig(FIG / "vn_fig3_sensitivity.png", dpi=130); plt.close(fig)

# ============ F. walk-forward / tach mau ============
def best_in(win_a, win_b, cols=None):
    cols = cols or list(R.columns); r = R.loc[win_a:win_b, cols]
    s = ((r.mean() - RFD) / r.std()) * np.sqrt(ANN); return s
wf = {}
for nm, (ia, ib, oa, ob) in {"IS 2014-19 -> OOS 2020-26": ("2014-03-03", "2019-12-31", "2020-01-01", "2026-12-31"), "IS 2020-26 -> OOS 2014-19": ("2020-01-01", "2026-12-31", "2014-03-03", "2019-12-31")}.items():
    s_is = best_in(ia, ib); k = s_is.idxmax(); s_oos = best_in(oa, ob)
    ew = shp(B["EW100_M"].loc[oa:ob])
    wf[nm] = dict(chosen=k, sharpe_is=float(s_is[k]), sharpe_oos=float(s_oos[k]), oos_rank_pct=float((s_oos < s_oos[k]).mean()), oos_median_all=float(s_oos.median()),
                  prim_is=float(s_is[PRIM]), prim_oos=float(s_oos[PRIM]), def_is=float(s_is[DEF]), def_oos=float(s_oos[DEF]), ew100_oos=ew,
                  corr_is_oos=float(np.corrcoef(s_is.values, s_oos.values)[0, 1]))
# walk-forward mo rong: moi nam chon cau hinh Sharpe 36 thang cuoi tot nhat -> nam sau
oos = []; picks = []
for y in range(2017, 2026):
    ra = pd.Timestamp(f"{y-2}-01-01"); rb = pd.Timestamp(f"{y}-12-31")
    s = best_in(ra, rb); k = s.idxmax(); picks.append((y + 1, k, float(s[k])))
    oos.append(R.loc[f"{y+1}-01-01":f"{y+1}-12-31", k])
wfo = pd.concat(oos)
wf["walk-forward 36m (2018-2026)"] = dict(sharpe=shp(wfo), cagr=cagr(wfo), prim_same_period=shp(R.loc[wfo.index[0]:, PRIM]), def_same_period=shp(R.loc[wfo.index[0]:, DEF]),
                                            ew100_same_period=shp(B["EW100_M"].loc[wfo.index[0]:]), n_distinct_picks=len(set(p[1] for p in picks)), picks=[(p[0], p[1]) for p in picks])
out["walk_forward"] = wf

# ============ G. placebo ============
pl = pd.read_csv(OUT / "vn_placebo.csv", index_col=0)
sh = lambda cols: np.array([shp(PL[c].loc[T0:]) for c in cols])
c_none = [c for c in PL.columns if c.startswith("rand|none")]; c_M = [c for c in PL.columns if c.startswith("rand|M")]; c_sh = [c for c in PL.columns if c.startswith("shift|M")]
s_none, s_M, s_sh = sh(c_none), sh(c_M), sh(c_sh)
sP, sD = shp(R.loc[T0:, PRIM]), shp(R.loc[T0:, DEF])
out["placebo"] = dict(
    random_none=dict(n=len(s_none), mean=float(s_none.mean()), sd=float(s_none.std()), p95=float(np.percentile(s_none, 95)), prim=sP, p_ge=float((s_none >= sP).mean()), z=float((sP - s_none.mean()) / s_none.std())),
    random_filter=dict(n=len(s_M), mean=float(s_M.mean()), sd=float(s_M.std()), p95=float(np.percentile(s_M, 95)), def_=sD, p_ge=float((s_M >= sD).mean()), z=float((sD - s_M.mean()) / s_M.std())),
    shift_regime=dict(n=len(s_sh), mean=float(s_sh.mean()), sd=float(s_sh.std()), p95=float(np.percentile(s_sh, 95)), def_=sD, p_ge=float((s_sh >= sD).mean()), z=float((sD - s_sh.mean()) / s_sh.std())))
fig, ax = plt.subplots(1, 2, figsize=(12, 3.8))
ax[0].hist(s_none, bins=25, color="#9db4c0", label="chọn ngẫu nhiên 15 cổ phiếu (top-100)"); ax[0].axvline(sP, color="#c0392b", lw=2, label=f"Momentum 12-1: {sP:.2f}")
ax[0].axvline(head.loc["Top-100 đều, hàng tháng", "Sharpe"], color="#2c3e50", ls="--", label="Top-100 đều")
ax[0].set_title("Placebo 1: chọn cổ phiếu ngẫu nhiên (không lọc)", fontsize=10); ax[0].set_xlabel("Sharpe"); ax[0].legend(fontsize=7)
ax[1].hist(s_sh, bins=25, color="#c8b99c", label="dịch vòng tròn tín hiệu MA200 (≥1 năm)"); ax[1].hist(s_M, bins=25, color="#9db4c0", alpha=.6, label="ngẫu nhiên + lọc MA200")
ax[1].axvline(sD, color="#c0392b", lw=2, label=f"Momentum + MA200: {sD:.2f}"); ax[1].set_title("Placebo 2: thời điểm lọc thị trường", fontsize=10); ax[1].set_xlabel("Sharpe"); ax[1].legend(fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "vn_fig4_placebo.png", dpi=130); plt.close(fig)

# ============ H. do nhay chi phi / von / thuc thi / sống sot ============
def row(k, pref):
    kk = f"{pref}|{k}"; r = S[kk].loc[T0:]
    return dict(Sharpe=shp(r), CAGR=cagr(r), MaxDD=mdd(r), TurnoverYr=float(ST_.loc[kk, "TurnoverYr"]), CostYr=float(ST_.loc[kk, "CostYr"]), Expo=float(ST_.loc[kk, "Expo"]))
sens = {}
for pref, nm in [("P", "CHÍNH"), ("F", "PHÒNG THỦ")]:
    sens[nm] = {k: row(k, pref) for k in [x.split("|", 1)[1] for x in S.columns if x.startswith(pref + "|")]}
sens["PHÒNG THỦ"]["daily filter"] = dict(Sharpe=shp(S["F|daily filter"].loc[T0:]), CAGR=cagr(S["F|daily filter"].loc[T0:]), MaxDD=mdd(S["F|daily filter"].loc[T0:]))
out["sens"] = sens
# rf nhay
out["rf_sens"] = {nm: {f"rf={rf}": shp(r.loc[T0:], rf) for rf in [0.0, 0.03, 0.045, 0.07]} for nm, r in {"CHÍNH": R[PRIM], "PHÒNG THỦ": R[DEF], "VN-Index": B["VNINDEX_BH"], "Top-100 đều": B["EW100_M"]}.items()}

# ============ I. beta/alpha ============
mon = lambda r: (1 + r.loc[T0:]).resample("ME").prod() - 1
mi = mon(B["VNINDEX_BH"]) - RF / 12
ba = {}
for nm, r in {"CHÍNH": R[PRIM], "PHÒNG THỦ": R[DEF], "Top-100 đều": B["EW100_M"], "Top-30 đều": B["EW30_Q"]}.items():
    y = (mon(r) - RF / 12).reindex(mi.index).values; x = mi.values; ok = np.isfinite(y) & np.isfinite(x)
    b, se = nw_ols(y[ok], x[ok]); ba[nm] = dict(alpha_ann=float(b[0] * 12), alpha_t=float(b[0] / se[0]), beta=float(b[1]), beta_se=float(se[1]), corr=float(np.corrcoef(y[ok], x[ok])[0, 1]), n=int(ok.sum()))
# alpha CHINH so voi Top-100 deu
y = (mon(R[PRIM]) - mon(B["EW100_M"])).dropna().values; x = (mi.reindex((mon(R[PRIM]) - mon(B["EW100_M"])).dropna().index)).values
b, se = nw_ols(y, x); ba["CHÍNH - Top100 (hoạt động)"] = dict(alpha_ann=float(b[0] * 12), alpha_t=float(b[0] / se[0]), beta=float(b[1]), beta_se=float(se[1]), n=len(y))
out["beta_alpha"] = ba

# ============ J. rolling Sharpe, equity ============
def roll_sh(r, w=756): return ((r.rolling(w).mean() - RFD) / r.rolling(w).std() * np.sqrt(ANN))
fig, ax = plt.subplots(3, 1, figsize=(11, 10), gridspec_kw={"height_ratios": [3, 1.6, 1.6]}, sharex=True)
cols = {"Momentum 12-1 (CHÍNH)": ("#c0392b", R[PRIM]), "Momentum + MA200 (PHÒNG THỦ)": ("#8e44ad", R[DEF]), "Top-100 đều (cùng universe)": ("#2c3e50", B["EW100_M"]),
        "VN-Index (giá)": ("#7f8c8d", B["VNINDEX_BH"]), "E1VFVN30": ("#16a085", B["ETF_BH"]), "Tiền mặt 4,5%": ("#bdc3c7", B["CASH"])}
for nm, (c, r) in cols.items():
    x = sl(r); eq = (1 + x).cumprod(); ax[0].plot(eq.index, eq, color=c, label=nm, lw=1.6 if "CHÍNH" in nm or "PHÒNG" in nm else 1.1)
    ax[1].plot(eq.index, eq / eq.cummax() - 1, color=c, lw=.9)
    if "CHÍNH" in nm or "PHÒNG" in nm or "Top-100" in nm: ax[2].plot(x.index, roll_sh(x), color=c, lw=1)
ax[0].set_yscale("log"); ax[0].set_ylabel("Giá trị (1 = 3/2014)"); ax[0].legend(fontsize=8, ncol=2); ax[0].set_title("Đường vốn (sau chi phí, log)", fontsize=10)
ax[1].set_ylabel("Drawdown"); ax[2].set_ylabel("Sharpe 3 năm"); ax[2].axhline(0, color="k", lw=.6)
for a in ax:
    for y_ in [2018, 2020, 2021, 2022, 2023]: a.axvline(pd.Timestamp(f"{y_}-01-01"), color="#ddd", lw=.6)
fig.tight_layout(); fig.savefig(FIG / "vn_fig1_equity.png", dpi=130); plt.close(fig)
fig, ax = plt.subplots(figsize=(11, 3.8)); w = .15; xs = np.arange(len(yr.index))
for i, (nm, c) in enumerate([("CHÍNH", "#c0392b"), ("PHÒNG THỦ", "#8e44ad"), ("Top-100 đều", "#2c3e50"), ("VN-Index", "#7f8c8d"), ("ETF", "#16a085")]):
    ax.bar(xs + (i - 2) * w, yr[nm] * 100, w, color=c, label=nm)
ax.set_xticks(xs); ax.set_xticklabels(yr.index); ax.axhline(0, color="k", lw=.6); ax.set_ylabel("% / năm"); ax.legend(fontsize=8, ncol=5); ax.set_title("Lợi suất theo năm dương lịch (sau chi phí)", fontsize=10)
fig.tight_layout(); fig.savefig(FIG / "vn_fig2_yearly.png", dpi=130); plt.close(fig)

# ============ K. von / song sot / chi phi hinh ============
fig, ax = plt.subplots(1, 3, figsize=(14, 3.6))
caps = [k for k in ST_.index if k.startswith("P|capital")]; capv = [float(k.split()[-1]) for k in caps]; o = np.argsort(capv)
ax[0].plot(np.array(capv)[o] / 1e9, ST_.loc[caps, "Sharpe"].values[o], "o-", color="#c0392b", label="CHÍNH")
capsF = [k for k in ST_.index if k.startswith("F|capital")]; ax[0].plot(np.array([float(k.split()[-1]) for k in capsF])[o] / 1e9, ST_.loc[capsF, "Sharpe"].values[o], "s-", color="#8e44ad", label="PHÒNG THỦ")
ax[0].set_xscale("log"); ax[0].set_xlabel("Vốn (tỷ VND)"); ax[0].set_ylabel("Sharpe"); ax[0].set_title("Sức chứa (giới hạn 10% KL TB 20 phiên)", fontsize=10); ax[0].legend(fontsize=8)
cm = [k for k in ST_.index if k.startswith("P|cost x")]; cmv = [float(k.split("x")[-1]) for k in cm]; oc = np.argsort(cmv)
ax[1].plot(np.array(cmv)[oc], ST_.loc[cm, "Sharpe"].values[oc], "o-", color="#c0392b"); cmF = [k for k in ST_.index if k.startswith("F|cost x")]
ax[1].plot(np.array([float(k.split("x")[-1]) for k in cmF])[oc], ST_.loc[cmF, "Sharpe"].values[oc], "s-", color="#8e44ad"); ax[1].set_xlabel("Hệ số chi phí (phí + thuế + trượt giá)"); ax[1].set_title("Nhạy chi phí", fontsize=10)
labs = ["base", "survivors-only universe", "today VN100 universe", "delist haircut 50%"]
ax[2].bar(np.arange(len(labs)) - .2, [ST_.loc["P|" + k, "Sharpe"] for k in labs], .4, color="#c0392b", label="CHÍNH"); ax[2].bar(np.arange(len(labs)) + .2, [ST_.loc["F|" + k, "Sharpe"] for k in labs], .4, color="#8e44ad", label="PHÒNG THỦ")
ax[2].set_xticks(range(len(labs))); ax[2].set_xticklabels(["đầy đủ\n(có cổ phiếu\nhủy niêm yết)", "chỉ ma còn\nniêm yết", "VN100\nhiện tại", "hủy niêm yết\n-50%"], fontsize=7); ax[2].set_title("Survivorship bias", fontsize=10); ax[2].legend(fontsize=8)
fig.tight_layout(); fig.savefig(FIG / "vn_fig5_capacity_cost_survivorship.png", dpi=130); plt.close(fig)

# ============ L. thang te nhat, tap trung ============
m_ = mon(R[PRIM]); out["worst_months"] = {str(k.date()): float(v) for k, v in m_.nsmallest(6).items()}; mD = mon(R[DEF]); out["worst_months_def"] = {str(k.date()): float(v) for k, v in mD.nsmallest(6).items()}
# ============ M. tin hieu thuan (chi phi 0) + ETF trend ============
E0 = pd.read_parquet(OUT / "vn_extra_ew0.parquet"); RR0 = pd.read_parquet(OUT / "vn_extra_rand0.parquet")
c0 = S["P|cost x0.0"]; s0 = np.array([shp(RR0[c].loc[T0:]) for c in RR0.columns])
out["gross"] = dict(prim_cost0=shp(c0.loc[T0:]), ew100_m_cost0=shp(E0["EW100_M|cost0"].loc[T0:]), ew100_q_cost0=shp(E0["EW100_Q|cost0"].loc[T0:]), ew30_q_cost0=shp(E0["EW30_Q|cost0"].loc[T0:]),
                    ew100_q_cost2=shp(E0["EW100_Q|cost2"].loc[T0:]), rand_cost0_mean=float(s0.mean()), rand_cost0_sd=float(s0.std()), rand_cost0_p95=float(np.percentile(s0, 95)),
                    p_ge=float((s0 >= shp(c0.loc[T0:])).mean()), cagr_prim0=cagr(c0.loc[T0:]), cagr_ew100_0=cagr(E0["EW100_M|cost0"].loc[T0:]), cagr_rand0=float(np.mean([cagr(RR0[c].loc[T0:]) for c in RR0.columns])),
                    diff_boot=boot_diff(sl(c0), sl(E0["EW100_M|cost0"])))
ET = pd.read_csv(OUT / "vn_extra_etf.csv", index_col=0); RE = pd.read_parquet(OUT / "vn_extra_etf.parquet")
et = {}
for k in ET.index:
    p = k.split("|")
    if p[3] == "0": et[k] = dict(Sharpe=float(ET.loc[k, "Sharpe"]), CAGR=float(ET.loc[k, "CAGR"]), MaxDD=float(ET.loc[k, "MaxDD"]), Expo=float(ET.loc[k, "Expo"]), Turn=float(ET.loc[k, "TurnoverYr"]))
out["etf_grid"] = et
sh_ = [shp(RE[c].loc[A2:]) for c in RE.columns if c.split("|")[3] != "0"]; k0 = "etf|200|M|0|1.0"; s_obs = shp(RE[k0].loc[A2:])
out["etf_placebo"] = dict(n=len(sh_), mean=float(np.mean(sh_)), sd=float(np.std(sh_)), p95=float(np.percentile(sh_, 95)), obs=s_obs, p_ge=float((np.array(sh_) >= s_obs).mean()))
ci, p0 = boot_sharpe(RE[k0].loc[A2:]); out["etf_ma200"] = dict(sharpe=s_obs, ci=ci, p_le0=p0, dsr=deflated_sharpe(RE[k0].loc[A2:] - RFD, np.array([(RE[c].loc[A2:].mean() - RFD) / RE[c].loc[A2:].std() for c in RE.columns if c.split("|")[3] == "0"]), 20)[0],
                                 vs_bh=boot_diff(RE[k0].loc[A2:], B["ETF_BH"].loc[A2:]))
fig, ax = plt.subplots(figsize=(7, 3.6)); ax.hist(sh_, bins=25, color="#c8b99c", label="dịch vòng tròn tín hiệu MA200"); ax.axvline(s_obs, color="#c0392b", lw=2, label=f"E1VFVN30 + MA200: {s_obs:.2f}"); ax.axvline(shp(B["ETF_BH"].loc[A2:]), color="#2c3e50", ls="--", label="mua-giữ ETF")
ax.legend(fontsize=8); ax.set_xlabel("Sharpe"); ax.set_title("Placebo thời điểm: ETF + MA200", fontsize=10); fig.tight_layout(); fig.savefig(FIG / "vn_fig6_etf_placebo.png", dpi=130); plt.close(fig)
sig_t = json.load(open(OUT / "vn_signal_test.json")); out["signal_test"] = sig_t

expo = pd.read_parquet(OUT / "vn_grid_expo.parquet"); out["regime_off_share"] = float(1 - expo[DEF].loc[T0:].gt(0.05).mean())
out["vni_stats"] = json.load(open(OUT / "vn_vni_stats.json"))
json.dump(out, open(OUT / "vn_analysis.json", "w"), indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
print(head.round(3).to_string()); print(json.dumps({k: out[k] for k in ["dsr", "grid_stats", "placebo", "walk_forward"]}, indent=1, default=str)[:6000])
