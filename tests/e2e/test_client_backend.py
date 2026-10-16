"""E2E backend client: lệnh chờ (mt-bridge -> bus -> storage-writer -> account_orders -> gateway), tiền tệ, cảnh báo cá nhân theo chủ sở hữu (IDOR)
và Web Push, đi qua nginx của client-ui (/c/) như người dùng thật. Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_client_backend.py
Tài khoản test mt5:97xxxxxx (không đụng tài khoản thật/demo); dọn sạch cuối. Không đặt lệnh. Không in token/secret."""
import asyncio
import base64
import hashlib
import hmac as hm
import json
import os
import re
import secrets
import subprocess
import sys
import time

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi", "cryptography"], capture_output=True, check=False)

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from qalib import BRIDGE, Ctx, Results, wait_for  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
CUI = os.getenv("QA_CLIENT_UI", "http://client-ui:8080")
CUI_HOST = CUI.split("//", 1)[1]
RUN = secrets.token_hex(3)
N = int(RUN, 16) % 90000
LA, LB = 97000000 + N, 97100000 + N
A, B = f"mt5:{LA}", f"mt5:{LB}"
MPW, CPW = "QaMaster-" + secrets.token_urlsafe(12), "Moi-" + secrets.token_urlsafe(12)
R = Results("client_backend")
sid_of = lambda r: (re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")) or [None, ""])[1]  # noqa: E731
_ip = iter(range(10, 250))
b64u = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731


def fake_ip() -> dict:
    return {"CF-Connecting-IP": f"10.96.{N % 200}.{next(_ip)}"}


def order(ticket: int, symbol: str, typ: int, lots: float, price: float) -> dict:
    return {"ticket": ticket, "symbol": symbol, "type": typ, "lots": lots, "price": price, "sl": price - 0.01, "tp": price + 0.02, "magic": 7, "comment": "qa", "setup_time": int(time.time()) - 600}


def batch(acc: str, login: int, currency: str, orders: list, bal: float = 1000.0) -> dict:
    return {"v": 1, "account_id": acc, "platform": "mt5", "ts": int(time.time()), "nonce": "n" + secrets.token_hex(8), "seq": 0,
            "account": {"login": login, "server": "QA-Server", "currency": currency, "leverage": 100, "balance": bal, "equity": bal, "margin": 0, "free_margin": bal},
            "positions": [], "orders": orders, "agent": {"ea": "1.1", "build": 4000, "company": "QA Broker", "rtt_ms": 20, "fail": 0}}


async def ingest(h, acc, token, secret, login, currency, orders) -> int:
    b = batch(acc, login, currency, orders)
    raw = json.dumps(b).encode()
    sig = hm.new(secret.encode(), f"{b['ts']}.{b['nonce']}.".encode() + raw, hashlib.sha256).hexdigest()
    hd = {"Authorization": f"Bearer {token}", "X-MT-Account": acc, "Content-Type": "application/json", "X-MT-Sig": sig}
    return (await h.post(BRIDGE + "/ingest/v1", content=raw, headers=hd)).status_code


def real_sub(path: str) -> dict:
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/qa-{RUN}-{path}", "keys": {"p256dh": b64u(pub), "auth": b64u(os.urandom(16))}, "user_agent": "qa-e2e"}


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=25, follow_redirects=False) as h:
        db = c.db
        ph = PasswordHasher()
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)", f"master:qa-{RUN}", ph.hash(MPW))
        try:
            await run(c, h, db)
        finally:
            ids = [A, B]
            uids = [r["user_id"] for r in await db.fetch("select user_id from portal_users where login_key = any($1)", ids)]
            sids = [str(u) for u in uids]
            await db.execute("delete from push_subscriptions where owner_user_id = any($1)", sids)
            await db.execute("delete from alert_rule_events where owner_user_id = any($1)", sids)
            await db.execute("delete from alert_rules where owner_user_id = any($1)", sids)
            await db.execute("delete from account_orders where account_id = any($1)", ids)
            await db.execute("delete from account_snapshots where account_id = any($1)", ids)
            await db.execute("delete from portal_users where login_key = any($1) or login_key=$2", ids, f"master:qa-{RUN}")
            await db.execute("delete from mt_accounts where account_id = any($1)", ids)
    return R.finish()


async def run(c, h, db):
    r = await h.post(f"{AUTH}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": MPW}, headers=fake_ip())
    msid = sid_of(r)
    R.check("master/login", r.status_code == 200 and msid, f"{r.status_code}", "critical")
    adm = lambda path, body=None: h.post(f"{AUTH}/auth/admin/{path}", json=body, headers={"Cookie": f"ts_session={msid}"})  # noqa: E731
    sec = {}
    for acc, login in ((A, LA), (B, LB)):
        r = await adm("accounts", {"platform": "mt5", "login": login, "server": "QA-Server", "label": f"qa-{RUN}"})
        sec[acc] = r.json()["secrets"]
        R.check(f"setup/tao-{acc}", r.status_code == 201, f"{r.status_code}", "critical")
        await adm(f"accounts/{acc}/activate")

    # ---------------------------------------------------------------- 1. lệnh chờ + tiền tệ: EA -> bridge -> writer -> DB
    oA = [order(7001, "EURUSD", 2, 0.3, 1.0790), order(7002, "XAUUSD", 5, 0.05, 2630.0)]
    oB = [order(9001, "GBPUSD", 4, 1.0, 1.3100)]
    R.check("ingest/A", await ingest(h, A, sec[A]["ea_token"], sec[A]["hmac_secret"], LA, "EUR", oA) == 200, "", "critical")
    R.check("ingest/B", await ingest(h, B, sec[B]["ea_token"], sec[B]["hmac_secret"], LB, "USD", oB) == 200, "", "critical")
    ok = await wait_for(lambda: db.fetchval("select count(*) = 3 from account_orders where account_id=any($1) and status='open'", [A, B]), 25)
    R.check("orders/DB-co-lenh-cho", bool(ok), "", "critical")
    rows = await db.fetch("select account_id, ticket, kind, status from account_orders where account_id=any($1) order by ticket", [A, B])
    R.check("orders/anh-xa-kind+upsert", {(r["ticket"], r["kind"]) for r in rows} == {("7001", "buy_limit"), ("7002", "sell_stop"), ("9001", "buy_stop")}, str([(r["ticket"], r["kind"]) for r in rows]), "critical")
    R.check("tien-te/currency-vao-account_snapshots", (await db.fetchval("select currency from account_snapshots where account_id=$1 order by ts desc limit 1", A)) == "EUR", "", "critical")

    # ---------------------------------------------------------------- 2. hai client đăng nhập qua nginx client-ui
    async def login(acc, login_no) -> str:
        r = await h.post(f"{CUI}/c/auth/login", json={"platform": "mt5", "login": str(login_no), "secret": sec[acc]["passcode"]}, headers={"Origin": f"http://{CUI_HOST}", **fake_ip()})
        sid = sid_of(r)
        r = await h.post(f"{CUI}/c/auth/change-password", json={"current_password": sec[acc]["passcode"], "new_password": CPW}, headers={"Cookie": f"ts_session={sid}", "Origin": f"http://{CUI_HOST}", **fake_ip()})
        R.check(f"client/{acc}/doi-mat-khau", r.status_code == 200, f"{r.status_code}", "critical")
        return sid
    sa, sb = await login(A, LA), await login(B, LB)

    def hdrs(sid, write=False, csrf=None, **extra):
        d = {"Cookie": f"ts_session={sid}", **fake_ip(), **extra}
        if write:
            d.update({"Origin": f"http://{CUI_HOST}", "X-CSRF-Token": csrf or ""})
        return d

    get = lambda sid, path, **kw: h.get(f"{CUI}/c/api/v1{path}", headers=hdrs(sid, **kw))  # noqa: E731

    async def csrf(sid):
        return (await get(sid, "/user/csrf")).json()["token"]

    async def w(method, sid, path, body=None, **kw):
        for _ in range(4):   # nginx giới hạn ghi theo IP: dùng IP giả khác nhau; vẫn thử lại khi 429
            r = await h.request(method, f"{CUI}/c/api/v1{path}", json=body, headers=hdrs(sid, True, await csrf(sid), **kw))
            if r.status_code != 429:
                return r
            await asyncio.sleep(2)
        return r

    r = await get(sa, "/accounts")
    j = r.json() if r.status_code == 200 else []
    R.check("accounts/A-chi-thay-A+currency+orders", r.status_code == 200 and [x["account_id"] for x in j] == [A] and j[0]["currency"] == "EUR"
            and sorted(o["order_id"] for o in j[0]["orders"]) == ["7001", "7002"], f"{r.status_code} {r.text[:120]}", "critical")
    j = (await get(sb, "/accounts")).json()
    R.check("accounts/B-chi-thay-B+USD", [x["account_id"] for x in j] == [B] and j[0]["currency"] == "USD" and [o["order_id"] for o in j[0]["orders"]] == ["9001"], "", "critical")
    r = await get(sa, f"/accounts/{A}/orders")
    o = r.json() if r.status_code == 200 else []
    R.check("orders/endpoint-A", r.status_code == 200 and sorted(x["order_id"] for x in o) == ["7001", "7002"] and {x["kind"] for x in o} == {"buy_limit", "sell_stop"}, f"{r.status_code}", "critical")
    for name, path in (("B-doc-A", f"/accounts/{A}/orders"), ("A-doc-B", f"/accounts/{B}/orders"), ("ma-hoa-%3A", f"/accounts/mt5%3A{LB}/orders"),
                       ("khong-ton-tai", "/accounts/mt5:1/orders"), ("ky-tu-la", "/accounts/a;b/orders")):
        sid = sb if name == "B-doc-A" else sa
        st = (await get(sid, path)).status_code
        R.check(f"orders/IDOR/{name}", st in (403, 404), f"{st}", "critical")
    R.check("orders/khong-ghi-duoc", (await w("POST", sa, f"/accounts/{A}/orders", {})).status_code in (403, 404, 405), "", "critical")

    # lệnh biến mất khỏi snapshot -> removed
    await asyncio.sleep(1.1)
    R.check("ingest/A-con-1-lenh", await ingest(h, A, sec[A]["ea_token"], sec[A]["hmac_secret"], LA, "EUR", oA[:1]) == 200, "", "critical")
    gone = await wait_for(lambda: db.fetchval("select count(*) from account_orders where account_id=$1 and ticket='7002' and status='removed'", A), 25)
    R.check("orders/bien-mat->removed", bool(gone), "", "critical")
    o = (await get(sa, f"/accounts/{A}/orders")).json()
    R.check("orders/mac-dinh-chi-lenh-dang-mo", [x["order_id"] for x in o] == ["7001"], str([x["order_id"] for x in o]), "critical")
    r = await h.get(f"{CUI}/c/api/v1/accounts/{A}/orders?status=all", headers=hdrs(sa))
    R.check("orders/status=all-co-removed", {x["order_id"]: x["status"] for x in r.json()} == {"7001": "open", "7002": "removed"}, "", "high")

    # ---------------------------------------------------------------- 3. cảnh báo cá nhân: chủ sở hữu / IDOR
    acct_rule = lambda acc, name: {"name": name, "mode": "once", "level": "warn", "channels": ["ntfy", "log", "push"], "cooldown_min": 1,
                                   "conditions": [{"type": "account", "account_id": acc, "metric": "floating_pl_pct", "op": "gte", "value": -1000}]}
    r = await w("POST", sa, "/user/rules", acct_rule(A, f"qa-{RUN}-A"))
    ra = r.json() if r.status_code in (200, 201) else {}
    R.check("rules/A-tao", r.status_code in (200, 201) and ra.get("account_id") == A, f"{r.status_code} {r.text[:100]}", "critical")
    R.check("rules/kenh-toan-cuc-bi-loai", ra.get("channels") == ["push"] and ra.get("cooldown_min", 0) >= 5, str(ra.get("channels")), "critical")
    r = await w("POST", sb, "/user/rules", acct_rule(B, f"qa-{RUN}-B"))
    rb = r.json() if r.status_code in (200, 201) else {}
    R.check("rules/B-tao", r.status_code in (200, 201), f"{r.status_code}", "critical")
    R.check("rules/B-khong-dung-tai-khoan-A", (await w("POST", sb, "/user/rules", acct_rule(A, "x"))).status_code == 422, "", "critical")
    R.check("rules/preview-khong-lo-tai-khoan-A", (await w("POST", sb, "/user/rules/preview", acct_rule(A, "x"))).status_code == 422, "", "critical")
    R.check("rules/A-liet-ke-chi-cua-A", [x["id"] for x in (await get(sa, "/user/rules")).json()["items"]] == [ra["id"]], "", "critical")
    R.check("rules/B-liet-ke-chi-cua-B", [x["id"] for x in (await get(sb, "/user/rules")).json()["items"]] == [rb["id"]], "", "critical")
    R.check("rules/B-sua-cua-A->404", (await w("PUT", sb, f"/user/rules/{ra['id']}", acct_rule(B, "hack"))).status_code == 404, "", "critical")
    R.check("rules/B-xoa-cua-A->404", (await w("DELETE", sb, f"/user/rules/{ra['id']}")).status_code == 404, "", "critical")
    R.check("rules/B-preview-cua-A->404", (await w("POST", sb, f"/user/rules/{ra['id']}/preview")).status_code == 404, "", "critical")
    spoof = {"X-Owner-User": str((await db.fetchval("select user_id from portal_users where login_key=$1", A))), "X-Owner-Role": "master", "X-User-Id": "x", "X-Role": "master"}
    j = (await h.get(f"{CUI}/c/api/v1/user/rules", headers=hdrs(sb, **spoof))).json()
    R.check("rules/gia-mao-header-danh-tinh-bi-bo-qua", [x["id"] for x in j["items"]] == [rb["id"]], "", "critical")
    R.check("rules/client-khong-doc-prefs", (await get(sa, "/user/prefs")).status_code in (403, 404), "", "critical")
    sts = [(await get(sa, p)).status_code for p in ("/system", "/alerts", "/user/prefs", "/paper/accounts", "/reports")]
    R.check("rules/client-khong-vao-system-alerts-paper", all(s in (403, 404) for s in sts), str(sts), "critical")
    n = (await db.fetchval("select count(*) from alert_rules where owner_user_id is not null and name like $1", f"qa-{RUN}%"))
    R.check("rules/DB-co-chu-so-huu", n == 2, str(n), "high")

    # ---------------------------------------------------------------- 4. Web Push: đăng ký theo chủ, nội dung chung, đường gửi thật (pywebpush)
    info = (await get(sa, "/user/push")).json()
    R.check("push/bat-tren-may-chu", info.get("enabled") is True and isinstance(info.get("public_key"), str) and len(info["public_key"]) == 87, str({k: v for k, v in info.items() if k != "public_key"}), "critical")
    subA = real_sub("a")
    r = await w("POST", sa, "/user/push/subscribe", subA)
    R.check("push/A-dang-ky", r.status_code == 201 and r.json()["subscriptions"] == 1, f"{r.status_code} {r.text[:80]}", "critical")
    row = await db.fetchrow("select endpoint_enc, p256dh_enc, auth_enc from push_subscriptions where owner_user_id=(select user_id::text from portal_users where login_key=$1)", A)
    R.check("push/luu-ma-hoa", row and subA["endpoint"] not in json.dumps(dict(row)) and subA["keys"]["auth"] not in json.dumps(dict(row)), "", "critical")
    for name, bad in (("http", {**subA, "endpoint": "http://fcm.googleapis.com/x"}), ("ssrf", {**subA, "endpoint": "https://169.254.169.254/x"}),
                      ("host-la", {**subA, "endpoint": "https://evil.example/x"}), ("khoa-sai", {**subA, "keys": {"p256dh": "abc" * 10, "auth": "abc" * 5}})):
        R.check(f"push/tu-choi/{name}", (await w("POST", sa, "/user/push/subscribe", bad)).status_code == 422, "", "critical")
    r = await w("POST", sb, "/user/push/unsubscribe", {"endpoint": subA["endpoint"]})
    R.check("push/B-huy-endpoint-cua-A-khong-co-tac-dung", r.status_code == 200 and (await get(sa, "/user/push")).json()["subscriptions"] == 1, "", "critical")
    R.check("push/B-khong-thay-dang-ky-cua-A", (await get(sb, "/user/push")).json()["subscriptions"] == 0, "", "critical")

    # quy tắc đã tạo ở bước 3 phải kích hoạt (tick 5s): sự kiện theo chủ, KHÔNG phát alerts.out (không lộ qua ntfy/telegram)
    async def ev(sid):
        j = (await get(sid, "/user/rule-events")).json()["items"]
        return j or None
    eva, evb = await wait_for(lambda: ev(sa), 45, 3), await wait_for(lambda: ev(sb), 45, 3)
    R.check("rules/A-kich-hoat+su-kien", bool(eva) and eva[0]["rule_name"] == f"qa-{RUN}-A" and A in eva[0]["body"], str(eva)[:120] if eva else "không có sự kiện", "critical")
    R.check("rules/B-kich-hoat+su-kien", bool(evb) and evb[0]["rule_name"] == f"qa-{RUN}-B" and B in evb[0]["body"], "", "critical")
    R.check("rules/su-kien-khong-lan-nhau", all(e["rule_name"].endswith("-A") for e in (eva or [])) and all(e["rule_name"].endswith("-B") for e in (evb or [])) and
            A not in json.dumps(evb) and B not in json.dumps(eva), "", "critical")
    R.check("rules/khong-phat-alerts.out-toan-cuc", (await db.fetchval("select count(*) from alerts where title like $1 or body like $2", f"%qa-{RUN}%", f"%{A}%")) == 0, "", "critical")
    # thử gửi push thật qua pywebpush (token FCM giả -> dịch vụ trả 4xx; 404/410 => đăng ký bị xoá)
    r = await w("POST", sa, "/user/push/test")
    R.check("push/test-chay-khong-loi", r.status_code in (200, 503), f"{r.status_code} {r.text[:60]}", "high")
    left = (await get(sa, "/user/push")).json()["subscriptions"]
    R.info("push/ket-qua-gui-that", f"sent={r.json().get('sent') if r.status_code == 200 else None}; dang-ky-con-lai={left} (0 = dịch vụ trả 404/410 -> đã dọn)")
    # huỷ đúng chủ
    await w("POST", sa, "/user/push/subscribe", real_sub("a2"))
    R.check("push/A-huy-chinh-minh", (await w("POST", sa, "/user/push/unsubscribe", {"endpoint": real_sub("a2")["endpoint"]})).status_code == 200, "", "high")
    R.check("rules/A-xoa-cua-minh", (await w("DELETE", sa, f"/user/rules/{ra['id']}")).status_code == 200, "", "high")
    R.check("rules/xoa-roi-khong-con", (await get(sa, "/user/rules")).json()["items"] == [], "", "high")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
