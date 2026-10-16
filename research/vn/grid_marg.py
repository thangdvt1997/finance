import pandas as pd, numpy as np
from vn_common import *
G = pd.read_csv(OUT / "vn_grid.csv", index_col=0)
p = G.index.to_series().str.split("|", expand=True); p.columns = ["lbskip", "uni", "N", "freq", "w", "filt"]
G = pd.concat([G, p], axis=1)
for c in ["lbskip", "uni", "N", "freq", "w", "filt"]:
    print(c, G.groupby(c).Sharpe.agg(["median", "mean", "min", "max"]).round(3).to_dict("index"))
print(G.sort_values("Sharpe", ascending=False)[["Sharpe", "CAGR", "MaxDD", "TurnoverYr", "CostYr"]].head(12).round(3).to_string())
print(G.sort_values("Sharpe")[["Sharpe", "CAGR", "MaxDD"]].head(5).round(3).to_string())
print("U100 only, filt none/M:"); print(G[(G.uni == "U100")].groupby(["freq", "w"]).Sharpe.median().round(3).to_dict())
