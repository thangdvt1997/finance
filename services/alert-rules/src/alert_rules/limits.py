"""Giới hạn & mục tiêu do CLIENT đặt (docs/CONTROL_PLANE_DESIGN.md: giới hạn của client có hiệu lực cao nhất) — chỉ để NHẮC/hiển thị tiến độ, KHÔNG chặn/đặt lệnh.

Quy tắc duyệt (logic thuần, dễ test):
  - SIẾT chặt (giảm daily_loss/max_dd/max_orders; tăng min_margin_level; đặt giới hạn mới từ chưa có) -> hiệu lực NGAY (huỷ pending nếu có).
  - NỚI LỎNG (tăng daily_loss/max_dd/max_orders; giảm min_margin_level; XOÁ giới hạn) -> pending 24 giờ; hiệu lực hiện hành vẫn là giá trị cũ.
  - đặt lại đúng giá trị hiện tại khi đang pending -> huỷ pending.
  - monthly_target_pct là mục tiêu: mọi thay đổi hiệu lực ngay.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DELAY = timedelta(hours=24)
VN_TZ = timezone(timedelta(hours=7))
STALE_S = 900.0                    # snapshot cũ hơn 15 phút -> tiến độ 'unknown' (không bao giờ báo sai)
THRESHOLDS = (70, 90, 100)

# key -> (min, max, đơn vị, số nguyên?, chiều siết: -1 = giá trị nhỏ hơn là chặt hơn, +1 = lớn hơn là chặt hơn, 0 = mục tiêu)
SPEC: dict[str, tuple[float, float, str, bool, int]] = {
    "daily_loss_pct": (0.1, 50.0, "%", False, -1),
    "max_dd_pct": (1.0, 90.0, "%", False, -1),
    "min_margin_level": (50.0, 5000.0, "%", False, +1),
    "max_orders_day": (1, 500, "orders", True, -1),
    "monthly_target_pct": (0.1, 1000.0, "%", False, 0),
}
KEYS = tuple(SPEC)


class LimitError(ValueError):
    pass


def validate(key: str, value) -> float | None:
    """value None = xoá. Trả số đã chuẩn hoá; ném LimitError khi sai miền."""
    if key not in SPEC:
        raise LimitError("khoá giới hạn không hợp lệ")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        raise LimitError("giá trị phải là số")
    lo, hi, _, integer, _ = SPEC[key]
    if integer and float(value) != int(value):
        raise LimitError("giá trị phải là số nguyên")
    if not lo <= value <= hi:
        raise LimitError(f"giá trị phải trong khoảng {lo:g}-{hi:g}")
    return float(int(value)) if integer else round(float(value), 4)


def is_tighter(key: str, new: float, old: float) -> bool:
    d = SPEC[key][4]
    return (new < old) if d < 0 else (new > old)


@dataclass
class Decision:
    applied: str                       # now | pending | noop | cancelled
    value: float | None                # hiệu lực hiện hành sau quyết định (None = không có giới hạn)
    pending_value: float | None = None
    pending_remove: bool = False
    effective_at: datetime | None = None
    history: tuple | None = None       # (old, new, applied, effective_at) cần ghi lịch sử, hoặc None


def decide(key: str, row: dict | None, value: float | None, now: datetime) -> Decision:
    """row: {value, pending_value, pending_remove, pending_effective_at} hiện có hoặc None. value đã qua validate()."""
    cur = row["value"] if row else None
    p_val, p_rm, p_at = (row.get("pending_value"), row.get("pending_remove"), row.get("pending_effective_at")) if row else (None, False, None)
    has_pending = bool(row) and (p_at is not None)
    goal = SPEC[key][4] == 0
    if cur is None:                                     # chưa có giới hạn
        if value is None:
            return Decision("noop", None)
        return Decision("now", value, history=(None, value, "now", None))
    if value is None:                                   # xoá
        if goal:
            return Decision("now", None, history=(cur, None, "now", None))
        if has_pending and p_rm:
            return Decision("noop", cur, None, True, p_at)
        eff = now + DELAY
        return Decision("pending", cur, None, True, eff, (cur, None, "pending", eff))
    if value == cur:
        if has_pending:
            return Decision("cancelled", cur, history=(cur, cur, "cancelled", None))
        return Decision("noop", cur)
    if goal or is_tighter(key, value, cur):             # siết (hoặc mục tiêu): áp ngay, huỷ pending
        return Decision("now", value, history=(cur, value, "now", None))
    if has_pending and not p_rm and p_val == value:     # nới lỏng đã chờ đúng giá trị này: không kéo dài
        return Decision("noop", cur, p_val, False, p_at)
    eff = now + DELAY
    return Decision("pending", cur, value, False, eff, (cur, value, "pending", eff))


# ---------------------------------------------------------------- tiến độ
def day_start(now: datetime) -> datetime:
    """0h giờ VN của ngày chứa `now` (UTC aware)."""
    n = now.astimezone(VN_TZ)
    return n.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def month_start(now: datetime) -> datetime:
    n = now.astimezone(VN_TZ)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def cycle_of(key: str, now: datetime) -> str:
    n = now.astimezone(VN_TZ)
    return n.strftime("%Y-%m") if key == "monthly_target_pct" else n.strftime("%Y-%m-%d")


def level_of(ratio: float) -> str:
    return "hit" if ratio >= 1.0 else "danger" if ratio >= 0.9 else "warn" if ratio >= 0.7 else "ok"


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _unknown(unit: str, limit: float, as_of) -> dict:
    return {"current": None, "limit": limit, "ratio": None, "remaining": None, "unit": unit, "level": "unknown", "as_of": as_of}


def progress_for(key: str, limit: float, m: dict | None, now: datetime) -> dict:
    """m = số liệu từ provider (equity, margin, equity_day_start, equity_month_start, peak_equity, flows_day, flows_month, orders_today, as_of epoch).
    Thiếu/cũ -> level 'unknown' (không suy đoán)."""
    unit = SPEC[key][2]
    as_of_ts = _num((m or {}).get("as_of"))
    as_of = datetime.fromtimestamp(as_of_ts, timezone.utc).isoformat() if as_of_ts else None
    if not m or as_of_ts is None or now.timestamp() - as_of_ts > STALE_S or as_of_ts - now.timestamp() > 300:
        return _unknown(unit, limit, as_of)
    eq = _num(m.get("equity"))
    if key == "daily_loss_pct":
        s = _num(m.get("equity_day_start"))
        if eq is None or not s or s <= 0:
            return _unknown(unit, limit, as_of)
        pnl = eq - s - (_num(m.get("flows_day")) or 0.0)
        cur = max(0.0, -pnl) / s * 100.0
        ratio, remaining = cur / limit, max(0.0, limit - cur)
    elif key == "max_dd_pct":
        peak = _num(m.get("peak_equity"))
        if eq is None or not peak or peak <= 0:
            return _unknown(unit, limit, as_of)
        peak = max(peak, eq)
        cur = max(0.0, (peak - eq) / peak * 100.0)
        ratio, remaining = cur / limit, max(0.0, limit - cur)
    elif key == "min_margin_level":
        mg = _num(m.get("margin"))
        if eq is None or mg is None or mg < 0:
            return _unknown(unit, limit, as_of)
        if mg == 0:                                     # không có vị thế mở: không có margin level -> an toàn
            return {"current": None, "limit": limit, "ratio": 0.0, "remaining": None, "unit": unit, "level": "ok", "as_of": as_of}
        cur = eq / mg * 100.0
        ratio, remaining = (limit / cur if cur > 0 else 9.99), max(0.0, cur - limit)
    elif key == "max_orders_day":
        n = _num(m.get("orders_today"))
        if n is None:
            return _unknown(unit, limit, as_of)
        cur = float(int(n))
        ratio, remaining = cur / limit, max(0.0, limit - cur)
    else:                                               # monthly_target_pct
        s = _num(m.get("equity_month_start"))
        if eq is None or not s or s <= 0:
            return _unknown(unit, limit, as_of)
        pnl = eq - s - (_num(m.get("flows_month")) or 0.0)
        cur = pnl / s * 100.0
        ratio, remaining = max(0.0, cur) / limit, max(0.0, limit - cur)
        lvl = "hit" if ratio >= 1.0 else "ok"           # mục tiêu: đạt = tin vui, không phải cảnh báo đỏ
        return {"current": round(cur, 4), "limit": limit, "ratio": round(ratio, 4), "remaining": round(remaining, 4), "unit": unit, "level": lvl, "as_of": as_of}
    return {"current": round(cur, 4), "limit": limit, "ratio": round(min(ratio, 99.0), 4), "remaining": round(remaining, 4),
            "unit": unit, "level": level_of(ratio), "as_of": as_of}


LABELS = {"daily_loss_pct": "lỗ trong ngày", "max_dd_pct": "mức sụt giảm từ đỉnh", "min_margin_level": "mức ký quỹ tối thiểu",
          "max_orders_day": "số lệnh mở trong ngày", "monthly_target_pct": "mục tiêu lợi nhuận tháng"}


def crossed(prog: dict) -> int:
    """Ngưỡng cao nhất (70/90/100) mà tiến độ đã vượt; 0 nếu chưa/unknown."""
    r = prog.get("ratio")
    if prog.get("level") == "unknown" or r is None:
        return 0
    return max([t for t in THRESHOLDS if r >= t / 100.0] or [0])
