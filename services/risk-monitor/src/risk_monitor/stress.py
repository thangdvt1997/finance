"""Stress test: áp kịch bản lên vị thế HIỆN TẠI.
 - replay: biến động giá thật trong cửa sổ [start,end] từ bars D1 (P&L_i = V_i · (C_end/C_start − 1)).
 - shock : giả định (ccy / classes / symbols / adverse_pct).
Giả định: tỷ giá quy đổi và margin yêu cầu giữ nguyên; không có trượt giá/gap/spread giãn (đánh giá THẤP so với thực tế)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .exposure import Holding


def _d(x) -> date:
    return x if isinstance(x, date) and not isinstance(x, datetime) else datetime.fromisoformat(str(x)).date()


def window_return(closes: pd.Series, start: date, end: date, tol_days: int = 6) -> float | None:
    """C(≤end)/C(≤start) − 1, mỗi mốc lấy phiên gần nhất trước/đúng ngày nhưng không cũ quá `tol_days`."""
    s = closes.dropna()
    if s.empty:
        return None
    idx = pd.to_datetime(s.index).normalize()
    s.index = idx

    def at(d: date):
        ts = pd.Timestamp(d)
        sub = s[s.index <= ts]
        if sub.empty or (ts - sub.index[-1]).days > tol_days:
            return None
        return float(sub.iloc[-1])

    a, b = at(start), at(end)
    if not a or b is None or a <= 0:
        return None
    return b / a - 1.0


def shock_for(h: Holding, scn: dict) -> float | None:
    """% thay đổi giá (dạng phân số) của mã theo kịch bản giả định; None nếu kịch bản không tác động mã này."""
    sym = h.symbol
    if sym in (scn.get("symbols") or {}):
        return float(scn["symbols"][sym]) / 100.0
    ccy = scn.get("ccy") or {}
    spec = h.spec
    if spec.kind == "fx" and ccy and (spec.base in ccy or spec.quote in ccy):
        b = float(ccy.get(spec.base, 0.0)) / 100.0
        q = float(ccy.get(spec.quote, 0.0)) / 100.0
        return (1 + b) / (1 + q) - 1
    cls = (scn.get("classes") or {})
    if spec.cls in cls:
        return float(cls[spec.cls]) / 100.0
    if spec.kind == "metal" and "USD" in ccy and spec.quote == "USD" and spec.cls not in cls:
        return 1.0 / (1 + float(ccy["USD"]) / 100.0) - 1  # vàng/bạc định giá bằng USD
    return None


def run_scenario(scn: dict, holdings: list[Holding], closes: pd.DataFrame | None, equity: float | None,
                 stop_out_equity: float | None = None) -> dict:
    items, missing = [], []
    kind = scn.get("type", "shock")
    for h in holdings:
        ret = None
        if kind == "replay":
            if closes is not None and h.symbol in closes.columns:
                ret = window_return(closes[h.symbol], _d(scn["start"]), _d(scn["end"]))
            if ret is None:
                missing.append(h.symbol)
                continue
        else:
            if "adverse_pct" in scn:
                ret = -float(scn["adverse_pct"]) / 100.0 * h.sign  # bất lợi cho vị thế: long giảm, short tăng
            else:
                ret = shock_for(h, scn)
            if ret is None:
                ret = 0.0
        pnl = h.value * ret
        items.append({"symbol": h.symbol, "side": h.side, "value": h.value, "move_pct": ret * 100.0, "pnl": pnl})
    total = sum(i["pnl"] for i in items)
    eq_after = (equity + total) if equity is not None else None
    covered = [h for h in holdings if h.symbol not in missing]
    gross_all = sum(abs(h.value) for h in holdings)
    cov_pct = (sum(abs(h.value) for h in covered) / gross_all * 100.0) if gross_all else 100.0
    items.sort(key=lambda i: i["pnl"])
    out = {
        "id": scn["id"], "name": scn.get("name", scn["id"]), "type": kind,
        "window": f"{scn['start']} → {scn['end']}" if kind == "replay" else None,
        "pnl": total, "pnl_pct": (total / equity * 100.0 if equity else None),
        "equity_after": eq_after, "coverage_pct": cov_pct, "missing": missing,
        "worst": items[:3], "best": items[-1:] if items and items[-1]["pnl"] > 0 else [],
        "breach_zero": bool(eq_after is not None and eq_after <= 0),
        "breach_stop_out": bool(eq_after is not None and stop_out_equity is not None and stop_out_equity > 0 and eq_after <= stop_out_equity),
    }
    if kind == "replay" and not items and holdings:
        out["note"] = "Không có dữ liệu lịch sử D1 trong cửa sổ này cho các mã đang giữ"
    return out


def run_all(scenarios: list[dict], holdings: list[Holding], closes_by_scn: dict[str, pd.DataFrame], equity: float | None,
            stop_out_equity: float | None = None) -> list[dict]:
    if not holdings:
        return []
    res = [run_scenario(s, holdings, closes_by_scn.get(s["id"]), equity, stop_out_equity) for s in scenarios]
    return sorted(res, key=lambda r: r["pnl"])
