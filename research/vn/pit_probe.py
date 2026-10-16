"""Kiem tra point-in-time cua ratios PE/PB VNDirect: EPS_ttm ngam dinh = close/PE thay doi vao ngay nao so voi cuoi quy?"""
import gzip, json, numpy as np, pandas as pd
import fetch_vn as fv
res = {}
for code in ["FPT", "VNM", "HPG", "VCB", "MWG", "SSI", "PNJ", "REE"]:
    pe = pd.DataFrame(fv.fetch_all("ratios", f"code:{code}~ratioCode:PRICE_TO_EARNINGS~reportDate:gte:2017-12-01", sort="reportDate"))
    pe["d"] = pd.to_datetime(pe.reportDate); pe = pe.set_index("d")["value"].sort_index()
    px = pd.DataFrame(fv.fetch_all("stock_prices", f"code:{code}~date:gte:2017-12-01"))
    px["d"] = pd.to_datetime(px["date"]); px = px.set_index("d").sort_index()
    c = px["close"].astype(float) * 1000; ac = px["adClose"].astype(float) * 1000
    j = pd.concat([c, pe], axis=1, keys=["c", "pe"]).dropna()
    j["eps"] = j.c / j.pe
    # EPS ngam dinh: tim buoc nhay > 2% (so voi 3 ngay truoc)
    e = j.eps; chg = (e / e.shift(1) - 1).abs()
    steps = chg[chg > 0.02].index
    # loai bo ngay do gia (nhay do chia tach): chi lay buoc ma gia (close) khong nhay
    pr = (j.c / j.c.shift(1) - 1).abs()
    ev = [d for d in steps if pr.loc[d] < 0.5]
    lags = []
    for d in ev:
        qe = (d - pd.offsets.QuarterEnd(0)) if False else d.to_period("Q").start_time - pd.Timedelta(days=1)   # cuoi quy TRUOC ngay d
        lags.append((d, (d - qe).days))
    res[code] = lags
    print(code, "n_steps", len(ev), "lag(days since prev quarter end) of EPS steps:", [(str(d.date()), l) for d, l in lags][:24], flush=True)
allags = [l for v in res.values() for _, l in v]
print("hist of lag (days): ", np.histogram(allags, bins=[0, 7, 15, 25, 35, 45, 60, 75, 95])[0].tolist(), "n", len(allags))
