"""In pivot ZigZag + nến lớn của 1 CSV (dev, chạy trên VPS).  python tools/inspect_pivots.py /fx/x.csv [from] [to] [--bars]"""
import sys

from pattern_engine.csvio import load_csv, parse_ts
from pattern_engine.series import Series
from pattern_engine.specs import load_specs
from pattern_engine.zigzag import ZigZag

path = sys.argv[1]
args = [a for a in sys.argv[2:] if not a.startswith("--")]
def _p(x):
    return parse_ts(x if "T" in x else x + "T00:00:00Z")


lo = _p(args[0]) if args else None
hi = _p(args[1]) if len(args) > 1 else None
P = next(iter(load_specs().values()))["params"]
s, zz = Series(P["atr_period"], P["lead_long_body_atr"]), ZigZag(float(__import__("os").environ.get("K", P["zigzag_atr"][0])))
bars = load_csv(path)
for b in bars:
    i = s.append(b)
    zz.update(i, b.o, b.h, b.l, b.c, s.atr[i])
print("pivots:")
for p in zz.pivots:
    t = s.ts[p.i]
    if (not lo or t >= lo) and (not hi or t < hi):
        print(f"  {p.kind} i={p.i} {t:%m-%d %H:%M} {p.price:.1f} conf@{s.ts[p.conf_i]:%m-%d %H:%M} atr={s.atr[p.i]:.2f}")
if "--bars" in sys.argv:
    for i, t in enumerate(s.ts):
        if (not lo or t >= lo) and (not hi or t < hi):
            col = "R" if s.c[i] < s.o[i] else "G"
            print(f"{i:5d} {t:%m-%d %H:%M} {col} o{s.o[i]:.1f} h{s.h[i]:.1f} l{s.l[i]:.1f} c{s.c[i]:.1f} body/atr={s.body(i) / s.atr_ref(i):.2f} atr={s.atr[i]:.2f}")
