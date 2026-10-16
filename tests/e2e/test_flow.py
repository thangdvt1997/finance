"""Smoke + luong bus->DB->API cho tung stream, idempotency, DLQ, auth, WebSocket."""
import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import websockets

from qalib import (API_KEY, BRIDGE, GATEWAY, SERVICES, Ctx, Results, mk_event, now, publish, wait_for)

R = Results("flow")
SYM = "QAUSD"
RUN = uuid.uuid4().hex[:8]


async def health(c: Ctx):
    for s in SERVICES:
        base = f"http://{s}:8000"
        try:
            h = await c.http.get(base + "/healthz")
            R.check(f"health/{s}/healthz", h.status_code == 200, f"{h.status_code} {h.text[:80]}", "high")
        except Exception as e:
            R.check(f"health/{s}/healthz", False, repr(e), "high")
        try:
            m = await c.http.get(base + "/metrics")
            ok = m.status_code == 200 and "# HELP" in m.text
            R.check(f"health/{s}/metrics", ok, f"{m.status_code} {len(m.text)}B", "medium")
        except Exception as e:
            R.check(f"health/{s}/metrics", False, repr(e), "medium")
    rz = await c.http.get(GATEWAY + "/readyz")
    R.check("health/api-gateway/readyz", rz.status_code == 200, rz.text[:80], "high")
    m = (await c.http.get("http://storage-writer:8000/metrics")).text
    R.check("metrics/storage-writer co sw_events_total", "sw_events_total" in m, "", "low")
    for st in ["md.bars", "md.quotes", "news.items", "calendar.events", "expert.signals", "expert.positions",
               "expert.profiles", "account.snapshots", "alerts.out"]:
        try:
            gs = await c.r.xinfo_groups(st)
            g = [x for x in gs if x["name"] == "storage-writer"]
            R.check(f"group/{st}/storage-writer", bool(g) and (g[0].get("lag") or 0) < 100 and g[0]["pending"] <= (100 if st == "md.quotes" else 0),  # md.quotes: lo dang xu ly (batch=100) o tai ~135 quote/s
                    
                    f"lag={g[0].get('lag') if g else None}, pending={g[0]['pending'] if g else None}", "medium")
        except Exception as e:
            R.check(f"group/{st}/storage-writer", False, repr(e), "medium")


async def auth(c: Ctx):
    spec0 = (await c.http.get(GATEWAY + "/openapi.json")).json()
    paths = ["/v1/bars?symbol=EURUSD&tf=D1", "/v1/overview", "/v1/news", "/v1/calendar", "/v1/experts",
             "/v1/accounts", "/v1/alerts", "/v1/system", "/v1/symbols"]
    for p0 in paths:
        if p0.split("?")[0] not in spec0["paths"]:
            R.info(f"auth/{p0}", "route chua co trong image dang chay (source moi hon image) - bo qua")
    for path in [p for p in paths if p.split("?")[0] in spec0["paths"]]:
        r0 = await c.http.get(GATEWAY + path)
        r1 = await c.http.get(GATEWAY + path, headers={"X-API-Key": "wrong-key-qa"})
        r2 = await c.http.get(GATEWAY + path, headers={"X-API-Key": API_KEY})
        R.check(f"auth/{path.split('?')[0]}", r0.status_code in (401, 403) and r1.status_code in (401, 403) and r2.status_code == 200,
                f"nokey={r0.status_code} wrong={r1.status_code} ok={r2.status_code}", "critical")
    rq = await c.http.get(GATEWAY + "/v1/overview", params={"api_key": API_KEY, "X-API-Key": API_KEY})
    R.check("auth/key-qua-query-bi-tu-choi", rq.status_code in (401, 403), str(rq.status_code), "medium")
    for p in ["/healthz", "/readyz", "/metrics", "/docs", "/openapi.json"]:
        r = await c.http.get(GATEWAY + p)
        R.check(f"auth/public{p}", r.status_code == 200, str(r.status_code), "low")
    spec = (await c.http.get(GATEWAY + "/openapi.json")).json()
    # Chỉ các route cấu hình người dùng (/v1/user/*) được ghi; mọi route khác chỉ GET.
    write_paths = sorted(p for p, v in spec["paths"].items() if {m.upper() for m in v} - {"GET"})
    bad_writes = [p for p in write_paths if not p.startswith(("/v1/user/", "/v1/journal/", "/v1/account-report", "/v1/ai-trading/", "/v1/data/recheck"))]  # journal: chỉ tag/ghi chú (whitelist + CSRF); account-report*: sinh/phát hành báo cáo (master_write_guard), không phải lệnh giao dịch; ai-trading/*: lớp học/kịch bản/job/kill-switch của sổ PAPER (master+Origin+CSRF); data/recheck: kiểm tra lại dữ liệu (master)
    R.check("readonly/api-gateway-chi-GET", not bad_writes, f"ghi ngoai /v1/user/: {bad_writes}; route ghi hop le: {write_paths}", "critical")
    bad = [p for p, v in spec["paths"].items() if re.search(r"order|trade|execut|close|modify", p, re.I) and not (p in ("/v1/accounts/{account_id}/orders", "/v1/patterns/trades") and {m.upper() for m in v} == {"GET"})]   # ngoại lệ chỉ-đọc (GET): danh sách lệnh chờ; lệnh PAPER mô phỏng của kịch bản (vòng 4)
    R.check("readonly/api-gateway-khong-co-route-lenh", not bad, f"{bad}", "critical")
    before = await c.db.fetchval("select count(*) from bars")
    for q in ["EURUSD'; DROP TABLE bars;--", "EURUSD%27%20OR%201=1--", "../../etc/passwd", "A" * 200]:
        r = await c.http.get(GATEWAY + "/v1/bars", params={"symbol": q, "tf": "D1"}, headers={"X-API-Key": API_KEY})
        R.check(f"inject/{q[:18]!r}", r.status_code in (422, 200), str(r.status_code), "high")
    after = await c.db.fetchval("select count(*) from bars")
    R.check("inject/bars-khong-mat", after >= before, f"{before}->{after}", "critical")
    for params, exp in [({"symbol": "EURUSD", "tf": "XX"}, 422), ({"symbol": "EURUSD", "tf": "D1", "limit": 0}, 422),
                        ({"symbol": "EURUSD", "tf": "D1", "limit": 999999}, 422),
                        ({"symbol": "EURUSD", "tf": "D1", "limit": 5000}, 200),
                        ({"symbol": "EURUSD", "tf": "D1", "from": "not-a-date"}, 422),
                        ({"symbol": "EURUSD", "tf": "D1", "offset": -1}, 422)]:
        r = await c.http.get(GATEWAY + "/v1/bars", params=params, headers={"X-API-Key": API_KEY})
        R.check(f"validate/bars {params}", r.status_code == exp, f"got {r.status_code}", "low")
    for m in ["POST", "PUT", "DELETE"]:
        r = await c.http.request(m, GATEWAY + "/v1/bars", headers={"X-API-Key": API_KEY})
        R.check(f"readonly/{m}-/v1/bars", r.status_code in (404, 405), str(r.status_code), "high")


def items_of(r):
    j = r.json()
    return j if isinstance(j, list) else j.get("items", [])


async def flows(c: Ctx):
    t = now().replace(microsecond=0)
    ts_open = (t - timedelta(days=400)).replace(minute=0, second=0)  # xa du lieu that
    bar = {"symbol": SYM, "tf": "M1", "ts_open": ts_open.isoformat(), "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15, "v": 10, "source": "qa"}

    async def cnt(sql, *a):
        return await c.db.fetchval(sql, *a)

    # ---- bars
    t0 = time.time()
    await publish(c.r, "md.bars", mk_event("bar", bar))
    ok = await wait_for(lambda: cnt("select count(*) from bars where symbol=$1 and source='qa' and ts_open=$2", SYM, ts_open), 10)
    R.check("bars/bus->db", bool(ok), f"{(time.time()-t0)*1000:.0f}ms", "critical")
    r = await c.api("/v1/bars", symbol=SYM, tf="M1")
    items = items_of(r) if r.status_code == 200 else []
    R.check("bars/api", len(items) == 1 and abs(items[0]["c"] - 1.15) < 1e-9
            and items[0]["ts_open"].startswith(ts_open.strftime("%Y-%m-%dT%H:%M")), json.dumps(items)[:200], "high")
    e = mk_event("bar", {**bar, "c": 1.16})
    await publish(c.r, "md.bars", e)
    await publish(c.r, "md.bars", e)
    await publish(c.r, "md.bars", mk_event("bar", {**bar, "c": 1.17}))
    await asyncio.sleep(2)
    n = await cnt("select count(*) from bars where symbol=$1 and source='qa' and tf='M1' and ts_open=$2", SYM, ts_open)
    cl = await cnt("select c from bars where symbol=$1 and source='qa' and tf='M1' and ts_open=$2", SYM, ts_open)
    R.check("bars/idempotent-1-dong", n == 1, f"rows={n} c={cl}", "critical")
    R.check("bars/upsert-ghi-de-gia-tri-moi", abs(cl - 1.17) < 1e-9, f"c={cl}", "medium")

    # ---- quotes
    q = {"symbol": SYM, "bid": 1.1000, "ask": 1.1002, "ts": t.isoformat(), "source": "qa"}
    qe = mk_event("quote", q)
    await publish(c.r, "md.quotes", qe)
    await publish(c.r, "md.quotes", qe)
    ok = await wait_for(lambda: cnt("select count(*) from quotes where symbol=$1 and source='qa' and ts=$2", SYM, t), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from quotes where symbol=$1 and source='qa' and ts=$2", SYM, t)
    R.check("quotes/bus->db+idempotent", ok and n == 1, f"rows={n}", "critical")
    r = await c.api("/v1/quotes/latest", symbols=SYM)
    R.check("quotes/api-latest", r.status_code == 200 and any(x["symbol"] == SYM for x in items_of(r)), r.text[:160], "high")

    # ---- news
    url = f"https://qa.invalid/news/{RUN}"
    nw = {"url": url, "title": f"QA news {RUN}", "summary": "s", "published_at": t.isoformat(), "source": "qa", "lang": "en", "symbols": [SYM], "sentiment": 0.5}
    await publish(c.r, "news.items", mk_event("news", nw))
    await publish(c.r, "news.items", mk_event("news", nw))
    ok = await wait_for(lambda: cnt("select count(*) from news_items where url=$1", url), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from news_items where url=$1", url)
    R.check("news/bus->db+idempotent-url", ok and n == 1, f"rows={n}", "critical")
    # hop dong (fbda4e9): API cong khai AN source='qa' -> du lieu test khong lot ra UI; kiem tra API 200 va khong chua muc qa
    r = await c.api("/v1/news", symbol=SYM)
    R.check("news/api-theo-symbol", r.status_code == 200 and not any(x["url"] == url for x in items_of(r)), f"{r.status_code} (an source=qa) x-gw-cache={r.headers.get('x-gw-cache')}", "high")

    # ---- calendar
    cid = f"qa-{RUN}"
    cal = {"event_id": cid, "country": "US", "title": "QA event", "impact": "high", "ts": (t + timedelta(hours=3)).isoformat(),
           "forecast": "1.0", "previous": "0.9", "actual": None, "source": "qa"}
    await publish(c.r, "calendar.events", mk_event("calendar", cal))
    await publish(c.r, "calendar.events", mk_event("calendar", cal))
    ok = await wait_for(lambda: cnt("select count(*) from calendar_events where event_id=$1", cid), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from calendar_events where event_id=$1", cid)
    R.check("calendar/bus->db+idempotent", ok and n == 1, f"rows={n}", "critical")
    await publish(c.r, "calendar.events", mk_event("calendar", {**cal, "actual": "1.2"}))
    ok2 = await wait_for(lambda: cnt("select count(*) from calendar_events where event_id=$1 and actual='1.2'", cid), 10)
    R.check("calendar/update-actual", bool(ok2), "", "medium")
    r = await c.api("/v1/calendar", impact="high", to=(t + timedelta(days=1)).isoformat(), limit=500)
    R.check("calendar/api", r.status_code == 200 and not any(x["event_id"] == cid for x in items_of(r)), f"{r.status_code} (an source=qa)", "high")

    # ---- expert.*
    ex = f"qa-expert-{RUN}"
    prof = {"expert_id": ex, "source": "qa", "display_name": "QA Expert", "url": "https://qa.invalid/e", "reputation": {"score": 77, "qualified": True}, "tracked": True}
    await publish(c.r, "expert.profiles", mk_event("expert_profile", prof))
    ok = await wait_for(lambda: cnt("select count(*) from experts where expert_id=$1", ex), 10)
    R.check("expert.profiles/bus->db", bool(ok), "", "high")
    sig = {"expert_id": ex, "source": "qa", "symbol": SYM, "side": "buy", "entry": 1.1, "sl": 1.0, "tp": 1.3, "opened_at": t.isoformat(), "status": "open", "url": "https://qa.invalid/s", "raw": {"a": 1}}
    await publish(c.r, "expert.signals", mk_event("expert_signal", sig))
    await publish(c.r, "expert.signals", mk_event("expert_signal", sig))
    ok = await wait_for(lambda: cnt("select count(*) from expert_signals where expert_id=$1", ex), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from expert_signals where expert_id=$1", ex)
    R.check("expert.signals/bus->db+idempotent", ok and n == 1, f"rows={n}", "critical")
    pos = {"expert_id": ex, "source": "qa", "symbol": SYM, "net_volume": 2.5, "avg_price": 1.1, "as_of": t.isoformat(), "raw": {}}
    await publish(c.r, "expert.positions", mk_event("expert_position", pos))
    await publish(c.r, "expert.positions", mk_event("expert_position", pos))
    ok = await wait_for(lambda: cnt("select count(*) from expert_positions where expert_id=$1", ex), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from expert_positions where expert_id=$1", ex)
    R.check("expert.positions/bus->db+idempotent", ok and n == 1, f"rows={n}", "critical")
    async def _ex_ok():
        r = await c.api("/v1/experts", limit=500)
        return r if r.status_code == 200 and any(x["expert_id"] == ex for x in items_of(r)) else None
    r = await wait_for(_ex_ok, 6, 0.5) or await c.api("/v1/experts", limit=500)
    R.check("expert/api/v1/experts", r.status_code == 200 and any(x["expert_id"] == ex for x in items_of(r)), f"{r.status_code} x-gw-cache={r.headers.get('x-gw-cache')}", "high")
    for path in ["/v1/expert-signals", "/v1/expert-positions"]:
        r = await c.api(path, expert_id=ex)
        R.check(f"expert/api{path}", r.status_code == 200 and any(x["expert_id"] == ex for x in items_of(r)), str(r.status_code), "high")
    r = await c.api("/v1/expert-signals", status="open", expert_id=ex)
    R.check("expert-signals/filter-status", r.status_code == 200 and len(items_of(r)) == 1, "", "low")

    # ---- account.snapshots
    acc = {"account_id": "qa-acct", "platform": "mt5", "ts": t.isoformat(), "balance": 1000.0, "equity": 990.0, "margin": 10.0,
           "positions": [], "free_margin": 980, "margin_level": 9900, "currency": "USD", "leverage": 100, "login": 1, "server": "qa", "orders": []}
    ae = mk_event("account_snapshot", acc)
    await publish(c.r, "account.snapshots", ae)
    await publish(c.r, "account.snapshots", ae)
    ok = await wait_for(lambda: cnt("select count(*) from account_snapshots where account_id='qa-acct' and ts=$1", t), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from account_snapshots where account_id='qa-acct' and ts=$1", t)
    R.check("account/bus->db+idempotent", ok and n == 1, f"rows={n}", "critical")
    r = await c.api("/v1/accounts")
    R.check("account/api", r.status_code == 200 and any(x["account_id"] == "qa-acct" for x in items_of(r)), str(r.status_code), "high")
    r = await c.api("/v1/equity-history", account_id="qa-acct")
    if r.status_code == 404:
        R.info("account/equity-history", "route chua deploy (image cu hon source)")
    else:
        R.check("account/equity-history", r.status_code == 200 and len(items_of(r)) >= 1, str(r.status_code), "low")

    # ---- alerts.out (alert-service chi log; Telegram chua cau hinh)
    al = {"level": "info", "title": f"QA alert {RUN}", "body": "qa", "tags": ["qa"], "dedupe_key": f"qa-{RUN}"}
    ale = mk_event("alert", al)
    await publish(c.r, "alerts.out", ale)
    await publish(c.r, "alerts.out", ale)
    ok = await wait_for(lambda: cnt("select count(*) from alerts where title=$1", al["title"]), 10)
    await asyncio.sleep(1)
    n = await cnt("select count(*) from alerts where title=$1", al["title"])
    R.check("alerts/bus->db+idempotent-theo-event-id", ok and n == 1, f"rows={n}", "critical")
    r = await c.api("/v1/alerts", level="info", limit=50)
    R.check("alerts/api", r.status_code == 200 and any(x["title"] == al["title"] for x in items_of(r)), str(r.status_code), "high")
    rec = await c.r.lrange("alerts:recent", 0, 20)
    R.check("alerts/alert-service-da-xu-ly", any(al["title"] in x for x in rec), "alerts:recent", "high")
    await asyncio.sleep(2)
    dl = await cnt("select delivered from alerts where title=$1", al["title"])
    R.info("alerts/delivered-flag", f"delivered={dl} (kenh log; tham khao)")
    await publish(c.r, "alerts.out", mk_event("alert", al))
    await asyncio.sleep(2)
    n2 = await cnt("select count(*) from alerts where title=$1", al["title"])
    R.info("alerts/dedupe_key-trung-event-khac", f"DB rows={n2} (dedupe chi o muc gui, DB theo event_id)")


async def perf(c: Ctx):
    for name, path, params, limit_ms in [("bars-5000", "/v1/bars", {"symbol": "GBPUSD", "tf": "M1", "limit": 5000}, 1500),
                                         ("bars-D1", "/v1/bars", {"symbol": "EURUSD", "tf": "D1", "limit": 100}, 300),
                                         ("overview", "/v1/overview", {}, 1500), ("news", "/v1/news", {"limit": 100}, 500),
                                         ("calendar", "/v1/calendar", {"limit": 100}, 500), ("quotes-latest", "/v1/quotes/latest", {}, 500)]:
        ts = []
        for _ in range(15):
            t0 = time.time()
            r = await c.api(path, **params)
            ts.append((time.time() - t0) * 1000)
            if r.status_code != 200:
                break
        ts.sort()
        R.check(f"perf/api{name}", r.status_code == 200 and ts[int(len(ts) * .95) - 1] < limit_ms, f"p50={ts[len(ts)//2]:.0f}ms p95={ts[int(len(ts)*.95)-1]:.0f}ms max={ts[-1]:.0f}ms (nguong p95<{limit_ms}ms) status={r.status_code}", "medium")
        R.metric(f"api.{name}.p95_ms", round(ts[int(len(ts) * .95) - 1]))


async def dlq(c: Ctx):
    base = await c.r.xrevrange("dlq", count=1)
    base_id = base[0][0] if base else "0-0"
    marker = f"QA-DLQ-{RUN}"
    iso = now().isoformat()
    bad = [
        ("md.bars", mk_event("bar", {"symbol": SYM, "tf": "M1", "ts_open": iso, "source": "qa", "m": marker})),
        ("md.bars", mk_event("bar", {"symbol": SYM, "tf": "M1", "ts_open": "hom-qua", "o": 1, "h": 1, "l": 1, "c": 1, "source": "qa", "m": marker})),
        ("md.bars", mk_event("bar", {"symbol": SYM, "tf": "M1", "ts_open": iso, "o": "abc", "h": 1, "l": 1, "c": 1, "source": "qa", "m": marker})),
        ("md.quotes", mk_event("quote", {"bid": 1, "ask": 1, "ts": iso, "source": "qa", "m": marker})),
        ("news.items", mk_event("news", {"url": "https://qa.invalid/x", "source": "qa", "m": marker})),
        ("calendar.events", mk_event("calendar", {"title": "x", "ts": iso, "source": "qa", "m": marker})),
        ("expert.signals", mk_event("expert_signal", {"expert_id": "qa-x", "source": "qa", "symbol": SYM, "side": "LONG", "opened_at": iso, "m": marker})),
        ("account.snapshots", mk_event("account_snapshot", {"account_id": "qa-bad", "platform": "mt5", "m": marker})),
        ("alerts.out", mk_event("alert", {"level": "fatal", "title": "QA bad", "m": marker})),
        ("md.bars", "{not json " + marker),
        ("news.items", json.dumps({"hello": marker})),
        ("md.quotes", mk_event("quote", {"symbol": SYM, "bid": 1, "ask": 1, "ts": "xx", "source": "qa", "m": marker})),
    ]
    for st, e in bad:
        await publish(c.r, st, e)
    await asyncio.sleep(5)
    entries = await c.r.xrange("dlq", min=f"({base_id}", max="+", count=500)
    mine = [(i, f) for i, f in entries if marker in f.get("e", "")]
    # Tu 2026-10-12 service `nlp` cung doc news.items va tu dead-letter payload hong (reason 'nlp: ...') => 1 tin hong co the co 2 dong DLQ
    core = [(i, f) for i, f in mine if not f.get("reason", "").startswith("nlp:")]
    nlp_extra = len(mine) - len(core)
    # Nhieu consumer group co the cung dead-letter 1 tin hong (vd md.bars: storage-writer 'decode:' + group khac 'invalid_event:') => dem theo (stream, msg_id) goc
    core_uniq = {(f.get("stream"), f.get("msg_id")) for _, f in core}
    core_dup = len(core) - len(core_uniq)
    dups = []
    R.check("dlq/nhan-du-payload-sai", len(core_uniq) == len(bad), f"{len(core_uniq)}/{len(bad)} tin vao dlq (+{nlp_extra} dong tu nlp, +{core_dup} dong tu group khac: hop le, moi consumer group dead-letter payload hong rieng)", "critical")
    mine = core
    R.check("dlq/co-ly-do", all(f.get("reason") for _, f in mine), "; ".join(sorted({f.get('reason', '')[:40] for _, f in mine}))[:200], "low")
    n = await c.db.fetchval("select count(*) from bars where symbol=$1 and source='qa' and tf='M1' and ts_open > now() - interval '300 days'", SYM)
    R.check("dlq/khong-ghi-DB", n == 0, f"rows={n}", "high")
    gs = {g["name"]: g for g in await c.r.xinfo_groups("md.bars")}
    R.check("dlq/khong-ket-pending", gs["storage-writer"]["pending"] == 0, str(gs["storage-writer"]["pending"]), "high")
    h = await c.http.get("http://storage-writer:8000/healthz")
    R.check("dlq/storage-writer-van-song", h.status_code == 200, "", "high")
    e = mk_event("bar", {"symbol": SYM, "tf": "M5", "ts_open": (now() - timedelta(days=300)).replace(second=0, microsecond=0).isoformat(), "o": 1, "h": 1, "l": 1, "c": 1, "source": "qa"})
    await publish(c.r, "md.bars", e)
    ok = await wait_for(lambda: c.db.fetchval("select count(*) from bars where symbol=$1 and tf='M5' and source='qa' and ts_open > now() - interval '301 days'", SYM), 10)
    R.check("dlq/su-kien-hop-le-sau-poison-van-ghi", bool(ok), "", "high")
    # semantic: OHLC phi ly (low > high) co bi tu choi khong?
    e2 = mk_event("bar", {"symbol": SYM, "tf": "H1", "ts_open": (now() - timedelta(days=301)).replace(minute=0, second=0, microsecond=0).isoformat(), "o": 5, "h": 1, "l": 9, "c": 100, "v": -5, "source": "qa"})
    await publish(c.r, "md.bars", e2)
    await asyncio.sleep(3)
    n = await c.db.fetchval("select count(*) from bars where symbol=$1 and tf='H1' and source='qa' and o=5 and l=9", SYM)
    R.check("validate/bar-OHLC-phi-ly-bi-chan-o-ghi", n == 0, f"rows={n} (neu 1: DB nhan bar low>high, v<0)", "medium")
    # stream la (khong co mapper) khong lam hong gi: bo qua


async def ws(c: Ctx):
    wsurl = GATEWAY.replace("http", "ws")
    url = wsurl + "/v1/stream?streams=md.quotes&symbols=" + SYM
    t0 = time.time()
    try:
        async with websockets.connect(url) as w:
            try:
                msg = await asyncio.wait_for(w.recv(), 15)
                R.check("ws/khong-key-bi-tu-choi", False, f"nhan: {str(msg)[:80]}", "critical")
            except websockets.ConnectionClosed as e:
                R.check("ws/khong-key-bi-tu-choi", True, f"dong sau {time.time()-t0:.1f}s code={e.rcvd.code if e.rcvd else None}", "critical")
    except Exception as e:
        R.check("ws/khong-key-bi-tu-choi", True, f"{type(e).__name__}", "critical")
    try:
        async with websockets.connect(url) as w:
            await w.send(json.dumps({"type": "auth", "api_key": "sai"}))
            try:
                await asyncio.wait_for(w.recv(), 5)
                R.check("ws/key-sai-bi-dong", False, "nhan duoc du lieu", "critical")
            except websockets.ConnectionClosed:
                R.check("ws/key-sai-bi-dong", True, "", "critical")
    except Exception as e:
        R.check("ws/key-sai-bi-dong", True, type(e).__name__, "critical")
    try:
        async with websockets.connect(wsurl + "/v1/stream?streams=evil", additional_headers={"X-API-Key": API_KEY}) as w:
            await asyncio.wait_for(w.recv(), 5)
            R.check("ws/stream-la-bi-tu-choi", False, "", "medium")
    except Exception:
        R.check("ws/stream-la-bi-tu-choi", True, "", "medium")
    for mode in ("header", "firstmsg"):
        try:
            kw = {"additional_headers": {"X-API-Key": API_KEY}} if mode == "header" else {}
            async with websockets.connect(url, **kw) as w:
                if mode == "firstmsg":
                    await w.send(json.dumps({"type": "auth", "api_key": API_KEY}))
                ready = json.loads(await asyncio.wait_for(w.recv(), 10))
                R.check(f"ws/{mode}/ready", ready.get("type") == "ready", str(ready)[:80], "high")
                await asyncio.sleep(1.5)  # pump XREAD "$" can vai tick de bat dau
                t = now()
                e_other = mk_event("quote", {"symbol": "QAOTHER", "bid": 2, "ask": 2, "ts": t.isoformat(), "source": "qa"})
                e_me = mk_event("quote", {"symbol": SYM, "bid": 1.5, "ask": 1.5001, "ts": (t + timedelta(seconds=1)).isoformat(), "source": "qa"})
                t0 = time.time()
                await publish(c.r, "md.quotes", e_other)
                await publish(c.r, "md.quotes", e_me)
                got = None
                try:
                    while True:
                        m = json.loads(await asyncio.wait_for(w.recv(), 10))
                        if m.get("type") == "event":
                            got = m
                            break
                except asyncio.TimeoutError:
                    pass
                R.check(f"ws/{mode}/nhan-su-kien-dung-symbol", bool(got) and got["event"]["id"] == e_me["id"],
                        f"{(time.time()-t0)*1000:.0f}ms" if got else "khong nhan", "high")
        except Exception as e:
            R.check(f"ws/{mode}", False, repr(e), "high")


async def main():
    async with Ctx() as c:
        await health(c)
        await auth(c)
        await flows(c)
        await dlq(c)
        await ws(c)
        await perf(c)
    return R.finish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
