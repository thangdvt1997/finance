"""Chay toan bo nghien cuu: python run_study.py  (sau fetch_data.py). Seed co dinh. Ket qua -> results/*.csv, figures/*.png, results/summary.md"""
import warnings, json, pathlib, itertools
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import engine as E, strategies as S

SEED = 20261011
R = pathlib.Path(__file__).parent; RES = R / "results"; FIG = R / "figures"; RES.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
START = pd.Timestamp("2002-06-01")            # cua so chung: JPY co lai suat that tu 2002-04 + khoi dong tin hieu
PANELS = {"A_FX7": E.FX, "B_FX7+XAU+XAG": E.FX + ["XAUUSD", "XAGUSD"]}
MAIN = {"TSMOM12": ("tsmom", dict(lb=252)), "MA50/200": ("ma", dict(fast=50, slow=200)), "DONCH55/20": ("donch", dict(n_in=55, n_out=20)),
        "CARRY_k3": ("carry", dict(k=3)), "RSI2_10/90": ("rsi2", dict(lo=10, hi=90)), "BOLL20/2": ("boll", dict(n=20, k=2.0))}
GRID = ([("tsmom", dict(lb=x)) for x in (63, 126, 252, 378)] + [("ma", dict(fast=f, slow=s)) for f, s in ((20, 50), (20, 100), (50, 200), (100, 250))]
        + [("donch", dict(n_in=a, n_out=b)) for a, b in ((20, 10), (55, 20), (100, 50))] + [("rsi2", dict(lo=l, hi=h)) for l, h in ((5, 95), (10, 90), (20, 80))]
        + [("boll", dict(n=n, k=k)) for n, k in ((20, 2.0), (20, 2.5), (10, 2.0))] + [("carry", dict(k=k)) for k in (2, 3)])
CRISES = {"2008": ("2008-01-01", "2008-12-31"), "2015": ("2015-01-01", "2015-12-31"), "2020": ("2020-01-01", "2020-12-31"), "2022": ("2022-01-01", "2022-12-31")}


def signal(kind, P, rates, **kw):
    if kind == "tsmom": return S.tsmom(P, **kw)
    if kind == "ma": return S.ma_cross(P, **kw)
    if kind == "donch": return S.donchian(P, **kw)
    if kind == "rsi2": return S.rsi2_mr(P, **kw)
    if kind == "boll": return S.bollinger_mr(P, **kw)
    if kind == "carry": return S.carry(P, rates, **kw)
    raise ValueError(kind)


def combine(streams, target=0.10):
    """Can bang rui ro: trong so ti le nghich dao vol 252d (tre 1 ngay), roi scale ve vol muc tieu ex-ante."""
    st = streams.dropna()
    vol = st.rolling(252, min_periods=126).std().shift(1)
    w = (1 / vol); w = w.div(w.sum(axis=1), axis=0)
    raw = (w * st).sum(axis=1).iloc[130:]
    sv = raw.ewm(span=60, min_periods=60).std().shift(1) * np.sqrt(E.ANN)
    return (raw * (target / sv.clip(lower=0.01)).clip(upper=4)).dropna()


def run_main(P, rates, cost_mult=1.0, markup=0.005):
    out = {}
    for name, (kind, kw) in MAIN.items():
        out[name] = E.run(P, signal(kind, P, rates, **kw), rates, cost_mult=cost_mult, markup=markup)
    out["BUYHOLD"] = E.run(P, S.buy_hold(P), rates, cost_mult=cost_mult, markup=markup)
    net = pd.DataFrame({k: v["net"] for k, v in out.items()})
    net["COMBO4(trend3+carry)"] = combine(net[["TSMOM12", "MA50/200", "DONCH55/20", "CARRY_k3"]])
    net["COMBO5(+RSI2)"] = combine(net[["TSMOM12", "MA50/200", "DONCH55/20", "CARRY_k3", "RSI2_10/90"]])
    net["TREND3"] = combine(net[["TSMOM12", "MA50/200", "DONCH55/20"]])
    return out, net


def fmt_table(df, pct=(), f2=(), f1=()):
    d = df.copy()
    for c in d.columns:
        if c in pct: d[c] = d[c].map(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
        elif c in f2: d[c] = d[c].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
        elif c in f1: d[c] = d[c].map(lambda x: f"{x:.1f}" if pd.notna(x) else "")
    cols = [d.index.name or ""] + list(d.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for i, row in d.iterrows(): lines.append("| " + " | ".join([str(i)] + [str(v) for v in row.values]) + " |")
    return "\n".join(lines)


MCOLS = dict(pct=("CAGR", "Vol", "MaxDD", "PctLossYears"), f2=("Sharpe", "Sortino", "Calmar", "Skew", "MaxUnderwaterYears", "Turn/yr", "AvgLev", "SharpeLo", "SharpeHi", "P(SR<=0)", "DSR", "PSR0"))
summary = []
def emit(title, df, **kw):
    summary.append(f"\n### {title}\n\n" + fmt_table(df, **kw)); print("\n==", title); print(df.round(3).to_string())


def window(s, a=START, b=None): return s.loc[a:b]


all_results = {}
trial_sr = []   # Sharpe ngay (khong nam hoa) cua moi cau hinh da thu -> DSR
trial_log = []
for pname, names in PANELS.items():
    P = E.load_prices(names); rates, rend = E.load_rates(P.index); P = P.loc[:rend]; rates = rates.loc[:rend]
    print(f"\n######## PANEL {pname}: {P.index.min().date()} -> {P.index.max().date()} (lai suat hop le toi {rend.date()})")
    # ---- grid (dem thu nghiem) ----
    gr = {}
    for kind, kw in GRID:
        o = E.run(P, signal(kind, P, rates, **kw), rates)
        r = window(o["net"]); m = E.metrics(r); label = f"{kind}{json.dumps(kw, separators=(',', ':'))}"
        gr[label] = dict(kind=kind, Sharpe=m["Sharpe"], CAGR=m["CAGR"], MaxDD=m["MaxDD"], net=o["net"])
        trial_sr.append(r.mean() / r.std()); trial_log.append((pname, label, m["Sharpe"]))
    all_results[pname] = dict(P=P, rates=rates, grid=gr)

N_TRIALS = len(trial_sr); SRV = np.array(trial_sr)
print("\nTONG SO CAU HINH DA THU (grid x panel):", N_TRIALS)
pd.DataFrame(trial_log, columns=["panel", "config", "Sharpe"]).to_csv(RES / "grid_all_trials.csv", index=False)

cmp_rows = []
for pname, names in PANELS.items():
    P = all_results[pname]["P"]; rates = all_results[pname]["rates"]; gr = all_results[pname]["grid"]
    summary.append(f"\n## Panel {pname}  ({P.index.min().date()} -> {P.index.max().date()}; cua so danh gia {START.date()} -> {P.index.max().date()})")
    out, net = run_main(P, rates)
    pd.concat([net], axis=1).to_csv(RES / f"returns_{pname}.csv")
    W = net.loc[START:]
    # ---- bang chinh ----
    rows = {}
    for c in W.columns:
        m = E.metrics(W[c].dropna()); (lo, hi), p0 = E.block_bootstrap_sharpe(W[c].dropna(), seed=SEED)
        dsr, sr0 = E.deflated_sharpe(W[c].dropna(), SRV, N_TRIALS)
        m.update(SharpeLo=lo, SharpeHi=hi, **{"P(SR<=0)": p0}, DSR=dsr, PSR0=E.psr0(W[c].dropna()))
        if c in out:
            o = out[c]; ww = o["net"].loc[START:].index
            m["Turn/yr"] = o["turnover"].loc[ww].sum() / E.years(ww); m["AvgLev"] = o["lev"].loc[ww].mean()
        rows[c] = m
    T = pd.DataFrame(rows).T; T.index.name = "Chien luoc"; T.to_csv(RES / f"main_{pname}.csv")
    emit(f"Ket qua chinh sau chi phi - {pname}", T[["CAGR", "Vol", "Sharpe", "SharpeLo", "SharpeHi", "Sortino", "MaxDD", "Calmar", "PctLossYears", "MaxUnderwaterYears", "Skew", "Turn/yr", "AvgLev", "P(SR<=0)", "PSR0", "DSR"]], **MCOLS)
    # ---- phan ra: tho/carry/chi phi ----
    dec = {c: dict(Spot=out[c]["spot"].loc[START:].mean() * 252, Carry_ròng_markup=out[c]["carry"].loc[START:].mean() * 252, ChiPhi_GD=-out[c]["cost"].loc[START:].mean() * 252) for c in out}
    D = pd.DataFrame(dec).T; D.index.name = "Chien luoc"; emit(f"Phan ra loi suat nam (cong don, % von) - {pname}", D, pct=tuple(D.columns))
    # ---- do nhay chi phi ----
    cs = {}
    for lab, (cm, mk) in {"khong_phi": (0.0, 0.0), "co_so(1x,0.5%)": (1.0, 0.005), "xau(2x,1%)": (2.0, 0.01)}.items():
        _, n2 = run_main(P, rates, cm, mk)
        cs[lab] = n2.loc[START:].apply(lambda s: E.metrics(s.dropna()).get("Sharpe", np.nan))
    C = pd.DataFrame(cs); C.index.name = "Chien luoc"; C.to_csv(RES / f"cost_sens_{pname}.csv"); emit(f"Sharpe theo gia dinh chi phi - {pname}", C, f2=tuple(C.columns))
    # ---- giai doan ----
    pre = {c: E.metrics(net[c].loc[START:"2011-12-31"].dropna()).get("Sharpe", np.nan) for c in net.columns}
    post = {c: E.metrics(net[c].loc["2012-01-01":].dropna()).get("Sharpe", np.nan) for c in net.columns}
    PP = pd.DataFrame(dict(Sharpe_2002_2011=pre, Sharpe_2012_nay=post)); PP.index.name = "Chien luoc"; emit(f"Truoc/sau cong bo MOP (2012) - {pname}", PP, f2=tuple(PP.columns))
    cr = {k: {c: ((1 + net[c].loc[a:b].dropna()).prod() - 1) for c in net.columns} for k, (a, b) in CRISES.items()}
    CR = pd.DataFrame(cr); CR["Ngay_CHF_2015-01-15"] = {c: net[c].get(pd.Timestamp("2015-01-15"), np.nan) for c in net.columns}
    CR["Ngay_te_nhat"] = W.min(); CR.index.name = "Chien luoc"; CR.to_csv(RES / f"crises_{pname}.csv"); emit(f"Giai doan khung hoang (loi suat) - {pname}", CR, pct=tuple(CR.columns))
    yr = (1 + W).groupby(W.index.year).prod() - 1; yr.to_csv(RES / f"yearly_{pname}.csv")
    # ---- tuong quan ----
    corr = W.dropna().corr(); corr.to_csv(RES / f"corr_{pname}.csv"); emit(f"Tuong quan loi suat ngay - {pname}", corr, f2=tuple(corr.columns))
    # ---- luoi do nhay ----
    G = pd.DataFrame({k: dict(v) for k, v in gr.items()}).T.drop(columns="net"); G.index.name = "Cau hinh"; G.to_csv(RES / f"grid_{pname}.csv")
    emit(f"Do nhay tham so (toan bo luoi, ca vung xau) - {pname}", G[["Sharpe", "CAGR", "MaxDD"]], pct=("CAGR", "MaxDD"), f2=("Sharpe",))
    # ---- walk-forward: chon cau hinh trend tot nhat 5 nam gan nhat ----
    pool = {k: v["net"] for k, v in gr.items() if v["kind"] in ("tsmom", "ma", "donch")}
    PoolDF = pd.DataFrame(pool); wf = []; chosen = {}
    for y in range(2007, P.index.max().year + 1):
        tr = PoolDF.loc[f"{y-5}-01-01":f"{y-1}-12-31"].loc[START:]
        if len(tr) < 3 * 252: continue
        sh = tr.mean() / tr.std(); best = sh.idxmax(); chosen[y] = best
        wf.append(PoolDF[best].loc[f"{y}-01-01":f"{y}-12-31"])
    WF = pd.concat(wf); WF.name = "WalkForward_best5y"
    ew = PoolDF.mean(axis=1)  # trung binh cac cau hinh (khong chon)
    span = WF.index
    cmp = {"Walk-forward (chon tot nhat 5y)": WF, "Co dinh TSMOM12": net["TSMOM12"].loc[span], "Co dinh MA50/200": net["MA50/200"].loc[span],
           "Co dinh DONCH55/20": net["DONCH55/20"].loc[span], "TB deu 11 cau hinh trend": ew.loc[span]}
    WFT = pd.DataFrame({k: E.metrics(v.dropna()) for k, v in cmp.items()}).T[["CAGR", "Vol", "Sharpe", "MaxDD", "PctLossYears"]]
    WFT.index.name = f"OOS {span.min().year}-{span.max().year}"; WFT.to_csv(RES / f"walkforward_{pname}.csv")
    emit(f"Walk-forward (chon tham so bang 5 nam truoc, ap dung nam sau) - {pname}", WFT, pct=("CAGR", "Vol", "MaxDD", "PctLossYears"), f2=("Sharpe",))
    summary.append("\nCau hinh duoc chon moi nam: " + ", ".join(f"{y}:{c}" for y, c in chosen.items()))
    # ---- baseline ngau nhien khop toc do dao chieu ----
    if pname == "A_FX7":
        rb = {}
        for nm in ("TSMOM12", "MA50/200", "DONCH55/20", "RSI2_10/90", "BOLL20/2", "CARRY_k3"):
            kind, kw = MAIN[nm]; sg = signal(kind, P, rates, **kw); shs = []
            for sd in range(300):
                o = E.run(P, S.shifted_signal(sg, SEED + sd), rates)
                shs.append(E.metrics(o["net"].loc[START:])["Sharpe"])
            shs = np.array(shs)
            rb[nm] = dict(rand_mean=shs.mean(), rand_p05=np.percentile(shs, 5), rand_p95=np.percentile(shs, 95), actual=T.loc[nm, "Sharpe"], pctile_of_actual=float((shs < T.loc[nm, "Sharpe"]).mean()))
            all_results[pname].setdefault("rand", {})[nm] = shs
        RB = pd.DataFrame(rb).T; RB.index.name = "Chien luoc"; RB.to_csv(RES / "random_baseline_A.csv")
        emit("Kiem soat dich-thoi-gian (300 mau, cung ty le long/short & so lan dao chieu, sau chi phi) - panel A", RB, f2=tuple(RB.columns))
        EX = {c: E.metrics(net[c].loc["2000-06-01":].dropna()) for c in ("TSMOM12", "MA50/200", "DONCH55/20", "BUYHOLD")}
        EX = pd.DataFrame(EX).T[["CAGR", "Vol", "Sharpe", "MaxDD"]]; EX.index.name = "Chien luoc"; emit("Cua so mo rong 2000-06 -> (panel A, chi chien luoc khong can lai suat JPY that)", EX, pct=("CAGR", "Vol", "MaxDD"), f2=("Sharpe",))
    # ---- tung instrument ----
    pi = {}
    for c in names:
        row = {}
        for nm in ("TSMOM12", "MA50/200", "DONCH55/20"):
            kind, kw = MAIN[nm]; sg = signal(kind, P[[c]], rates, **kw); o = E.run(P[[c]], sg, rates)
            row[nm] = E.metrics(o["net"].loc[START:]).get("Sharpe", np.nan)
        row["BuyHold(vol10%)"] = E.metrics(E.run(P[[c]], S.buy_hold(P[[c]]), rates)["net"].loc[START:]).get("Sharpe", np.nan)
        pi[c] = row
    PI = pd.DataFrame(pi).T; PI.index.name = "Instrument"; PI.to_csv(RES / f"per_instrument_{pname}.csv"); emit(f"Sharpe tung instrument (dung rieng le) - {pname}", PI, f2=tuple(PI.columns))
    all_results[pname].update(net=net, W=W, T=T, C=C, corr=corr, yr=yr, G=G, out=out)

# ---- benchmark mua-va-giu thuan ----
y = E.pq.load(E.D / "yahoo_close.parquet"); y = y[y.index.dayofweek < 5]
bh = {}
for c in ("SPY", "XAUUSD"):
    s = y[c].dropna().loc[START:rend].pct_change().dropna(); bh[c + "_buyhold_unlevered"] = E.metrics(s)
BH = pd.DataFrame(bh).T[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "PctLossYears"]]; BH.index.name = "Benchmark"
emit("Mua-va-giu thuan (SPY tong loi suat; vang = GC=F chua tru lai/khong carry)", BH, pct=("CAGR", "Vol", "MaxDD", "PctLossYears"), f2=("Sharpe", "Calmar"))

# ================= FIGURES =================
plt.rcParams.update({"figure.dpi": 130, "axes.grid": True, "grid.alpha": .25, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
COL = {"TSMOM12": "#1f77b4", "MA50/200": "#2ca02c", "DONCH55/20": "#17becf", "CARRY_k3": "#ff7f0e", "RSI2_10/90": "#d62728", "BOLL20/2": "#e377c2",
       "BUYHOLD": "#7f7f7f", "COMBO4(trend3+carry)": "#000000", "COMBO5(+RSI2)": "#8c564b", "TREND3": "#9467bd"}
for pname in PANELS:
    W = all_results[pname]["W"]
    fig, ax = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for c in W.columns:
        eq = (1 + W[c].dropna()).cumprod(); ax[0].plot(eq.index, eq, label=c, color=COL.get(c), lw=2 if "COMBO4" in c else 1.1)
        dd = eq / eq.cummax() - 1; ax[1].plot(dd.index, dd, color=COL.get(c), lw=.9)
    ax[0].set_yscale("log"); ax[0].set_title(f"Von (log, sau chi phi, vol muc tieu 10%) - {pname}"); ax[0].legend(ncol=3, fontsize=7)
    ax[1].set_title("Drawdown"); fig.tight_layout(); fig.savefig(FIG / f"fig1_equity_dd_{pname}.png"); plt.close(fig)
    corr = all_results[pname]["corr"]; fig, ax = plt.subplots(figsize=(7, 6)); im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=60, ha="right", fontsize=7); ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index, fontsize=7)
    for i in range(len(corr)):
        for j in range(len(corr)): ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=6)
    ax.grid(False); fig.colorbar(im); ax.set_title(f"Tuong quan loi suat ngay - {pname}"); fig.tight_layout(); fig.savefig(FIG / f"fig3_corr_{pname}.png"); plt.close(fig)
    T = all_results[pname]["T"]; fig, ax = plt.subplots(figsize=(8, 5)); T2 = T.sort_values("Sharpe")
    ax.errorbar(T2["Sharpe"], range(len(T2)), xerr=[T2["Sharpe"] - T2["SharpeLo"], T2["SharpeHi"] - T2["Sharpe"]], fmt="o", color="#1f77b4", capsize=3)
    ax.axvline(0, color="k", lw=.8); ax.set_yticks(range(len(T2))); ax.set_yticklabels(T2.index, fontsize=8); ax.set_xlabel("Sharpe (95% block-bootstrap CI)"); ax.set_title(f"Sharpe va khoang tin cay - {pname}")
    fig.tight_layout(); fig.savefig(FIG / f"fig4_sharpe_ci_{pname}.png"); plt.close(fig)
    G = all_results[pname]["G"]; fig, ax = plt.subplots(figsize=(10, 4.5)); cols = [COL.get({"tsmom": "TSMOM12", "ma": "MA50/200", "donch": "DONCH55/20", "rsi2": "RSI2_10/90", "boll": "BOLL20/2", "carry": "CARRY_k3"}[k]) for k in G["kind"]]
    ax.bar(range(len(G)), G["Sharpe"], color=cols); ax.axhline(0, color="k", lw=.8); ax.set_xticks(range(len(G))); ax.set_xticklabels(G.index, rotation=75, ha="right", fontsize=6.5)
    ax.set_title(f"Do nhay tham so: Sharpe sau chi phi cua moi cau hinh trong luoi - {pname}"); fig.tight_layout(); fig.savefig(FIG / f"fig5_sensitivity_{pname}.png"); plt.close(fig)
    C = all_results[pname]["C"]; fig, ax = plt.subplots(figsize=(9, 4.5)); C.plot.bar(ax=ax, width=.8); ax.axhline(0, color="k", lw=.8); ax.set_title(f"Sharpe theo gia dinh chi phi - {pname}"); ax.set_xlabel("")
    plt.xticks(rotation=40, ha="right", fontsize=7); fig.tight_layout(); fig.savefig(FIG / f"fig7_costs_{pname}.png"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for c in ("TSMOM12", "MA50/200", "DONCH55/20", "CARRY_k3", "COMBO4(trend3+carry)"):
        s = all_results[pname]["net"][c].dropna(); rs = s.rolling(756).mean() / s.rolling(756).std() * np.sqrt(252); ax.plot(rs.index, rs, label=c, color=COL[c], lw=1.2)
    ax.axhline(0, color="k", lw=.8); ax.set_title(f"Sharpe truot 3 nam - {pname}"); ax.legend(fontsize=7, ncol=3); fig.tight_layout(); fig.savefig(FIG / f"fig8_rolling_sharpe_{pname}.png"); plt.close(fig)
    yr = all_results[pname]["yr"]; fig, ax = plt.subplots(figsize=(10, 6)); im = ax.imshow(yr.T.values * 100, cmap="RdYlGn", vmin=-25, vmax=25, aspect="auto")
    ax.set_xticks(range(len(yr))); ax.set_xticklabels(yr.index, rotation=90, fontsize=7); ax.set_yticks(range(yr.shape[1])); ax.set_yticklabels(yr.columns, fontsize=7); ax.grid(False)
    for i in range(yr.shape[1]):
        for j in range(len(yr)): ax.text(j, i, f"{yr.values[j, i]*100:.0f}", ha="center", va="center", fontsize=5.5)
    ax.set_title(f"Loi suat theo nam (%) - {pname}"); fig.colorbar(im); fig.tight_layout(); fig.savefig(FIG / f"fig9_yearly_{pname}.png"); plt.close(fig)
rb = all_results["A_FX7"]["rand"]; T = all_results["A_FX7"]["T"]
fig, ax = plt.subplots(1, 6, figsize=(18, 3.4), sharey=True)
for a, nm in zip(ax, rb):
    a.hist(rb[nm], bins=25, color="#bbbbbb"); a.axvline(T.loc[nm, "Sharpe"], color="r", lw=2); a.set_title(f"{nm}\nthat={T.loc[nm, 'Sharpe']:.2f}", fontsize=9)
fig.suptitle("Kiem soat dich-thoi-gian: phan phoi Sharpe khi tin hieu bi dich ngau nhien (do = chien luoc that) - panel A", fontsize=10); fig.tight_layout(); fig.savefig(FIG / "fig6_random_baseline_A.png"); plt.close(fig)

summary.append(f"\n\nTong so cau hinh da thu (grid x 2 panel) N = {N_TRIALS}; std Sharpe ngay giua cac cau hinh = {SRV.std(ddof=1):.5f}; SR0 nam hoa ky vong cua max-trong-N = {E.deflated_sharpe(pd.Series(np.random.default_rng(0).normal(0, .01, 1000)), SRV, N_TRIALS)[1]:.2f}")
(RES / "summary.md").write_text("\n".join(summary), encoding="utf-8")
print("\nXONG. N_TRIALS =", N_TRIALS)
