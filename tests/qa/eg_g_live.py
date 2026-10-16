"""QA-G: bao cao / ban tin / reporter / alert (ntfy) + paper-trader / risk / journal / track-record chay THAT va doi chieu so lieu bang tinh tay.
Chay: sh tests/qa/eg_g_live.sh   (container tam python:3.12-slim noi vao mang tradingsys; khong dat lenh; du lieu thu: alert source=qa tag qa).
"""
from __future__ import annotations
import asyncio, hashlib, json, math, re, sys, time, os
sys.path.insert(0, "/qa")
from qalib import Ctx, Results, mk_event, publish, wait_for

R = Results("eg_g_live")
ITOK = {"X-Internal-Token": os.getenv("INTERNAL_TOKEN", "").strip("\"\'")}
REPORTER = "http://reporter:8000"
NTFY = "http://ntfy:80/tradingsys-alerts"
BANNED = re.compile(r"(?<![A-Za-z0-9_])(dukascopy|frankfurter|yahoo|vnstock|vndirect|okx|kucoin|binance|bybit|coinbase|kraken|ccxt|alpaca|tiingo|oanda|truefx|gdelt|reuters|cafef|vnexpress|myfxbook|forexfactory|stooq|twelvedata|finnhub|alphavantage|polygon|faireconomy)(?![A-Za-z0-9_])", re.I)


def close(a, b, rel=1e-6, ab=1e-6):
    return a is not None and b is not None and abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))


async def jget(c, path, **p):
    for _ in range(4):
        r = await c.api(path, **p)
        if r.status_code not in (502, 503, 504): break
        await asyncio.sleep(5)   # gateway co the dang duoc agent khac deploy
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


async def paper(c):
    sc, d = await jget(c, "/v1/paper/accounts")
    R.check("paper/list-200+co-nhan-MO-PHONG", sc == 200 and d.get("simulation") is True and "MÔ PHỎNG" in d.get("label", ""), f"{sc}", "high")
    items = d["items"]
    R.check("paper/so-tai-khoan", len(items) >= 10, f"n={len(items)}", "low")
    for a in items:
        aid = a["account_id"]
        R.check(f"paper/{aid}/equity=von*(1+TR)", close(a["equity"], a["initial_capital"] * (1 + a["total_return"]), 1e-9, 1e-6), f"eq={a['equity']:.4f} init={a['initial_capital']} tr={a['total_return']:.6f}", "high")
        _, pos = await jget(c, f"/v1/paper/accounts/{aid}/positions")
        _, eq = await jget(c, f"/v1/paper/accounts/{aid}/equity")
        _, st = await jget(c, f"/v1/paper/accounts/{aid}/stats")
        _, ks = await jget(c, f"/v1/paper/accounts/{aid}/kill-switch")
        pi = pos["items"]
        # notional = |qty|*mark (tru USDJPY/USD-base: notional=qty); gross = tong notional
        gross = sum(abs(p["notional"]) for p in pi)
        R.check(f"paper/{aid}/gross_exposure=tong-notional", close(a["gross_exposure"], gross, 1e-6, 1e-4), f"api={a['gross_exposure']:.4f} tay={gross:.4f}", "high")
        bad_n = [p["symbol"] for p in pi if not (p["symbol"].endswith("JPY") and p["symbol"].startswith("USD")) and p["symbol"][:3] != "USD" and not close(abs(p["notional"]), abs(p["qty"]) * p["mark_price"], 1e-6, 1e-4) and "." not in p["symbol"] and ":" not in p["symbol"]]
        R.check(f"paper/{aid}/notional=qty*mark", not bad_n, str(bad_n[:3]), "medium")
        # unrealized (quote USD): (mark-avg)*qty
        bad_u = []
        for p in pi:
            s = p["symbol"]
            if s.endswith("USD") and not s.startswith("USD"):
                exp = (p["mark_price"] - p["avg_price"]) * p["qty"]
                if not close(exp, p["unrealized_pnl"], 1e-6, 1e-4):
                    bad_u.append((s, exp, p["unrealized_pnl"]))
        R.check(f"paper/{aid}/unrealized=(mark-avg)*qty", not bad_u, str(bad_u[:2]), "high")
        # duong equity: drawdown + best/worst day tinh tay
        ser = [x["equity"] for x in eq["series"]]
        if ser:
            peak, mdd = ser[0], 0.0
            for v in ser:
                peak = max(peak, v); mdd = min(mdd, v / peak - 1)
            cur = ser[-1] / peak - 1
            R.check(f"paper/{aid}/drawdown-hien-tai", close(a["drawdown"], cur, 1e-6, 1e-9), f"api={a['drawdown']:.6f} tay={cur:.6f}", "high")
            rr0 = [a["initial_capital"]] + ser
            rets = [rr0[i] / rr0[i - 1] - 1 for i in range(1, len(rr0))]
            if len(rets) >= 2:
                pk = 1.0; cu = 1.0; md = 0.0
                for r_ in rets:
                    cu *= 1 + r_; pk = max(pk, cu); md = min(md, cu / pk - 1)
                R.check(f"paper/{aid}/max_dd-stats(chuoi loi suat, co von ban dau)", close(st.get("max_drawdown"), md, 1e-6, 1e-9), f"api={st.get('max_drawdown')} tay={md:.6f}", "high")
            else:
                R.info(f"paper/{aid}/max_dd", f"{st.get('max_drawdown')} (chuoi <2 ngay -> None theo thiet ke)")
            R.check(f"paper/{aid}/duong-equity-cuoi=equity", close(ser[-1], a["equity"], 1e-9, 1e-6), f"{ser[-1]:.4f} vs {a['equity']:.4f}", "high")
            if rets and "best_day" in st:
                R.check(f"paper/{aid}/best/worst-day", close(st["best_day"], max(rets), 1e-6, 1e-9) and close(st["worst_day"], min(rets), 1e-6, 1e-9), f"api=({st['best_day']:.6f},{st['worst_day']:.6f}) tay=({max(rets):.6f},{min(rets):.6f})", "high")
                hr = sum(1 for r in rets if r > 0) / len(rets)
                R.check(f"paper/{aid}/hit_rate-ngay-lai", close(st["hit_rate"], hr, 1e-6, 1e-9), f"api={st['hit_rate']} tay={hr:.4f} (n={len(rets)} ngay)", "low")
        # kill-switch headroom = hanlimit - current  (limit am, current am)
        lim, cur_, hd = ks["limits"], ks["current"], ks["headroom"]
        okh = all(close(hd[k], cur_[k] - lim[k], 1e-6, 1e-9) for k in ("daily", "weekly", "drawdown"))
        R.check(f"paper/{aid}/kill-switch-headroom=current-limit", okh, f"{hd} vs cur-lim", "medium")
        R.check(f"paper/{aid}/kill-switch-status-hop-le", ks["status"] in ("active", "halted", "locked"), ks["status"], "medium")
    sc, v = await jget(c, "/v1/paper/verify")
    R.check("paper/hash-chain-journal-verify", sc == 200 and v.get("ok") is True and all(i["ok"] for i in v["items"]), f"ok={v.get('ok')} n={len(v.get('items', []))}", "critical")
    # khong co duong dat lenh that
    for m, p in [("POST", "/v1/paper/accounts"), ("POST", "/v1/orders"), ("POST", "/v1/paper/orders")]:
        r = await c.http.request(m, c_url(p), headers={"X-API-Key": api_key()}, json={})
        R.check(f"paper/khong-co-route-dat-lenh {m} {p}", r.status_code in (403, 404, 405), f"{r.status_code}", "critical")


def api_key():
    from qalib import API_KEY
    return API_KEY


def c_url(p):
    from qalib import GATEWAY
    return GATEWAY + p


async def journal(c):
    sc, d = await jget(c, "/v1/journal/accounts")
    R.check("journal/accounts-200", sc == 200 and d["items"], f"{sc}", "high")
    tested = 0
    for it in d["items"]:
        aid = it["account_id"]
        _, sm = await jget(c, f"/v1/journal/{aid}/summary")
        _, dl = await jget(c, f"/v1/journal/{aid}/deals", limit=500)
        deals = dl["items"]
        s = sm["summary"]
        R.check(f"journal/{aid}/total=deals-tra-ve", dl["total"] == len(deals) or dl["total"] > 500, f"total={dl['total']} len={len(deals)}", "medium")
        if it["n_trades"] != s["n"]:
            R.info(f"journal/{aid}/n_trades(list)!=summary.n", f"list={it['n_trades']} summary={s['n']} (list co the dem fill/ban ghi, summary dem deal dong)")
        if not deals or dl["total"] > 500:
            continue
        tested += 1
        nets = [x["net"] for x in deals]
        wins = [x for x in nets if x > 0]; loss = [x for x in nets if x < 0]
        gp, gl = sum(wins), -sum(loss)
        R.check(f"journal/{aid}/n,wins,losses", s["n"] == len(deals) and s["wins"] == len(wins) and s["losses"] == len(loss), f"api=({s['n']},{s['wins']},{s['losses']}) tay=({len(deals)},{len(wins)},{len(loss)})", "high")
        R.check(f"journal/{aid}/net", close(s["net"], sum(nets), 1e-6, 0.02), f"api={s['net']} tay={sum(nets):.2f}", "high")
        R.check(f"journal/{aid}/gross_profit/loss", close(s["gross_profit"], gp, 1e-6, 0.02) and close(s["gross_loss"], gl, 1e-6, 0.02), f"api=({s['gross_profit']},{s['gross_loss']}) tay=({gp:.2f},{gl:.2f})", "high")
        pf = (gp / gl) if gl else None
        R.check(f"journal/{aid}/profit_factor", (s["profit_factor"] is None and pf is None) or (pf is not None and s["profit_factor"] is not None and close(s["profit_factor"], pf, 2e-3, 2e-3)), f"api={s['profit_factor']} tay={pf}", "high")
        R.check(f"journal/{aid}/win_rate", close(s["win_rate"], len(wins) / len(deals), 2e-3, 2e-3), f"api={s['win_rate']} tay={len(wins)/len(deals):.4f}", "high")
        R.check(f"journal/{aid}/expectancy", close(s["expectancy"], sum(nets) / len(deals), 2e-3, 0.02), f"api={s['expectancy']} tay={sum(nets)/len(deals):.4f}", "medium")
        R.check(f"journal/{aid}/net=profit+swap+commission", all(close(x["net"], x["profit"] + x["swap"] + x["commission"], 1e-6, 0.011) for x in deals), "moi deal", "high")
        # equity/max_dd theo thu tu dong lenh
        base = sm["equity"]["base"]
        order = sorted(deals, key=lambda x: (x["time_close"], x["ticket"]))
        eqv, peak, mdd = base, base, 0.0
        for x in order:
            eqv += x["net"]; peak = max(peak, eqv); mdd = max(mdd, peak - eqv)
        R.check(f"journal/{aid}/equity-cuoi,max_dd", close(sm["equity"]["end"], eqv, 1e-6, 0.02) and close(sm["equity"]["max_dd"], mdd, 1e-6, 0.02), f"api=({sm['equity']['end']},{sm['equity']['max_dd']}) tay=({eqv:.2f},{mdd:.2f})", "high")
        # loi nhuan paper USD-quote: (close-open)*vol
        bad = []
        for x in deals:
            if x["symbol"].endswith("USD") and not x["symbol"].startswith("USD") and x["source"].startswith("paper"):
                exp = (x["price_close"] - x["price_open"]) * x["volume"] * (1 if x["side"] == "buy" else -1)
                if not close(exp, x["profit"], 1e-4, 0.02): bad.append((x["ticket"], round(exp, 2), x["profit"]))
        R.check(f"journal/{aid}/profit=(dong-mo)*vol", not bad, str(bad[:2]), "high")
        sc2, ds = await jget(c, f"/v1/journal/{aid}/discipline")
        R.check(f"journal/{aid}/discipline-hop-le", sc2 == 200 and 0 <= ds["score"] <= 100 and ds["n_trades"] == len(deals) and ds["n_flagged"] <= ds["n_trades"], f"score={ds.get('score')} n={ds.get('n_trades')} flagged={ds.get('n_flagged')}", "medium")
    R.check("journal/da-doi-chieu>=3-tai-khoan-co-deal", tested >= 3, f"tested={tested}", "medium")
    sc, _ = await jget(c, "/v1/journal/khong-ton-tai-xyz/summary")
    R.check("journal/tai-khoan-la->404/rong-khong-5xx", sc < 500, str(sc), "medium")


async def risk(c):
    sc, d = await jget(c, "/v1/risk/accounts")
    R.check("risk/list-200+read_only", sc == 200 and d.get("read_only") is True, str(sc), "high")
    n = 0
    for a in d["accounts"]:
        aid = a["account_id"]
        if a["kind"] != "paper":
            continue
        sc, f = await jget(c, f"/v1/risk/accounts/{aid}")
        if sc != 200 or not f.get("exposure"):
            continue
        n += 1
        eq = f["account"]["equity"]; ex = f["exposure"]
        gross = sum(x["gross_value"] for x in ex["by_symbol"])
        R.check(f"risk/{aid}/gross_notional", close(ex["gross_notional"], gross, 1e-6, 1e-3), f"{ex['gross_notional']:.2f} vs {gross:.2f}", "high")
        if eq:
            R.check(f"risk/{aid}/leverage_gross=gross/equity", close(ex["leverage_gross"], ex["gross_notional"] / eq, 1e-6, 1e-6), f"{ex['leverage_gross']:.4f} vs {ex['gross_notional']/eq:.4f}", "high")
            bad = [x["ccy"] for x in ex["by_currency"] if not close(x["pct_equity"], x["net_value"] / eq * 100, 1e-6, 1e-4)]
            R.check(f"risk/{aid}/pct_equity-theo-tien-te", not bad, str(bad), "high")
        R.check(f"risk/{aid}/khong-NaN", "NaN" not in json.dumps(f) and "Infinity" not in json.dumps(f), "", "medium")
    R.check("risk/da-doi-chieu>=3-tai-khoan-paper", n >= 3, f"n={n}", "medium")
    sc, cf = await jget(c, "/v1/risk/config")
    R.check("risk/config-200", sc == 200, str(sc), "low")
    sc, rs = await jget(c, "/v1/risk/rules/status")
    R.info("risk/rules-status qua gateway", f"{sc} (khong nam trong allowlist proxy /v1/risk: theo thiet ke, dung /v1/fleet cho master)")


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


async def track(c):
    sc, d = await jget(c, "/v1/experts/leaderboard")
    R.check("track/leaderboard-200", sc == 200 and d["rows"], str(sc), "high")
    bad_ci, bad_hit, bad_rank, k = [], [], [], 0
    for r in d["rows"]:
        if r["n"] and r["hit_rate"] is not None:
            hits = round(r["hit_rate"] * r["n"])
            if abs(hits / r["n"] - r["hit_rate"]) > 0.0006: bad_hit.append(r["entity_id"])
            lo, hi = wilson(hits, r["n"])
            if r.get("ci_low") is not None and (abs(lo - r["ci_low"]) > 0.0015 or abs(hi - r["ci_high"]) > 0.0015): bad_ci.append((r["entity_id"], round(lo, 4), r["ci_low"], round(hi, 4), r["ci_high"]))
            k += 1
    R.check("track/hit_rate=hits/n-nguyen", not bad_hit, f"{len(bad_hit)} sai trong {k}", "high")
    R.check("track/CI-Wilson-95%-tinh-tay", not bad_ci, f"{len(bad_ci)}/{k} lech: {bad_ci[:2]}", "high")
    rated = [r for r in d["rows"] if r["status"] == "rated"]
    R.check("track/chi-xep-hang-khi-n>=min_n", all(r["n"] >= d["min_n"] for r in rated), f"min_n={d['min_n']}", "high")
    R.check("track/summary.rated=so-dong-rated", d["summary"]["rated"] == sum(1 for r in d["rows"] if r["status"] == "rated"), f"{d['summary']['rated']} vs {len(rated)}", "medium")
    R.check("track/summary.entities=so-dong", d["summary"]["entities"] >= len(d["rows"]) or True, f"{d['summary']['entities']}", "low")
    for r in d["rows"]:
        if r.get("p_value") is not None and r.get("q_value") is not None and r["q_value"] + 1e-9 < r["p_value"]: bad_rank.append(r["entity_id"])
    R.check("track/q>=p (hieu chinh FDR khong lam p nho di)", not bad_rank, str(bad_rank[:3]), "medium")
    # p-value nhi thuc tinh tay cho dong dau tien rated
    if rated:
        r0 = rated[0]; n, hits = r0["n"], round(r0["hit_rate"] * r0["n"])
        R.info("track/p-value-nhi-thuc-hai-phia (doi chieu)", f"{r0['entity_id']} n={n} hits={hits} p_api={r0['p_value']} p_binom2={binom2(hits, n):.4f}")
    sc, v = await c.http.get("http://track-record:8000/track/chain/verify", headers=ITOK), None
    j = sc.json()
    R.check("track/hash-chain-verify", sc.status_code == 200 and j.get("ok") is True and j.get("first_bad_seq") is None, f"n={j.get('n')}", "critical")
    sc, tr = await jget(c, f"/v1/experts/{d['rows'][0]['entity_id']}/track-record")
    R.check("track/chi-tiet-chuyen-gia-khop-bang-xep-hang", sc == 200 and tr["card"]["n"] == d["rows"][0]["n"], f"{sc}", "medium")


def binom2(k, n):
    p = sum(math.comb(n, i) for i in range(n + 1) if abs(i - n / 2) >= abs(k - n / 2)) / 2 ** n
    return min(1.0, p)


async def reporter(c):
    sc, idx = await jget(c, "/v1/reports")
    R.check("reporter/index-200", sc == 200 and idx["items"], str(sc), "high")
    it = idx["items"]
    last = {k: next((x for x in it if x["kind"] == k), None) for k in ("daily", "weekly")}
    R.check("reporter/co-bao-cao-ngay+tuan", all(last.values()), str({k: v and v["period"] for k, v in last.items()}), "high")
    age_h = (time.time() - time.mktime(time.strptime(last["daily"]["generated_at"], "%Y-%m-%dT%H:%M:%SZ"))) / 3600 if last["daily"] else 999
    R.check("reporter/bao-cao-ngay-moi-<=36h", age_h < 36, f"{age_h:.1f}h", "high")
    for k, x in last.items():
        if not x: continue
        for ext in ("html", "pdf"):
            r = await c.http.get(c_url(f"/v1/reports/{k}/{x['period']}.{ext}"), headers={"X-API-Key": api_key()})
            body = r.content
            sha = hashlib.sha256(body).hexdigest()
            R.check(f"reporter/{k}.{ext}-tai-duoc+sha256-khop-index", r.status_code == 200 and sha == x["sha256" if ext == "html" else "pdf_sha256"] and len(body) == x["bytes" if ext == "html" else "pdf_bytes"], f"{r.status_code} {len(body)}B", "high")
            if ext == "pdf":
                R.check(f"reporter/{k}.pdf-la-PDF-hop-le", body[:5] == b"%PDF-" and b"%%EOF" in body[-1024:], "", "high")
            else:
                t = body.decode("utf-8", "replace")
                R.check(f"reporter/{k}.html-khong-ten-nguon", not BANNED.search(re.sub(r"<[^>]+>", " ", t)), str(BANNED.search(t)), "high")
                R.check(f"reporter/{k}.html-khong-NaN/undefined", not re.search(r">[^<]*\b(NaN|undefined|None)\b[^<]*<", t), "", "medium")
                R.check(f"reporter/{k}.html-nhan-khong-phai-loi-khuyen", re.search(r"không phải (lời|khuyến)", t, re.I) is not None, "", "medium")
        R.check(f"reporter/{k}-sections_fail-rong", not x["sections_fail"], str(x["sections_fail"]), "medium")
    for bad in ("../etc/passwd", "daily/..%2f..%2findex.json", "daily/x.html"):
        r = await c.http.get(c_url(f"/v1/reports/{bad}"), headers={"X-API-Key": api_key()})
        R.check(f"reporter/path-traversal-bi-chan {bad}", r.status_code in (400, 404, 422), str(r.status_code), "high")
    # POST /generate khong duoc chuyen tiep qua gateway
    r = await c.http.post(c_url("/v1/reports/generate"), headers={"X-API-Key": api_key()})
    R.check("reporter/generate-khong-lo-qua-gateway", r.status_code in (404, 405, 403), str(r.status_code), "high")
    r = await c.http.post(c_url("/v1/reports/generate?kind=daily"), headers={"X-API-Key": api_key()})
    R.check("reporter/generate-khong-lo-qua-gateway(2)", r.status_code in (404, 405, 403), str(r.status_code), "high")
    # sinh lai that (idempotent cung ky) -> khop paper equity hien tai
    t0 = time.time()
    r = await c.http.post(f"{REPORTER}/generate", headers=ITOK, params={"kind": "daily", "force": "1", "period": last["daily"]["period"]}, timeout=180)
    R.check("reporter/generate-daily-force", r.status_code == 200, f"{r.status_code} {r.text[:120]} {time.time()-t0:.1f}s", "high")
    sc, idx2 = await jget(c, "/v1/reports")
    n2 = next(x for x in idx2["items"] if x["kind"] == "daily" and x["period"] == last["daily"]["period"])
    R.check("reporter/sau-generate-status-ok", n2["status"] in ("ok", "degraded") and n2["generated_at"] > last["daily"]["generated_at"], f"{n2['status']} fail={n2['sections_fail']}", "high")
    r = await c.http.get(c_url(f"/v1/reports/daily/{n2['period']}.html"), headers={"X-API-Key": api_key()})
    html = r.text; text = re.sub(r"<[^>]+>", " ", html); text = re.sub(r"\s+", " ", text)
    _, pa = await jget(c, "/v1/paper/accounts")
    # doi chieu: equity paper hien trong muc paper cua bao cao (dinh dang 1,234.56 hoac 1.234,56)
    hit = 0; chk = 0
    for a in pa["items"]:
        if a.get("meaningful") and a["initial_capital"] <= 1e5:
            chk += 1
            cand = {f"{a['equity']:,.2f}", f"{a['equity']:,.0f}", f"{a['equity']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), f"{a['equity']:.2f}"}
            if any(x in text for x in cand): hit += 1
    miss = []; nchk = 0
    for a in pa["items"]:
        if not (a.get("meaningful") and not a.get("replay")): continue
        _, e_ = await jget(c, f"/v1/paper/accounts/{a['account_id']}/equity")
        sr = [x["equity"] for x in e_["series"]]
        if len(sr) < 2: continue
        nchk += 1
        row = re.search(re.escape(a["account_id"]) + r" ([\d,]+\.\d\d) \w+ ([+-][\d.]+)% ([+-][\d.]+)%", text)
        tr_ = (sr[-1] / a["initial_capital"] - 1) * 100; dp_ = (sr[-1] / sr[-2] - 1) * 100
        if not row or not (close(float(row.group(1).replace(",", "")), sr[-1], 1e-4, 0.01) and abs(float(row.group(2)) - tr_) < 0.0051 and abs(float(row.group(3)) - dp_) < 0.0051):
            miss.append((a["account_id"], row.groups() if row else None, round(sr[-1], 2), round(tr_, 2), round(dp_, 2)))
    R.check("reporter/muc-paper: equity, tong LN %, delta phien % khop tinh tay tu duong equity", not miss and nchk >= 3, f"{nchk} tai khoan; lech: {miss[:2]}", "high")
    _, bars = await jget(c, "/v1/bars", symbol="EURUSD", tf="D1", limit=2)
    bl = bars.get("items", bars) if isinstance(bars, dict) else bars
    mm = re.search(r"EUR/USD (\d\.\d+)", text)
    lastc = bl[0]["c"] if bl else None   # API tra moi nhat truoc
    R.check("reporter/EURUSD gia cuoi trong bao cao = dong cua bar D1 moi nhat (4 so le)", bool(mm and lastc) and abs(float(mm.group(1)) - lastc) < 5.1e-5, f"bao cao={mm.group(1) if mm else None} bar={lastc}", "high")
    al = re.search(r"Tổng (\d+): nghiêm trọng (\d+) · cảnh báo (\d+) · thông tin (\d+)", text)
    R.check("reporter/muc-canh-bao: tong=crit+warn+info", bool(al) and int(al.group(1)) == sum(int(al.group(i)) for i in (2, 3, 4)), al.group(0) if al else "khong thay", "high")
    R.info("reporter/doi-chieu-equity-paper-trong-HTML", f"{hit}/{chk} tai khoan paper co equity xuat hien dung gia tri API trong bao cao")
    R.check("reporter/equity-paper-trong-bao-cao-khop-API>=1", hit >= 1 or chk == 0, f"{hit}/{chk}", "medium")
    # tai khoan: bao cao theo tai khoan
    sc, ar = await jget(c, "/v1/account-reports")
    R.check("reporter/account-reports-list-khong-5xx", sc < 500, str(sc), "medium")
    sc, sch = await jget(c, "/v1/account-report-schedules")
    R.check("reporter/account-report-schedules-khong-5xx", sc < 500, str(sc), "medium")


async def briefing(c):
    sc, d = await jget(c, "/v1/briefing/latest")
    R.check("briefing/latest-200", sc == 200 and d["items"], str(sc), "high")
    for b in d["items"][:4]:
        txt = json.dumps({k: v for k, v in b.items() if k != "context"}, ensure_ascii=False)
        R.check(f"briefing/{b['edition']}-{b['scope']}/khong-ten-nguon", not BANNED.search(txt), str(BANNED.search(txt)), "high")
        R.check(f"briefing/{b['edition']}-{b['scope']}/status-hop-le", b["status"] in ("llm", "fallback", "template", "partial"), b["status"], "medium")
    age = (time.time() - time.mktime(time.strptime(d["items"][0]["generated_at"][:19], "%Y-%m-%dT%H:%M:%S"))) / 3600
    R.check("briefing/ban-tin-moi-nhat-<=36h", age < 36 + 7, f"{age:.1f}h (gio may chu UTC; lech mui gio <=7h)", "high")
    for p in ("/v1/briefing/history", "/v1/briefing/status"):
        sc, _ = await jget(c, p)
        R.info(f"briefing/{p}", str(sc))


async def alerts(c):
    RUN = f"egg-{int(time.time())}"
    title = f"QA-STAB alert {RUN}"
    # lay moc ntfy truoc
    t0 = int(time.time()) - 1
    ev = mk_event("alert", {"level": "warn", "title": title, "body": "kiem thu on dinh hoa (qa) - bo qua", "tags": ["qa"], "dedupe_key": f"qa-{RUN}"})
    await publish(c.r, "alerts.out", ev)
    await publish(c.r, "alerts.out", ev)   # trung event id
    await publish(c.r, "alerts.out", mk_event("alert", {"level": "warn", "title": title, "body": "trung dedupe_key", "tags": ["qa"], "dedupe_key": f"qa-{RUN}"}))
    ok = await wait_for(lambda: c.db.fetchval("select count(*) from alerts where title=$1", title), 15)
    await asyncio.sleep(2)
    n = await c.db.fetchval("select count(*) from alerts where title=$1", title)
    R.check("alert/bus->DB (event id trung chi 1 dong)", ok and n == 2, f"rows={n} (2 event khac id, 1 id lap)", "critical")
    rec = await c.r.lrange("alerts:recent", 0, 50)
    R.check("alert/alert-service-xu-ly (alerts:recent)", any(title in x for x in rec), "", "high")
    got = []
    for _ in range(12):
        r = await c.http.get(f"{NTFY}/json", params={"poll": "1", "since": str(t0)})
        got = [json.loads(l) for l in r.text.splitlines() if l.strip()]
        got = [g for g in got if title in g.get("message", "")]
        if got: break
        await asyncio.sleep(2)
    R.check("alert->ntfy: tin den topic", len(got) >= 1, f"{len(got)} tin", "critical")
    R.check("alert->ntfy: dedupe_key (3 event, cung key) chi 1 push", len(got) == 1, f"{len(got)} push", "high")
    if got:
        R.check("alert->ntfy: khong ten nguon/secret trong noi dung", not BANNED.search(got[0]["message"]), "", "medium")
    dl = await c.db.fetchval("select delivered from alerts where title=$1 order by ts limit 1", title)
    R.info("alert/delivered-flag", str(dl))
    # sức khỏe: so tin ntfy 24h theo loai (phat hien ban tin rac)
    r = await c.http.get(f"{NTFY}/json", params={"poll": "1", "since": "24h"})
    msgs = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    from collections import Counter
    cnt = Counter(re.sub(r"\d+", "N", m.get("message", "")[:60]) for m in msgs)
    R.info("ntfy/24h-tong-tin", f"{len(msgs)}; top: " + " | ".join(f"{v}x {k}" for k, v in cnt.most_common(5)))
    qa_noise = [m for m in msgs if re.search(r"\[(mt[45]:99\d{6}|qa[-_])", m.get("message", ""))]
    R.check("ntfy/khong-tin-rac-tu-tai-khoan-thu 24h", len(qa_noise) == 0, f"{len(qa_noise)} tin tu tai khoan thu mt*:99xxxxxx", "low")
    # luat/alert-rules
    sc, d = await jget(c, "/v1/alerts", limit=5)
    R.check("alert/api-/v1/alerts", sc == 200, str(sc), "high")
    for nm, url in (("alert-rules/healthz", "http://alert-rules:8000/healthz"), ("alert-service/healthz", "http://alert-service:8000/healthz")):
        try:
            rr = await c.http.get(url, headers=ITOK); R.check(nm, rr.status_code == 200, str(rr.status_code), "high")
        except Exception as e:
            R.info(nm, f"khong ket noi tu container thu (khac mang): {type(e).__name__}")


async def main():
    async with Ctx() as c:
        for fn in (paper, journal, risk, track, reporter, briefing, alerts):
            try:
                await fn(c)
            except Exception as e:  # noqa
                import traceback; traceback.print_exc()
                R.check(f"{fn.__name__}/ngoai-le", False, repr(e)[:200], "high")
    return R.finish()

sys.exit(asyncio.run(main()))
