#!/usr/bin/env python3
"""IJ-I: tải nhẹ vào web-ui (trang chính + WebSocket /api/v1/rt). Cần phiên master thử (cookie) -> ij_run.sh tạo/xoá.
Dùng: IJ_USER=.. IJ_PASS=.. python3 ij_load.py [BASE] [USERS] [SECONDS]
nginx giới hạn ws_conn 20/IP nên WS tối đa 20; còn lại là người dùng HTTP tải trang+API với nhịp người thật."""
import asyncio, json, os, sys, time, statistics as st
import aiohttp, websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8580"
USERS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
DUR = int(sys.argv[3]) if len(sys.argv) > 3 else 90
NWS = int(os.environ.get("IJ_WS", min(20, USERS)))
lat = {"page": [], "api": [], "ws_first": []}; err = {}; ticks = [0]; wsdrop = [0]
def bad(k): err[k] = err.get(k, 0) + 1

async def login(s):
    r = await s.post(f"{BASE}/auth/login", json={"platform": "master", "login": os.environ["IJ_USER"], "secret": os.environ["IJ_PASS"]}, headers={"Origin": BASE})
    if r.status != 200: raise SystemExit(f"login {r.status}")
    ck = {}  # cookie Secure: aiohttp bỏ qua trên http -> đọc Set-Cookie thủ công
    for h in r.headers.getall("Set-Cookie", []):
        k, _, v = h.split(";")[0].partition("="); ck[k] = v
    return ck

async def http_user(i, cookies, end):
    async with aiohttp.ClientSession(headers={"Origin": BASE, "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}) as s:
        while time.time() < end:
            for kind, path in (("page", "/"), ("api", "/api/v1/symbols"), ("api", "/auth/me")):
                t = time.time()
                try:
                    async with s.get(BASE + path) as r:
                        await r.read(); lat[kind].append(time.time() - t)
                        if r.status >= 400: bad(f"{kind}_{r.status}")
                except Exception as e: bad(f"{kind}_{type(e).__name__}")
                await asyncio.sleep(2.5 + (i % 5) * 0.5)

async def ws_user(i, cookies, end):
    await asyncio.sleep(i * 0.4)  # rải kết nối: mọi VU chung 1 IP nên limit_req/limit_conn per-IP của nginx sẽ 429 nếu dồn
    ck = "; ".join(f"{k}={v}" for k, v in cookies.items())
    while time.time() < end:
        t = time.time(); first = True
        try:
            async with websockets.connect(BASE.replace("http", "ws") + "/api/v1/rt?topics=q:EURUSD,q:XAUUSD,q:GBPUSD",
                                          additional_headers={"Cookie": ck, "Origin": BASE}, open_timeout=10) as w:
                while time.time() < end:
                    try: m = await asyncio.wait_for(w.recv(), 5)
                    except asyncio.TimeoutError: continue
                    if first: lat["ws_first"].append(time.time() - t); first = False
                    ticks[0] += 1
        except Exception as e:
            bad(f"ws_{type(e).__name__}_{getattr(getattr(e, 'response', None), 'status_code', '')}"); wsdrop[0] += 1; await asyncio.sleep(3)

def q(a, p): return round(sorted(a)[min(len(a) - 1, int(len(a) * p))] * 1000) if a else None

async def main():
    async with aiohttp.ClientSession() as s0:
        cookies = await login(s0)
    end = time.time() + DUR
    await asyncio.gather(*[ws_user(i, cookies, end) for i in range(NWS)], *[http_user(i, cookies, end) for i in range(USERS)])
    out = {"users": USERS, "ws": NWS, "sec": DUR, "ticks": ticks[0], "ws_reconnects": wsdrop[0], "errors": err,
           **{k: {"n": len(v), "p50_ms": q(v, .5), "p95_ms": q(v, .95), "max_ms": q(v, 1)} for k, v in lat.items()}}
    print(json.dumps(out, ensure_ascii=False))
asyncio.run(main())
