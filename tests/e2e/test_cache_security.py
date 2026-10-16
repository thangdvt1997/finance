"""E2E an toàn của các tầng cache (nginx proxy_cache + auth_request cache + Redis cache gateway): IDOR, đầu độc cache, giả header, Vary/Cache-Control, thu hồi phiên, stampede.
Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_cache_security.py      (docs/PERFORMANCE.md §Bảo mật)
Dùng: web-ui/nginx (http://web-ui:8080 — đường thật của trình duyệt), auth (http://auth:8000, tạo phiên), gateway (http://api-gateway:8000, chỉ để đọc /metrics + so sánh), DB (gieo/dọn dữ liệu qa).
Dữ liệu test: master `master:cs-<run>`, 3 tài khoản MT 98xxxxxx; dọn sạch ở cuối. Không in bí mật; không có route đặt lệnh."""
import asyncio
import hashlib
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)

import os  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import API_KEY, GATEWAY, Ctx, Results, now  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
RUN = secrets.token_hex(3)
LA, LB, LC = (98000000 + int(RUN, 16) % 900000 + i * 1000000 for i in range(3))
ACC_A, ACC_B, ACC_C = f"mt5:{LA}", f"mt5:{LB}", f"mt5:{LC}"
MPW, STRONG = "QaMaster-" + secrets.token_urlsafe(12), "Moi-" + secrets.token_urlsafe(12)
R = Results("cache_security")
sid_of = lambda r: (re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")) or [None, ""])[1]  # noqa: E731
ck = lambda sid: {"Cookie": f"ts_session={sid}"}  # noqa: E731
nip = iter(range(10, 250))
ip_hdr = lambda: {"X-Real-IP": f"10.97.0.{next(nip)}"}  # noqa: E731


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=30, follow_redirects=False) as h:
        db = c.db
        master = await db.fetchrow("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false) returning user_id",
                                   f"master:cs-{RUN}", PasswordHasher().hash(MPW))
        try:
            await run(c, h, db, master)
        finally:
            await db.execute("delete from account_snapshots where account_id = any($1)", [ACC_A, ACC_B, ACC_C])
            await db.execute("delete from portal_users where login_key = any($1) or role='client' and login_key = any($2)", [f"master:cs-{RUN}"], [ACC_A, ACC_B, ACC_C])
            await db.execute("delete from mt_accounts where account_id = any($1)", [ACC_A, ACC_B, ACC_C])
    return R.finish()


async def run(c, h, db, master):
    login = lambda user, pw, plat="master": h.post(f"{AUTH}/auth/login", json={"platform": plat, "login": user, "secret": pw}, headers=ip_hdr())  # noqa: E731
    r = await login(f"cs-{RUN}", MPW)
    msid = sid_of(r)
    R.check("setup/master-login", r.status_code == 200 and msid, f"{r.status_code}", "critical")
    sids = {}
    for acc, lg in ((ACC_A, LA), (ACC_B, LB), (ACC_C, LC)):
        r = await h.post(f"{AUTH}/auth/admin/accounts", json={"platform": "mt5", "login": lg, "server": "QA", "label": f"cs-{acc}"}, headers=ck(msid))
        pc = r.json()["secrets"]["passcode"]
        r = await login(str(lg), pc, "mt5")
        s0 = sid_of(r)
        r = await h.post(f"{AUTH}/auth/change-password", json={"current_password": pc, "new_password": STRONG}, headers=ck(s0))
        r = await login(str(lg), STRONG, "mt5")
        sids[acc] = sid_of(r)
        R.check(f"setup/client-{acc}", r.status_code == 200 and sids[acc], f"{r.status_code}", "critical")
    sa, sb, sc = sids[ACC_A], sids[ACC_B], sids[ACC_C]
    ts = now()
    for acc, bal in ((ACC_A, 1111.0), (ACC_B, 2222.0), (ACC_C, 3333.0)):
        await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) values ($1,'mt5',$2,$3,$3,0,'[]'::jsonb)", acc, ts, bal)

    async def web(path, sid, extra=None, enc=None):
        hd = {**(ck(sid) if sid else {}), **(extra or {})}
        if enc:
            hd["Accept-Encoding"] = enc
        return await h.get(WEB + path, headers=hd)

    # ------------------------------------------------------------ 1. dữ liệu dùng chung: micro-cache nginx khoá theo VAI TRÒ
    u = f"/api/v1/news?limit=5&offset={int(RUN, 16) % 90}"
    m1 = await web(u, msid)
    m2 = await web(u, msid)
    st1, st2 = m1.headers.get("x-cache-status"), m2.headers.get("x-cache-status")
    R.check("nginx/master-lan-1-MISS", m1.status_code == 200 and st1 in ("MISS", "EXPIRED", "STALE", "HIT"), f"{m1.status_code} {st1}", "high")
    R.check("nginx/master-lan-2-HIT", m2.status_code == 200 and st2 == "HIT" and m1.content == m2.content, f"{st2}", "high")
    a1 = await web(u, sa)
    R.check("nginx/client-KHONG-nhan-ban-cua-master", a1.status_code == 200 and a1.headers.get("x-cache-status") in ("MISS", "EXPIRED", "UPDATING"), f"{a1.headers.get('x-cache-status')}", "critical")
    b1 = await web(u, sb)
    R.check("nginx/client-B-dung-chung-ban-cua-client (cung vai tro, du lieu chung)", b1.status_code == 200 and b1.content == a1.content, f"{b1.headers.get('x-cache-status')}", "medium")
    R.check("nginx/khong-cookie->401-khong-doc-duoc-cache", (await web(u, None)).status_code == 401, "", "critical")
    R.check("nginx/cookie-gia->401", (await web(u, "A" * 43)).status_code == 401, "", "critical")
    spoof = {"X-Role": "master", "X-Accounts": "*", "X-User-Id": "x", "X-Auth-Secret": "doan", "X-API-Key": "doan", "X-Forwarded-Host": "evil.example", "X-Original-URI": "/c/x"}
    r = await web(u, sa, spoof)
    r2 = await web(u, msid)
    R.check("nginx/gia-header-khong-doi-khoa-cache", r.status_code == 200 and r.content == a1.content and r2.content == m1.content, "", "critical")
    ch = m2.headers.get("cache-control", "")
    R.check("http/du-lieu-chung-Cache-Control-private-khong-public", "private" in ch and "public" not in ch and "max-age" in ch and "x-accel-expires" not in m2.headers, ch, "critical")
    R.check("http/khong-lo-ten-nguon-qua-header", not any(k.lower().startswith(("x-source", "x-provider", "x-data-source")) for k in m2.headers) and "x-gw-cache" in m2.headers, ",".join(sorted(m2.headers)), "medium")
    R.check("http/ETag", bool(m2.headers.get("etag")), "", "low")

    # ------------------------------------------------------------ 2. theo tài khoản: không bao giờ qua cache chung; không rò chéo (nhiều vòng, đan xen)
    seen = {sa: set(), sb: set(), sc: set(), msid: set()}
    order = [sa, sb, msid, sc, sb, sa, sc, msid, sa, sb, sc, msid] * 2
    for sid in order:
        for p in ("/api/v1/accounts", "/api/v1/overview"):
            r = await web(p, sid)
            if r.status_code != 200:
                R.check(f"acc/{p}-{r.status_code}", False, r.text[:100], "critical")
                continue
            j = r.json()
            rows = j if p.endswith("accounts") else j["accounts"]
            seen[sid] |= {x["account_id"] for x in rows if x["account_id"] in (ACC_A, ACC_B, ACC_C)}
            if p.endswith("accounts"):
                R.check("acc/no-store-va-khong-nginx-cache", r.headers.get("cache-control", "").lower().find("no-store") >= 0 and r.headers.get("x-cache-status") in (None, "BYPASS"), r.headers.get("cache-control", ""), "critical")
    R.check("idor/cache/A-chi-thay-A", seen[sa] == {ACC_A}, f"{seen[sa]}", "critical")
    R.check("idor/cache/B-chi-thay-B", seen[sb] == {ACC_B}, f"{seen[sb]}", "critical")
    R.check("idor/cache/C-chi-thay-C", seen[sc] == {ACC_C}, f"{seen[sc]}", "critical")
    R.check("idor/cache/master-thay-ca-3", seen[msid] == {ACC_A, ACC_B, ACC_C}, f"{seen[msid]}", "critical")
    r = await web("/api/v1/accounts", sa, spoof)
    R.check("idor/cache/gia-X-Accounts-X-Role-khong-mo-rong-pham-vi", {x["account_id"] for x in r.json()} == {ACC_A}, "", "critical")
    for sid, other in ((sa, ACC_B), (sb, ACC_A)):
        for _ in range(2):
            r = await web(f"/api/v1/equity-history?account_id={other}", sid)
            R.check("idor/cache/equity-history-tai-khoan-khac->403", r.status_code == 403, f"{r.status_code}", "critical")
    for sid in (sa, sb):
        for _ in range(2):
            r = await web("/api/v1/risk/accounts", sid)
            R.check("idor/cache/risk-accounts-loc", r.status_code == 200 and not any(x in r.text for x in (ACC_C, ACC_A if sid == sb else ACC_B)), f"{r.status_code}", "critical")

    # ------------------------------------------------------------ 3. client không lấy được route chỉ-master dù master vừa "làm nóng"
    for p in ("/api/v1/alerts?limit=3", "/api/v1/system", "/api/v1/data-sources", "/api/v1/reports"):
        mr = await web(p, msid)
        await web(p, msid)
        cr = await web(p, sa)
        R.check(f"phan-quyen/{p.split('?')[0]}-client-403-sau-khi-master-nong", cr.status_code == 403 and mr.status_code in (200, 404, 502, 503) and cr.headers.get("x-cache-status") in (None, "BYPASS"), f"{mr.status_code}/{cr.status_code}", "critical")
    me_a, me_b = (await web("/api/v1/me", sa)).json(), (await web("/api/v1/me", sb)).json()
    R.check("me/khong-cache-giua-nguoi-dung", me_a["accounts"] == [ACC_A] and me_b["accounts"] == [ACC_B], "", "critical")

    # ------------------------------------------------------------ 4. thu hồi phiên có hiệu lực nhanh dù có cache auth_request (<=2s) + cache dữ liệu không cứu phiên đã thu hồi
    for _ in range(3):
        assert (await web("/api/v1/symbols", sc)).status_code == 200
    r = await h.post(f"{AUTH}/auth/logout", json={}, headers={**ck(sc), "Origin": AUTH})
    t0 = time.monotonic()
    code = 200
    while time.monotonic() - t0 < 6:
        code = (await web("/api/v1/symbols", sc)).status_code
        if code == 401:
            break
        await asyncio.sleep(0.25)
    R.check("session/thu-hoi->401-trong-<=4s (auth_request cache 2s)", code == 401 and time.monotonic() - t0 <= 4.0, f"{code} sau {time.monotonic() - t0:.1f}s", "critical")
    R.check("session/sau-thu-hoi-khong-doc-duoc-bang-cache-du-lieu-chung", (await web(u, sc)).status_code == 401, "", "critical")

    # ------------------------------------------------------------ 5. stampede: N request đồng thời cùng khoá MỚI chỉ tạo ≤ vài MISS
    uq = f"/api/v1/calendar?limit=7&offset={secrets.randbelow(900) + 100}"
    res = await asyncio.gather(*[web(uq, sa, {"CF-Connecting-IP": f"10.96.{i // 250}.{i % 250 + 1}"}) for i in range(60)])
    stt = [x.headers.get("x-cache-status") for x in res]
    R.check("stampede/60-request-dong-thoi-<=2-MISS", all(x.status_code == 200 for x in res) and sum(1 for s in stt if s == "MISS") <= 2, f"{ {s: stt.count(s) for s in set(stt)} }", "high")
    R.check("stampede/noi-dung-dong-nhat", len({x.content for x in res}) == 1, "", "high")

    # ------------------------------------------------------------ 6. static / HTTP caching chuẩn
    idx = await web("/", msid, enc="gzip")
    R.check("static/index-no-cache", idx.status_code == 200 and "no-cache" in idx.headers.get("cache-control", ""), idx.headers.get("cache-control", ""), "high")
    mj = re.search(r"/assets/[^\"']+\.js", idx.text)
    if mj:
        a = await web(mj.group(0), msid, enc="gzip")
        R.check("static/assets-immutable-1nam", "immutable" in a.headers.get("cache-control", "") and "31536000" in a.headers.get("cache-control", ""), a.headers.get("cache-control", ""), "high")
        R.check("static/gzip-nen", a.headers.get("content-encoding") == "gzip", a.headers.get("content-encoding", "-"), "medium")
        cond = await h.get(WEB + mj.group(0), headers={**ck(msid), "If-None-Match": a.headers.get("etag", "x")})
        R.check("static/ETag-If-None-Match->304", cond.status_code == 304, f"{cond.status_code}", "medium")
    # ETag + 304 ở gateway (trực tiếp, nội bộ)
    gh = {"X-API-Key": API_KEY}
    g1 = await h.get(f"{GATEWAY}/v1/symbols", headers=gh)
    g2 = await h.get(f"{GATEWAY}/v1/symbols", headers={**gh, "If-None-Match": g1.headers.get("etag", "x")})
    R.check("gateway/ETag-304", g1.status_code == 200 and g1.headers.get("etag") and g2.status_code == 304, f"{g1.status_code}/{g2.status_code}", "medium")
    R.check("gateway/forged-header-khong-secret->403-khong-lay-tu-cache", (await h.get(f"{GATEWAY}/v1/accounts", headers={**gh, "X-Role": "master", "X-Accounts": "*"})).status_code == 403
            and (await h.get(f"{GATEWAY}/v1/news", headers={"X-Role": "master"})).status_code in (401, 403), "", "critical")

    # ------------------------------------------------------------ 7. metrics cache có số liệu (hit > 0)
    mt = (await h.get(f"{GATEWAY}/metrics")).text
    hits = sum(float(x.split()[-1]) for x in mt.splitlines() if x.startswith("gateway_cache_requests_total") and 'result="hit"' in x)
    R.check("metrics/gateway-cache-co-hit", hits > 0, f"hit={hits}", "medium")
    for acc in (ACC_A, ACC_B, ACC_C):
        await h.delete(f"{AUTH}/auth/admin/accounts/{acc}", headers=ck(msid))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
