"""Kiểm tra chất lượng dữ liệu -> results/data_quality.csv (+ in ra)."""
import pandas as pd, numpy as np, pathlib
import pq
R = pathlib.Path(__file__).parent; D = R/"data"; (R/"results").mkdir(exist_ok=True)
y = pq.load(D/"yahoo_close.parquet")
e = pq.load(D/"ecb_close.parquet")
rows = []
for c in y.columns:
    s = y[c].dropna(); wk = int((s.index.dayofweek >= 5).sum()); s = s[s.index.dayofweek < 5]
    r = s.pct_change().dropna()
    row = dict(asset=c, source="yahoo", start=s.index.min().date(), end=s.index.max().date(), n=len(s), weekend_rows_dropped=wk,
               max_abs_ret=round(r.abs().max(), 4), n_gt5pct=int((r.abs() > .05).sum()), n_zero_ret=int((r == 0).sum()),
               min_price=round(s.min(), 4))
    if c in e.columns:
        j = pd.concat([s, e[c]], axis=1, keys=["y", "e"]).dropna()
        rr = j.pct_change().dropna()
        row.update(corr_daily_ret_vs_ECB=round(rr.corr().iloc[0, 1], 3), corr_5d_ret_vs_ECB=round(j.pct_change(5).dropna().corr().iloc[0, 1], 3),
                   max_level_diff_pct=round(((j.y/j.e - 1).abs().max())*100, 2), median_level_diff_pct=round(((j.y/j.e - 1).abs().median())*100, 3))
    rows.append(row)
for c in e.columns:
    s = e[c].dropna(); r = s.pct_change().dropna()
    rows.append(dict(asset=c, source="ecb", start=s.index.min().date(), end=s.index.max().date(), n=len(s), max_abs_ret=round(r.abs().max(), 4),
                     n_gt5pct=int((r.abs() > .05).sum()), n_zero_ret=int((r == 0).sum()), min_price=round(s.min(), 4)))
q = pd.DataFrame(rows); q.to_csv(R/"results/data_quality.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); print(q.to_string())
print("CHF 2015-01-14..16 ECB:", e.loc["2015-01-13":"2015-01-16", "USDCHF"].round(4).to_dict())
print("CHF 2015-01-14..16 Yahoo:", y.loc["2015-01-13":"2015-01-16", "USDCHF"].round(4).to_dict())
print("WTI min:", y.WTI.min())
