"""Dung bang loi suat excess da tai san + bang chat luong du lieu. Chay tren VPS: python build_dataset.py
Dau ra: $DATA/excess_returns.parquet, $DATA/rf.parquet, $RESULTS/data_quality_multiasset.csv, $RESULTS/data_checks.txt"""
import sys, numpy as np, pandas as pd
from ma_common import *
OUT.mkdir(parents=True, exist_ok=True)
raw = pd.read_parquet(DATA / "raw_yahoo.parquet"); fred = pd.read_parquet(DATA / "fred.parquet")
ecb = pd.read_parquet(DATA / "ecb.parquet"); rates = pd.read_parquet(DATA / "rates3m.parquet")
log = []
cal = pd.bdate_range("1976-06-01", pd.Timestamp(raw.index.max()))
dtd = pd.Series(cal, index=cal).diff().dt.days.fillna(1).values  # so ngay lich giua 2 phien
acc = pd.Series(dtd / 365.0, index=cal)
rf = (fred["DTB3"].reindex(cal).ffill() / 100.0).shift(1).bfill()      # lai T-bill 3M (biet tai t-1)
rfd = rf * acc                                                          # tien mat tich luy / phien


def yh(t, col):
    return raw[(t, col)].dropna()


def clean_ret(price, name, thr=0.25):
    """price tren lich cal (chua ffill). Spike = |r|>thr va dao chieu gan nhu het ngay sau (bad print) -> loai."""
    s = price.reindex(cal)
    first, last = s.first_valid_index(), s.last_valid_index()
    s = s.loc[first:last].ffill(limit=7)
    r = s.pct_change()
    bad = 0
    ab = r.abs()
    cand = r.index[(ab > thr).values]
    for d in cand:
        i = r.index.get_loc(d)
        if i + 1 < len(r) and np.sign(r.iloc[i]) != np.sign(r.iloc[i + 1]) and abs(r.iloc[i] + r.iloc[i + 1]) < 0.5 * abs(r.iloc[i]):
            r.iloc[i] = 0.0; r.iloc[i + 1] = 0.0; bad += 1
            log.append(f"SPIKE removed {name} {d.date()} ({ab[d]:.0%})")
    return r, bad


def bond_ret(y_series, M):
    """Par-bond constant-maturity: mua o t-1 voi coupon = y(t-1), dinh gia lai o t voi dao han M-dt, yield y(t). TR = gia moi + coupon tich luy."""
    y = y_series.reindex(cal).ffill(limit=7) / 100.0
    yp = y.shift(1); dt = acc
    T = (M - dt)
    n = 2 * T; i = y / 2
    a = (1 - (1 + i) ** (-n)) / i
    p = yp / 2 * a + (1 + i) ** (-n)
    return (p - 1 + yp * dt)


R = {}; info = {}
for k, (cl, c, q, t) in ASSETS.items():
    if cl != "eq": continue
    if k == "VNM":
        s = yh(t, "adjclose"); r, b = clean_ret(s, k); r = r - rfd
    else:
        s = yh(t, "close"); r, b = clean_ret(s, k); r = r + (q / 100.0) * acc - rfd
    R[k] = r
for k, (cl, c, M, t) in ASSETS.items():
    if cl != "bond": continue
    if k == "UST30":
        r30 = bond_ret(fred["DGS30"], 30); r20 = bond_ret(fred["DGS20"], 20)
        ok30 = fred["DGS30"].reindex(cal).ffill(limit=7).notna() & fred["DGS30"].reindex(cal).shift(1).ffill(limit=7).notna()
        r = r30.where(ok30 & r30.notna(), r20)
        first = fred["DGS30"].first_valid_index()
        r = r.loc[first:]
        info["UST30_gap_filled_days(DGS20 proxy)"] = int((~(ok30 & r30.notna()) & (cal > first)).sum())
    else:
        r = bond_ret(fred[t], M); r = r.loc[fred[t].first_valid_index():]
    R[k] = r - rfd
# FX: ECB spot + carry OECD (tre 1 thang)
rt = rates.copy(); rt["JPY"] = rt["JPY"].fillna(0.1); rt["CHF"] = rt["CHF"].bfill()
rt = (rt.shift(1) / 100.0).reindex(rt.index.union(cal)).sort_index().ffill().reindex(cal)
FXB = {"EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"), "AUDUSD": ("AUD", "USD"), "USDCAD": ("USD", "CAD"), "USDCHF": ("USD", "CHF"), "NZDUSD": ("NZD", "USD")}
for k, (b, q_) in FXB.items():
    r, _ = clean_ret(ecb[k], k, thr=0.08)
    R[k] = r + (rt[b] - rt[q_]) * acc
# commodities (+crypto)
for k, (cl, c, _, t) in ASSETS.items():
    if cl not in ("metal", "energy", "agri", "crypto"): continue
    parts = t.split(">")
    seg = []
    for p in parts:
        if p.startswith("FRED:"):
            s = fred[p[5:]]; r, _ = clean_ret(s.where(s > 0), k, thr=0.4); seg.append(r)
        else:
            col = "close" if p in ("GC=F", "SI=F", "HG=F") else "adjclose"
            r, _ = clean_ret(yh(p, col), k, thr=0.4); seg.append(r)
    if len(seg) == 2:
        s0, s1 = seg; st = s1.first_valid_index()
        r = pd.concat([s0.loc[:st - pd.Timedelta(days=1)], s1.loc[st:]])
        info[k + "_splice_at"] = str(st.date())
    else:
        r = seg[0]
    R[k] = r - rfd
R = pd.DataFrame(R).reindex(cal)[list(ASSETS.keys())]
for c in R:
    f, l = R[c].first_valid_index(), R[c].last_valid_index(); R.loc[f:l, c] = R.loc[f:l, c].fillna(0.0)
R.iloc[0] = np.nan
R.to_parquet(DATA / "excess_returns.parquet"); rf.to_frame("rf").to_parquet(DATA / "rf.parquet")

rows = []
for k, (cl, c, q, t) in ASSETS.items():
    if k in FXB: src = "ECB/Frankfurter spot + OECD 3M carry"; present = ecb[k].dropna().index
    elif cl == "bond": src = f"FRED {t} -> par-bond TR proxy"; present = fred[t].dropna().index
    else:
        src = t; first = t.split(">")[0]
        present = (fred[first[5:]].dropna().index if first.startswith("FRED:") else yh(first, "close").index)
        for p in t.split(">")[1:]:
            present = present.union(yh(p, "close").index)
    r = R[k].dropna(); f, l = r.index.min(), r.index.max()
    exp = len(cal[(cal >= f) & (cal <= l)]); n_present = len(present[(present >= f) & (present <= l) & (present.dayofweek < 5)])
    miss = 1 - n_present / exp
    gaps = pd.Series(present.sort_values()).diff().dt.days; big = int((gaps > 7).sum())
    nz = (r != 0).mean()
    rows.append(dict(asset=k, cls=cl, source=src, start=f.date(), end=l.date(), years=round((l - f).days / 365.25, 1),
                     pct_weekdays_missing=round(100 * miss, 1), gaps_gt7d=big, pct_zero_ret_days=round(100 * (1 - nz), 1),
                     ann_vol=round(r.std() * np.sqrt(252), 3), max_abs_daily_ret=round(r.abs().max(), 3),
                     n_days_abs_gt_10pct=int((r.abs() > 0.10).sum()), cost_bps=c))
Q = pd.DataFrame(rows); Q.to_csv(OUT / "data_quality_multiasset.csv", index=False)
chk = []


def cmp(name, mine, etf_t, start=None):
    e = yh(etf_t, "adjclose"); e = e.reindex(cal).ffill(limit=7).pct_change() - rfd
    d = pd.concat([mine, e], axis=1).dropna(); d.columns = ["proxy", "etf"]
    d = d.loc[start:] if start else d
    chk.append(f"{name} vs {etf_t}: n={len(d)} corr_daily={d.corr().iloc[0,1]:.3f} ann_excess_proxy={d.proxy.mean()*252:.3%} ann_excess_etf={d.etf.mean()*252:.3%}")


cmp("UST10 proxy", R["UST10"], "IEF"); cmp("UST30 proxy", R["UST30"], "TLT"); cmp("UST2 proxy", R["UST2"], "SHY")
cmp("SPX index+q", R["SPX"], "SPY"); cmp("GOLD(GC=F/GLD)", R["GOLD"], "GLD", "2004-12-01")
cmp("COPPER HG=F", R["COPPER"], "CPER", "2011-12-01")
u = yh("USO", "adjclose").reindex(cal).ffill(limit=7).pct_change() - rfd
o = fred["DCOILWTICO"].where(fred["DCOILWTICO"] > 0).reindex(cal).ffill(limit=7).pct_change() - rfd
d = pd.concat([o, u], axis=1).dropna().loc["2006-04-10":]; d = d[d.index < "2020-03-01"]
chk.append(f"WTI spot(FRED) vs USO 2006-2020: corr_daily={d.corr().iloc[0,1]:.3f}  (spot khong co roll yield => proxy kem hon)")
chk.append("Spike removed: " + (", ".join(log) if log else "none"))
chk.append(f"info: {info}")
mx = R.stack().abs().sort_values(ascending=False).head(12)
chk.append("Top |daily excess ret|: " + "; ".join(f"{i[1]} {i[0].date()} {v:.1%}" for i, v in mx.items()))
chk.append("rates3m last obs per ccy: " + str({c: str(rates[c].dropna().index.max().date()) for c in rates}))
open(OUT / "data_checks.txt", "w").write("\n".join(chk)); print("\n".join(chk)); print(Q.to_string())
