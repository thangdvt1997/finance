# P-006: do route GET noi bo cua 1 service NGAY TRONG container (khong qua nginx/gateway). Chay: docker exec -i <ctr> python - [N] < p_internal.py
# Chi route khong tham so duong dan / khong tham so bat buoc; N mau tuan tu (mac dinh 10) sau 1 warm-up; in JSON 1 dong/route.
import json, os, sys, time, urllib.request, urllib.error, re
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
PORT = os.environ.get("PORT", "8000"); B = f"http://127.0.0.1:{PORT}"
SKIP = re.compile(r"/(rt|stream|events|sse|ws|metrics|export|download|backtest|pdf|html)(/|$)|\.csv$")
hdr = {}
for k in ("API_KEY", "INTERNAL_API_KEY", "GATEWAY_API_KEY"):
    if os.environ.get(k): hdr["X-API-Key"] = os.environ[k]; break
def get(p, t=15):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(B + p, headers=hdr), timeout=t) as x: x.read(); return x.status, time.time() - t0
    except urllib.error.HTTPError as e: e.read(); return e.code, time.time() - t0
    except Exception: return 0, time.time() - t0
spec = json.load(urllib.request.urlopen(B + "/openapi.json", timeout=10))
def q(a, p): return round(sorted(a)[min(len(a) - 1, int(len(a) * p))] * 1000)
for path, m in spec["paths"].items():
    g = m.get("get")
    if not g or "{" in path or SKIP.search(path): continue
    if any(p["in"] == "query" and p.get("required") for p in g.get("parameters", [])): print(json.dumps({"path": path, "skip": "tham so bat buoc"})); continue
    if float(open("/proc/loadavg").read().split()[0]) > 40: print(json.dumps({"path": path, "skip": "load>40"})); continue
    s0, t0 = get(path); lat = []; codes = {}
    n = 3 if t0 > 5 else N
    for _ in range(n):
        s, t = get(path); codes[s] = codes.get(s, 0) + 1
        if s == 200: lat.append(t)
        time.sleep(0.05)
    print(json.dumps({"path": path, "first_ms": round(t0 * 1000), "codes": codes, "n": len(lat), "p50": q(lat, .5) if lat else None, "p95": q(lat, .95) if lat else None, "max": q(lat, 1) if lat else None}))
