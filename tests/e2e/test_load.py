"""Tai nhe + do tre bus->DB + kill/restart storage-writer giua luong.

  python test_load.py load    # 5.000 su kien/stream (alerts 1.000): burst + steady 50ev/s x 300
  python test_load.py crash   # xem run_crash.sh (host restart/kill storage-writer giua luong)
Du lieu: source='qa', symbol QALOAD/QACRASH, account qa-load-*, url qa.invalid.
"""
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

from qalib import DSN, OUT, Ctx, Results, lat_summary, mk_event, now, pct, publish, publish_many

RUN = uuid.uuid4().hex[:8]
N = int(os.getenv("QA_N", "5000"))
# CANH BAO: moi alert di qua alert-service -> ntfy (apprise ~5s/tin, kenh THAT). Mac dinh KHONG tai alerts (QA_N_ALERT=0).
N_ALERT = int(os.getenv("QA_N_ALERT", "0"))
BASE = (now() - timedelta(days=500)).replace(second=0, microsecond=0, minute=0, hour=0)


def gen(stream: str, n: int, tag: str):
    """Tra ve (events, count_sql, count_args)."""
    evs = []
    BASE = globals()["BASE"] + timedelta(days={"b": 0, "s": 10, "m": 20, "c": 30}.get(tag, 40))  # khoa theo thoi gian khong dung chung giua cac bac
    if stream == "md.bars":
        for i in range(n):
            ts = BASE + timedelta(minutes=i)
            evs.append(mk_event("bar", {"symbol": "QALOAD", "tf": "M1", "ts_open": ts.isoformat(), "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05, "v": i, "source": "qa"}))
        return evs, "select count(*) from bars where symbol='QALOAD' and source='qa' and ts_open >= $1 and ts_open < $2", (BASE, BASE + timedelta(minutes=n))
    if stream == "md.quotes":
        for i in range(n):
            ts = BASE + timedelta(seconds=i)
            evs.append(mk_event("quote", {"symbol": "QALOAD", "bid": 1.0 + i * 1e-6, "ask": 1.0001 + i * 1e-6, "ts": ts.isoformat(), "source": "qa"}))
        return evs, "select count(*) from quotes where symbol='QALOAD' and source='qa' and ts >= $1 and ts < $2", (BASE, BASE + timedelta(seconds=n))
    if stream == "news.items":
        for i in range(n):
            evs.append(mk_event("news", {"url": f"https://qa.invalid/load/{RUN}/{tag}/{i}", "title": f"QA load {i}", "summary": "x", "published_at": now().isoformat(), "source": "qa", "lang": "en", "symbols": ["QALOAD"], "sentiment": 0.1}))
        return evs, "select count(*) from news_items where url like $1", (f"https://qa.invalid/load/{RUN}/{tag}/%",)
    if stream == "calendar.events":
        for i in range(n):
            evs.append(mk_event("calendar", {"event_id": f"qaload-{RUN}-{tag}-{i}", "country": "XX", "title": f"QA load {i}", "impact": "low", "ts": (now() + timedelta(days=400, minutes=i)).isoformat(), "source": "qa"}))
        return evs, "select count(*) from calendar_events where source='qa' and event_id like $1", (f"qaload-{RUN}-{tag}-%",)
    if stream == "expert.signals":
        for i in range(n):
            evs.append(mk_event("expert_signal", {"expert_id": f"qa-load-{RUN}-{tag}", "source": "qa", "symbol": "QALOAD", "side": "buy", "entry": 1, "sl": 0.9, "tp": 1.2, "opened_at": (BASE + timedelta(minutes=i)).isoformat(), "status": "open"}))
        return evs, "select count(*) from expert_signals where expert_id=$1", (f"qa-load-{RUN}-{tag}",)
    if stream == "expert.positions":
        for i in range(n):
            evs.append(mk_event("expert_position", {"expert_id": f"qa-load-{RUN}-{tag}", "source": "qa", "symbol": "QALOAD", "net_volume": i, "avg_price": 1.0, "as_of": (BASE + timedelta(minutes=i)).isoformat()}))
        return evs, "select count(*) from expert_positions where expert_id=$1", (f"qa-load-{RUN}-{tag}",)
    if stream == "account.snapshots":
        for i in range(n):
            evs.append(mk_event("account_snapshot", {"account_id": f"qa-load-{RUN}-{tag}", "platform": "mt5", "ts": (BASE + timedelta(seconds=i)).isoformat(), "balance": 1000, "equity": 1000 + i, "margin": 0, "positions": []}))
        return evs, "select count(*) from account_snapshots where account_id=$1", (f"qa-load-{RUN}-{tag}",)
    if stream == "alerts.out":
        for i in range(n):
            evs.append(mk_event("alert", {"level": "info", "title": f"QA load {RUN} {tag} {i}", "body": "x", "tags": ["qa", "qaload"], "dedupe_key": f"qaload-{RUN}-{tag}-{i}"}))
        return evs, "select count(*) from alerts where title like $1", (f"QA load {RUN} {tag} %",)
    raise ValueError(stream)


async def drain_stage(c: Ctx, R: Results, stream: str, n: int, tag: str, rate: float | None):
    evs, sql, args = gen(stream, n, tag)
    t_pub: list[float] = []
    t0 = time.time()
    seen_t: list[tuple[float, int]] = []
    done = asyncio.Event()

    pdb = await asyncpg.connect(DSN)

    async def poll():
        last = 0
        while not done.is_set() or last < n:
            v = await pdb.fetchval(sql, *args)
            tt = time.time()
            if v != last:
                seen_t.append((tt, v))
                last = v
            if last >= n or tt - t0 > 240:
                break
            await asyncio.sleep(0.05)
        return last

    pt = asyncio.create_task(poll())
    if rate is None:  # burst
        pubs = await publish_many(c.r, stream, evs, pipe=500)
        t_pub = [t for _, t in pubs]
    else:  # steady
        for i, e in enumerate(evs):
            await publish(c.r, stream, e)
            t_pub.append(time.time())
            await asyncio.sleep(1.0 / rate)
    t_pub_end = time.time()
    done.set()
    last = await pt
    await pdb.close()
    t_end = time.time()
    # do tre theo tung su kien: event k duoc thay khi count>=k+1
    lats = []
    j = 0
    for k in range(min(last, n)):
        while j < len(seen_t) and seen_t[j][1] < k + 1:
            j += 1
        if j < len(seen_t):
            lats.append(max(0.0, seen_t[j][0] - t_pub[k]))
    mode = "burst" if rate is None else f"steady@{rate:.0f}/s"
    s = lat_summary(lats)
    thr = last / (t_end - t0) if t_end > t0 else 0
    ok = last == n
    R.check(f"load/{stream}/{mode}/n={n}/du-so-dong", ok, f"DB={last}/{n}; publish={t_pub_end-t0:.1f}s; xong={t_end-t0:.1f}s; thong luong={thr:.0f} ev/s; tre(s) {s}", "critical" if not ok else "medium")
    R.metric(f"{stream}.{mode}", {"n": n, "db": last, "publish_s": round(t_pub_end - t0, 2), "total_s": round(t_end - t0, 2), "ev_per_s": round(thr), **s})
    return ok


async def load():
    R = Results("load")
    async with Ctx() as c:
        # luu gia tri dlq truoc
        dlq0 = await c.r.xlen("dlq")
        streams = [("md.bars", N), ("md.quotes", N), ("news.items", N), ("calendar.events", N), ("expert.signals", N),
                   ("expert.positions", N), ("account.snapshots", N)] + ([("alerts.out", N_ALERT)] if N_ALERT else [])
        for st, n in streams:
            await drain_stage(c, R, st, n, "b", None)
            await asyncio.sleep(1)
        for st, n in [("md.bars", 300), ("news.items", 300), ("account.snapshots", 300)] + ([("alerts.out", 100)] if N_ALERT else []):
            await drain_stage(c, R, st, n, "s", 50)
        # mixed: dong thoi nhieu stream
        t0 = time.time()
        res = await asyncio.gather(*[drain_stage(c, R, st, 1000, "m", None) for st in ("md.bars", "news.items", "calendar.events", "expert.signals", "account.snapshots")])
        R.metric("mixed.total_s", round(time.time() - t0, 2))
        dlq1 = await c.r.xlen("dlq")
        R.check("load/dlq-khong-tang-do-tai", dlq1 == dlq0, f"{dlq0}->{dlq1}", "high")
        for st in ("md.bars", "news.items"):
            g = [x for x in await c.r.xinfo_groups(st) if x["name"] == "storage-writer"][0]
            R.check(f"load/{st}/ket-thuc-lag=0-pending=0", g["pending"] == 0 and (g.get("lag") or 0) == 0, f"lag={g.get('lag')} pending={g['pending']}", "high")
        h = await c.http.get("http://storage-writer:8000/healthz")
        R.check("load/storage-writer-van-song", h.status_code == 200, "", "high")
    return R.finish()


async def crash():
    """Chay ben trong container; host (run_crash.sh) restart/kill storage-writer khi thay co flag."""
    R = Results("crash")
    n_bar, n_news, n_alert = N, N, int(os.getenv('QA_N_ALERT_CRASH', '0'))
    async with Ctx() as c:
        dlq0 = await c.r.xlen("dlq")
        bars, bsql, bargs = gen("md.bars", n_bar, "c")
        news, nsql, nargs = gen("news.items", n_news, "c")
        alerts, asql, aargs = gen("alerts.out", n_alert, "c")
        # doi bars sang symbol QACRASH
        for e in bars:
            e["payload"]["symbol"] = "QACRASH"
        bsql = bsql.replace("QALOAD", "QACRASH")
        # trung lap: 10% gui lai cung su kien (cung event id) + 5% event id khac cung khoa tu nhien
        dup_same = [bars[i] for i in range(0, n_bar, 10)] + [news[i] for i in range(0, n_news, 10)] + [alerts[i] for i in range(0, n_alert, 10)]
        dup_key = [mk_event("bar", {**bars[i]["payload"], "c": 1.06}) for i in range(0, n_bar, 20)] + \
                  [mk_event("news", {**news[i]["payload"], "title": "QA dup-key"}) for i in range(0, n_news, 20)]
        total = n_bar + n_news + n_alert
        sent = 0
        chunk = 50
        t0 = time.time()
        fl = {30: False, 65: False}
        i = j = k = 0
        while i < n_bar or j < n_news or k < n_alert:
            p = c.r.pipeline(transaction=False)
            cnt = 0
            for e in bars[i:i + chunk]:
                p.xadd("md.bars", {"e": json.dumps(e)}); cnt += 1
            for e in news[j:j + chunk]:
                p.xadd("news.items", {"e": json.dumps(e)}); cnt += 1
            for e in alerts[k:k + 12]:
                p.xadd("alerts.out", {"e": json.dumps(e)}); cnt += 1
            streams = ["md.bars"] * len(bars[i:i + chunk]) + ["news.items"] * len(news[j:j + chunk]) + ["alerts.out"] * len(alerts[k:k + 12])
            ids = await p.execute()
            for st, mid in zip(streams, ids):
                from qalib import _track
                _track(st, mid)
            i += chunk; j += chunk; k += 12
            sent += cnt
            pct_ = sent * 100 // total
            for th in fl:
                if not fl[th] and pct_ >= th:
                    fl[th] = True
                    open(os.path.join(OUT, f"crash_flag_{th}"), "w").write(str(time.time()))
                    print(f"FLAG {th}% sent={sent}", flush=True)
            await asyncio.sleep(0.5)  # ~ 220 ev/s (~ nang luc writer), tong ~50s
        # gui trung lap (cung id) o cuoi + xen giua
        for e in dup_same[:len(dup_same)]:
            st = "md.bars" if e["type"] == "bar" else "news.items" if e["type"] == "news" else "alerts.out"
            await publish(c.r, st, e)
        for e in dup_key:
            await publish(c.r, "md.bars" if e["type"] == "bar" else "news.items", e)
        print(f"published {sent}+{len(dup_same)}+{len(dup_key)} in {time.time()-t0:.1f}s", flush=True)
        # cho hoi phuc
        t_wait = time.time()
        res = {}
        while time.time() - t_wait < 180:
            res = {"bars": await c.db.fetchval(bsql, *bargs), "news": await c.db.fetchval(nsql, *nargs), "alerts": (await c.db.fetchval(asql, *aargs)) if n_alert else 0}
            if res["bars"] == n_bar and res["news"] == n_news and res["alerts"] == n_alert:
                break
            await asyncio.sleep(0.5)
        rec = time.time() - t_wait
        await asyncio.sleep(3)
        res = {"bars": await c.db.fetchval(bsql, *bargs), "news": await c.db.fetchval(nsql, *nargs), "alerts": (await c.db.fetchval(asql, *aargs)) if n_alert else 0}
        R.check("crash/khong-mat-bars", res["bars"] == n_bar, f"{res['bars']}/{n_bar}", "critical")
        R.check("crash/khong-mat-news", res["news"] == n_news, f"{res['news']}/{n_news}", "critical")
        if n_alert:
            R.check("crash/khong-mat-alerts", res["alerts"] == n_alert, f"{res['alerts']}/{n_alert}", "critical")
        # khong trung (khoa tu nhien): dem phan biet
        d = await c.db.fetchrow("select count(*) n, count(distinct ts_open) u from bars where symbol='QACRASH' and source='qa'")
        R.check("crash/khong-trung-bars", d["n"] == d["u"] == n_bar, f"rows={d['n']} distinct={d['u']}", "critical")
        d = await c.db.fetchrow("select count(*) n, count(distinct url) u from news_items where url like $1", nargs[0])
        R.check("crash/khong-trung-news", d["n"] == d["u"] == n_news, f"rows={d['n']} distinct={d['u']}", "critical")
        if n_alert:
            d = await c.db.fetchrow("select count(*) n, count(distinct event_id) u from alerts where title like $1", aargs[0])
            R.check("crash/khong-trung-alerts(event_id)", d["n"] == d["u"] == n_alert, f"rows={d['n']} distinct={d['u']}", "critical")
        # doi drain het (ke ca ban trung lap gui cuoi)
        t_dr = time.time()
        while time.time() - t_dr < 90:
            gl = [[x for x in await c.r.xinfo_groups(st) if x["name"] == "storage-writer"][0] for st in ("md.bars", "news.items")]
            if all(g["pending"] == 0 and (g.get("lag") or 0) == 0 for g in gl):
                break
            await asyncio.sleep(1)
        R.metric("crash.drain_them_s", round(time.time() - t_dr, 1))
        d = await c.db.fetchval("select count(*) from bars where symbol='QACRASH' and source='qa' and c=1.06")
        R.check("crash/upsert-khoa-tu-nhien-ghi-de-250-bars", d == len(range(0, n_bar, 20)), f"{d} dong c=1.06 (ky vong {len(range(0, n_bar, 20))}; event id khac nhau, cung khoa, gui sau cung)", "high")
        d = await c.db.fetchval("select count(*) from news_items where url like $1 and title='QA dup-key'", nargs[0])
        R.check("crash/upsert-news-theo-url-250", d == len(range(0, n_news, 20)), f"{d}", "high")
        for st in ("md.bars", "news.items"):
            g = [x for x in await c.r.xinfo_groups(st) if x["name"] == "storage-writer"][0]
            R.check(f"crash/{st}/pending=0,lag=0", g["pending"] == 0 and (g.get("lag") or 0) == 0, f"lag={g.get('lag')} pending={g['pending']} consumers={g['consumers']}", "high")
        dlq1 = await c.r.xlen("dlq")
        R.check("crash/dlq-khong-tang", dlq1 == dlq0, f"{dlq0}->{dlq1}", "high")
        R.metric("crash.thoi_gian_hoi_phuc_s", round(rec, 1))
        # consumer cu (sau restart ten cung 'sw-1' nen khong tao thanh vien ma)
        gs = (await c.r.xinfo_consumers("md.bars", "storage-writer"))
        R.info("crash/consumers", str([(x["name"], x["pending"], x["idle"]) for x in gs]))
    return R.finish()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "load"
    raise SystemExit(asyncio.run(load() if mode == "load" else crash()))
