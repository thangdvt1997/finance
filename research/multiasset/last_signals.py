"""Tin hieu ensemble (backtest) + tin hieu 'plugin paper-trader' (TSMOM12-1 & MA200) o phien cuoi trong dataset, de doi chieu dau voi paper-trader.
Xuat JSON: {asset: {ens, tsmom121, ma200, plugin}} + ngay. python last_signals.py"""
import json, sys
from ma_engine import *
R, rf = pd.read_parquet(DATA / "excess_returns.parquet"), pd.read_parquet(DATA / "rf.parquet")["rf"]
ctx = Ctx(R, rf, CORE); I = ctx.I
ens, ts, ma = sig_ens(I), sig_tsmom(I, 252, 21), sig_ma(I, 200)
d = I.index[-1] if len(sys.argv) < 2 else I.index[I.index <= pd.Timestamp(sys.argv[1])][-1]
plugin = ts.where((ts > 0) & (ma > 0), 0.0).where(~((ts < 0) & (ma < 0)), -1.0).where(ts.notna() & ma.notna())
out = {"date": str(d.date())}
for c in CORE:
    f = lambda s: None if pd.isna(s.loc[d, c]) else round(float(s.loc[d, c]), 3)
    out[c] = {"ens": f(ens), "tsmom121": f(ts), "ma200": f(ma), "plugin_rule": f(plugin)}
(OUT / ("ens_last.json" if len(sys.argv) < 2 else f"ens_{d.date()}.json")).write_text(json.dumps(out, indent=1))
print(json.dumps(out))
