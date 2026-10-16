"""TCA (phân tích chi phí giao dịch) cho paper: chi phí/slippage THỰC TẾ MÔ PHỎNG vs GIẢ ĐỊNH, chi phí luỹ kế, vòng quay.
Lưu ý trung thực: giá khớp do bộ mô phỏng sinh ra (open ± nửa spread ± slippage cố định ± frac×biên độ bar) nên 'thực tế' ở đây = mô hình
có tính biên độ bar; chưa phải fill thật. Cùng công thức sẽ dùng cho fill demo/live khi có (so với quote lúc gửi lệnh)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .perfx import asset_class

MIN_FILLS_RATIO = 10      # dưới số fill này không kết luận tỷ lệ chi phí thực/giả định


def _assumed_fixed_bps(a: dict | None) -> float | None:
    """Giả định cố định mỗi chiều: nửa spread + trượt giá cố định (bps). Phần frac×biên độ bar KHÔNG nằm trong giả định cố định."""
    if not a:
        return None
    return float(a.get("spread_bps", 0.0)) / 2.0 + float(a.get("slippage_bps", 0.0))


def _assumed_fee_bps(a: dict | None, side: str) -> float | None:
    if not a:
        return None
    return float(a.get("commission_bps", 0.0)) + (float(a.get("sell_tax_bps", 0.0)) if side == "sell" else 0.0)


def fill_table(fills: list[dict], assumptions: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for f in fills:
        notional = float(f["qty"]) * float(f["ref_price"]) * float(f.get("q2b") or 1.0)
        if notional <= 0:
            continue
        a = assumptions.get(f["symbol"])
        slip = (float(f.get("spread_cost") or 0) + float(f.get("slippage_cost") or 0)) / notional * 1e4
        fee = (float(f.get("commission") or 0) + float(f.get("tax") or 0)) / notional * 1e4
        fx = _assumed_fixed_bps(a)
        fa = _assumed_fee_bps(a, f["side"])
        rows.append({"ts": pd.Timestamp(f["ts"]), "symbol": f["symbol"], "cls": asset_class(f["symbol"]), "side": f["side"], "notional": notional,
                     "slip_bps": slip, "fee_bps": fee, "assumed_slip_bps": fx, "assumed_fee_bps": fa,
                     "spread_cost": float(f.get("spread_cost") or 0), "slippage_cost": float(f.get("slippage_cost") or 0),
                     "commission": float(f.get("commission") or 0), "tax": float(f.get("tax") or 0)})
    return pd.DataFrame(rows)


def _wavg(df: pd.DataFrame, col: str) -> float | None:
    d = df.dropna(subset=[col])
    w = d["notional"].sum()
    return float((d[col] * d["notional"]).sum() / w) if w > 0 and len(d) else None


def _agg(df: pd.DataFrame) -> dict:
    slip, fee = _wavg(df, "slip_bps"), _wavg(df, "fee_bps")
    a_slip, a_fee = _wavg(df, "assumed_slip_bps"), _wavg(df, "assumed_fee_bps")
    allin = None if slip is None or fee is None else slip + fee
    a_all = None if a_slip is None or a_fee is None else a_slip + a_fee
    return {"fills": int(len(df)), "notional": float(df["notional"].sum()), "realized_slip_bps": slip, "assumed_slip_bps": a_slip,
            "range_extra_bps": None if slip is None or a_slip is None else slip - a_slip, "fee_bps": fee, "assumed_fee_bps": a_fee,
            "all_in_bps": allin, "assumed_all_in_bps": a_all, "ratio": (allin / a_all) if allin is not None and a_all and a_all > 1e-9 else None}


def report(fills: list[dict], assumptions: dict[str, dict], state_costs: dict, traded_notional: float, eq_rows: list[dict], initial: float,
           ppy: int = 252, expectation: dict | None = None, days: int | None = None) -> dict:
    out: dict[str, Any] = {"fills": len(fills), "status": "insufficient", "model": "bộ mô phỏng: giá khớp = open ± (nửa spread + slippage cố định + frac×biên độ bar)"}
    costs = {k: float(state_costs.get(k, 0.0)) for k in ("spread", "slippage", "commission", "tax", "swap")}
    total = sum(costs.values())
    avg_eq = float(np.mean([float(e["equity"]) for e in eq_rows])) if eq_rows else float(initial)
    out["costs_cum"] = {**costs, "total": total, "pct_of_initial": total / initial if initial else None, "pct_of_avg_equity": total / avg_eq if avg_eq else None,
                        "note": "spread/slippage đã nằm trong giá khớp (không trừ lần hai); phí/thuế/swap trừ tiền mặt"}
    out["turnover"] = {"traded_notional": traded_notional, "x_equity": traded_notional / avg_eq if avg_eq else None}
    n_days = days if days is not None else len(eq_rows)
    if n_days >= 20 and avg_eq:
        yrs = n_days / ppy
        out["turnover"]["x_equity_annualized"] = out["turnover"]["x_equity"] / yrs
        out["cost_drag_annualized"] = (total / avg_eq) / yrs
    if expectation:
        out["backtest_reference"] = {"turnover_per_year": expectation.get("turnover_yr"), "cost_drag_per_year": expectation.get("cost_drag_yr"),
                                     "note": "đòn bẩy trung bình paper thấp hơn backtest (trần gộp 2,0x vs 2,3x) nên so theo bps trên giá trị khớp, không theo %/năm"}
    df = fill_table(fills, assumptions)
    if df.empty:
        out["overall"] = None
        out["note"] = "chưa có fill nào"
        return out
    out["overall"] = _agg(df)
    ov = out["overall"]
    out["status"] = "insufficient"
    if ov["fills"] >= MIN_FILLS_RATIO and ov["ratio"] is not None:
        out["status"] = "red" if ov["ratio"] > 2.0 else "yellow" if ov["ratio"] > 1.5 else "green"
    out["by_class"] = [{"class": c, **_agg(g)} for c, g in df.groupby("cls")]
    top = df.groupby("symbol")["notional"].sum().sort_values(ascending=False).head(10).index
    out["by_symbol"] = [{"symbol": s, **_agg(df[df.symbol == s])} for s in top]
    out["by_side"] = [{"side": s, **_agg(g)} for s, g in df.groupby("side")]
    d = df.sort_values("ts")
    d["cost"] = d["spread_cost"] + d["slippage_cost"] + d["commission"] + d["tax"]
    cum = d.groupby(d["ts"].dt.floor("D"))["cost"].sum().cumsum()
    out["cumulative"] = [{"ts": t.isoformat(), "cost": float(v), "pct_initial": float(v) / initial if initial else None} for t, v in cum.items()][-300:]
    out["note"] = (f"{ov['fills']} fill: chi phí toàn phần {ov['all_in_bps']:.2f} bps/chiều vs giả định {ov['assumed_all_in_bps']:.2f} bps"
                   if ov["all_in_bps"] is not None and ov["assumed_all_in_bps"] is not None else "")
    return out
