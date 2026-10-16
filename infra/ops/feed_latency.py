#!/usr/bin/env python3
"""Do p50/p95 do tre MT5->bridge (histogram mtbridge_feed_latency_seconds, class=fx|metal|index) trong cua so N giay. CHI DOC.
Dung: python3 infra/ops/feed_latency.py [giay=60]   (chay tren host; exec vao container mt-bridge)"""
import re, subprocess, sys, time
C = "tradingsys-mt-bridge-1"
CODE = "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=5).read().decode())"
def snap(cls):
    t = subprocess.run(["docker", "exec", C, "python", "-c", CODE], capture_output=True, text=True, check=True).stdout
    b = {}
    for m in re.finditer(r'mtbridge_feed_latency_seconds_bucket\{class="%s",le="([^"]+)"\} (\S+)' % cls, t):
        b[float(m.group(1))] = float(m.group(2))
    return b
def q(d, p):
    ks = sorted(d); tot = d[ks[-1]]; tgt = p * tot; prev_k = prev_v = 0.0
    for k in ks:
        if d[k] >= tgt:
            return prev_k + (k - prev_k) * (tgt - prev_v) / max(d[k] - prev_v, 1e-9) if k != float("inf") else prev_k
        prev_k, prev_v = k, d[k]
w = float(sys.argv[1]) if len(sys.argv) > 1 else 60
CLS = ("fx", "metal", "index")
a = {c: snap(c) for c in CLS}      # cung mot cua so cho moi class
time.sleep(w)
for cls in CLS:
    b = snap(cls)
    d = {k: b[k] - a[cls].get(k, 0) for k in b}
    n = d[max(d)] if d else 0
    if n <= 0:
        print(f"{cls}: n=0 (khong co mau trong {w:g}s)"); continue
    print(f"{cls}: n={int(n)} p50={q(d,.5):.3f}s p95={q(d,.95):.3f}s p99={q(d,.99):.3f}s")
