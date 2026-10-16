"""E2E báo cáo THEO TÀI KHOẢN (docs/FLEET_MGMT.md §5) qua nginx web-ui (đường thật của trình duyệt): master sinh/phát hành, client A chỉ thấy bản đã phát hành của mình,
client B không đọc được của A (IDOR, 403 đồng nhất), client không ghi được, HTML/PDF không lộ tên nguồn. Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_account_reports.py
Dữ liệu thử: master `master:qa-<run>`, 2 tài khoản mt5:98xxxxxx + snapshot equity; báo cáo thử bị XOÁ (reporter DELETE /account-reports/{id}) và bảng lịch được khôi phục.
Không đụng tài khoản demo. Không in bí mật. Không có đường đặt lệnh."""
import io
import re
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi", "pypdf"], capture_output=True, check=False)

import os  # noqa: E402

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import Ctx, Results  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
REPORTER = os.getenv("QA_REPORTER", "http://reporter:8000")
IH = {"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "")}  # gọi THẲNG service nội bộ cần X-Internal-Token (HARDENING §7)
WEB_HOST = WEB.split("//", 1)[1]
RUN = secrets.token_hex(3)
LA, LB = 98000000 + int(RUN, 16) % 900000, 98900000 + int(RUN, 16) % 90000
A, B = f"mt5:{LA}", f"mt5:{LB}"
MPW, CPW = "QaMaster-" + secrets.token_urlsafe(12), "Moi-" + secrets.token_urlsafe(12)
R = Results("account_reports")
sid_of = lambda r: (re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", "")) or [None, ""])[1]  # noqa: E731
ck = lambda sid: {"Cookie": f"ts_session={sid}"}  # noqa: E731
BANNED = ("dukascopy", "yahoo", "frankfurter", "twelvedata", "cafef", "vietstock", "reuters", "forexfactory", "myfxbook", "mql5", "oanda", "ccxt")
_ip = iter(range(10, 250))
fake_ip = lambda: {"X-Real-IP": f"10.97.{int(RUN[:2], 16)}.{next(_ip)}"}  # noqa: E731


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=180, follow_redirects=False) as h:
        db = c.db
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)",
                         f"master:qa-{RUN}", PasswordHasher().hash(MPW))
        saved = None
        try:
            saved = await run(c, h, db)
        finally:
            for acc in (A, B):
                try:
                    await h.delete(f"{REPORTER}/account-reports/{acc}", headers=IH)
                except Exception:  # noqa: BLE001
                    pass
            if saved is not None:       # khôi phục bảng lịch trước khi thử
                try:
                    await h.put(f"{REPORTER}/account-report-schedules", json={"schedules": saved}, headers=IH)
                except Exception:  # noqa: BLE001
                    pass
            await db.execute("delete from account_snapshots where account_id = any($1)", [A, B])
            await db.execute("delete from portal_users where login_key = any($1)", [f"master:qa-{RUN}", A, B])
            await db.execute("delete from mt_accounts where account_id = any($1)", [A, B])
    return R.finish()


async def run(c, h, db):
    saved = (await h.get(f"{REPORTER}/account-report-schedules", headers=IH)).json().get("schedules", [])
    r = await h.post(f"{AUTH}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": MPW}, headers=fake_ip())
    msid = sid_of(r)
    R.check("master/login", r.status_code == 200 and msid, f"{r.status_code}", "critical")
    sec = {}
    for acc, lg in ((A, LA), (B, LB)):
        r = await h.post(f"{AUTH}/auth/admin/accounts", json={"platform": "mt5", "login": lg, "server": "QA-Server", "label": f"qa-{RUN}"}, headers=ck(msid))
        R.check(f"setup/tao-{acc}", r.status_code == 201, f"{r.status_code}", "critical")
        sec[acc] = r.json().get("secrets", {})
        await h.post(f"{AUTH}/auth/admin/accounts/{acc}/activate", json={}, headers=ck(msid))

    async def client_sid(acc, lg):
        r = await h.post(f"{AUTH}/auth/login", json={"platform": "mt5", "login": str(lg), "secret": sec[acc]["passcode"]}, headers=fake_ip())
        s0 = sid_of(r)
        r = await h.post(f"{AUTH}/auth/change-password", json={"current_password": sec[acc]["passcode"], "new_password": CPW}, headers=ck(s0))
        R.check(f"client/{acc}/doi-mat-khau", r.status_code == 200, f"{r.status_code}", "critical")
        r = await h.post(f"{AUTH}/auth/login", json={"platform": "mt5", "login": str(lg), "secret": CPW}, headers=fake_ip())
        return sid_of(r)
    sa, sb = await client_sid(A, LA), await client_sid(B, LB)

    # dữ liệu equity của A trong kỳ "hôm qua" (giờ VN); B không có dữ liệu
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    day = (datetime.now(tz) - timedelta(days=1)).date()
    base = datetime(day.year, day.month, day.day, 9, 0, tzinfo=tz).astimezone(timezone.utc)
    for i, eq in enumerate((1000.0, 1012.5, 1007.0, 1030.0)):
        await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) values ($1,'mt5',$2,1000,$3,10,'[]'::jsonb)",
                         A, base + timedelta(hours=i), eq)
    period = day.isoformat()

    def web(sid, method, path, body=None, csrf=None, **kw):
        hd = {**ck(sid), **fake_ip(), **kw.pop("extra", {})}
        if method != "GET":
            hd.update({"Origin": f"http://{WEB_HOST}", "X-CSRF-Token": csrf or ""})
        return h.request(method, WEB + path, json=body, headers=hd, **kw)

    async def csrf(sid):
        return (await web(sid, "GET", "/api/v1/user/csrf")).json().get("token")

    mt = await csrf(msid)
    # ---------------------------------------------------------------- 1. master sinh báo cáo (mặc định CHƯA phát hành)
    r = await web(msid, "POST", "/api/v1/account-reports/generate", {"account_id": A, "kind": "daily", "period": period}, mt)
    e = r.json() if r.status_code == 200 else {}
    R.check("master/generate", r.status_code == 200 and e.get("released") is False and e.get("period") == period and e.get("status") in ("ok", "degraded"), f"{r.status_code} {r.text[:150]}", "critical")
    R.check("master/generate-co-pdf", e.get("has_pdf") is True, str(e.get("sections_fail")), "high")
    R.check("master/generate-khong-du-lieu->409", (await web(msid, "POST", "/api/v1/account-reports/generate", {"account_id": B, "kind": "daily", "period": period}, mt)).status_code == 409, "", "high")
    R.check("master/generate-id-xau->422", (await web(msid, "POST", "/api/v1/account-reports/generate", {"account_id": "../x", "kind": "daily"}, mt)).status_code == 422, "", "critical")
    R.check("master/generate-thieu-csrf->403", (await web(msid, "POST", "/api/v1/account-reports/generate", {"account_id": A, "kind": "daily"}, "")).status_code == 403, "", "critical")
    r = await web(msid, "GET", f"/api/v1/account-reports?account_id={A}")
    R.check("master/list-thay-ban-chua-phat-hanh", r.status_code == 200 and [(i["kind"], i["released"]) for i in r.json()["items"]] == [("daily", False)], f"{r.status_code} {r.text[:120]}", "critical")

    # ---------------------------------------------------------------- 2. client chỉ thấy bản đã phát hành của mình
    r = await web(sa, "GET", f"/api/v1/account-reports?account_id={A}")
    R.check("client-A/list-chua-phat-hanh-rong", r.status_code == 200 and r.json()["items"] == [], f"{r.status_code} {r.text[:100]}", "critical")
    R.check("client-A/file-chua-phat-hanh->404", (await web(sa, "GET", f"/api/v1/account-reports/{A}/{period}/html")).status_code == 404, "", "critical")
    R.check("client-A/pdf-chua-phat-hanh->404", (await web(sa, "GET", f"/api/v1/account-reports/{A}/{period}/pdf")).status_code == 404, "", "critical")
    r = await web(msid, "POST", "/api/v1/account-reports/release", {"account_id": A, "kind": "daily", "period": period, "released": True}, mt)
    R.check("master/release", r.status_code == 200 and r.json().get("released") is True, f"{r.status_code} {r.text[:100]}", "critical")
    r = await web(sa, "GET", f"/api/v1/account-reports?account_id={A}")
    R.check("client-A/list-thay-ban-da-phat-hanh", r.status_code == 200 and [i["period"] for i in r.json()["items"]] == [period], f"{r.status_code}", "critical")
    r = await web(sa, "GET", f"/api/v1/account-reports/{A}/{period}/html")
    html = r.text
    csp = r.headers.get("content-security-policy", "")
    R.check("client-A/html-200+CSP+nosniff", r.status_code == 200 and "default-src 'none'" in csp and r.headers.get("x-content-type-options") == "nosniff"
            and "text/html" in r.headers.get("content-type", "") and r.headers.get("cache-control") == "no-store" and A in html, f"{r.status_code} csp={csp[:60]}", "critical")
    R.check("client-A/CSP-mot-ban-duy-nhat", len([k for k, _ in r.headers.multi_items() if k.lower() == "content-security-policy"]) == 1, "", "medium")
    text = re.sub(r"<[^>]+>", " ", html.lower())
    R.check("client-A/html-khong-lo-ten-nguon", not any(w in html.lower() or w in text for w in BANNED), "", "critical")
    R.check("client-A/html-khong-co-script", "<script" not in html.lower(), "", "critical")
    r = await web(sa, "GET", f"/api/v1/account-reports/{A}/{period}/pdf?kind=daily")
    pdf_ok = r.status_code == 200 and r.content[:4] == b"%PDF" and "attachment" in r.headers.get("content-disposition", "")
    R.check("client-A/pdf-200", pdf_ok, f"{r.status_code}", "high")
    if pdf_ok:
        import pypdf
        t = "".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages).lower()
        R.check("client-A/pdf-khong-lo-ten-nguon", bool(t) and not any(w in t for w in BANNED), "", "critical")

    # ---------------------------------------------------------------- 3. IDOR + quyền ghi
    for name, sid, path in (("B-doc-list-A", sb, f"/api/v1/account-reports?account_id={A}"), ("B-doc-html-A", sb, f"/api/v1/account-reports/{A}/{period}/html"),
                            ("B-doc-pdf-A", sb, f"/api/v1/account-reports/{A}/{period}/pdf"), ("A-doc-list-B", sa, f"/api/v1/account-reports?account_id={B}"),
                            ("A-hai-account_id", sa, f"/api/v1/account-reports?account_id={A}&account_id={B}"), ("A-ma-hoa-traversal", sa, f"/api/v1/account-reports/{A}%2F..%2F{B}/{period}/html"),
                            ("A-chu-hoa", sa, f"/api/v1/account-reports?account_id={A.upper()}"), ("A-khong-account_id", sa, "/api/v1/account-reports"),
                            ("A-khong-ton-tai", sa, f"/api/v1/account-reports/mt5:1/{period}/html")):
        r = await web(sid, "GET", path)
        R.check(f"idor/{name}", r.status_code in (403, 404) and "equity" not in r.text.lower(), f"{r.status_code}", "critical")
    r1 = await web(sb, "GET", f"/api/v1/account-reports/{A}/{period}/html")
    r2 = await web(sb, "GET", f"/api/v1/account-reports/mt5:1/{period}/html")
    R.check("idor/403-dong-nhat-khong-oracle", r1.status_code == r2.status_code == 403 and r1.text == r2.text, f"{r1.status_code}/{r2.status_code}", "critical")
    ca_ = await csrf(sa)
    for name, method, path, body in (("generate", "POST", "/api/v1/account-reports/generate", {"account_id": A, "kind": "daily"}),
                                     ("release", "POST", "/api/v1/account-reports/release", {"account_id": A, "kind": "daily", "period": period, "released": True}),
                                     ("schedules-put", "PUT", "/api/v1/account-report-schedules", {"schedules": []}),
                                     ("xoa", "DELETE", f"/api/v1/account-reports/{A}/{period}/html", None)):
        r = await web(sa, method, path, body, ca_)
        R.check(f"client-A/khong-ghi-duoc/{name}", r.status_code in (403, 404, 405), f"{r.status_code}", "critical")
    R.check("client-A/khong-doc-lich", (await web(sa, "GET", "/api/v1/account-report-schedules")).status_code == 403, "", "critical")
    R.check("khong-dang-nhap->401", (await h.get(WEB + f"/api/v1/account-reports?account_id={A}")).status_code == 401, "", "critical")
    r = await web(msid, "POST", "/api/v1/account-reports/release", {"account_id": A, "kind": "daily", "period": period, "released": False}, mt)
    R.check("master/thu-hoi", r.status_code == 200 and r.json().get("released") is False, f"{r.status_code}", "critical")
    R.check("client-A/sau-thu-hoi-khong-thay", (await web(sa, "GET", f"/api/v1/account-reports/{A}/{period}/html")).status_code == 404, "", "critical")

    # ---------------------------------------------------------------- 4. lịch (master)
    r = await web(msid, "PUT", "/api/v1/account-report-schedules", {"schedules": [{"scope": {"type": "account", "ref": A}, "kind": "weekly", "hour": 7, "enabled": False, "auto_release": False}]}, mt)
    R.check("lich/master-ghi", r.status_code == 200 and r.json()["schedules"][0]["scope"] == {"type": "account", "ref": A}, f"{r.status_code} {r.text[:100]}", "high")
    r = await web(msid, "GET", "/api/v1/account-report-schedules")
    R.check("lich/master-doc", r.status_code == 200 and len(r.json()["schedules"]) == 1, "", "high")
    r = await web(msid, "PUT", "/api/v1/account-report-schedules", {"schedules": [{"scope": {"type": "group", "ref": "<x>"}, "kind": "daily", "hour": 99}]}, mt)
    R.check("lich/du-lieu-xau->422", r.status_code == 422, f"{r.status_code}", "high")
    return saved


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
