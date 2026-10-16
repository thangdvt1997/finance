#!/usr/bin/env python3
"""P-003: xu huong RSS tu cac file stats_*.txt (p_stats.sh). In ten, MiB moi mau theo thoi gian, delta, co danh dau tang don dieu."""
import glob, re, sys
D = "/root/trading-system/data/research/program/perf"
U = {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "B": 1 / 1048576}
def mib(s): m = re.match(r"([\d.]+)(\w+)", s); return float(m.group(1)) * U[m.group(2)]
S = []
for f in sorted(glob.glob(D + "/stats_t*.txt"), key=lambda p: open(p).readline()):
    ts = open(f).readline().strip(); d = {}
    for l in open(f):
        p = l.split()
        if len(p) >= 4 and p[0].startswith("tradingsys-") and "%" in p[1]: d[p[0]] = (mib(p[2]), float(p[1].rstrip("%")))
    S.append((ts, d))
print("mau:", [s[0][11:19] for s in S])
for n in sorted(S[0][1]):
    v = [s[1].get(n, (None,))[0] for s in S]
    if None in v: continue
    inc = all(b > a for a, b in zip(v, v[1:])); d = v[-1] - v[0]
    print(f"{n[11:]:28s} " + " ".join(f"{x:8.1f}" for x in v) + f"  d={d:+8.1f} ({d / max(v[0], 1) * 100:+.1f}%)" + ("  TANG-DON-DIEU" if inc and d > 5 else ""))
