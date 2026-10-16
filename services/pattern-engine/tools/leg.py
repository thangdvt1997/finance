"""Thống kê 1 nhịp giảm [i0,i1]: nến đỏ dài, tỷ lệ xanh, độ dài theo ATR (dev). python tools/leg.py /fx/x.csv i0 i1 [impulse_bars]"""
import sys

from pattern_engine.csvio import load_csv
from pattern_engine.series import Series

path, i0, i1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
s = Series(14, 1.5)
for b in load_csv(path):
    s.append(b)
for w in (0, 8, 12, 20, 30):
    a, e = i0 + 1, i1 if w == 0 else min(i1, i0 + w)
    n = e - a + 1
    print(f"window={w or 'all'} n={n} longred={s.longred_count(a, e)} green={s.green_count(a, e)}/{n}={s.green_count(a, e) / n:.0%}")
h = s.h[i0] - s.l[i1]
print(f"height={s.h[i0] - s.l[i1]:.1f} atr@l1={s.atr[i1]:.2f} -> {h / s.atr[i1]:.1f} ATR")
print("seq:", "".join(("L" if (s.c[j] < s.o[j] and s.body(j) / s.atr_ref(j) >= 1.5) else ("r" if s.c[j] < s.o[j] else "g")) for j in range(i0 + 1, i1 + 1)))
rng = range(i0 + 1, i1 + 1)
gb = sum(s.body(j) for j in rng if s.c[j] > s.o[j])
rb = sum(s.body(j) for j in rng if s.c[j] < s.o[j])
print(f"green body share={gb / (gb + rb):.0%}  net/sum_body={(s.h[i0] - s.l[i1]) / (gb + rb):.2f}")
for k in (0.6, 0.8, 1.0, 1.2):
    print(f"red body>={k}atr: {sum(1 for j in rng if s.c[j] < s.o[j] and s.body(j) / s.atr_ref(j) >= k)}", end="  ")
print()
print("red bodies/atr:", [round(s.body(j) / s.atr_ref(j), 1) for j in rng if s.c[j] < s.o[j]][:25])
