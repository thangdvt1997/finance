"""Kiểm tra tham số mẫu luật + mẫu gợi ý TRUNG TÍNH (không gắn tên prop firm). docs/FLEET_MGMT.md mục 4.
Engine tính điểm nằm ở services/risk-monitor (rules_engine.py); auth chỉ lưu/kiểm hợp lệ."""
from __future__ import annotations

import re

KINDS = ("daily_loss", "max_drawdown", "margin_level", "best_day", "max_trades_day")
TZ_RE = re.compile(r"^(UTC([+-]\d{1,2}(:\d{2})?)?|[A-Za-z]+(/[A-Za-z_+\-0-9]+){1,2})$")
KIND_LABEL = {"daily_loss": "Lỗ trong ngày", "max_drawdown": "Drawdown tối đa", "margin_level": "Margin level tối thiểu",
              "best_day": "Ngày lãi tốt nhất / nhất quán", "max_trades_day": "Số lệnh/ngày"}


def _num(params: dict, key: str, lo: float, hi: float, default=None, required=False) -> float | None:
    v = params.get(key, default)
    if v is None or v == "":
        if required:
            raise ValueError(f"thiếu tham số {key}")
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{key} phải là số") from None
    if not (lo <= f <= hi) or f != f:
        raise ValueError(f"{key} phải trong khoảng [{lo:g}, {hi:g}]")
    return f


def validate_params(kind: str, params: dict) -> dict:
    """Trả params đã chuẩn hoá (chỉ khoá hợp lệ). ValueError(thông điệp tiếng Việt) nếu sai."""
    if kind not in KINDS:
        raise ValueError("loại luật không hợp lệ")
    if not isinstance(params, dict):
        raise ValueError("params phải là đối tượng")
    out: dict = {"warn_usage_pct": _num(params, "warn_usage_pct", 10, 99, 70)}
    tz = str(params.get("tz") or "UTC").strip()
    if not TZ_RE.match(tz) or len(tz) > 40:
        raise ValueError("tz không hợp lệ (vd UTC, UTC+3, Europe/Prague, America/New_York)")
    out["tz"] = tz
    h = params.get("reset_hour", 0)
    try:
        h = int(h)
    except (TypeError, ValueError):
        raise ValueError("reset_hour phải là số nguyên 0-23") from None
    if not 0 <= h <= 23:
        raise ValueError("reset_hour phải là số nguyên 0-23")
    out["reset_hour"] = h
    if kind == "daily_loss":
        out["limit_pct"] = _num(params, "limit_pct", 0.1, 100, required=True)
        basis = str(params.get("basis") or "day_start_equity")
        if basis not in ("day_start_equity", "initial_balance"):
            raise ValueError("basis phải là day_start_equity hoặc initial_balance")
        out["basis"] = basis
        out["initial_balance"] = _num(params, "initial_balance", 1, 1e12)
    elif kind == "max_drawdown":
        out["limit_pct"] = _num(params, "limit_pct", 0.1, 100, required=True)
        mode = str(params.get("mode") or "static")
        if mode not in ("static", "trailing_eod", "trailing_intraday"):
            raise ValueError("mode phải là static, trailing_eod hoặc trailing_intraday")
        out["mode"] = mode
        out["initial_balance"] = _num(params, "initial_balance", 1, 1e12)
    elif kind == "margin_level":
        out["min_level_pct"] = _num(params, "min_level_pct", 10, 100000, required=True)
    elif kind == "best_day":
        out["max_share_pct"] = _num(params, "max_share_pct", 5, 100, required=True)
        out["min_total_profit"] = _num(params, "min_total_profit", 0, 1e12, 0)
    elif kind == "max_trades_day":
        out["limit"] = int(_num(params, "limit", 1, 10000, required=True))
    return {k: v for k, v in out.items() if v is not None}


PRESETS = [
    {"name": "Lỗ ngày 5% (equity, reset 00:00 UTC)", "kind": "daily_loss", "params": {"limit_pct": 5, "basis": "day_start_equity", "tz": "UTC", "reset_hour": 0}},
    {"name": "Lỗ ngày 4% (equity, reset 17:00 New York)", "kind": "daily_loss", "params": {"limit_pct": 4, "basis": "day_start_equity", "tz": "America/New_York", "reset_hour": 17}},
    {"name": "Lỗ ngày 5% so với vốn ban đầu", "kind": "daily_loss", "params": {"limit_pct": 5, "basis": "initial_balance", "tz": "UTC", "reset_hour": 0}},
    {"name": "Drawdown tối đa 10% (tĩnh)", "kind": "max_drawdown", "params": {"limit_pct": 10, "mode": "static"}},
    {"name": "Drawdown 6% (trailing cuối ngày)", "kind": "max_drawdown", "params": {"limit_pct": 6, "mode": "trailing_eod", "tz": "UTC", "reset_hour": 0}},
    {"name": "Drawdown 8% (trailing theo đỉnh equity)", "kind": "max_drawdown", "params": {"limit_pct": 8, "mode": "trailing_intraday"}},
    {"name": "Margin level tối thiểu 150%", "kind": "margin_level", "params": {"min_level_pct": 150}},
    {"name": "Ngày tốt nhất ≤ 40% tổng lãi", "kind": "best_day", "params": {"max_share_pct": 40, "min_total_profit": 0}},
    {"name": "Tối đa 50 lệnh đóng mỗi ngày", "kind": "max_trades_day", "params": {"limit": 50}},
]
DISCLAIMER = ("Luật của nhà cái/prop firm KHÁC NHAU và thay đổi theo thời gian (static/trailing, mốc reset ngày, cách tính consistency). "
              "Đây là công cụ THEO DÕI cấu hình được — hãy đặt tham số theo hợp đồng thực tế của từng khách.")
