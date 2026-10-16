"""E2E đăng nhập master/client + phân quyền/IDOR (docs/AUTH.md). Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_auth.py
Dùng: service auth (http://auth:8000, trực tiếp), web-ui/nginx (http://web-ui:8080, đường thật của trình duyệt), DB (siêu người dùng, chỉ để gieo/dọn dữ liệu qa).
Dữ liệu test: master `master:qa-<run>`, tài khoản MT 99xxxxxx (nền tảng mt5), account_snapshots/account_deals của chúng; dọn sạch ở cuối.
Không in bí mật. Không gọi bất kỳ route đặt lệnh nào (không có)."""
import asyncio
import hashlib
import json
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi", "pyotp"], capture_output=True, check=False)

import os  # noqa: E402

import httpx  # noqa: E402
import pyotp  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import API_KEY, GATEWAY, Ctx, Results, mk_event, now, publish, wait_for  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
WEB_HOST = WEB.split("//", 1)[1]
RUN = secrets.token_hex(3)
LA, LB = 99000000 + int(RUN, 16) % 900000, 99900000 + int(RUN, 16) % 90000
ACC_A, ACC_B = f"mt5:{LA}", f"mt5:{LB}"
MPW = "QaMaster-" + secrets.token_urlsafe(12)
STRONG = "Moi-" + secrets.token_urlsafe(12)
R = Results("auth")
sid_of = lambda r: (re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")) or [None, ""])[1]  # noqa: E731
ck = lambda sid: {"Cookie": f"ts_session={sid}"}  # noqa: E731
nip = iter(range(10, 250))


def ip_hdr() -> dict:
    return {"X-Real-IP": f"10.99.0.{next(nip)}"}


async def post(h: httpx.AsyncClient, url, body=None, sid="", extra=None, origin=None):
    hd = {**(ck(sid) if sid else {}), **(extra or {})}
    if origin:
        hd["Origin"] = origin
    return await h.post(url, json=body if body is not None else {}, headers=hd)


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=20, follow_redirects=False) as h:
        db = c.db
        ph = PasswordHasher()
        master = await db.fetchrow("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false) returning user_id",
                                   f"master:qa-{RUN}", ph.hash(MPW))
        created: list[str] = []
        events: list[tuple[str, str]] = []
        try:
            await run(c, h, db, master, created, events)
        finally:
            # dọn: dữ liệu gieo + tài khoản/user qa (cascade phiên) + sự kiện đã publish
            await db.execute("delete from account_deals where account_id = any($1)", [ACC_A, ACC_B])
            await db.execute("delete from account_snapshots where account_id = any($1)", [ACC_A, ACC_B])
            await db.execute("delete from portal_users where login_key = any($1) or role='client' and login_key like 'mt5:99%' and display_name like 'qa-%'",
                             [f"master:qa-{RUN}", ACC_A, ACC_B])
            await db.execute("delete from mt_accounts where account_id = any($1)", [ACC_A, ACC_B])
            for st, mid in events:
                await c.r.xdel(st, mid)
    return R.finish()


async def run(c, h, db, master, created, events):
    # ---------------------------------------------------------------- 1. đăng nhập master, lỗi chung, cookie
    login = lambda pw, plat="master", user=f"qa-{RUN}", **kw: post(h, f"{AUTH}/auth/login", {"platform": plat, "login": user, "secret": pw, **kw}, extra=ip_hdr())  # noqa: E731
    r_bad = await login("sai-mat-khau-xyz")
    r_unk = await login("sai-mat-khau-xyz", user=f"khong-ton-tai-{RUN}")
    r_unk2 = await login("sai", plat="mt5", user="12345678")
    R.check("login/loi-chung-chong-do-tai-khoan", r_bad.status_code == r_unk.status_code == r_unk2.status_code == 401 and r_bad.json() == r_unk.json() == r_unk2.json(),
            f"{r_bad.status_code}/{r_unk.status_code}/{r_unk2.status_code}", "critical")
    r = await login(MPW)
    msid = sid_of(r)
    sc = r.headers.get("set-cookie", "")
    R.check("login/master-ok", r.status_code == 200 and r.json()["role"] == "master" and len(msid) >= 40, f"{r.status_code}", "critical")
    R.check("login/cookie-HttpOnly+Secure+SameSite=Strict", all(x in sc for x in ("HttpOnly", "Secure")) and "samesite=strict" in sc.lower() and "Path=/" in sc, "", "critical")
    dbs = await db.fetchval("select count(*) from portal_sessions where session_id=$1", msid)
    dbh = await db.fetchval("select count(*) from portal_sessions where session_id=$1", hashlib.sha256(msid.encode()).hexdigest())
    R.check("login/phien-luu-BAM-khong-luu-id-goc", dbs == 0 and dbh == 1, f"raw={dbs} hash={dbh}", "critical")
    R.check("login/mat-khau-argon2id", (await db.fetchval("select password_hash from portal_users where user_id=$1", master["user_id"])).startswith("$argon2id$"), "", "high")
    me = await h.get(f"{AUTH}/auth/me", headers=ck(msid))
    R.check("me/master", me.status_code == 200 and me.json()["accounts"] == ["*"], f"{me.status_code}", "high")
    R.check("me/khong-cookie->401", (await h.get(f"{AUTH}/auth/me")).status_code == 401, "", "high")
    R.check("me/cookie-gia->401", (await h.get(f"{AUTH}/auth/me", headers=ck("a" * 43))).status_code == 401, "", "high")

    # CSRF / Origin
    r = await post(h, f"{AUTH}/auth/admin/accounts", {"platform": "mt5", "login": 1}, msid, origin="http://evil.example")
    R.check("csrf/origin-la->403", r.status_code == 403, f"{r.status_code}", "critical")
    r = await post(h, f"{AUTH}/auth/admin/accounts", {"platform": "mt5", "login": 1}, msid, extra={"Sec-Fetch-Site": "cross-site"})
    R.check("csrf/sec-fetch-site-cross->403", r.status_code == 403, f"{r.status_code}", "critical")

    # ---------------------------------------------------------------- 2. tạo 2 tài khoản MT, bí mật hiển thị một lần
    adm = lambda path, body=None, sid=msid, method="post": h.request(method.upper(), f"{AUTH}/auth/admin/{path}", json=body if method != "get" else None, headers=ck(sid))  # noqa: E731
    sec = {}
    for acc, lg in ((ACC_A, LA), (ACC_B, LB)):
        r = await adm("accounts", {"platform": "mt5", "login": lg, "server": "QA-Server", "label": f"qa-{acc}"})
        created.append(acc)
        sec[acc] = r.json().get("secrets", {})
        R.check(f"admin/tao-tai-khoan-{acc}", r.status_code == 201 and {"passcode", "pairing_code", "ea_token", "hmac_secret"} <= set(sec[acc]), f"{r.status_code}", "critical")
    row = await db.fetchrow("select * from mt_accounts where account_id=$1", ACC_A)
    s = sec[ACC_A]
    R.check("db/ea-token-luu-sha256", row["ea_token_hash"] == hashlib.sha256(s["ea_token"].encode()).hexdigest() and s["ea_token"] not in json.dumps(dict(row), default=str), "", "critical")
    R.check("db/hmac-secret-ma-hoa", row["ea_hmac_secret_enc"] and s["hmac_secret"] not in row["ea_hmac_secret_enc"] and row["ea_hmac_secret_enc"].startswith("gAAAA"), "", "critical")
    R.check("db/pairing-chi-luu-bam", row["pairing_code_hash"] == hashlib.sha256(re.sub("[^A-Za-z0-9]", "", s["pairing_code"]).upper().encode()).hexdigest(), "", "high")
    R.check("db/passcode-chi-luu-argon2", (await db.fetchval("select password_hash from portal_users where login_key=$1", ACC_A)).startswith("$argon2id$"), "", "critical")
    r = await adm("accounts", {"platform": "mt5", "login": LA, "server": "QA-Server"})
    R.check("admin/trung-tai-khoan->409", r.status_code == 409, f"{r.status_code}", "medium")
    lst = (await adm("accounts", method="get")).json()["items"]
    R.check("admin/danh-sach-khong-lo-bi-mat", {a["account_id"] for a in lst} >= {ACC_A, ACC_B} and all(sec[k][f] not in json.dumps(lst) for k in sec for f in ("ea_token", "hmac_secret", "passcode", "pairing_code")) and not any("hash" in k or k.endswith("_enc") for a in lst for k in a), "", "critical")

    # ---------------------------------------------------------------- 3. client: đăng nhập, đổi mật khẩu bắt buộc
    ca = lambda pw, **kw: login(pw, "mt5", str(LA), **kw)  # noqa: E731
    r = await ca(s["passcode"])
    csid_a = sid_of(r)
    R.check("client/login-bang-passcode", r.status_code == 200 and r.json()["role"] == "client" and r.json()["must_change_password"] is True and r.json()["accounts"] == [ACC_A], f"{r.status_code}", "critical")
    r = await h.get(f"{AUTH}/auth/admin/accounts", headers=ck(csid_a))
    R.check("client/khong-vao-API-master", r.status_code in (403,), f"{r.status_code}", "critical")
    r = await h.get(f"{AUTH}/auth/verify", headers={**ck(csid_a), "X-Original-URI": "/api/v1/accounts"})
    R.check("client/must-change->verify-401", r.status_code == 401, f"{r.status_code}", "critical")
    r = await post(h, f"{AUTH}/auth/change-password", {"current_password": s["passcode"], "new_password": "ngan"}, csid_a)
    R.check("doi-mat-khau/chinh-sach-tu-choi", r.status_code == 422, f"{r.status_code}", "high")
    r = await post(h, f"{AUTH}/auth/change-password", {"current_password": "sai-xxxxxxxxxxxx", "new_password": STRONG}, csid_a, extra=ip_hdr())
    R.check("doi-mat-khau/mat-khau-cu-sai", r.status_code in (400, 401), f"{r.status_code}", "high")
    r = await post(h, f"{AUTH}/auth/change-password", {"current_password": s["passcode"], "new_password": STRONG}, csid_a)
    R.check("doi-mat-khau/ok", r.status_code == 200, f"{r.status_code}", "critical")
    r = await h.get(f"{AUTH}/auth/verify", headers={**ck(csid_a), "X-Original-URI": "/api/v1/accounts"})
    R.check("verify/client-ok-header-dung", r.status_code == 200 and r.headers.get("x-role") == "client" and r.headers.get("x-accounts") == ACC_A, f"{r.status_code} {r.headers.get('x-accounts')}", "critical")
    R.check("login/passcode-cu-het-hieu-luc", (await ca(s["passcode"])).status_code == 401, "", "critical")
    r = await ca(STRONG)
    csid_a = sid_of(r)
    R.check("login/client-mat-khau-moi", r.status_code == 200 and r.json()["must_change_password"] is False, "", "critical")

    # ---------------------------------------------------------------- 4. khoá tạm
    for _ in range(5):
        await login("sai-mat-khau-xyz", "mt5", str(LB), **{})  # cùng IP khác nhau mỗi lần (ip_hdr) -> thử lock theo tài khoản
    r = await login(sec[ACC_B]["passcode"], "mt5", str(LB))
    R.check("khoa-tam/sau-5-lan-sai-dung-pass-van-bi-chan", r.status_code == 401 and r.json()["detail"] == r_bad.json()["detail"], f"{r.status_code}", "critical")
    ur = await db.fetchrow("select locked_until from portal_users where login_key=$1", ACC_B)
    R.check("khoa-tam/ghi-DB-locked_until", ur["locked_until"] is not None, "", "high")
    uid_b = str(await db.fetchval("select user_id from portal_users where login_key=$1", ACC_B))
    r = await adm(f"users/{uid_b}/unlock")
    R.check("khoa-tam/master-mo-khoa", r.status_code == 200, f"{r.status_code}", "high")
    r = await login(sec[ACC_B]["passcode"], "mt5", str(LB))
    csid_b = sid_of(r)
    R.check("khoa-tam/dang-nhap-lai-ok", r.status_code == 200, f"{r.status_code}", "high")
    # rate limit theo IP
    ip = {"X-Real-IP": f"10.98.{int(RUN[:2], 16)}.{int(RUN[2:4], 16)}"}   # IP riêng mỗi lần chạy (cửa sổ giới hạn 10 phút)
    codes = [(await post(h, f"{AUTH}/auth/login", {"platform": "mt5", "login": f"1{i:07d}", "secret": "x"}, extra=ip)).status_code for i in range(35)]
    R.check("rate-limit/IP-sau-30-lan-sai->429", 429 in codes and codes[0] == 401, f"{codes.count(401)}x401 {codes.count(429)}x429", "high")
    # hoàn tác đổi pass B để dùng phiên: đổi mật khẩu B (bắt buộc) để có phiên đầy đủ
    r = await post(h, f"{AUTH}/auth/change-password", {"current_password": sec[ACC_B]["passcode"], "new_password": STRONG + "B"}, csid_b)
    R.check("client-B/doi-mat-khau", r.status_code == 200, f"{r.status_code}", "high")

    # ---------------------------------------------------------------- 5. ghép cặp bằng mã
    r = await adm(f"accounts/{ACC_A}/pairing-code")
    pc = r.json()["pairing_code"]
    bad = await post(h, f"{AUTH}/auth/pair", {"platform": "mt5", "login": str(LA), "pairing_code": "AAAA-BBBB-CCCC", "new_password": STRONG + "P"}, extra=ip_hdr())
    R.check("pair/ma-sai->400", bad.status_code == 400, f"{bad.status_code}", "high")
    ok = await post(h, f"{AUTH}/auth/pair", {"platform": "mt5", "login": str(LA), "pairing_code": pc.lower(), "new_password": STRONG + "P"}, extra=ip_hdr())
    R.check("pair/ma-dung-dat-mat-khau", ok.status_code == 200, f"{ok.status_code}", "critical")
    again = await post(h, f"{AUTH}/auth/pair", {"platform": "mt5", "login": str(LA), "pairing_code": pc, "new_password": STRONG + "Q"}, extra=ip_hdr())
    R.check("pair/ma-dung-mot-lan", again.status_code == 400, f"{again.status_code}", "critical")
    r = await h.get(f"{AUTH}/auth/me", headers=ck(csid_a))
    R.check("pair/thu-hoi-phien-cu", r.status_code == 401, f"{r.status_code}", "high")
    r = await ca(STRONG + "P")
    csid_a = sid_of(r)
    R.check("pair/dang-nhap-mat-khau-moi", r.status_code == 200, f"{r.status_code}", "critical")

    # ---------------------------------------------------------------- 6. đình chỉ / kích hoạt / reset / xoay token
    await adm(f"accounts/{ACC_B}/suspend")
    R.check("suspend/phien-bi-thu-hoi", (await h.get(f"{AUTH}/auth/me", headers=ck(csid_b))).status_code == 401, "", "critical")
    R.check("suspend/khong-dang-nhap-duoc", (await login(STRONG + "B", "mt5", str(LB))).status_code == 401, "", "critical")
    await adm(f"accounts/{ACC_B}/activate")
    r = await adm(f"accounts/{ACC_B}/reset-passcode")
    npc = r.json().get("passcode")
    R.check("reset-passcode/tra-mot-lan", r.status_code == 200 and npc, "", "high")
    R.check("reset-passcode/pass-cu-het-hieu-luc", (await login(STRONG + "B", "mt5", str(LB))).status_code == 401, "", "high")
    r = await login(npc, "mt5", str(LB))
    R.check("reset-passcode/dang-nhap-bang-pass-moi-phai-doi", r.status_code == 200 and r.json()["must_change_password"] is True, "", "high")
    old_hash = (await db.fetchrow("select ea_token_hash, ea_hmac_secret_enc from mt_accounts where account_id=$1", ACC_A))
    t = (await adm(f"accounts/{ACC_A}/rotate-ea-token")).json()["ea_token"]
    hm = (await adm(f"accounts/{ACC_A}/rotate-hmac")).json()["hmac_secret"]
    new_hash = (await db.fetchrow("select ea_token_hash, ea_hmac_secret_enc from mt_accounts where account_id=$1", ACC_A))
    R.check("rotate/ea-token+hmac-doi", new_hash["ea_token_hash"] != old_hash["ea_token_hash"] == hashlib.sha256(s["ea_token"].encode()).hexdigest()
            and new_hash["ea_token_hash"] == hashlib.sha256(t.encode()).hexdigest() and new_hash["ea_hmac_secret_enc"] != old_hash["ea_hmac_secret_enc"] and hm not in new_hash["ea_hmac_secret_enc"], "", "high")
    # master đăng nhập lại phải đổi mật khẩu? (qa master đã must_change=false)

    # ---------------------------------------------------------------- 7. TOTP master
    r = await post(h, f"{AUTH}/auth/totp/setup", {}, msid)
    tsec = r.json()["secret"]
    R.check("totp/setup", r.status_code == 200 and r.json()["otpauth_uri"].startswith("otpauth://totp/"), "", "high")
    r = await post(h, f"{AUTH}/auth/totp/enable", {"code": "000000"}, msid)
    R.check("totp/enable-ma-sai->400", r.status_code == 400, f"{r.status_code}", "high")
    code = pyotp.TOTP(tsec).now()
    r = await post(h, f"{AUTH}/auth/totp/enable", {"code": code}, msid)
    R.check("totp/enable-ok", r.status_code == 200, f"{r.status_code}", "high")
    r = await login(MPW)
    R.check("totp/thieu-ma->totp_required", r.status_code == 401 and r.json().get("totp_required") is True, f"{r.status_code}", "high")
    r = await login(MPW, totp=code)   # mã vừa dùng để bật -> chống phát lại
    R.check("totp/chong-phat-lai-ma-da-dung", r.status_code == 401, f"{r.status_code}", "high")
    nxt = pyotp.TOTP(tsec).at(int(__import__("time").time()) + 30)
    r = await login(MPW, totp=nxt)
    msid2 = sid_of(r)
    R.check("totp/ma-moi-dang-nhap-ok", r.status_code == 200, f"{r.status_code}", "high")
    R.check("totp/secret-ma-hoa-trong-DB", tsec not in (await db.fetchval("select totp_secret_enc from portal_users where user_id=$1", master["user_id"]) or ""), "", "critical")
    await db.execute("update portal_users set totp_enabled=false, totp_secret_enc=null where user_id=$1", master["user_id"])   # dọn: tắt TOTP để các bước sau không cần mã
    msid = msid2

    # ---------------------------------------------------------------- 8. gieo dữ liệu theo tài khoản + kiểm phân quyền qua nginx (đường thật)
    ts = now()
    for acc, bal in ((ACC_A, 1111.0), (ACC_B, 2222.0)):
        await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) values ($1,'mt5',$2,$3,$3,0,'[]'::jsonb)", acc, ts, bal)
        await db.execute("insert into account_deals (account_id, ticket, position_id, platform, symbol, broker_symbol, side, volume, time_close, profit, source) "
                         "values ($1,'1','1','mt5','EURUSD','EURUSD','buy',0.1,$2,5,'qa') on conflict do nothing", acc, ts)
    async def web(path, sid, method="get", json_=None, extra=None):
        hd = {**(ck(sid) if sid else {}), **(extra or {})}
        if method != "get":
            hd["Origin"] = f"http://{WEB_HOST}"
        return await h.request(method.upper(), WEB + path, headers=hd, json=json_)

    r = await h.get(WEB + "/", follow_redirects=False)
    R.check("nginx/chua-dang-nhap-/->302-login", r.status_code == 302 and r.headers["location"].startswith("/auth/login"), f"{r.status_code} {r.headers.get('location')}", "critical")
    r = await h.get(WEB + "/api/v1/accounts")
    R.check("nginx/chua-dang-nhap-api->401-json", r.status_code == 401 and r.json().get("detail") == "unauthorized", f"{r.status_code}", "critical")
    r = await h.get(WEB + "/api/v1/stream")
    R.check("nginx/chua-dang-nhap-ws-path->401", r.status_code == 401, f"{r.status_code}", "critical")
    R.check("nginx/auth-verify-khong-lo-ra-ngoai", (await h.get(WEB + "/auth/verify")).status_code == 404, "", "critical")
    R.check("nginx/trang-dang-nhap-cong-khai", (await h.get(WEB + "/auth/login")).status_code == 200 and (await h.get(WEB + "/auth/static/login.js")).status_code == 200, "", "high")
    r = await h.get(WEB + "/auth/admin/accounts")
    R.check("nginx/admin-api-chua-dang-nhap->401", r.status_code == 401, f"{r.status_code}", "critical")
    r = await h.get(WEB + "/c/", follow_redirects=False)
    R.check("nginx/vo-tinh-/c/-cong-khai-khong-bi-chuyen-dang-nhap", not (r.status_code in (301, 302) and "/auth/login" in r.headers.get("location", "")) and r.status_code != 401, f"{r.status_code}", "high")
    r = await h.get(WEB + "/", headers={"Authorization": "Basic " + __import__("base64").b64encode(b"admin:admin").decode()})
    R.check("nginx/basic-auth-du-phong-tat-mac-dinh", r.status_code in (302, 401), f"{r.status_code}", "critical")
    # đăng nhập qua nginx
    rr = await h.post(WEB + "/auth/login", json={"platform": "mt5", "login": str(LA), "secret": STRONG + "P"}, headers={"Origin": f"http://{WEB_HOST}"})
    wsid_a = sid_of(rr)
    R.check("nginx/login-client-A", rr.status_code == 200 and wsid_a, f"{rr.status_code}", "critical")
    rr = await h.post(WEB + "/auth/login", json={"platform": "mt5", "login": str(LB), "secret": "x"}, headers={"Origin": "http://evil.example"})
    R.check("nginx/login-origin-la->403", rr.status_code == 403, f"{rr.status_code}", "critical")
    rr = await h.post(WEB + "/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": MPW}, headers={"Origin": f"http://{WEB_HOST}"})
    wsid_m = sid_of(rr)
    R.check("nginx/login-master", rr.status_code == 200 and wsid_m, f"{rr.status_code}", "critical")
    # đổi mật khẩu B qua DB-free: B đã phải đổi; đăng nhập B bằng cách đặt lại
    rB = await login(npc, "mt5", str(LB))
    await post(h, f"{AUTH}/auth/change-password", {"current_password": npc, "new_password": STRONG + "B2"}, sid_of(rB))
    rr = await h.post(WEB + "/auth/login", json={"platform": "mt5", "login": str(LB), "secret": STRONG + "B2"}, headers={"Origin": f"http://{WEB_HOST}"})
    wsid_b = sid_of(rr)

    # 8a. giả mạo header danh tính từ client
    spoof = {"X-Role": "master", "X-Accounts": "*", "X-User-Id": "x", "X-Auth-Secret": "doan", "X-API-Key": "doan"}
    r = await web("/api/v1/me", wsid_a, extra=spoof)
    R.check("idor/gia-mao-header-X-Role-bi-nginx-de", r.status_code == 200 and r.json()["role"] == "client" and r.json()["accounts"] == [ACC_A], f"{r.status_code} {r.text[:120]}", "critical")
    r = await web("/api/v1/accounts", wsid_a, extra=spoof)
    ids = sorted(a["account_id"] for a in r.json()) if r.status_code == 200 else None
    R.check("idor/accounts-client-A-chi-thay-A", ids == [ACC_A], f"{ids}", "critical")
    r = await h.get(f"{GATEWAY}/v1/accounts", headers={"X-API-Key": API_KEY, "X-Role": "master", "X-Accounts": "*"})
    R.check("idor/truc-tiep-gateway-header-gia-thieu-secret->403", r.status_code == 403, f"{r.status_code}", "critical")
    r = await h.get(f"{GATEWAY}/v1/accounts", headers={"X-API-Key": API_KEY})
    R.check("gateway/dich-vu-noi-bo-API-key-van-chay", r.status_code == 200, f"{r.status_code}", "critical")
    r = await h.get(f"{GATEWAY}/v1/accounts")
    R.check("gateway/thieu-API-key->401", r.status_code == 401, "", "critical")
    r = await web("/api/v1/accounts", wsid_m)
    R.check("idor/master-thay-ca-A-va-B", r.status_code == 200 and {ACC_A, ACC_B} <= {a["account_id"] for a in r.json()}, "", "critical")
    r = await web("/api/v1/overview", wsid_a)
    R.check("idor/overview-A-khong-lo-B", r.status_code == 200 and ACC_B not in r.text and ACC_A in r.text, f"{r.status_code}", "critical")

    # 8b. IDOR trên từng endpoint theo tài khoản (A -> B)
    checks = {
        "equity-history": f"/api/v1/equity-history?account_id={ACC_B}",
        "risk-chi-tiet": f"/api/v1/risk/accounts/{ACC_B}",
        "journal-summary": f"/api/v1/journal/{ACC_B}/summary",
        "journal-deals": f"/api/v1/journal/{ACC_B}/deals",
        "journal-notes": f"/api/v1/journal/{ACC_B}/notes",
        "journal-review": f"/api/v1/journal/{ACC_B}/review",
        "journal-traversal": f"/api/v1/journal/{ACC_A}%2F..%2F{ACC_B}/summary",
        "equity-2-gia-tri": f"/api/v1/equity-history?account_id={ACC_A}&account_id={ACC_B}",
        "equity-chu-hoa": f"/api/v1/equity-history?account_id={ACC_B.upper()}",
    }
    for name, path in checks.items():
        r = await web(path, wsid_a)
        R.check(f"idor/A->B/{name}", r.status_code in (403, 404), f"{r.status_code}", "critical")
        R.check(f"idor/A->B/{name}/khong-ro-ri-du-lieu", "2222" not in r.text, "", "critical")
    r = await web(f"/api/v1/equity-history?account_id={ACC_A}", wsid_a)
    R.check("idor/A->A/equity-history-ok", r.status_code == 200 and any(abs(p["balance"] - 1111.0) < 1e-6 for p in r.json()), f"{r.status_code}", "critical")
    r = await web(f"/api/v1/equity-history?account_id={ACC_B}", wsid_b)
    R.check("idor/B->B/equity-history-ok", r.status_code == 200 and any(abs(p["balance"] - 2222.0) < 1e-6 for p in r.json()), f"{r.status_code}", "critical")
    r = await web(f"/api/v1/equity-history?account_id={ACC_B}", wsid_m)
    R.check("idor/master->B-ok", r.status_code == 200, f"{r.status_code}", "critical")
    r = await web("/api/v1/journal/accounts", wsid_a)
    R.check("idor/journal-accounts-loc", r.status_code == 200 and ACC_B not in r.text and all(x["account_id"] == ACC_A for x in r.json()["items"]), f"{r.status_code}", "critical")
    r = await web("/api/v1/risk/accounts", wsid_a)
    R.check("idor/risk-accounts-loc", r.status_code == 200 and ACC_B not in r.text, f"{r.status_code}", "critical")
    r = await web(f"/api/v1/journal/{ACC_A}/summary", wsid_a)
    R.check("idor/A->A/journal-summary-khong-bi-chan", r.status_code in (200, 404), f"{r.status_code}", "high")
    # ghi ghi chú
    rc = await web("/api/v1/user/csrf", wsid_a)
    tok = rc.json()["token"] if rc.status_code == 200 else ""
    r = await web(f"/api/v1/journal/{ACC_B}/notes/deal/1", wsid_a, "put", {"note": "xam-nhap", "tags": []}, {"X-CSRF-Token": tok})
    R.check("idor/A-ghi-note-cua-B->403", r.status_code == 403, f"{r.status_code}", "critical")
    r = await web(f"/api/v1/journal/{ACC_B}/notes/deal/1", wsid_a, "delete", None, {"X-CSRF-Token": tok})
    R.check("idor/A-xoa-note-cua-B->403", r.status_code == 403, f"{r.status_code}", "critical")
    n_b = await db.fetchval("select count(*) from journal_notes where account_id=$1", ACC_B)
    R.check("idor/note-cua-B-khong-bi-ghi", n_b == 0, f"{n_b}", "critical")

    # 8c. route chỉ master
    for p in ("/api/v1/system", "/api/v1/alerts", "/api/v1/paper/overview", "/api/v1/paper/accounts", "/api/v1/user/prefs",
              "/api/v1/reports", "/api/v1/data-sources"):
        r = await web(p, wsid_a)
        R.check(f"phan-quyen/client-bi-chan{p}", r.status_code == 403, f"{r.status_code}", "critical")
        r = await web(p, wsid_m)
        R.check(f"phan-quyen/master-vao-duoc{p}", r.status_code in (200, 404, 502, 503), f"{r.status_code}", "high")
    for p in ("/api/v1/quotes/latest", "/api/v1/news", "/api/v1/calendar", "/api/v1/symbols", "/api/v1/risk-windows", "/api/v1/analytics/overview", "/api/v1/experts"):
        r = await web(p, wsid_a)
        R.check(f"phan-quyen/client-du-lieu-chung{p}", r.status_code == 200, f"{r.status_code}", "high")
    # cảnh báo cá nhân: client được dùng nhưng chỉ trên rule CỦA MÌNH (IDOR đối chiếu ở test_client_backend.py)
    r = await web("/api/v1/user/rules", wsid_a)
    R.check("phan-quyen/client-xem-rule-cua-minh", r.status_code == 200 and isinstance(r.json().get("items"), list), f"{r.status_code}", "high")
    r = await web("/api/v1/user/rules", wsid_a, "post", {})
    R.check("phan-quyen/client-tao-rule-rong-bi-tu-choi", r.status_code in (400, 403, 422), f"{r.status_code}", "critical")
    r = await web("/api/v1/me", wsid_m)
    R.check("me/gateway-master", r.status_code == 200 and r.json()["role"] == "master" and {ACC_A, ACC_B} <= set(r.json()["accounts"]), f"{r.status_code}", "high")

    # ---------------------------------------------------------------- 9. WebSocket qua nginx (xác thực + lọc theo tài khoản)
    import websockets
    url = WEB.replace("http://", "ws://") + "/api/v1/stream?streams=account.snapshots"

    async def ws_collect(sid, n_expected, timeout=8.0):
        kw = {"additional_headers": ck(sid)} if sid else {}
        try:
            conn = websockets.connect(url, **kw)
        except TypeError:
            conn = websockets.connect(url, extra_headers=ck(sid) if sid else None)
        got = []
        async with conn as ws:
            ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert ready["type"] == "ready"
            await asyncio.sleep(2.0)   # (QA-C: 0.7 flaky khi tải cao) để pump của gateway bắt đầu XREAD từ '$' trước khi publish
            for acc in (ACC_B, ACC_A):
                snap = {"account_id": acc, "platform": "mt5", "ts": now().isoformat(), "balance": 3333.0 if acc == ACC_B else 4444.0, "equity": 1, "margin": 0,
                        "positions": [], "free_margin": 1, "margin_level": 0, "currency": "USD", "leverage": 100, "login": 1, "server": "qa", "orders": []}
                mid = await publish(c.r, "account.snapshots", mk_event("account_snapshot", snap))
                events.append(("account.snapshots", mid))
            end = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < end:
                try:
                    m = json.loads(await asyncio.wait_for(ws.recv(), 1.5))
                except asyncio.TimeoutError:
                    break
                if m.get("type") == "event":
                    got.append(m["event"]["payload"]["account_id"])
        return got

    try:
        g_a = await ws_collect(wsid_a, 2, 4)
        R.check("ws/client-A-chi-nhan-su-kien-cua-A-va-chi-A", ACC_A in g_a and set(g_a) == {ACC_A}, f"{sorted(set(g_a))}", "critical")
        g_m = await ws_collect(wsid_m, 2, 4)
        R.check("ws/master-nhan-ca-hai", set(g_m) >= {ACC_A, ACC_B}, f"{sorted(set(g_m))}", "critical")
    except Exception as e:  # noqa: BLE001
        R.check("ws/ket-noi-qua-nginx", False, repr(e)[:160], "high")
    try:
        await ws_collect("", 0, 1)
        R.check("ws/khong-cookie-bi-tu-choi", False, "ket noi duoc", "critical")
    except Exception as e:  # noqa: BLE001
        R.check("ws/khong-cookie-bi-tu-choi", True, type(e).__name__, "critical")
    try:
        async with websockets.connect(WEB.replace("http://", "ws://") + "/api/v1/stream?streams=alerts.out", additional_headers=ck(wsid_a)) as ws:
            m = await asyncio.wait_for(ws.recv(), 3)
        R.check("ws/client-khong-dang-ky-alerts.out", False, str(m)[:80], "critical")
    except Exception as e:  # noqa: BLE001
        R.check("ws/client-khong-dang-ky-alerts.out", True, type(e).__name__, "critical")

    # ---------------------------------------------------------------- 10. thu hồi phiên, đăng xuất, audit
    r = await post(h, f"{AUTH}/auth/admin/sessions/" + hashlib.sha256(wsid_a.encode()).hexdigest() + "/revoke", {}, msid)
    R.check("session/master-thu-hoi-phien-client", r.status_code == 200, f"{r.status_code}", "high")
    await asyncio.sleep(0.2)
    r = await web("/api/v1/accounts", wsid_a)
    R.check("session/phien-bi-thu-hoi->API-401", r.status_code == 401, f"{r.status_code}", "critical")
    r = await post(h, f"{AUTH}/auth/logout", {}, wsid_b)
    R.check("session/logout", r.status_code == 200 and (await web("/api/v1/accounts", wsid_b)).status_code == 401, "", "critical")
    r = await adm("view-as", {"account_id": ACC_A})
    R.check("audit/view-as-thieu-ly-do->422", r.status_code == 422, f"{r.status_code}", "high")
    r = await adm("view-as", {"account_id": ACC_A, "reason": "qa e2e kiem tra ho tro khach"})
    R.check("view-as/master-chua-bat-TOTP->403-totp_required", r.status_code == 403 and r.json().get("totp_required") is True, f"{r.status_code} {r.text[:100]}", "high")
    await db.execute("update portal_users set totp_enabled=true where user_id=$1", master["user_id"])   # view-as bắt buộc 2FA: bật tạm để kiểm đường thành công
    for _ in range(40):   # cache phiên của auth có TTL 5 giây: chờ tới khi thấy cờ TOTP mới (điều kiện, không sleep cố định)
        r = await adm("view-as", {"account_id": ACC_A, "reason": "qa e2e kiem tra ho tro khach"})
        if r.status_code != 403:
            break
        await asyncio.sleep(0.5)
    await db.execute("update portal_users set totp_enabled=false where user_id=$1", master["user_id"])
    R.check("audit/view-as-ghi-nhat-ky", r.status_code == 200, f"{r.status_code} {r.text[:120]}", "medium")
    r = await adm("view-as", {"account_id": ACC_A, "reason": "x"}, sid=wsid_b)
    R.check("view-as/client-khong-dung-duoc", r.status_code in (401, 403), f"{r.status_code}", "critical")
    a = (await adm("audit?limit=500", method="get")).json()["items"]
    acts = {x["action"] for x in a}
    R.check("audit/co-cac-su-kien-chinh", {"login_ok", "login_fail", "account_created", "pair_ok", "pair_fail", "account_suspended", "passcode_reset", "view_as", "account_locked"} <= acts, f"thieu={sorted({'login_ok','login_fail','account_created','pair_ok','pair_fail','account_suspended','passcode_reset','view_as','account_locked'} - acts)}", "high")
    R.check("audit/khong-chua-bi-mat", s["passcode"] not in json.dumps(a) and STRONG not in json.dumps(a) and MPW not in json.dumps(a), "", "critical")
    v = (await adm("audit/verify", method="get")).json()
    R.check("audit/chuoi-bam-toan-ven", v.get("ok") is True and v.get("rows", 0) > 10, f"{v}", "high")
    # xoá tài khoản qua API
    for acc in (ACC_A, ACC_B):
        r = await h.delete(f"{AUTH}/auth/admin/accounts/{acc}", headers=ck(msid))
        R.check(f"admin/xoa-tai-khoan-{acc}", r.status_code == 200 and r.json()["user_deleted"] is True, f"{r.status_code}", "medium")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
