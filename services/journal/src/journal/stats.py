"""Thong ke nhat ky (HAM THUAN, khong I/O). Moi so lieu tinh tu giao dich DA DONG; tien theo tien te tai khoan.

Quy uoc:
- net = profit + swap + commission (commission/swap am = chi phi). Thang = net > 0; thua = net < 0; hoa = net == 0.
- win_rate = thang / tong so lenh (lenh hoa khong tinh la thang).
- profit_factor = tong lai / tong lo (None khi khong co lenh lo); expectancy = net trung binh / lenh.
- R-multiple theo GIA: (gia_dong - gia_vao) * huong / |gia_vao - SL ban dau| (gross, chi khi SL > 0).
- Duong von theo deal: equity_t = base + tich luy (net + thao tac so du). Thao tac so du (nap/rut) dich ca dinh (peak) va von
  cung luong => khong bi tinh la drawdown/loi nhuan. MaxDD tren duong von DA CHOT (khong gom floating).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from .models import Trade

SESSIONS = [("asia", 0, 7), ("london", 7, 12), ("london_ny", 12, 16), ("ny", 16, 21), ("late", 21, 24)]  # gio UTC cua LUC VAO LENH
R_BINS = [-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0]


def trades_only(ts: Iterable[Trade]) -> list[Trade]:
    return sorted((t for t in ts if t.kind == "trade"), key=lambda t: (t.time_close, t.ticket))


def session_of(dt: datetime) -> str:
    h = dt.astimezone(timezone.utc).hour
    for name, a, b in SESSIONS:
        if a <= h < b:
            return name
    return "late"


def _r(x: Optional[float], n: int = 4) -> Optional[float]:
    return None if x is None else round(x, n)


def summarize(trades: list[Trade]) -> dict:
    """Thong ke tong hop cho tap lenh (chi kind=trade)."""
    ts = [t for t in trades if t.kind == "trade"]
    n = len(ts)
    out: dict = {"n": n}
    if n == 0:
        return {**out, "wins": 0, "losses": 0, "breakeven": 0, "win_rate": None, "net": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
                "profit_factor": None, "expectancy": None, "avg_win": None, "avg_loss": None, "payoff": None, "best": None, "worst": None,
                "volume": 0.0, "avg_r": None, "n_r": 0}
    nets = [t.net for t in ts]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    gp, gl = sum(wins), -sum(losses)
    avg_win = gp / len(wins) if wins else None
    avg_loss = gl / len(losses) if losses else None
    rs = [t.r_multiple for t in ts if t.r_multiple is not None]
    out.update(
        wins=len(wins), losses=len(losses), breakeven=n - len(wins) - len(losses),
        win_rate=_r(len(wins) / n), net=_r(sum(nets), 2), gross_profit=_r(gp, 2), gross_loss=_r(gl, 2),
        profit_factor=_r(gp / gl) if gl > 0 else None,
        expectancy=_r(sum(nets) / n, 4), avg_win=_r(avg_win, 2), avg_loss=_r(avg_loss, 2),
        payoff=_r(avg_win / avg_loss) if avg_win is not None and avg_loss else None,
        best=_r(max(nets), 2), worst=_r(min(nets), 2), volume=_r(sum(t.volume for t in ts), 2),
        avg_r=_r(sum(rs) / len(rs)) if rs else None, n_r=len(rs),
    )
    return out


def equity_curve(rows: list[Trade], base: Optional[float]) -> dict:
    """Duong von theo tung deal (trade + thao tac so du) sap theo thoi gian dong.

    `base` = so du truoc deal dau tien (None -> 0 va %DD khong xac dinh)."""
    ordered = sorted(rows, key=lambda t: (t.time_close, t.ticket))
    b = 0.0 if base is None else float(base)
    eq = peak = b
    max_dd = 0.0
    max_dd_pct: Optional[float] = None
    max_dd_period: Optional[tuple[datetime, datetime]] = None
    cur_peak_t: Optional[datetime] = ordered[0].time_close if ordered else None
    pts: list[dict] = []
    for t in ordered:
        if t.kind == "balance":
            eq += t.profit
            peak += t.profit
        else:
            eq += t.net
        if eq >= peak:
            peak = eq
            cur_peak_t = t.time_close
        dd = peak - eq
        dd_pct = (dd / peak * 100.0) if (base is not None and peak > 0) else None
        if dd > max_dd:
            max_dd = dd
            max_dd_period = (cur_peak_t or t.time_close, t.time_close)
        if dd_pct is not None and (max_dd_pct is None or dd_pct > max_dd_pct):
            max_dd_pct = dd_pct
        pts.append({"t": t.time_close.isoformat(), "ticket": t.ticket, "kind": t.kind, "equity": round(eq, 2), "dd": round(dd, 2),
                    "dd_pct": _r(dd_pct, 3)})
    return {"base": base, "start": round(b, 2), "end": round(eq, 2), "peak": round(peak, 2), "max_dd": round(max_dd, 2), "max_dd_pct": _r(max_dd_pct, 3),
            "max_dd_from": max_dd_period[0].isoformat() if max_dd_period else None, "max_dd_to": max_dd_period[1].isoformat() if max_dd_period else None,
            "current_dd": pts[-1]["dd"] if pts else 0.0, "points": pts}


def streaks(trades: list[Trade]) -> dict:
    """Chuoi thang/thua lien tiep theo thu tu dong lenh. Lenh hoa (net == 0) ngat chuoi."""
    best_w = best_l = cur_w = cur_l = 0
    run = worst_run_money = 0.0
    for t in trades_only(trades):
        x = t.net
        if x > 0:
            cur_w, cur_l, run = cur_w + 1, 0, 0.0
        elif x < 0:
            cur_l, cur_w = cur_l + 1, 0
            run += x
            worst_run_money = min(worst_run_money, run)
        else:
            cur_w = cur_l = 0
            run = 0.0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    cur = {"type": "win", "len": cur_w} if cur_w else ({"type": "loss", "len": cur_l} if cur_l else {"type": None, "len": 0})
    return {"max_win_streak": best_w, "max_loss_streak": best_l, "current": cur, "worst_loss_run": _r(worst_run_money, 2)}


def hold_stats(trades: list[Trade]) -> dict:
    ts = [t for t in trades if t.kind == "trade"]
    if not ts:
        return {"avg_s": None, "median_s": None, "avg_win_s": None, "avg_loss_s": None, "buckets": []}
    h = [t.hold_s for t in ts]
    w = [t.hold_s for t in ts if t.net > 0]
    lo = [t.hold_s for t in ts if t.net < 0]
    edges = [("<5m", 300), ("5-30m", 1800), ("30m-2h", 7200), ("2-8h", 28800), ("8-24h", 86400), (">1d", float("inf"))]
    cnt = {k: [0, 0.0] for k, _ in edges}
    for t in ts:
        for k, e in edges:
            if t.hold_s < e:
                cnt[k][0] += 1
                cnt[k][1] += t.net
                break
    return {"avg_s": round(sum(h) / len(h)), "median_s": round(statistics.median(h)), "avg_win_s": round(sum(w) / len(w)) if w else None,
            "avg_loss_s": round(sum(lo) / len(lo)) if lo else None, "buckets": [{"bucket": k, "n": v[0], "net": round(v[1], 2)} for k, v in cnt.items()]}


def costs(trades: list[Trade]) -> dict:
    ts = [t for t in trades if t.kind == "trade"]
    comm = sum(t.commission for t in ts)
    swap = sum(t.swap for t in ts)
    gross = sum(t.profit for t in ts)
    sp = [t.spread_cost for t in ts if t.spread_cost is not None]
    sl = [t.slippage_cost for t in ts if t.slippage_cost is not None]
    paid = -min(comm, 0.0) - min(swap, 0.0)
    return {"commission": round(comm, 2), "swap": round(swap, 2), "gross_profit_before_costs": round(gross, 2),
            "costs_pct_of_gross": _r(paid / abs(gross) * 100, 2) if gross else None,
            "spread_cost": round(sum(sp), 2) if sp else None, "slippage_cost": round(sum(sl), 2) if sl else None,
            "note": "Spread/trượt giá của paper đã nằm trong giá khớp; với MT, spread không có trong lịch sử deal (xem excursions.spread_bps)."}


def r_distribution(trades: list[Trade]) -> dict:
    ts = [t for t in trades if t.kind == "trade"]
    rs = [t.r_multiple for t in ts if t.r_multiple is not None]
    labels, counts = [], []
    edges = R_BINS
    for i in range(len(edges) + 1):
        lo = edges[i - 1] if i > 0 else None
        hi = edges[i] if i < len(edges) else None
        labels.append(f"<{hi:g}" if lo is None else (f">={lo:g}" if hi is None else f"{lo:g}..{hi:g}"))
        counts.append(sum(1 for r in rs if (lo is None or r >= lo) and (hi is None or r < hi)))
    return {"n": len(rs), "avg": _r(sum(rs) / len(rs)) if rs else None, "median": _r(statistics.median(rs)) if rs else None,
            "expectancy_r": _r(sum(rs) / len(rs)) if rs else None, "bins": [{"label": a, "n": b} for a, b in zip(labels, counts)],
            "pct_with_sl": _r(len(rs) / len(ts) * 100, 1) if ts else None}


def group_by(trades: list[Trade], key: Callable[[Trade], object], order: Optional[list] = None) -> list[dict]:
    g: dict[object, list[Trade]] = defaultdict(list)
    for t in trades:
        if t.kind == "trade":
            g[key(t)].append(t)
    rows = []
    for k, ts in g.items():
        s = summarize(ts)
        rows.append({"key": k, "n": s["n"], "net": s["net"], "win_rate": s["win_rate"], "profit_factor": s["profit_factor"],
                     "expectancy": s["expectancy"], "avg_r": s["avg_r"], "wins": s["wins"], "losses": s["losses"]})
    if order is not None:
        pos = {k: i for i, k in enumerate(order)}
        rows.sort(key=lambda r: pos.get(r["key"], 999))
    else:
        rows.sort(key=lambda r: -abs(r["net"] or 0))
    return rows


def local(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


def calendar_days(trades: list[Trade], tz: ZoneInfo) -> list[dict]:
    """Lai/lo theo NGAY DONG LENH (gio dia phuong tz) - dung cho heatmap lich."""
    d: dict[str, list[float]] = defaultdict(lambda: [0.0, 0, 0, 0])
    for t in trades:
        if t.kind != "trade":
            continue
        k = local(t.time_close, tz).date().isoformat()
        v = d[k]
        v[0] += t.net
        v[1] += 1
        v[2] += 1 if t.net > 0 else 0
        v[3] += 1 if t.net < 0 else 0
    return [{"date": k, "net": round(v[0], 2), "n": int(v[1]), "wins": int(v[2]), "losses": int(v[3])} for k, v in sorted(d.items())]


def groups(trades: list[Trade], tz: ZoneInfo) -> dict:
    """Lai/lo theo gio/ngay/phien (LUC VAO LENH, gio dia phuong tz; phien theo UTC), symbol, EA(magic), huong."""
    wd = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    return {
        "hour": group_by(trades, lambda t: local(t.time_open, tz).hour, order=list(range(24))),
        "weekday": [{**r, "label": wd[r["key"]]} for r in group_by(trades, lambda t: local(t.time_open, tz).weekday(), order=list(range(7)))],
        "session": group_by(trades, lambda t: session_of(t.time_open), order=[s[0] for s in SESSIONS]),
        "symbol": group_by(trades, lambda t: t.symbol),
        "magic": group_by(trades, lambda t: t.group or "manual"),
        "side": group_by(trades, lambda t: t.side, order=["buy", "sell"]),
    }


def contribution(trades: list[Trade]) -> list[dict]:
    """Bang dong gop theo EA (magic/chien luoc): so lenh, net, ty trong dong gop vao tong net, WR, PF, expectancy."""
    total = sum(t.net for t in trades if t.kind == "trade")
    rows = group_by(trades, lambda t: t.group or "manual")
    gross = sum(abs(r["net"] or 0.0) for r in rows)
    for r in rows:
        # share_pct = ty trong dong gop vao TONG net (None khi tong net ~ 0: ty le vo nghia); abs_share_pct = ty trong |net| trong tong |net| cac EA
        r["share_pct"] = _r(r["net"] / total * 100, 2) if gross > 0 and abs(total) >= 0.05 * gross else None
        r["abs_share_pct"] = _r(abs(r["net"] or 0.0) / gross * 100, 2) if gross > 0 else None
        r["ea"] = r.pop("key")
    return rows


def iso_week_label(d: datetime, tz: ZoneInfo) -> str:
    y, w, _ = local(d, tz).isocalendar()
    return f"{y}-W{w:02d}"


def week_range(label: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[T2 00:00 tz, T2 ke tiep) -> UTC."""
    y, w = int(label[:4]), int(label[6:8])
    mon = datetime.fromisocalendar(y, w, 1).replace(tzinfo=tz)
    return mon.astimezone(timezone.utc), (mon + timedelta(days=7)).astimezone(timezone.utc)
