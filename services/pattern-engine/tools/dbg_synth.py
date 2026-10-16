"""Chẩn đoán KB-4 tổng hợp: in checklist từng bước ở các nến cuối. (dev)"""
from pattern_engine.detector import Detector
from pattern_engine.specs import load_specs
from tests.test_kb4_synthetic import build

bars, idx = build()
print(idx, len(bars))
d = Detector("S", "M15", load_specs(), ["KB-4"])
for n, b in enumerate(bars):
    ev = d.feed(b)
    for k, su in d.active.items():
        if n >= idx["top3"] - 14:
            print(n, k, su.state, "".join("+" if x["ok"] else "-" for x in su.steps), [x["detail"] for x in su.steps][:5])
    for e in ev:
        print("   EVENT", n, e.state, e.reason)
    if n == idx["top3"] + 1:
        for z in d.zzs:
            print("pivots k=%s:" % z.k, [(p.kind, p.i, round(p.price, 2), p.conf_i >= 0) for p in z.view()][-12:])
print("atr tail", [round(x, 2) for x in d.s.atr[-6:]], "prices tail", [round(x, 2) for x in d.s.c[-12:]])
