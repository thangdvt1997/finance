#!/usr/bin/env python3
"""P-004: kich thuoc/thoi gian tai bundle JS/CSS cua web-ui (cookie master thu) qua nginx. Dung: PERF_USER/PERF_PASS python3 p_bundle.py [BASE] [login_platform=master]
Ra JSON data/research/program/perf/bundle_<port>.json. Chi GET, tai tuan tu."""
import gzip, json, os, re, sys, time, urllib.request, urllib.error
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8580"; PLAT = sys.argv[2] if len(sys.argv) > 2 else "master"
body = json.dumps({"platform": PLAT, "login": os.environ["PERF_USER"], "secret": os.environ["PERF_PASS"]}).encode()
with urllib.request.urlopen(urllib.request.Request(BASE + "/auth/login", body, {"content-type": "application/json", "Origin": BASE})) as x:
    ck = "; ".join(h.split(";")[0] for h in x.headers.get_all("Set-Cookie"))
def get(p):
    r = urllib.request.Request(BASE + p, headers={"Cookie": ck, "Accept-Encoding": "gzip"}); t = time.time()
    with urllib.request.urlopen(r) as x:
        b = x.read(); dt = time.time() - t; enc = x.headers.get("Content-Encoding")
        raw = gzip.decompress(b) if enc == "gzip" else b; return dt, len(b), enc, x.headers.get("Cache-Control"), raw
t, n, enc, cc, html = get("/")
assets = sorted(set(re.findall(r'(?:src|href)="(/[^"]+\.(?:js|css))"', html.decode("utf8", "replace"))))
rows = [{"path": "/", "ms": round(t * 1000), "wire_bytes": n, "enc": enc}]
for a in assets:
    t, n, enc, cc, _ = get(a); rows.append({"path": a, "ms": round(t * 1000), "wire_bytes": n, "raw_bytes": len(_), "enc": enc, "cache": cc})
tot = sum(r["wire_bytes"] for r in rows)
res = {"base": BASE, "assets": rows, "total_wire_kb": round(tot / 1024), "js_kb": round(sum(r["wire_bytes"] for r in rows if r["path"].endswith(".js")) / 1024), "css_kb": round(sum(r["wire_bytes"] for r in rows if r["path"].endswith(".css")) / 1024)}
json.dump(res, open(f"/root/trading-system/data/research/program/perf/bundle_{BASE.rsplit(':',1)[-1]}.json", "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "assets"}), len(rows), "files")
