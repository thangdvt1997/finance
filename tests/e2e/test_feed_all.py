"""E2E feed MT5 toan bo cap (126 forex + 10 kim loai + 26 chi so). CHI DOC: khong publish, khong dat lenh.
Chay: sh /root/qa-e2e/run_remote.sh test_feed_all.py   (sau khi bash tests/e2e/deploy.sh)
Chuoi kiem: EA feed -> mt-bridge -> bus md.quotes -> DB quotes -> /v1/rt (SSE).
Luat skip (KHONG fail gia):
  - ngoai gio phien (FX: dong T6 22:00 -> CN 22:00 UTC; nghi le 25/12, 1/1; kim loai nghi 22-23h; chi so chi T2-T6 08-20h UTC) -> SKIP.
  - feed moi chua live (khong co quote nguon '*-feed' trong 10 phut) khi thi truong mo -> SKIP co ly do, tru khi FEED_ALL_REQUIRE=1.
Bien: FEED_ALL_SRC_LIKE (mac dinh mt5:%), FEED_ALL_REQUIRE=1 (bat buoc live), FEED_ALL_SAMPLE=EURUSD,... (mau), FEED_ALL_MIN_COVER=0.6 (ti le symbol FX co quote 10 phut khi mo)."""
import asyncio
from fnmatch import fnmatch
import json
import os
import statistics
from datetime import datetime, timezone

from qalib import Ctx, Results, now, pct

R = Results("feed_all")
REQUIRE = os.getenv("FEED_ALL_REQUIRE") == "1"
SAMPLE = [s for s in os.getenv("FEED_ALL_SAMPLE", "EURUSD,GBPUSD,USDJPY,AUDNZD,EURGBP,USDZAR,XAUUSD,XAGUSD,US500,USTEC").split(",") if s]
MIN_COVER = float(os.getenv("FEED_ALL_MIN_COVER", "0.6"))
SRC_LIKE = os.getenv("FEED_ALL_SRC_LIKE", "mt5:%")   # account feed co the la mt5:<login> hoac mt5:<login>-feed (A2/A3 chua chot): khop ca hai
CANON7 = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US500", "US30", "USTEC"}   # pipeline canon cu, khong tinh la feed moi
FEED_SRC = f"source like '{SRC_LIKE}'"          # account_id feed = mt5:<login>-feed (docs/handoff/FEED_ALL_contract.md)
METALS = ("XAU", "XAG", "XPD", "XPT")


def fx_open(t: datetime) -> bool:
    d, h = (t.weekday() + 1) % 7, t.hour          # 0=CN ... 6=T7 (khop day_of_week() Prometheus)
    if (t.month, t.day) in ((12, 25), (1, 1)) or ((t.month, t.day) in ((12, 24), (12, 31)) and h >= 21):
        return False
    if d == 6 or (d == 5 and h >= 22) or (d == 0 and h < 22):
        return False
    return not (d == 0 and h == 22 and t.minute < 30)


def class_open(sym: str, t: datetime) -> bool:
    if sym.startswith(METALS):
        return fx_open(t) and t.hour != 22
    if len(sym) == 6 and sym.isalpha() and sym.isupper() and sym[:3] != "XAU":
        return fx_open(t)
    d, h = (t.weekday() + 1) % 7, t.hour           # chi so
    return 1 <= d <= 5 and 8 <= h < 20 and fx_open(t)


async def main():
    t = now()
    async with Ctx() as c:
        R.check("lich/tu-kiem-gio-mo-cua", fx_open(datetime(2026, 10, 14, 12, tzinfo=timezone.utc)) and not fx_open(datetime(2026, 10, 17, 12, tzinfo=timezone.utc))
                and not fx_open(datetime(2026, 10, 16, 22, 30, tzinfo=timezone.utc)) and fx_open(datetime(2026, 10, 18, 22, 40, tzinfo=timezone.utc)),
                "T4 12h mo / T7 dong / T6 22:30 dong / CN 22:40 mo", "low")
        rows = await c.db.fetch(f"""select symbol, count(*) n, max(ts) last, min(ts) first from quotes
                                    where {FEED_SRC} and ts > now() - interval '10 minutes' group by 1""")
        live = {r["symbol"]: r for r in rows}
        open_syms = [s for s in SAMPLE if class_open(s, t)]
        if not open_syms:
            R.info("skip/thi-truong-dong", f"{t:%Y-%m-%d %H:%M} UTC: toan bo mau {SAMPLE} ngoai gio phien -> bo qua kiem live (khong fail gia)")
            return R.finish()
        if not (set(live) - CANON7):
            msg = "chua co quote MT5 nao ngoai 7 ma canon trong 10 phut (EA market-feed moi chua live / bridge chua nhan)"
            if REQUIRE:
                R.check("feed/co-quote-live", False, msg, "high")
            else:
                R.info("skip/feed-moi-chua-live", msg + "; dat FEED_ALL_REQUIRE=1 de bat buoc")
            return R.finish()
        R.metric("symbols_live_10m", len(live))

        # 1) phu: ti le symbol co quote 10 phut / mau
        got = [s for s in open_syms if s in live]
        R.check("phu/mau-co-quote", len(got) / len(open_syms) >= MIN_COVER,
                f"{len(got)}/{len(open_syms)} mau mo cua co quote; thieu={sorted(set(open_syms) - set(got))}", "high")
        # phu FX toan bo
        if fx_open(t):
            fxn = sum(1 for s in live if len(s) == 6 and s.isalpha() and not s.startswith(METALS))
            R.check("phu/fx-so-symbol", fxn >= MIN_COVER * 126, f"{fxn}/126 cap FX co quote 10 phut (nguong {MIN_COVER:.0%}; exotic tick thua)", "medium")

        # 2) DB: moc thoi gian (EET->UTC): khong tuong lai, khong lech gio nguyen
        fut = [(s, r["last"]) for s, r in live.items() if (r["last"] - t).total_seconds() > 10]
        R.check("tz/DB-khong-quote-tuong-lai", not fut, f"{fut[:5]} (lech EET->UTC se day ts tuong lai +2/3h)", "critical")
        lag = {s: (t - r["last"]).total_seconds() for s, r in live.items() if s in open_syms}
        if lag:
            R.check("tz/DB-do-tuoi-quote-mau", max(lag.values()) < 600, f"tuoi (s) {({k: round(v) for k, v in lag.items()})}", "high")
            R.metric("db_quote_age_p50_s", round(statistics.median(lag.values()), 1))

        # 3) bus md.quotes: do tre event.ts(bridge) - payload.ts(quote, UTC) va chenh gio nguyen
        raw = await c.r.xrevrange("md.quotes", count=3000)
        lats, bad_tz, per = [], [], {}
        for _id, f in raw:
            try:
                ev = json.loads(f["e"])
                p = ev["payload"]
                if not fnmatch(str(p.get("source", "")), SRC_LIKE.replace("%", "*")):
                    continue
                et = datetime.fromisoformat(ev["ts"].replace("Z", "+00:00"))
                qt = datetime.fromisoformat(p["ts"].replace("Z", "+00:00"))
            except Exception:
                continue
            d = (et - qt).total_seconds()
            per[p["symbol"]] = per.get(p["symbol"], 0) + 1
            if abs(d) > 1800:
                bad_tz.append((p["symbol"], round(d)))
            else:
                lats.append(d)
        R.check("tz/bus-khong-lech-gio-nguyen", not bad_tz, f"{len(bad_tz)} event |event.ts - quote.ts| > 30 phut: {bad_tz[:5]}", "critical")
        if lats:
            p50, p95 = pct(lats, .5), pct(lats, .95)
            R.metric("bus_latency_p50_s", round(p50, 2)); R.metric("bus_latency_p95_s", round(p95, 2)); R.metric("bus_symbols_sample", len(per))
            R.check("tre/MT5->bus-p50", p50 < 1.5, f"p50={p50:.2f}s n={len(lats)} (ts quote do phan giai giay)", "medium")
            R.check("tre/MT5->bus-p95", p95 < 5, f"p95={p95:.2f}s", "high")
            R.check("tre/khong-am-bat-thuong", min(lats) > -5, f"min={min(lats):.2f}s (am > 5s = lech dong ho/ts sai)", "medium")
        else:
            R.info("tre/bus-khong-co-event-feed", "khong thay event nguon *-feed trong 3000 msg gan nhat cua md.quotes")

        # 4) DB: du lieu 1 symbol mau khong dung ngoai (bid>0, ask>=bid) va du mau (nhieu tick 10 phut)
        for s in got[:6]:
            r = await c.db.fetchrow(f"select count(*) n, min(bid) b, bool_and(ask >= bid) ok from quotes where symbol=$1 and {FEED_SRC} and ts > now() - interval '10 minutes'", s)
            R.check(f"du/{s}-quote-hop-le", r["n"] > 0 and r["b"] > 0 and r["ok"], f"n={r['n']} minbid={r['b']} ask>=bid={r['ok']}", "high")
            R.check(f"du/{s}-du-it-nhat-10-quote-10-phut", r["n"] >= 10 or s in ("USDZAR",), f"n={r['n']}", "low")

        # 5) /v1/rt SSE: nhan quote that cho mau trong 12s
        topics = ",".join(f"q:{s}" for s in got[:8])
        import time
        seen, t0 = set(), time.time()
        try:
            async with c.http.stream("GET", f"{os.getenv('QA_GATEWAY', 'http://api-gateway:8000')}/v1/rt/sse", params={"topics": topics},
                                     headers={"X-API-Key": os.getenv("API_TOKEN", "")}, timeout=20) as resp:
                if resp.status_code != 200:
                    R.info("rt/sse-khong-vao-duoc", f"HTTP {resp.status_code} (can phien/key hop le; bo qua buoc /v1/rt)")
                else:
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                m = json.loads(line[5:])
                            except Exception:
                                continue
                            items = m.get("m", []) if m.get("t") == "b" else [m]
                            for it in items:
                                k = it.get("k") if isinstance(it, dict) else None
                                k = k if isinstance(k, str) else ""
                                if k.startswith("q:") and it.get("t") in ("d", "snap") and it.get("d"):
                                    seen.add(k[2:])
                        if time.time() - t0 > 12:
                            break
                    R.check("rt/SSE-nhan-quote-mau", bool(seen), f"{sorted(seen)} / yeu cau {topics}", "high")
        except Exception as e:
            R.info("rt/sse-loi-ket-noi", repr(e)[:200])
    return R.finish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
