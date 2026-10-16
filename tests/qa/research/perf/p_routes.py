#!/usr/bin/env python3
"""P-001: do p50/p95/p99 moi route GET cua api-gateway (qua nginx web-ui, cookie master thu). Tuan tu, n=30, warm-up 2.
Dung: PERF_USER=.. PERF_PASS=.. python3 p_routes.py [BASE=http://127.0.0.1:8580] [N=30] ; ra JSON data/research/program/perf/routes.json
An toan tai: dung neu load1>40; route cham (warm-up>5s) chi do 5 mau. Chi GET. Nghen nginx limit_req 15r/s -> nghi 0.12s giua cac mau; chi tinh do tre mau ma 200."""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8580"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
SKIP = re.compile(r"/(rt|stream|events|sse)(/|$)|/media/|/pdf$|/html$|/export|/download|/metrics$|/ws")
SAMPLE = {"symbol": "EURUSD", "timeframe": "M1", "tf": "M1", "limit": "50", "days": "7", "range": "1d", "interval": "1m"}
def load1(): return float(open("/proc/loadavg").read().split()[0])
def req(path, ck, t=20):
    r = urllib.request.Request(BASE + path, headers={"Cookie": ck, "Origin": BASE}); t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=t) as x: b = x.read(); return x.status, time.time() - t0, len(b)
    except urllib.error.HTTPError as e: e.read(); return e.code, time.time() - t0, 0
    except Exception: return 0, time.time() - t0, 0
def q(a, p): return round(sorted(a)[min(len(a) - 1, int(len(a) * p))] * 1000)
def main():
    body = json.dumps({"platform": "master", "login": os.environ["PERF_USER"], "secret": os.environ["PERF_PASS"]}).encode()
    r = urllib.request.Request(BASE + "/auth/login", body, {"content-type": "application/json", "Origin": BASE})
    with urllib.request.urlopen(r) as x: ck = "; ".join(h.split(";")[0] for h in x.headers.get_all("Set-Cookie"))
    spec = json.load(urllib.request.urlopen(os.environ.get("PERF_SPEC", "http://127.0.0.1:8480/openapi.json")))
    out = []
    for path, m in spec["paths"].items():
        g = m.get("get")
        if not g or SKIP.search(path) or "{" in path: continue
        if os.environ.get("PERF_ONLY") and path not in os.environ["PERF_ONLY"].split(","): continue
        qs = []; skip = False
        for p in g.get("parameters", []):
            if p["in"] != "query" or not p.get("required"): continue
            if p["name"] in SAMPLE: qs.append(f"{p['name']}={SAMPLE[p['name']]}")
            else: skip = True
        if skip: out.append({"path": path, "status": "SKIP", "why": "tham so bat buoc la"}); continue
        url = "/api" + path + ("?" + "&".join(qs) if qs else "")
        w = 0
        while load1() > 38 and w < 600: time.sleep(10); w += 10   # cho tai ha, toi da 10 phut
        if load1() > 40: out.append({"path": path, "status": "SKIP", "why": f"load1>40 ({load1()})"}); continue
        st, t, sz = req(url, ck); time.sleep(0.12); st2, t2, _ = req(url, ck); time.sleep(0.12)
        n = 5 if max(t, t2) > 5 else N
        lat = []; codes = {}
        for _ in range(n):
            s, t, _ = req(url, ck); codes[s] = codes.get(s, 0) + 1; time.sleep(0.12)
            if s == 200: lat.append(t)
        lat = lat or [0]
        out.append({"path": url, "n": n, "codes": codes, "p50": q(lat, .5), "p95": q(lat, .95), "p99": q(lat, .99), "max": q(lat, 1), "bytes": sz})
        print(out[-1], flush=True)
    json.dump(out, open(os.environ.get("PERF_OUT", "/root/trading-system/data/research/program/perf/routes.json"), "w"), indent=1)
main()
