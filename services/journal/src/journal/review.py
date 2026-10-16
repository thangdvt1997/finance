"""Review hang tuan (HAM THUAN): tong ket tuan, so voi tuan truoc, ky luat, lenh tot/xau nhat, nhan xet tu dong (quy tac don gian)."""
from __future__ import annotations

from typing import Optional
from zoneinfo import ZoneInfo

from . import discipline, stats
from .models import Trade


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None else round(a - b, 4)


def _brief(t: Trade) -> dict:
    return {"ticket": t.ticket, "symbol": t.symbol, "side": t.side, "volume": t.volume, "net": round(t.net, 2), "r": None if t.r_multiple is None else round(t.r_multiple, 2),
            "time_close": t.time_close.isoformat(), "group": t.group}


def insights(cur: dict, prev: dict, disc: dict, st: dict, days: list[dict]) -> list[str]:
    out: list[str] = []
    n = cur["n"]
    if n == 0:
        return ["Không có lệnh nào đóng trong tuần này."]
    wr, pf = cur["win_rate"], cur["profit_factor"]
    if cur["net"] < 0 and wr is not None and wr >= 0.5 and cur["payoff"] is not None and cur["payoff"] < 1:
        out.append(f"Tỷ lệ thắng {wr*100:.0f}% nhưng vẫn lỗ: lãi trung bình chỉ bằng {cur['payoff']:.2f}× lỗ trung bình — cắt lỗ chậm/chốt lãi sớm.")
    if cur["net"] > 0 and wr is not None and wr < 0.4:
        out.append(f"Lãi dù chỉ thắng {wr*100:.0f}% số lệnh: lợi nhuận phụ thuộc vài lệnh lớn — kiểm tra có giữ được kỷ luật cắt lỗ.")
    if st["max_loss_streak"] >= 3:
        out.append(f"Chuỗi thua dài nhất {st['max_loss_streak']} lệnh (tổng {abs(st['worst_loss_run'] or 0):.2f}) — xem lại quyết định sau lệnh thua thứ 2.")
    if disc["score"] is not None and disc["score"] < 80:
        worst = max(disc["rules"], key=lambda r: r["count"])
        if worst["count"]:
            out.append(f"Điểm kỷ luật {disc['score']:.0f}/100; vi phạm nhiều nhất: «{worst['label']}» ({worst['count']} lệnh, P/L {worst['net']:+.2f}).")
    if disc["n_flagged"] and disc["net_flagged"] < 0 <= disc["net_clean"]:
        out.append(f"Các lệnh vi phạm kỷ luật lỗ {disc['net_flagged']:.2f} trong khi lệnh sạch lãi {disc['net_clean']:.2f} — loại bỏ vi phạm là cải thiện lớn nhất.")
    if prev["n"] and n > prev["n"] * 1.5 and n >= 10:
        out.append(f"Số lệnh tăng mạnh ({prev['n']} → {n}); kiểm tra overtrading.")
    if days:
        w = min(days, key=lambda d: d["net"])
        if w["net"] < 0:
            out.append(f"Ngày lỗ nhất: {w['date']} ({w['net']:+.2f}, {w['n']} lệnh).")
    if pf is not None and pf < 1 and cur["net"] < 0:
        out.append(f"Profit factor {pf:.2f} < 1 trong tuần.")
    return out[:6]


def weekly(week: str, tz: ZoneInfo, cur_trades: list[Trade], prev_trades: list[Trade], *, events: Optional[list[dict]] = None,
           rw_cfg: Optional[dict] = None, params: Optional[dict] = None, base_equity: Optional[float] = None,
           notes: Optional[list[dict]] = None) -> dict:
    cs, ps = stats.summarize(cur_trades), stats.summarize(prev_trades)
    disc = discipline.check(cur_trades, tz, events=events, rw_cfg=rw_cfg, params=params, base_equity=base_equity)
    st = stats.streaks(cur_trades)
    days = stats.calendar_days(cur_trades, tz)
    ts = stats.trades_only(cur_trades)
    ranked = sorted(ts, key=lambda t: t.net)
    sym = stats.group_by(cur_trades, lambda t: t.symbol)
    tag_use: dict[str, int] = {}
    for n in notes or []:
        if n["kind"] == "deal":
            for t in n["tags"]:
                tag_use[t] = tag_use.get(t, 0) + 1
    review_note = next((n for n in (notes or []) if n["kind"] == "week" and n["ref"] == week), None)
    return {
        "week": week, "summary": cs, "prev_summary": ps,
        "delta": {"net": _delta(cs["net"], ps["net"]), "win_rate": _delta(cs["win_rate"], ps["win_rate"]), "profit_factor": _delta(cs["profit_factor"], ps["profit_factor"]),
                  "expectancy": _delta(cs["expectancy"], ps["expectancy"]), "n": cs["n"] - ps["n"]},
        "streaks": st, "days": days, "best": [_brief(t) for t in ranked[::-1][:3] if t.net > 0], "worst": [_brief(t) for t in ranked[:3] if t.net < 0],
        "by_symbol": sym[:6], "contribution": stats.contribution(cur_trades),
        "discipline": {k: disc[k] for k in ("score", "n_flagged", "net_flagged", "net_clean", "rules", "day_breaches")},
        "flagged": disc["flagged"][:20], "tags": [{"tag": k, "n": v} for k, v in sorted(tag_use.items(), key=lambda kv: -kv[1])],
        "review": review_note, "insights": insights(cs, ps, disc, st, days),
    }
