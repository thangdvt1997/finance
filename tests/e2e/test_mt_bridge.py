"""mt-bridge /ingest/v1: auth hop le/sai/replay/skew/schema + chung minh READ-ONLY (khong co duong dat lenh).

Dung tai khoan demo-mt4-01 (chua co du lieu that), symbol QAUSD, balance danh dau 777777.77 de cleanup.
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone

from qalib import BRIDGE, OUT, Ctx, Results, now, wait_for

R = Results("mt_bridge")
ACC = "demo-mt4-01"
TOK = os.getenv("MT_TOKEN_DEMO_MT4_01", "").strip("\"'")
MARK = 777777.77


def nonce() -> str:
    return "qa" + uuid.uuid4().hex[:20]


def batch(**kw) -> dict:
    b = {"v": 1, "account_id": ACC, "platform": "mt4", "ts": int(time.time()), "nonce": nonce(), "seq": 1}
    b.update(kw)
    return b


def H(tok=TOK, acc=ACC):
    h = {"Content-Type": "application/json", "X-MT-Account": acc}
    if tok is not None:
        h["Authorization"] = f"Bearer {tok}"
    return h


HMAC_SECRET = os.getenv("MT_HMAC_DEMO_MT4_01", "").strip("\"'")


async def post(c, body, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body)
    h = dict(headers or H())
    if HMAC_SECRET and raw is None and h.get("X-MT-Account") == ACC and isinstance(body, dict) and "X-MT-Sig" not in h:
        import hashlib, hmac  # noqa: E401  (bridge bật HMAC cho demo-mt4-01: ký "<ts>.<nonce>." + body)
        h["X-MT-Sig"] = hmac.new(HMAC_SECRET.encode(), f"{body['ts']}.{body['nonce']}.".encode() + data.encode(), hashlib.sha256).hexdigest()
    return await c.http.post(BRIDGE + "/ingest/v1", content=data, headers=h)


async def readonly_tail(c):
    # ---------- READ-ONLY: khong co duong nao dat lenh
    spec = await c.http.get(BRIDGE + "/openapi.json")
    if spec.status_code == 200:
        ps = spec.json()["paths"]
        meths = {(p, m.upper()) for p, v in ps.items() for m in v}
        R.info("readonly/bridge-routes", json.dumps(sorted(meths)))
        bad = [p for p in ps if any(k in p.lower() for k in ("order", "trade", "exec", "close", "modify", "send", "position"))]
        R.check("readonly/bridge-khong-co-route-lenh", not bad, str(bad), "critical")
        R.check("readonly/bridge-chi-POST-ingest", {p for p, m in meths if m != "GET"} == {"/ingest/v1", "/ingest/v1/register", "/internal/invalidate"}, str(sorted(p for p, m in meths if m != "GET")), "critical")
    for p in ["/order", "/orders", "/trade", "/v1/order", "/execute", "/positions/close", "/ingest/v1/order", "/ingest/v2", "/command", "/commands", "/poll", "/ea/commands"]:
        for m in ("GET", "POST"):
            r = await c.http.request(m, BRIDGE + p, headers=H(), content=b"{}")
            if r.status_code not in (404, 405):
                R.check(f"readonly/bridge{m} {p}", False, str(r.status_code), "critical")
    R.check("readonly/bridge-cac-route-lenh-gia-deu-404/405", True, "12 path x GET/POST", "critical")
    # /accounts co auth admin khong?
    r = await c.http.get(BRIDGE + "/accounts")
    R.check("bridge/GET-/accounts-can-admin-token", r.status_code in (401, 403),
            f"{r.status_code} (200 = lo so du/equity khong can token trong mang noi bo; cong 8490 chi bind 127.0.0.1)", "medium")
    with open(os.path.join(OUT, "windows.json"), "a") as f:
        f.write(json.dumps({"mt_end": now().isoformat()}) + chr(10))
    return R.finish()


LIVE = os.getenv("QA_MT_LIVE", "0") == "1"


async def main():
    """QA_MT_LIVE=1 de gui du lieu hop le (tao snapshot/bar/quote that cho demo-mt4-01). CANH BAO: sau ~120s khong con heartbeat,
    mt-bridge phat alert crit 'Mat heartbeat' -> alert-service -> ntfy (kenh that). Mac dinh chi chay phan auth/schema/read-only."""
    with open(os.path.join(OUT, "windows.json"), "a") as f:
        f.write(json.dumps({"mt_start": now().isoformat()}) + "\n")
    async with Ctx() as c:
        R.check("env/co-token-test", bool(TOK), "MT_TOKEN_DEMO_MT4_01 trong env (khong in)", "high")
        base_snap = await c.db.fetchval("select count(*) from account_snapshots where account_id=$1", ACC)
        R.info("baseline", f"{ACC} snapshots truoc test = {base_snap}")

        # ---------- auth
        r = await post(c, batch(), headers={"Content-Type": "application/json", "X-MT-Account": ACC})
        R.check("ingest/khong-token->401", r.status_code == 401, str(r.status_code), "critical")
        r_wrong = await post(c, batch(), headers=H("sai-token-qa"))
        R.check("ingest/token-sai->401", r_wrong.status_code == 401, str(r_wrong.status_code), "critical")
        r_unk = await post(c, batch(account_id="qa-khong-co"), headers=H(TOK, "qa-khong-co"))
        R.check("ingest/account-la->401", r_unk.status_code == 401, str(r_unk.status_code), "critical")
        R.check("ingest/401-dong-nhat-khong-lo-account", r_wrong.text == r_unk.text, f"{r_wrong.text} | {r_unk.text}", "medium")
        r = await post(c, batch(platform="mt5", account_id="demo-mt5-01"), headers=H(TOK, "demo-mt5-01"))
        R.check("ingest/token-mt4-dung-cho-account-mt5->401", r.status_code == 401, str(r.status_code), "critical")
        r = await post(c, batch(), headers={**H(), "Authorization": TOK})  # thieu 'Bearer '
        R.check("ingest/thieu-Bearer->401", r.status_code == 401, str(r.status_code), "high")
        r = await c.http.get(BRIDGE + "/ingest/v1", headers=H())
        R.check("ingest/GET-khong-cho-phep", r.status_code in (404, 405), str(r.status_code), "low")

        if LIVE:
            # ---------- hop le: heartbeat
            b = batch()
            r = await post(c, b)
            R.check("ingest/heartbeat-hop-le->200", r.status_code == 200 and r.json().get("ok") is True, f"{r.status_code} {r.text[:120]}", "critical")
            keys = set(r.json().keys()) if r.status_code == 200 else set()
            R.check("readonly/response-khong-co-kenh-lenh-cho-EA", keys <= {"ok", "quotes", "bars", "snapshot"}, f"keys={sorted(keys)}", "critical")
            # replay: cung body/nonce
            r = await post(c, b)
            R.check("ingest/replay-cung-nonce->409", r.status_code == 409, str(r.status_code), "critical")
        # ts lech
        r = await post(c, batch(ts=int(time.time()) - 600))
        R.check("ingest/ts-cu-600s->401", r.status_code == 401, str(r.status_code), "high")
        r = await post(c, batch(ts=int(time.time()) + 600))
        R.check("ingest/ts-tuong-lai-600s->401", r.status_code == 401, str(r.status_code), "high")
        # schema
        for name, body, exp in [
            ("truong-thua-order", batch(order={"symbol": "EURUSD", "type": "buy", "lots": 1}), 422),
            ("truong-thua-action", batch(action="buy"), 422),
            ("platform-sai", batch(platform="mt9"), 422),
            ("nonce-ngan", batch(nonce="abc"), 422),
            ("version-sai", batch(v=2), 422),
            ("quote-bid-am", batch(quotes=[{"symbol": "QAUSD", "bid": -1, "ask": 1, "time": 1}]), 422),
            ("symbol-injection", batch(quotes=[{"symbol": "A';DROP TABLE bars;--", "bid": 1, "ask": 1, "time": 1}]), 422),
            ("position-lots-0", batch(positions=[{"ticket": 1, "symbol": "QAUSD", "type": 0, "lots": 0, "open_price": 1, "price": 1, "open_time": 1}]), 422),
            ("order-type-1-(market)", batch(orders=[{"ticket": 1, "symbol": "QAUSD", "type": 1, "lots": 1, "price": 1, "setup_time": 1}]), 422),
            ("qua-nhieu-quotes(>400, feed-all)", batch(quotes=[{"symbol": "QAUSD", "bid": 1, "ask": 1, "time": i} for i in range(401)]), 422),
        ]:
            r = await post(c, body)
            R.check(f"ingest/schema/{name}->{exp}", r.status_code == exp, f"{r.status_code} {r.text[:100]}", "high")
        r = await post(c, None, raw=json.dumps(batch()).replace('"seq": 1', '"seq": NaN'))
        R.check("ingest/NaN->422", r.status_code == 422, str(r.status_code), "medium")
        r = await post(c, None, raw="{khong phai json")
        R.check("ingest/json-hong->422", r.status_code == 422, str(r.status_code), "medium")
        r = await post(c, None, raw="x" * 1_100_000)
        R.check("ingest/body>1MB->413", r.status_code == 413, str(r.status_code), "medium")
        r = await post(c, batch(platform="mt5"))
        R.check("ingest/platform-khong-khop-cau-hinh->400", r.status_code == 400, str(r.status_code), "medium")

        if not LIVE:
            R.info("live", "bo qua nhom du lieu hop le (dat QA_MT_LIVE=1 de chay; xem docstring)")
            return await readonly_tail(c)
        # ---------- du lieu hop le -> bus -> DB (kiem tra quy doi mui gio server Europe/Athens)
        # 2025-03-12 10:00Z (Athens UTC+2) va 2025-07-10 10:00Z (Athens UTC+3)
        t_w = int(datetime(2025, 3, 12, 10, 0, tzinfo=timezone.utc).timestamp())
        t_s = int(datetime(2025, 7, 10, 10, 0, tzinfo=timezone.utc).timestamp())
        u = int(uuid.uuid4().int % 1000) / 1e4  # gia tri khac nhau moi lan chay (bridge dedupe nen giong het trong RAM)
        bars = [{"symbol": "QAUSD", "tf": "H1", "time": t_w + 2 * 3600, "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15 + u, "v": 5},
                {"symbol": "QAUSD", "tf": "H1", "time": t_s + 3 * 3600, "o": 2.1, "h": 2.2, "l": 2.0, "c": 2.15 + u, "v": 6}]
        quotes = [{"symbol": "QAUSD", "bid": 1.2345 + u, "ask": 1.2347 + u, "time": int(time.time()) + 3 * 3600}]
        acc = {"login": 99999, "server": "QA-Server", "currency": "USD", "leverage": 100, "balance": MARK, "equity": MARK, "margin": 0.0,
               "free_margin": MARK, "margin_level": None, "margin_mode": "hedging", "trade_allowed": False}
        b = batch(account=acc, quotes=quotes, bars=bars, server_time=int(time.time()) + 3 * 3600)
        r = await post(c, b)
        R.check("ingest/du-lieu-day-du->200", r.status_code == 200 and r.json().get("bars") == 2, f"{r.status_code} {r.text[:150]}", "critical")
        okb = await wait_for(lambda: c.db.fetchval("select count(*) from bars where symbol='QAUSD' and tf='H1' and source<>'qa'"), 10)
        rows = await c.db.fetch("select ts_open, source, c from bars where symbol='QAUSD' and tf='H1' and source<>'qa' order by ts_open")
        got = [x["ts_open"].astimezone(timezone.utc).isoformat() for x in rows]
        R.check("bridge/bar->DB", len(rows) == 2, f"rows={len(rows)} src={[x['source'] for x in rows][:1]}", "critical")
        R.check("bridge/quy-doi-gio-server->UTC (mua dong +2)", len(rows) == 2 and got[0].startswith("2025-03-12T10:00"), str(got), "critical")
        R.check("bridge/quy-doi-gio-server->UTC (mua he +3)", len(rows) == 2 and got[1].startswith("2025-07-10T10:00"), str(got), "critical")
        okq = await wait_for(lambda: c.db.fetchval("select count(*) from quotes where symbol='QAUSD' and source<>'qa'"), 10)
        R.check("bridge/quote->DB", bool(okq), "", "high")
        if okq:
            qts = await c.db.fetchval("select ts from quotes where symbol='QAUSD' and source<>'qa' limit 1")
            drift = abs((now() - qts).total_seconds())
            R.check("bridge/quote-ts-quy-ve-UTC (lech < 120s)", drift < 120, f"drift={drift:.0f}s (neu ~10800s: chua tru gio server)", "high")
        oka = await wait_for(lambda: c.db.fetchval("select count(*) from account_snapshots where account_id=$1 and balance=$2", ACC, MARK), 10)
        R.check("bridge/account-snapshot->DB", bool(oka), "", "critical")
        # idempotency: gui lai cung du lieu nen/nonce moi -> khong tang so dong bar
        r = await post(c, batch(account=acc, quotes=quotes, bars=bars))
        R.check("bridge/gui-lai-cung-bar-bi-bridge-dedupe(bars=0 trong response)", r.status_code == 200 and r.json().get("bars") == 0, r.text[:100], "low")
        await asyncio.sleep(2)
        n = await c.db.fetchval("select count(*) from bars where symbol='QAUSD' and tf='H1' and source<>'qa'")
        R.check("bridge/gui-lai-cung-bar-khong-nhan-doi", n == 2, f"rows={n}", "critical")
        # API doc duoc tai khoan
        r = await c.api("/v1/accounts")
        accs = r.json() if r.status_code == 200 else []
        accs = accs if isinstance(accs, list) else accs.get("items", [])
        R.check("bridge/api-accounts-thay-demo-mt4-01", any(a["account_id"] == ACC and a["balance"] == MARK for a in accs), "", "high")

        # ---------- trade_allowed=true -> canh bao bao mat
        a2 = dict(acc, trade_allowed=True)
        t_a = now()
        await post(c, batch(account=a2))
        okw = await wait_for(lambda: c.db.fetchval("select count(*) from alerts where ts >= $1 and 'security' = any(tags) and title like $2", t_a, f"%{ACC}%"), 10)
        R.check("bridge/trade_allowed=true->canh-bao-warn-security", bool(okw), "", "medium")

        return await readonly_tail(c)
    with open(os.path.join(OUT, "windows.json"), "a") as f:
        f.write(json.dumps({"mt_end": now().isoformat()}) + chr(10))
    return R.finish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
