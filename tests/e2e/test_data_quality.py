"""Chat luong du lieu that: nen Dukascopy vs ECB(Frankfurter), scale, OHLC hop le, khoang trong, mui gio,
nen nhieu khung nhat quan (M1->M5/M15/H1/H4/D1), vnstock, tin tuc, lich kinh te.  CHI DOC du lieu that."""
import asyncio
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

import httpx

from qalib import Ctx, Results, now

R = Results("data_quality")
FX = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
RANGE = {"EURUSD": (0.8, 1.6), "GBPUSD": (1.0, 1.9), "USDJPY": (90, 200), "XAUUSD": (1000, 10000)}
TFS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
REAL = "source <> 'qa' AND symbol NOT LIKE 'QA%'"


def utc(d):
    return d.astimezone(timezone.utc)


async def ohlc_scale(c: Ctx):
    rows = await c.db.fetch(f"""select source, tf, count(*) n,
        count(*) filter (where l > least(o,c) or h < greatest(o,c) or l > h) bad_ohlc,
        count(*) filter (where o<=0 or h<=0 or l<=0 or c<=0) nonpos,
        count(*) filter (where v < 0) negv,
        count(*) filter (where ts_open > now()) future,
        count(*) filter (where o='NaN' or h='NaN' or l='NaN' or c='NaN') nan
        from bars where {REAL} group by 1,2 order by 1,2""")
    tot = sum(r["n"] for r in rows)
    bad = [(r["source"], r["tf"], r["bad_ohlc"], r["nonpos"], r["negv"], r["future"], r["nan"]) for r in rows
           if r["bad_ohlc"] or r["nonpos"] or r["negv"] or r["future"] or r["nan"]]
    R.check("ohlc/hop-le-toan-bang", not bad, f"{tot} nen; vi pham (source,tf,low>.., <=0, v<0, tuong lai, NaN)={bad[:8]}", "high")
    for sym in FX:
        for tf in ("M1", "D1"):
            r = await c.db.fetchrow("select min(c) lo, max(c) hi, count(*) n from bars where symbol=$1 and tf=$2 and source='dukascopy'", sym, tf)
            if not r["n"]:
                continue
            lo, hi = RANGE[sym]
            R.check(f"scale/{sym}/{tf}", lo <= r["lo"] and r["hi"] <= hi, f"min={r['lo']:.5g} max={r['hi']:.5g} (ky vong {lo}-{hi}) n={r['n']}", "critical")
    # do rong nen bat thuong (high-low / close) -> phat hien spike / sai scale
    for sym in FX:
        r = await c.db.fetchrow("select max((h-l)/c) mx, avg((h-l)/c) av, count(*) n from bars where symbol=$1 and tf='M1' and source='dukascopy'", sym)
        if r["n"]:
            R.check(f"spike/{sym}/M1-range", r["mx"] < 0.01, f"max (h-l)/c = {r['mx']*100:.3f}% avg={r['av']*100:.4f}%", "medium")
    # nhay gia giua 2 nen M1 lien tiep
    for sym in FX:
        rows = await c.db.fetch("select ts_open, c, o from bars where symbol=$1 and tf='M1' and source='dukascopy' order by ts_open", sym)
        worst = (0, None)
        for a, b in zip(rows, rows[1:]):
            if (b["ts_open"] - a["ts_open"]).total_seconds() == 60:
                j = abs(b["o"] - a["c"]) / a["c"]
                if j > worst[0]:
                    worst = (j, b["ts_open"])
        if rows:
            R.check(f"spike/{sym}/M1-lien-tiep", worst[0] < 0.005, f"nhay lon nhat close->open = {worst[0]*100:.3f}% tai {worst[1]}", "medium")


async def vs_ecb(c: Ctx):
    days = [r["d"] for r in await c.db.fetch(
        "select distinct (ts_open at time zone 'UTC')::date d from bars where source='dukascopy' and tf in ('M1','H1') and symbol=any($1) order by 1", FX)]
    if not days:
        R.info("ecb", "khong co ngay nao")
        return
    d0, d1 = min(days), max(days)
    ecb = None
    for base in ("https://api.frankfurter.dev/v1", "https://api.frankfurter.app"):
        try:
            r = await c.http.get(f"{base}/{d0}..{d1}", params={"base": "EUR", "symbols": "USD,GBP,JPY"})
            if r.status_code == 200:
                ecb = r.json()["rates"]
                R.info("ecb/nguon", f"{base} {len(ecb)} ngay {d0}..{d1}")
                break
        except Exception as e:
            R.info("ecb/loi", repr(e))
    if not ecb:
        R.check("ecb/tai-duoc-du-lieu", False, "khong goi duoc Frankfurter", "medium")
        return
    # ECB fix ~14:15 CET/CEST: chuyen sang UTC theo mui gio Europe/Berlin
    def fix_utc(d):
        return datetime(d.year, d.month, d.day, 14, 15, tzinfo=ZoneInfo("Europe/Berlin")).astimezone(timezone.utc)

    def ecb_pair(day, sym):
        x = ecb.get(str(day))
        if not x:
            return None
        if sym == "EURUSD":
            return x["USD"]
        if sym == "GBPUSD":
            return x["USD"] / x["GBP"]
        if sym == "USDJPY":
            return x["JPY"] / x["USD"]

    summary = {}
    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        diffs, d1diffs, det = [], [], []
        for day in days:
            ref = ecb_pair(day, sym)
            if ref is None:
                continue
            f = fix_utc(day)
            m = await c.db.fetchrow("select c, ts_open from bars where symbol=$1 and tf='M1' and source='dukascopy' and ts_open between $2 and $3 order by abs(extract(epoch from ts_open - $4)) limit 1",
                                    sym, f - timedelta(minutes=3), f + timedelta(minutes=3), f)
            if m is None:  # fallback H1
                m = await c.db.fetchrow("select c, ts_open from bars where symbol=$1 and tf='H1' and source='dukascopy' and ts_open = $2", sym, f.replace(minute=0))
            if m:
                dd = (m["c"] - ref) / ref * 100
                diffs.append(abs(dd))
                det.append((str(day), round(ref, 5), round(m["c"], 5), round(dd, 3)))
            dc = await c.db.fetchrow("select c from bars where symbol=$1 and tf='D1' and source='dukascopy' and ts_open=$2", sym, datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
            if dc:
                d1diffs.append(abs((dc["c"] - ref) / ref * 100))
        summary[sym] = det
        if diffs:
            R.check(f"ecb/{sym}/gia-luc-fix-lech<=0.3%", max(diffs) <= 0.3, f"{len(diffs)} ngay, max={max(diffs):.3f}% mean={statistics.mean(diffs):.3f}% chi tiet={det}", "high")
        else:
            R.info(f"ecb/{sym}", "khong co ngay trung de so sanh")
        if d1diffs:
            R.info(f"ecb/{sym}/D1-close-vs-ECB", f"{len(d1diffs)} ngay, max={max(d1diffs):.3f}% (close cuoi ngay vs fix 14:15 CET, tham khao)")
    # Frankfurter trong DB phai khop API
    rows = await c.db.fetch("select symbol, ts_open, c from bars where source='frankfurter' and tf='D1'")
    mism = []
    for r in rows:
        ref = ecb_pair(r["ts_open"].date(), r["symbol"]) if r["symbol"] in ("EURUSD", "GBPUSD", "USDJPY") else None
        if ref is not None and abs(r["c"] - ref) / ref > 1e-4:
            mism.append((r["symbol"], str(r["ts_open"].date()), r["c"], ref))
    R.check("ecb/frankfurter-trong-DB-khop-API", not mism and rows, f"{len(rows)} dong, lech={mism[:5]}", "high")
    # ECB range quet rong hon: ngay Dukascopy khong co -> bao
    have = defaultdict(set)
    for r in await c.db.fetch("select symbol, (ts_open at time zone 'UTC')::date d from bars where source='dukascopy' and tf='M1' group by 1,2"):
        have[r["symbol"]].add(r["d"])
    wk = [d for d in (d0 + timedelta(i) for i in range((d1 - d0).days + 1)) if d.weekday() < 5]
    miss = {s: [str(d) for d in wk if d not in have[s]] for s in FX}
    R.info("coverage/ngay-thieu-M1 (backfill co the dang chay)", json.dumps(miss))


async def freshness(c: Ctx):
    n = now()
    # lan dong cua gan nhat (T6 21:00 UTC mua he My; 22:00 mua dong) neu thi truong dang dong, nguoc lai bay gio
    close = (n - timedelta(days=(n.weekday() - 4) % 7)).replace(hour=21, minute=0, second=0, microsecond=0)
    closed = (n.weekday() == 5) or (n.weekday() == 4 and n.hour >= 21) or (n.weekday() == 6 and n.hour < 23)  # CN: mo cua 21-22h UTC, du lieu den tre ~1h => coi la dong den 23h UTC
    ref = close if closed else n
    # Vong 5 (FEED): chuoi HIEU LUC = cai moi duong doc thay (DISTINCT ON (ts_open) ORDER BY source): canon (feed EA, tre ~1-2')
    # uu tien, dukascopy du phong (tre cau truc 80-100'). Dung sai M1 hieu luc siet 120 -> 5 phut; du phong giu 120.
    for sym in FX:
        for tf, tol, srcs, cid, sev in (("M1", 5, ("canon:%", "dukascopy"), "moi-nhat", "high" if sym == "EURUSD" else "medium"),
                                        ("M1", 120, ("dukascopy",), "du-phong-moi-nhat", "low"),
                                        ("D1", 24 * 60, ("canon:%", "dukascopy"), "moi-nhat", "medium")):
            r = await c.db.fetchval("select max(ts_open) from bars where symbol=$1 and tf=$2 and source like any($3::text[]) and ts_open > now() - interval '10 days'", sym, tf, list(srcs))
            lag = (ref - r).total_seconds() / 60 if r else None
            R.check(f"fresh/{sym}/{tf}-{cid}", r is not None and lag <= tol,
                    f"nen cuoi {r}; tham chieu {'dong cua T6' if closed else 'bay gio'} {ref:%Y-%m-%d %H:%M}; tre {lag:.0f} phut (cho phep {tol})" if r else "khong co nen", sev)
            if tf == "M1" and cid == "moi-nhat" and r is not None:
                R.metric(f"fresh_m1_lag_min_{sym}", round(lag, 1))
    for sym in ("US500", "US30", "USTEC"):   # chi so: chi co tu feed EA; gio nghi rieng -> chi ghi nhan
        r = await c.db.fetchval("select max(ts_open) from bars where symbol=$1 and tf='M1' and source like 'canon:%' and ts_open > now() - interval '10 days'", sym)
        R.info(f"fresh/{sym}/M1", f"nen cuoi {r}" + (f"; tre {(n - r).total_seconds() / 60:.0f} phut" if r else ""))
    for st, col, tab in (("news", "coalesce(published_at, ingested_at)", "news_items"), ("calendar", "updated_at", "calendar_events")):
        r = await c.db.fetchval(f"select max({col}) from {tab} where source <> 'qa'")
        R.info(f"fresh/{st}", f"moi nhat {r} (tre {(n - r).total_seconds()/3600:.1f}h)")


async def xau_ref(c: Ctx):
    # XAUUSD khong co o ECB. Thu Stooq (tuy chon) de doi chieu D1.
    try:
        r = await c.http.get("https://stooq.com/q/d/l/?s=xauusd&i=d", headers={"User-Agent": "qa-e2e/0.1"})
        if r.status_code == 200 and r.text.startswith("Date"):
            ref = {ln.split(",")[0]: float(ln.split(",")[4]) for ln in r.text.strip().splitlines()[1:]}
            rows = await c.db.fetch("select ts_open, c from bars where symbol='XAUUSD' and tf='D1' and source='dukascopy'")
            diffs = []
            for x in rows:
                k = str(x["ts_open"].date())
                if k in ref:
                    diffs.append((k, round(x["c"], 2), ref[k], round(abs(x["c"] - ref[k]) / ref[k] * 100, 3)))
            R.info("xau/stooq-D1", json.dumps(diffs))
            if diffs:
                R.check("xau/D1-close-vs-stooq<=1%", max(d[3] for d in diffs) <= 1.0, str(diffs), "medium")
        else:
            R.info("xau/stooq", f"khong dung duoc ({r.status_code}); XAUUSD chi kiem scale + nhat quan noi bo")
    except Exception as e:
        R.info("xau/stooq", f"loi {e!r}; XAUUSD chi kiem scale + nhat quan noi bo")


async def tf_consistency(c: Ctx):
    await _tf_consistency(c, "dukascopy", "")
    src = await c.db.fetchval("select source from bars where source like 'canon:%' and tf='M1' and ts_open > now() - interval '3 days' limit 1")
    if src:
        await _tf_consistency(c, src, "canon/")
    # khong xen ke: moi nen H4/D1 FX (MOI nguon) phai theo moc UTC - nen H4/D1 gio server broker lam vo chuoi DISTINCT ON
    for tf, cond in (("H4", "extract(hour from ts_open)::int % 4 <> 0 or extract(minute from ts_open) <> 0"), ("D1", "ts_open::time <> '00:00'")):
        bad = await c.db.fetch(f"select source, count(*) n from bars where tf='{tf}' and symbol = any($1::text[]) and ({cond}) and ts_open > now() - interval '400 days' group by 1", FX + ["US500", "US30", "USTEC"])
        R.check(f"tz/align-{tf}-UTC-moi-nguon", not bad, f"lech moc={[(x['source'], x['n']) for x in bad]}", "high")


async def _tf_consistency(c: Ctx, source: str, tag: str):
    """canon: bucket do dang (dau phien / EA offline) va bucket dang chay KHONG duoc phat -> 'thieu' chi ghi nhan; lech/ngoai bien van la loi."""
    for sym in FX:
        rows = await c.db.fetch("select ts_open, o,h,l,c,v from bars where symbol=$1 and tf='M1' and source=$2 and ts_open > now() - interval '30 days' order by ts_open", sym, source)
        if not rows:
            continue
        m1 = {utc(r["ts_open"]): r for r in rows}
        for tf in ("M5", "M15", "H1", "H4", "D1"):
            sec = TFS[tf]
            stored = {utc(r["ts_open"]): r for r in await c.db.fetch("select ts_open,o,h,l,c,v from bars where symbol=$1 and tf=$2 and source=$3 and ts_open > now() - interval '31 days'", sym, tf, source)}
            buckets = defaultdict(list)
            for ts, r in m1.items():
                b = datetime.fromtimestamp((ts.timestamp() // sec) * sec, tz=timezone.utc)
                buckets[b].append((ts, r))
            full = cmp_ = mism = bound_bad = missing = 0
            ex = []
            for b, lst in buckets.items():
                lst.sort(key=lambda x: x[0])
                s = stored.get(b)
                if s is None:
                    missing += 1
                    continue
                o, h, l, cl = lst[0][1]["o"], max(x[1]["h"] for x in lst), min(x[1]["l"] for x in lst), lst[-1][1]["c"]
                v = sum(x[1]["v"] for x in lst)
                if s["h"] < h - 1e-9 or s["l"] > l + 1e-9:
                    bound_bad += 1
                if len(lst) == sec // 60:
                    full += 1
                    tol = max(abs(cl), 1) * 1e-7
                    if abs(s["o"] - o) > tol or abs(s["h"] - h) > tol or abs(s["l"] - l) > tol or abs(s["c"] - cl) > tol or abs(s["v"] - v) > max(1e-6, abs(v) * 1e-4):
                        mism += 1
                        if len(ex) < 2:
                            ex.append((str(b), (o, h, l, cl, round(v, 2)), (s["o"], s["h"], s["l"], s["c"], round(s["v"], 2))))
                cmp_ += 1
            R.check(f"tf/{tag}{sym}/{tf}-khop-M1", mism == 0 and bound_bad == 0 and (missing == 0 or bool(tag)),
                    f"bucket={len(buckets)} day-du={full} lech={mism} h/l-ngoai-bien={bound_bad} thieu-nen-{tf}={missing} vd={ex}", "high")


async def gaps_tz(c: Ctx):
    for sym in FX:
        rows = await c.db.fetch("select ts_open from bars where symbol=$1 and tf='M1' and source='dukascopy' order by ts_open", sym)
        if len(rows) < 2:
            continue
        gaps = []
        for a, b in zip(rows, rows[1:]):
            dt_ = (b["ts_open"] - a["ts_open"]).total_seconds()
            if dt_ > 300:
                gaps.append((a["ts_open"], b["ts_open"], dt_ / 60))
        weekend = [g for g in gaps if g[0].weekday() == 4 and g[1].weekday() == 6]

        def benign(g):  # nghi hang ngay cua vang (~21-22h UTC) va thanh khoan mong 90' dau phien Chu Nhat
            a = utc(g[0])
            if sym == "XAUUSD" and a.hour == 20 and a.minute == 59 and 55 <= g[2] <= 65:
                return True
            return a.weekday() == 6 and a.hour in (21, 22) and g[2] <= 10
        abnormal = [g for g in gaps if g not in weekend and not benign(g)]
        # gio dong cua/mo cua theo UTC (forex: T6 21:00/22:00 -> CN 21:00/22:00)
        wk = [(utc(g[0]).strftime("%a %H:%M"), utc(g[1]).strftime("%a %H:%M"), round(g[2])) for g in weekend]
        ab = [(str(utc(g[0])), str(utc(g[1])), round(g[2])) for g in abnormal]
        ok = len(abnormal) == 0
        R.check(f"gap/{sym}/M1-khong-co-khoang-trong-bat-thuong(>5')", ok, f"{len(rows)} nen; {len(gaps)-len(abnormal)} khoang trong binh thuong (cuoi tuan/nghi vang/CN-mo-cua mong); bat thuong={ab[:5]}", "medium" if sym != "XAUUSD" else "low")
        # nen vao ngay thu 7 / sau dong cua
        sat = sum(1 for r in rows if utc(r["ts_open"]).weekday() == 5)
        fri_late = sum(1 for r in rows if utc(r["ts_open"]).weekday() == 4 and utc(r["ts_open"]).hour >= 22)
        sun_early = sum(1 for r in rows if utc(r["ts_open"]).weekday() == 6 and utc(r["ts_open"]).hour < 20)
        R.check(f"tz/{sym}/khong-co-nen-trong-gio-dong-cua-cuoi-tuan", sat == 0 and fri_late == 0 and sun_early == 0, f"thu7={sat} thu6>=22h={fri_late} CN<20h={sun_early}", "high")
    # canh nen: tf align
    for tf, cond in {"M5": "extract(minute from ts_open)::int % 5 <> 0", "M15": "extract(minute from ts_open)::int % 15 <> 0",
                     "H1": "extract(minute from ts_open) <> 0", "H4": "extract(hour from ts_open)::int % 4 <> 0 or extract(minute from ts_open) <> 0",
                     "D1": "ts_open::time <> '00:00'", "M1": "false"}.items():
        n = await c.db.fetchval(f"select count(*) from bars where tf='{tf}' and source='dukascopy' and (extract(second from ts_open) <> 0 or {cond})")
        R.check(f"tz/align-{tf}-UTC", n == 0, f"lech={n}", "high")
    # D1 theo ngay lich UTC: co nen D1 ngay CN?
    for sym in FX:
        r = await c.db.fetch("select ts_open, v from bars where symbol=$1 and tf='D1' and source='dukascopy' and extract(dow from ts_open)=0", sym)
        if r:
            # Vong 4: D1 = ngay lich UTC la HOP DONG da chot (CONTRACTS md.bars, HUONG_DAN_SU_DUNG) -> nen CN ~3h la hop le,
            # khong con la loi; D1 kieu broker (dong 17:00 NY) lay tu du lieu MT5 (docs/handoff/MT5_status.md)
            R.info(f"d1/{sym}/nen-D1-ngay-Chu-Nhat(D1-theo-ngay-UTC)", f"{len(r)} nen D1 vao Chu Nhat (~3h phien Sydney 21-24h UTC), dung hop dong")
    # DST: mo cua CN theo UTC (Oct 2026 la gio he My -> 21:00)
    for sym in ("EURUSD", "GBPUSD"):
        r = await c.db.fetch("select min(ts_open) f from bars where symbol=$1 and tf='M1' and source='dukascopy' and extract(dow from ts_open)=0 group by (ts_open at time zone 'UTC')::date", sym)
        R.info(f"tz/{sym}/gio-mo-cua-CN-UTC", str([utc(x['f']).strftime('%a %H:%M') for x in r]))


async def vnstock(c: Ctx):
    rows = await c.db.fetch("select symbol, ts_open, o,h,l,c,v from bars where source='vnstock' and tf='D1' order by symbol, ts_open")
    by = defaultdict(list)
    for r in rows:
        by[r["symbol"]].append(r)
    for sym, lst in by.items():
        closes = [x["c"] for x in lst]
        med = statistics.median(closes)
        unit = "dong (VND)" if med > 1000 else "nghin dong (x1000 VND)"
        R.check(f"vn/{sym}/don-vi-VND-theo-san (khong x1000)", med > 1000,
                f"close median={med:g}: luu theo NGHIN DONG (vd {closes[-1]} = {closes[-1]*1000:,.0f} VND). Hop dong CONTRACTS khong ghi don vi; consumer tron voi gia VND se sai 1000 lan -> chuan hoa x1000 hoac ghi ro", "medium")
        R.info(f"vn/{sym}/don-vi", f"close median={med:g} => don vi {unit}; ngay={[str(x['ts_open'].date()) for x in lst]}; closes={closes}; vol={[x['v'] for x in lst]}")
        R.check(f"vn/{sym}/ngay-khong-roi-cuoi-tuan", all(x["ts_open"].weekday() < 5 for x in lst), "", "medium")
        jumps = [abs(b["c"] / a["c"] - 1) for a, b in zip(lst, lst[1:])]
        R.check(f"vn/{sym}/bien-do-ngay<=7%(HOSE)", all(j <= 0.075 for j in jumps), f"max={max(jumps)*100:.2f}%" if jumps else "", "medium")
    # doi chieu doc lap: VNDirect public API (don vi nghin dong) va TCBS
    ref = {}
    for sym in by:
        code = sym.split(":")[1]
        try:
            r = await c.http.get("https://finfo-api.vndirect.com.vn/v4/stock_prices", params={"q": f"code:{code}~date:gte:{(now()-timedelta(days=14)).date()}", "size": 20, "sort": "date"},
                                 headers={"User-Agent": "Mozilla/5.0 qa-e2e"})
            if r.status_code == 200:
                ref[sym] = {x["date"]: x for x in r.json().get("data", [])}
        except Exception as e:
            R.info(f"vn/{sym}/vndirect", repr(e))
    if not ref:
        R.info("vn/doi-chieu-doc-lap", "VNDirect khong truy cap duoc tu VPS; bo qua doi chieu doc lap")
    for sym, byday in ref.items():
        lst = by[sym]
        out = []
        for x in lst:
            d = str(x["ts_open"].date())
            if d in byday:
                rc = byday[d]["close"]
                out.append((d, x["c"], rc, round(x["c"] / rc, 3)))
        R.info(f"vn/{sym}/vs-VNDirect(close,ref,ratio)", str(out))
        if out:
            ratios = [o[3] for o in out]
            R.check(f"vn/{sym}/gia-khop-VNDirect(cho phep ratio 1 hoac 1000)", all(abs(r - 1) < 0.01 or abs(r - 1000) < 10 for r in ratios), str(out), "high")


def norm_url(u: str) -> str:
    p = urlsplit(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref"))]
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}" + ("?" + urlencode(sorted(q)) if q else "")


async def news_quality(c: Ctx):
    rows = await c.db.fetch("select url,title,summary,published_at,source,lang,symbols,sentiment,ingested_at from news_items where source<>'qa'")
    R.info("news/tong", f"{len(rows)} tin; theo nguon={dict(Counter(r['source'] for r in rows))}")
    nu = defaultdict(list)
    for r in rows:
        nu[norm_url(r["url"]) + ("#" + urlsplit(r["url"]).fragment if urlsplit(r["url"]).fragment else "")].append(r["url"])
    dup = {k: v for k, v in nu.items() if len(v) > 1}
    R.check("news/khong-trung-url-sau-chuan-hoa", not dup, f"{len(dup)} nhom trung vd={list(dup.values())[:3]}", "medium")
    nt = defaultdict(list)
    for r in rows:
        nt[(re.sub(r"\W+", " ", r["title"].lower()).strip(), r["published_at"].date() if r["published_at"] else None)].append((r["source"], r["url"]))
    dt_ = {k: v for k, v in nt.items() if len(v) > 1}
    # Vong 4: DB giu moi ban (khoa = URL; bao dang lai/ repost la ban ghi rieng hop le) -> chi thong tin;
    # yeu cau that la KHONG HIEN THI trung: kiem qua API /v1/news (gateway bo trung theo tieu de chuan hoa + ngay)
    R.info("news/trung-tieu-de-trong-DB(khac-nguon/repost)", f"{len(dt_)} nhom (title,ngay) vd={[(k[0][:50], v[:2]) for k, v in list(dt_.items())[:3]]}")
    st_api = await c.api("/v1/news", limit=200)
    its = st_api.json().get("items", []) if st_api.status_code == 200 else []
    ka = Counter((re.sub(r"\W+", " ", (it.get("title") or "").lower()).strip(), str(it.get("published_at") or "")[:10]) for it in its)
    dd = [k for k, v in ka.items() if v > 1]
    R.check("news/api-khong-trung-tieu-de-hien-thi", st_api.status_code == 200 and its and not dd, f"{st_api.status_code} n={len(its)} trung={dd[:3]}", "low")
    n = now()
    fut = [(r["source"], r["published_at"], r["url"]) for r in rows if r["published_at"] and r["published_at"] > n + timedelta(hours=1)]
    R.check("news/khong-co-published_at-tuong-lai", not fut, f"{len(fut)} vd={fut[:3]}", "high")
    old = [(r["source"], str(r["published_at"])[:10]) for r in rows if r["published_at"] and r["published_at"] < n - timedelta(days=365)]
    R.check("news/khong-co-published_at-qua-xa(>1 nam)", not old, f"{len(old)} vd={old[:3]}", "medium")
    nul = [r["source"] for r in rows if r["published_at"] is None]
    # Vong 4: da sua parse pubDate M/D/Y (tuoitre/baochinhphu); con lai NULL CO CHU DICH (vd PIIE: ngay > now+1 ngay la ngay su kien) -> cho phep <=0,5%
    R.check("news/published_at-null(<=0.5%)", len(nul) <= 0.005 * max(1, len(rows)), f"{len(nul)}/{len(rows)} {Counter(nul)}", "low")
    bad_url = [r["url"] for r in rows if not re.match(r"^https?://", r["url"])]
    R.check("news/url-http(s)", not bad_url, str(bad_url[:3]), "medium")
    html = [r["url"] for r in rows if r["summary"] and re.search(r"<[a-z/][^>]*>", r["summary"])]
    R.check("news/summary-khong-con-html", not html, f"{len(html)} vd={html[:2]}", "low")
    ent = [r["url"] for r in rows if re.search(r"&(amp|lt|gt|quot|#\d+);", r["title"])]
    R.check("news/title-khong-con-html-entity", not ent, f"{len(ent)}", "low")
    sent = [r["sentiment"] for r in rows if r["sentiment"] is not None and not -1 <= r["sentiment"] <= 1]
    R.check("news/sentiment-trong[-1,1]", not sent, "", "medium")
    nolang = sum(1 for r in rows if not r["lang"])
    nosym = sum(1 for r in rows if not r["symbols"])
    R.info("news/lang-null", f"{nolang}/{len(rows)}; symbols-rong={nosym}/{len(rows)}; ngon-ngu={dict(Counter(r['lang'] for r in rows))}")
    lag = [(r["ingested_at"] - r["published_at"]).total_seconds() / 86400 for r in rows if r["published_at"]]
    R.info("news/tre-ingest", f"median {statistics.median(lag):.1f} ngay, max {max(lag):.1f} ngay")
    # gio phut luon 00:00:00? (nguon chi co ngay)
    mid = Counter(r["source"] for r in rows if r["published_at"] and r["published_at"].time().isoformat()[:8] == "00:00:00")
    R.info("news/published_at-chi-co-ngay(00:00:00Z)", str(dict(mid)))
    # tieu de qua dai/ngan
    bad_t = [r["url"] for r in rows if len(r["title"].strip()) < 5 or len(r["title"]) > 500]
    R.check("news/do-dai-tieu-de-hop-ly", not bad_t, str(bad_t[:3]), "low")


async def calendar_quality(c: Ctx):
    rows = await c.db.fetch("select event_id,source,country,title,impact,ts,forecast,previous,actual,updated_at from calendar_events where source<>'qa'")
    n = now()
    R.info("calendar/tong", f"{len(rows)} su kien; nguon={dict(Counter(r['source'] for r in rows))}; impact={dict(Counter(r['impact'] for r in rows))}; country={dict(Counter(r['country'] for r in rows))}")
    R.info("calendar/khoang-ts", f"{min(r['ts'] for r in rows)} .. {max(r['ts'] for r in rows)}")
    badimp = [r["impact"] for r in rows if r["impact"] not in ("low", "med", "high")]
    R.check("calendar/impact-thuoc-low|med|high", not badimp, f"{Counter(badimp)}", "medium")
    key = defaultdict(list)
    for r in rows:
        key[(r["country"], r["title"].strip().lower(), r["ts"])].append(r["event_id"])
    dup = {k: v for k, v in key.items() if len(v) > 1}
    R.check("calendar/khong-trung-(country,title,ts)", not dup, f"{len(dup)} nhom vd={list(dup.items())[:3]}", "medium")
    far = [(str(r["ts"])[:10], r["title"][:30]) for r in rows if r["ts"] > n + timedelta(days=900) or r["ts"] < n - timedelta(days=800)]  # ECB cong bo lich hop den ~2028
    R.check("calendar/ts-khong-vo-ly(-800d..+900d)", not far, f"{len(far)} vd={far[:3]}", "medium")
    futact = [(str(r["ts"])[:16], r["title"][:30], r["actual"]) for r in rows if r["ts"] > n + timedelta(hours=1) and r["actual"] not in (None, "")]
    R.check("calendar/su-kien-tuong-lai-khong-co-actual", not futact, f"{len(futact)} vd={futact[:3]}", "high")
    # mui gio: gio dia phuong New York cua BLS/FED
    ny = ZoneInfo("America/New_York")
    for src in sorted({r["source"] for r in rows}):
        cnt = Counter(utc(r["ts"]).astimezone(ny).strftime("%H:%M") for r in rows if r["source"] == src)
        R.info(f"calendar/{src}/gio-New-York", str(dict(cnt.most_common(8))))
        utcc = Counter(utc(r["ts"]).strftime("%H:%M") for r in rows if r["source"] == src)
        R.info(f"calendar/{src}/gio-UTC", str(dict(utcc.most_common(8))))
    exp = {"bls": {"08:30", "10:00", "14:00", "09:00", "00:00"}, "fed": {"14:00", "14:30", "08:30", "10:00", "00:00", "09:00", "13:00"}}
    for src, ok_set in exp.items():
        bad = [(str(r["ts"]), r["title"][:30]) for r in rows if r["source"] == src and utc(r["ts"]).astimezone(ny).strftime("%H:%M") not in ok_set]
        if any(r["source"] == src for r in rows):
            R.check(f"calendar/{src}/gio-phat-hanh-hop-ly-theo-NY(DST dung)", len(bad) == 0, f"ngoai-ky-vong={len(bad)} vd={bad[:4]}", "high")
    # bo phat bieu/ngay le/hop (cac su kien nay co the roi T7/CN that: IMF/G20, ngay le Nhat 23h UTC CN) va CN >= 21h UTC (mo cua chau A)
    wk = [(str(r["ts"])[:16], r["title"][:30]) for r in rows if utc(r["ts"]).weekday() >= 5
          and not re.search(r"(?i)speak|speech|holiday|testif|meeting|summit|g20|imf|conference|minutes", r["title"])
          and not (utc(r["ts"]).weekday() == 6 and utc(r["ts"]).hour >= 21)]
    R.check("calendar/khong-roi-cuoi-tuan", not wk, f"{len(wk)} vd={wk[:3]}", "low")
    stale = [r for r in rows if r["ts"] < n - timedelta(days=2) and r["actual"] in (None, "")]
    R.info("calendar/su-kien-qua-han-chua-co-actual", f"{len(stale)}/{len(rows)} (BLS release calendar khong kem so lieu actual?)")
    R.info("calendar/forecast-previous-null", f"forecast null={sum(1 for r in rows if not r['forecast'])}/{len(rows)} previous null={sum(1 for r in rows if not r['previous'])}")
    # su kien sap toi trong 7 ngay (dashboard huu ich?)
    nxt = [r for r in rows if n <= r["ts"] <= n + timedelta(days=7)]
    R.check("calendar/co-su-kien-7-ngay-toi", len(nxt) > 0, f"{len(nxt)} su kien trong 7 ngay toi (chi bls+fed; thieu lich da quoc gia/ECB/BoE... neu 0)", "medium")
    # coverage: country
    R.check("calendar/phu-nhieu-quoc-gia", len({r["country"] for r in rows}) >= 3, f"chi {len({r['country'] for r in rows})} quoc gia: {sorted({r['country'] for r in rows if r['country']})}", "medium")


async def experts_quality(c: Ctx):
    ex = await c.db.fetch("select expert_id, source, display_name, tracked, reputation from experts where source<>'qa'")
    R.info("experts/tong", f"{len(ex)}: {dict(Counter((r['source'], r['tracked']) for r in ex))}")
    pos = await c.db.fetch("select expert_id, source, symbol, as_of, net_volume, avg_price from expert_positions where source<>'qa'")
    R.info("expert_positions", f"{len(pos)} dong; symbols={dict(Counter(r['symbol'] for r in pos))}; as_of={min(r['as_of'] for r in pos) if pos else None}..{max(r['as_of'] for r in pos) if pos else None}")
    sig = await c.db.fetchval("select count(*) from expert_signals where source<>'qa'")
    R.info("expert_signals", f"{sig} dong (EXPERT_COLLECTOR_ENABLED=false -> chi COT/ho so?)")
    fut = [r for r in pos if r["as_of"] > now() + timedelta(days=1)]
    R.check("experts/as_of-khong-tuong-lai", not fut, f"{len(fut)}", "medium")
    # ho so thieu reputation?
    empty = [r["expert_id"] for r in ex if not r["reputation"] or r["reputation"] in ("{}", {})]
    R.info("experts/reputation-rong", f"{len(empty)}/{len(ex)}")


async def mt_pollution(c: Ctx):
    # du lieu mt5 demo 2024 (khong phai qa) nam trong DB that
    r = await c.db.fetch("select source, min(ts_open) lo, max(ts_open) hi, count(*) n from bars where source like 'mt%' and source not like 'mt4:demo-mt4-01' group by 1")
    R.info("mt/nen-tu-mt5-demo-trong-DB", str([(x['source'], str(x['lo'])[:10], str(x['hi'])[:10], x['n']) for x in r]))
    old = [x for x in r if x["hi"] < now() - timedelta(days=365)]
    R.check("mt/khong-co-nen-nam-2024-tu-fake/test-trong-DB-that", not old,
            f"{[(x['source'], str(x['lo'])[:10], str(x['hi'])[:10], x['n']) for x in old]} (nen demo mt5 cu hon 1 nam; nghi du lieu thu nghiem lab) ", "medium")


async def main():
    async with Ctx() as c:
        for fn in (ohlc_scale, vs_ecb, freshness, xau_ref, tf_consistency, gaps_tz, vnstock, news_quality, calendar_quality, experts_quality, mt_pollution):
            try:
                await fn(c)
            except Exception as e:
                import traceback
                traceback.print_exc()
                R.check(f"{fn.__name__}/exception", False, repr(e), "medium")
    return R.finish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
