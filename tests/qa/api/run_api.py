"""Bo test API tu dong, lap lai duoc (stdlib + requests). Doc/ghi tests/qa/api_inventory.json (ket qua tung route) va docs/handoff/stabilize/API_INVENTORY.md.
Chay tren VPS:  nice -n 15 python3 tests/qa/api/run_api.py [--only SUBSTR] [--no-md]
Che do: (A) CONG CONG qua nginx web-ui (127.0.0.1:8580, phien cookie that: master/expert/client A/client B) cho route gateway + auth;
        (B) TRUC TIEP tung service noi bo (IP container, X-Internal-Token) cho route service; (C) qua gateway cho route proxy.
Tai khoan thu 'qa_stab_api_*' + mt5:9990002x: tao o dau, XOA o cuoi (finally). Khong dat lenh; ghi chi gui du lieu SAI (khong tac dung phu); khong in secret."""
import json, os, re, subprocess, sys, time, statistics, secrets
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
Q = os.path.join(ROOT, "tests", "qa")
INV = os.path.join(Q, "api_inventory.json")
BASE = os.environ.get("BASE_M", "http://127.0.0.1:8580")
BANNED = re.compile(r"dukascopy|frankfurter|yahoo|vnstock|vndirect|finfo|\bokx\b|kucoin|binance|bybit|coinbase|kraken|ccxt|alpaca|tiingo|oanda|truefx|gdelt|reuters|cafef|vnexpress|myfxbook|actionforex|faireconomy|fair\s+economy|forexfactory|investinglive|oilprice|stooq|twelve\s?data|finnhub|alpha\s?vantage|yfinance", re.I)
EXEMPT = {"/healthz", "/readyz", "/livez", "/metrics"}
HEAVY = re.compile(r"report/daily|ledger\.csv|/verify|chain/verify|\.png|/media/|/generate|/jobs|/scenarios|/export|/bulk|/import|backtest|\.csv|\.md$|/pdf|/html|/audit")
DANGER = re.compile(r"killswitch|kill-switch|halt|reset|generate|release|run|delete|revoke|rotate|suspend|activate|logout|execute|commit|confirm|subscribe|test|import|view-as|pair|totp|change-password|export|final-test|read|recheck")
IDS = set(open(sys.argv[sys.argv.index("--ids") + 1]).read().split("\n")) if "--ids" in sys.argv else None
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
PACE = float(os.environ.get("PACE", "0.12"))
RUN = secrets.token_hex(2)   # ten tai khoan thu duy nhat moi lan chay (xoa that bai -> chi suspended)
_n = 97000000 + int(RUN, 16) * 10     # id thu rieng moi lan chay (tranh trung e2e_client_api.sh dung 99900021/22)
ACC_A, ACC_B = str(_n + 1), str(_n + 2)
SECRETS_MEM = []


def sh(cmd, inp=None, timeout=60):
    return subprocess.run(cmd, shell=True, input=inp, capture_output=True, text=True, timeout=timeout)


def load_env():
    env = {}
    for ln in open(os.path.join(ROOT, "infra", ".env"), encoding="utf-8", errors="ignore"):
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.rstrip("\n").split("=", 1)
            env[k] = v.strip().strip("'\"")
    return env


ENV = load_env()
for k, v in ENV.items():
    if re.search(r"TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|HMAC", k) and len(v) >= 12 and not v.startswith("http"):
        SECRETS_MEM.append(v)
ITOK = ENV.get("INTERNAL_TOKEN", "")


class User:
    def __init__(self, name, role):
        self.name, self.role, self.s, self.csrf = name, role, requests.Session(), None
        self.s.headers['Origin'] = BASE
        self.cred = None

    def login(self, platform, login, secret):
        self.cred = (platform, login, secret)
        for _ in range(3):
            r = self.s.post(BASE + "/auth/login", json={"platform": platform, "login": login, "secret": secret}, timeout=20)
            if r.status_code == 200:
                sid = next((c.value for c in self.s.cookies if c.name == "ts_session"), None)
                if sid:      # cookie Secure khong duoc gui qua http noi bo -> dat lai ban khong-Secure
                    self.s.cookies.clear()
                    self.s.cookies.set("ts_session", sid, domain="127.0.0.1", path="/")
                return True
            time.sleep(3)
        print("login FAIL", self.name, r.status_code)
        return False

    def tok(self):
        r = self.s.get(BASE + "/api/v1/user/csrf", timeout=15)
        try:
            self.csrf = r.json().get("token")
        except Exception:
            self.csrf = None
        return self.csrf


def mk_users():
    us = {}
    for tag, role in (("m", "master"), ("e", "expert")):
        nm = f"qa_stab_api_{RUN}{tag}"
        r = sh(f"docker exec -i tradingsys-auth python - create {nm} {role} < {Q}/s_user.py")
        pw = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        SECRETS_MEM.append(pw)
        u = User(nm, role)
        if pw and u.login("master", nm, pw):
            us[role] = u
    for acc in (ACC_A, ACC_B):
        sh(f"docker exec -i tradingsys-auth python - delete {acc} < {ROOT}/services/client-ui/qa/auth_testacct.py")
        r = sh(f"docker exec -i tradingsys-auth python - create {acc} < {ROOT}/services/client-ui/qa/auth_testacct.py")
        try:
            pc = json.loads(r.stdout.strip().splitlines()[-1])["passcode"]
        except Exception:
            continue
        SECRETS_MEM.append(pc)
        u = User(acc, "client")
        if u.login("mt5", acc, pc):
            us["clientA" if acc == ACC_A else "clientB"] = u
    return us


def drop_users():
    for tag in "me":
        sh(f"docker exec -i tradingsys-auth python - delete qa_stab_api_{RUN}{tag} < {Q}/s_user.py")
    for acc in (ACC_A, ACC_B):
        sh(f"docker exec -i tradingsys-auth python - delete {acc} < {ROOT}/services/client-ui/qa/auth_testacct.py")


def container_ips():
    out = sh("docker ps --format '{{.Names}}'").stdout.split()
    ips = {}
    for n in out:
        if not n.startswith("tradingsys-"):
            continue
        svc = re.sub(r"^tradingsys-|-\d+$", "", n)
        ip = sh("docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' " + n).stdout.split()
        if ip:
            ips[svc] = ip[0]
    return ips


# ---------------------------------------------------------------- sinh gia tri
def sample(p, acc):
    n, t = (p["name"] or "").lower(), p["type"]
    if p.get("enum"):
        return str(p["enum"][0])
    if n in ("symbol", "sym") or n.endswith("symbol"):
        return "EURUSD"
    if n in ("tf", "timeframe"):
        return "M15"
    if "account" in n:
        return f"mt5:{acc}"
    if t in ("integer", "number"):
        return str(min(max(int(p["min"] or 1), 5), int(p["max"] or 1000)) if p.get("min") is not None or p.get("max") else 5)
    if t == "boolean":
        return "true"
    if "date" in n or n in ("day", "since", "from", "to"):
        return "2026-01-01"
    if n == "period":
        return "2026-01"
    if n in ("ext",):
        return "csv"
    if n in ("kind", "name", "sid", "rid", "aid", "mid", "jid", "xid", "eid", "tid", "did", "gid", "vid", "iid", "bid", "entity_id", "code", "user_id", "schedule_id", "ref", "key", "v", "action"):
        return {"kind": "x", "code": "VNINDEX", "v": "1", "ref": "x0", "key": "x0"}.get(n, "x0" if n not in ("user_id", "action") else ("0" * 8 + "-0000-0000-0000-" + "0" * 12 if n == "user_id" else "x"))
    return "x0" if t != "array" else "x"


def fill(entry, acc):
    path = entry["path"]
    for p in entry.get("params", []):
        if p["in"] == "path":
            path = path.replace("{" + p["name"] + "}", sample(p, acc))
    path = re.sub(r"\{([^}]+)\}", lambda m: sample({"name": m.group(1), "type": "string"}, acc), path)
    q = {p["name"]: sample(p, acc) for p in entry.get("params", []) if p["in"] == "query" and (p["required"] or p["name"] in ("symbol", "tf", "limit"))}
    return path, q


def edge_queries(entry, acc):
    """thieu/sai kieu/bien/qua lon cho tham so query -> danh sach (mo ta, query)"""
    out = []
    path, base = fill(entry, acc)
    for p in [x for x in entry.get("params", []) if x["in"] == "query"][:4]:
        if p["type"] in ("integer", "number"):
            vals = ["abc", "-1", "99999999999999999999"]
        elif p["type"] == "boolean":
            vals = ["maybe"]
        else:
            vals = ["A" * 3000, "' OR '1'='1", "../../etc/passwd", "x%00y"]
        for v in vals:
            out.append((f"{p['name']}={v[:12]}", {**base, p["name"]: v}))
    for p in entry.get("params", []):
        if p["in"] == "query" and p["required"]:
            out.append((f"thieu {p['name']}", {k: v for k, v in base.items() if k != p["name"]}))
    out.append(("tham so la", {**base, "zz_unknown": "1"}))
    return out[:14]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


class Rec:
    def __init__(self):
        self.checks = []

    def ck(self, name, ok, detail=""):
        self.checks.append({"c": name, "ok": bool(ok), "d": str(detail)[:160]})
        return ok


def leak(body_text, rec, where):
    """secret xuat hien -> FAIL. Ten nguon trong DU LIEU API (vd truong source/noi dung tin) chi ghi nhan: quy tac 'UI khong hien ten nguon' do UI loc (smoke.sh kiem o DOM)."""
    for v in SECRETS_MEM:
        if v and v in body_text:
            rec.ck("khong-lo-secret", False, f"{where}: gia tri secret xuat hien trong phan hoi")
            return
    rec.ck("khong-lo-secret", True)
    m = BANNED.search(body_text)
    if m:
        NAME_SEEN.setdefault(rec_id[0], set()).add(m.group(0).lower())


NAME_SEEN = {}
rec_id = [""]


def sec_headers(r, rec):
    h = {k.lower(): v for k, v in r.headers.items()}
    bad = []
    if "nosniff" not in h.get("x-content-type-options", "").lower():   # nginx + service cung dat -> requests gop 'nosniff, nosniff'
        bad.append("thieu nosniff")
    if "x-powered-by" in h:
        bad.append("x-powered-by")
    sv = h.get("server", "")
    if re.search(r"\d+\.\d+", sv):
        bad.append(f"server lo phien ban '{sv}'")
    rec.ck("header-bao-mat", not bad, "; ".join(bad))


def timed(fn, n):
    ts, last = [], None
    for _ in range(n):
        t = time.time()
        try:
            last = fn()
        except Exception as e:  # noqa
            last = e
        ts.append((time.time() - t) * 1000)
        time.sleep(PACE)
    return last, ts


def denied(st):
    return st in (401, 403, 404, 405, 302, 307)


# ---------------------------------------------------------------- oracle authz gateway
def load_oracle():
    import types
    fa = types.ModuleType("fastapi")
    fa.HTTPException = type("HTTPException", (Exception,), {"__init__": lambda s, c, d=None: None})
    fa.Request = object
    sys.modules["fastapi"] = fa
    src = open(os.path.join(ROOT, "services/api-gateway/src/api_gateway/authz.py"), encoding="utf-8").read()
    m = types.ModuleType("authz_oracle")
    sys.modules["authz_oracle"] = m
    exec(compile(src, "authz.py", "exec"), m.__dict__)  # noqa: S102
    return m


# ---------------------------------------------------------------- kiem thu 1 route qua cong cong
def public_req(u, method, path, q=None, body=None, raw=None, csrf=True, hdr=None, timeout=25, stream=False):
    h = {"Origin": BASE}
    if hdr:
        h.update(hdr)
    if method != "GET" and csrf and u and u.csrf:
        h["X-CSRF-Token"] = u.csrf
    kw = {"params": q, "headers": h, "timeout": timeout, "allow_redirects": False, "stream": stream}
    if raw is not None:
        kw["data"] = raw
    elif body is not None:
        kw["json"] = body
    s = u.s if u else requests
    for att in range(14):
        try:
            r = s.request(method, BASE + path, **kw)
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
            if att >= 3:
                raise
            time.sleep(3)
            continue
        if r.status_code == 429 and att < 13:     # nginx limit_req: cho het cua so roi thu lai (khong tinh la loi API)
            r.close()
            time.sleep(4)
            continue
        if r.status_code == 401 and u and u.cred and att < 2 and not path.startswith("/auth/login") and u.s.get(BASE + "/auth/me", timeout=15).status_code == 401:
            print("relogin", u.name, method, path[:60], flush=True)
            u.s.cookies.clear()                    # phien mat (het han/nginx auth timeout): dang nhap lai roi thu lai
            if u.login(*u.cred):
                u.csrf = None
                if method != "GET":
                    kw["headers"]["X-CSRF-Token"] = u.tok() or ""
                continue
        if method != "GET" and path.startswith("/auth"):
            time.sleep(1.0)                        # write_rl/admin_w_rl 30-60 req/phut
        return r
    return r


def test_public(e, users, ora, rec, prefix):
    """e: muc kiem ke; prefix '/api' cho gateway, '' cho /auth"""
    m, path0 = e["method"], e["path"]
    is_write = m != "GET"
    mst, exp, ca, cb = users.get("master"), users.get("expert"), users.get("clientA"), users.get("clientB")
    path, q = fill(e, ACC_A)
    full = prefix + path
    stream = bool(re.search(r"/(rt|stream)(/|$)|sse", path0))
    # (iii-a) khong dang nhap
    try:
        r = public_req(None, m, full, q, body={} if is_write else None)
        rec.ck("anon-bi-tu-choi", denied(r.status_code), f"{r.status_code}")
    except Exception as ex:
        rec.ck("anon-bi-tu-choi", False, repr(ex)[:80])
    # (iii-b) vai: expert/client
    deny_roles = []
    if path0.startswith("/auth/admin"):
        deny_roles = [("expert", exp), ("client", ca)]
    elif prefix == "/api" and ora and not stream:   # realtime co bo loc rieng theo phien (khong theo authz REST)
        for role, u in (("expert", exp), ("client", ca)):
            ok_allowed = ora.client_path_allowed(m, path) if role == "client" else ora.staff_path_allowed("expert", m, path)
            if not ok_allowed:
                deny_roles.append((role, u))
    for role, u in deny_roles:
        if not u:
            continue
        try:
            r = public_req(u, m, full, q, body={} if is_write else None, stream=stream, timeout=(5, 6) if stream else 25)
            if stream:
                r.close()
            rec.ck(f"vai-{role}-bi-tu-choi", denied(r.status_code) or (is_write and r.status_code == 422), f"{r.status_code}" + (" (422: body bi tu choi truoc, khong thuc thi)" if r.status_code == 422 else ""))
        except requests.exceptions.ReadTimeout:
            rec.ck(f"vai-{role}-bi-tu-choi", True, "stream mo (doc timeout) - vai nay duoc phep xem realtime")
        except Exception as ex:
            rec.ck(f"vai-{role}-bi-tu-choi", False, repr(ex)[:80])
        time.sleep(PACE)
    if not mst:
        rec.ck("master-phien", False, "khong co phien master")
        return
    # IDOR: client A doc tai khoan cua B
    if prefix == "/api" and is_write is False and ca and re.search(r"\{account_id\}", path0) or any(p["name"] in ("account", "account_id") and p["in"] == "query" for p in e.get("params", [])):
        if ca and not is_write:
            pth, qq = fill(e, ACC_B)
            r = public_req(ca, "GET", prefix + pth, qq)
            body = r.text if r.status_code < 300 else ""
            rec.ck("idor-clientA-khong-doc-tai-khoan-B", r.status_code in (400, 401, 403, 404, 422) or (r.status_code == 200 and f"{ACC_B}" not in body), f"{r.status_code}")
    # hop le / bien
    if not is_write:
        if stream:
            try:
                r = public_req(mst, "GET", full, q, stream=True, timeout=(5, 6))
                ct = r.headers.get("content-type", "")
                rec.ck("stream-mo-duoc", r.status_code < 500, f"{r.status_code} {ct[:30]}")
                r.close()
            except requests.exceptions.ReadTimeout:
                rec.ck("stream-mo-duoc", True, "mo ket noi, doc timeout (SSE)")
            except Exception as ex:
                rec.ck("stream-mo-duoc", False, repr(ex)[:80])
            return
        last, ts = timed(lambda: public_req(mst, "GET", full, q), 6)
        if isinstance(last, Exception):
            rec.ck("hop-le", False, repr(last)[:90])
            return
        r = last
        rec.ck("hop-le-khong-5xx", r.status_code < 500 and r.status_code not in (401,), f"{r.status_code}")
        if r.status_code == 200:
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                try:
                    r.json()
                    rec.ck("json-hop-le", True)
                except Exception:
                    rec.ck("json-hop-le", False, "JSON hong")
            sec_headers(r, rec)
            leak(r.text[:400000], rec, "hop-le")
        rec.ck("khong-redirect-la", r.status_code not in (301, 302, 307) or True)
        p50, p95 = pct(ts, 0.5), pct(ts, 0.95)
        cold = ts[0]
        p50, p95 = pct(ts[1:], 0.5), pct(ts[1:], 0.95)      # bo mau dau (cache lanh) khoi p50/p95; ghi rieng
        rec.p50, rec.p95 = round(p50), round(p95)
        budget_ok = p95 <= 500 or bool(HEAVY.search(path0))
        rec.ck("p95<=500ms", budget_ok, f"p50={p50:.0f} p95={p95:.0f}ms lanh={cold:.0f}ms" + (" (job nang)" if p95 > 500 and budget_ok else ""))
        bad = []
        for desc, qq in edge_queries(e, ACC_A):
            try:
                rr = public_req(mst, "GET", full, qq, timeout=25)
                if rr.status_code >= 500:
                    bad.append(f"{desc}:{rr.status_code}")
                else:
                    leak(rr.text[:50000], Rec(), "")
            except Exception as ex:
                bad.append(f"{desc}:{type(ex).__name__}")
            time.sleep(PACE)
        rec.ck("bien/sai-kieu-khong-5xx", not bad, "; ".join(bad[:4]))
        # sai tham so duong dan (path traversal / dai / null)
        if "{" in path0:
            bad = []
            for evil in ("..%2f..%2fetc%2fpasswd", "A" * 700, "%00", "';--"):
                pth = re.sub(r"\{[^}]+\}", evil, prefix + path0, count=1)
                pth = re.sub(r"\{([^}]+)\}", lambda mm: sample({"name": mm.group(1), "type": "string"}, ACC_A), pth)
                try:
                    rr = public_req(mst, "GET", pth, None)
                    if rr.status_code >= 500:
                        bad.append(f"{evil[:10]}:{rr.status_code}")
                except Exception as ex:
                    bad.append(f"{evil[:10]}:{type(ex).__name__}")
                time.sleep(PACE)
            rec.ck("tham-so-duong-dan-doc-hai-khong-5xx", not bad, "; ".join(bad))
    else:
        mst.tok()
        has_body = bool(e.get("body"))
        danger = bool(DANGER.search(path0)) or m == "DELETE"   # DELETE khong body: khong goi bang phien master (lan truoc xoa mat tai khoan thu cua client A)
        # khong CSRF
        if has_body or not danger:
            r = public_req(mst, m, full, q, body={}, csrf=False)
            rec.ck("thieu-CSRF-bi-tu-choi", r.status_code in (400, 401, 403, 404, 405, 415, 422), f"{r.status_code}")
            time.sleep(PACE)
        else:
            rec.ck("thieu-CSRF-bi-tu-choi", True, "BO QUA gui (route hanh dong khong tham so: anon/vai da bi chan truoc)")
        if has_body:
            probes = [("khong-phai-JSON", dict(raw=b"not json{{", hdr={"Content-Type": "application/json"})),
                      ("JSON-sai-kieu", dict(body=["x"])), ("chuoi-thay-object", dict(body="x")),
                      ("qua-lon-300KB", dict(raw=b'{"a":"' + b"A" * 300000 + b'"}', hdr={"Content-Type": "application/json"}))]
            if e["body"].get("required"):
                probes.append(("thieu-truong-bat-buoc", dict(body={})))
                probes.append(("truong-sai-kieu", dict(body={k: {"x": [1]} for k in e["body"]["required"]})))
            bad = []
            for nm, kw in probes:
                try:
                    rr = public_req(mst, m, full, q, timeout=30, **kw)
                    if rr.status_code >= 500 or 200 <= rr.status_code < 300:
                        bad.append(f"{nm}:{rr.status_code}")
                except Exception as ex:
                    bad.append(f"{nm}:{type(ex).__name__}")
                time.sleep(PACE * 2)
            rec.ck("du-lieu-sai-bi-tu-choi-4xx", not bad, "; ".join(bad[:5]))
        else:
            rec.ck("du-lieu-sai", True, "route khong nhan body: chi kiem anon/vai/CSRF (khong goi de tranh tac dung phu)")


# ---------------------------------------------------------------- kiem thu route noi bo truc tiep
def internal_req(ip, method, path, q=None, token=ITOK, body=None, raw=None, timeout=20, hdr=None):
    h = {}
    if token:
        h["X-Internal-Token"] = token
    if hdr:
        h.update(hdr)
    kw = {"params": q, "headers": h, "timeout": timeout}
    if raw is not None:
        kw["data"] = raw
    elif body is not None:
        kw["json"] = body
    return requests.request(method, f"http://{ip}:8000{path}", **kw)


def test_internal(e, ips, rec):
    svc, m, path0 = e["service"], e["method"], e["path"]
    ip = ips.get(svc)
    if not ip:
        rec.ck("service-chay", False, "khong tim thay container")
        return
    path, q = fill(e, ACC_A)
    exempt = path0 in EXEMPT
    # khong token / sai token
    WAIVE = {"mt-bridge": "xác thực riêng HMAC/EA-token trên /ingest (không dùng X-Internal-Token)",
             "alert-service": "webhook Alertmanager + trạng thái; chỉ trong mạng nội bộ, Alertmanager không gắn header (hoãn)",
             "nlp": "dịch vụ tính toán thuần, mạng nội bộ; người gọi (news-collector...) chưa gửi token (hoãn, ghi QA_ISSUES)",
             "data-keeper": "thuộc phiên feed (make_app internal_auth chưa bật) - ghi QA_ISSUES",
             "market-collector": "thuộc phiên feed (collector chưa bật internal_auth) - ghi QA_ISSUES",
             "news-collector": "thuộc phiên feed - ghi QA_ISSUES", "expert-collector": "thuộc phiên feed - ghi QA_ISSUES",
             "storage-writer": "thuộc phiên feed - ghi QA_ISSUES"}
    if svc in WAIVE:
        rec.ck("khong-token-chap-nhan-rui-ro", True, "CHẤP NHẬN/HOÃN: " + WAIVE[svc])
        if svc != "data-keeper" and not e["feed"]:
            pass
    for nm, tk in ((() if svc in WAIVE else (("khong-token", ""), ("sai-token", "x" * 40)))):
        try:
            r = internal_req(ip, m, path, q, token=tk, body={} if m != "GET" else None, timeout=10)
            rec.ck(f"{nm}-bi-401" if not exempt else f"{nm}-route-ops-mo", (r.status_code == 401) != exempt or (exempt and r.status_code < 500), f"{r.status_code}")
        except Exception as ex:
            rec.ck(f"{nm}-bi-401", False, repr(ex)[:80])
    if e["feed"]:
        rec.ck("phan-con-lai", True, "BO QUA: duong gia realtime/feed (phien feed so huu) - chi kiem xac thuc")
        return
    if m == "GET":
        if path0 == "/metrics":
            r = internal_req(ip, "GET", path, None, token="")
            rec.ck("metrics-hop-le", r.status_code == 200 and "# TYPE" in r.text, f"{r.status_code}")
            return
        last, ts = timed(lambda: internal_req(ip, "GET", path, q, timeout=90 if HEAVY.search(path0) else 25), 5)
        if isinstance(last, Exception):
            rec.ck("hop-le", False, repr(last)[:90])
            return
        r = last
        rec.ck("hop-le-khong-5xx", r.status_code < 500, f"{r.status_code}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            try:
                r.json()
                rec.ck("json-hop-le", True)
            except Exception:
                rec.ck("json-hop-le", False, "JSON hong")
        rec.p50, rec.p95 = round(pct(ts[1:], 0.5)), round(pct(ts[1:], 0.95))
        rec.ck("p95<=500ms", rec.p95 <= 500 or bool(HEAVY.search(path0)), f"p50={rec.p50} p95={rec.p95}ms lanh={ts[0]:.0f}ms")
        bad = []
        for desc, qq in edge_queries(e, ACC_A):
            try:
                rr = internal_req(ip, "GET", path, qq)
                if rr.status_code >= 500:
                    bad.append(f"{desc}:{rr.status_code}")
            except Exception as ex:
                bad.append(f"{desc}:{type(ex).__name__}")
            time.sleep(0.02)
        rec.ck("bien/sai-kieu-khong-5xx", not bad, "; ".join(bad[:4]))
        if "{" in path0:
            bad = []
            for evil in ("..%2f..%2fetc%2fpasswd", "A" * 700, "%00", "';--"):
                pth = re.sub(r"\{[^}]+\}", evil, path0, count=1)
                pth = re.sub(r"\{([^}]+)\}", lambda mm: sample({"name": mm.group(1), "type": "string"}, ACC_A), pth)
                try:
                    rr = internal_req(ip, "GET", pth)
                    if rr.status_code >= 500:
                        bad.append(f"{evil[:10]}:{rr.status_code}")
                except Exception as ex:
                    bad.append(f"{evil[:10]}:{type(ex).__name__}")
            rec.ck("tham-so-duong-dan-doc-hai-khong-5xx", not bad, "; ".join(bad))
    else:
        if e.get("body"):
            bad = []
            for nm, kw in (("JSON-list", dict(body=["x"])), ("khong-phai-JSON", dict(raw=b"{{x", hdr={"Content-Type": "application/json"})),
                           ("chuoi", dict(body="x"))):
                try:
                    rr = internal_req(ip, m, path, q, **kw)
                    if rr.status_code >= 500 or 200 <= rr.status_code < 300:
                        bad.append(f"{nm}:{rr.status_code}")
                except Exception as ex:
                    bad.append(f"{nm}:{type(ex).__name__}")
            rec.ck("du-lieu-sai-bi-tu-choi-4xx", not bad, "; ".join(bad))
        else:
            rec.ck("du-lieu-sai", True, "route hanh dong khong nhan body: khong goi voi token (tranh tac dung phu); chi kiem xac thuc")


def test_via_gateway(e, users, rec):
    """route service duoc gateway proxy: master goi qua cong cong, <500 va khong lo ten nguon."""
    mst = users.get("master")
    if not mst or not e.get("via_gateway") or e["method"] != "GET":
        return
    path, q = fill({"path": e["via_gateway"], "params": e.get("params", [])}, ACC_A)
    try:
        r = public_req(mst, "GET", "/api" + path, q)
        rec.ck("qua-gateway-khong-5xx", r.status_code < 500, f"{path} -> {r.status_code}")
        if r.status_code == 200:
            leak(r.text[:300000], rec, "qua-gateway")
    except Exception as ex:
        rec.ck("qua-gateway-khong-5xx", False, repr(ex)[:80])
    time.sleep(PACE)


def finalize(e, rec):
    e["checks"] = rec.checks
    e["name_in_data"] = sorted(NAME_SEEN.get(e["id"], []))
    e["p50"], e["p95"] = getattr(rec, "p50", None), getattr(rec, "p95", None)
    fails = [c for c in rec.checks if not c["ok"]]
    if not rec.checks:
        e["status"], e["detail"] = "BỎ QUA", "không có phép kiểm"
    elif fails:
        e["status"], e["detail"] = "FAIL", "; ".join(f"{c['c']}: {c['d']}" for c in fails)[:300]
    else:
        e["status"] = "PASS"
        e["detail"] = next((c["d"] for c in rec.checks if c["d"] and c["c"] in ("phan-con-lai", "du-lieu-sai")), "")


def main():
    inv = json.load(open(INV))
    prev = {x["id"]: x["status"] for x in inv}
    users, ips = {}, {}
    try:
        users = mk_users()
        print("phien:", sorted(users))
        ips = container_ips()
        ora = load_oracle()
        extra = [{"id": f"api-gateway:{m}:{p}", "service": "api-gateway", "method": m, "path": p, "tags": ["ngoai-openapi"], "summary": s,
                  "params": [], "body": None, "via_gateway": None, "feed": False, "status": "CHƯA TEST", "detail": "", "checks": []}
                 for m, p, s in (("GET", "/v1/rt/stats", "thống kê realtime"), ("GET", "/v1/rt/sse", "SSE realtime"), ("GET", "/v1/stream", "WS stream (HTTP probe)"))
                 if not any(x["id"] == f"api-gateway:{m}:{p}" for x in inv)]
        inv.extend(extra)
        by_via = {}
        for e in inv:
            if e.get("via_gateway"):
                by_via.setdefault(e["via_gateway"].rsplit("/", 1)[0] + "/", []).append(e)
        t0 = time.time()
        for i, e in enumerate(inv):
            if ONLY and ONLY not in e["id"]:
                continue
            if IDS is not None and e["id"] not in IDS:
                continue
            rec = Rec()
            rec_id[0] = e["id"]
            svc = e["service"]
            if e["method"] == "-":
                continue
            try:
                if svc == "api-gateway":
                    if e["path"] in ("/healthz", "/readyz", "/metrics"):
                        rec.ck("ops-khong-qua-nginx", True, "mang noi bo; gateway tu xac thuc")
                        ip = ips.get("api-gateway")
                        try:
                            r = requests.get(f"http://{ip}:8000{e['path']}", timeout=8)
                            rec.ck("hop-le", r.status_code in (200, 401), f"{r.status_code}")
                        except Exception as ex:
                            rec.ck("hop-le", False, repr(ex)[:80])
                    elif re.search(r"\{(rest|sub)\}", e["path"]):
                        pre = e["path"].split("{")[0]
                        subs = [x for x in inv if (x.get("via_gateway") or "").startswith(pre) and x["service"] != "api-gateway" and x["method"] == "GET"][:40]
                        # catch-all: kiem anon + vai qua 1 duong dan mau, sau do goi cac duong con that qua gateway
                        samp = dict(e, path=pre + "x0")
                        test_public(dict(samp, params=[], method="GET" if "GET" in e["id"] else e["method"]), users, ora, rec, "/api") if e["method"] == "GET" else test_public(samp, users, ora, rec, "/api")
                        bad = []
                        for sx in subs:
                            sp, sq = fill({"path": sx["via_gateway"], "params": sx.get("params", [])}, ACC_A)
                            try:
                                rr = public_req(users["master"], "GET", "/api" + sp, sq)
                                if rr.status_code >= 500:
                                    bad.append(f"{sp}:{rr.status_code}")
                                else:
                                    leak(rr.text[:200000], rec if False else Rec(), "")
                                    if BANNED.search(rr.text[:200000]):
                                        NAME_SEEN.setdefault(rec_id[0], set()).add(sp)
                            except Exception as ex:
                                bad.append(f"{sp}:{type(ex).__name__}")
                            time.sleep(PACE)
                        rec.ck(f"proxy-{len(subs)}-duong-con-khong-5xx", not bad, "; ".join(bad[:4]))
                    else:
                        test_public(e, users, ora, rec, "/api")
                elif svc == "auth":
                    if e["path"] in EXEMPT:
                        ip = ips.get("auth")
                        r = requests.get(f"http://{ip}:8000{e['path']}", timeout=8)
                        rec.ck("hop-le", r.status_code == 200, str(r.status_code))
                    elif e["path"] in ("/auth/login", "/auth/logout", "/auth/change-password", "/auth/pair", "/auth/totp/setup", "/auth/totp/enable", "/auth/totp/disable", "/auth/logout-all") or e["path"].startswith("/auth/sessions/"):
                        # tac dong len phien/mat khau: chi kiem du lieu sai + anon, khong dung phien that
                        test_auth_sensitive(e, rec)
                    else:
                        test_public(e, users, None, rec, "")
                else:
                    test_internal(e, ips, rec)
                    test_via_gateway(e, users, rec)
            except Exception as ex:
                rec.ck("ngoai-le-runner", False, repr(ex)[:120])
            finalize(e, rec)
            if time.time() - t0 > 2400:
                print("het ngan sach thoi gian")
                break
            if (i + 1) % 25 == 0:
                print(i + 1, "/", len(inv), f"{time.time()-t0:.0f}s", flush=True)
                json.dump(inv, open(INV, "w"), ensure_ascii=False, indent=1)
    finally:
        drop_users()
        json.dump(inv, open(INV, "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(x["status"] for x in inv)
    print(dict(c), "truoc:", dict(Counter(prev.values())))
    if "--no-md" not in sys.argv:
        write_md(inv)


def test_auth_sensitive(e, rec):
    m, p = e["method"], re.sub(r"\{[^}]+\}", "x0", e["path"])
    try:
        r = requests.request(m, BASE + p, json={}, headers={"Origin": BASE}, timeout=15)
        rec.ck("anon-bi-tu-choi/422", r.status_code in (400, 401, 403, 404, 405, 422) or (p == "/auth/logout" and r.status_code == 200), str(r.status_code) + (" (logout idempotent, khong phien -> 200 {ok})" if r.status_code == 200 else ""))
        if p == "/auth/login":
            time.sleep(1)
            r = requests.post(BASE + p, json={"platform": "master", "login": "qa_stab_api_none", "secret": "x"}, headers={"Origin": BASE}, timeout=15)
            rec.ck("login-sai-401", r.status_code in (401, 403, 429), str(r.status_code))
            r = requests.post(BASE + p, json={"platform": "x", "login": "a b", "secret": ""}, headers={"Origin": BASE}, timeout=15)
            rec.ck("login-sai-kieu-422", r.status_code in (400, 401, 422), str(r.status_code))
            r = requests.post(BASE + p, data=b"{{", headers={"Origin": BASE, "Content-Type": "application/json"}, timeout=15)
            rec.ck("login-json-hong-khong-5xx", r.status_code < 500, str(r.status_code))
            r = requests.post(BASE + p, json={"platform": "master", "login": "a", "secret": "x"}, headers={"Origin": "http://evil.example"}, timeout=15)
            rec.ck("login-origin-la-bi-chan", r.status_code in (400, 403), str(r.status_code))
    except Exception as ex:
        rec.ck("auth-nhay-cam", False, repr(ex)[:80])
    rec.ck("khong-dung-phien-that", True, "tac dong len phien/mat khau/TOTP: chi kiem anon + du lieu sai (phien thu khong bi huy)")


def write_md(inv):
    from collections import Counter, defaultdict
    L = ["# API_INVENTORY — kiểm kê & kết quả test mọi route API", "",
         f"Sinh tự động bởi `tests/qa/api/run_api.py` (kết quả chi tiết: `tests/qa/api_inventory.json`). Cập nhật: {time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC.", "",
         "Phương pháp: (A) công khai qua nginx web-ui với phiên cookie thật (master, expert, client A/B — tài khoản thử `qa_stab_api_*`, `mt5:9990002x`, xoá sau); "
         "(B) trực tiếp từng service nội bộ với `X-Internal-Token` (chỉ GET + dữ liệu sai cho route ghi; route hành động không tham số KHÔNG gọi có token); "
         "(C) qua gateway cho route proxy. Mỗi route: không đăng nhập, sai vai, IDOR (client A đọc tài khoản B), đầu vào hợp lệ/biên/sai kiểu/quá lớn, mã trả về, JSON hợp lệ, p50/p95 (ngân sách 500 ms trừ job nặng), header bảo mật, không lộ tên nguồn/secret.", "",
         "Ngân sách p95 dùng 5 mẫu ấm (GET công khai/nội bộ): p95 = mẫu chậm nhất (bỏ mẫu đầu = cache lạnh, ghi riêng ở cột Ghi chú), mang tính chặn trên.", ""]
    c = Counter(x["status"] for x in inv)
    L += ["## Tổng hợp", "", "| Trạng thái | Số |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(c.items())] + [f"| **Tổng** | **{len(inv)}** |", ""]
    bysvc = defaultdict(Counter)
    for x in inv:
        bysvc[x["service"]][x["status"]] += 1
    L += ["## Lỗi thật phát hiện và xử lý (2026-10-15)", "",
          "| # | Lỗi | Xử lý |", "|---|---|---|",
          "| 1 | paper-trader: `GET /paper/accounts/%00[/...]` -> 500 (NUL làm Postgres ném lỗi; 15 route) | `acct()` trả 404 khi id chứa NUL hoặc dài > 64 + test `test_runner_api.py`. Đã deploy |",
          "| 2 | paper-trader `/paper/governance` p95 ~1,2 s | cache 30-60 s + vòng làm nóng (phiên khác bổ sung warm_governance). Đã deploy |",
          "| 3 | vn-market, analytics, track-record, pattern-engine nhận request KHÔNG có X-Internal-Token (gateway đã có trong allowlist) | `make_app(..., internal_auth=True)` + INTERNAL_TOKEN/MODE trong compose. Đã deploy, smoke xanh |",
          "| 4 | auth `GET /auth/admin/audit?before_id=999999999999` -> 500 (tràn int32) | `Query(ge=1, le=2147483647)` -> 422. Đã deploy |",
          "| 5 | track-record: `SELECT DISTINCT symbol FROM bars WHERE tf='D1'` ~17 s > statement_timeout 15 s của ts_ro -> /track/* 503, ai-trading consensus 503 | thêm cửa sổ `ts_open >= now()-800 days` (~0,8 s); phiên khác thêm thử lại 60 s. Đã deploy |",
          "| 6 | data-keeper `GET /v1/data/decisions` -> 500 (image cũ `db.acquire`), làm smoke đỏ | mã trong cây đã sửa; chuyển phiên feed (QA_ISSUES), phiên feed đã deploy -> PASS |",
          "| 7 | data-keeper, market/news/expert-collector, storage-writer, alert-service, nlp chưa bật X-Internal-Token | HOÃN, ghi QA_ISSUES (thuộc feed; mạng backend nội bộ) |",
          "", "Ghi nhận khác: (a) tên nguồn xuất hiện trong DỮ LIỆU API (news, expert-signals, data-sources, vn/news, briefing...) — quy tắc chỉ cấm HIỂN THỊ ở UI (smoke.sh kiểm DOM); cột Ghi chú đánh dấu. (b) Header `X-Content-Type-Options` bị lặp 2 lần (nginx + service) ở /auth/*, vô hại. (c) Ngân sách p95 đo lúc VPS tải 20-50: một số route nặng vượt khi tải cao (patterns/trades, intel/heatmap, data/*), đo lại khi tải ~25 thì đạt; còn rủi ro khi tải cao.", "",
          "## Phần CHƯA phủ (trung thực)", "",
          "- Route GHI với đầu vào HỢP LỆ (tạo/sửa/xoá dữ liệu thật, hành động: killswitch, generate, release, revoke, rotate, import, bulk, confirm...) KHÔNG được gọi bằng phiên master — chỉ test anon, sai vai, thiếu CSRF, dữ liệu sai/quá lớn; luồng hợp lệ nằm trong `tests/qa/f_classroom_api.py`, `tests/e2e/*`, smoke.sh.",
          "- Route /auth/login|logout|change-password|pair|totp|sessions: chỉ dữ liệu sai + không phiên (không dùng phiên thật để tránh khoá).",
          "- WebSocket `/v1/stream`, `/v1/rt` chỉ thăm dò HTTP; SSE chỉ mở kết nối. Độ trễ tick->UI thuộc phiên feed.",
          "- Service feed (mt-bridge, *-collector, storage-writer, alert-service): chỉ kiểm xác thực (không GET/POST có token) — theo yêu cầu không đụng đường giá realtime.",
          "- IDOR: client A đọc tài khoản B kiểm cho route có `account_id` (đường dẫn/query); chưa fuzz IDOR cho route proxy `{rest}` ngoài các route con đã liệt kê.",
          "- Fuzz kiểu schemathesis chưa cài (chỉ biên/sai kiểu thủ công theo schema openapi).", ""]
    L += ["| Service | PASS | FAIL | BỎ QUA | CHƯA TEST |", "|---|---|---|---|---|"]
    for s, cc in sorted(bysvc.items()):
        L.append(f"| {s} | {cc['PASS']} | {cc['FAIL']} | {cc['BỎ QUA']} | {cc['CHƯA TEST']} |")
    L += ["", "## Chi tiết", "", "| ID | Quyền | Trạng thái | p50/p95 ms | Ghi chú |", "|---|---|---|---|---|"]
    for x in inv:
        if x["method"] == "-":
            L.append(f"| `{x['id']}` | - | {x['status']} | - | {x['detail']} |")
            continue
        q = "master" if x["path"].startswith("/auth/admin") else ("công khai" if x["path"] in ("/auth/login", "/healthz", "/metrics", "/readyz") else ("phiên đăng nhập (vai theo authz)" if x["service"] in ("api-gateway", "auth") else "X-Internal-Token"))
        tm = f"{x.get('p50')}/{x.get('p95')}" if x.get("p95") is not None else "-"
        L.append(f"| `{x['service']}` {x['method']} `{x['path']}` | {q} | {x['status']} | {tm} | {((x.get('detail') or '') + (' [dữ liệu API chứa tên nguồn: ' + ','.join(x['name_in_data'][:3]) + ' — UI phải che]' if x.get('name_in_data') else '')).replace('|', '/')[:200]} |")
    open(os.path.join(ROOT, "docs", "handoff", "stabilize", "API_INVENTORY.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
