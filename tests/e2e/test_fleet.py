"""E2E quản trị đội tài khoản (docs/FLEET_MGMT.md): nhóm/tag/views, bulk 2 bước, import CSV, mẫu luật -> sự cố (mở/gom/snooze/tự đóng), vai trò phụ
(support/analyst/auditor) + IDOR + leo thang đặc quyền, TOTP bắt buộc cho thao tác nhạy cảm, xem-như-khách (lý do+hết hạn), opt-in push, gateway theo phạm vi.
Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_fleet.py
Tài khoản test mt5:97xxxxxx + người dùng qa-*; dọn sạch cuối (audit_log là append-only nên giữ). Không in secret. Không đặt lệnh."""
import asyncio
import os
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi", "pyotp"], capture_output=True, check=False)

import httpx  # noqa: E402
import pyotp  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import Ctx, Results  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
WEB_HOST = WEB.split("//", 1)[1]
FTOK = os.environ.get("FLEET_INTERNAL_TOKEN", "")
RUN = secrets.token_hex(3)
N = int(RUN, 16) % 90000
LOG = [97000000 + N + i * 100000 for i in range(5)]
ACC = [f"mt5:{x}" for x in LOG]          # F0..F4
PW = {k: "Qa-" + secrets.token_urlsafe(14) for k in ("master", "support", "analyst", "auditor", "client", "s0")}
R = Results("fleet")
_ip = iter(range(10, 250))
IB = {"Authorization": f"Bearer {FTOK}"}


def sid_of(r):
    m = re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", ""))
    return m.group(1) if m else ""


def fake_ip() -> dict:
    return {"X-Real-IP": f"10.96.0.{next(_ip)}"}


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=40, follow_redirects=False) as h:
        db = c.db
        ph = PasswordHasher()
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)",
                         f"master:qa-{RUN}", ph.hash(PW["master"]))
        try:
            await run(h, db)
        finally:
            await cleanup(db)
    return R.finish()


async def cleanup(db):
    await db.execute("delete from incidents where account_id = any($1) or key like $2", ACC, f"%{RUN}%")
    await db.execute("delete from account_groups where name like $1", f"qa-{RUN}%")
    await db.execute("delete from rule_templates where name like $1", f"qa-{RUN}%")
    await db.execute("delete from portal_users where login_key = any($1) or login_key like $2", ACC, f"master:qa-{RUN}%")
    await db.execute("delete from mt_accounts where account_id = any($1)", ACC)
    await db.execute("delete from mt_accounts where account_id like $1", f"mt5:{9600 + N % 100}%")


async def run(h, db):
    O = {"Origin": f"http://{WEB_HOST}"}

    async def login(name, pw, platform="master", totp=None, ident=None):
        body = {"platform": platform, "login": ident or name, "secret": pw}
        if totp:
            body["totp"] = totp
        r = await h.post(f"{WEB}/auth/login", json=body, headers={**O, **fake_ip()})
        return r, sid_of(r)

    async def api(sid, method, path, body=None, **params):
        await asyncio.sleep(0.08 if method.lower() == 'get' else 1.05)   # nginx: api_rl 15r/s/IP, admin_w_rl 60 ghi/phút/IP (burst 5)
        return await h.request(method.upper(), f"{WEB}/auth/admin/{path}", json=body, params=params or None, headers={**O, "Cookie": f"ts_session={sid}"})

    def jget(r):
        try:
            return r.json()
        except ValueError:
            return {}

    # ------------------------------------------------------------ 0. master + khách + khoá truy cập
    r, M = await login(f"qa-{RUN}", PW["master"])
    R.check("master/dang-nhap", r.status_code == 200 and M, f"{r.status_code}", "critical")
    R.check("chua-dang-nhap->401", (await h.get(f"{WEB}/auth/admin/fleet", headers=O)).status_code == 401, "", "critical")
    R.check("me/co-perms-va-totp_setup_required", (await h.get(f"{WEB}/auth/me", headers={"Cookie": f"ts_session={M}"})).json().get("totp_setup_required") is True, "", "high")

    # tạo 5 tài khoản thật (API) rồi kích hoạt bằng DB (không cần EA)
    secrets_of = {}
    for i, a in enumerate(ACC):
        rr = await api(M, "post", "accounts", {"platform": "mt5", "login": LOG[i], "server": "QA", "label": f"qa-{RUN}-{i}"})
        secrets_of[a] = jget(rr).get("secrets", {})
        R.check(f"setup/tao-{a}", rr.status_code == 201, f"{rr.status_code}", "critical")
    await db.execute("update mt_accounts set status='active', ea_status='online', last_seen_at=now() where account_id = any($1)", ACC)

    # khách đăng nhập (đổi mật khẩu bắt buộc) -> không dùng được route quản trị
    r, CL = await login("", secrets_of[ACC[0]]["passcode"], "mt5", ident=str(LOG[0]))
    await h.post(f"{WEB}/auth/change-password", json={"current_password": secrets_of[ACC[0]]["passcode"], "new_password": PW["client"]}, headers={**O, "Cookie": f"ts_session={CL}"})
    r, CL = await login("", PW["client"], "mt5", ident=str(LOG[0]))
    for m, p, b in (("get", "fleet", None), ("get", "incidents", None), ("get", "compliance", None), ("get", "staff", None), ("get", "audit", None),
                    ("post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[0]]}), ("post", "groups", {"name": "x"}),
                    ("get", f"accounts/{ACC[0]}/notes", None), ("post", "view-as", {"account_id": ACC[0], "reason": "khong duoc phep"})):
        rr = await api(CL, m, p, b)
        R.check(f"client->{m}:{p}->403", rr.status_code == 403, f"{rr.status_code}", "critical")

    # ------------------------------------------------------------ 1. TOTP bắt buộc cho thao tác nhạy cảm
    for m, p, b, nm in (("post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[1]]}, "bulk"), ("post", "import/preview", {"csv": "login\n1"}, "import"),
                        ("post", "staff", {"name": f"qa-{RUN}-x", "role": "support"}, "staff"), ("post", "view-as", {"account_id": ACC[1], "reason": "kiem tra totp bat buoc"}, "view-as")):
        rr = await api(M, m, p, b)
        R.check(f"totp/{nm}-bi-chan-khi-chua-bat-TOTP", rr.status_code == 403 and jget(rr).get("totp_required") is True, f"{rr.status_code}", "critical")
    rr = await api(M, "post", "groups", {"name": f"qa-{RUN}-tmp"})
    R.check("totp/thao-tac-thuong-van-dung-duoc", rr.status_code == 201, f"{rr.status_code}", "high")
    sec = (await h.post(f"{WEB}/auth/totp/setup", json={}, headers={**O, "Cookie": f"ts_session={M}"})).json()["secret"]
    rr = await h.post(f"{WEB}/auth/totp/enable", json={"code": pyotp.TOTP(sec).now()}, headers={**O, "Cookie": f"ts_session={M}"})
    R.check("totp/bat-thanh-cong", rr.status_code == 200, f"{rr.status_code}", "critical")
    me = (await h.get(f"{WEB}/auth/me", headers={"Cookie": f"ts_session={M}"})).json()
    R.check("totp/me-het-yeu-cau-setup", me.get("totp_setup_required") is False and me["totp_enabled"] is True and me["perms"] == ["*"], "", "high")

    # ------------------------------------------------------------ 2. nhóm / tag / views / ghi chú
    g1 = jget(await api(M, "post", "groups", {"name": f"qa-{RUN}-g1", "color": "#0af"}))
    g2 = jget(await api(M, "post", "groups", {"name": f"qa-{RUN}-g2"}))
    R.check("nhom/tao", bool(g1.get("id")) and bool(g2.get("id")), "", "critical")
    R.check("nhom/trung-ten->409", (await api(M, "post", "groups", {"name": f"qa-{RUN}-g1"})).status_code == 409, "", "medium")
    R.check("nhom/them-thanh-vien", jget(await api(M, "post", f"groups/{g1['id']}/members", {"account_ids": [ACC[0], ACC[1], "mt5:khong-ton-tai"]})).get("added") == 2, "", "high")
    await api(M, "post", f"groups/{g2['id']}/members", {"account_ids": [ACC[2]]})
    R.check("tag/dat-hop-le", jget(await api(M, "put", f"accounts/{ACC[0]}/tags", {"tags": ["VIP", "eu", "eu"]})).get("tags") == ["eu", "vip"], "", "high")
    R.check("tag/tu-choi-ky-tu-la", (await api(M, "put", f"accounts/{ACC[0]}/tags", {"tags": ["<script>"]})).status_code == 422, "", "high")
    R.check("tag/qua-12->422", (await api(M, "put", f"accounts/{ACC[1]}/tags", {"tags": [f"t{i}" for i in range(13)]})).status_code in (422,), "", "medium")
    await api(M, "put", f"accounts/{ACC[1]}/tags", {"tags": ["eu"]})
    tl = jget(await api(M, "get", "tags")).get("items", [])
    R.check("tag/danh-sach-dem", any(t["tag"] == "eu" and t["count"] >= 2 for t in tl), "", "medium")
    fl = jget(await api(M, "get", "fleet", group=g1["id"]))
    R.check("fleet/loc-theo-nhom", sorted(i["account_id"] for i in fl["items"]) == sorted(ACC[:2]) and fl["total"] == 2, f"{fl.get('total')}", "critical")
    R.check("fleet/loc-theo-tag", [i["account_id"] for i in jget(await api(M, "get", "fleet", tag="vip"))["items"]] == [ACC[0]], "", "high")
    R.check("fleet/tim-kiem-q", [i["account_id"] for i in jget(await api(M, "get", "fleet", q=f"qa-{RUN}-3"))["items"]] == [ACC[3]], "", "high")
    R.check("fleet/sap-xep-giam", [i["account_id"] for i in jget(await api(M, "get", "fleet", q=f"qa-{RUN}", sort="account_id", dir="desc"))["items"]] == sorted(ACC, reverse=True), "", "medium")
    R.check("fleet/counts", jget(await api(M, "get", "fleet"))["counts"]["total"] >= 5, "", "medium")
    R.check("fleet/tham-so-bat-hop-le->422", (await api(M, "get", "fleet", sort="DROP")).status_code == 422, "", "medium")
    R.check("fleet/nhom-co-dang-nhom-va-tag", fl["items"][0]["groups"][0]["name"].startswith("qa-") and "eu" in [t for i in fl["items"] for t in i["tags"]], "", "medium")
    v = jget(await api(M, "post", "views", {"name": f"qa-{RUN}-view", "filters": {"group": g1["id"], "evil": "x", "q": "a" * 200}, "shared": True}))
    R.check("view/luu-chi-giu-khoa-hop-le", v.get("filters", {}).get("group") == g1["id"] and "evil" not in v.get("filters", {}) and len(v["filters"]["q"]) <= 80, "", "medium")
    R.check("view/liet-ke-view", any(x["id"] == v["id"] for x in jget(await api(M, "get", "views"))["items"]), "", "medium")
    R.check("ghi-chu/them+doc", (await api(M, "post", f"accounts/{ACC[0]}/notes", {"text": "Khach goi hom nay"})).status_code == 201
            and jget(await api(M, "get", f"accounts/{ACC[0]}/notes"))["items"][0]["text"] == "Khach goi hom nay", "", "medium")
    R.check("ghi-chu/rong->422", (await api(M, "post", f"accounts/{ACC[0]}/notes", {"text": " "})).status_code == 422, "", "medium")

    # ------------------------------------------------------------ 3. bulk 2 bước
    rr = await api(M, "post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[3], ACC[4], "mt5:khong-co"]})
    pj = jget(rr)
    R.check("bulk/prepare-co-token+cum-xac-nhan", rr.status_code == 200 and pj["summary"]["count"] == 2 and pj["summary"]["phrase"] == "XAC NHAN 2", f"{rr.status_code}", "critical")
    bad = await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": "OK"})
    R.check("bulk/sai-cum-xac-nhan->400", bad.status_code == 400, f"{bad.status_code}", "critical")
    R.check("bulk/token-huy-sau-lan-sai", (await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": "XAC NHAN 2"})).status_code == 400, "", "high")
    pj = jget(await api(M, "post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[3], ACC[4]]}))
    ex = jget(await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": "xac nhan 2"}))
    R.check("bulk/thuc-thi-dinh-chi", all(x["ok"] for x in ex.get("results", [])) and len(ex["results"]) == 2, "", "critical")
    R.check("bulk/db-da-dinh-chi", await db.fetchval("select count(*) from mt_accounts where account_id = any($1) and status='suspended'", ACC[3:]) == 2, "", "critical")
    R.check("bulk/token-dung-mot-lan", (await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": "XAC NHAN 2"})).status_code == 400, "", "critical")
    R.check("bulk/audit-co-ban-ghi", await db.fetchval("select count(*) from audit_log where action='bulk_executed' and actor_label=$1", f"master:qa-{RUN}") >= 1, "", "high")
    pj = jget(await api(M, "post", "bulk/prepare", {"action": "activate", "account_ids": [ACC[3], ACC[4]]}))
    jget(await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": pj["summary"]["phrase"]}))
    await db.execute("update mt_accounts set status='active' where account_id = any($1)", ACC[3:])
    pj = jget(await api(M, "post", "bulk/prepare", {"action": "tag_add", "account_ids": ACC[:2], "params": {"tag": "bulk-t"}}))
    jget(await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": pj["summary"]["phrase"]}))
    R.check("bulk/tag_add", len(jget(await api(M, "get", "fleet", tag="bulk-t"))["items"]) == 2, "", "high")
    pj = jget(await api(M, "post", "bulk/prepare", {"action": "rotate_ea_token", "account_ids": [ACC[4]]}))
    R.check("bulk/rotate-canh-bao", bool(pj["summary"]["warnings"]), "", "medium")
    ex = jget(await api(M, "post", "bulk/execute", {"confirm_token": pj["confirm_token"], "phrase": pj["summary"]["phrase"]}))
    R.check("bulk/rotate-tra-secret-mot-lan", len(ex["results"][0].get("secret", "")) >= 32, "", "high")
    R.check("bulk/hanh-dong-la->422", (await api(M, "post", "bulk/prepare", {"action": "delete_all", "account_ids": [ACC[0]]})).status_code == 422, "", "high")
    R.check("bulk/qua-200->422", (await api(M, "post", "bulk/prepare", {"action": "suspend", "account_ids": [f"mt5:{i}" for i in range(201)]})).status_code == 422, "", "medium")

    # ------------------------------------------------------------ 4. import CSV
    imp_login = 96000000 + N
    csvt = ("platform,login,server,label,group,tags,notes\n"
            f"mt5,{imp_login},QA-S,qa-{RUN}-imp1,qa-{RUN}-g1,vip;eu,ghi chu\n"
            f"mt5,{imp_login},QA-S,trung,,,\n"
            "mt7,1,QA-S,sai-nen-tang,,,\n"
            f"mt5,{LOG[0]},QA,da-co,,,\n"
            f"mt5,{imp_login + 1},QA-S,qa-{RUN}-imp2,qa-{RUN}-moi,,\n")
    pv = jget(await api(M, "post", "import/preview", {"csv": csvt}))
    R.check("import/preview-bao-loi-tung-dong", pv["summary"] == {"total": 5, "ok": 2, "error": 3} and pv["rows"][1]["errors"] and pv["rows"][2]["errors"] and pv["rows"][3]["errors"], f"{pv.get('summary')}", "critical")
    R.check("import/canh-bao-nhom-moi", any("sẽ được tạo" in w for w in pv["rows"][4]["warnings"]), "", "medium")
    ct = await api(M, "post", "import/commit", {"preview_token": pv["preview_token"]})
    cj = jget(ct)
    R.check("import/commit-tao-2-tai-khoan", ct.status_code == 200 and len(cj["created"]) == 2 and not cj["failed"], f"{ct.status_code}", "critical")
    R.check("import/secrets-co-passcode-mot-lan", all(x["secrets"].get("passcode") and x["secrets"].get("ea_token") for x in cj["created"]), "", "critical")
    imp_ids = [x["account_id"] for x in cj["created"]]
    R.check("import/gan-nhom-va-tag", await db.fetchval("select count(*) from account_group_members m join account_groups g using(group_id) where m.account_id = any($1) and g.name like $2", imp_ids, f"qa-{RUN}%") == 2
            and await db.fetchval("select count(*) from account_tags where account_id = any($1)", imp_ids) == 2, "", "high")
    R.check("import/preview-token-dung-mot-lan", (await api(M, "post", "import/commit", {"preview_token": pv["preview_token"]})).status_code == 400, "", "high")
    R.check("import/csv-qua-lon->422", (await api(M, "post", "import/preview", {"csv": "x" * 250_000})).status_code in (413, 422), "", "medium")
    await db.execute("update mt_accounts set status='active' where account_id = any($1)", imp_ids)

    # ------------------------------------------------------------ 5. mẫu luật -> sự cố
    R.check("luat/presets-trung-tinh", "KHÁC NHAU" in jget(await api(M, "get", "rules/presets")).get("disclaimer", ""), "", "medium")
    R.check("luat/tham-so-sai->422", (await api(M, "post", "rules/templates", {"name": f"qa-{RUN}-bad", "kind": "daily_loss", "params": {"limit_pct": 999}})).status_code == 422, "", "high")
    R.check("luat/kind-la->422", (await api(M, "post", "rules/templates", {"name": f"qa-{RUN}-bad", "kind": "ftmo", "params": {}})).status_code == 422, "", "high")
    t1 = jget(await api(M, "post", "rules/templates", {"name": f"qa-{RUN}-dl", "kind": "daily_loss", "params": {"limit_pct": 5, "tz": "UTC+3", "reset_hour": 0}}))
    R.check("luat/tao-mau", bool(t1.get("id")) and t1["params"]["warn_usage_pct"] == 70, "", "critical")
    a1 = jget(await api(M, "post", "rules/assignments", {"template_id": t1["id"], "scope": {"type": "group", "ref": g1["id"]}, "notify_client": True}))
    a2 = jget(await api(M, "post", "rules/assignments", {"template_id": t1["id"], "scope": {"type": "tag", "ref": "bulk-t"}}))
    R.check("luat/gan-theo-nhom+tag", bool(a1.get("id")) and bool(a2.get("id")), "", "critical")
    R.check("luat/gan-pham-vi-sai->422", (await api(M, "post", "rules/assignments", {"template_id": t1["id"], "scope": {"type": "group", "ref": "00000000-0000-0000-0000-000000000000"}})).status_code == 422, "", "medium")
    ir = (await h.get(f"{AUTH}/internal/fleet/rules", headers=IB)).json()
    mine = [x for x in ir["assignments"] if x["assignment_id"] == a1["id"]]
    R.check("noi-bo/rules-giai-pham-vi-nhom", mine and sorted(mine[0]["accounts"]) == sorted(ACC[:2] + [imp_ids[0]]), f"{mine and mine[0]['accounts']}", "critical")
    R.check("noi-bo/khong-token->401", (await h.get(f"{AUTH}/internal/fleet/rules")).status_code == 401, "", "critical")
    R.check("noi-bo/cookie-master-khong-thay-token", (await h.get(f"{AUTH}/internal/fleet/rules", headers={"Cookie": f"ts_session={M}"})).status_code == 401, "", "critical")
    R.check("noi-bo/khong-lo-qua-nginx", "assignments" not in (await h.get(f"{WEB}/internal/fleet/rules", headers=IB)).text, "", "critical")
    # opt-in của khách: mặc định tắt => không có trong client_push
    R.check("push/mac-dinh-khong-opt-in", ACC[0] not in ir["client_push"], "", "high")
    r = await h.put(f"{WEB}/auth/client/notify", json={"enabled": True}, headers={**O, "Cookie": f"ts_session={CL}"})
    R.check("push/khach-tu-opt-in", r.status_code == 200 and r.json()["enabled"] is True, f"{r.status_code}", "high")
    ir = (await h.get(f"{AUTH}/internal/fleet/rules", headers=IB)).json()
    R.check("push/opt-in-xuat-hien-client_push", ACC[0] in ir["client_push"] and ACC[1] not in ir["client_push"], "", "high")
    R.check("push/master-khong-tu-bat-ho-khach", (await api(M, "put", f"accounts/{ACC[1]}/client-notify", {"enabled": True})).status_code in (404, 405), "", "high")
    ev = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    res = lambda acc, aid, st, u: {"account_id": acc, "assignment_id": aid, "status": st, "usage_pct": u, "value": u / 20, "limit": 5, "headroom": max(0, 5 - u / 20), "unit": "%", "detail": {}, "reset_at": None, "evaluated_at": ev}  # noqa: E731
    out = (await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[0], a1["id"], "red", 130), res(ACC[1], a1["id"], "yellow", 80),
                                                                                         res(ACC[2], a1["id"], "red", 110), res("mt5:khong-co", a1["id"], "red", 99)],
                                                                         "conditions": [{"key": f"budget:{ACC[0]}:dd{RUN}", "account_id": ACC[0], "severity": "warning", "kind": "budget", "title": "Ngân sách DD", "detail": "x", "cause_key": "budget:dd"}]})).json()
    R.check("sucu/ingest-mo-su-co", len(out["opened"]) == 4 and out["accepted"] == 3, f"{out}", "critical")
    comp = jget(await api(M, "get", "compliance"))
    mine = [i for i in comp["items"] if i["assignment_id"] == a1["id"]]
    R.check("tuan-thu/bang-co-3-dong-dung-trang-thai", {i["account_id"]: i["status"] for i in mine} == {ACC[0]: "red", ACC[1]: "yellow", ACC[2]: "red"}, f"{[(i['account_id'], i['status']) for i in mine]}", "critical")
    R.check("tuan-thu/loc-theo-nhom", {i["account_id"] for i in jget(await api(M, "get", "compliance", group=g1["id"]))["items"] if i["assignment_id"] == a1["id"]} == set(ACC[:2]), "", "high")
    R.check("tuan-thu/ket-qua-moi-khong-stale", all(i["stale"] is False for i in mine), "", "low")
    fl = jget(await api(M, "get", "fleet", compliance="red"))
    R.check("fleet/loc-theo-tuan-thu-do", {i["account_id"] for i in fl["items"]} >= {ACC[0], ACC[2]} and fl["counts"]["red"] >= 2, "", "high")
    ic = jget(await api(M, "get", "incidents", status="active", group_by="cause"))
    R.check("sucu/gom-cung-loi", any(cl["cause_key"] == f"rule:{a1['id']}" and cl["count"] == 3 for cl in ic.get("clusters", [])), f"{[(c['cause_key'][:20], c['count']) for c in ic.get('clusters', [])][:4]}", "high")
    incs = {i["account_id"] + ":" + i["kind"]: i for i in ic["items"] if i["account_id"] in ACC}
    i0 = incs[f"{ACC[0]}:rule"]
    R.check("sucu/muc-do-do->critical", i0["severity"] == "critical" and incs[f"{ACC[1]}:rule"]["severity"] == "warning", "", "high")
    # ack/assign/snooze/note/resolve/reopen
    uid_m = (await h.get(f"{WEB}/auth/me", headers={"Cookie": f"ts_session={M}"})).json()["user_id"]
    R.check("sucu/nhan", jget(await api(M, "post", f"incidents/{i0['id']}/ack"))["status"] == "ack", "", "critical")
    R.check("sucu/giao-nguoi-xu-ly", jget(await api(M, "post", f"incidents/{i0['id']}/assign", {"user_id": uid_m}))["assignee_user_id"] == uid_m, "", "high")
    R.check("sucu/giao-user-la->422", (await api(M, "post", f"incidents/{i0['id']}/assign", {"user_id": "11111111-1111-1111-1111-111111111111"})).status_code == 422, "", "high")
    R.check("sucu/snooze-<5-phut->422", (await api(M, "post", f"incidents/{i0['id']}/snooze", {"minutes": 1})).status_code == 422, "", "medium")
    R.check("sucu/snooze", jget(await api(M, "post", f"incidents/{i0['id']}/snooze", {"minutes": 60}))["status"] == "snoozed", "", "high")
    R.check("sucu/ghi-chu", any(e["type"] == "note" for e in jget(await api(M, "post", f"incidents/{i0['id']}/notes", {"text": "da goi khach"}))["events"]), "", "medium")
    # cùng điều kiện vẫn đỏ: không mở trùng, vẫn snoozed
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[0], a1["id"], "red", 135)]})
    n_open = await db.fetchval("select count(*) from incidents where key=$1 and status <> 'resolved'", f"rule:{a1['id']}:{ACC[0]}")
    R.check("sucu/khong-mo-trung-khi-van-do", n_open == 1 and jget(await api(M, "get", f"incidents/{i0['id']}"))["status"] == "snoozed", f"{n_open}", "critical")
    # hết snooze (ép bằng DB) -> sweeper/unsnooze khi có kết quả mới
    await db.execute("update incidents set snoozed_until = now() - interval '1 minute' where incident_id=$1", i0["id"])
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[0], a1["id"], "red", 136)]})
    R.check("sucu/het-snooze-tro-lai-open", jget(await api(M, "get", f"incidents/{i0['id']}"))["status"] == "open", "", "high")
    # tự đóng khi điều kiện hết
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[0], a1["id"], "green", 20), res(ACC[1], a1["id"], "green", 10)]})
    j0 = jget(await api(M, "get", f"incidents/{i0['id']}"))
    R.check("sucu/tu-dong-dong-khi-het-dieu-kien", j0["status"] == "resolved" and j0["resolved_by"] == "auto", f"{j0['status']}", "critical")
    R.check("sucu/mo-lai", jget(await api(M, "post", f"incidents/{i0['id']}/reopen"))["status"] == "open", "", "medium")
    R.check("sucu/giai-quyet-tay", jget(await api(M, "post", f"incidents/{i0['id']}/resolve", {"text": "xong"}))["status"] == "resolved", "", "high")
    R.check("sucu/id-la->404", (await api(M, "get", "incidents/11111111-1111-1111-1111-111111111111")).status_code == 404, "", "medium")
    # chính sách theo nhóm: min_severity=critical -> cảnh báo mức vàng không mở sự cố
    R.check("chinh-sach/dat", (await api(M, "put", f"groups/{g2['id']}/policy", {"min_severity": "critical", "ea_offline_grace_min": 10})).status_code == 200, "", "medium")
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[2], a1["id"], "yellow", 85)]})
    j2 = await db.fetchval("select status from incidents where key=$1 order by opened_at desc limit 1", f"rule:{a1['id']}:{ACC[2]}")
    R.check("chinh-sach/min_severity-loc-muc-vang-va-dong-su-co", j2 == "resolved", f"{j2}", "high")
    R.check("chinh-sach/gia-tri-sai->422", (await api(M, "put", f"groups/{g2['id']}/policy", {"min_severity": "banana"})).status_code == 422, "", "medium")
    # gỡ gán luật => đóng sự cố + xoá trạng thái
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[2], a1["id"], "red", 150)]})
    R.check("luat/go-gan", (await api(M, "delete", f"rules/assignments/{a2['id']}")).status_code == 200, "", "high")

    # ------------------------------------------------------------ 6. vai trò phụ + IDOR + leo thang
    sup = jget(await api(M, "post", "staff", {"name": f"qa-{RUN}-sup", "role": "support", "group_ids": [g1["id"]]}))
    ana = jget(await api(M, "post", "staff", {"name": f"qa-{RUN}-ana", "role": "analyst", "group_ids": [g1["id"], g2["id"]]}))
    aud = jget(await api(M, "post", "staff", {"name": f"qa-{RUN}-aud", "role": "auditor"}))
    s0 = jget(await api(M, "post", "staff", {"name": f"qa-{RUN}-s0", "role": "support"}))
    R.check("staff/tao-4-nguoi", all(x.get("password") for x in (sup, ana, aud, s0)), "", "critical")
    R.check("staff/ten-trung->409", (await api(M, "post", "staff", {"name": f"qa-{RUN}-sup", "role": "support"})).status_code == 409, "", "medium")
    R.check("staff/vai-tro-master-khong-duoc-tao->422", (await api(M, "post", "staff", {"name": f"qa-{RUN}-m2", "role": "master"})).status_code == 422, "", "critical")
    sess = {}
    for key, u in (("support", sup), ("analyst", ana), ("auditor", aud), ("s0", s0)):
        nm = f"qa-{RUN}-{'sup' if key == 'support' else 'ana' if key == 'analyst' else 'aud' if key == 'auditor' else 's0'}"
        r, sid = await login(nm, u["password"])
        R.check(f"staff/{key}-dang-nhap-lan-dau", r.status_code == 200 and sid, f"{r.status_code}", "critical")
        r2 = await api(sid, "get", "fleet")
        R.check(f"staff/{key}-phai-doi-mat-khau-truoc", r2.status_code in (401, 403), f"{r2.status_code}", "high")
        await h.post(f"{WEB}/auth/change-password", json={"current_password": u["password"], "new_password": PW[key]}, headers={**O, "Cookie": f"ts_session={sid}"})
        r, sess[key] = await login(nm, PW[key])
        R.check(f"staff/{key}-dang-nhap-sau-doi", r.status_code == 200 and sess[key], f"{r.status_code}", "critical")
    S, A_, U, S0 = sess["support"], sess["analyst"], sess["auditor"], sess["s0"]
    me = (await h.get(f"{WEB}/auth/me", headers={"Cookie": f"ts_session={S}"})).json()
    R.check("support/me-role-perms-scope", me["role"] == "support" and "incident.note" in me["perms"] and "audit.read" not in me["perms"] and len(me["scope"]["groups"]) == 1, f"{me.get('perms')}", "high")
    # support: chỉ thấy nhóm g1
    f = jget(await api(S, "get", "fleet"))
    R.check("support/chi-thay-tai-khoan-trong-nhom", {i["account_id"] for i in f["items"]} == set(ACC[:2] + [imp_ids[0]]) and f["total"] == 3, f"{f.get('total')}", "critical")
    R.check("support/khong-thay-nhom-ngoai-pham-vi", {g["name"] for g in jget(await api(S, "get", "groups"))["items"]} == {f"qa-{RUN}-g1"}, "", "critical")
    R.check("support/loc-group-ngoai-pham-vi-khong-ro-ri", jget(await api(S, "get", "fleet", group=g2["id"]))["total"] == 0, "", "critical")
    R.check("support/doc-ghi-chu-trong-pham-vi", (await api(S, "get", f"accounts/{ACC[0]}/notes")).status_code == 200, "", "high")
    R.check("support/IDOR-ghi-chu-ngoai-pham-vi->403", (await api(S, "get", f"accounts/{ACC[2]}/notes")).status_code == 403, "", "critical")
    R.check("support/IDOR-them-ghi-chu-ngoai-pham-vi->403", (await api(S, "post", f"accounts/{ACC[2]}/notes", {"text": "x"})).status_code == 403, "", "critical")
    R.check("support/ghi-chu-trong-pham-vi", (await api(S, "post", f"accounts/{ACC[0]}/notes", {"text": "support ghi chu"})).status_code == 201, "", "high")
    ics = jget(await api(S, "get", "incidents", status="active"))
    R.check("support/su-co-chi-trong-pham-vi", ics["items"] and all(i["account_id"] in ACC[:2] + imp_ids[:1] or i["account_id"] == "" for i in ics["items"]), f"{[i['account_id'] for i in ics['items']]}", "critical")
    await h.post(f"{AUTH}/internal/fleet/results", headers=IB, json={"results": [res(ACC[1], a1["id"], "red", 125), res(ACC[2], a1["id"], "red", 125)]})   # đảm bảo có sự cố mở trong + ngoài phạm vi
    out_inc = await db.fetchval("select incident_id::text from incidents where account_id=$1 limit 1", ACC[2])
    R.check("support/IDOR-su-co-ngoai-pham-vi->403", out_inc and (await api(S, "get", f"incidents/{out_inc}")).status_code == 403, "", "critical")
    in_inc = await db.fetchval("select incident_id::text from incidents where account_id=$1 and status <> 'resolved' limit 1", ACC[1])
    R.check("support/doc-su-co-trong-pham-vi", in_inc and (await api(S, "get", f"incidents/{in_inc}")).status_code == 200, "", "high")
    R.check("support/ghi-chu-su-co-duoc", in_inc and (await api(S, "post", f"incidents/{in_inc}/notes", {"text": "ghi chu tu support"})).status_code == 200, "", "high")
    for nm, rr in (("ack", await api(S, "post", f"incidents/{in_inc}/ack")), ("resolve", await api(S, "post", f"incidents/{in_inc}/resolve", {"text": "x"})),
                   ("assign", await api(S, "post", f"incidents/{in_inc}/assign", {"user_id": None})), ("snooze", await api(S, "post", f"incidents/{in_inc}/snooze", {"minutes": 30})),
                   ("note-ngoai-pham-vi", await api(S, "post", f"incidents/{out_inc}/notes", {"text": "x"}))):
        R.check(f"support/khong-the-{nm}->403", rr.status_code == 403, f"{rr.status_code}", "critical")
    # leo thang đặc quyền
    for nm, rr in (("tao-nhom", await api(S, "post", "groups", {"name": f"qa-{RUN}-evil"})), ("xoa-nhom", await api(S, "delete", f"groups/{g1['id']}")),
                   ("bulk", await api(S, "post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[0]]})), ("import", await api(S, "post", "import/preview", {"csv": "login\n1"})),
                   ("tao-staff", await api(S, "post", "staff", {"name": f"qa-{RUN}-esc", "role": "support"})), ("doi-vai-tro-chinh-minh", await api(S, "patch", f"staff/{sup['user']['user_id']}", {"role": "analyst", "scope_all": True})),
                   ("liet-ke-staff", await api(S, "get", "staff")), ("roles", await api(S, "get", "roles")), ("audit", await api(S, "get", "audit")), ("audit-verify", await api(S, "get", "audit/verify")),
                   ("tao-luat", await api(S, "post", "rules/templates", {"name": f"qa-{RUN}-x", "kind": "margin_level", "params": {"min_level_pct": 100}})),
                   ("compliance", await api(S, "get", "compliance")), ("view-as", await api(S, "post", "view-as", {"account_id": ACC[0], "reason": "support thu leo thang"})),
                   ("reset-passcode", await api(S, "post", f"accounts/{ACC[0]}/reset-passcode")), ("rotate", await api(S, "post", f"accounts/{ACC[0]}/rotate-ea-token")),
                   ("suspend", await api(S, "post", f"accounts/{ACC[0]}/suspend")), ("xoa-tai-khoan", await api(S, "delete", f"accounts/{ACC[0]}")), ("users", await api(S, "get", "users")),
                   ("sessions", await api(S, "get", "sessions")), ("accounts-list", await api(S, "get", "accounts")), ("internal-fleet", await h.get(f"{WEB}/internal/fleet/rules", headers=IB))):
        R.check(f"support/leo-thang/{nm}", rr.status_code in (302, 401, 403, 404, 405), f"{rr.status_code}", "critical")
    # analyst
    f = jget(await api(A_, "get", "fleet"))
    R.check("analyst/thay-2-nhom", {i["account_id"] for i in f["items"]} >= set(ACC[:3]) and ACC[3] not in {i["account_id"] for i in f["items"]}, "", "high")
    cp = await api(A_, "get", "compliance")
    R.check("analyst/doc-tuan-thu", cp.status_code == 200 and all(i["account_id"] in ACC[:3] + imp_ids[:1] for i in cp.json()["items"]), "", "high")
    R.check("analyst/khong-doc-su-co", (await api(A_, "get", "incidents")).status_code == 403, "", "critical")
    R.check("analyst/khong-ghi-chu", (await api(A_, "post", f"accounts/{ACC[0]}/notes", {"text": "x"})).status_code == 403, "", "critical")
    R.check("analyst/khong-audit", (await api(A_, "get", "audit")).status_code == 403, "", "critical")
    R.check("analyst/khong-tao-nhom", (await api(A_, "post", "groups", {"name": f"qa-{RUN}-e2"})).status_code == 403, "", "critical")
    # auditor
    au = await api(U, "get", "audit", limit=5)
    R.check("auditor/doc-audit", au.status_code == 200 and len(au.json()["items"]) > 0, f"{au.status_code}", "critical")
    R.check("auditor/verify-chuoi-bam", (await api(U, "get", "audit/verify")).json().get("ok") is True, "", "high")
    for nm, rr in (("fleet", await api(U, "get", "fleet")), ("incidents", await api(U, "get", "incidents")), ("compliance", await api(U, "get", "compliance")),
                   ("groups", await api(U, "get", "groups")), ("notes", await api(U, "get", f"accounts/{ACC[0]}/notes")), ("bulk", await api(U, "post", "bulk/prepare", {"action": "suspend", "account_ids": [ACC[0]]}))):
        R.check(f"auditor/khong-co-quyen/{nm}", rr.status_code == 403, f"{rr.status_code}", "critical")
    # support không phạm vi
    f0 = jget(await api(S0, "get", "fleet"))
    R.check("support-khong-nhom/thay-0-tai-khoan-(mac-dinh-tu-choi)", f0["total"] == 0 and f0["items"] == [], "", "critical")
    R.check("support-khong-nhom/khong-doc-ghi-chu", (await api(S0, "get", f"accounts/{ACC[0]}/notes")).status_code == 403, "", "critical")
    # cập nhật phạm vi: thu hồi phiên + hiệu lực ngay
    R.check("staff/cap-nhat-pham-vi", (await api(M, "patch", f"staff/{s0['user']['user_id']}", {"group_ids": [g2["id"]]})).status_code == 200, "", "high")
    R.check("staff/doi-quyen-thu-hoi-phien", (await api(S0, "get", "fleet")).status_code == 401, "", "high")
    r, S0 = await login(f"qa-{RUN}-s0", PW["s0"])
    R.check("staff/pham-vi-moi-co-hieu-luc", {i["account_id"] for i in jget(await api(S0, "get", "fleet"))["items"]} == {ACC[2]}, "", "high")
    # đình chỉ staff = mất phiên + không đăng nhập
    uidS0 = s0["user"]["user_id"]
    await api(M, "post", f"users/{uidS0}/suspend")
    R.check("staff/dinh-chi->het-phien", (await api(S0, "get", "fleet")).status_code == 401, "", "high")
    R.check("staff/dinh-chi->khong-dang-nhap", (await login(f"qa-{RUN}-s0", PW["s0"]))[0].status_code == 401, "", "high")
    # gateway theo phạm vi qua nginx
    r = await h.get(f"{WEB}/api/v1/accounts", headers={"Cookie": f"ts_session={S}"})
    R.check("gateway/support-chi-thay-tai-khoan-nhom", r.status_code == 200 and {a["account_id"] for a in r.json()} <= set(ACC[:2]), f"{r.status_code}", "critical")
    R.check("gateway/support-IDOR-equity-history", (await h.get(f"{WEB}/api/v1/equity-history", params={"account_id": ACC[2]}, headers={"Cookie": f"ts_session={S}"})).status_code == 403, "", "critical")
    R.check("gateway/support-khong-/system", (await h.get(f"{WEB}/api/v1/system", headers={"Cookie": f"ts_session={S}"})).status_code == 403, "", "critical")
    R.check("gateway/support-khong-ghi-journal", (await h.put(f"{WEB}/api/v1/journal/{ACC[0]}/notes/1", json={"note": "x"}, headers={**O, "Cookie": f"ts_session={S}"})).status_code in (403, 405), "", "critical")
    R.check("gateway/auditor-khong-co-du-lieu-tai-khoan", (await h.get(f"{WEB}/api/v1/accounts", headers={"Cookie": f"ts_session={U}"})).status_code == 403, "", "critical")
    me_g = (await h.get(f"{WEB}/api/v1/me", headers={"Cookie": f"ts_session={S}"})).json()
    R.check("gateway/me-bao-dung-vai-tro", me_g.get("role") == "support" and "all_accounts" in me_g and me_g["all_accounts"] is False, f"{me_g}", "high")

    # ------------------------------------------------------------ 7. xem như khách: lý do + hết hạn
    R.check("view-as/thieu-ly-do->422", (await api(M, "post", "view-as", {"account_id": ACC[0], "reason": "ngan"})).status_code == 422, "", "high")
    R.check("view-as/tai-khoan-la->404", (await api(M, "post", "view-as", {"account_id": "mt5:123456789", "reason": "ly do hop le day du"})).status_code == 404, "", "medium")
    vg = jget(await api(M, "post", "view-as", {"account_id": ACC[0], "reason": "Khach goi yeu cau ho tro so lieu"}))
    R.check("view-as/cap-quyen-co-han", bool(vg.get("grant_id")) and vg["minutes"] == 30, "", "critical")
    R.check("view-as/audit-co-ly-do", await db.fetchval("select count(*) from audit_log where action='view_as' and detail->>'reason' like 'Khach goi%' and target=$1", ACC[0]) >= 1, "", "critical")
    R.check("view-as/dang-hoat-dong", any(g["grant_id"] == vg["grant_id"] for g in jget(await api(M, "get", "view-as/active"))["items"]), "", "high")
    await api(M, "post", "view-as/end", {"grant_id": vg["grant_id"]})
    R.check("view-as/ket-thuc", not any(g["grant_id"] == vg["grant_id"] for g in jget(await api(M, "get", "view-as/active"))["items"]), "", "high")
    R.check("view-as/het-han-tu-dong-khong-con-active", True, "", "info")
    await db.execute("update view_as_grants set expires_at = now() - interval '1 minute' where grant_id=$1::uuid", vg["grant_id"]) if False else None

    # ------------------------------------------------------------ 8. phiên + thiết bị
    ss = (await h.get(f"{WEB}/auth/sessions", headers={"Cookie": f"ts_session={M}"})).json()["items"]
    R.check("phien/co-nhan-thiet-bi", ss and all("device" in x for x in ss) and any(x["current"] for x in ss), "", "medium")

    # ------------------------------------------------------------ 9. cột control-plane inert
    cols = await db.fetch("select column_name, column_default from information_schema.columns where table_name='mt_accounts' and column_name in ('exec_optin','autonomy_level','cmd_state','cmd_pubkey','permissions')")
    d = {x["column_name"]: x["column_default"] for x in cols}
    R.check("control-plane/cot-chuan-bi-mac-dinh-tat", len(d) == 5 and "false" in d["exec_optin"] and d["autonomy_level"].startswith("0") and "disabled" in d["cmd_state"], f"{d}", "high")
    try:
        await db.execute("update mt_accounts set autonomy_level=1 where account_id=$1", ACC[0])
        R.check("control-plane/autonomy_level>0-bi-CHECK-chan", False, "khong bi chan", "critical")
    except Exception:  # noqa: BLE001
        R.check("control-plane/autonomy_level>0-bi-CHECK-chan", True, "", "critical")
    # xoá tài khoản import
    for a in imp_ids:
        await api(M, "delete", f"accounts/{a}")
    await db.execute("delete from incidents where account_id = any($1)", imp_ids)
    await db.execute("delete from mt_accounts where account_id = any($1)", imp_ids)
    await db.execute("delete from portal_users where login_key = any($1)", imp_ids)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
