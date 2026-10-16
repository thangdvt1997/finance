"""Chẩn đoán: nạp nến tới 1 mốc rồi in cấu trúc pivot/lead mà từng kịch bản nhìn thấy. (dev, chạy trên VPS)
   python tools/dbg.py /fx/x.csv 2026-09-27T23:30:00Z KB-3"""
import sys

from pattern_engine.common import Ctx, lead_wave
from pattern_engine.csvio import load_csv, parse_ts
from pattern_engine.detector import Detector
from pattern_engine.specs import load_specs

path, upto, pid = sys.argv[1], parse_ts(sys.argv[2]), sys.argv[3]
specs = load_specs()
d = Detector("X", "M15", specs, [pid])
for b in load_csv(path):
    if b.ts > upto:
        break
    d.feed(b)
s = d.s
i = len(s) - 1
P = specs[pid]["params"]
print("bar", i, s.ts[i], "atr", round(s.atr[i], 2))
for k, pv in zip(d.zzs, d._pvs):
    print("== scale", k.k, "pivots (last 12):")
    for p in pv[-12:]:
        print("   ", p.kind, p.i, f"{s.ts[p.i]:%m-%d %H:%M}", p.price, "prov" if p.conf_i < 0 else "")
    ctx = Ctx(s, pv, i, d._cache, d._pvs[0])
    n = len(pv)
    # ứng viên sóng dẫn: mọi đáy pivot, mọi đỉnh trước đó -> lý do loại
    shown = 0
    for kk in range(n - 1, max(-1, n - 16), -1):
        l1 = pv[kk]
        if l1.is_high:
            continue
        for jj in range(kk - 1, max(-1, kk - 15), -1):
            h0 = pv[jj]
            if not h0.is_high or h0.price <= l1.price:
                continue
            hn = (h0.price - l1.price) / s.atr[l1.i]
            if hn < P["lead_min_atr"]:
                continue
            r = lead_wave(ctx, h0, l1, P)
            a, b = h0.i + 1, l1.i
            hi_ok = s.hi(h0.i, l1.i) <= h0.price + 1e-9 and s.lo(h0.i, l1.i) >= l1.price - 1e-9
            if shown < 14:
                print(f"   lead H{h0.i} {h0.price:.1f} -> L{l1.i} {l1.price:.1f}: hn={hn:.1f} extremes_ok={hi_ok} longred={s.longred_count(a, b)} "
                      f"greenbody={s.green_body_share(a, b):.0%} => {'OK' if r else 'no'}")
                shown += 1
    sc = specs[pid]
    from pattern_engine.patterns import PATTERNS
    sets = PATTERNS[pid](sc).scan(ctx)
    print("   scan ->", [(x.key, x.state, "".join('+' if t['ok'] else '-' for t in x.steps), [t['detail'] for t in x.steps]) for x in sets])
