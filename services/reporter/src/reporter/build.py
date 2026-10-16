"""Dựng ngữ cảnh báo cáo từ dữ liệu thô. Mỗi mục độc lập: lỗi/thiếu dữ liệu -> {"ok": False, "error": ...} (hiện 'Chưa có dữ liệu')."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from tscommon.sources import scrub_obj

from . import charts
from .collect import Raw
from .config import Settings

log = logging.getLogger("reporter.build")

SRC_PRI = ["dukascopy", "yahoo_daily", "frankfurter"]
IMPACT_VI = {"high": "Cao", "med": "Trung bình", "low": "Thấp"}
SECTION_TITLES = {
    "market": "Tổng quan thị trường", "calendar": "Lịch sự kiện", "news": "Tin quan trọng & tình cảm",
    "experts": "Đồng thuận tín hiệu chuyên gia", "mt": "Tài khoản MT & rủi ro", "paper": "Hiệu suất mô phỏng (paper)",
    "journal": "Nhật ký giao dịch & kỷ luật", "briefing": "Bản tin thị trường (AI tóm tắt)",
    "risk": "Rủi ro & stress nổi bật", "tech": "Chỉ báo kỹ thuật nổi bật", "system": "Sức khoẻ hệ thống & dữ liệu",
}


def pdt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def num(v, d=2):
    return "—" if v is None else f"{v:,.{d}f}"


def pct(v, d=2):
    """v là tỷ lệ (0.01 = 1%)."""
    return "—" if v is None else f"{v * 100:+.{d}f}%"


def pct_pts(v, d=2):
    """v đã ở đơn vị phần trăm."""
    return "—" if v is None else f"{v:+.{d}f}%"


def _sec(fn, *a):
    try:
        r = fn(*a)
        r = r if isinstance(r, dict) else {}
        r.setdefault("ok", True)
        return r
    except Exception as e:  # noqa: BLE001
        log.exception("mục lỗi")
        return {"ok": False, "error": f"lỗi xử lý ({type(e).__name__})"}


def _fail(raw: Raw, *names) -> dict | None:
    bad = [n for n in names if not raw.ok(n)]
    if bad and len(bad) == len(names):
        return {"ok": False, "error": "chưa đọc được dữ liệu " + ", ".join(bad)}
    return None


# ---------- thị trường ----------
def _series(raw: Raw, sym: str):
    d = raw.data.get(f"bars:{sym}")
    rows = d.get("items") if isinstance(d, dict) else None
    if not rows:
        return None
    by: dict[str, dict] = {}
    for r in rows:
        by.setdefault(r.get("source") or "", {})[r["ts_open"]] = r

    newest = pdt(max(max(v) for v in by.values()))
    cands = [k for k in by if (newest - pdt(max(by[k]))).days < 2]   # nguồn có nến gần nhất (<2 ngày: nến canon MT5 chốt trễ 1 ngày so với nến ngày đang chạy); chọn nguồn nhiều lịch sử nhất

    def key(s):
        return (len(by[s]), -(SRC_PRI.index(s) if s in SRC_PRI else 99))

    best = max(cands, key=key)
    rows = dict(by[best])
    for k in by:   # gateway trả chuỗi gộp nhiều nguồn (canon + nến sống): nối thêm các nến MỚI hơn nguồn chính để giá cuối khớp nến mới nhất
        if k != best:
            last = max(rows)
            for t, r in by[k].items():
                if t > last:
                    rows[t] = r
    return [rows[t] for t in sorted(rows)], best


def sec_market(raw: Raw, cfg, now, kind):
    groups: dict[str, list] = {}
    for grp, sym, lab in cfg.instruments:
        s = _series(raw, sym)
        if not s or len(s[0]) < 2:
            continue
        bars, src = s
        closes = [b["c"] for b in bars]
        last_ts = pdt(bars[-1]["ts_open"])
        d1 = closes[-1] / closes[-2] - 1 if closes[-2] else None
        ref = None
        for b in reversed(bars):
            if pdt(b["ts_open"]) <= last_ts - timedelta(days=7):
                ref = b["c"]
                break
        w1 = closes[-1] / ref - 1 if ref else None
        dec = 4 if closes[-1] < 20 else 2
        groups.setdefault(grp, []).append({
            "symbol": sym, "label": lab, "last": num(closes[-1], dec), "d1": d1, "w1": w1, "d1s": pct(d1), "w1s": pct(w1),
            "asof": last_ts.strftime("%d/%m"), "spark": charts.sparkline(closes[-30:], title=f"{lab} 30 phiên"),
            "up": (d1 or 0) >= 0})
    if not groups:
        errs = sorted({v for k, v in raw.errors.items() if k.startswith("bars:")})
        return {"ok": False, "error": "chưa có nến D1"}
    allr = [r for g in groups.values() for r in g]
    key = "w1" if kind == "weekly" else "d1"
    chart_rows = sorted(((r["label"], (r[key] * 100) if r[key] is not None else None) for r in allr),
                        key=lambda x: -(x[1] if x[1] is not None else -999))
    movers = sorted((r for r in allr if r[key] is not None), key=lambda r: r[key])
    return {"groups": groups, "chart": charts.hbar(chart_rows, w=300, label_w=104, unit="%"),
            "chart_title": "Thay đổi " + ("7 ngày" if kind == "weekly" else "phiên gần nhất"),
            "best": movers[-1] if movers else None, "worst": movers[0] if movers else None, "n": len(allr)}


# ---------- lịch ----------
def sec_calendar(raw: Raw, cfg, now, kind):
    f = _fail(raw, "calendar")
    if f:
        return f
    tz = ZoneInfo(cfg.tz)
    items = (raw.data["calendar"] or {}).get("items") or []
    cap = 45 if kind == "weekly" else 25
    items = [i for i in items if pdt(i.get("ts"))]
    items.sort(key=lambda i: (i.get("impact") != "high", i["ts"]))
    shown = sorted(items[:cap], key=lambda i: i["ts"])
    rows = []
    for i in shown:
        t = pdt(i["ts"]).astimezone(tz)
        rows.append({"day": t.strftime("%d/%m"), "time": t.strftime("%H:%M"), "country": i.get("country") or "",
                     "title": i.get("title") or "", "impact": i.get("impact"),
                     "impact_vi": IMPACT_VI.get(i.get("impact"), str(i.get("impact"))),
                     "forecast": i.get("forecast") or "—", "previous": i.get("previous") or "—"})
    n_high = sum(1 for i in items if i.get("impact") == "high")
    nxt = next((r for r in rows if r["impact"] == "high"), None)
    return {"rows": rows, "total": len(items), "high": n_high, "hidden": max(0, len(items) - cap), "next_high": nxt,
            "title": "Lịch " + ("tuần tới" if kind == "weekly" else "24 giờ tới")}


# ---------- tin ----------
def sec_news(raw: Raw, cfg, now, kind):
    f = _fail(raw, "news")
    if f:
        return f
    tz = ZoneInfo(cfg.tz)
    items = (raw.data["news"] or {}).get("items") or []
    sc = [i for i in items if isinstance(i.get("sentiment"), (int, float))]
    top = sorted(sc, key=lambda i: -abs(i["sentiment"]))[: 12 if kind == "weekly" else 6]
    rows = []
    for i in top:
        t = pdt(i.get("published_at"))
        rows.append({"title": (i.get("title") or "")[:160], "sent": i["sentiment"],
                     "time": t.astimezone(tz).strftime("%d/%m %H:%M") if t else "", "symbols": ", ".join((i.get("symbols") or [])[:4])})
    by: dict[str, list] = {}
    for i in sc:
        for s in i.get("symbols") or []:
            by.setdefault(s, []).append(i["sentiment"])
    avg = sorted(((s, mean(v), len(v)) for s, v in by.items() if len(v) >= 2), key=lambda x: -abs(x[1]))[:10]
    pos = sum(1 for i in sc if i["sentiment"] > .25)
    neg = sum(1 for i in sc if i["sentiment"] < -.25)
    return {"rows": rows, "total": len(items), "scored": len(sc), "avg_all": mean(i["sentiment"] for i in sc) if sc else None,
            "avg_chart": charts.hbar([(f"{s} (n={n})", a) for s, a, n in avg], unit="", digits=2) if avg else "",
            "share": charts.stacked_share([("Tích cực", pos), ("Trung lập", len(sc) - pos - neg), ("Tiêu cực", neg)]),
            "pos": pos, "neg": neg, "neu": len(sc) - pos - neg}


# ---------- chuyên gia ----------
def sec_experts(raw: Raw, cfg, now, kind):
    f = _fail(raw, "signals")
    if f:
        return f
    items = (raw.data["signals"] or {}).get("items") or []
    by: dict[str, dict] = {}
    for s in items:
        if s.get("side") in ("buy", "sell"):
            r = by.setdefault(s["symbol"], {"symbol": s["symbol"], "buy": 0, "sell": 0})
            r[s["side"]] += 1
    rows = sorted(by.values(), key=lambda r: -(r["buy"] + r["sell"]))[:12]
    for r in rows:
        r["lean"] = "Nghiêng mua" if r["buy"] > r["sell"] else "Nghiêng bán" if r["sell"] > r["buy"] else "Cân bằng"
    return {"rows": rows, "total": len(items), "empty": not rows}


# ---------- MT + rủi ro ----------
def _risk_rows(raw: Raw, kind_filter=None):
    d = raw.data.get("risk")
    accs = d.get("accounts") if isinstance(d, dict) else None
    if accs is None:
        return None
    return [a for a in accs if kind_filter is None or a.get("kind") == kind_filter]


def _risk_fmt(a):
    ws = a.get("worst_stress") or {}
    ml = a.get("margin_level")
    return {"id": a.get("account_id"), "platform": a.get("platform") or a.get("kind") or "", "currency": a.get("currency") or "",
            "equity": num(a.get("equity")), "margin": "—" if ml is None else f"{ml:,.0f}%",
            "lev": num(a.get("leverage_effective"), 2), "day": pct_pts(a.get("day_pnl_pct")), "dd": pct_pts(a.get("dd_from_peak_pct")),
            "var": pct_pts(a.get("var95_1d_pct")), "es": pct_pts(a.get("es975_1d_pct")),
            "stress": f"{ws.get('name', '—')} ({pct_pts(ws.get('pnl_pct'))})" if ws else "—",
            "budget": a.get("budget_status") or "—", "warnings": a.get("warnings") or [], "stale": bool(a.get("stale"))}


def sec_mt(raw: Raw, cfg, now, kind):
    risk_mt = _risk_rows(raw, "mt")
    if risk_mt is not None:   # equity = 0 nghĩa là chưa hoạt động thật
        risk_mt = [a for a in risk_mt if (a.get("equity") or 0) > 0]
    f = _fail(raw, "accounts")
    if f and risk_mt is None:
        return f
    accs = raw.data.get("accounts") or []
    active = [a for a in accs if (a.get("equity") or 0) > 0 or a.get("positions")]
    reg = len(accs)
    out = {"registered": reg, "risk_note": None}
    if risk_mt is None:
        out["risk_note"] = "Chưa có dữ liệu rủi ro (endpoint /v1/risk/accounts chưa khả dụng)."
    if risk_mt:
        out["rows"] = [_risk_fmt(a) for a in risk_mt]
        out["mode"] = "risk"
    elif active:
        out["rows"] = [{"id": a["account_id"], "platform": a.get("platform", ""), "equity": num(a.get("equity")),
                        "balance": num(a.get("balance")), "margin": num(a.get("margin")), "pos": len(a.get("positions") or [])}
                       for a in active]
        out["mode"] = "acc"
    else:
        out["rows"] = []
        out["mode"] = "none"
        out["empty_msg"] = (f"Chưa có tài khoản MT hoạt động ({reg} tài khoản đã đăng ký nhưng equity = 0 và chưa có vị thế; "
                            "chờ EA gửi dữ liệu thật).") if reg else "Chưa có tài khoản MT hoạt động."
    return out


def sec_risk(raw: Raw, cfg, now, kind):
    rows = _risk_rows(raw)
    if rows is None:
        return {"ok": False, "error": "endpoint /v1/risk/accounts chưa khả dụng"}
    fm = [_risk_fmt(a) for a in rows]
    bad = [r for r in fm if r["budget"] in ("warn", "crit") or r["warnings"]]
    st = [(a.get("account_id"), (a.get("worst_stress") or {}).get("pnl_pct")) for a in rows if a.get("worst_stress")]
    return {"rows": fm, "flagged": bad,
            "stress_chart": charts.hbar(sorted(st, key=lambda x: x[1] if x[1] is not None else 0), unit="%") if st else "",
            "empty": not rows}


# ---------- paper ----------
def _idx_change(series, now, kind):
    """Thay đổi chỉ số (base 100) trong kỳ: tuần = so với điểm <= now-7d (hoặc điểm đầu), ngày = so với điểm liền trước."""
    pts = [(pdt(p["ts"]), p["index"]) for p in series or [] if p.get("index") is not None and pdt(p.get("ts"))]
    if len(pts) < 2:
        return None
    if kind == "weekly":
        ref = next((v for t, v in reversed(pts) if t <= now - timedelta(days=7)), pts[0][1])
    else:
        ref = pts[-2][1]
    return pts[-1][1] / ref - 1 if ref else None


def _num(s):
    try:
        return float(s.replace("%", "").replace("+", ""))
    except (ValueError, AttributeError):
        return None


def sec_paper(raw: Raw, cfg, now, kind):
    f = _fail(raw, "paper_accounts")
    if f:
        return f
    items = {i["account_id"]: i for i in (raw.data["paper_accounts"] or {}).get("items") or []}
    rows = []
    for aid in raw.data.get("_paper_ids") or []:
        a = items.get(aid) or {}
        st = raw.data.get(f"stats:{aid}") or {}
        eq = raw.data.get(f"equity:{aid}") or {}
        ser, bm = eq.get("series") or [], eq.get("benchmark") or []
        ch, bch = _idx_change(ser, now, kind), _idx_change(bm, now, kind)
        cur_dd = st.get("current_drawdown")
        rows.append({"id": aid, "name": a.get("name") or aid, "strategy": a.get("strategy") or "", "ccy": a.get("base_ccy") or "",
                     "equity": num(a.get("equity")), "rets": pct(a.get("total_return")),
                     "dd": pct(a.get("drawdown")), "maxdd": pct(st.get("max_drawdown")),
                     "sharpe": num(st.get("sharpe"), 2) if st.get("reliable") else "n/a",
                     "period_ch": pct(ch), "bench": a.get("benchmark_id") or "", "bench_ch": pct(bch) if a.get("benchmark_id") else "—",
                     "excess": pct((ch - bch) if ch is not None and bch is not None else None),
                     "days": st.get("days"), "short": not st.get("reliable"), "status": a.get("status") or "",
                     "spark": charts.sparkline([p["index"] for p in ser if p.get("index") is not None][-60:], title=f"{aid} chỉ số vốn"),
                     "dd_use": charts.meter(abs(cur_dd) / 0.5 if cur_dd is not None else None, label="DD / giới hạn 50%")})
    if not rows:
        return {"ok": False, "error": "chưa có tài khoản mô phỏng đang hoạt động"}
    n_short = sum(1 for r in rows if r["short"])
    return {"rows": rows, "n": len(rows), "n_short": n_short, "period_label": "7 ngày" if kind == "weekly" else "phiên gần nhất",
            "chart": charts.hbar([(r["id"], _num(r["period_ch"])) for r in rows], unit="%")}


# ---------- nhật ký giao dịch (journal; chỉ báo cáo tuần) ----------
def _jn(v, d=2):
    return "—" if v is None else f"{v:+,.{d}f}"


def sec_journal(raw: Raw, cfg, now, kind):
    f = _fail(raw, "journal_accounts")
    if f:
        return f
    rows = []
    for aid in raw.data.get("_journal_ids") or []:
        rv = raw.data.get(f"journal:{aid}")
        if not rv:
            continue
        s, d = rv.get("summary") or {}, rv.get("discipline") or {}
        if not s.get("n"):
            continue
        dl = rv.get("delta") or {}
        rows.append({"id": aid, "n": s["n"], "net": _jn(s.get("net")), "net_up": (s.get("net") or 0) >= 0, "wr": pct(s.get("win_rate"), 0),
                     "pf": num(s.get("profit_factor")), "exp": _jn(s.get("expectancy")), "avg_r": num(s.get("avg_r")),
                     "d_net": _jn(dl.get("net")), "score": "—" if d.get("score") is None else f"{d['score']:.0f}/100", "flagged": d.get("n_flagged", 0),
                     "net_flagged": _jn(d.get("net_flagged")), "net_clean": _jn(d.get("net_clean")),
                     "streak": (rv.get("streaks") or {}).get("max_loss_streak", 0), "insights": (rv.get("insights") or [])[:4],
                     "rules": [r for r in (d.get("rules") or []) if r.get("count")][:4]})
    if not rows:
        return {"rows": [], "week": raw.data.get("_journal_week"), "empty": True,
                "empty_msg": "Chưa có tài khoản MT/paper nào có lệnh đã đóng trong tuần (EA gửi lịch sử deal; xem /#/nhat-ky)."}
    return {"rows": rows, "week": raw.data.get("_journal_week"), "empty": False}


# ---------- bản tin AI (briefing; chỉ báo cáo ngày) ----------
SCOPE_VI = {"vn": "Việt Nam", "intl": "Quốc tế"}
EDITION_VI = {"morning": "sáng", "close": "cuối phiên"}


def sec_briefing(raw: Raw, cfg, now, kind):
    f = _fail(raw, "briefing")
    if f:
        return f
    tz = ZoneInfo(cfg.tz)
    rows = []
    for b in (raw.get("briefing") or {}).get("items") or []:
        try:
            gen = pdt(b.get("generated_at"))
        except Exception:  # noqa: BLE001
            continue
        if gen is None or now - gen > timedelta(hours=36):
            continue
        titles = {i["n"]: i.get("title") for i in (b.get("context") or {}).get("items") or []}
        body = b.get("body") or {}
        cited = sorted({n for p in body.get("points") or [] for n in p.get("cites") or []})
        rows.append({"title": f"Bản tin {EDITION_VI.get(b.get('edition'), '')} — {SCOPE_VI.get(b.get('scope'), '')}", "when": gen.astimezone(tz).strftime("%d/%m %H:%M"),
                     "ai": b.get("status") == "llm", "model": b.get("model") if b.get("status") == "llm" else None, "headline": b.get("headline"),
                     "points": [{"text": p.get("text"), "cites": p.get("cites") or []} for p in (body.get("points") or [])[:8]],
                     "mood": (body.get("mood") or {}).get("text"), "watch": [w.get("text") if isinstance(w, dict) else str(w) for w in (body.get("watch") or [])[:4]],
                     "refs": [{"n": n, "title": titles.get(n)} for n in cited if titles.get(n)][:12]})
    if not rows:
        return {"rows": [], "empty": True}
    return {"rows": rows, "empty": False}


# ---------- kỹ thuật ----------
def sec_tech(raw: Raw, cfg, now, kind):
    f = _fail(raw, "analytics")
    if f:
        return f
    items = [i for i in (raw.data["analytics"] or {}).get("items") or [] if i.get("tf") == "D1" and i.get("heat") is not None]
    top = sorted(items, key=lambda i: -i["heat"])[:8]
    rows = [{"symbol": i.get("symbol", "?"), "heat": i["heat"], "trend": {"up": "Tăng", "down": "Giảm"}.get(i.get("trend"), "Đi ngang"),
             "rsi": num(i.get("rsi"), 0), "adx": num(i.get("adx"), 0), "bias": i.get("bias")} for i in top]
    return {"rows": rows, "empty": not rows}


# ---------- hệ thống ----------
def sec_system(raw: Raw, cfg, now, kind):
    if not raw.ok("system") and not raw.ok("datasources") and not raw.ok("alerts"):
        return {"ok": False, "error": "không đọc được /v1/system, /v1/data-sources, /v1/alerts"}
    back = timedelta(days=7 if kind == "weekly" else 1)
    out: dict = {"notes": []}
    sysd = raw.data.get("system")
    if sysd:
        svcs = sysd.get("services") or []
        up = sum(1 for s in svcs if s.get("up"))
        out["svc_up"], out["svc_total"] = up, len(svcs)
        out["svc_down"] = [s["name"] for s in svcs if not s.get("up")]
        out["svc_meter"] = charts.meter((len(svcs) - up) / len(svcs) if svcs else None, warn=.01, crit=.34, label="service lỗi")
        out["streams"] = [{"name": s["stream"], "len": s.get("length"), "last": (s.get("last_event_at") or "")[:19].replace("T", " ")}
                          for s in sysd.get("streams") or []][:12]
        out["sources"] = [{"name": s["name"], "age_h": (s.get("age_seconds") or 0) / 3600, "n24": s.get("count_24h")}
                          for s in sysd.get("sources") or []]
    else:
        out["notes"].append("Chưa có dữ liệu /v1/system")
    ds = raw.data.get("datasources")
    if ds:
        mk = ds.get("market") or []
        out["ds_counts"] = {"active": sum(1 for m in mk if m.get("state") == "active"),
                            "needs_key": sum(1 for m in mk if m.get("state") == "needs_key"),
                            "disabled": sum(1 for m in mk if m.get("state") == "disabled")}
        oks = [pdt(m.get("last_ok")) for m in mk if m.get("state") == "active" and m.get("last_ok")]
        newest = max((t for t in oks if t), default=None)
        act = out["ds_counts"]["active"]
        stale = bool(newest) and (now - newest).total_seconds() > 6 * 3600
        out["ds_summary"] = {"active": act, "total": len(mk) or act,
                             "age": f"{(now - newest).total_seconds() / 3600:.1f} giờ trước" if newest else "",
                             "state": "chậm cập nhật" if stale else ("ổn định" if act else "chưa có luồng hoạt động")}
        out["reconcile"] = (ds.get("reconcile") or {}).get("summary") or {}
    else:
        out["notes"].append("Chưa có dữ liệu /v1/data-sources")
    al = raw.data.get("alerts")
    if al:
        its = [a for a in al.get("items") or [] if pdt(a.get("ts")) and pdt(a["ts"]) >= now - back]
        lv = {"crit": 0, "warn": 0, "info": 0}
        for a in its:
            lv[a.get("level", "info")] = lv.get(a.get("level", "info"), 0) + 1
        notable = [a for a in its if a.get("level") in ("crit", "warn")][:6]
        out["alerts"] = {"total": len(its), **lv,
                         "notable": [{"level": a["level"], "title": (a.get("title") or "")[:140], "ts": a["ts"][:16].replace("T", " ")} for a in notable],
                         "truncated": len(al.get("items") or []) >= 500}
    else:
        out["notes"].append("Chưa có dữ liệu /v1/alerts")
    return out


# ---------- tóm tắt ----------
def summary_lines(kind, sec):
    L = []
    m = sec["market"]
    if m.get("ok") and m.get("best"):
        b, w = m["best"], m["worst"]
        key = "w1s" if kind == "weekly" else "d1s"
        L.append(f"Thị trường ({m['n']} mã): mạnh nhất {b['label']} {b[key]}, yếu nhất {w['label']} {w[key]}.")
    else:
        L.append("Thị trường: chưa có dữ liệu.")
    c = sec["calendar"]
    if c.get("ok"):
        s = f"Lịch: {c['high']} sự kiện tác động cao trong {'tuần tới' if kind == 'weekly' else '24 giờ tới'}"
        nh = c.get("next_high")
        s += f"; sớm nhất {nh['day']} {nh['time']} {nh['country']} {nh['title']}." if nh else "."
        L.append(s)
    else:
        L.append("Lịch: chưa có dữ liệu.")
    n = sec["news"]
    if n.get("ok") and n.get("avg_all") is not None:
        L.append(f"Tin: {n['total']} bài, tình cảm trung bình {n['avg_all']:+.2f} ({n['pos']} tích cực / {n['neg']} tiêu cực).")
    else:
        L.append("Tin: chưa có dữ liệu có điểm tình cảm.")
    p, mt = sec["paper"], sec["mt"]
    parts = []
    if p.get("ok"):
        parts.append(f"mô phỏng {p['n']} tài khoản" + (f" ({p['n_short']} mẫu còn ngắn)" if p["n_short"] else ""))
    if mt.get("ok"):
        parts.append("MT: chưa có tài khoản hoạt động" if mt.get("mode") == "none" else "MT: có dữ liệu")
    else:
        parts.append("MT: chưa có dữ liệu")
    L.append("Tài khoản: " + "; ".join(parts) + ".")
    j = sec.get("journal")
    if j and j.get("ok") and j.get("rows"):
        L.append("Nhật ký: " + "; ".join(f"{x['id']} {x['n']} lệnh, P/L {x['net']}, kỷ luật {x['score']}" for x in j["rows"][:3]) + ".")
    s = sec["system"]
    if s.get("ok") and "svc_up" in s:
        a = s.get("alerts") or {}
        L.append(f"Hệ thống: {s['svc_up']}/{s['svc_total']} service hoạt động; cảnh báo kỳ này: {a.get('total', 'n/a')} "
                 f"(nghiêm trọng {a.get('crit', 0)}, cảnh báo {a.get('warn', 0)}).")
    else:
        L.append("Hệ thống: chưa có dữ liệu.")
    return L


def build(kind: str, period: str, raw: Raw, cfg: Settings, now: datetime) -> dict:
    return scrub_obj(_build(kind, period, raw, cfg, now), drop_keys=False)


def _build(kind: str, period: str, raw: Raw, cfg: Settings, now: datetime) -> dict:
    sec = {
        "market": _sec(sec_market, raw, cfg, now, kind), "calendar": _sec(sec_calendar, raw, cfg, now, kind),
        "news": _sec(sec_news, raw, cfg, now, kind), "experts": _sec(sec_experts, raw, cfg, now, kind),
        "mt": _sec(sec_mt, raw, cfg, now, kind), "paper": _sec(sec_paper, raw, cfg, now, kind),
        "tech": _sec(sec_tech, raw, cfg, now, kind), "system": _sec(sec_system, raw, cfg, now, kind),
    }
    if kind == "weekly":
        sec["risk"] = _sec(sec_risk, raw, cfg, now, kind)
        sec["journal"] = _sec(sec_journal, raw, cfg, now, kind)
    else:
        sec["briefing"] = _sec(sec_briefing, raw, cfg, now, kind)
    order = ["market", "calendar", "news", "experts", "mt", "paper"] + (["journal", "risk"] if kind == "weekly" else ["briefing"]) + ["tech", "system"]
    tz = ZoneInfo(cfg.tz)
    loc = now.astimezone(tz)
    start = loc - timedelta(days=7 if kind == "weekly" else 1)
    return {
        "kind": kind, "kind_vi": "Báo cáo ngày" if kind == "daily" else "Báo cáo tuần", "period": period,
        "code": f"{'NGAY' if kind == 'daily' else 'TUAN'}-{period}",
        "generated_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "generated_vn": loc.strftime("%d/%m/%Y %H:%M") + " (giờ VN)",
        "window": f"{start.strftime('%d/%m %H:%M')} → {loc.strftime('%d/%m/%Y %H:%M')} (giờ VN)",
        "sections": sec, "order": order, "titles": SECTION_TITLES, "summary": summary_lines(kind, sec),
        "ok": [k for k in order if sec[k].get("ok")], "fail": [k for k in order if not sec[k].get("ok")],
        "errors": {k: "không đọc được" for k in raw.errors},
    }
