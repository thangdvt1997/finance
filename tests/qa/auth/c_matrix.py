"""QA nhom C: ma tran route x vai + chuyen gia chi thay phong duoc moi + phien/vai co ban qua nginx that.
Chay: sh tests/qa/c_run.sh tests/qa/auth/c_matrix.py     (tai khoan thu: login_key 'master:qa_stab_<run>*', xoa het o cuoi; phong lop hoc tieu de 'qa_stab_<run>' -> xoa bang c_cleanup_rooms.sh)
Khong dat lenh; khong in bi mat; master chi GET."""
import asyncio
import importlib.util
import re
import sys
import types

import httpx

sys.path.insert(0, "/qa/tests/e2e")
import test_pentest_authz as P  # noqa: E402
from qalib import API_KEY, GATEWAY, Ctx, Results  # noqa: E402

R = Results("c_matrix")
RUN = P.RUN
KEY = lambda r: f"master:qa_stab_{RUN}{r}"  # noqa: E731
SKIP = re.compile(r"/(rt|stream)(/|$)|/media/|/backtest/|/pdf$|/html$|/minutes\.md$|/export|/download")


def load_oracle():
    """Nap authz.py cua gateway (stub fastapi) de co 'oracle' chinh sach."""
    fa = types.ModuleType("fastapi")
    fa.HTTPException = type("HTTPException", (Exception,), {"__init__": lambda s, c, d=None: None})
    fa.Request = object
    sys.modules["fastapi"] = fa
    src = open("/qa/services/api-gateway/src/api_gateway/authz.py", encoding="utf-8").read()
    m = types.ModuleType("authz_oracle")
    sys.modules["authz_oracle"] = m
    m.__name__ = "authz_oracle"
    exec(compile(src, "authz.py", "exec"), m.__dict__)  # noqa: S102
    return m


def fill(path: str) -> str:
    def rep(m):
        n = m.group(1).lower()
        if "rid" in n or "room" in n:
            return "0" * 32
        if "account" in n:
            return "mt5:99999999"
        if n in ("date", "day"):
            return "2026-01-01"
        return "x0"
    return re.sub(r"\{([^}]+)\}", rep, path)


async def main():
    ora = load_oracle()
    async with Ctx() as c, httpx.AsyncClient(timeout=30, follow_redirects=False) as H:
        P.H = H
        db = c.db
        try:
            await run(ora, db, H)
        finally:
            await db.execute("delete from portal_users where login_key like $1", f"master:qa_stab_{RUN}%")
            await db.execute("delete from mt_accounts where account_id = $1", f"mt5:{9990000000 + int(RUN, 16)}")
    return R.finish()


async def run(ora, db, H):
    # ---- tai khoan thu (vai) + phien
    U, S = {}, {}
    for role in ("master", "support", "analyst", "auditor", "expert", "client"):
        U[role] = await P.mk_user(db, role, KEY("-" + role))
        S[role] = await P.mk_sess(db, U[role])
    U["expert2"] = await P.mk_user(db, "expert", KEY("-expert2"))
    S["expert2"] = await P.mk_sess(db, U["expert2"])
    S["none"] = None

    # ---- danh sach route tu openapi cua gateway
    r = await H.get(GATEWAY + "/openapi.json", headers={"X-API-Key": API_KEY})
    routes = []
    if r.status_code == 200:
        for p, ops in r.json().get("paths", {}).items():
            for m in ops:
                if m.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    routes.append((m.upper(), p))
    R.check("matrix/openapi-co-route", len(routes) > 50, f"{len(routes)} route", "medium")
    # them route khong nam trong schema (include_in_schema=False)
    for m, p in (("GET", "/v1/rt/stats"), ("POST", "/v1/rt/kick"), ("GET", "/v1/me"), ("GET", "/v1/user/csrf")):
        if (m, p) not in routes:
            routes.append((m, p))
    R.info("matrix/routes", f"{len(routes)} (method,path)")

    # ---- 1. khong key -> gateway tu choi moi route /v1
    bad = []
    for m, p in routes[:400]:
        rr = await H.request(m, GATEWAY + fill(p), headers={})
        if rr.status_code not in (401, 403, 404, 405) and p not in ("/healthz", "/readyz", "/metrics"):   # ops: mang noi bo, khong qua nginx
            bad.append(f"{m} {p}:{rr.status_code}")
    R.check("matrix/gateway-thieu-key-moi-route-bi-tu-choi", not bad, f"{len(bad)} sai: {bad[:5]}", "critical")

    # ---- 2. qua nginx: chua dang nhap
    bad = []
    for m, p in routes:
        if SKIP.search(p):
            continue
        kw = dict(origin=True)
        rr = await P.call(P.WS_, m, fill(p), None, body={} if m != "GET" else None, **kw)
        if rr.status_code not in (401, 403, 404, 405, 302):
            bad.append(f"{m} {p}:{rr.status_code}")
    R.check("matrix/nginx-khong-dang-nhap-moi-route-bi-tu-choi", not bad, f"{len(bad)} sai: {bad[:6]}", "critical")

    # ---- 3. ma tran vai (qua nginx) doi chieu oracle
    leaks, mism, allowed_stats = [], [], {}
    for role in ("client", "support", "analyst", "auditor", "expert"):
        n_allowed = 0
        for m, p in routes:
            if SKIP.search(p):
                continue
            path = fill(p)
            if role == "client":
                ok = ora.client_path_allowed(m, path)
            else:
                ok = ora.staff_path_allowed(role, m, path)
            if ok and m != "GET":
                continue    # khong goi route ghi duoc phep (tranh tac dung phu)
            rr = await P.call(P.WS_, m, path, S[role], body={} if m != "GET" else None)
            st = rr.status_code
            if not ok:
                if st not in P.DENY:
                    leaks.append(f"{role} {m} {p}:{st}")
            else:
                n_allowed += 1
                if st in (401, 403) and not re.search(r"account|equity-history|journal", p):   # route theo tai khoan: placeholder khong thuoc vai -> 403 la dung
                    mism.append(f"{role} {m} {p}:{st}")
        allowed_stats[role] = n_allowed
    R.check("matrix/vai-khong-duoc-phep-thi-bi-tu-choi", not leaks, f"{len(leaks)}: {leaks[:8]}", "critical")
    R.check("matrix/vai-duoc-phep-khong-bi-chan-nham", not mism, f"{len(mism)}: {mism[:8]}", "low")
    R.info("matrix/so-route-GET-duoc-phep", str(allowed_stats))

    # ---- 4. master: GET khong bi 401/403
    bad = []
    for m, p in routes:
        if m != "GET" or SKIP.search(p) or p in ("/v1/rt/stats",):
            continue
        rr = await P.call(P.WS_, "GET", fill(p), S["master"])
        if rr.status_code in (401, 403):
            bad.append(f"{p}:{rr.status_code}")
    R.check("matrix/master-GET-khong-bi-chan", not bad, f"{len(bad)}: {bad[:6]}", "medium")

    # ---- 5. chuyen gia chi thay phong duoc moi
    title = f"qa_stab_{RUN}"
    C = "/v1/ai-trading/class"
    tok = {}
    for nm in ("expert", "expert2", "master", "client", "support"):
        t = await P.call(P.WS_, "GET", "/v1/user/csrf", S[nm])
        tok[nm] = t.json().get("token", "") if t.status_code == 200 else ""
    R.check("expert/csrf-lay-duoc", bool(tok["expert"]) and bool(tok["expert2"]), f"{[bool(v) for v in tok.values()]}", "high")
    r = await P.call(P.WS_, "POST", C + "/rooms", S["expert"], body={"title": title}, csrf=tok["expert"])
    rid = r.json().get("id", "") if r.status_code == 201 else ""
    R.check("expert/tao-phong", bool(rid), f"{r.status_code}", "high")
    if rid:
        ids = lambda rr: [x.get("id") for x in rr.json().get("items", [])] if rr.status_code == 200 else []  # noqa: E731
        r = await P.call(P.WS_, "GET", C + "/rooms", S["expert2"])
        R.check("expert/E2-chua-duoc-moi-khong-thay-phong-trong-danh-sach", r.status_code == 200 and rid not in ids(r), f"{r.status_code}", "critical")
        r = await P.call(P.WS_, "GET", f"{C}/rooms/{rid}", S["expert2"])
        R.check("expert/E2-doc-phong-chua-moi->404", r.status_code == 404, f"{r.status_code}", "critical")
        for sub, meth, body in (("members", "POST", {"user_id": U["expert2"], "role": "expert"}), ("pins", "POST", {"message_id": "x"}), ("messages", "POST", {"text": "xin chao"}),
                                ("profile", "GET", None), ("minutes.md", "GET", None), ("labels", "GET", None), ("actions", "GET", None), ("canvas", "GET", None)):
            r = await P.call(P.WS_, meth, f"{C}/rooms/{rid}/{sub}", S["expert2"], body=body, csrf=tok["expert2"] if meth != "GET" else None)
            R.check(f"expert/E2-{meth}-{sub}-phong-chua-moi->404", r.status_code in (403, 404), f"{r.status_code}", "critical")
        for nm in ("client", "support"):
            r = await P.call(P.WS_, "GET", C + "/rooms", S[nm])
            R.check(f"expert/{nm}-khong-vao-lop-hoc", r.status_code in P.DENY, f"{r.status_code}", "critical")
        r = await P.call(P.WS_, "GET", C + "/rooms", S["master"])
        R.check("expert/master-thay-moi-phong", r.status_code == 200 and rid in ids(r), f"{r.status_code}", "high")
        r = await P.call(P.WS_, "POST", f"{C}/rooms/{rid}/members", S["expert"], body={"user_id": U["expert2"], "name": "qa", "role": "expert"}, csrf=tok["expert"])
        R.check("expert/E1-moi-E2", r.status_code == 201, f"{r.status_code}", "high")
        r = await P.call(P.WS_, "GET", C + "/rooms", S["expert2"])
        R.check("expert/E2-sau-khi-moi-thay-phong", r.status_code == 200 and rid in ids(r), f"{r.status_code}", "high")
        r = await P.call(P.WS_, "POST", f"{C}/rooms/{rid}/members", S["expert"], body={"user_id": U["expert2"], "role": "master"}, csrf=tok["expert"])
        R.check("expert/E1-khong-the-cap-vai-master", r.status_code in P.DENY, f"{r.status_code}", "critical")
        # CSRF/Origin tren ghi lop hoc
        r = await P.call(P.WS_, "POST", C + "/rooms", S["expert"], body={"title": title + "x"})
        R.check("expert/tao-phong-thieu-csrf->403", r.status_code == 403, f"{r.status_code}", "high")
        r = await P.call(P.WS_, "POST", C + "/rooms", S["expert"], body={"title": title + "x"}, csrf=tok["expert"], origin="http://evil.example")
        R.check("expert/tao-phong-origin-la->403", r.status_code == 403, f"{r.status_code}", "high")
        r = await P.call(P.WS_, "POST", C + "/rooms", S["expert"], body={"title": title + "x"}, csrf=tok["expert"], origin=False)
        R.check("expert/tao-phong-khong-origin->403", r.status_code == 403, f"{r.status_code}", "high")
        r = await P.call(P.WS_, "POST", C + "/rooms", S["expert"], body={"title": title + "x"}, csrf=tok["expert2"])
        R.check("expert/tao-phong-csrf-cua-phien-khac->403", r.status_code == 403, f"{r.status_code}", "high")

    # ---- 6. phien: het han / thu hoi / dang xuat
    uid = U["client"]
    for nm, kw in (("het-han", dict(ttl=P.timedelta(seconds=-5))), ("thu-hoi", dict(revoked=True)), ("nhan-roi-3-ngay", dict(last=P.timedelta(days=3)))):
        sid = await P.mk_sess(db, uid, **kw)
        r = await P.call(P.WS_, "GET", "/v1/me", sid)
        R.check(f"phien/{nm}->401", r.status_code == 401, f"{r.status_code}", "critical")
    r = await P.call(P.WS_, "GET", "/v1/me", S["support"])
    R.check("phien/support-me", r.status_code == 200 and r.json().get("role") == "support", f"{r.status_code}", "high")
    sid = await P.mk_sess(db, uid)
    t = (await P.call(P.WS_, "GET", "/v1/user/csrf", sid)).json().get("token", "")
    r = await P.call(P.WS_, "POST", "/auth/logout", sid, body={}, csrf=t)
    R.check("phien/dang-xuat", r.status_code in (200, 204), f"{r.status_code}", "high")
    r = await P.call(P.WS_, "GET", "/v1/me", sid)
    R.check("phien/sau-dang-xuat-401", r.status_code == 401, f"{r.status_code}", "critical")
    # cookie gia
    r = await P.call(P.WS_, "GET", "/v1/me", "A" * 43)
    R.check("phien/cookie-gia->401", r.status_code == 401, f"{r.status_code}", "critical")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
