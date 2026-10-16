"""Kiem chung COT: cuc doan positioning (percentile 3 nam) -> loi suat tuan/thang ke tiep, khong look-ahead.
Tai lap: python fetch_data.py && python cot_study.py  -> ket qua trong out/cot_*.csv, in tom tat ra stdout."""
import glob, io, json, pathlib, zipfile
import numpy as np, pandas as pd
D = pathlib.Path(__file__).parent / "data"; O = pathlib.Path(__file__).parent / "out"; O.mkdir(exist_ok=True)
rng = np.random.default_rng(42)

def load_zip(patterns):
    patterns = [patterns] if isinstance(patterns, str) else patterns
    fr = []
    for f in sorted(sum((glob.glob(str(D / p)) for p in patterns), [])):
        z = zipfile.ZipFile(f)
        fr.append(pd.read_csv(z.open(z.namelist()[0]), low_memory=False))
    df = pd.concat(fr); df["date"] = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"])
    return df.drop_duplicates(["Market_and_Exchange_Names", "date"]).sort_values("date")

tff = load_zip(["fin_fut_txt_*.zip", "fut_fin_txt_*.zip"]); dis = load_zip("fut_disagg_txt*.zip")
MK = {"EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE", "GBP": "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE",
      "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE", "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
      "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE", "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE"}
PX = {"EUR": ("EURUSD", 1), "GBP": ("GBPUSD", 1), "AUD": ("AUDUSD", 1), "JPY": ("USDJPY", -1), "CAD": ("USDCAD", -1), "CHF": ("USDCHF", -1), "XAU": ("XAU", 1)}

def px(sym):
    r = json.loads((D / f"px_{sym}.json").read_text())["chart"]["result"][0]
    s = pd.Series(r["indicators"]["quote"][0]["close"], index=pd.to_datetime(r["timestamp"], unit="s").normalize(), dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()

def positions():
    out = {}
    for c, name in MK.items():
        d = tff[tff.Market_and_Exchange_Names == name].set_index("date")
        oi = d["Open_Interest_All"]
        out[(c, "LevMoney")] = (d.Lev_Money_Positions_Long_All - d.Lev_Money_Positions_Short_All) / oi
        out[(c, "AssetMgr")] = (d.Asset_Mgr_Positions_Long_All - d.Asset_Mgr_Positions_Short_All) / oi
    g = dis[dis.Market_and_Exchange_Names == "GOLD - COMMODITY EXCHANGE INC."].set_index("date")
    out[("XAU", "ManagedMoney")] = (g.M_Money_Positions_Long_All - g.M_Money_Positions_Short_All) / g.Open_Interest_All
    return out

def pct_rank(s, w=156, minp=104):
    return s.rolling(w, min_periods=minp).apply(lambda x: (x[:-1] < x[-1]).mean() + 0.5 * (x[:-1] == x[-1]).mean(), raw=True)

def fwd_ret(p, entry_dates, h_weeks, sign):
    """log-return tu close ngay vao lenh den close sau h tuan (ngay giao dich dau tien >= moc)."""
    idx = p.index; res = []
    for e in entry_dates:
        i = idx.searchsorted(e)
        if i >= len(idx): res.append(np.nan); continue
        e_d = idx[i]; j = idx.searchsorted(e_d + pd.Timedelta(days=7 * h_weeks))
        res.append(np.nan if j >= len(idx) else sign * np.log(p.iloc[j] / p.iloc[i]))
    return pd.Series(res, index=entry_dates)

def stat_boot(sig, ret, B=4000, mean_block=8):
    """Trung binh (s*ret) tren cac tuan co tin hieu; stationary bootstrap theo chi so tuan (xu ly chong lan + cum)."""
    sr = (sig * ret).to_numpy(); act = (sig != 0).to_numpy() & ~np.isnan(sr)
    n = len(sr); 
    if act.sum() < 10: return dict(n=int(act.sum()), mean=np.nan, lo=np.nan, hi=np.nan, p=np.nan, hit=np.nan)
    m = sr[act].mean(); hit = (sr[act] > 0).mean(); ms = np.empty(B); pr = 1 / mean_block
    for b in range(B):
        idx = np.empty(n, int); idx[0] = rng.integers(n)
        jump = rng.random(n) < pr; rnd = rng.integers(n, size=n)
        for t in range(1, n): idx[t] = rnd[t] if jump[t] else (idx[t - 1] + 1) % n
        a = act[idx]; ms[b] = sr[idx][a].mean() if a.any() else np.nan
    ms = ms[~np.isnan(ms)]; c = ms - ms.mean()   # p theo phan phoi tam hoa quanh 0
    p = (np.abs(c) >= abs(m)).mean()
    return dict(n=int(act.sum()), mean=m, lo=np.percentile(ms, 2.5), hi=np.percentile(ms, 97.5), p=max(p, 1 / B), hit=hit)

def bh(pv):
    pv = np.array(pv); o = np.argsort(pv); m = len(pv); q = np.empty(m); prev = 1
    for k, i in list(enumerate(o))[::-1]: prev = min(prev, pv[i] * m / (k + 1)); q[i] = prev
    return q
def holm(pv):
    pv = np.array(pv); o = np.argsort(pv); m = len(pv); q = np.empty(m); prev = 0
    for k, i in enumerate(o): prev = max(prev, min(1, pv[i] * (m - k))); q[i] = prev
    return q

if __name__ == "__main__":
    pos = positions(); rows = []
    for (c, kind), net in pos.items():
        psym, sg = PX[c]; p = px(psym); pr = pct_rank(net.dropna())
        # entry: thu Hai sau thu Sau cong bo (as_of Tue + 6 ngay) -> khong look-ahead; "naive": ngay thu Ba (look-ahead)
        for variant, off in (("honest_Mon", 6), ("naive_Tue_lookahead", 0)):
            ent = pr.index + pd.Timedelta(days=off)
            for h in (1, 4):
                r = fwd_ret(p, ent, h, sg); r.index = pr.index
                for thr in (0.10, 0.20):
                    contr = pd.Series(np.where(pr >= 1 - thr, -1, np.where(pr <= thr, 1, 0)), index=pr.index).where(pr.notna(), 0)
                    for per, (a, b) in {"all": ("2006", "2026"), "IS_2006_15": ("2006", "2015"), "OOS_2016_26": ("2016", "2026")}.items():
                        sl = slice(a, b); st = stat_boot(contr[sl], r[sl], B=2000)
                        rows.append(dict(asset=c, series=kind, variant=variant, h_weeks=h, thr=thr, period=per, **st))
    R = pd.DataFrame(rows); R.to_csv(O / "cot_contrarian_raw.csv", index=False)
    fam = R[(R.variant == "honest_Mon") & (R.period == "all")].copy()
    fam["p_bh"] = bh(fam.p.fillna(1).values); fam["p_holm"] = holm(fam.p.fillna(1).values)
    fam.to_csv(O / "cot_family_adjusted.csv", index=False)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
    print("FAMILY size", len(fam))
    print(fam[["asset", "series", "h_weeks", "thr", "n", "mean", "lo", "hi", "hit", "p", "p_bh", "p_holm"]].round(4).to_string())
    print("\nNAIVE (look-ahead) vs HONEST, thr=0.10 all periods, mean per active week")
    pv = R[(R.period == "all") & (R.thr == 0.10)].pivot_table(index=["asset", "series", "h_weeks"], columns="variant", values="mean")
    print(pv.round(4).to_string())
    print("\nIS vs OOS honest thr=0.10")
    pv = R[(R.variant == "honest_Mon") & (R.thr == 0.10)].pivot_table(index=["asset", "series", "h_weeks"], columns="period", values="mean")
    print(pv.round(4).to_string())
    # pooled panel (6 FX LevMoney, 4w) mean contrarian
    for kind in ("LevMoney", "AssetMgr"):
        sub = R[(R.variant == "honest_Mon") & (R.period == "all") & (R.series == kind) & (R.thr == 0.10)]
        print(kind, "so tai san co mean<0:", ((sub.groupby('h_weeks').apply(lambda d: (d['mean'] < 0).sum()))).to_dict(), "tren", sub.asset.nunique())
