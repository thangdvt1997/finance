"""Kiem tra KY LUAT tren chuoi lenh (HAM THUAN). Moi quy tac gan co (flag) len tung lenh, khong tu dong chan/can thiep.

Quy tac (id -> y nghia):
- news_window     : vao lenh trong cua so rui ro tin HIGH impact cua symbol (tscommon.risk_windows: truoc/sau tin).
- reentry_after_loss : vao lenh moi trong `revenge_gap_min` phut sau khi mot lenh THUA vua dong (dau hieu "go gac").
- size_up_after_loss : nhu tren va khoi luong >= `size_up_ratio` x khoi luong lenh thua truoc (tang volume sau thua).
- averaging_down  : nhoi lenh cung huong/cung symbol khi lenh cu con mo va gia vao xau hon gia vao lenh cu (binh quan gia xuong).
- overtrading_day : lenh thu > `max_trades_day` mo trong cung ngay (gio dia phuong).
- overtrading_hour: lenh thu > `max_trades_hour` mo trong cung 60 phut (cua so truot).
- no_sl           : khong dat SL luc vao lenh (chi khi require_sl).
Diem ky luat = 100 * (1 - so lenh bi gan co / tong lenh). Phat hien SAU KHI da xay ra: dung de tu soi lai, khong phai canh bao thoi gian thuc.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from tscommon import risk_windows as rw

from .models import Trade

DEFAULTS = {"revenge_gap_min": 30, "size_up_ratio": 1.5, "max_trades_day": 10, "max_trades_hour": 5, "require_sl": True,
            "daily_loss_limit_pct": 3.0}
RULES = {
    "news_window": "Vào lệnh trong cửa sổ rủi ro tin (high impact)",
    "reentry_after_loss": "Vào lại ngay sau lệnh thua",
    "size_up_after_loss": "Tăng khối lượng sau lệnh thua",
    "averaging_down": "Nhồi lệnh bình quân giá xấu",
    "overtrading_day": "Quá nhiều lệnh trong ngày",
    "overtrading_hour": "Quá nhiều lệnh trong 1 giờ",
    "no_sl": "Vào lệnh không đặt SL",
}


def _news_flags(trades: list[Trade], events: list[dict], cfg: Optional[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not events or cfg is None:
        return out
    by_sym: dict[str, list[rw.Window]] = {}
    for t in trades:
        if not t.symbol:
            continue
        wins = by_sym.get(t.symbol)
        if wins is None:
            wins = by_sym[t.symbol] = rw.windows_for_symbol(events, t.symbol, cfg)
        for w in wins:
            if w.start <= t.time_open <= w.end:
                out[t.ticket] = {"event": w.title, "country": w.country, "event_ts": w.ts.isoformat(),
                                 "min_from_event": round((t.time_open - w.ts).total_seconds() / 60)}
                break
    return out


def check(trades: list[Trade], tz: ZoneInfo, *, events: Optional[list[dict]] = None, rw_cfg: Optional[dict] = None,
          params: Optional[dict] = None, base_equity: Optional[float] = None) -> dict:
    p = {**DEFAULTS, **(params or {})}
    ts = sorted((t for t in trades if t.kind == "trade"), key=lambda t: (t.time_open, t.ticket))
    flags: dict[str, list[dict]] = defaultdict(list)  # ticket -> [{rule, detail}]

    def add(t: Trade, rule: str, **detail):
        flags[t.ticket].append({"rule": rule, **detail})

    # --- tin ---
    for tk, d in _news_flags(ts, events or [], rw_cfg).items():
        t = next(x for x in ts if x.ticket == tk)
        add(t, "news_window", **d)

    # --- sau lenh thua ---
    gap = timedelta(minutes=float(p["revenge_gap_min"]))
    closed_losses = sorted((t for t in ts if t.net < 0), key=lambda t: t.time_close)
    for t in ts:
        prev = None
        for lo in closed_losses:
            if lo.ticket == t.ticket:
                continue
            if lo.time_close <= t.time_open and t.time_open - lo.time_close <= gap:
                prev = lo  # lenh thua dong gan nhat truoc luc vao (list sap tang theo time_close)
        if prev is not None:
            add(t, "reentry_after_loss", after=prev.ticket, gap_min=round((t.time_open - prev.time_close).total_seconds() / 60, 1))
            if prev.volume > 0 and t.volume >= p["size_up_ratio"] * prev.volume:
                add(t, "size_up_after_loss", after=prev.ticket, ratio=round(t.volume / prev.volume, 2))

    # --- nhoi lenh bu lo ---
    for i, t in enumerate(ts):
        for e in ts[:i]:
            if e.symbol != t.symbol or e.side != t.side:
                continue
            if e.time_open < t.time_open < e.time_close:  # lenh cu con mo
                worse = t.price_open < e.price_open if t.side == "buy" else t.price_open > e.price_open
                if worse:
                    add(t, "averaging_down", against=e.ticket)
                    break

    # --- overtrading ---
    per_day: dict[str, list[Trade]] = defaultdict(list)
    for t in ts:
        per_day[t.time_open.astimezone(tz).date().isoformat()].append(t)
    for d, lst in per_day.items():
        for t in lst[int(p["max_trades_day"]):]:
            add(t, "overtrading_day", day=d, n_day=len(lst))
    hour_win = timedelta(minutes=60)
    for i, t in enumerate(ts):
        n = sum(1 for u in ts[: i + 1] if t.time_open - u.time_open < hour_win)
        if n > int(p["max_trades_hour"]):
            add(t, "overtrading_hour", n_hour=n)

    # --- khong SL ---
    if p["require_sl"]:
        for t in ts:
            if t.sl <= 0:
                add(t, "no_sl")

    # --- tong hop ---
    by_ticket = {t.ticket: t for t in ts}
    per_rule = {r: {"rule": r, "label": RULES[r], "count": 0, "net": 0.0} for r in RULES}
    for tk, fl in flags.items():
        for f in fl:
            pr = per_rule[f["rule"]]
            pr["count"] += 1
            pr["net"] = round(pr["net"] + by_ticket[tk].net, 2)
    flagged = [{"ticket": tk, "symbol": by_ticket[tk].symbol, "side": by_ticket[tk].side, "time_open": by_ticket[tk].time_open.isoformat(),
                "net": round(by_ticket[tk].net, 2), "flags": fl} for tk, fl in sorted(flags.items(), key=lambda kv: by_ticket[kv[0]].time_open)]
    n = len(ts)
    nf = len(flags)
    net_flagged = round(sum(by_ticket[tk].net for tk in flags), 2)
    net_clean = round(sum(t.net for t in ts) - net_flagged, 2)

    # --- lo trong ngay vuot han muc ---
    day_breaches = []
    if base_equity and base_equity > 0 and p.get("daily_loss_limit_pct"):
        by_close: dict[str, float] = defaultdict(float)
        for t in ts:
            by_close[t.time_close.astimezone(tz).date().isoformat()] += t.net
        lim = -base_equity * float(p["daily_loss_limit_pct"]) / 100.0
        day_breaches = [{"date": d, "net": round(v, 2), "limit": round(lim, 2)} for d, v in sorted(by_close.items()) if v < lim]

    return {"params": p, "n_trades": n, "n_flagged": nf, "score": round(100.0 * (1 - nf / n), 1) if n else None,
            "net_flagged": net_flagged, "net_clean": net_clean, "rules": [r for r in per_rule.values()],
            "flagged": flagged, "day_breaches": day_breaches, "tickets": {tk: [f["rule"] for f in fl] for tk, fl in flags.items()}}
