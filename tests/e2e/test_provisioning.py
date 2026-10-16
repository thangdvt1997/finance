"""E2E cấp phát tài khoản động: master tạo tài khoản MT (API admin) -> EA (mô phỏng, ký HMAC) -> mt-bridge -> auth -> DB -> gateway/nginx (master + client).
Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_provisioning.py     (cần BRIDGE_AUTH_TOKEN trong env = infra/.env, qua run_remote)
Không đặt lệnh. Tài khoản test mt5:98xxxxxx; dọn sạch cuối (xoá tài khoản/user/snapshots). Không in token/secret."""
import asyncio
import hashlib
import hmac as hm
import json
import os
import re
import secrets
import subprocess
import sys
import time

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import API_KEY, BRIDGE, GATEWAY, Ctx, Results, wait_for  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
WEB_HOST = WEB.split("//", 1)[1]
BTOK = os.environ.get("BRIDGE_AUTH_TOKEN", "")
RUN = secrets.token_hex(3)
N = int(RUN, 16) % 90000
LA, LB, LC = 98000000 + N, 98100000 + N, 98200000 + N
A, B, C = (f"mt5:{x}" for x in (LA, LB, LC))
MPW, CPW = "QaMaster-" + secrets.token_urlsafe(12), "Moi-" + secrets.token_urlsafe(12)
R = Results("provisioning")
sid_of = lambda r: (re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")) or [None, ""])[1]  # noqa: E731
ck = lambda s: {"Cookie": f"ts_session={s}"}  # noqa: E731
IB = {"Authorization": f"Bearer {BTOK}"}
_ip = iter(range(10, 250))


def fake_ip() -> dict:
    return {"X-Real-IP": f"10.97.0.{next(_ip)}"}


def batch(acc: str, login: int, bal: float = 1234.5) -> dict:
    return {"v": 1, "account_id": acc, "platform": "mt5", "ts": int(time.time()), "nonce": "n" + secrets.token_hex(8), "seq": 0,
            "account": {"login": login, "server": "QA-Server", "currency": "USD", "leverage": 100, "balance": bal, "equity": bal, "margin": 0, "free_margin": bal},
            "positions": [], "orders": [], "agent": {"ea": "1.1", "build": 4000, "company": "QA Broker", "rtt_ms": 20, "fail": 0}}


async def ingest(h, acc, token, secret, login, bal=1234.5, sign=True, bad_sig=False) -> int:
    b = batch(acc, login, bal)
    raw = json.dumps(b).encode()
    hd = {"Authorization": f"Bearer {token}", "X-MT-Account": acc, "Content-Type": "application/json"}
    if sign:
        sig = hm.new(secret.encode(), f"{b['ts']}.{b['nonce']}.".encode() + raw, hashlib.sha256).hexdigest()
        hd["X-MT-Sig"] = "0" * 64 if bad_sig else sig
    return (await h.post(BRIDGE + "/ingest/v1", content=raw, headers=hd)).status_code


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=20, follow_redirects=False) as h:
        db = c.db
        ph = PasswordHasher()
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)", f"master:qa-{RUN}", ph.hash(MPW))
        try:
            await run(c, h, db)
        finally:
            ids = [A, B, C]
            await db.execute("delete from account_snapshots where account_id = any($1)", ids)
            await db.execute("delete from account_deals where account_id = any($1)", ids)
            await db.execute("delete from portal_users where login_key = any($1) or login_key=$2", ids, f"master:qa-{RUN}")
            await db.execute("delete from mt_accounts where account_id = any($1)", ids)
    return R.finish()


async def run(c, h, db):
    R.check("cau-hinh/BRIDGE_AUTH_TOKEN-co-trong-env-test", bool(BTOK), "", "critical")
    r = await h.post(f"{AUTH}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": MPW}, headers=fake_ip())
    msid = sid_of(r)
    R.check("master/login", r.status_code == 200 and msid, f"{r.status_code}", "critical")
    adm = lambda path, body=None, method="post": h.request(method.upper(), f"{AUTH}/auth/admin/{path}", json=body if method != "get" else None, headers=ck(msid))  # noqa: E731

    # ------------------------------------------------ 1. API nội bộ: chỉ có token dịch vụ
    R.check("noi-bo/khong-token->401", (await h.get(f"{AUTH}/internal/mt-accounts")).status_code == 401, "", "critical")
    R.check("noi-bo/sai-token->401", (await h.get(f"{AUTH}/internal/mt-accounts", headers={"Authorization": "Bearer sai"})).status_code == 401, "", "critical")
    R.check("noi-bo/cookie-master-khong-thay-the-token", (await h.get(f"{AUTH}/internal/mt-accounts", headers=ck(msid))).status_code == 401, "", "critical")
    R.check("noi-bo/khong-lo-qua-nginx", (await h.get(WEB + "/internal/mt-accounts", headers=IB)).status_code in (301, 302, 401, 404) and
            "accounts" not in (await h.get(WEB + "/internal/mt-accounts", headers=IB)).text, "", "critical")

    # ------------------------------------------------ 2. master tạo tài khoản -> bridge thấy bản ghi (pending)
    r = await adm("accounts", {"platform": "mt5", "login": LA, "server": "QA-Server", "label": f"qa-{RUN}"})
    sa = r.json()["secrets"]
    R.check("master/tao-tai-khoan-A", r.status_code == 201, f"{r.status_code}", "critical")
    rec = (await h.get(f"{AUTH}/internal/mt-accounts/{A.replace(':', '%3A')}", headers=IB))
    rj = rec.json() if rec.status_code == 200 else {}
    R.check("noi-bo/record-dung-dinh-dang", rec.status_code == 200 and rj["status"] == "pending" and rj["require_hmac"] is True and rj["platform"] == "mt5"
            and rj["ea_token_hash"] == hashlib.sha256(sa["ea_token"].encode()).hexdigest() and rj["hmac_secret"] == sa["hmac_secret"] and isinstance(rj["rev"], int), f"{rec.status_code}", "critical")
    lst = (await h.get(f"{AUTH}/internal/mt-accounts", headers=IB)).json()
    R.check("noi-bo/list-co-rev-va-tai-khoan", isinstance(lst["rev"], int) and any(a["account_id"] == A for a in lst["accounts"]), "", "high")
    R.check("noi-bo/404-tai-khoan-la", (await h.get(f"{AUTH}/internal/mt-accounts/mt5%3A1", headers=IB)).status_code == 404, "", "high")

    # ------------------------------------------------ 3. EA (token+HMAC do master giao): pending -> 202; duyệt -> 200
    st = await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA)
    R.check("bridge/pending->202-khong-nhan-du-lieu", st == 202, f"{st}", "critical")
    r = await adm(f"accounts/{A}/activate")
    R.check("master/duyet-kich-hoat", r.status_code == 200 and r.json()["status"] == "active", f"{r.status_code}", "critical")
    st = await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA, 1234.5)
    R.check("bridge/active+HMAC-dung->200-ngay-khong-cho-TTL", st == 200, f"{st}", "critical")
    R.check("bridge/HMAC-sai->401", await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA, bad_sig=True) == 401, "", "critical")
    R.check("bridge/thieu-HMAC->401", await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA, sign=False) == 401, "", "critical")
    R.check("bridge/token-sai->401", await ingest(h, A, "x" * 43, sa["hmac_secret"], LA) == 401, "", "critical")

    # ------------------------------------------------ 4. hiển thị: DB -> gateway (master) -> client qua nginx
    ok = await wait_for(lambda: db.fetchval("select count(*) from account_snapshots where account_id=$1", A), 20)
    R.check("du-lieu/snapshot-vao-DB", bool(ok), "", "critical")
    r = await h.get(f"{GATEWAY}/v1/accounts", headers={"X-API-Key": API_KEY})
    R.check("master/v1-accounts-thay-tai-khoan-moi", r.status_code == 200 and any(a["account_id"] == A for a in r.json()), "", "critical")
    # client đăng nhập (passcode -> đổi mật khẩu bắt buộc) rồi xem qua nginx
    r = await h.post(f"{WEB}/auth/login", json={"platform": "mt5", "login": str(LA), "secret": sa["passcode"]}, headers={"Origin": f"http://{WEB_HOST}"})
    csid = sid_of(r)
    r = await h.post(f"{WEB}/auth/change-password", json={"current_password": sa["passcode"], "new_password": CPW}, headers={**ck(csid), "Origin": f"http://{WEB_HOST}"})
    R.check("client/doi-mat-khau-lan-dau", r.status_code == 200, f"{r.status_code}", "critical")
    r = await h.get(f"{WEB}/api/v1/accounts", headers=ck(csid))
    R.check("client/thay-tai-khoan-cua-minh-qua-nginx", r.status_code == 200 and [a["account_id"] for a in r.json()] == [A], f"{r.status_code} {r.text[:80]}", "critical")
    # sức khoẻ EA đẩy lên auth qua /seen (bridge flush ~30s)
    async def online():
        a = [x for x in (await adm("accounts", method="get")).json()["items"] if x["account_id"] == A][0]
        return a if a.get("ea_status") in ("online", "degraded") and a.get("last_seen_at") else None
    await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA, 1235.5)
    a = await wait_for(online, 45, 3)
    R.check("suc-khoe/ea_status+last_seen-len-auth-qua-seen", bool(a) and a["ea_version"] and a["ea_broker"], f"{(a or {}).get('ea_status')}", "high")

    # ------------------------------------------------ 5. xoay token / HMAC / đình chỉ: hiệu lực NGAY
    nt = (await adm(f"accounts/{A}/rotate-ea-token")).json()["ea_token"]
    t0 = time.time()
    R.check("xoay-token/token-cu-bi-tu-choi-ngay", await ingest(h, A, sa["ea_token"], sa["hmac_secret"], LA) == 401, f"{time.time()-t0:.2f}s", "critical")
    R.check("xoay-token/token-moi-dung", await ingest(h, A, nt, sa["hmac_secret"], LA) == 200, "", "critical")
    nh = (await adm(f"accounts/{A}/rotate-hmac")).json()["hmac_secret"]
    R.check("xoay-hmac/secret-cu-bi-tu-choi-ngay", await ingest(h, A, nt, sa["hmac_secret"], LA) == 401, "", "critical")
    R.check("xoay-hmac/secret-moi-dung", await ingest(h, A, nt, nh, LA) == 200, "", "critical")
    await adm(f"accounts/{A}/suspend")
    R.check("dinh-chi/403-ngay", await ingest(h, A, nt, nh, LA) == 403, "", "critical")
    R.check("dinh-chi/client-het-phien", (await h.get(f"{WEB}/api/v1/accounts", headers=ck(csid))).status_code == 401, "", "critical")
    await adm(f"accounts/{A}/activate")
    R.check("kich-hoat-lai/200", await ingest(h, A, nt, nh, LA) == 200, "", "critical")

    # ------------------------------------------------ 6. PairCode: EA gọi /register, nhận credential MỘT lần
    r = await adm("accounts", {"platform": "mt5", "login": LB, "server": "QA-Server", "label": f"qa-b-{RUN}"})
    sb = r.json()["secrets"]
    reg = lambda **kw: h.post(BRIDGE + "/ingest/v1/register", json={"v": 1, "platform": "mt5", "login": LB, "server": "QA-Server", "company": "QA Broker", "build": 4000, "ea": "1.1", **kw})  # noqa: E731
    r = await reg(pair_code="AAAA-BBBB-CCCC")
    R.check("pair-code/sai->403", r.status_code in (403,), f"{r.status_code}", "critical")
    r = await reg(pair_code=sb["pairing_code"])
    jb = r.json()
    R.check("pair-code/dung->active+token+hmac-mot-lan", r.status_code == 200 and jb.get("status") == "active" and jb.get("token") and jb.get("hmac_secret") and r.headers.get("cache-control") == "no-store", f"{r.status_code}", "critical")
    R.check("pair-code/dung-mot-lan", (await reg(pair_code=sb["pairing_code"])).status_code == 403, "", "critical")
    R.check("pair-code/credential-moi-chay-duoc", await ingest(h, B, jb["token"], jb["hmac_secret"], LB) == 200, "", "critical")
    R.check("pair-code/credential-cu-cua-master-het-hieu-luc", await ingest(h, B, sb["ea_token"], sb["hmac_secret"], LB) == 401, "", "critical")
    R.check("pair-code/khong-lo-bi-mat-trong-audit", jb["token"] not in json.dumps((await adm("audit?limit=300", method="get")).json()), "", "critical")

    # ------------------------------------------------ 7. EA tự đăng ký -> mã ghép cặp -> client ghép ở /auth/pair -> EA nhận credential
    regc = lambda **kw: h.post(BRIDGE + "/ingest/v1/register", json={"v": 1, "platform": "mt5", "login": LC, "server": "QA-Server", "company": "QA Broker", "build": 4000, "ea": "1.1", **kw})  # noqa: E731
    r = await regc()
    jc = r.json()
    R.check("tu-dang-ky/pending+pairing_code", r.status_code == 200 and jc.get("status") == "pending" and jc.get("pairing_code"), f"{r.status_code} {jc.get('status')}", "critical")
    row = await db.fetchrow("select status, client_id from mt_accounts where account_id=$1", C)
    R.check("tu-dang-ky/DB-pending-chua-co-chu", row and row["status"] == "pending" and row["client_id"] is None, "", "high")
    R.check("tu-dang-ky/chua-ghep-cap-ingest->202-hoac-401", await ingest(h, C, "x" * 43, "y" * 64, LC) in (202, 401), "", "high")
    r = await h.post(f"{AUTH}/auth/pair", json={"platform": "mt5", "login": str(LC), "pairing_code": jc["pairing_code"], "new_password": CPW + "C"}, headers=fake_ip())
    R.check("tu-dang-ky/client-ghep-cap-bang-ma", r.status_code == 200, f"{r.status_code}", "critical")
    r = await regc()
    jc2 = r.json()
    R.check("tu-dang-ky/EA-nhan-credential-sau-ghep-cap", r.status_code == 200 and jc2.get("status") == "active" and jc2.get("token") and jc2.get("hmac_secret"), f"{r.status_code} {jc2.get('status')}", "critical")
    R.check("tu-dang-ky/credential-chi-giao-mot-lan", not (await regc()).json().get("token"), "", "critical")
    R.check("tu-dang-ky/ingest-voi-credential-nhan-duoc", await ingest(h, C, jc2["token"], jc2["hmac_secret"], LC) == 200, "", "critical")
    r = await h.post(f"{AUTH}/auth/login", json={"platform": "mt5", "login": str(LC), "secret": CPW + "C"}, headers=fake_ip())
    R.check("tu-dang-ky/client-dang-nhap-thay-tai-khoan", r.status_code == 200 and r.json()["accounts"] == [C], f"{r.status_code}", "critical")

    # ------------------------------------------------ 8. xoá tài khoản -> bridge từ chối ngay
    for acc, tok, sec_ in ((A, nt, nh), (B, jb["token"], jb["hmac_secret"]), (C, jc2["token"], jc2["hmac_secret"])):
        lg = int(acc.split(":")[1])
        r = await h.delete(f"{AUTH}/auth/admin/accounts/{acc}", headers=ck(msid))
        R.check(f"xoa/{acc}", r.status_code == 200, f"{r.status_code}", "high")
        R.check(f"xoa/{acc}/bridge-tu-choi-ngay", await ingest(h, acc, tok, sec_, lg) in (401, 403, 404), "", "critical")
    # không lọt vào audit: bí mật
    au = json.dumps((await adm("audit?limit=500", method="get")).json())
    R.check("audit/khong-chua-token-hmac", nt not in au and nh not in au and jc2["token"] not in au, "", "critical")
    R.check("audit/chuoi-bam-con-toan-ven", (await adm("audit/verify", method="get")).json().get("ok") is True, "", "high")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
