"""E2E BẢO MẬT kênh realtime rt.v1 (docs/REALTIME.md §3, docs/AUTH.md). Chạy trên VPS:  sh /root/qa-e2e/run_rt_security.sh
Mục tiêu: client A (tài khoản rtq-a1) KHÔNG nhận dữ liệu của B (rtq-a2); sys chỉ master; header giả/role lạ bị đóng 1008; giới hạn kết nối/người dùng;
hết tuổi -> bye reauth + 4401; kick đúng user; Origin lạ bị từ chối; tin quá lớn/ spam bị bỏ/đóng; SSE: không API key -> 401, chỉ topic của mình.
Dữ liệu: gateway TẠM (perf-ws-gw-sec / perf-ws-gw-age, RT_EXTRA_STREAMS=rt.sec) đọc stream RIÊNG `rt.sec` (KHÔNG chạm md.*/account.* thật, không vào DB); dọn DEL rt.sec ở cuối.
Qua nginx thật (web-ui /api/v1/rt, client-ui /c/api/v1/rt): chỉ kiểm phần KHÔNG cần đăng nhập (401 khi thiếu phiên, header giả bị nginx ghi đè).
Không in bí mật. READ-ONLY (không có thao tác đặt lệnh)."""
import asyncio
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
import websockets
from qalib import Results

GW = os.getenv("QA_RT_GW", "ws://perf-ws-gw-sec:8000")
GW_AGE = os.getenv("QA_RT_GW_AGE", "ws://perf-ws-gw-age:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
CLIENT_UI = os.getenv("QA_CLIENT_UI", "http://client-ui:8080")
TOKEN = os.environ["API_TOKEN"]
SECRET = os.environ["AUTH_TRUST_SECRET"]
STREAM = "rt.sec"
RUN = secrets.token_hex(3)
A1, A2 = f"rtq-a1-{RUN}", f"rtq-a2-{RUN}"
R = Results("realtime_security")


def ident(role, uid, accs="", secret=SECRET, key=TOKEN) -> dict:
    h = {"X-API-Key": key, "X-User-Id": uid, "X-Role": role, "X-Accounts": accs}
    if secret is not None:
        h["X-Auth-Secret"] = secret
    return h


def http(base: str) -> str:
    return base.replace("ws://", "http://")


class Rej(Exception):
    def __init__(self, what):
        self.what = what


async def connect(base, path, headers, subproto=None):
    """-> ws, hoặc ném Rej(mã HTTP 4xx lúc bắt tay | mã đóng WS)."""
    try:
        for attempt in range(8):  # tải máy cao: gateway tạm chậm/chưa nhận kết nối -> thử lại với lỗi MẠNG (không thử lại khi bị từ chối hợp lệ)
            try:
                return await asyncio.wait_for(websockets.connect(base + path, additional_headers=headers, max_size=2**22, open_timeout=10, ping_interval=None), 15)
            except (OSError, asyncio.TimeoutError):
                if attempt == 7:
                    raise
                await asyncio.sleep(min(2 * (attempt + 1), 6))
    except websockets.exceptions.InvalidStatus as e:
        raise Rej(f"http{e.response.status_code}") from e
    except websockets.exceptions.ConnectionClosed as e:
        raise Rej(f"close{e.rcvd.code if e.rcvd else '?'}") from e
    except Exception as e:  # noqa: BLE001
        raise Rej(type(e).__name__) from e


async def msgs(ws, timeout=3.0, until=None):
    """Đọc tin (phẳng hoá khung b) tới khi `until(m)` đúng hoặc hết timeout. Trả (list, closed_code|None)."""
    out, code = [], None
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), max(0.05, end - time.monotonic()))
        except asyncio.TimeoutError:
            break
        except websockets.exceptions.ConnectionClosed as e:
            code = e.rcvd.code if e.rcvd else 1006
            break
        fr = json.loads(raw)
        for m in (fr["m"] if fr.get("t") == "b" else [fr]):
            out.append(m)
            if until and until(m):
                return out, None
    return out, code


async def expect_rejected(name, base, path, headers, codes=("http403", "close1008"), sev="critical"):
    try:
        ws = await connect(base, path, headers)
    except Rej as r:
        return R.check(name, r.what in codes, r.what, sev)
    # chấp nhận bắt tay rồi đóng ngay bằng 1008
    out, code = await msgs(ws, 3)
    await ws.close()
    return R.check(name, code == 1008 and not any(m.get("t") in ("snap", "d") for m in out), f"đã nối, close={code}", sev)


def ev(typ, payload):
    return {"id": secrets.token_hex(6), "type": typ, "source": "qa", "ts": datetime.now(timezone.utc).isoformat(), "schema_version": 1, "trace_id": "qa", "payload": payload}


async def pub(r, typ, payload):
    await r.xadd(STREAM, {"e": json.dumps(ev(typ, payload))}, maxlen=1000, approximate=True)


async def main():
    r = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        await run(r)
    finally:
        await r.delete(STREAM)
        await r.aclose()
    return R.finish()


async def run(r):
    # ------------------------------------------------------------------ 1. hello / sub / forbidden đồng nhất
    ha = ident("client", "uA", A1)
    wa = await connect(GW, f"/v1/rt?topics=a:{A1}", ha)
    out, _ = await msgs(wa, 3, until=lambda m: m.get("t") == "ok")
    hello = next((m for m in out if m["t"] == "hello"), {})
    R.check("ws/hello-role-client", hello.get("role") == "client" and hello.get("v") == 1 and hello.get("limits", {}).get("topics", 0) > 0, str({k: hello.get(k) for k in ("role", "v")}), "high")
    R.check("ws/sub-own-account-ok", any(m["t"] == "ok" and m.get("k") == [f"a:{A1}"] for m in out), "", "high")
    await wa.send(json.dumps({"op": "sub", "topics": [f"a:{A2}", f"e:{A2}", f"a:khong-ton-tai-{RUN}", f"e:khong-ton-tai-{RUN}", "sys", f"e:{A1}", "q:EURUSD", "n"]}))
    out, _ = await msgs(wa, 3, until=lambda m: m["t"] == "ok" and "e" in m)
    ok = next(m for m in out if m["t"] == "ok" and "e" in m)
    errs = {t: c for t, c in ok["e"]}
    R.check("ws/idor-forbidden-dong-nhat", set(errs.values()) == {"forbidden"} and set(errs) == {f"a:{A2}", f"e:{A2}", f"a:khong-ton-tai-{RUN}", f"e:khong-ton-tai-{RUN}", "sys"},
            f"{errs}", "critical")
    R.check("ws/sub-hop-le-van-ok", set(ok["k"]) == {f"e:{A1}", "q:EURUSD", "n"}, str(ok["k"]), "high")

    # ------------------------------------------------------------------ 2. A không nhận snapshot/sự kiện của B; master thấy cả hai
    wm = await connect(GW, f"/v1/rt?topics=a:{A1},a:{A2},e:{A2},sys", ident("master", "uM"))
    out, _ = await msgs(wm, 3, until=lambda m: m["t"] == "ok")
    okm = next(m for m in out if m["t"] == "ok")
    R.check("ws/master-sub-moi-tai-khoan-va-sys", len(okm["k"]) == 4 and not okm["e"], str(okm), "high")
    await msgs(wa, 0.5)
    await pub(r, "account_snapshot", {"account_id": A2, "balance": 222222.0, "equity": 222222.0})
    await pub(r, "account_snapshot", {"account_id": A1, "balance": 111111.0, "equity": 111111.0})
    await pub(r, "account_status", {"account_id": A2, "status": "connected", "reason": "rtq-b-secret"})
    await pub(r, "deals", {"account_id": A2, "deals": [{"ticket": 777777, "profit": 1.0}]})
    got_a, _ = await msgs(wa, 20, until=lambda m: m.get("k") == f"a:{A1}" and m["t"] == "d")  # chờ có điều kiện (tải cao làm trễ hub), không nới kiểm tra
    blob = json.dumps(got_a)
    R.check("ws/A-nhan-snapshot-cua-minh", any(m.get("k") == f"a:{A1}" and m["t"] == "d" and m["d"]["balance"] == 111111.0 for m in got_a), "", "high")
    more, _ = await msgs(wa, 1.5)
    blob += json.dumps(more)
    R.check("ws/A-KHONG-nhan-du-lieu-cua-B", "222222" not in blob and "rtq-b-secret" not in blob and "777777" not in blob and A2 not in blob.replace(f'"{A2}"', "") and f":{A2}" not in blob,
            "không thấy 222222/777777/rtq-b-secret/tên tài khoản B trong luồng của A", "critical")
    R.check("ws/A-KHONG-nhan-sys", not any(m.get("k") == "sys" for m in got_a + more), "", "critical")
    seen = set()

    def _master_done(m):  # chờ tới khi đủ sự kiện mong đợi (tối đa 20s) thay vì cửa sổ cố định 4s
        if m["t"] == "d":
            seen.add(m.get("k") if m.get("k") != "sys" else ("sys", m["d"].get("k")))
        return {f"a:{A1}", f"a:{A2}", f"e:{A2}", ("sys", "ea_status")} <= seen
    gm, _ = await msgs(wm, 20, until=_master_done)
    ks = {m.get("k") for m in gm if m["t"] == "d"}
    R.check("ws/master-thay-ca-hai-tai-khoan", {f"a:{A1}", f"a:{A2}", f"e:{A2}"} <= ks, str(sorted(k for k in ks if k)), "high")
    R.check("ws/master-nhan-sys-ea_status", any(m.get("k") == "sys" and m["t"] == "d" and m["d"].get("k") == "ea_status" for m in gm), "", "medium")
    await wm.close()

    # ------------------------------------------------------------------ 3. header giả / role lạ / sai API key
    base = ident("client", "uX", A1)
    await expect_rejected("ws/header-thieu-secret", GW, "/v1/rt", {k: v for k, v in base.items() if k != "X-Auth-Secret"})
    await expect_rejected("ws/header-sai-secret", GW, "/v1/rt", {**base, "X-Auth-Secret": "sai-" + RUN})
    await expect_rejected("ws/header-secret-rong", GW, "/v1/rt", {**base, "X-Auth-Secret": ""})
    await expect_rejected("ws/role-anon", GW, "/v1/rt", ident("anon", "x"))
    await expect_rejected("ws/role-la", GW, "/v1/rt", ident("admin", "x"))
    await expect_rejected("ws/role-master-nhung-sai-secret", GW, "/v1/rt", {**ident("master", "x"), "X-Auth-Secret": "sai"})
    # sai API key: không có header danh tính -> "service"; WS chờ tin auth đầu -> sai key -> đóng 1008
    try:
        ws = await connect(GW, "/v1/rt?topics=q:EURUSD", {"X-API-Key": "sai-key-" + RUN})
        await ws.send(json.dumps({"type": "auth", "api_key": "van-sai"}))
        out, code = await msgs(ws, 5)
        R.check("ws/sai-api-key-bi-dong-1008", code == 1008 and not any(m["t"] in ("hello", "snap", "d") for m in out), f"close={code}", "critical")
    except Rej as rj:
        R.check("ws/sai-api-key-bi-dong-1008", rj.what in ("http403", "close1008", "http401"), rj.what, "critical")
    try:
        ws = await connect(GW, "/v1/rt?topics=q:EURUSD", {})
        await ws.send(json.dumps({"type": "auth", "api_key": "van-sai"}))
        out, code = await msgs(ws, 5)
        R.check("ws/khong-API-key-bi-dong", code == 1008 and not any(m["t"] in ("hello", "snap") for m in out), f"close={code}", "critical")
    except Rej as rj:
        R.check("ws/khong-API-key-bi-dong", rj.what in ("http403", "close1008", "http401"), rj.what, "critical")

    # ------------------------------------------------------------------ 4. Origin
    await expect_rejected("ws/origin-la-bi-tu-choi", GW, "/v1/rt", {**ident("client", "uA", A1), "Origin": "https://evil.example"})
    host = GW.split("//", 1)[1]
    try:
        ws = await connect(GW, "/v1/rt", {**ident("client", "uA", A1), "Origin": f"http://{host.split(':')[0]}"})
        R.check("ws/origin-cung-host-duoc-phep", (await msgs(ws, 2, until=lambda m: m["t"] == "hello"))[0][0]["t"] == "hello", "", "medium")
        await ws.close()
    except Rej as rj:
        R.check("ws/origin-cung-host-duoc-phep", False, rj.what, "medium")

    # ------------------------------------------------------------------ 5. giới hạn kết nối / người dùng
    held = []
    try:
        for i in range(6):
            held.append(await connect(GW, "/v1/rt", ident("client", "uLim", A1)))
        R.check("ws/6-ket-noi-dau-cua-user-duoc-nhan", True, "6/6", "high")
    except Rej as rj:
        R.check("ws/6-ket-noi-dau-cua-user-duoc-nhan", False, f"{len(held)}/6 {rj.what}", "high")
    try:
        w7 = await connect(GW, "/v1/rt", ident("client", "uLim", A1))
        o7, c7 = await msgs(w7, 2)
        R.check("ws/ket-noi-thu-7-bi-tu-choi", False, f"được nhận! close={c7}", "critical")
    except Rej as rj:
        R.check("ws/ket-noi-thu-7-bi-tu-choi", rj.what in ("http403", "close1013"), rj.what, "critical")
    # người dùng khác vẫn vào được; đóng một -> vào lại được
    try:
        wo = await connect(GW, "/v1/rt", ident("client", "uOther", A1))
        R.check("ws/user-khac-khong-bi-anh-huong", (await msgs(wo, 2, until=lambda m: m["t"] == "hello"))[0][0]["t"] == "hello", "", "medium")
        await wo.close()
    except Rej as rj:
        R.check("ws/user-khac-khong-bi-anh-huong", False, rj.what, "medium")
    await held[0].close()
    await asyncio.sleep(0.5)
    try:
        w = await connect(GW, "/v1/rt", ident("client", "uLim", A1))
        R.check("ws/dong-mot-thi-noi-lai-duoc", True, "", "medium")
        held.append(w)
    except Rej as rj:
        R.check("ws/dong-mot-thi-noi-lai-duoc", False, rj.what, "medium")
    for w in held[1:]:
        await w.close()
    # quá 120 topic/ kết nối
    wt = await connect(GW, "/v1/rt", ident("master", "uTop"))
    await msgs(wt, 1, until=lambda m: m["t"] == "hello")
    for i in range(3):
        await wt.send(json.dumps({"op": "sub", "topics": [f"q:T{j}" for j in range(i * 50, i * 50 + 50)]}))
        await asyncio.sleep(0.15)
    o, _ = await msgs(wt, 2)
    errs = [c for m in o if m["t"] == "ok" for _, c in m.get("e", [])]
    R.check("ws/gioi-han-topic-120", errs.count("too_many_topics") == 30, f"too_many_topics={errs.count('too_many_topics')}", "medium")
    await wt.close()

    # ------------------------------------------------------------------ 6. kick
    k1 = await connect(GW, "/v1/rt", ident("client", "uK", A1))
    k2 = await connect(GW, "/v1/rt", ident("client", "uK", A1))
    ko = await connect(GW, "/v1/rt", ident("client", "uKeep", A1))
    for w in (k1, k2, ko):
        await msgs(w, 1, until=lambda m: m["t"] == "hello")
    async with httpx.AsyncClient(timeout=10) as h:
        rc = await h.post(http(GW) + "/v1/rt/kick", json={"user_id": "uK"}, headers=ident("client", "uKeep", A1))
        R.check("kick/client-khong-duoc-goi", rc.status_code == 403, str(rc.status_code), "critical")
        rn = await h.post(http(GW) + "/v1/rt/kick", json={"user_id": "uK"}, headers={"X-API-Key": "sai"})
        R.check("kick/khong-API-key-401", rn.status_code == 401, str(rn.status_code), "critical")
        rs = await h.get(http(GW) + "/v1/rt/stats", headers=ident("client", "uKeep", A1))
        R.check("stats/client-khong-duoc-xem", rs.status_code == 403, str(rs.status_code), "high")
        rm = await h.post(http(GW) + "/v1/rt/kick", json={"user_id": "uK"}, headers=ident("master", "uM"))
        R.check("kick/master-ngat-dung-user", rm.status_code == 200 and rm.json() == {"kicked": 2}, str(rm.json()), "high")
    o1, c1 = await msgs(k1, 3)
    o2, c2 = await msgs(k2, 3)
    R.check("kick/ket-noi-nhan-bye-kicked-va-dong-4403", any(m["t"] == "bye" and m["c"] == "kicked" for m in o1) and c1 == 4403 and c2 == 4403, f"c1={c1} c2={c2}", "high")
    await ko.send(json.dumps({"op": "ping", "t": 5}))
    o3, c3 = await msgs(ko, 2, until=lambda m: m["t"] == "pong")
    R.check("kick/user-khac-van-song", c3 is None and any(m["t"] == "pong" for m in o3), "", "high")
    await ko.close()

    # ------------------------------------------------------------------ 7. tin quá lớn / spam
    ws = await connect(GW, "/v1/rt", ident("client", "uSpam", A1))
    await msgs(ws, 1, until=lambda m: m["t"] == "hello")
    await ws.send(json.dumps({"op": "sub", "topics": ["q:EURUSD"], "pad": "x" * 6000}))
    o, c = await msgs(ws, 2, until=lambda m: m["t"] == "err")
    R.check("ws/tin-qua-lon-bi-tu-choi", any(m["t"] == "err" and m["c"] == "too_big" for m in o), "", "high")
    ws2 = await connect(GW, "/v1/rt", ident("client", "uSpam2", A1))
    await msgs(ws2, 1, until=lambda m: m["t"] == "hello")
    for _ in range(600):
        await ws2.send('{"op":"ping","t":1}')
    o, c = await msgs(ws2, 6, until=None)
    R.check("ws/spam-vuot-toc-do-bi-dong", c == 1008 and any(m["t"] == "bye" and m["c"] == "rate" for m in o), f"close={c} pongs={sum(1 for m in o if m['t'] == 'pong')}", "high")
    ws3 = await connect(GW, "/v1/rt", ident("client", "uJunk", A1))
    await msgs(ws3, 1, until=lambda m: m["t"] == "hello")
    for payload in ("khong-phai-json", "[1,2,3]", '{"op":"ping"}', '{"op":"sub","topics":"q:EURUSD"}', '{"op":"__proto__"}'):
        await ws3.send(payload)
    await ws3.send('{"op":"ping","t":9}')
    o, c = await msgs(ws3, 2, until=lambda m: m["t"] == "pong" and m.get("c") == 9)
    R.check("ws/tin-rac-khong-lam-sap-hub", c is None and any(m["t"] == "pong" and m["c"] == 9 for m in o), "", "high")
    await ws3.close()

    # ------------------------------------------------------------------ 8. hết tuổi -> bye reauth + 4401 (gateway tạm RT_MAX_AGE_S nhỏ)
    t0 = time.monotonic()
    wg = await connect(GW_AGE, f"/v1/rt?topics=e:{A1}", ident("client", "uAge", A1))
    o, c = await msgs(wg, 20, until=None)
    hello = next((m for m in o if m["t"] == "hello"), {})
    R.check("ws/het-tuoi-bye-reauth-dong-4401", any(m["t"] == "bye" and m["c"] == "reauth" for m in o) and c == 4401 and time.monotonic() - t0 < 8,
            f"max_age={hello.get('max_age')} sau {time.monotonic() - t0:.1f}s close={c}", "high")

    # ------------------------------------------------------------------ 9. SSE
    async with httpx.AsyncClient(timeout=15) as h:
        s0 = await h.get(http(GW) + "/v1/rt/sse?topics=q:EURUSD")
        R.check("sse/khong-API-key-401", s0.status_code == 401, str(s0.status_code), "critical")
        s1 = await h.get(http(GW) + "/v1/rt/sse", headers={"X-API-Key": "sai"})
        R.check("sse/sai-API-key-401", s1.status_code == 401, str(s1.status_code), "critical")
        s2 = await h.get(http(GW) + "/v1/rt/sse", headers={**ident("client", "uA", A1), "X-Auth-Secret": "sai"})
        R.check("sse/header-gia-403", s2.status_code == 403, str(s2.status_code), "critical")
        s3 = await h.get(http(GW) + "/v1/rt/sse", headers={**ident("client", "uA", A1), "Origin": "https://evil.example"})
        R.check("sse/origin-la-403", s3.status_code == 403, str(s3.status_code), "high")
        got = []
        async with h.stream("GET", http(GW) + f"/v1/rt/sse?topics=a:{A1},a:{A2},e:{A2},sys,q:EURUSD", headers=ident("client", "uA", A1)) as resp:
            R.check("sse/client-stream-200", resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream"), str(resp.status_code), "high")
            t_end = time.monotonic() + 3
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    fr = json.loads(line[6:])
                    got += fr["m"] if fr.get("t") == "b" else [fr]
                if time.monotonic() > t_end or any(m.get("t") == "snap" for m in got) and any(m.get("t") == "ok" for m in got):
                    break
        ok = next((m for m in got if m["t"] == "ok"), {})
        R.check("sse/chi-co-topic-cua-minh", set(ok.get("k", [])) == {f"a:{A1}", "q:EURUSD"} and {e[0] for e in ok.get("e", [])} == {f"a:{A2}", f"e:{A2}", "sys"}, str(ok), "critical")

    # ------------------------------------------------------------------ 10. qua nginx thật (chỉ phần không cần phiên)
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as h:
        for name, base_url, path in (("web-ui", WEB, "/api/v1/rt"), ("client-ui", CLIENT_UI, "/c/api/v1/rt"), ("web-ui-client-path", WEB, "/c/api/v1/rt")):
            try:
                spoof = {"X-User-Id": "uM", "X-Role": "master", "X-Accounts": A1, "X-Auth-Secret": SECRET, "X-API-Key": TOKEN}
                a = await h.get(base_url + path, headers={"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
                b = await h.get(base_url + path, headers={"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==", **spoof})
                c = await h.get(base_url + path + "/sse?topics=sys", headers=spoof)
                d = await h.get(base_url + path, headers={"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==", "Cookie": "ts_session=" + "0" * 48})
                R.check(f"nginx/{name}-khong-phien-bi-tu-choi", a.status_code in (401, 403) and d.status_code in (401, 403), f"{a.status_code}/{d.status_code}", "critical")
                R.check(f"nginx/{name}-header-gia-khong-vuot-qua", b.status_code in (401, 403) and c.status_code in (401, 403), f"ws={b.status_code} sse={c.status_code}", "critical")
            except Exception as e:  # noqa: BLE001
                R.check(f"nginx/{name}", False, f"{type(e).__name__}: {str(e)[:80]}", "medium")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
