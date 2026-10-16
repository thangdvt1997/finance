import time, numpy as np, pandas as pd
from vn_common import *
from vn_engine import *
from vn_strats import *
t0 = time.time()
df = load_raw(); print("rows", len(df), "codes", df.code.nunique(), "t", round(time.time()-t0,1), flush=True)
P = Panel(df); print("panel", P.T, P.N, P.dates[0], P.dates[-1], round(time.time()-t0,1), flush=True)
idx = pd.read_parquet(DATA / "vn_index_raw.parquet")
vni, st = build_vni(P, idx); print("vni", st, flush=True)
S = P.mom(252, 21)
reg = regime(vni)
tr = triggers(P, "M", None, "M")
t1 = time.time()
res = simulate(P, momentum(P, S, 15, 100), tr, Cfg(start=int(np.searchsorted(P.dates, START) - 5)))
print("sim s", round(time.time()-t1,2)); print(summarize(res, label="mom"))
res2 = simulate(P, ew_universe(P, 30), triggers(P, "Q", None, "M"), Cfg(start=int(np.searchsorted(P.dates, START) - 5)))
print(summarize(res2, label="ew30"))
print("tot", res["tot"])
