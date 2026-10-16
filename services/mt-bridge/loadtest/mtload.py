#!/usr/bin/env python3
"""Tai gia lap 50-200 tai khoan EA gui dong thoi toi mt-bridge (CHAY TRONG CONTAINER TAM `mtload-*`, khong mang, khong Redis/DB that).

  server : bridge THAT (BridgeService + create_app) voi InMemoryRegistry chua N tai khoan `loadtest-NNNN`, publisher dem/serialize
           (khong ghi Redis/DB => khong lam ban du lieu that; don dep = xoa container). Lo them /_stats (RSS, nonce, health).
  gen    : N client asyncio (HTTP/1.1 keep-alive) gui batch day du (snapshot+vi the+lenh+quote+nen) co ky HMAC moi `interval` giay.
Kich ban: base (tat ca hop le) | mixed (them tai khoan loi: sai chu ky, replay, schema, flood, dinh chi giua chung) de kiem chung co lap loi.
Dung: xem run_loadtest.sh. READ-ONLY: chi POST /ingest/v1 (heartbeat/snapshot), khong co duong dat lenh.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import uuid

PORT = 18000
CRED = "/tmp/mtload-creds.json"


# ------------------------------------------------------------------------------------------------ server
def server(n: int) -> None:
    import uvicorn
    from tscommon import make_event  # noqa: F401

    from mtbridge.accounts import BridgeConfig
    from mtbridge.registry import InMemoryRegistry
    from mtbridge.service import BridgeService, Settings, create_app

    class SinkPub:
        """Giong Bus: serialize event (chi phi that) nhung bo di."""

        def __init__(self):
            self.n = 0
            self.bytes = 0

        async def publish(self, stream, event):
            self.bytes += len(event.model_dump_json())
            self.n += 1

    reg = InMemoryRegistry()
    creds = {}
    for i in range(n):
        aid = f"loadtest-{i:04d}"
        c = reg.create("mt5" if i % 2 else "mt4", 9_000_000 + i, status="active")
        # doi ten theo quy uoc loadtest-* (de nhan dien/don dep)
        rec = reg._recs.pop(c["account_id"])  # noqa: SLF001
        rec.account_id, rec.cfg.account_id = aid, aid
        reg._recs[aid] = rec  # noqa: SLF001
        creds[aid] = {"token": c["token"], "hmac": c["hmac_secret"], "platform": rec.platform}
    json.dump(creds, open(CRED, "w"))
    pub = SinkPub()
    svc = BridgeService(BridgeConfig(accounts=[]), pub, settings=Settings(admin_token="x", skew_s=120), registry=reg)
    app = create_app(svc, background=True)

    @app.get("/_stats")
    async def stats():
        rss = 0
        for ln in open("/proc/self/status"):
            if ln.startswith("VmRSS:"):
                rss = int(ln.split()[1]) // 1024
        return {"rss_mb": rss, "nonces": len(svc.nonces._seen), "health": len(svc.health), "gateways": len(svc.gateways), "events": pub.n, "event_mb": round(pub.bytes / 1e6, 1)}

    @app.post("/_suspend/{aid}")
    async def suspend(aid: str):
        reg.set_status(aid, "suspended")
        return {"ok": True}

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False)


# ------------------------------------------------------------------------------------------------ generator
def make_batch(aid: str, platform: str, seq: int, ts: int, nonce: str) -> dict:
    off = 3 * 3600
    now = ts + off
    b = {"v": 1, "account_id": aid, "platform": platform, "ts": ts, "server_time": now, "nonce": nonce, "seq": seq,
         "account": {"login": 9000000, "server": "Load-Srv", "currency": "USD", "leverage": 100, "balance": 10000.0, "equity": 9950.5, "margin": 200.0, "free_margin": 9750.5, "margin_level": 4975.25, "margin_mode": "hedging", "trade_allowed": False},
         "positions": [{"ticket": 1000 + k, "symbol": "EURUSD", "type": k % 2, "lots": 0.1, "open_price": 1.08, "price": 1.085, "sl": 0.0, "tp": 0.0, "profit": 5.0, "swap": 0.0, "magic": 1, "comment": "lt", "open_time": now - 3600} for k in range(5)],
         "orders": [{"ticket": 2001, "symbol": "EURUSD", "type": 2, "lots": 0.2, "price": 1.07, "sl": 0.0, "tp": 0.0, "magic": 1, "comment": "", "setup_time": now - 600}],
         "quotes": [{"symbol": s, "bid": 1.0850 + random.random() * 1e-4, "ask": 1.0852 + random.random() * 1e-4, "time": now} for s in ("EURUSD", "XAUUSD", "GBPUSD")],
         "bars": [{"symbol": s, "tf": tf, "time": now - (now % 60), "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1, "v": 10.0} for s in ("EURUSD", "XAUUSD") for tf in ("M1", "M5", "M15")],
         "agent": {"ea": "1.1", "build": 6253, "company": "LoadBroker", "rtt_ms": random.randint(10, 80), "fail": 0}}
    return b


async def http(reader, writer, method: str, path: str, headers: dict, body: bytes = b"") -> tuple[int, bytes]:
    h = {"Host": "x", "Content-Length": str(len(body)), **headers}
    writer.write((f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in h.items()) + "\r\n").encode() + body)
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    cl = 0
    for ln in head.split(b"\r\n"):
        if ln.lower().startswith(b"content-length:"):
            cl = int(ln.split(b":")[1])
    data = await reader.readexactly(cl) if cl else b""
    return status, data


async def client(aid: str, cred: dict, interval: float, dur: float, kind: str, res: dict, t_end: float, stagger: float) -> None:
    import hashlib
    import hmac as _hmac

    await asyncio.sleep(stagger)
    reader, writer = await asyncio.open_connection("127.0.0.1", PORT)
    seq, last_raw, last_sig = 0, None, None
    while time.time() < t_end:
        seq += 1
        ts = int(time.time())
        nonce = uuid.uuid4().hex
        raw = json.dumps(make_batch(aid, cred["platform"], seq, ts, nonce)).encode()
        sig = _hmac.new(cred["hmac"].encode(), f"{ts}.{nonce}.".encode() + raw, hashlib.sha256).hexdigest()
        hdr = {"Authorization": f"Bearer {cred['token']}", "X-MT-Account": aid, "Content-Type": "application/json", "X-MT-Sig": sig}
        want = 200
        if kind == "badsig" and seq % 2 == 0:
            hdr["X-MT-Sig"], want = "00" * 32, 401
        elif kind == "replay" and last_raw is not None and seq % 2 == 0:
            raw, hdr["X-MT-Sig"], want = last_raw, last_sig, 409
        elif kind == "schema" and seq % 2 == 0:
            raw = raw.replace(b'"v": 1', b'"v": 9')
            hdr["X-MT-Sig"] = _hmac.new(cred["hmac"].encode(), f"{ts}.{nonce}.".encode() + raw, hashlib.sha256).hexdigest()
            want = 422
        elif kind == "suspend":
            want = None  # 200 truoc, 403 sau khi bi dinh chi
        elif kind == "flood":
            want = None
        last_raw, last_sig = raw, hdr["X-MT-Sig"]
        n_send = 40 if kind == "flood" and seq % 2 == 0 else 1
        for _ in range(n_send):
            t0 = time.perf_counter()
            try:
                st, _ = await http(reader, writer, "POST", "/ingest/v1", hdr, raw)
            except Exception:  # noqa: BLE001
                res.setdefault("conn_err", []).append(aid)
                reader, writer = await asyncio.open_connection("127.0.0.1", PORT)
                continue
            dt = (time.perf_counter() - t0) * 1000
            res.setdefault("lat", {}).setdefault(kind, []).append(dt)
            res.setdefault("codes", {}).setdefault(kind, {}).setdefault(st, 0)
            res["codes"][kind][st] += 1
            if want is not None and st != want and not (kind in ("badsig", "replay", "schema") and st == 200 and seq % 2):
                res.setdefault("unexpected", []).append((aid, kind, st, want))
            nonce = uuid.uuid4().hex  # flood: cac lan sau cung payload khac nonce -> khong thay doi ts/nonce gia, chi de do 429
            hdr = dict(hdr)
        await asyncio.sleep(max(0.0, interval - (time.perf_counter() - t0) / 1000))
    writer.close()


def pct(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


async def gen(n: int, interval: float, dur: float, mixed: bool) -> int:
    creds = json.load(open(CRED))
    ids = list(creds)[:n]
    res: dict = {}
    t_end = time.time() + dur
    kinds = {}
    if mixed:
        bad = ids[-12:]
        for i, a in enumerate(bad[:3]):
            kinds[a] = "badsig"
        for a in bad[3:6]:
            kinds[a] = "replay"
        for a in bad[6:9]:
            kinds[a] = "schema"
        kinds[bad[9]] = "flood"
        kinds[bad[10]] = "suspend"
    tasks = [asyncio.create_task(client(a, creds[a], interval, dur, kinds.get(a, "good"), res, t_end, random.random() * interval)) for a in ids]
    if mixed:
        async def suspender():
            await asyncio.sleep(dur / 2)
            r, w = await asyncio.open_connection("127.0.0.1", PORT)
            await http(r, w, "POST", f"/_suspend/{[a for a, k in kinds.items() if k == 'suspend'][0]}", {})
            w.close()
        tasks.append(asyncio.create_task(suspender()))
    mon = []

    async def poll():
        while time.time() < t_end:
            r, w = await asyncio.open_connection("127.0.0.1", PORT)
            _, d = await http(r, w, "GET", "/_stats", {})
            mon.append(json.loads(d))
            w.close()
            await asyncio.sleep(5)

    tasks.append(asyncio.create_task(poll()))
    await asyncio.gather(*tasks)
    good = res.get("lat", {}).get("good", [])
    total = sum(sum(c.values()) for c in res.get("codes", {}).values())
    print(f"== {n} tai khoan, interval={interval}s, {dur:.0f}s, mixed={mixed}: {total} request ({total / dur:.0f} rps)")
    if good:
        print(f"good: n={len(good)} p50={statistics.median(good):.1f}ms p95={pct(good, .95):.1f}ms p99={pct(good, .99):.1f}ms max={max(good):.1f}ms")
    for k, c in sorted(res.get("codes", {}).items()):
        print(f"  {k:8s} {c}")
    print("conn_err:", len(res.get("conn_err", [])), "| unexpected:", res.get("unexpected", [])[:5])
    if mon:
        print("server:", {k: [m[k] for m in (mon[0], mon[-1])] for k in ("rss_mb", "nonces", "health", "gateways", "events")})
    bad_good = [(k, c) for k, c in res.get("codes", {}).get("good", {}).items() if k != 200]
    ok = not bad_good and not res.get("conn_err") and not res.get("unexpected")
    print("KET QUA:", "OK" if ok else f"LOI good!=200: {bad_good}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["server", "gen"])
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--dur", type=float, default=45.0)
    ap.add_argument("--mixed", action="store_true")
    a = ap.parse_args()
    if a.mode == "server":
        server(a.n)
    else:
        sys.exit(asyncio.run(gen(a.n, a.interval, a.dur, a.mixed)))
