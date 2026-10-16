"""E2E engine luật rủi ro (risk-monitor) <-> auth: dữ liệu snapshot giả (tài khoản qa) -> mẫu luật + gán -> risk-monitor đánh giá -> rule_status/sự cố/alerts.out.
Chạy trên VPS:  sh /root/qa-e2e/run_remote.sh test_fleet_engine.py     (chờ tới ~3 chu kỳ risk-monitor). Dọn sạch cuối. READ-ONLY."""
import asyncio
import json
import os
import re
import secrets
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "argon2-cffi"], capture_output=True, check=False)

import httpx  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from qalib import Ctx, Results, wait_for  # noqa: E402

AUTH = os.getenv("QA_AUTH", "http://auth:8000")
RISK = os.getenv("QA_RISK", "http://risk-monitor:8000")
IH = {"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "")}  # gọi THẲNG service nội bộ cần X-Internal-Token (HARDENING §7)
RUN = secrets.token_hex(3)
N = int(RUN, 16) % 90000
LOGIN = 96000000 + N
ACC = f"mt5:{LOGIN}"
PW = "Qa-" + secrets.token_urlsafe(14)
R = Results("fleet_engine")


async def main():
    async with Ctx() as c, httpx.AsyncClient(timeout=30, follow_redirects=False) as h:
        db = c.db
        await db.execute("insert into portal_users (role, login_key, display_name, password_hash, must_change_password) values ('master',$1,'qa',$2,false)",
                         f"master:qa-{RUN}", PasswordHasher().hash(PW))
        try:
            await run(c, h, db)
        finally:
            await db.execute("delete from account_snapshots where account_id=$1", ACC)
            await db.execute("delete from incidents where account_id=$1", ACC)
            await db.execute("delete from rule_templates where name like $1", f"qa-{RUN}%")
            await db.execute("delete from portal_users where login_key = any($1)", [ACC, f"master:qa-{RUN}"])
            await db.execute("delete from mt_accounts where account_id=$1", ACC)
            with __import__("contextlib").suppress(Exception):
                await c.r.hdel("risk:rule_state", ACC)
    return R.finish()


async def run(c, h, db):
    r = await h.post(f"{AUTH}/auth/login", json={"platform": "master", "login": f"qa-{RUN}", "secret": PW}, headers={"X-Real-IP": f"10.95.0.{N % 200 + 10}"})
    m = re.search(r"ts_session=([^;]+)", r.headers.get("set-cookie", ""))
    ck = {"Cookie": f"ts_session={m.group(1)}"} if m else {}
    R.check("master/login", r.status_code == 200 and bool(m), f"{r.status_code}", "critical")

    def api(method, path, body=None, **p):
        return h.request(method, f"{AUTH}/auth/admin/{path}", json=body, params=p or None, headers=ck)

    rr = await api("POST", "accounts", {"platform": "mt5", "login": LOGIN, "server": "QA", "label": f"qa-{RUN}"})
    R.check("setup/tao-tai-khoan", rr.status_code == 201, f"{rr.status_code}", "critical")
    await db.execute("update mt_accounts set status='active' where account_id=$1", ACC)
    # chuỗi equity: 26 giờ qua (mỗi 30 phút) = 10000, 60 phút gần nhất = 9600 (lỗ 4%)
    await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) "
                     "select $1, 'mt5', now() - make_interval(mins => g*30), 10000, case when g <= 2 then 9600 else 10000 end, 1000, '[]'::jsonb from generate_series(0, 52) g", ACC)
    t_dl = (await api("POST", "rules/templates", {"name": f"qa-{RUN}-dl", "kind": "daily_loss", "params": {"limit_pct": 5, "tz": "UTC", "reset_hour": 0}})).json()
    t_dd = (await api("POST", "rules/templates", {"name": f"qa-{RUN}-dd", "kind": "max_drawdown", "params": {"limit_pct": 10, "mode": "static", "initial_balance": 10000}})).json()
    t_ml = (await api("POST", "rules/templates", {"name": f"qa-{RUN}-ml", "kind": "margin_level", "params": {"min_level_pct": 150}})).json()
    ids = {}
    for k, t in (("dl", t_dl), ("dd", t_dd), ("ml", t_ml)):
        a = (await api("POST", "rules/assignments", {"template_id": t["id"], "scope": {"type": "account", "ref": ACC}, "notify_client": k == "dl"})).json()
        ids[k] = a["id"]
    R.check("setup/3-luat-gan-theo-tai-khoan", len(ids) == 3 and all(ids.values()), "", "critical")

    async def rows():
        d = await db.fetch("select assignment_id::text a, status, usage_pct, headroom, evaluated_at from rule_status where account_id=$1", ACC)
        return {x["a"]: x for x in d} if len(d) == 3 else None
    got = await wait_for(rows, 200, 5)
    R.check("engine/risk-monitor-danh-gia-du-3-luat", bool(got), "chưa có rule_status sau 200s", "critical")
    if not got:
        return
    R.check("engine/daily_loss-vang-80%", got[ids["dl"]]["status"] == "yellow" and 70 <= got[ids["dl"]]["usage_pct"] <= 95, f"{got[ids['dl']]['status']} {got[ids['dl']]['usage_pct']}", "critical")
    R.check("engine/dd-tinh-xanh-40%", got[ids["dd"]]["status"] == "green" and 30 <= got[ids["dd"]]["usage_pct"] <= 50, f"{got[ids['dd']]['status']} {got[ids['dd']]['usage_pct']}", "critical")
    R.check("engine/margin_level-xanh", got[ids["ml"]]["status"] == "green", f"{got[ids['ml']]['status']}", "high")
    R.check("engine/du-dia-con-lai", got[ids["dl"]]["headroom"] is not None and got[ids["dl"]]["headroom"] > 0, "", "high")
    inc = await db.fetchrow("select severity, status, kind from incidents where key=$1 and status <> 'resolved'", f"rule:{ids['dl']}:{ACC}")
    R.check("sucu/luat-vang-mo-su-co-warning", bool(inc) and inc["severity"] == "warning" and inc["kind"] == "rule", f"{dict(inc) if inc else None}", "critical")
    R.check("sucu/luat-xanh-khong-mo-su-co", not await db.fetchval("select count(*) from incidents where key = any($1) and status <> 'resolved'", [f"rule:{ids['dd']}:{ACC}", f"rule:{ids['ml']}:{ACC}"]), "", "high")
    # alerts.out: có cảnh báo luật, KHÔNG chứa tên nguồn
    ent = await c.r.xrevrange("alerts.out", count=400)
    mine = [json.loads(f["e"]) for _, f in ent if ACC in f.get("e", "")]
    R.check("alerts.out/co-canh-bao-luat-khi-doi-trang-thai", bool(mine), f"{len(mine)}", "high")
    R.check("alerts.out/khong-ten-nguon", not any(w in json.dumps(mine).lower() for w in ("dukascopy", "yahoo", "cafef", "forexfactory")), "", "high")
    # vượt luật: equity 9300 (-7%) -> đỏ + sự cố nghiêm trọng
    await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) values ($1,'mt5',now(),10000,9300,1000,'[]'::jsonb) on conflict do nothing", ACC)

    async def red():
        s = await db.fetchval("select status from rule_status where account_id=$1 and assignment_id=$2::uuid", ACC, ids["dl"])
        return s == "red"
    R.check("engine/vuot-luat-chuyen-do", bool(await wait_for(red, 200, 5)), "", "critical")
    inc = await db.fetchrow("select severity from incidents where key=$1 and status <> 'resolved'", f"rule:{ids['dl']}:{ACC}")
    R.check("sucu/leo-thang-critical", bool(inc) and inc["severity"] == "critical", "", "critical")
    # hồi phục: equity về 10000 -> xanh, sự cố tự đóng
    await db.execute("insert into account_snapshots (account_id, platform, ts, balance, equity, margin, positions) values ($1,'mt5',now() + interval '1 second',10000,10050,1000,'[]'::jsonb) on conflict do nothing", ACC)

    async def green():
        s = await db.fetchval("select status from rule_status where account_id=$1 and assignment_id=$2::uuid", ACC, ids["dl"])
        return s == "green"
    R.check("engine/hoi-phuc-ve-xanh", bool(await wait_for(green, 200, 5)), "", "critical")
    st = await db.fetchrow("select status, resolved_by from incidents where key=$1 order by opened_at desc limit 1", f"rule:{ids['dl']}:{ACC}")
    R.check("sucu/tu-dong-dong-khi-hoi-phuc", st and st["status"] == "resolved" and st["resolved_by"] == "auto", f"{dict(st) if st else None}", "critical")
    # endpoint chẩn đoán
    rs = await h.get(f"{RISK}/risk/rules/status", headers=IH)
    R.check("risk-monitor/rules-status-endpoint", rs.status_code == 200, f"{rs.status_code}", "medium")
    await asyncio.sleep(0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
