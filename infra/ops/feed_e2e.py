#!/usr/bin/env python3
"""Do p50/p95 do tre theo cua so N giay tai gateway (CHI DOC): tick nguon -> hub nhan (rt_tick_to_gateway),
bus -> hub (rt_bus_to_gateway md.quotes), tick -> hang doi gui (rt_tick_to_send, gom throttle+flush),
gateway -> trinh duyet do client bao (rt_client_net, neu co). Chay tren host.
Dung: python3 infra/ops/feed_e2e.py [giay=60]"""
import re, subprocess, sys, time
C = "tradingsys-api-gateway-1"
CODE = "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics',timeout=5).read().decode())"
M = {"tick->hub": 'rt_tick_to_gateway_seconds', "bus->hub": 'rt_bus_to_gateway_seconds{stream="md.quotes"}',
     "tick->queue": 'rt_tick_to_send_seconds', "hub->browser": 'rt_client_net_seconds'}
def snap():
    t = subprocess.run(["docker", "exec", C, "python", "-c", CODE], capture_output=True, text=True, check=True).stdout
    out = {}
    for lab, m in M.items():
        name, _, sel = m.partition("{")
        b = {}
        for x in re.finditer(r'^%s_bucket\{(.*?)\} (\S+)$' % re.escape(name), t, re.M):
            if sel and sel.rstrip("}") not in x.group(1): continue
            b[float(re.search(r'le="([^"]+)"', x.group(1)).group(1))] = float(x.group(2))
        out[lab] = b
    return out
def q(d, p):
    ks = sorted(d); tot = d[ks[-1]]; tgt = p * tot; pk = pv = 0.0
    for k in ks:
        if d[k] >= tgt:
            return pk + (k - pk) * (tgt - pv) / max(d[k] - pv, 1e-9) if k != float("inf") else pk
        pk, pv = k, d[k]
w = float(sys.argv[1]) if len(sys.argv) > 1 else 60
a = snap(); time.sleep(w); b = snap()
for lab in M:
    d = {k: b[lab][k] - a[lab].get(k, 0) for k in b[lab]}
    n = d[max(d)] if d else 0
    print(f"{lab:13s} n=0" if n <= 0 else f"{lab:13s} n={int(n)} p50={q(d,.5):.3f}s p95={q(d,.95):.3f}s p99={q(d,.99):.3f}s")
