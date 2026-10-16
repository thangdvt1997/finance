import numpy as np, pandas as pd
from vn_common import *
from vn_engine import *
from vn_strats import *
df = load_raw(); P = Panel(df)
S = P.mom(252, 21); tr = triggers(P, "M", None, "M")
st = int(np.searchsorted(P.dates, START) - 5)
res = simulate(P, momentum(P, S, 15, 100), tr, Cfg(start=st), want_log=True)
nav = res["nav"]; r = res["ret"]
print(r.sort_values().head(5)); print(r.sort_values().tail(5))
print(nav.iloc[:12]); print(res["expo"].iloc[:12])
print([ (str(a.date()),b,c,round(d),round(e)) for a,b,c,d,e in res["log"][:30]])
i0 = tr[0]; print("first trig", P.dates[i0], "decide ->", momentum(P,S,15,100)(i0))
print("n elig on first trig", int((P.rank_tv[i0] <= 100).sum()), int(np.isfinite(S[i0]).sum()))
print(pd.Series(res["expo"]).resample("YE").mean())
