"""E2E phía KHÁCH qua nginx client-ui (/c/): opt-in thông báo luật (mặc định tắt, chỉ khách đổi), báo cáo theo tài khoản (chỉ bản đã phát hành, IDOR), vai trò phụ không dùng được cổng khách.
Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_fleet_client.py   Dọn sạch cuối. READ-ONLY."""
import asyncio
import os
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import Ctx, Results  # noqa: E402

CUI = os.getenv("QA_CLIENT_UI", "http://client-ui:8080")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
RUN = secrets.token_hex(3)
N = int(RUN, 16) % 90000
LA, LB = 95000000 + N, 95100000 + N
A, B = f"mt5:{LA}", f"mt5:{LB}"
PW = {k: "Qa-" + secrets.token_urlsafe(12) for k in ("master", "a", "b", "staff")}
R = Results("fleet_client")
_ip = iter(range(10, 250))


def sid_of(r):
    m = re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", ""))
    return m.group(1) if m else ""


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=40, follow_redirects=False) as h:
        db, ph = c.db, PasswordHasher()
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)", f"master:qa-{RUN}", ph.hash(PW["master"]))
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('support',$1,'qa',$2,false)", f"master:qa-{RUN}-s", ph.hash(PW["staff"]))
        try:
            await run(h, db, ph)
        finally:
            await db.execute("delete from portal_users where login_key = any($1) or login_key like $2", [A, B], f"master:qa-{RUN}%")
            await db.execute("delete from account_snapshots where account_id = any($1)", [A, B])
            await db.execute("delete from mt_accounts where account_id = any($1)", [A, B])
    return R.finish()


async def run(h, db, ph):
    ip = lambda: {"X-Real-IP": f"10.93.0.{next(_ip)}"}  # noqa: E731
    OW, OC = {"Origin": "http://web-ui:8080"}, {"Origin": "http://client-ui:8080"}
    r = await h.post(f"{WEB}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": PW["master"]}, headers={**OW, **ip()})
    M = sid_of(r)
    R.check("master/login", bool(M), f"{r.status_code}", "critical")

    async def adm(method, path, body=None):
        await asyncio.sleep(1.05 if method != "GET" else 0.1)
        return await h.request(method, f"{WEB}/auth/admin/{path}", json=body, headers={**OW, "Cookie": f"ts_session={M}"})
    for acc, lg, k in ((A, LA, "a"), (B, LB, "b")):
        rr = await adm("POST", "accounts", {"platform": "mt5", "login": lg, "server": "QA", "label": f"qa-{RUN}-{k}"})
        sec = rr.json().get("secrets", {})
        await db.execute("update mt_accounts set status='active' where account_id=$1", acc)
        await db.execute("update portal_users set password_hash=$2, must_change_password=false where login_key=$1", acc, ph.hash(PW[k]))
        await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) select $1,'mt5', now() - make_interval(hours => g), 5000, 5000 + (g % 7) * 3, 0, '[]'::jsonb from generate_series(0, 96) g", acc)
        R.check(f"setup/{acc}", rr.status_code == 201 and bool(sec.get("passcode")), f"{rr.status_code}", "critical")
    ra = await h.post(f"{CUI}/c/auth/login", json={"platform": "mt5", "login": str(LA), "secret": PW["a"]}, headers={**OC, **ip()})
    rb = await h.post(f"{CUI}/c/auth/login", json={"platform": "mt5", "login": str(LB), "secret": PW["b"]}, headers={**OC, **ip()})
    SA, SB = sid_of(ra), sid_of(rb)
    R.check("khach/dang-nhap-A-B", bool(SA) and bool(SB), f"{ra.status_code} {rb.status_code}", "critical")
    ca, cb = {"Cookie": f"ts_session={SA}"}, {"Cookie": f"ts_session={SB}"}

    # opt-in mặc định tắt, chỉ khách đổi
    g = await h.get(f"{CUI}/c/auth/client/notify", headers=ca)
    R.check("notify/mac-dinh-tat", g.status_code == 200 and g.json()["enabled"] is False and g.json()["accounts"] == [A], f"{g.status_code} {g.text[:80]}", "critical")
    R.check("notify/PUT-thieu-Origin->403", (await h.put(f"{CUI}/c/auth/client/notify", json={"enabled": True}, headers=ca)).status_code == 403, "", "critical")
    R.check("notify/PUT-Origin-la->403", (await h.put(f"{CUI}/c/auth/client/notify", json={"enabled": True}, headers={**ca, "Origin": "http://evil.example"})).status_code == 403, "", "critical")
    p = await h.put(f"{CUI}/c/auth/client/notify", json={"enabled": True}, headers={**ca, **OC})
    R.check("notify/khach-A-bat", p.status_code == 200 and p.json()["enabled"] is True, f"{p.status_code}", "critical")
    R.check("notify/DB-chi-A-doi", await db.fetchval("select client_notify from mt_accounts where account_id=$1", A) is True and await db.fetchval("select client_notify from mt_accounts where account_id=$1", B) is False, "", "critical")
    R.check("notify/body-thua-bi-tu-choi", (await h.put(f"{CUI}/c/auth/client/notify", json={"enabled": True, "account_id": B}, headers={**ca, **OC})).status_code == 422, "", "critical")
    R.check("notify/chua-dang-nhap->401", (await h.get(f"{CUI}/c/auth/client/notify")).status_code == 401, "", "high")
    # vai trò phụ không dùng được cổng khách (không phải client)
    rs = await h.post(f"{WEB}/auth/login", json={"platform": "master", "login": f"qa-{RUN}-s", "secret": PW["staff"]}, headers={**OW, **ip()})
    SS = sid_of(rs)
    R.check("support/khong-opt-in-giup-khach", (await h.put(f"{CUI}/c/auth/client/notify", json={"enabled": True}, headers={"Cookie": f"ts_session={SS}", **OC})).status_code == 403, "", "critical")

    # báo cáo: client chỉ thấy bản đã phát hành của chính mình
    csrf = (await h.get(f"{WEB}/api/v1/user/csrf", headers={"Cookie": f"ts_session={M}"})).json().get("token", "")
    gen = lambda acc, rel: h.post(f"{WEB}/api/v1/account-reports/generate", json={"account_id": acc, "kind": "daily", "release": rel}, headers={**OW, "X-CSRF-Token": csrf, "Cookie": f"ts_session={M}"})  # noqa: E731
    g1, g2 = await gen(A, False), await gen(B, True)
    R.check("bao-cao/master-tao", g1.status_code in (200, 201, 202) and g2.status_code in (200, 201, 202), f"{g1.status_code} {g2.status_code}", "high")
    la = await h.get(f"{CUI}/c/api/v1/account-reports", params={"account_id": A}, headers=ca)
    R.check("bao-cao/client-A-khong-thay-ban-chua-phat-hanh", la.status_code == 200 and la.json()["items"] == [], f"{la.status_code} {la.text[:100]}", "critical")
    R.check("bao-cao/IDOR-A-doc-danh-sach-cua-B->403", (await h.get(f"{CUI}/c/api/v1/account-reports", params={"account_id": B}, headers=ca)).status_code == 403, "", "critical")
    lb = await h.get(f"{CUI}/c/api/v1/account-reports", params={"account_id": B}, headers=cb)
    items = lb.json().get("items", []) if lb.status_code == 200 else []
    R.check("bao-cao/client-B-thay-ban-da-phat-hanh", len(items) == 1 and items[0].get("released") is True, f"{lb.status_code} {len(items)}", "critical")
    if items:
        per = items[0]["period"]
        d = await h.get(f"{CUI}/c/api/v1/account-reports/{B}/{per}/html", params={"kind": "daily"}, headers=cb)
        R.check("bao-cao/client-B-xem-html", d.status_code == 200 and "text/html" in d.headers.get("content-type", ""), f"{d.status_code}", "high")
        R.check("bao-cao/HTML-khong-ten-nguon", not any(w in d.text.lower() for w in ("dukascopy", "yahoo", "cafef", "forexfactory")), "", "high")
        R.check("bao-cao/IDOR-A-doc-bao-cao-cua-B->403", (await h.get(f"{CUI}/c/api/v1/account-reports/{B}/{per}/html", params={"kind": "daily"}, headers=ca)).status_code == 403, "", "critical")
        R.check("bao-cao/A-xem-ban-chua-phat-hanh-cua-A->404/403", (await h.get(f"{CUI}/c/api/v1/account-reports/{A}/{per}/html", params={"kind": "daily"}, headers=ca)).status_code in (403, 404), "", "critical")
    R.check("bao-cao/client-khong-ghi(generate)", (await h.post(f"{CUI}/c/api/v1/account-reports/generate", json={"account_id": A, "kind": "daily"}, headers={**ca, **OC})).status_code in (403, 404, 405), "", "critical")
    # dọn báo cáo thử
    for acc in (A, B):
        await h.request("DELETE", f"http://reporter:8000/account-reports/{acc}", headers={"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "")})


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
