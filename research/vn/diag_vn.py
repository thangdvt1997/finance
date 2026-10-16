"""Kiem tra chat luong du lieu + universe theo thoi diem (khong chay chien luoc)."""
import json, numpy as np, pandas as pd
from vn_common import *
from vn_engine import *
from vn_strats import *
df = load_raw(); P = Panel(df)
now = json.load(open(DATA / "vn_universe_now.json"))
meta = pd.read_parquet(DATA / "vn_meta.parquet").set_index("code")
print("rows", len(df), "codes", df.code.nunique(), "dates", P.T, P.dates[0].date(), P.dates[-1].date(), "ETF codes", int(P.is_etf.sum()))
print("floors on last date", P.floor.iloc[-1].value_counts().to_dict())
print("codes per year (rows/day):", pd.Series(P.has.sum(axis=1), index=P.dates).resample("YE").mean().round(0).astype(int).to_dict())
# ---- dieu chinh gia: nhay ad/raw
rr = pd.DataFrame(P.C, index=P.dates, columns=P.codes).pct_change(fill_method=None); ra = P.ACd.pct_change(fill_method=None)
jump = (1 + ra) / (1 + rr) - 1
for c in ["VNM", "VCB", "FPT", "HPG"]:
    j = jump[c].dropna(); j = j[j.abs() > 0.002]
    print(c, "n_adj_days", len(j), "small(<3%)", int((j.abs() < 0.03).sum()), "mid(3-12%)", int(((j.abs() >= 0.03) & (j.abs() < 0.12)).sum()), "big(>12%)", int((j.abs() >= 0.12).sum()))
print("VNM adj jumps:", [(str(d.date()), round(v, 3)) for d, v in jump["VNM"].dropna()[lambda s: s.abs() > 0.002].items()][:30])
# ---- gia tri bat thuong: |ret dieu chinh| > 25% o ma trong top-100 thanh khoan, trong khi gia tho nam trong bien
bad = []
for j, c in enumerate(P.codes):
    s = ra[c]; m = (s.abs() > 0.25) & (P.rank_tv[:, j] <= 100)
    for d in s.index[m.values]: bad.append((c, str(d.date()), round(float(s[d]), 3), round(float(rr[c][d]), 3), round(float(jump[c][d]), 3)))
print("n |adret|>25% in top100:", len(bad), "of which raw-in-band(|raw|<0.12):", sum(1 for b in bad if abs(b[3]) < 0.12))
print(bad[:25])
# ---- universe theo thoi diem
for d in ["2014-03-31", "2018-03-30", "2022-03-31", "2026-10-09"]:
    i = P.dates.get_indexer([pd.Timestamp(d)], method="pad")[0]
    top = np.argsort(np.where(np.isfinite(P.rank_tv[i]), P.rank_tv[i], 1e9))[:12]
    print(d, "n_elig", int(np.isfinite(P.rank_tv[i]).sum()), "top12:", [P.codes[j] for j in top])
i = P.T - 1; top30 = set(P.codes[j] for j in np.flatnonzero(P.rank_tv[i] <= 30)); top100 = set(P.codes[j] for j in np.flatnonzero(P.rank_tv[i] <= 100))
print("PIT top30 vs VN30 hien tai: overlap", len(top30 & set(now["vn30"])), "/30;  top100 vs VN100: ", len(top100 & set(now["vn100"])), "/100")
# ---- survivorship: ty le thanh vien top-100 tai ngay rebalance KHONG con niem yet o cuoi mau
alive = P.last_idx >= P.T - 5
rows = []
for d in period_ends(P.dates, "Q", START):
    m = np.flatnonzero(P.rank_tv[d] <= 100)
    rows.append((str(P.dates[d].date()), len(m), int((~alive[m]).sum())))
t = pd.DataFrame(rows, columns=["date", "n", "dead_by_2026"]); t["year"] = t.date.str[:4]
print(t.groupby("year").agg(n=("n", "mean"), dead=("dead_by_2026", "mean")).round(1).T.to_string())
print("tong ma chet tung vao top-100 (>=1 lan):", len(set(P.codes[j] for d in period_ends(P.dates, "Q", START) for j in np.flatnonzero(P.rank_tv[d] <= 100) if not alive[j])),
      "/", len(set(P.codes[j] for d in period_ends(P.dates, "Q", START) for j in np.flatnonzero(P.rank_tv[d] <= 100))))
# ---- so khop VNI proxy
idx_raw = pd.read_parquet(DATA / "vn_index_raw.parquet"); vni, st = build_vni(P, idx_raw); print("VNI proxy vs real:", st)
# ---- thanh khoan: GTGD TB60 cua top-100 (ty VND/ngay) theo nam, va thanh vien thu 15/50/100
for y in [2014, 2016, 2018, 2020, 2022, 2024, 2026]:
    i = P.dates.get_indexer([pd.Timestamp(f"{y}-06-30")], method="pad")[0]
    v = np.sort(P.tv60.values[i][np.isfinite(P.tv60.values[i]) & (P.rank_tv[i] <= 100)])[::-1] / 1e9
    print(y, "top100 GTGD TB60 (ty VND/ngay): #1", round(v[0], 1), "#15", round(v[14], 1), "#50", round(v[49], 1), "#100", round(v[min(99, len(v) - 1)], 2))
# ---- ETF E1VFVN30
j = P.cidx["E1VFVN30"]; print("E1VFVN30 first", P.dates[P.first_idx[j]].date(), "last", P.dates[P.last_idx[j]].date())
# ---- cac chi so
print(idx_raw.groupby("code").date.agg(["min", "max", "count"]).to_string())
