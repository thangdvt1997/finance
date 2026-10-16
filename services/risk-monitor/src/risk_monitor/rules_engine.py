"""Engine mẫu luật rủi ro cho đội tài khoản (docs/FLEET_MGMT.md mục 4). HÀM THUẦN, READ-ONLY, không I/O, không ném lỗi.

Đầu vào: kind + params, chuỗi equity [(ts, equity)] (bước 5 phút, nhiều ngày), snapshot mới nhất, thời điểm đóng deal, now.
Đầu ra: {status green|yellow|red|na, usage_pct, value, limit, headroom, unit, detail, reset_at}.
Giả định (ghi trong `detail`): mọi mức lỗ/lãi đo bằng EQUITY (gồm lệnh đang mở, gồm nạp/rút nếu có); đỉnh equity lấy từ chuỗi 5 phút
(đỉnh nhọn trong 5 phút có thể bị bỏ sót); luật nhà cái/prop firm khác nhau — cấu hình theo hợp đồng thực tế."""
from __future__ import annotations

import bisect
import math
import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

KINDS = ("daily_loss", "max_drawdown", "margin_level", "best_day", "max_trades_day")
DEFAULT_WARN = 70.0
USAGE_CAP = 999.0

# Dự phòng khi image không có dữ liệu tz IANA: chỉ các múi KHÔNG có giờ mùa hè (offset cố định, giờ).
_FIXED = {"UTC": 0, "ETC/UTC": 0, "GMT": 0, "ETC/GMT": 0, "ASIA/HO_CHI_MINH": 7, "ASIA/SAIGON": 7, "ASIA/BANGKOK": 7, "ASIA/JAKARTA": 7,
          "ASIA/SINGAPORE": 8, "ASIA/SHANGHAI": 8, "ASIA/HONG_KONG": 8, "ASIA/TAIPEI": 8, "ASIA/MANILA": 8, "ASIA/TOKYO": 9,
          "ASIA/SEOUL": 9, "ASIA/DUBAI": 4, "ASIA/KOLKATA": 5.5, "EUROPE/MOSCOW": 3, "EUROPE/ISTANBUL": 3}
_OFFSET_RE = re.compile(r"^(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.I)


def resolve_tz(name: Any) -> tuple[tzinfo, str | None]:
    """(tzinfo, ghi chú nếu phải dự phòng). Hỗ trợ IANA (zoneinfo), 'UTC', 'UTC+3', 'UTC-05:30'. Không bao giờ ném lỗi."""
    raw = str(name).strip() if name not in (None, "") else "UTC"
    m = _OFFSET_RE.match(raw)
    if m:
        h, mi = int(m.group(2)), int(m.group(3) or 0)
        if h <= 14 and mi < 60:
            sign = -1 if m.group(1) == "-" else 1
            return timezone(sign * timedelta(hours=h, minutes=mi), raw.upper().replace(" ", "")), None
    if raw.upper() in ("UTC", "Z", "GMT"):
        return timezone.utc, None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(raw), None
    except Exception:  # noqa: BLE001  (thiếu tzdata / tên sai)
        off = _FIXED.get(raw.upper())
        if off is not None:
            return timezone(timedelta(hours=off), raw), f"múi giờ {raw} dùng offset cố định (thiếu dữ liệu tz)"
        return timezone.utc, f"múi giờ '{raw}' không nhận diện được, dùng UTC"


def day_bounds(now: datetime, tz: tzinfo, reset_hour: int) -> tuple[datetime, datetime]:
    """(mốc reset gần nhất <= now, mốc reset kế tiếp) — cả hai UTC. Ngày giao dịch bắt đầu lúc reset_hour theo tz."""
    loc = now.astimezone(tz)
    start = loc.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    if start > loc:
        start -= timedelta(days=1)
    nxt = start + timedelta(days=1)
    return start.astimezone(timezone.utc), nxt.astimezone(timezone.utc)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _clean(series: Any) -> list[tuple[datetime, float]]:
    out = []
    for p in series or []:
        try:
            t, e = p
            e = _num(e)
            if e is None or not isinstance(t, datetime):
                continue
            out.append((_utc(t), e))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def _band(usage: float, warn: float) -> str:
    return "red" if usage >= 100.0 else "yellow" if usage >= warn else "green"


def _res(status: str, usage: float | None, value, limit, headroom, unit: str, detail: str, reset_at: datetime | None) -> dict:
    return {"status": status, "usage_pct": None if usage is None else round(min(max(usage, 0.0), USAGE_CAP), 2),
            "value": None if value is None else round(float(value), 4), "limit": None if limit is None else round(float(limit), 4),
            "headroom": None if headroom is None else round(float(headroom), 4), "unit": unit, "detail": detail,
            "reset_at": reset_at.isoformat() if reset_at else None}


def _na(reason: str, reset_at: datetime | None = None, unit: str = "") -> dict:
    return _res("na", None, None, None, None, unit, reason, reset_at)


def _usage_max(value: float, limit: float) -> float:
    return value / limit * 100.0 if limit > 0 else USAGE_CAP


def evaluate(kind: str, params: dict | None, *, series, snapshot: dict | None, deal_times=None, now: datetime) -> dict:
    """Đánh giá 1 luật cho 1 tài khoản. Không bao giờ ném lỗi: lỗi nội bộ -> 'na'."""
    try:
        p = params if isinstance(params, dict) else {}
        fn = _KIND.get(kind)
        if fn is None:
            return _na(f"loại luật không hỗ trợ: {kind}")
        now = _utc(now)
        tz, tz_note = resolve_tz(p.get("tz"))
        rh = _num(p.get("reset_hour"))
        reset_hour = int(rh) if rh is not None and 0 <= rh <= 23 else 0
        warn = _num(p.get("warn_usage_pct"))
        warn = warn if warn is not None and 0 < warn < 100 else DEFAULT_WARN
        start, nxt = day_bounds(now, tz, reset_hour)
        ctx = {"p": p, "warn": warn, "start": start, "reset_at": nxt, "tz": tz, "reset_hour": reset_hour, "now": now,
               "series": _clean(series), "snap": snapshot or {}, "deals": deal_times}
        res = fn(ctx)
        if tz_note:
            res["detail"] += f" [{tz_note}]"
        return res
    except Exception as e:  # noqa: BLE001
        return _na(f"lỗi đánh giá luật ({type(e).__name__})")


def _current_equity(ctx: dict) -> float | None:
    e = _num(ctx["snap"].get("equity"))
    if e is not None:
        return e
    return ctx["series"][-1][1] if ctx["series"] else None


def _equity_at(series: list, t: datetime) -> tuple[float, datetime] | None:
    """Equity tại/ngay trước t; nếu chưa có điểm nào trước t thì điểm đầu tiên sau t."""
    ts = [x[0] for x in series]
    i = bisect.bisect_right(ts, t)
    if i > 0:
        return series[i - 1][1], series[i - 1][0]
    return (series[0][1], series[0][0]) if series else None


def _day_key(t: datetime, tz: tzinfo, rh: int):
    return (t.astimezone(tz) - timedelta(hours=rh)).date()


def _eod(ctx: dict, include_now: bool) -> list[tuple[Any, float]]:
    """[(ngày, equity cuối ngày)] theo mốc reset; ngày hiện tại lấy equity hiện tại nếu include_now."""
    last: dict = {}
    for t, e in ctx["series"]:
        last[_day_key(t, ctx["tz"], ctx["reset_hour"])] = e
    cur = _current_equity(ctx)
    if include_now and cur is not None:
        last[_day_key(ctx["now"], ctx["tz"], ctx["reset_hour"])] = cur
    return sorted(last.items())


# ---- daily_loss ----
def _daily_loss(c: dict) -> dict:
    p, ra = c["p"], c["reset_at"]
    lim_pct = _num(p.get("limit_pct"))
    if not lim_pct or lim_pct <= 0:
        return _na("thiếu limit_pct", ra, "ccy")
    cur = _current_equity(c)
    ref = _equity_at(c["series"], c["start"]) if c["series"] else None
    if cur is None or ref is None:
        return _na("chưa có dữ liệu equity", ra, "ccy")
    start_eq, ref_ts = ref
    basis = p.get("basis") if p.get("basis") in ("day_start_equity", "initial_balance") else "day_start_equity"
    ib = _num(p.get("initial_balance"))
    note = ""
    if basis == "initial_balance" and not (ib and ib > 0):
        basis, note = "day_start_equity", " (thiếu initial_balance: dùng equity đầu ngày)"
    base = ib if basis == "initial_balance" else start_eq
    if base <= 0:
        return _na("equity cơ sở không hợp lệ", ra, "ccy")
    limit = base * lim_pct / 100.0
    loss = max(0.0, start_eq - cur)
    usage = _usage_max(loss, limit)
    if ref_ts > c["start"] + timedelta(hours=1):
        note += " (chưa có điểm equity trước mốc reset: dùng điểm đầu tiên trong ngày)"
    detail = (f"Lỗ ngày theo EQUITY (gồm lệnh đang mở): {loss:.2f} / hạn mức {limit:.2f} ({lim_pct:g}% của "
              f"{'số dư ban đầu' if basis == 'initial_balance' else 'equity đầu ngày'} {base:.2f}); equity đầu ngày {start_eq:.2f}, hiện tại {cur:.2f}{note}")
    return _res(_band(usage, c["warn"]), usage, loss, limit, limit - loss, "ccy", detail, ra)


# ---- max_drawdown ----
def _max_dd(c: dict) -> dict:
    p, ra = c["p"], c["reset_at"]
    lim_pct = _num(p.get("limit_pct"))
    if not lim_pct or lim_pct <= 0:
        return _na("thiếu limit_pct", ra, "ccy")
    mode = p.get("mode") if p.get("mode") in ("static", "trailing_eod", "trailing_intraday") else "static"
    cur = _current_equity(c)
    ib = _num(p.get("initial_balance"))
    ib = ib if ib and ib > 0 else None
    if cur is None:
        return _na("chưa có dữ liệu equity", ra, "ccy")
    note = ""
    if mode == "static":
        if ib is None:
            return _na("static cần initial_balance", ra, "ccy")
        peak, what = ib, "số dư ban đầu"
    elif mode == "trailing_eod":
        today = _day_key(c["now"], c["tz"], c["reset_hour"])
        past = [e for d, e in _eod(c, include_now=False) if d < today]
        cands = ([ib] if ib else []) + past
        if not cands:
            cands = [c["series"][0][1]] if c["series"] else [cur]
            note = " (chưa có ngày hoàn tất: dùng equity đầu chuỗi làm đỉnh)"
        peak, what = max(cands), "đỉnh equity cuối ngày"
    else:
        cands = ([ib] if ib else []) + [e for _, e in c["series"]] + [cur]
        peak, what = max(cands), "đỉnh equity (trong cửa sổ dữ liệu, bước 5 phút)"
    if peak <= 0:
        return _na("đỉnh equity không hợp lệ", ra, "ccy")
    limit = peak * lim_pct / 100.0
    dd = max(0.0, peak - cur)
    usage = _usage_max(dd, limit)
    detail = (f"Sụt giảm [{mode}] so với {what} {peak:.2f}: {dd:.2f} / hạn mức {limit:.2f} ({lim_pct:g}%); sàn {peak - limit:.2f}, "
              f"equity hiện tại {cur:.2f}{note}")
    return _res(_band(usage, c["warn"]), usage, dd, limit, limit - dd, "ccy", detail, ra)


# ---- margin_level ----
def _margin(c: dict) -> dict:
    p, ra = c["p"], c["reset_at"]
    mn = _num(p.get("min_level_pct"))
    if not mn or mn <= 0:
        return _na("thiếu min_level_pct", ra, "%")
    s = c["snap"]
    eq, mg = _num(s.get("equity")), _num(s.get("margin"))
    lvl = _num(s.get("margin_level"))
    if lvl is None and eq is not None and mg is not None and mg > 0:
        lvl = eq / mg * 100.0
    if mg is not None and mg <= 0:
        return _res("green", 0.0, None, mn, None, "%", "Không có margin đang dùng (không có vị thế mở).", ra)
    if lvl is None:
        return _na("chưa có dữ liệu margin", ra, "%")
    usage = mn / lvl * 100.0 if lvl > 0 else USAGE_CAP
    detail = f"Mức margin hiện tại {lvl:.1f}% so với mức tối thiểu {mn:g}% (usage = tối thiểu / hiện tại)"
    return _res(_band(usage, c["warn"]), usage, lvl, mn, lvl - mn, "%", detail, ra)


# ---- best_day ----
def _best_day(c: dict) -> dict:
    p, ra = c["p"], c["reset_at"]
    mx = _num(p.get("max_share_pct"))
    if not mx or mx <= 0:
        return _na("thiếu max_share_pct", ra, "%")
    cur = _current_equity(c)
    if cur is None or not c["series"]:
        return _na("chưa có dữ liệu equity", ra, "%")
    days = _eod(c, include_now=True)
    prev, pnl = c["series"][0][1], []
    for d, e in days:
        pnl.append((d, e - prev))
        prev = e
    total = sum(x for _, x in pnl)
    best_d, best = max(pnl, key=lambda x: x[1])
    mtp = _num(p.get("min_total_profit")) or 0.0
    asm = " Xấp xỉ bằng chênh equity theo ngày (gồm nạp/rút nếu có)."
    if total <= 0 or total < mtp or best <= 0:
        why = "tổng lãi chưa dương" if total <= 0 else "tổng lãi chưa đạt mức tối thiểu" if total < mtp else "chưa có ngày lãi"
        return _res("green", 0.0, 0.0, mx, mx, "%", f"Chưa áp dụng: {why} (tổng {total:.2f}, ngày tốt nhất {best:.2f}).{asm}", ra)
    share = best / total * 100.0
    usage = _usage_max(share, mx)
    detail = f"Ngày tốt nhất {best_d} lãi {best:.2f} = {share:.1f}% tổng lãi {total:.2f} / ngưỡng {mx:g}%.{asm}"
    return _res(_band(usage, c["warn"]), usage, share, mx, mx - share, "%", detail, ra)


# ---- max_trades_day ----
def _max_trades(c: dict) -> dict:
    p, ra = c["p"], c["reset_at"]
    lim = _num(p.get("limit"))
    if not lim or lim <= 0:
        return _na("thiếu limit", ra, "deal")
    if c["deals"] is None:
        return _na("chưa có dữ liệu deal", ra, "deal")
    n = sum(1 for t in c["deals"] if isinstance(t, datetime) and c["start"] <= _utc(t) <= c["now"])
    usage = _usage_max(float(n), lim)
    return _res(_band(usage, c["warn"]), usage, n, lim, lim - n, "deal", f"Số deal đóng trong ngày (từ mốc reset): {n} / {lim:g}", ra)


_KIND = {"daily_loss": _daily_loss, "max_drawdown": _max_dd, "margin_level": _margin, "best_day": _best_day, "max_trades_day": _max_trades}
