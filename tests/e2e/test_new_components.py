"""QA vong 2: kiem tra cac thanh phan MOI (crypto 24/7, class/registry symbol, nguon uu tien ETF/US/VN, vn-market,
lich kinh te actual/forecast, paper hash-chain, risk-monitor, journal, reporter, risk-windows, analytics, web-ui).
CHI DOC (GET + doc DB); khong publish len bus, khong gui canh bao.  Ngoai le an toan duy nhat: thu UPDATE/DELETE vao paper_chain
BEN TRONG transaction roi ROLLBACK de chung minh trigger bat bien chan sua."""
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta

from qalib import API_KEY, GATEWAY, Ctx, Results, now

R = Results("new_components")
WEB = os.getenv("QA_WEB", "http://web-ui:8080")
TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
# cua so kiem tra khoang trong (crypto 24/7: khong cuoi tuan, khong nghi trua)
GAP_WINDOW = {"M1": timedelta(hours=36), "M5": timedelta(days=3), "M15": timedelta(days=7),
              "H1": timedelta(days=30), "H4": timedelta(days=60), "D1": timedelta(days=365)}
THIN = {"CRYPTO:TONUSDT"}   # chi co tren san thanh khoan mong (Bitfinex/Kraken) => nen M1..H1 co the vang
MAX_LAG = {"M1": 600, "M5": 1800, "M15": 3600, "H1": 4 * 3600, "H4": 10 * 3600, "D1": 50 * 3600}   # giay (them vao do dai nen)


async def j(c: Ctx, path, **params):
    r = await c.api(path, **params)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


async def registry(c: Ctx):
    st, classes = await j(c, "/v1/symbols/classes")
    R.check("registry/classes-200", st == 200 and isinstance(classes, list) and len(classes) >= 6, f"{st} {len(classes or [])} lop", "high")
    st, syms = await j(c, "/v1/symbols")
    R.check("registry/symbols-200", st == 200 and isinstance(syms, list) and len(syms) > 50, f"{st} {len(syms or [])} symbol", "high")
    if not syms:
        return {}
    cls_names = {x["class"] for x in classes}
    unreg = [s["symbol"] for s in syms if not s.get("registered") and not s["symbol"].startswith("QA")]
    noclass = [s["symbol"] for s in syms if not s.get("class")]
    badcls = [s["symbol"] for s in syms if s.get("class") and s["class"] not in cls_names]
    R.check("registry/moi-symbol-co-class", not noclass and not badcls, f"thieu class={noclass[:10]} class-la={badcls[:10]}", "high")
    R.check("registry/moi-symbol-da-dang-ky", not unreg, f"{len(unreg)} symbol co du lieu nhung KHONG o registry (assets.yaml): {unreg[:15]}", "medium")
    miss = [s["symbol"] for s in syms if s.get("registered") and (s.get("precision") is None or not s.get("session") or not s.get("name"))]
    R.check("registry/precision-session-name", not miss, f"thieu: {miss[:15]}", "medium")
    cnt = {}
    for s in syms:
        cnt[s.get("class")] = cnt.get(s.get("class"), 0) + 1
    off = [(x["class"], x["count"], cnt.get(x["class"], 0)) for x in classes if x["count"] != cnt.get(x["class"], 0)]
    R.check("registry/dem-lop-khop-symbols", not off, f"(lop, classes.count, symbols) lech: {off}", "low")
    bad = [s["symbol"] for s in syms if (s.get("class") == "crypto") != s["symbol"].startswith("CRYPTO:")]
    bad += [s["symbol"] for s in syms if s.get("class") in ("etf", "stock_us") and not s["symbol"].startswith("US:")]
    R.check("registry/quy-uoc-ten-symbol", not bad, f"{bad[:10]}", "medium")
    weird = [(s["symbol"], s.get("last"), s.get("change_pct")) for s in syms
             if s.get("last") is not None and (s["last"] <= 0 or abs(s.get("change_pct") or 0) > 60)]
    R.check("registry/gia-last-hop-ly", not weird, f"{weird[:8]}", "high")
    nosrc = [s["symbol"] for s in syms if s.get("registered") and s.get("last") is None and s.get("tfs")]
    R.check("registry/co-gia-last-khi-co-nen", not nosrc, f"{nosrc[:10]}", "medium")
    return {s["symbol"]: s for s in syms}


async def crypto(c: Ctx, syms: dict):
    cr = sorted(s for s in syms if s.startswith("CRYPTO:"))
    R.check("crypto/so-symbol", len(cr) >= 25, f"{len(cr)} symbol crypto", "medium")
    t = now()
    rows = await c.db.fetch("select symbol, tf, max(ts_open) last, count(*) n from bars where source='crypto_ccxt' group by 1,2")
    last = {(r["symbol"], r["tf"]): r for r in rows}
    stale, miss_tf = [], []
    for s in cr:
        for tf, lim in MAX_LAG.items():
            r = last.get((s, tf))
            if not r:
                miss_tf.append(f"{s}/{tf}")
            elif (t - r["last"]).total_seconds() - TF_SEC[tf] > lim and s not in THIN:
                stale.append(f"{s}/{tf} tre {((t - r['last']).total_seconds() / 3600):.1f}h")
    R.check("crypto/du-6-khung-thoi-gian", not miss_tf, f"thieu {len(miss_tf)}: {miss_tf[:10]}", "high")
    R.check("crypto/do-moi", not stale, f"{len(stale)} chuoi tre: {stale[:10]}", "high")
    for tf, win in GAP_WINDOW.items():
        sql = """with b as (select symbol, ts_open, lag(ts_open) over (partition by symbol order by ts_open) prev
                  from bars where source='crypto_ccxt' and tf=$1 and ts_open >= now() - $2::interval)
                  select symbol, count(*) filter (where ts_open - prev > $3::interval) gaps,
                         coalesce(max(extract(epoch from ts_open - prev)) filter (where ts_open - prev > $3::interval),0) maxgap,
                         count(*) n from b group by 1"""
        rs = await c.db.fetch(sql, tf, win, timedelta(seconds=TF_SEC[tf] * 1.5))
        bad = [(r["symbol"], r["gaps"], round(r["maxgap"] / TF_SEC[tf])) for r in rs if r["gaps"] and r["symbol"] not in THIN]
        thin = [(r["symbol"], r["gaps"], round(r["maxgap"] / TF_SEC[tf])) for r in rs if r["gaps"] and r["symbol"] in THIN]
        if thin:
            R.info(f"crypto/thanh-khoan-mong-co-lo-nen/{tf}", f"{thin} (TON chi co tren Bitfinex/Kraken, cap it giao dich -> san khong tra nen rong; khong phai loi collector)")
        low = [r["symbol"] for r in rs if r["n"] < (win.total_seconds() / TF_SEC[tf]) * 0.8]
        sev = "high" if tf in ("H1", "H4", "D1") else "medium"
        R.check(f"crypto/khong-thieu-nen/{tf}", not bad, f"{len(bad)}/{len(rs)} symbol co khoang trong >1.5 nen trong {win}: (sym,so_lo,maxgap_nen)={bad[:6]}", sev)
        R.check(f"crypto/du-so-nen/{tf}", len(low) <= 1, f"{len(low)} symbol <80% so nen ky vong: {low[:6]}", "low")
    dow = await c.db.fetch("select extract(dow from ts_open)::int d, count(*) n from bars where source='crypto_ccxt' and tf='H1' and symbol='CRYPTO:BTCUSDT' and ts_open>=now()-interval '28 days' group by 1 order by 1")
    byd = {r["d"]: r["n"] for r in dow}
    R.check("crypto/co-nen-thu7-chunhat", byd.get(0, 0) > 0 and byd.get(6, 0) > 0, f"BTC H1 28 ngay theo thu(0=CN): {byd}", "high")
    bad = await c.db.fetchval("select count(*) from bars where source='crypto_ccxt' and (l>least(o,c) or h<greatest(o,c) or l<=0 or v<0 or l>h)")
    R.check("crypto/ohlc-hop-le", bad == 0, f"{bad} nen vi pham", "high")
    rng = {"CRYPTO:BTCUSDT": (10000, 500000), "CRYPTO:ETHUSDT": (300, 30000), "CRYPTO:DOGEUSDT": (0.01, 5), "CRYPTO:SHIBUSDT": (1e-7, 1e-3)}
    for s, (lo, hi) in rng.items():
        r = await c.db.fetchrow("select c from bars where source='crypto_ccxt' and tf='M1' and symbol=$1 order by ts_open desc limit 1", s)
        if r:
            R.check(f"crypto/scale/{s}", lo <= r["c"] <= hi, f"close M1 moi nhat={r['c']} (ky vong {lo}-{hi})", "high")
    fut = await c.db.fetchval("select count(*) from bars where source='crypto_ccxt' and ts_open + (case tf when 'M1' then interval '1 minute' when 'M5' then interval '5 minutes' when 'M15' then interval '15 minutes' when 'H1' then interval '1 hour' when 'H4' then interval '4 hours' else interval '1 day' end) > now() + interval '1 minute'")
    R.check("crypto/chi-nen-da-dong", fut == 0, f"{fut} nen chua dong", "high")
    r = await c.db.fetchval("select count(*) from bars where source='crypto_ccxt' and ((tf='D1' and ts_open <> date_trunc('day', ts_open)) or (tf='H4' and extract(hour from ts_open)::int % 4 <> 0) or (tf='H1' and ts_open <> date_trunc('hour', ts_open)) or (tf='M15' and extract(minute from ts_open)::int % 15 <> 0))")
    R.check("crypto/can-moc-utc", r == 0, f"{r} nen lech moc", "medium")
    rs = await c.db.fetch("""with m as (select symbol, date_trunc('hour', ts_open) h, count(*) n, max(h) hh, min(l) ll, (array_agg(c order by ts_open desc))[1] cc
                             from bars where source='crypto_ccxt' and tf='M1' and symbol in ('CRYPTO:BTCUSDT','CRYPTO:ETHUSDT') and ts_open >= now()-interval '30 hours' and ts_open < date_trunc('hour', now()) group by 1,2 having count(*)=60)
                             select m.symbol, m.h, m.hh, m.ll, m.cc, b.h bh, b.l bl, b.c bc from m join bars b on b.symbol=m.symbol and b.tf='H1' and b.ts_open=m.h and b.source='crypto_ccxt'""")
    badr = [(r["symbol"], r["h"].isoformat()[5:13]) for r in rs if abs(r["bh"] - r["hh"]) / r["hh"] > 0.002 or abs(r["bl"] - r["ll"]) / r["ll"] > 0.002 or abs(r["bc"] - r["cc"]) / r["cc"] > 0.002]
    R.check("crypto/H1-khop-gop-M1(<=0.2%)", bool(rs) and not badr, f"{len(rs)} gio doi chieu, lech: {badr[:5]}", "low")


async def sources(c: Ctx, syms: dict):
    st, ds = await j(c, "/v1/data-sources")
    R.check("nguon/data-sources-200", st == 200 and isinstance(ds, dict), f"{st}", "medium")
    mk = (ds or {}).get("market", []) if ds else []
    # Tu 2026-10-12 gateway an danh ten nguon (HIDE_SOURCES): "Luong gia N" -> chi con state/kind; chap nhan ca hai dang
    provs = {p.get("provider"): p for p in mk}
    anon = all(str(p.get("provider", "")).startswith("Luồng") for p in mk) if mk else False
    if anon:
        act = [p for p in mk if p.get("state") == "active"]
        R.check("nguon/data-sources-an-danh-van-co-trang-thai", len(mk) >= 10 and len(act) >= 5, f"{len(mk)} luong gia, {len(act)} dang chay (ten nguon bi an: HIDE_SOURCES)", "medium")
        leak = [p for p in mk if any(k in json.dumps(p).lower() for k in ("dukascopy", "frankfurter", "yahoo", "oanda", "twelvedata", "ccxt", "alpaca", "tiingo"))]
        R.check("nguon/data-sources-khong-lo-ten-nguon", not leak, f"{len(leak)} muc lo ten", "medium")
    else:
        for need in ("dukascopy", "frankfurter", "yahoo_daily", "crypto_ccxt"):
            R.check(f"nguon/provider-{need}-co-mat", need in provs, f"state={provs.get(need, {}).get('state')}", "medium")
    rows = await c.db.fetch("select source, count(distinct symbol) syms from bars group by 1")
    present = {r["source"] for r in rows}
    ghost = [k for k in ("alpaca", "tiingo", "twelvedata", "oanda", "truefx") if k in present]   # chua co key => khong duoc co du lieu
    R.check("nguon/khong-du-lieu-tu-nguon-chua-co-key", not ghost, f"{ghost}", "medium")
    ov = await c.db.fetch("select symbol, array_agg(distinct source order by source) srcs from bars where tf='D1' group by 1 having count(distinct source)>1")
    bad = []
    for r in ov:
        s, srcs = r["symbol"], r["srcs"]
        if s in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD") and not (srcs[0].startswith("canon:mt5") or srcs[0] == "dukascopy"):   # thiet ke canon: canon:mt5 dung dau (sort theo ten), dukascopy du phong
            bad.append((s, srcs))
        if s.startswith("US:") and srcs[0] not in ("alpaca", "tiingo", "yahoo_daily"):
            bad.append((s, srcs))
    R.check("nguon/uu-tien-theo-ten(source)-dung", not bad, f"{bad[:8]} (da gop nhieu nguon: {[(r['symbol'], r['srcs']) for r in ov][:6]})", "high")
    vn = await c.db.fetch("select distinct source from bars where symbol like 'VN:%' and tf='D1'")
    R.check("nguon/VN:-D1-chi-yahoo_daily", [r["source"] for r in vn] == ["yahoo_daily"], f"{[r['source'] for r in vn]}", "high")
    us = await c.db.fetch("select symbol, max(ts_open) last, count(*) n from bars where symbol like 'US:%' and tf='D1' and source='yahoo_daily' group by 1")
    t = now()
    old = [(r["symbol"], r["last"].date().isoformat()) for r in us if (t - r["last"]).days > 4]
    R.check("nguon/US-D1-moi(<=4 ngay)", not old, f"{len(us)} symbol; cu: {old[:8]}", "high")
    short = [(r["symbol"], r["n"]) for r in us if r["n"] < 500]
    R.check("nguon/US-D1-du-lich-su(>=500)", not short, f"{short[:8]}", "low")
    for s, (lo, hi) in {"US:SPY": (100, 2000), "US:QQQ": (100, 2000), "US:GLD": (50, 1000), "US:AAPL": (20, 1000), "US:TLT": (30, 300)}.items():
        r = await c.db.fetchrow("select c from bars where symbol=$1 and tf='D1' order by ts_open desc limit 1", s)
        if r:
            R.check(f"nguon/scale/{s}", lo <= r["c"] <= hi, f"close={r['c']}", "high")
    jr = await c.db.fetch("""with x as (select symbol, ts_open, c/lag(c) over (partition by symbol order by ts_open)-1 r from bars where symbol like 'US:%' and tf='D1' and source='yahoo_daily' and ts_open>=now()-interval '2 years')
                             select symbol, ts_open::date d, round((r*100)::numeric,1) pct from x where abs(r)>0.4""")
    R.check("nguon/US-khong-nhay-gia-ngay>40%(split-chua-dieu-chinh)", not jr, f"{[(r['symbol'], str(r['d']), float(r['pct'])) for r in jr][:6]}", "medium")
    vj = await c.db.fetch("""with x as (select symbol, ts_open, c/lag(c) over (partition by symbol order by ts_open)-1 r from bars where symbol like 'VN:%' and tf='D1' and ts_open>=now()-interval '2 years')
                             select symbol, ts_open::date d, round((r*100)::numeric,1) pct from x where abs(r)>0.2""")
    R.info("nguon/VN-D1-nhay>20%/ngay(da-biet:thuong/chia-co-phieu-chua-dieu-chinh)", f"{[(r['symbol'], str(r['d']), float(r['pct'])) for r in vj][:6]}")


async def vn(c: Ctx):
    st, s = await j(c, "/v1/vn/status")
    R.check("vn/status-200", st == 200 and isinstance(s, dict), f"{st}", "high")
    if not s:
        return
    R.check("vn/khong-stale", s.get("stale") is False and (s.get("lag_days") or 0) <= 1, f"latest={s.get('latest')} expected={s.get('expected_latest')} lag={s.get('lag_days')}", "high")
    R.check("vn/so-ma>=1500", (s["counts"]["symbols"] or 0) >= 1500, f"{s['counts']['symbols']}", "medium")
    r = await c.db.fetchrow("select close from vn_daily where code='VCB' order by d desc limit 1")
    R.check("vn/don-vi-VND(VCB 20k-200k)", bool(r) and 20000 <= r["close"] <= 200000, f"VCB close={r and r['close']}", "high")
    rs = await c.db.fetch("select code, basic, ceil, flr from vn_daily where d=(select max(d) from vn_daily) and floor='HOSE' and basic>0 and ceil>0 limit 400")
    off = [x["code"] for x in rs if not (0.06 < x["ceil"] / x["basic"] - 1 < 0.075 and 0.06 < 1 - x["flr"] / x["basic"] < 0.075)]
    R.check("vn/tran-san-HOSE-±7%", len(off) <= len(rs) * 0.03, f"{len(off)}/{len(rs)} ma lech: {off[:8]}", "medium")
    bad = await c.db.fetchval("select count(*) from vn_daily where d>=current_date-30 and (close>ceil*1.0001 or close<flr*0.9999) and ceil>0 and flr>0 and close>0")
    R.check("vn/close-trong-tran-san", bad <= 10, f"{bad} dong ngoai [san,tran] trong 30 ngay", "low")
    wk = await c.db.fetchval("select count(distinct d) from vn_daily where extract(dow from d) in (0,6)")
    R.check("vn/khong-phien-cuoi-tuan", wk == 0, f"{wk} ngay", "medium")
    bo = await c.db.fetchval("select count(*) from vn_daily where d>=current_date-90 and close>0 and (low>least(open,close) or high<greatest(open,close) or low>high)")
    R.check("vn/ohlc-hop-le-90-ngay", bo == 0, f"{bo}", "high")
    st, ov = await j(c, "/v1/vn/overview")
    idx = {x["code"]: x for x in (ov or {}).get("indices", [])}
    R.check("vn/chi-so-chinh", all(k in idx for k in ("VNINDEX", "VN30", "HNX")), f"{list(idx)}", "high")
    vi = idx.get("VNINDEX", {}).get("close")
    R.check("vn/VNINDEX-hop-ly(300-5000)", vi is not None and 300 < vi < 5000, f"{vi}", "high")
    for fl, b in (ov or {}).get("breadth", {}).items():
        sm = b["advances"] + b["declines"] + b["unchanged"] + b["no_trade"]
        R.check(f"vn/breadth-{fl}-cong-dung", abs(sm - b["total"]) <= max(3, b["total"] * 0.01), f"tang+giam+dung+khongGD={sm} total={b['total']}", "medium")
    st, se = await j(c, "/v1/vn/session")
    R.check("vn/session-co-lich-phien", st == 200 and bool((se or {}).get("sessions")), f"{st} {list((se or {}).keys())[:6]}", "low")
    st, ru = await j(c, "/v1/vn/rules")
    R.check("vn/rules-200", st == 200, f"{st}", "low")
    for ep in ("heatmap", "movers", "limits", "foreign", "screener", "sectors", "liquidity", "events", "news", "indices", "symbols"):
        st, _ = await j(c, f"/v1/vn/{ep}")
        R.check(f"vn/endpoint/{ep}", st == 200, f"{st}", "medium")
    st, _ = await j(c, "/v1/vn/symbol/VCB")
    R.check("vn/symbol-VCB", st == 200, f"{st}", "medium")
    st, _ = await j(c, "/v1/vn/symbol/KHONGCO123")
    R.check("vn/symbol-la->404", st in (404, 422), f"{st}", "low")
    st, _ = await j(c, "/v1/vn/symbol/%27%3BDROP%20TABLE")
    R.check("vn/sql-injection-bi-chan", st in (400, 404, 422), f"{st}", "high")
    st, acc = await j(c, "/v1/paper/accounts")
    vnacc = [a for a in (acc or {}).get("items", []) if a.get("base_ccy") == "VND"]
    R.check("vn/paper-tai-khoan-VND", len(vnacc) >= 1, f"{[a['account_id'] for a in vnacc]}", "low")


async def calendar(c: Ctx):
    qa_rows = await c.db.fetchval("select count(*) from calendar_events where source='qa'")
    if qa_rows:
        R.info("calendar/bo-qua-dong-qa", f"{qa_rows} dong source=qa (test khac dang chay song song) - bo khoi kiem tra tuong lai")
    st, d = await j(c, "/v1/calendar", limit=500)
    items = (d or {}).get("items", [])
    R.check("calendar/api-200", st == 200 and bool(items), f"{st} {len(items)}", "high")
    t = now()
    fut_act = await c.db.fetchval("select count(*) from calendar_events where source<>'qa' and ts>now()+interval '5 minutes' and actual is not null")
    R.check("calendar/tuong-lai-khong-co-actual", fut_act == 0, f"{fut_act}", "high")
    rows = await c.db.fetch("""select source, count(*) n, count(*) filter (where forecast is not null) fc,
        count(*) filter (where ts<now()-interval '3 hours') past3, count(*) filter (where ts<now()-interval '3 hours' and actual is not null) pact
        from calendar_events group by 1""")
    info = {r["source"]: (r["n"], r["fc"], r["past3"], r["pact"]) for r in rows}
    R.info("calendar/nguon(n,forecast,qua-khu>3h,actual)", json.dumps(info))
    ff = info.get("faireconomy", (0, 0, 0, 0))
    R.check("calendar/faireconomy-co-forecast", ff[0] > 0 and ff[1] / ff[0] >= 0.3, f"{ff[1]}/{ff[0]} su kien co forecast", "medium")
    # Vong 4: mau so cu (moi su kien da qua >3h) sai gia dinh - phan lon la phat bieu/ dau gia/ ngay le/ chi so
    # khong co nguon actual mien phi (vd CN, NFIB). Kiem tren su kien high/med CO forecast (co so lieu) trong 14 ngay.
    am = await c.db.fetchrow("""select count(*) n, count(*) filter (where actual is not null) a from calendar_events
        where source='faireconomy' and impact in ('high','med') and forecast is not null
        and ts < now()-interval '3 hours' and ts > now()-interval '14 days'""")
    R.info("calendar/actual-moi-su-kien-da-qua>3h", f"{ff[3]}/{ff[2]} (gom ca su kien khong co so lieu)")
    if am["n"] >= 3:
        R.check("calendar/actual-duoc-dien-sau-phat-hanh(high/med co forecast)", am["a"] / am["n"] >= 0.5, f"{am['a']}/{am['n']} su kien high/med da qua >3h co actual", "high")
    else:
        R.info("calendar/actual-sau-phat-hanh", f"CHUA KIEM CHUNG: chi {am['n']} su kien high/med co forecast da qua >3h trong 14 ngay")
    dup = await c.db.fetchval("select count(*) from (select 1 from calendar_events group by country, title, ts, source having count(*)>1) x")
    R.check("calendar/khong-trung", dup == 0, f"{dup}", "medium")
    bi = await c.db.fetchval("select count(*) from calendar_events where impact not in ('high','med','low')")
    R.check("calendar/impact-hop-le", bi == 0, f"{bi}", "medium")
    far = await c.db.fetch("select source, title, ts from calendar_events where ts>now()+interval '800 days' limit 5")
    R.check("calendar/khong-co-su-kien->800-ngay", not far, f"{[(r['source'], r['ts'].date().isoformat()) for r in far]}", "low")
    far2 = await c.db.fetchval("select count(*) from calendar_events where ts>now()+interval '400 days'")
    R.info("calendar/su-kien->400-ngay(ECB cong bo lich truoc)", f"{far2}")
    wk = await c.db.fetch("""select source, title, ts from calendar_events where extract(dow from ts) in (0,6)
        and not (title ~* 'speak|speech|holiday|testif|meeting|summit|g20|imf|conference|minutes') and ts>now()-interval '60 days'
        and not (extract(dow from ts)=0 and extract(hour from ts)>=21)""")
    R.check("calendar/khong-roi-cuoi-tuan(tru-phat-bieu/ngay-le)", not wk, f"{[(r['source'], r['title'][:30], r['ts'].isoformat()[5:16]) for r in wk][:6]}", "low")
    st, d2 = await j(c, "/v1/calendar", limit=500, **{"from": (t - timedelta(days=2)).isoformat(), "to": (t + timedelta(days=14)).isoformat()})
    its = (d2 or {}).get("items", [])
    key = {}
    for it in its:
        k = (it.get("country"), it["ts"][:13], re.sub(r"\W+", "", it["title"].lower())[:25])
        key[k] = key.get(k, 0) + 1
    dd = [k for k, v in key.items() if v > 1]
    R.check("calendar/api-khong-trung-hien-thi", not dd, f"{dd[:5]}", "low")
    bl = await c.db.fetch("select distinct to_char(ts at time zone 'America/New_York','HH24:MI') h from calendar_events where source='bls'")
    R.check("calendar/BLS-gio-NY-8:30/10:00", {r["h"] for r in bl} <= {"08:30", "10:00"}, f"{[r['h'] for r in bl]}", "medium")


async def paper(c: Ctx):
    st, v = await j(c, "/v1/paper/verify")
    R.check("paper/verify-200", st == 200 and isinstance(v, dict), f"{st}", "critical")
    if not v:
        return
    R.check("paper/hash-chain-toan-bo-ok", v.get("ok") is True, f"ok={v.get('ok')} items={len(v.get('items', []))}", "critical")
    bad = [i["account_id"] for i in v.get("items", []) if not i.get("ok") or i.get("anchor_ok") is False or i.get("problems")]
    R.check("paper/moi-tai-khoan-chain-ok+anchor", not bad, f"{bad}", "critical")
    R.check("paper/co-nhan-MO-PHONG", v.get("simulation") is True and "MÔ PHỎNG" in (v.get("label") or ""), f"{v.get('label')}", "high")
    items = {i["account_id"]: i for i in v["items"]}
    rows = await c.db.fetch("select account_id, seq, prev_hash, row_hash from paper_chain order by account_id, seq")
    by = {}
    for r in rows:
        by.setdefault(r["account_id"], []).append(r)
    probs = []
    for a, lst in by.items():
        for i, r in enumerate(lst):
            if r["seq"] != i + 1:
                probs.append(f"{a}: seq {r['seq']} khong lien tuc")
                break
            if i > 0 and r["prev_hash"] != lst[i - 1]["row_hash"]:
                probs.append(f"{a}: prev_hash lech tai seq {r['seq']}")
                break
            if i == 0 and r["prev_hash"] != hashlib.sha256(f"genesis:{a}".encode()).hexdigest():
                probs.append(f"{a}: prev_hash cua seq=1 khac sha256('genesis:<tai khoan>')")
            if i == 0 and a in items and items[a].get("genesis") != r["row_hash"]:
                probs.append(f"{a}: verify.genesis khac row_hash seq=1")
        if a in items and items[a]["entries"] != len(lst):
            probs.append(f"{a}: verify.entries={items[a]['entries']} DB={len(lst)}")
    R.check("paper/chain-DB-doc-lap(seq,prev_hash,genesis,so-dong)", not probs, f"{len(by)} tai khoan; {probs[:5]}", "critical")
    miss = [a for a in by if a not in items]
    R.check("paper/verify-phu-moi-tai-khoan-trong-DB", not miss, f"{miss}", "high")
    res = {}
    for name, sql in (("UPDATE", "update paper_chain set row_hash=row_hash where seq=1"), ("DELETE", "delete from paper_chain where seq=1")):
        tx = c.db.transaction()
        await tx.start()
        blocked = False
        try:
            try:
                await c.db.execute(sql)
            except Exception:
                blocked = True
        finally:
            await tx.rollback()
        res[name] = blocked
    for name, blocked in res.items():
        R.check(f"paper/chain-bat-bien({name}-bi-trigger-chan)", blocked, "", "critical")
    n_after = await c.db.fetchval("select count(*) from paper_chain")
    R.check("paper/chain-nguyen-ven-sau-thu", n_after == len(rows), f"{n_after} vs {len(rows)}", "critical")
    st, acc = await j(c, "/v1/paper/accounts")
    its = (acc or {}).get("items", [])
    R.check("paper/accounts>=8", st == 200 and len(its) >= 8, f"{len(its)}", "medium")
    badacc = [a["account_id"] for a in its if a.get("equity") is None or a["equity"] <= 0 or abs(a.get("drawdown") or 0) > 1]
    R.check("paper/tai-khoan-equity-hop-ly", not badacc, f"{badacc}", "high")
    for a in its[:20]:
        aid = a["account_id"]
        st, s = await j(c, f"/v1/paper/accounts/{aid}/stats")
        if st != 200:
            R.check(f"paper/stats/{aid}", False, f"{st}", "medium")
            continue
        if s.get("days", 0) < 84:
            R.check(f"paper/mau-ngan-khong-tuyen-bo-Sharpe/{aid}", s.get("reliable") is False or s.get("sharpe") in (None, 0), f"days={s.get('days')} reliable={s.get('reliable')} sharpe={s.get('sharpe')}", "medium")
    st, g = await j(c, "/v1/paper/governance")
    R.check("paper/governance-200", st == 200 and bool((g or {}).get("items")), f"{st}", "medium")
    st, k = await j(c, "/v1/paper/accounts/bh_fx/kill-switch")
    R.check("paper/kill-switch-doc-duoc", st == 200, f"{st}", "medium")
    for m in ("POST", "PUT", "DELETE"):
        r = await c.http.request(m, GATEWAY + "/v1/paper/accounts/bh_fx/kill-switch/reset", headers={"X-API-Key": API_KEY})
        R.check(f"paper/readonly/{m}-kill-switch-reset-khong-qua-gateway", r.status_code in (404, 405), f"{r.status_code}", "critical")
    fut = [a["account_id"] for a in its if a.get("as_of") and datetime.fromisoformat(a["as_of"]) > now() + timedelta(days=1)]
    R.check("paper/as_of-khong-tuong-lai", not fut, f"{fut}", "medium")


async def risk(c: Ctx):
    st, r = await j(c, "/v1/risk/accounts")
    R.check("risk/accounts-200", st == 200 and bool(r) and r.get("read_only") is True, f"{st} read_only={r and r.get('read_only')}", "high")
    if not r:
        return
    accs = r["accounts"]
    R.check("risk/co-ca-MT-va-paper", {a["kind"] for a in accs} >= {"mt", "paper"}, f"{[(a['account_id'], a['kind']) for a in accs][:6]}", "medium")
    vals = sorted({str(a.get("budget_status")) for a in accs})
    R.check("risk/budget_status-hop-le", set(vals) <= {"ok", "warn", "crit", "breach", "no_data", "unknown", "None"}, f"{vals}", "medium")
    ranges = [a["account_id"] for a in accs if a.get("var95_1d_pct") is not None and not (0 <= a["var95_1d_pct"] <= 50)]
    R.check("risk/VaR-trong-khoang(0-50%)", not ranges, f"{ranges}", "high")
    es = [a["account_id"] for a in accs if a.get("var95_1d_pct") and a.get("es975_1d_pct") is not None and a["es975_1d_pct"] + 1e-9 < a["var95_1d_pct"]]
    R.check("risk/ES>=VaR", not es, f"{es}", "medium")
    for a in accs:
        if a["kind"] == "paper" and a.get("positions", 0) > 0:
            R.check(f"risk/VaR-co-so-khi-co-vi-the/{a['account_id']}", a.get("var95_1d_pct") is not None, f"pos={a['positions']} var={a.get('var95_1d_pct')}", "medium")
    st, cf = await j(c, "/v1/risk/config")
    R.check("risk/config-kich-ban>=10", st == 200 and len((cf or {}).get("scenarios", [])) >= 10, f"{len((cf or {}).get('scenarios', []))}", "low")
    st, _ = await j(c, f"/v1/risk/accounts/{accs[0]['account_id']}")
    R.check("risk/chi-tiet-1-tai-khoan", st == 200, f"{st}", "medium")
    st, _ = await j(c, "/v1/risk/accounts/khong..co")
    R.check("risk/tai-khoan-la->4xx", 400 <= st < 500, f"{st}", "low")
    # tai khoan MT mat ket noi cu: co co stale
    stale = [(a["account_id"], a.get("stale")) for a in accs if a["kind"] == "mt"]
    R.info("risk/mt-stale-flag", f"{stale}")


async def journal(c: Ctx):
    st, a = await j(c, "/v1/journal/accounts")
    items = (a or {}).get("items", [])
    R.check("journal/accounts-200", st == 200 and bool(items), f"{st} {len(items)}", "high")
    if not items:
        return
    acc = ([x for x in items if x["kind"] == "mt"] or items)[0]["account_id"]
    for ep in ("summary", "deals", "discipline", "excursions", "review", "notes"):
        st, _ = await j(c, f"/v1/journal/{acc}/{ep}")
        R.check(f"journal/{ep}", st == 200, f"{acc} {st}", "medium")
    st, s = await j(c, f"/v1/journal/{items[0]['account_id']}/summary")
    sm = (s or {}).get("summary", {})
    R.check("journal/summary-nhat-quan(win+loss+be=n)", sm.get("wins", 0) + sm.get("losses", 0) + sm.get("breakeven", 0) == sm.get("n", 0), f"{sm.get('n')}", "high")
    st, _ = await j(c, "/v1/journal/khong-co-tk/summary")
    R.check("journal/tai-khoan-la->4xx", 400 <= st < 500, f"{st}", "low")
    for p in ("order", "trade", "close", "deals/1/close"):
        st, _ = await j(c, f"/v1/journal/{acc}/{p}")
        R.check(f"journal/khong-duong-{p}", st in (404, 405), f"{st}", "critical")


async def reporter(c: Ctx):
    st, r = await j(c, "/v1/reports")
    R.check("reporter/list-200", st == 200 and bool(r) and r.get("read_only") is True, f"{st}", "high")
    if not r:
        return
    its = r["items"]
    kinds = {i["kind"] for i in its}
    R.check("reporter/co-daily+weekly", {"daily", "weekly"} <= kinds, f"{kinds}", "medium")
    R.check("reporter/lich-tiep-theo", bool(r.get("next_runs", {}).get("daily")) and bool(r.get("next_runs", {}).get("weekly")), f"{r.get('next_runs')}", "medium")
    bad = [(i["kind"], i["period"], i["sections_fail"]) for i in its if i.get("sections_fail") or i.get("status") != "ok"]
    R.check("reporter/khong-muc-loi", not bad, f"{bad}", "high")
    t = now()
    for kind in ("daily", "weekly"):
        last = [i for i in its if i["kind"] == kind]
        if last:
            g = datetime.fromisoformat(last[0]["generated_at"].replace("Z", "+00:00"))
            R.check(f"reporter/{kind}-khong-qua-cu", (t - g) < timedelta(days=2 if kind == "daily" else 9), f"tao {g.isoformat()[:16]}", "medium")
    for i in its[:2]:
        for ext, sha, nb in (("html", "sha256", "bytes"), ("pdf", "pdf_sha256", "pdf_bytes")):
            resp = await c.http.get(GATEWAY + f"/v1/reports/{i['kind']}/{i['period']}.{ext}", headers={"X-API-Key": API_KEY})
            same = hashlib.sha256(resp.content).hexdigest() == i[sha]
            # HTML co the bi gateway an danh ten nguon khi phuc vu (HIDE_SOURCES) nen byte khac file goc; PDF (nhi phan) phai khop tuyet doi
            ok = resp.status_code == 200 and (same or (ext == "html" and abs(len(resp.content) - i[nb]) <= max(200, i[nb] * 0.02)))
            R.check(f"reporter/{i['kind']}-{i['period']}.{ext}-sha256-khop", ok, f"{resp.status_code} {len(resp.content)}B (list: {i[nb]}B) sha_trung={same}", "high")
            if ext == "pdf":
                R.check("reporter/pdf-dung-dinh-dang", resp.content[:5] == b"%PDF-", f"{resp.content[:8]!r}", "medium")
            else:
                txt = resp.text.lower()
                R.check("reporter/html-co-disclaimer", "khuyến nghị" in txt or "mô phỏng" in txt, "", "medium")
                R.check("reporter/html-khong-lo-secret", not re.search(r"(password|api[_-]?key|token)\s*[=:]\s*['\"]?[a-z0-9]{16,}", txt), "", "critical")
                R.check("reporter/html-khong-script-ngoai", not re.search(r"<script[^>]+src=[\"']https?://", txt), "", "high")
    for p in ("daily/../../etc/passwd", "daily/x.html", "evil/2026-10-11.html", "daily/2026-10-11.exe"):
        resp = await c.http.get(GATEWAY + "/v1/reports/" + p, headers={"X-API-Key": API_KEY})
        R.check(f"reporter/duong-dan-xau/{p}", resp.status_code in (400, 404, 422), f"{resp.status_code}", "high")
    resp = await c.http.post(GATEWAY + "/v1/reports/generate", headers={"X-API-Key": API_KEY})
    R.check("reporter/generate-khong-expose-qua-gateway", resp.status_code in (404, 405), f"{resp.status_code}", "high")


async def windows_analytics_web(c: Ctx, syms: dict):
    st, w = await j(c, "/v1/risk-windows/status")
    R.check("risk-windows/status-200", st == 200 and isinstance(w, dict), f"{st}", "high")
    if w:
        cfg = w.get("config", {})
        R.check("risk-windows/cau-hinh-before15-after30", cfg.get("default", {}).get("before_min") == 15 and cfg.get("default", {}).get("after_min") == 30, f"{cfg.get('default')}", "low")
        R.check("risk-windows/bo-qua-Holiday", any("Holiday" in x for x in cfg.get("ignore_title_any", [])), "", "low")
        R.check("risk-windows/universe-co-VN-va-FX", {"EURUSD", "XAUUSD", "VN:VNM"} <= set(cfg.get("universe", [])), f"{len(cfg.get('universe', []))}", "medium")
        R.info("risk-windows/universe-vs-registry", f"universe {len(cfg.get('universe', []))} ma; clear_symbols={w.get('clear_symbols')} (crypto khong nam trong cua so tin = dung thiet ke)")
    st, _ = await j(c, "/v1/risk-windows")
    R.check("risk-windows/list-200", st == 200, f"{st}", "medium")
    st, a = await j(c, "/v1/analytics/overview")
    R.check("analytics/overview-200", st == 200 and bool(a), f"{st}", "high")
    if a:
        R.check("analytics/du-lieu-moi(<30 phut)", a.get("age_seconds", 1e9) < 1800, f"{a.get('age_seconds'):.0f}s", "high")
        R.check("analytics/co-disclaimer", "khuyến nghị" in a.get("disclaimer", ""), "", "medium")
        miss = sorted(x for x in set(syms) - set(a["symbols"]) if not x.startswith(("FRED:", "QA")) and x not in ("DFF", "DGS10", "DGS2", "DTWEXBGS", "T10YIE"))
        miss_d1 = [m for m in miss if "D1" in (syms.get(m, {}).get("tfs") or [])]
        R.check("analytics/phu-moi-symbol-co-nen-D1", not miss_d1, f"thieu: {miss_d1[:12]} (khong co D1/chua du nen: {len(miss) - len(miss_d1)})", "medium")
        badv = []
        for it in a["items"]:
            for k, lo, hi in (("rsi", 0, 100), ("adx", 0, 100), ("stoch_k", -0.01, 100.01)):
                v = it.get(k)
                if v is not None and not (lo <= v <= hi):
                    badv.append((it["symbol"], it["tf"], k, v))
            if it.get("close") is not None and it["close"] <= 0:
                badv.append((it["symbol"], it["tf"], "close", it["close"]))
        R.check("analytics/chi-bao-trong-khoang(RSI/ADX/Stoch 0-100)", not badv, f"{badv[:6]}", "high")
        for sname in ("EURUSD", "CRYPTO:BTCUSDT", "US:SPY", "VN:VCB"):
            it = next((x for x in a["items"] if x["symbol"] == sname and x["tf"] == "D1"), None)
            if not it:
                continue
            r = await c.db.fetchrow("select c from bars where symbol=$1 and tf='D1' order by ts_open desc, source limit 1", sname)
            if r:
                R.check(f"analytics/close-khop-bars/{sname}", abs(it["close"] - r["c"]) / r["c"] < 0.01, f"analytics={it['close']} bars={r['c']}", "medium")
        bb = [(x["symbol"], x["tf"], x.get("bias")) for x in a["items"] if x.get("bias") is not None and not (-100 <= x["bias"] <= 100)]
        R.check("analytics/bias-trong-[-100,100]", not bb, f"{bb[:5]}", "medium")
    st, e = await j(c, "/v1/analytics/symbol/EURUSD")
    R.check("analytics/symbol-EURUSD", st == 200 and bool(e) and {"H1", "H4", "D1"} <= set(e.get("tfs", {})), f"{st}", "medium")
    st, _ = await j(c, "/v1/analytics/symbol/%27%3BDROP")
    R.check("analytics/symbol-injection-chan", st in (400, 404, 422), f"{st}", "high")
    for ep in ("correlation", "sessions", "screener"):
        st, _ = await j(c, f"/v1/analytics/{ep}")
        R.check(f"analytics/{ep}-200", st == 200, f"{st}", "low")
    st, sy = await j(c, "/v1/system")
    if sy:
        down = [s["name"] for s in sy["services"] if not s.get("up")]
        R.check("he-thong/moi-service-up", not down, f"{len(sy['services'])} service; down={down}", "high")
        dl = [x for x in sy["streams"] if x["stream"] == "dlq"]
        R.check("he-thong/dlq-nho(<=5)", not dl or dl[0]["length"] <= 5, f"{dl[0]['length'] if dl else 0}", "high")
    try:
        r = await c.http.get(WEB + "/", timeout=10, follow_redirects=False)   # đăng nhập phiên: chưa đăng nhập -> 302 tới trang đăng nhập (hoặc 401 nếu dự phòng basic)
        R.check("web-ui/khong-dang-nhap->chuyen-dang-nhap", r.status_code == 401 or (r.status_code == 302 and "/auth/login" in r.headers.get("location", "")), f"{r.status_code}", "critical")
        r = await c.http.get(WEB + "/api/v1/symbols", timeout=10)
        R.check("web-ui/api-khong-dang-nhap->401", r.status_code == 401, f"{r.status_code}", "critical")
        r = await c.http.post(WEB + "/api/v1/paper/accounts/bh_fx/kill-switch/reset", timeout=10)
        R.check("web-ui/khong-route-kill-switch-POST", r.status_code in (401, 403, 404, 405), f"{r.status_code}", "critical")
    except Exception as e:
        R.info("web-ui/khong-toi-duoc-tu-container-test", repr(e)[:120])


async def main():
    async with Ctx() as c:
        syms = await registry(c)
        for fn, args in ((crypto, (syms,)), (sources, (syms,)), (vn, ()), (calendar, ()), (paper, ()), (risk, ()), (journal, ()), (reporter, ()), (windows_analytics_web, (syms,))):
            try:
                await fn(c, *args)
            except Exception as e:
                R.check(f"{fn.__name__}/ngoai-le", False, repr(e)[:300], "high")
    return R.finish()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
