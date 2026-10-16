#!/usr/bin/env python3
"""Kiểm thử TẢI hub realtime (docs/REALTIME.md "Kết quả đo"). Chạy TRONG container tạm cùng image api-gateway (có websockets/redis/orjson):
  - `pub`  : bộ phát tick tổng hợp -> XADD vào stream RIÊNG `rt.perf` (KHÔNG BAO GIỜ md.quotes/md.bars/account.*), symbol PERF1..PERFn.
  - `load` : N kết nối WS (ramp dần, một phần "chậm" không đọc socket) tới gateway TẠM (RT_EXTRA_STREAMS=rt.perf); đo snap đầu, tin/s, byte/s,
             độ trễ tick->client (d.t = ts tick gốc, cùng đồng hồ host), khoảng nhảy seq, kết nối bị đóng + lý do; kèm delta metric /metrics của gateway.
Điều phối: infra/perf/run_ws_load.sh. Header danh tính giả lập (X-Auth-Secret = AUTH_TRUST_SECRET) nhiều "người dùng" client.
Mọi bí mật lấy từ env (REDIS_URL, API_TOKEN, AUTH_TRUST_SECRET) — không in ra."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

STREAM = "rt.perf"


# ----------------------------------------------------------------------------- phát tick
async def run_pub(a) -> None:
    import redis.asyncio as aioredis
    import orjson
    r = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    syms = [f"PERF{i + 1}" for i in range(a.symbols)]
    px = {s: 1.0 + 0.1 * i for i, s in enumerate(syms)}
    interval = 0.05
    t_end = time.time() + a.duration if a.duration else float("inf")
    sent, carry, i, ne_f, en = 0, 0.0, 0, 0.0, 0
    nxt = time.perf_counter()
    while time.time() < t_end:
        carry += a.rate * interval
        n, carry = int(carry), carry - int(carry)
        p = r.pipeline(transaction=False)
        now = datetime.now(timezone.utc).isoformat()
        for _ in range(n):
            s = syms[i % len(syms)]
            i += 1
            px[s] += random.choice((-1, 1)) * 0.00001 * random.randint(1, 5)
            ts = datetime.now(timezone.utc).isoformat()
            ev = {"id": f"p{i}", "type": "quote", "source": "mt-perf", "ts": ts, "schema_version": 1, "trace_id": None,
                  "payload": {"symbol": s, "bid": round(px[s], 6), "ask": round(px[s] + 0.0001, 6), "ts": ts, "source": "mt-perf"}}
            p.xadd(STREAM, {"e": orjson.dumps(ev).decode()}, maxlen=20000, approximate=True)
        ne_f += a.erate * interval
        ne, ne_f = int(ne_f), ne_f - int(ne_f)
        for _ in range(ne):
            en += 1
            ts = datetime.now(timezone.utc).isoformat()
            ev = {"id": f"e{en}", "type": "account_status", "source": "mt-perf", "ts": ts, "schema_version": 1, "trace_id": None,
                  "payload": {"account_id": f"perf-acc{en % a.users}", "status": "connected", "reason": "perf", "ts": ts}}
            p.xadd(STREAM, {"e": orjson.dumps(ev).decode()}, maxlen=20000, approximate=True)
        if n or ne:
            await p.execute()
            sent += n
        nxt += interval
        d = nxt - time.perf_counter()
        if d > 0:
            await asyncio.sleep(d)
        else:
            nxt = time.perf_counter()
    print(json.dumps({"pub_sent": sent, "pub_events": en}), flush=True)
    await r.aclose()


# ----------------------------------------------------------------------------- tải
def pctl(v: list[float], q: float) -> float | None:
    if not v:
        return None
    s = sorted(v)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1)


async def run_worker(a) -> None:
    """Tiến trình con: mở a.n kết nối, in MỘT dòng JSON kết quả."""
    import orjson
    import websockets
    host, port = re.match(r"^wss?://([^:/]+):?(\d*)", a.url).groups()
    port = int(port or 80)
    token = os.environ.get("API_TOKEN", "")
    secret = os.environ.get("AUTH_TRUST_SECRET", "")
    loop = asyncio.get_running_loop()
    syms = [f"PERF{i + 1}" for i in range(a.symbols)]
    st = {"emsgs": 0, "egaps": 0, "msgs": 0, "frames": 0, "bytes": 0, "gaps": 0, "seqs": 0, "ok": 0, "fail": 0, "bye": {}, "closed": {}, "measuring": False}
    fails: dict[str, int] = {}
    snap_ms: list[float] = []
    lat: list[float] = []
    state: dict[int, str] = {}      # id -> open|closed:<code>
    slow_ids: set[int] = set()
    stop = asyncio.Event()
    t_meas = [0.0]

    def hdrs(i: int) -> dict:
        u = i % a.users
        h = {"X-API-Key": token, "X-User-Id": f"perf-u{u}", "X-Role": "client", "X-Accounts": f"perf-acc{u}", "X-Auth-Secret": secret}
        return h

    async def one(i: int, slow: bool) -> None:
        topics = ",".join([f"q:{syms[(i + k) % len(syms)]}" for k in range(a.topics)] + [f"e:perf-acc{i % a.users}"])
        t0 = time.perf_counter()
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if slow:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)     # nhận buffer nhỏ -> server nghẽn nhanh
            sock.setblocking(False)
            await asyncio.wait_for(loop.sock_connect(sock, (host, port)), 20)
            ws = await asyncio.wait_for(websockets.connect(f"ws://{host}:{port}/v1/rt?topics={topics}", sock=sock, additional_headers=hdrs(i),
                                                         max_queue=1 if slow else 64, compression="deflate" if a.compress else None,
                                                         open_timeout=30, ping_interval=None), 40)
        except Exception as e:  # noqa: BLE001
            st["fail"] += 1
            k = f"{type(e).__name__}:{str(e)[:60]}"
            fails[k] = fails.get(k, 0) + 1
            if sock is not None:
                sock.close()
            return
        st["ok"] += 1
        state[i] = "open"
        if slow:
            slow_ids.add(i)
            await stop.wait()
            # cuối bài: xả socket để biết server đã đóng lý do gì
            try:
                for _ in range(400):
                    m = await asyncio.wait_for(ws.recv(), 0.3)
                    if isinstance(m, str) and '"t":"bye"' in m:
                        try:
                            c = orjson.loads(m).get("c", "?")
                        except ValueError:
                            c = "?"
                        st["bye"][c] = st["bye"].get(c, 0) + 1
            except asyncio.TimeoutError:
                pass
            except Exception:  # noqa: BLE001
                pass
            state[i] = f"closed:{ws.close_code}" if ws.close_code else "open"
            return
        got_snap = False
        last: dict[str, int] = {}
        last_e: dict[str, int] = {}
        try:
            async for raw in ws:
                now_ms = time.time() * 1000.0
                if stop.is_set():
                    break
                try:
                    fr = orjson.loads(raw)
                except ValueError:
                    continue
                if fr.get("t") == "bye":
                    st["bye"][fr.get("c", "?")] = st["bye"].get(fr.get("c", "?"), 0) + 1
                    continue
                if fr.get("t") != "b":
                    continue
                meas = st["measuring"]
                if meas:
                    st["frames"] += 1
                    st["bytes"] += len(raw)
                for m in fr["m"]:
                    tt = m.get("t")
                    if tt == "snap" and not got_snap and m["k"].startswith("q:"):
                        got_snap = True
                        snap_ms.append((time.perf_counter() - t0) * 1000.0)
                    elif tt == "d" and m["k"][0] == "q":
                        q = m["q"]
                        p = last.get(m["k"])
                        if meas:
                            st["msgs"] += 1
                            if p is not None:
                                st["seqs"] += 1
                                if q > p + 1:
                                    st["gaps"] += q - p - 1
                            if len(lat) < 400_000:
                                lat.append(now_ms - m["d"]["t"])
                        last[m["k"]] = q
                    elif tt == "d" and m["k"][0] == "e" and meas:
                        st["emsgs"] += 1
                        pe, qe = last_e.get(m["k"]), m["q"]
                        if pe is not None and qe != pe + 1:
                            st["egaps"] += abs(qe - pe - 1)
                        last_e[m["k"]] = qe
                    elif tt == "d" and m["k"][0] == "e":
                        last_e[m["k"]] = m["q"]
            state[i] = f"closed:{ws.close_code}"
        except Exception as e:  # noqa: BLE001
            state[i] = f"closed:{type(e).__name__}"
        finally:
            with_code = state.get(i, "closed")
            st["closed"][with_code] = st["closed"].get(with_code, 0) + 1

    tasks = []
    gap = 1.0 / a.ramp if a.ramp > 0 else 0
    t_start = time.time()
    for i in range(a.n):
        slow = (i % 100) < a.slow_pct
        tasks.append(asyncio.create_task(one(a.offset + i, slow)))
        if gap:
            await asyncio.sleep(gap)
    ramp_s = time.time() - t_start
    await asyncio.sleep(a.settle)               # chờ các kết nối cuối nhận snap
    st["measuring"] = True
    t_meas[0] = time.time()
    await asyncio.sleep(a.duration)
    el = time.time() - t_meas[0]
    st["measuring"] = False
    open_now = sum(1 for v in state.values() if v == "open")
    stop.set()
    await asyncio.sleep(1.0)
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    closed_codes: dict[str, int] = {}
    for k, v in state.items():
        if v != "open":
            tag = ("slow:" if k in slow_ids else "fast:") + v
            closed_codes[tag] = closed_codes.get(tag, 0) + 1
    out = {"ok": st["ok"], "fail": st["fail"], "fails": fails, "open_at_end": open_now, "ramp_s": round(ramp_s, 1), "meas_s": round(el, 1),
           "emsgs": st["emsgs"], "egaps": st["egaps"], "msgs": st["msgs"], "frames": st["frames"], "bytes": st["bytes"], "seqs": st["seqs"], "gaps": st["gaps"],
           "snap_ms": snap_ms, "lat": lat[::max(1, len(lat) // 200_000)] if lat else [], "closed": closed_codes, "bye": st["bye"],
           "slow_conns": len(slow_ids)}
    sys.stdout.write("RESULT " + json.dumps(out) + "\n")
    sys.stdout.flush()


def scrape(url: str) -> dict:
    """Đọc /metrics của gateway -> dict tên{nhãn}->giá trị (chỉ rt_* + process)."""
    txt = urllib.request.urlopen(url.replace("ws://", "http://") + "/metrics", timeout=10).read().decode()
    out = {}
    for ln in txt.splitlines():
        if ln.startswith("#") or not (ln.startswith("rt_") or ln.startswith("process_cpu")):
            continue
        k, _, v = ln.rpartition(" ")
        try:
            out[k] = float(v)
        except ValueError:
            pass
    return out


def hist_q(m0: dict, m1: dict, name: str, q: float) -> float | None:
    """Phân vị xấp xỉ từ delta bucket của histogram Prometheus (giây)."""
    pts = []
    for k, v in m1.items():
        if k.startswith(name + "_bucket{"):
            le = re.search(r'le="([^"]+)"', k).group(1)
            pts.append((float("inf") if le == "+Inf" else float(le), v - m0.get(k, 0.0)))
    pts.sort()
    if not pts or pts[-1][1] <= 0:
        return None
    tot, tgt = pts[-1][1], q * pts[-1][1]
    for le, c in pts:
        if c >= tgt:
            return le
    return None


def delta_sum(m0: dict, m1: dict, prefix: str) -> float:
    return sum(v - m0.get(k, 0.0) for k, v in m1.items() if k.startswith(prefix))


async def run_load(a) -> None:
    per = a.n // a.procs
    m0 = scrape(a.url)
    t0 = time.time()
    children = []
    for p in range(a.procs):
        cmd = [sys.executable, os.path.abspath(__file__), "worker", "--url", a.url, "--n", str(per), "--offset", str(p * per), "--duration", str(a.duration),
               "--symbols", str(a.symbols), "--topics", str(a.topics), "--slow-pct", str(a.slow_pct), "--ramp", str(a.ramp / a.procs),
               "--users", str(a.users), "--settle", str(a.settle)] + (["--compress"] if a.compress else [])
        children.append(await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE))
    mid = None

    async def sampler():
        nonlocal mid
        await asyncio.sleep(per / (a.ramp / a.procs) + a.settle + 2)
        mid = scrape(a.url)
        await asyncio.sleep(a.duration - 4)
        return scrape(a.url)

    samp = asyncio.create_task(sampler())
    outs = await asyncio.gather(*(c.communicate() for c in children))
    try:
        m1 = await asyncio.wait_for(samp, 5)
    except Exception:  # noqa: BLE001
        m1 = scrape(a.url)
    agg = {"emsgs": 0, "egaps": 0, "ok": 0, "fail": 0, "msgs": 0, "frames": 0, "bytes": 0, "seqs": 0, "gaps": 0, "open_at_end": 0, "slow_conns": 0}
    snap, lat, closed, bye, fails = [], [], {}, {}, {}
    meas = 0.0
    for (so, se), c in zip(outs, children):
        line = next((ln for ln in so.decode().splitlines() if ln.startswith("RESULT ")), None)
        if not line:
            print("worker lỗi:", se.decode()[-400:], file=sys.stderr)
            continue
        r = json.loads(line[7:])
        for k in agg:
            agg[k] += r[k]
        snap += r["snap_ms"]
        lat += r["lat"]
        meas = max(meas, r["meas_s"])
        for src, dst in ((r["closed"], closed), (r["bye"], bye), (r["fails"], fails)):
            for k, v in src.items():
                dst[k] = dst.get(k, 0) + v
    live = m1 if mid is None else m1
    base = mid or m0
    res = {"n": a.n, "slow_pct": a.slow_pct, "topics": a.topics, "rate_tps": a.rate, "compress": a.compress, **agg,
           "meas_s": meas, "msgs_per_s": round(agg["msgs"] / meas) if meas else None, "kB_per_s": round(agg["bytes"] / 1024 / meas) if meas else None,
           "gap_ratio": round(agg["gaps"] / max(1, agg["seqs"] + agg["gaps"]), 3),
           "snap_ms": {"p50": pctl(snap, .5), "p95": pctl(snap, .95), "p99": pctl(snap, .99)},
           "lat_ms": {"p50": pctl(lat, .5), "p95": pctl(lat, .95), "p99": pctl(lat, .99), "max": pctl(lat, 1.0), "n": len(lat)},
           "closed": closed, "bye": bye, "fails": fails,
           "gw": {"flush_p50_ms": None, "flush_p95_ms": None, "send_p95_ms": None,
                  "closed_total": {k: v for k, v in ((k, delta_sum(m0, live, k)) for k in ('rt_closed_total{reason="slow"}', 'rt_closed_total{reason="reauth"}', 'rt_closed_total{reason="rate"}')) if v},
                  "dropped_coalesced": delta_sum(base, live, 'rt_dropped_total{reason="coalesced"}'), "dropped_overflow": delta_sum(base, live, 'rt_dropped_total{reason="overflow"}'),
                  "dropped_slow": delta_sum(m0, live, 'rt_dropped_total{reason="slow"}'), "conn_attempts": {k: v for k, v in ((k, delta_sum(m0, live, k)) for k in ('rt_conn_attempts_total{result="accepted"}', 'rt_conn_attempts_total{result="capacity"}', 'rt_conn_attempts_total{result="user_limit"}')) if v}}}
    for nm, key, q in (("rt_flush_seconds", "flush_p50_ms", .5), ("rt_flush_seconds", "flush_p95_ms", .95), ("rt_send_seconds", "send_p95_ms", .95)):
        v = hist_q(base, live, nm, q)
        res["gw"][key] = None if v is None else round(v * 1000, 2)
    res["gw"]["e2e_tick_to_gw_p95_ms"] = (lambda v: None if v is None else round(v * 1000, 1))(hist_q(base, live, "rt_tick_to_gateway_seconds", .95))
    res["gw"]["cpu_s_delta"] = round(live.get("process_cpu_seconds_total", 0) - base.get("process_cpu_seconds_total", 0), 2)
    res["wall_s"] = round(time.time() - t0, 1)
    print("LOADRESULT " + json.dumps(res), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("pub")
    p.add_argument("--rate", type=float, default=200, help="tick/s tổng")
    p.add_argument("--symbols", type=int, default=5)
    p.add_argument("--duration", type=float, default=0, help="0 = vô hạn")
    p.add_argument("--erate", type=float, default=0, help="sự kiện reliable account_status/s tổng (topic e:perf-accN)")
    p.add_argument("--users", type=int, default=100)
    for name in ("load", "worker"):
        p = sp.add_parser(name)
        p.add_argument("--url", default="ws://perf-ws-gw:8000")
        p.add_argument("--n", type=int, default=500)
        p.add_argument("--slow-pct", type=int, default=5, help="% kết nối chậm (không đọc socket)")
        p.add_argument("--topics", type=int, default=5, help="số topic q:PERFx / kết nối (+1 e:)")
        p.add_argument("--symbols", type=int, default=5)
        p.add_argument("--duration", type=float, default=60)
        p.add_argument("--ramp", type=float, default=100, help="kết nối mới/giây (tổng)")
        p.add_argument("--users", type=int, default=100, help="số 'người dùng' giả")
        p.add_argument("--settle", type=float, default=5)
        p.add_argument("--compress", action="store_true", default=False, help="đề nghị permessage-deflate như trình duyệt")
        p.add_argument("--rate", type=float, default=0, help="chỉ để ghi vào kết quả")
        if name == "load":
            p.add_argument("--procs", type=int, default=4)
        else:
            p.add_argument("--offset", type=int, default=0)
    a = ap.parse_args()
    asyncio.run({"pub": run_pub, "load": run_load, "worker": run_worker}[a.cmd](a))


if __name__ == "__main__":
    main()
