#!/usr/bin/env python3
"""P-007: do tre tick->client qua WS /api/v1/rt (nginx) = now - ts trong tin nhan (cung dong ho VPS), 20 giay, 1 ket noi. Can PERF_USER/PERF_PASS. Chi doc."""
import asyncio, json, os, sys, time, statistics, urllib.request, datetime
import websockets
BASE = "http://127.0.0.1:8580"
body = json.dumps({"platform": "master", "login": os.environ["PERF_USER"], "secret": os.environ["PERF_PASS"]}).encode()
with urllib.request.urlopen(urllib.request.Request(BASE + "/auth/login", body, {"content-type": "application/json", "Origin": BASE})) as x:
    ck = "; ".join(h.split(";")[0] for h in x.headers.get_all("Set-Cookie"))
def ts_of(m):
    for k in ("ts", "time", "t", "ts_ms"):
        v = m.get(k) if isinstance(m, dict) else None
        if v is None and isinstance(m, dict) and isinstance(m.get("data"), dict): v = m["data"].get(k)
        if v is None: continue
        if isinstance(v, (int, float)): return v / 1000 if v > 1e11 else v
        try: return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
        except Exception: pass
async def main():
    lat = []; n = 0; sample = None
    async with websockets.connect("ws" + BASE[4:] + "/api/v1/rt?topics=q:EURUSD,q:XAUUSD,q:GBPUSD,q:USDJPY,q:USDCAD,q:AUDUSD", additional_headers={"Cookie": ck, "Origin": BASE}) as w:
        end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 20)
        while time.time() < end:
            try: raw = await asyncio.wait_for(w.recv(), 5)
            except asyncio.TimeoutError: continue
            n += 1; m = json.loads(raw); now = time.time() * 1000
            for it in (m.get("m") or []) if m.get("t") == "b" else []:
                if it.get("t") == "d" and isinstance(it.get("d"), dict) and it["d"].get("t"): lat.append((now - it["d"]["t"]) / 1000)   # d.t = ms thoi diem tick (EA/nguon)
    lat.sort(); q = lambda p: round(lat[min(len(lat) - 1, int(len(lat) * p))] * 1000) if lat else None
    print(json.dumps({"msgs": n, "with_ts": len(lat), "p50_ms": q(.5), "p95_ms": q(.95), "max_ms": q(1), "note": "now - d.t cua tick (ms), gom ca tre nguon->bridge->WS; ky ky tick tu EA"}, ensure_ascii=False))
asyncio.run(main())
