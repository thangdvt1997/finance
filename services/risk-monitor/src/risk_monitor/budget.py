"""Ngân sách rủi ro (R6): mức tiêu thụ = giá trị / hạn mức. warn >= warn_ratio (mặc định 80%), crit >= 100%.
Hạn mức tối thiểu (limit_min, ví dụ mức margin): tiêu thụ = hạn mức / giá trị."""
from __future__ import annotations

LABELS = {
    "day_loss_pct": ("Lỗ trong ngày", "%"),
    "week_loss_pct": ("Lỗ trong tuần", "%"),
    "dd_pct": ("Drawdown từ đỉnh", "%"),
    "leverage_gross": ("Đòn bẩy hiệu dụng (gross)", "x"),
    "margin_level_min": ("Mức margin tối thiểu", "%"),
    "es_1d_pct": ("ES 97,5% 1 ngày / equity", "%"),
    "ccy_conc_pct": ("Tập trung 1 tiền tệ / equity", "%"),
    "positions": ("Số vị thế mở", ""),
}
LEVEL = {"ok": 0, "warn": 1, "crit": 2}


def limits_for(cfg: dict, kind: str, account_id: str) -> dict:
    b = cfg.get("budget", {})
    lim = dict(b.get(kind, {}))
    lim.update((b.get("accounts") or {}).get(account_id, {}))
    return lim


def _item(key: str, value: float | None, limit: float, warn_ratio: float, invert: bool = False) -> dict:
    label, unit = LABELS[key]
    if value is None:
        used = None
        status = "na"
    elif invert:
        used = float("inf") if value <= 0 else limit / value
    else:
        used = value / limit if limit else None
    if used is not None:
        status = "crit" if used >= 1.0 else "warn" if used >= warn_ratio else "ok"
        if used == float("inf"):
            used = 99.0
    return {"key": key, "label": label, "unit": unit, "value": value, "limit": limit, "used_pct": (used * 100.0 if used is not None else None),
            "status": status, "direction": "min" if invert else "max"}


def evaluate(cfg: dict, kind: str, account_id: str, *, day_pnl_pct: float | None, week_pnl_pct: float | None,
             dd_from_peak_pct: float | None, leverage_gross: float | None, margin_level: float | None,
             es_1d_pct: float | None, ccy_conc_pct: float | None, positions: int) -> list[dict]:
    lim = limits_for(cfg, kind, account_id)
    wr = float(cfg.get("budget", {}).get("warn_ratio", 0.8))
    loss = lambda p: None if p is None else max(0.0, -p)  # noqa: E731
    vals = {
        "day_loss_pct": loss(day_pnl_pct), "week_loss_pct": loss(week_pnl_pct),
        "dd_pct": None if dd_from_peak_pct is None else max(0.0, -dd_from_peak_pct),
        "leverage_gross": leverage_gross, "es_1d_pct": es_1d_pct, "ccy_conc_pct": ccy_conc_pct, "positions": float(positions),
    }
    items = [_item(k, vals[k], float(lim[k]), wr) for k in vals if k in lim]
    if "margin_level_min" in lim and margin_level is not None:
        items.append(_item("margin_level_min", margin_level, float(lim["margin_level_min"]), wr, invert=True))
    return items


def worst_status(items: list[dict]) -> str:
    return max((i["status"] for i in items if i["status"] in LEVEL), key=lambda s: LEVEL[s], default="ok")
