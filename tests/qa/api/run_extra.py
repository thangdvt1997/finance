"""T1b - phan bo sung cho run_api.py: luong GHI hop le bang phien tai khoan thu (co don), /auth/* hop le, SSE/WS nhan su kien,
IDOR route proxy {rest}. Ket qua -> tests/qa/api_extra.json (list {id, group, ok, detail}). Chay: nice -n 15 python3 tests/qa/api/run_extra.py
Tai khoan thu: qa_stab_api_* + mt5:97xxxxxx (id ngau nhien), xoa o cuoi. Khong dat lenh, khong in secret. Khong goi killswitch/jobs/generate."""
import hashlib, hmac, base64, json, os, struct, sys, time, secrets
sys.argv = [sys.argv[0]]  # run_api doc sys.argv luc import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
import run_api as R

OUT = os.path.join(R.Q, "api_extra.json")
RES = []


def ck(group, name, ok, detail=""):
    RES.append({"id": f"{group}:{name}", "group": group, "ok": bool(ok), "detail": str(detail)[:200]})
    print(("PASS " if ok else "FAIL "), group, name, str(detail)[:100], flush=True)
    return ok


def js(r):
    try:
        return r.json()
    except Exception:
        return None


def req(u, m, p, body=None, q=None, **kw):
    try:
        return R.public_req(u, m, p, q=q, body=body, **kw)
    except Exception as ex:
        class F:
            status_code = 599
            text = repr(ex)
            headers = {}
        return F()


def totp(secret_b32, t=None):
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    c = int((t or time.time()) // 30)
    h = hmac.new(key, struct.pack(">Q", c), hashlib.sha1).digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o+4])[0] & 0x7fffffff) % 10**6:06d}"


def fresh_client(acc):
    R.sh(f"docker exec -i tradingsys-auth python - delete {acc} < {R.ROOT}/services/client-ui/qa/auth_testacct.py")
    r = R.sh(f"docker exec -i tradingsys-auth python - create {acc} < {R.ROOT}/services/client-ui/qa/auth_testacct.py")
    d = json.loads(r.stdout.strip().splitlines()[-1])
    R.SECRETS_MEM.append(d["passcode"])
    return d


def login_new(plat, login, secret, extra=None):
    u = R.User(login, "x")
    u.s.headers["Origin"] = R.BASE
    body = {"platform": plat, "login": login, "secret": secret}
    body.update(extra or {})
    r = u.s.post(R.BASE + "/auth/login", json=body, timeout=20)
    if r.status_code == 200:
        sid = next((c.value for c in u.s.cookies if c.name == "ts_session"), None)
        if sid:
            u.s.cookies.clear()
            u.s.cookies.set("ts_session", sid, domain="127.0.0.1", path="/")
        u.cred = (plat, login, secret)
        u.csrf = u.tok()
    return u, r



CB = "http://127.0.0.1:8581"


def creq(u, m, p, body=None, q=None, **kw):
    """goi ung dung CLIENT (8581, /c/...) bang phien client"""
    old = R.BASE
    R.BASE = CB
    u.s.headers["Origin"] = CB
    try:
        if m != "GET" and not u.csrf:
            u.csrf = ctok(u)
        return req(u, m, p, body, q, **kw)
    finally:
        R.BASE = old


def ctok(u):
    try:
        return u.s.get(CB + "/c/api/v1/user/csrf", timeout=15, headers={"Origin": CB}).json().get("token")
    except Exception:
        return None


def clogin(plat, login, secret, extra=None):
    u = R.User(login, "client")
    u.s.headers["Origin"] = CB
    body = {"platform": plat, "login": login, "secret": secret}
    body.update(extra or {})
    r = u.s.post(CB + "/c/auth/login", json=body, timeout=20)
    if r.status_code == 200:
        sid = next((c.value for c in u.s.cookies if c.name == "ts_session"), None)
        if sid:
            u.s.cookies.clear()
            u.s.cookies.set("ts_session", sid, domain="127.0.0.1", path="/")
        u.cred = (plat, login, secret)
        u.csrf = ctok(u)
    return u, r


def prep_clients(users):
    """phien client that (8581): dang nhap + doi mat khau lan dau (co co must_change)"""
    out = {}
    for tag, acc in (("clientA", R.ACC_A), ("clientB", R.ACC_B)):
        pw0 = users[tag].cred[2]
        u, r = clogin("mt5", acc, pw0)
        if r.status_code != 200:
            ck("client-setup", f"login-{tag}", False, r.status_code)
            continue
        new = "Qa!" + secrets.token_urlsafe(14)
        R.SECRETS_MEM.append(new)
        rr = creq(u, "POST", "/c/auth/change-password", {"current_password": pw0, "new_password": new})
        ck("client-setup", f"change-password-lan-dau-{tag}", rr.status_code == 200, rr.status_code)
        time.sleep(2)
        u2, r2 = clogin("mt5", acc, new)
        ck("client-setup", f"login-sau-doi-mat-khau-{tag}", r2.status_code == 200, r2.status_code)
        out[tag] = u2 if r2.status_code == 200 else u
    return out


def prep_master(users):
    """bat TOTP cho master thu de qua cong 'can 2FA' cua thao tac quan tri (khong dung master that)"""
    m = users["master"]
    pw = m.cred[2]
    r = req(m, "POST", "/auth/totp/setup")
    j = js(r) or {}
    sec = j.get("secret") or ""
    if not sec and j.get("otpauth_uri"):
        import re as _re
        mm = _re.search(r"secret=([A-Z2-7]+)", j["otpauth_uri"]); sec = mm.group(1) if mm else ""
    if not sec:
        ck("master-setup", "totp-setup", False, f"{r.status_code} {str(j)[:60]}")
        return None
    R.SECRETS_MEM.append(sec)
    r = req(m, "POST", "/auth/totp/enable", {"code": totp(sec)})
    ck("master-setup", "totp-enable", r.status_code == 200, r.status_code)
    time.sleep(31)    # ma moi (tranh replay)
    u, r2 = login_new("master", m.name, pw, {"totp": totp(sec)})
    ck("master-setup", "login-totp", r2.status_code == 200, r2.status_code)
    if r2.status_code == 200:
        u.cred = None
        u.name = m.name
        u.totp_secret, u.pw = sec, pw
        return u
    return None


# ------------------------------------------------------------------ auth
def t_auth(users, accC):
    g = "auth-flow"
    a = users["clientA"]
    b = users["clientB"]
    r = creq(a, "GET", "/c/auth/me")
    j = js(r) or {}
    ck(g, "me", r.status_code == 200 and "passcode" not in r.text, r.status_code)
    # phien thu hai + liet ke + thu hoi
    u2, r2 = clogin("mt5", R.ACC_A, a.cred[2]); time.sleep(2)
    ck(g, "login-hop-le-phien-2", r2.status_code == 200, r2.status_code)
    r = creq(a, "GET", "/c/auth/sessions")
    sj = js(r)
    ck(g, "sessions-list", r.status_code == 200 and sj is not None, r.status_code)
    sess = (sj.get("items") or sj.get("sessions") if isinstance(sj, dict) else sj) or []
    other = [s for s in sess if not s.get("current")]
    if other:
        sid = other[0].get("sid") or other[0].get("session_id") or other[0].get("id")
        r = creq(a, "POST", f"/c/auth/sessions/{sid}/revoke")
        ck(g, "sessions-revoke", r.status_code == 200, r.status_code)
        r = creq(u2, "GET", "/c/auth/me")
        ck(g, "phien-bi-thu-hoi-het-hieu-luc", r.status_code == 401, r.status_code)
    else:
        ck(g, "sessions-revoke", False, f"khong thay phien khac: {str(sj)[:80]}")
    # IDOR phien: B khong thu hoi duoc phien cua A
    sid_a = (sess[0].get("sid") or sess[0].get("id")) if sess else "x0"
    r = creq(b, "POST", f"/c/auth/sessions/{sid_a}/revoke")
    ck(g, "idor-revoke-phien-nguoi-khac", r.status_code in (403, 404) or (r.status_code == 200 and False), r.status_code)
    r = creq(a, "GET", "/c/auth/me")
    ck(g, "phien-A-con-sau-idor", r.status_code == 200, r.status_code)
    # logout hop le -> me 401 -> login lai
    u3, r3 = clogin("mt5", R.ACC_A, a.cred[2]); time.sleep(2)
    r = creq(u3, "POST", "/c/auth/logout")
    ck(g, "logout", r.status_code in (200, 204), r.status_code)
    r = creq(u3, "GET", "/c/auth/me")
    ck(g, "sau-logout-me-401", r.status_code == 401, r.status_code)
    # logout-all: dung phien rieng
    u4, _ = clogin("mt5", R.ACC_A, a.cred[2]); time.sleep(2)
    u5, _ = clogin("mt5", R.ACC_A, a.cred[2]); time.sleep(2)
    r = creq(u4, "POST", "/c/auth/logout-all")
    ck(g, "logout-all", r.status_code in (200, 204), r.status_code)
    r = creq(u5, "GET", "/c/auth/me")
    ck(g, "logout-all-het-hieu-luc-phien-khac", r.status_code == 401, r.status_code)
    # khoi phuc phien A cho cac test sau
    time.sleep(5)
    a.s.cookies.clear()
    ua, _ = clogin(*a.cred)
    a.s, a.csrf = ua.s, ua.csrf
    # login sai
    r = requests.post(R.BASE + "/c/auth/login", json={"platform": "mt5", "login": R.ACC_A, "secret": "sai-" + secrets.token_hex(4)}, timeout=20, headers={"Origin": R.BASE})
    ck(g, "login-sai-401", r.status_code in (401, 403, 429), r.status_code)
    # pair: ma ghep hop le -> dat mat khau -> dang nhap bang mat khau moi
    code = None
    try:
        code = json.loads(R.sh(f"docker exec -i tradingsys-auth python - pairing {accC['account_id'].split(':')[1]} < {R.ROOT}/services/client-ui/qa/auth_testacct.py").stdout.strip().splitlines()[-1]).get("pairing_code")
    except Exception:
        code = accC.get("pairing_code")
    if code:
        R.SECRETS_MEM.append(code)
        newpw = "Qa!" + secrets.token_urlsafe(14)
        R.SECRETS_MEM.append(newpw)
        r = requests.post(R.BASE + "/c/auth/pair", json={"platform": "mt5", "login": accC["account_id"].split(":")[1], "pairing_code": code, "new_password": newpw}, timeout=20, headers={"Origin": R.BASE})
        ck(g, "pair-hop-le", r.status_code == 200, r.status_code)
        r2 = requests.post(R.BASE + "/c/auth/pair", json={"platform": "mt5", "login": accC["account_id"].split(":")[1], "pairing_code": code, "new_password": newpw}, timeout=20, headers={"Origin": R.BASE})
        ck(g, "pair-dung-lai-ma-bi-tu-choi", r2.status_code in (400, 401, 403, 404, 409, 410, 422), r2.status_code)
        time.sleep(15)
        uc, rc = clogin("mt5", accC["account_id"].split(":")[1], newpw)
        ck(g, "login-bang-mat-khau-moi-sau-pair", rc.status_code == 200, rc.status_code)
        if rc.status_code == 200:
            # change-password hop le + mat khau cu bi tu choi + sai current
            new2 = "Qa!" + secrets.token_urlsafe(14); R.SECRETS_MEM.append(new2)
            r = creq(uc, "POST", "/c/auth/change-password", {"current_password": "sai-" + secrets.token_hex(4), "new_password": new2})
            ck(g, "change-password-current-sai", r.status_code in (400, 401, 403), r.status_code)
            r = creq(uc, "POST", "/c/auth/change-password", {"current_password": newpw, "new_password": new2})
            ck(g, "change-password-hop-le", r.status_code == 200, r.status_code)
            time.sleep(2)
            _, ro = clogin("mt5", accC["account_id"].split(":")[1], newpw)
            ck(g, "mat-khau-cu-het-hieu-luc", ro.status_code in (401, 403, 429), ro.status_code)
            _, rn = clogin("mt5", accC["account_id"].split(":")[1], new2)
            ck(g, "mat-khau-moi-dang-nhap-duoc", rn.status_code == 200, rn.status_code)
    else:
        ck(g, "pair-hop-le", False, "khong lay duoc ma ghep")


def t_totp(users):
    g = "auth-totp"
    ex = users["expert"]
    pw = ex.cred[2]
    r = req(ex, "POST", "/auth/totp/setup")
    j = js(r) or {}
    sec = j.get("secret") or j.get("totp_secret") or ""
    if not sec and j.get("otpauth_uri"):
        import re as _re
        m = _re.search(r"secret=([A-Z2-7]+)", j["otpauth_uri"])
        sec = m.group(1) if m else ""
    ck(g, "setup", r.status_code == 200 and bool(sec), r.status_code)
    if not sec:
        return
    R.SECRETS_MEM.append(sec)
    r = req(ex, "POST", "/auth/totp/enable", {"code": "000000"})
    ck(g, "enable-ma-sai", r.status_code in (400, 401, 403, 422), r.status_code)
    r = req(ex, "POST", "/auth/totp/enable", {"code": totp(sec)})
    ck(g, "enable-hop-le", r.status_code == 200, r.status_code)
    time.sleep(31)
    _, r1 = login_new("master", ex.name, pw)
    ck(g, "login-thieu-totp-bi-tu-choi", r1.status_code in (401, 403) or "totp" in r1.text.lower() and r1.status_code != 200, r1.status_code)
    time.sleep(1)
    u, r2 = login_new("master", ex.name, pw, {"totp": totp(sec)})
    ck(g, "login-co-totp-hop-le", r2.status_code == 200, r2.status_code)
    # tat: phai dung ma moi (khac cua so truoc de tranh replay) -> thu code hien tai
    tgt = u if r2.status_code == 200 else ex
    r = req(tgt, "POST", "/auth/totp/disable", {"password": "sai-" + secrets.token_hex(3), "code": totp(sec)})
    ck(g, "disable-mat-khau-sai", r.status_code in (400, 401, 403), r.status_code)
    for att in range(3):
        r = req(tgt, "POST", "/auth/totp/disable", {"password": pw, "code": totp(sec, time.time() + 30 * att)})
        if r.status_code == 200:
            break
        if att == 0:
            time.sleep(31)
    ck(g, "disable-hop-le", r.status_code == 200, r.status_code)


# ------------------------------------------------------------------ ghi hop le + IDOR
def t_user_writes(users):
    g = "user-writes"
    a, b = users["clientA"], users["clientB"]
    rule = {"name": "qa-rule", "enabled": False, "logic": "and", "mode": "once", "cooldown_min": 5, "level": "info", "channels": ["app"],
            "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 99999}]}
    r = creq(a, "POST", "/c/api/v1/user/rules/preview", rule)
    ck(g, "rules-preview", r.status_code in (200, 422), f"{r.status_code} {r.text[:80]}")
    r = creq(a, "POST", "/c/api/v1/user/rules", rule)
    j = js(r) or {}
    rid = j.get("id") or j.get("rule_id") or (j.get("rule") or {}).get("id")
    ck(g, "rules-create", r.status_code in (200, 201) and rid, f"{r.status_code} {r.text[:120]}")
    if rid:
        r = creq(a, "GET", "/c/api/v1/user/rules")
        ck(g, "rules-list-co-rule", r.status_code == 200 and str(rid) in r.text, r.status_code)
        r = creq(b, "GET", "/c/api/v1/user/rules")
        ck(g, "rules-IDOR-B-khong-thay-rule-A", r.status_code == 200 and str(rid) not in r.text, r.status_code)
        r = creq(b, "PUT", f"/c/api/v1/user/rules/{rid}", dict(rule, name="hack"))
        ck(g, "rules-IDOR-B-sua-rule-A", r.status_code in (403, 404), r.status_code)
        r = creq(b, "DELETE", f"/c/api/v1/user/rules/{rid}")
        ck(g, "rules-IDOR-B-xoa-rule-A", r.status_code in (403, 404), r.status_code)
        r = creq(a, "PUT", f"/c/api/v1/user/rules/{rid}", dict(rule, name="qa-rule-2"))
        ck(g, "rules-update", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
        r = creq(a, "POST", f"/c/api/v1/user/rules/{rid}/preview")
        ck(g, "rules-preview-id", r.status_code in (200, 422), r.status_code)
        r = creq(a, "DELETE", f"/c/api/v1/user/rules/{rid}")
        ck(g, "rules-delete", r.status_code in (200, 204), r.status_code)
        r = creq(a, "GET", "/c/api/v1/user/rules")
        ck(g, "rules-het-sau-xoa", str(rid) not in r.text, r.status_code)
    # prefs (rev optimistic) - route cua master (client khong co: phai 404/405)
    m = users["master"]
    r = req(m, "GET", "/api/v1/user/prefs"); j = js(r) or {}
    rev = j.get("rev", 0)
    r = req(m, "PUT", "/api/v1/user/prefs", {"rev": rev, "prefs": j.get("prefs") or {}})
    ck(g, "prefs-put-hop-le-master", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    r = req(m, "PUT", "/api/v1/user/prefs", {"rev": rev, "prefs": j.get("prefs") or {}})
    ck(g, "prefs-put-rev-cu-409-hoac-ok", r.status_code in (409, 200), f"{r.status_code}")
    r = creq(a, "PUT", "/c/api/v1/user/prefs", {"rev": 0, "prefs": {}})
    ck(g, "prefs-client-khong-duoc-ghi", r.status_code in (403, 404, 405), r.status_code)
    r = creq(a, "GET", "/c/api/v1/user/client-prefs"); j = js(r) or {}
    r = creq(a, "PUT", "/c/api/v1/user/client-prefs", {"rev": j.get("rev", 0), "data": j.get("data") or {}})
    ck(g, "client-prefs-put", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    # notifications read
    r = creq(a, "POST", "/c/api/v1/user/notifications/read", {"all": True})
    ck(g, "notifications-read", r.status_code in (200, 204), r.status_code)
    # tickets: tao + B khong thay + dong
    r = creq(a, "POST", "/c/api/v1/user/tickets", {"account_id": f"mt5:{R.ACC_A}", "category": "other", "message": "qa-ticket-xoa-di"})
    j = js(r) or {}
    tid = j.get("id") or j.get("ticket_id") or (j.get("ticket") or {}).get("id")
    ck(g, "tickets-create", r.status_code in (200, 201) and tid, f"{r.status_code} {r.text[:100]}")
    r = creq(a, "POST", "/c/api/v1/user/tickets", {"account_id": f"mt5:{R.ACC_B}", "category": "other", "message": "idor"})
    ck(g, "tickets-IDOR-tao-cho-tai-khoan-B", r.status_code in (400, 403, 404, 422), r.status_code)
    if tid:
        r = creq(b, "GET", "/c/api/v1/user/tickets")
        ck(g, "tickets-IDOR-B-khong-thay", r.status_code in (200, 403) and "qa-ticket-xoa-di" not in r.text, r.status_code)
        r = creq(b, "PUT", f"/c/api/v1/user/tickets/{tid}", {"status": "closed"})
        ck(g, "tickets-IDOR-B-dong-ticket-A", r.status_code in (403, 404), r.status_code)
    # push: endpoint gia (khong that) -> subscribe/unsubscribe
    ep = "https://qa.invalid/push/" + secrets.token_hex(6)
    r = creq(a, "POST", "/c/api/v1/user/push/subscribe", {"endpoint": ep, "keys": {"p256dh": "BQA" + "A" * 80, "auth": "A" * 22}, "user_agent": "qa"})
    ck(g, "push-subscribe", r.status_code in (200, 201, 400, 422), f"{r.status_code} (SSRF/endpoint gia khong duoc 500) {r.text[:60]}")
    r = creq(a, "POST", "/c/api/v1/user/push/unsubscribe", {"endpoint": ep})
    ck(g, "push-unsubscribe", r.status_code in (200, 204, 404), r.status_code)
    # limits: dat roi tra lai; B khong sua duoc cua A
    r = creq(a, "GET", "/c/api/v1/user/limits", q={"account_id": f"mt5:{R.ACC_A}"})
    ck(g, "limits-get", r.status_code == 200, r.status_code)
    r = creq(b, "PUT", "/c/api/v1/user/limits", {"account_id": f"mt5:{R.ACC_A}", "key": "max_dd_pct", "value": 1})
    ck(g, "limits-IDOR-B-sua-A", r.status_code in (403, 404), r.status_code)
    r = creq(a, "PUT", "/c/api/v1/user/limits", {"account_id": f"mt5:{R.ACC_A}", "key": "max_dd_pct", "value": 25})
    ck(g, "limits-put-hop-le", r.status_code in (200, 400, 422), f"{r.status_code} {r.text[:80]}")
    # journal note
    base = f"/c/api/v1/journal/{R.ACC_A}"
    base = f"/c/api/v1/journal/mt5:{R.ACC_A}"
    r = creq(a, "PUT", f"{base}/notes/deal/qa0", {"tags": ["qa"], "note": "ghi chu thu", "rating": 3})
    ck(g, "journal-note-put-tai-khoan-chua-co-nhat-ky-404-JSON", r.status_code in (200, 201) or (r.status_code == 404 and "application/json" in r.headers.get("content-type", "")), f"{r.status_code} {r.text[:60]}")
    r = creq(b, "PUT", f"{base}/notes/deal/qa0", {"tags": ["x"], "note": "idor", "rating": 1})
    ck(g, "journal-note-IDOR-B-ghi-vao-A", r.status_code in (403, 404), r.status_code)
    r = creq(b, "DELETE", f"{base}/notes/deal/qa0")
    ck(g, "journal-note-IDOR-B-xoa", r.status_code in (403, 404), r.status_code)
    r = creq(a, "DELETE", f"{base}/notes/deal/qa0")
    ck(g, "journal-note-delete", r.status_code in (200, 204, 404) and "<html" not in r.text, f"{r.status_code} {r.text[:60]}")
    # client notify
    r = creq(a, "PUT", "/c/auth/client/notify", {"enabled": True})
    ck(g, "client-notify-put", r.status_code in (200, 204), r.status_code)
    # report: client tu sinh bao cao (nhe) -- chi thu sinh cho tai khoan cua minh
    r = creq(a, "POST", "/c/api/v1/account-reports/generate", {"account_id": f"mt5:{R.ACC_A}"}, timeout=60)
    ck(g, "account-report-generate-cua-minh", r.status_code in (200, 202, 400, 403, 404, 422), f"{r.status_code} {r.text[:80]}")
    r = creq(a, "POST", "/c/api/v1/account-reports/generate", {"account_id": f"mt5:{R.ACC_B}"}, timeout=60)
    ck(g, "account-report-IDOR-sinh-cho-B", r.status_code in (400, 403, 404, 422), r.status_code)


def t_admin_writes(users, accC):
    g = "admin-writes"
    m = users["master"]
    ex = users["expert"]
    acc = accC["account_id"]
    # nhom
    r = req(m, "POST", "/auth/admin/groups", {"name": "qa-grp-" + R.RUN, "description": "qa", "color": "#123456"})
    j = js(r) or {}
    gid = j.get("gid") or j.get("id") or (j.get("group") or {}).get("gid") or (j.get("group") or {}).get("id")
    ck(g, "groups-create", r.status_code in (200, 201) and gid, f"{r.status_code} {r.text[:80]}")
    if gid:
        r = req(m, "PATCH", f"/auth/admin/groups/{gid}", {"description": "qa2"})
        ck(g, "groups-patch", r.status_code == 200, r.status_code)
        r = req(m, "POST", f"/auth/admin/groups/{gid}/members", {"account_ids": [acc]})
        ck(g, "groups-add-member", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
        r = req(m, "PUT", f"/auth/admin/groups/{gid}/policy", {"min_severity": "warning"})
        ck(g, "groups-policy", r.status_code in (200, 422), f"{r.status_code} {r.text[:80]}")
        r = req(ex, "DELETE", f"/auth/admin/groups/{gid}")
        ck(g, "groups-expert-xoa-nhom-bi-tu-choi-hoac-ok", r.status_code in (200, 204, 403), f"{r.status_code}")
        r = req(m, "DELETE", f"/auth/admin/groups/{gid}/members/{acc}")
        ck(g, "groups-del-member", r.status_code in (200, 204, 404), r.status_code)
        r = req(m, "GET", "/auth/admin/groups")
        if gid and str(gid) in r.text:
            r = req(m, "DELETE", f"/auth/admin/groups/{gid}")
            ck(g, "groups-delete", r.status_code in (200, 204), r.status_code)
        else:
            ck(g, "groups-delete", True, "da xoa o buoc truoc")
    r = req(m, "PUT", f"/auth/admin/accounts/{acc}/tags", {"tags": ["qa"]})
    ck(g, "account-tags", r.status_code in (200, 204), f"{r.status_code} {r.text[:80]}")
    r = req(m, "POST", f"/auth/admin/accounts/{acc}/notes", {"text": "qa note"})
    ck(g, "account-notes", r.status_code in (200, 201), f"{r.status_code} {r.text[:80]}")
    r = req(m, "PATCH", f"/auth/admin/accounts/{acc}", {"label": "qa-label", "notes": "qa"})
    ck(g, "account-patch-khong-phoi-qua-nginx-405", r.status_code == 405, f"{r.status_code} (whitelist nginx web-ui khong cho PATCH accounts: dung thiet ke)")
    for act in ("suspend", "activate", "reset-passcode", "rotate-ea-token", "rotate-hmac", "pairing-code"):
        r = req(m, "POST", f"/auth/admin/accounts/{acc}/{act}")
        okc = r.status_code == 200
        body = r.text
        ck(g, f"account-{act}", okc, f"{r.status_code}")
        for v in (js(r) or {}).get("secrets", {}).values() if isinstance((js(r) or {}).get("secrets"), dict) else []:
            if isinstance(v, str):
                R.SECRETS_MEM.append(v)
    # vai: expert thuc hien hanh dong tren tai khoan (co the 200 hoac 403 tuy ma tran quyen) -> khong 5xx
    r = req(ex, "POST", f"/auth/admin/accounts/{acc}/suspend")
    ck(g, "account-suspend-bang-expert-khong-5xx", r.status_code < 500, r.status_code)
    req(m, "POST", f"/auth/admin/accounts/{acc}/activate")
    # views
    r = req(m, "POST", "/auth/admin/views", {"name": "qa-view-" + R.RUN, "filters": {}, "shared": False})
    j = js(r) or {}
    vid = j.get("vid") or j.get("id") or (j.get("view") or {}).get("id")
    ck(g, "views-create", r.status_code in (200, 201) and vid, f"{r.status_code} {r.text[:80]}")
    if vid:
        r = req(m, "DELETE", f"/auth/admin/views/{vid}")
        ck(g, "views-delete", r.status_code in (200, 204), r.status_code)
    # rules templates + assignments
    r = req(m, "POST", "/auth/admin/rules/templates", {"name": "qa-tpl-" + R.RUN, "kind": "ea_offline", "params": {}, "description": "qa"})
    j = js(r) or {}
    tid = j.get("tid") or j.get("id") or (j.get("template") or {}).get("id")
    ck(g, "rules-template-create", r.status_code in (200, 201, 422), f"{r.status_code} {r.text[:100]}")
    if tid:
        r = req(m, "PUT", f"/auth/admin/rules/templates/{tid}", {"name": "qa-tpl2-" + R.RUN, "params": {}})
        ck(g, "rules-template-put", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
        r = req(m, "POST", "/auth/admin/rules/assignments", {"template_id": tid, "scope": {"type": "account", "id": acc}, "enabled": False, "notify_client": False})
        j2 = js(r) or {}
        aid = j2.get("aid") or j2.get("id") or (j2.get("assignment") or {}).get("id")
        ck(g, "rules-assignment-create", r.status_code in (200, 201, 422), f"{r.status_code} {r.text[:100]}")
        if aid:
            r = req(m, "PATCH", f"/auth/admin/rules/assignments/{aid}", {"enabled": False})
            ck(g, "rules-assignment-patch", r.status_code == 200, r.status_code)
            r = req(m, "DELETE", f"/auth/admin/rules/assignments/{aid}")
            ck(g, "rules-assignment-delete", r.status_code in (200, 204), r.status_code)
        r = req(m, "DELETE", f"/auth/admin/rules/templates/{tid}")
        ck(g, "rules-template-delete", r.status_code in (200, 204), r.status_code)
    # view-as
    r = req(m, "POST", "/auth/admin/view-as", {"account_id": acc, "reason": "qa kiem thu api tu dong"})
    j = js(r) or {}
    gr = j.get("grant_id") or j.get("id")
    ck(g, "view-as-start", r.status_code == 200 and gr, f"{r.status_code} {r.text[:80]}")
    if gr:
        r = req(m, "POST", "/auth/admin/view-as/end", {"grant_id": gr})
        ck(g, "view-as-end", r.status_code in (200, 204), r.status_code)
    # bulk: prepare (khong execute that), execute voi cum tu sai
    r = req(m, "POST", "/auth/admin/bulk/prepare", {"action": "add_tag", "account_ids": [acc], "params": {"tag": "qa"}})
    j = js(r) or {}
    ck(g, "bulk-prepare", r.status_code in (200, 422), f"{r.status_code} {r.text[:100]}")
    ct = j.get("confirm_token")
    if ct:
        r = req(m, "POST", "/auth/admin/bulk/execute", {"confirm_token": ct, "phrase": "sai-cum-tu"})
        ck(g, "bulk-execute-cum-tu-sai-bi-tu-choi", r.status_code in (400, 403, 422), r.status_code)
    # import preview (csv 1 dong tai khoan thu) -> commit -> xoa
    acc2 = str(int(R.ACC_B) + 5)
    csv = f"platform,login\nmt5,{acc2}\n"
    r = req(m, "POST", "/auth/admin/import/preview", {"csv": csv})
    j = js(r) or {}
    ck(g, "import-preview", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
    pt = j.get("preview_token")
    if pt:
        r = req(m, "POST", "/auth/admin/import/commit", {"preview_token": pt})
        ck(g, "import-commit", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
        for v in ((js(r) or {}).get("secrets") or {}).values() if isinstance((js(r) or {}).get("secrets"), dict) else []:
            if isinstance(v, str):
                R.SECRETS_MEM.append(v)
        R.sh(f"docker exec -i tradingsys-auth python - delete {acc2} < {R.ROOT}/services/client-ui/qa/auth_testacct.py")
    # tao tai khoan qua API admin roi xoa
    acc3 = str(int(R.ACC_B) + 6)
    r = req(m, "POST", "/auth/admin/accounts", {"platform": "mt5", "login": acc3, "label": "qa", "notes": "qa"})
    ck(g, "accounts-create", r.status_code in (200, 201), f"{r.status_code} {r.text[:80]}")
    r = req(m, "DELETE", f"/auth/admin/accounts/mt5:{acc3}")
    ck(g, "accounts-delete", r.status_code in (200, 204), r.status_code)
    # staff + users action
    nm = "qa_stab_api_" + R.RUN + "s"
    r = req(m, "POST", "/auth/admin/staff", {"name": nm, "role": "analyst", "display_name": "QA staff", "scope_all": False, "group_ids": []})
    j = js(r) or {}
    ck(g, "staff-create", r.status_code in (200, 201), f"{r.status_code}")
    for v in [j.get("password"), (j.get("secrets") or {}).get("password") if isinstance(j.get("secrets"), dict) else None, j.get("temp_password")]:
        if isinstance(v, str):
            R.SECRETS_MEM.append(v)
    uid = j.get("user_id") or (j.get("user") or {}).get("user_id")
    if uid:
        r = req(m, "PATCH", f"/auth/admin/staff/{uid}", {"display_name": "QA staff 2"})
        ck(g, "staff-patch", r.status_code == 200, r.status_code)
        r = req(m, "POST", f"/auth/admin/users/{uid}/accounts", {"account_id": acc})
        ck(g, "user-assign-account", r.status_code in (200, 201, 405), f"{r.status_code} (405 = nginx whitelist khong phoi)")
        r = req(m, "DELETE", f"/auth/admin/users/{uid}/accounts/{acc}")
        ck(g, "user-unassign-account", r.status_code in (200, 204, 405), f"{r.status_code} (405 = nginx whitelist khong phoi)")
        r = req(m, "POST", f"/auth/admin/users/{uid}/suspend")
        ck(g, "user-suspend", r.status_code in (200, 204), r.status_code)
        r = req(m, "POST", f"/auth/admin/users/{uid}/activate")
        ck(g, "user-activate", r.status_code in (200, 204), r.status_code)
    R.sh(f"docker exec -i tradingsys-auth python - delete qa_stab_api_{R.RUN}s < {R.Q}/s_user.py")


# ------------------------------------------------------------------ realtime
def t_realtime(users):
    g = "realtime"
    m = users["master"]
    try:
        r = m.s.get(R.BASE + "/api/v1/rt/sse", stream=True, timeout=(8, 25), headers={"Origin": R.BASE, "Accept": "text/event-stream"})
        ct = r.headers.get("content-type", "")
        got, t0 = [], time.time()
        for ln in r.iter_lines(decode_unicode=True):
            if ln:
                got.append(ln[:80])
            if len(got) >= 3 or time.time() - t0 > 20:
                break
        r.close()
        ck(g, "sse-nhan-su-kien", r.status_code == 200 and "event-stream" in ct and len(got) >= 1, f"{r.status_code} {ct} {len(got)} dong trong {time.time()-t0:.1f}s")
    except Exception as ex:
        ck(g, "sse-nhan-su-kien", False, repr(ex)[:100])
    r = requests.get(R.BASE + "/api/v1/rt/sse", stream=True, timeout=10, headers={"Origin": R.BASE})
    ck(g, "sse-anon-bi-tu-choi", r.status_code in (401, 403), r.status_code); r.close()
    try:
        import websocket  # websocket-client
        sid = next((c.value for c in m.s.cookies if c.name == "ts_session"), "")
        ws = websocket.create_connection("ws://127.0.0.1:8580/api/v1/stream", timeout=20, header=[f"Cookie: ts_session={sid}", f"Origin: {R.BASE}"])
        msgs = []
        t0 = time.time()
        while time.time() - t0 < 20 and len(msgs) < 2:
            try:
                msgs.append(ws.recv()[:80])
            except Exception:
                break
        ws.close()
        ck(g, "ws-nhan-su-kien", len(msgs) >= 1, f"{len(msgs)} tin trong {time.time()-t0:.1f}s")
    except ImportError:
        try:
            import asyncio, websockets
            async def go():
                sid = next((c.value for c in m.s.cookies if c.name == "ts_session"), "")
                async with websockets.connect("ws://127.0.0.1:8580/api/v1/stream", additional_headers={"Cookie": f"ts_session={sid}", "Origin": R.BASE}, open_timeout=15) as ws:
                    msgs = []
                    t0 = time.time()
                    while time.time() - t0 < 20 and len(msgs) < 2:
                        try:
                            msgs.append((await asyncio.wait_for(ws.recv(), 10))[:80])
                        except Exception:
                            break
                    return msgs, time.time() - t0
            msgs, dt = asyncio.run(go())
            ck(g, "ws-nhan-su-kien", len(msgs) >= 1, f"{len(msgs)} tin trong {dt:.1f}s")
        except ImportError:
            ck(g, "ws-nhan-su-kien", False, "khong co thu vien websocket(s) tren host (BO QUA: khong cai them)")
        except Exception as ex:
            ck(g, "ws-nhan-su-kien", False, repr(ex)[:120])
    except Exception as ex:
        ck(g, "ws-nhan-su-kien", False, repr(ex)[:120])
    # WS anon
    try:
        r = requests.get(R.BASE + "/api/v1/stream", headers={"Origin": R.BASE, "Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}, timeout=10)
        ck(g, "ws-anon-bi-tu-choi", r.status_code in (401, 403, 404, 426), r.status_code)
    except Exception as ex:
        ck(g, "ws-anon-bi-tu-choi", False, repr(ex)[:80])


def t_idor_proxy(users):
    g = "idor-proxy"
    a, b = users["clientA"], users["clientB"]
    A, Bacc = f"mt5:{R.ACC_A}", f"mt5:{R.ACC_B}"
    paths = [f"/c/api/v1/journal/{Bacc}/summary", f"/c/api/v1/journal/{Bacc}/trades", f"/c/api/v1/journal/{Bacc}/equity",
             f"/c/api/v1/risk/accounts/{Bacc}", f"/c/api/v1/risk/{Bacc}", f"/c/api/v1/paper/accounts/{Bacc}",
             f"/c/api/v1/account-reports/{Bacc}", f"/c/api/v1/user/limits?account_id={Bacc}", f"/c/api/v1/user/tickets?account_id={Bacc}",
             f"/c/api/v1/user/notifications?account_id={Bacc}", f"/c/api/v1/briefing/{Bacc}", f"/c/api/v1/experts/accounts/{Bacc}",
             f"/c/api/v1/journal/{Bacc}/notes", "/c/api/v1/user/../risk/accounts/" + Bacc, "/c/api/v1/user/%2e%2e/journal/" + Bacc + "/summary",
             "/c/api/v1/user//..//..//auth/admin/accounts", "/c/api/v1/user/%2e%2e%2f%2e%2e%2fauth/admin/accounts",
             f"/c/api/v1/journal/{Bacc.replace(':', '%3A')}/summary", f"/c/api/v1/journal/MT5:{R.ACC_B}/summary", f"/c/api/v1/journal/mt5:{R.ACC_B}%00/summary",
             "/c/api/v1/journal/mt5:*/summary", "/c/api/v1/journal/%25/summary", f"/c/api/v1/journal/mt5:{R.ACC_A}/../mt5:{R.ACC_B}/summary"]
    leaks = []
    for p in paths:
        r = creq(a, "GET", p)
        body_has_b = R.ACC_B in r.text and r.status_code == 200 and "qa-" not in p
        bad = r.status_code >= 500 or (r.status_code == 200 and R.ACC_B in r.text and R.ACC_A not in p.split(R.ACC_B)[0][:0] + "")
        if r.status_code >= 500:
            leaks.append(f"{p[:60]}:{r.status_code}")
        elif r.status_code == 200 and R.ACC_B in r.text:
            leaks.append(f"{p[:60]}:200 chua id B")
        time.sleep(0.15)
    ck(g, "clientA-doc-du-lieu-B-qua-proxy", not leaks, "; ".join(leaks[:4]) or f"{len(paths)} duong dan deu bi chan/rong")
    # client truy cap /auth/admin va route master qua proxy
    leaks = []
    for p in ("/c/auth/admin/accounts", "/c/auth/admin/audit", "/c/api/v1/user/../../auth/admin/users", "/c/api/v1/ai-trading/class/rooms",
              "/c/api/v1/ai-trading/guardrail", "/c/api/v1/data/sources"):
        r = creq(a, "GET", p)
        if r.status_code == 200:
            leaks.append(f"{p[:50]}:200")
        time.sleep(0.15)
    ck(g, "clientA-khong-vao-route-master", True if not leaks else False, "; ".join(leaks) or "403/404 het (route cho phep rut gon da ghi o authz)")
    # ghi cheo qua {rest}
    leaks = []
    for m_, p, bd in (("PUT", f"/c/api/v1/user/limits", {"account_id": Bacc, "key": "max_dd_pct", "value": 1}),
                      ("PUT", f"/c/api/v1/journal/{Bacc}/notes/deal/zz", {"note": "idor"}),
                      ("DELETE", f"/c/api/v1/journal/{Bacc}/notes/deal/zz", None),
                      ("POST", "/c/api/v1/user/tickets", {"account_id": Bacc, "category": "other", "message": "idor"})):
        r = creq(a, m_, p, bd)
        if r.status_code < 400:
            leaks.append(f"{m_} {p[:40]}:{r.status_code}")
    ck(g, "clientA-ghi-cheo-vao-B-qua-proxy", not leaks, "; ".join(leaks) or "bi chan het")


def main():
    users, accC = {}, None
    accCn = str(int(R.ACC_B) + 3)
    try:
        users = R.mk_users()
        accC = fresh_client(accCn)
        accC["account_id"] = f"mt5:{accCn}"
        print("phien:", sorted(users), flush=True)
        users.update(prep_clients(users))
        mm = prep_master(users)
        if mm:
            users["master"] = mm
        for fn, args in ((t_realtime, (users,)), (t_idor_proxy, (users,)), (t_user_writes, (users,)), (t_admin_writes, (users, accC)),
                         (t_auth, (users, accC)), (t_totp, (users,))):
            try:
                fn(*args)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ck(fn.__name__, "ngoai-le-runner", False, repr(ex)[:150])
    finally:
        R.drop_users()
        for a in (accCn, str(int(R.ACC_B) + 5), str(int(R.ACC_B) + 6)):
            R.sh(f"docker exec -i tradingsys-auth python - delete {a} < {R.ROOT}/services/client-ui/qa/auth_testacct.py")
        # quet ro ri secret
        txt = json.dumps(RES)
        for v in R.SECRETS_MEM:
            if v and len(v) >= 10 and v in txt:
                ck("secret", "khong-lo-trong-ket-qua", False, "secret xuat hien trong chi tiet")
        json.dump(RES, open(OUT, "w"), ensure_ascii=False, indent=1)
        p = sum(1 for x in RES if x["ok"])
        print(f"extra: {p} PASS / {len(RES)-p} FAIL")


if __name__ == "__main__":
    main()
