"""Vị thế -> exposure quy đổi tiền tệ tài khoản. MT4 hedging (nhiều ticket/mã, có thể ngược chiều) vs MT5 netting (1 vị thế/mã).
Mọi số là ƯỚC TÍNH từ snapshot (READ-ONLY); không thay thế số margin của broker."""
from __future__ import annotations

from dataclasses import dataclass

from .instruments import Spec, classify, fx_rate


@dataclass
class Holding:
    symbol: str
    side: str            # buy | sell | long | short
    units: float         # đơn vị công cụ, luôn dương
    lots: float | None   # MT: lot; paper: None
    price: float
    value: float         # GIÁ TRỊ DANH NGHĨA có dấu (long +, short -) tính bằng tiền tệ tài khoản
    spec: Spec
    pnl: float = 0.0
    position_id: str = ""

    @property
    def sign(self) -> int:
        return 1 if self.side in ("buy", "long") else -1


def mt_holdings(positions: list[dict], acct_ccy: str, prices: dict[str, float], cfg: dict) -> tuple[list[Holding], list[str]]:
    """positions = list dict theo mô hình mt-bridge (symbol, side, volume, price_current, profit, position_id)."""
    out: list[Holding] = []
    warns: list[str] = []
    px = dict(prices)
    for p in positions:  # giá hiện tại của chính vị thế ưu tiên hơn nến D1
        if p.get("price_current"):
            px[p["symbol"].upper()] = float(p["price_current"])
    for p in positions:
        sym = p["symbol"]
        spec = classify(sym, cfg, default_quote=acct_ccy)
        lots = float(p.get("volume") or 0.0)
        units = lots * spec.contract
        price = float(p.get("price_current") or p.get("price_open") or 0.0)
        if units <= 0 or price <= 0:
            continue
        if spec.kind == "fx":  # danh nghĩa = lượng tiền BASE quy ra tiền tệ tài khoản
            r = fx_rate(spec.base, acct_ccy, px)
            val = units * r if r is not None else None
        else:
            rq = fx_rate(spec.quote, acct_ccy, px)
            val = units * price * rq if rq is not None else None
        if val is None:
            warns.append(f"Thiếu tỷ giá quy đổi sang {acct_ccy} cho {sym}: bỏ khỏi exposure")
            continue
        sign = 1 if str(p.get("side", "buy")).lower() == "buy" else -1
        out.append(Holding(sym, "buy" if sign > 0 else "sell", units, lots, price, sign * val, spec,
                           pnl=float(p.get("profit") or 0.0), position_id=str(p.get("position_id", ""))))
    return out, warns


def paper_holdings(rows: list[dict], base_ccy: str, cfg: dict) -> list[Holding]:
    """rows = paper_positions: symbol, qty (âm = short), mark_price/avg_price, notional, unrealized_pnl (tiền tệ cơ sở)."""
    out = []
    for r in rows:
        qty = float(r.get("qty") or 0.0)
        if qty == 0:
            continue
        price = float(r.get("mark_price") or r.get("avg_price") or 0.0)
        notional = r.get("notional")
        val = float(notional) if notional is not None else qty * price
        val = abs(val) * (1 if qty > 0 else -1)  # ép dấu theo qty
        spec = classify(r["symbol"], cfg, default_quote=base_ccy)
        out.append(Holding(r["symbol"], "long" if qty > 0 else "short", abs(qty), None, price, val, spec,
                           pnl=float(r.get("unrealized_pnl") or 0.0)))
    return out


def summarize(holdings: list[Holding], equity: float | None, platform: str = "mt5", margin_mode: str = "unknown") -> dict:
    """Exposure theo mã / tiền tệ / nhóm tài sản + gross/net/đòn bẩy hiệu dụng."""
    by_sym: dict[str, dict] = {}
    by_ccy: dict[str, float] = {}
    by_cls: dict[str, float] = {}
    for h in holdings:
        s = by_sym.setdefault(h.symbol, {"symbol": h.symbol, "cls": h.spec.cls, "long_lots": 0.0, "short_lots": 0.0,
                                         "long_value": 0.0, "short_value": 0.0, "positions": 0, "pnl": 0.0})
        qty = h.lots if h.lots is not None else h.units
        if h.sign > 0:
            s["long_lots"] += qty
            s["long_value"] += h.value
        else:
            s["short_lots"] += qty
            s["short_value"] += h.value
        s["positions"] += 1
        s["pnl"] += h.pnl
        if h.spec.kind in ("fx", "metal"):  # exposure tiền tệ: cặp BASE/QUOTE = long BASE, short QUOTE cùng độ lớn
            if h.spec.base:
                by_ccy[h.spec.base] = by_ccy.get(h.spec.base, 0.0) + h.value
            by_ccy[h.spec.quote] = by_ccy.get(h.spec.quote, 0.0) - h.value
    rows = []
    for s in by_sym.values():
        s["net_lots"] = round(s["long_lots"] - s["short_lots"], 8)
        s["net_value"] = s["long_value"] + s["short_value"]
        s["gross_value"] = s["long_value"] - s["short_value"]
        s["hedged_lots"] = round(min(s["long_lots"], s["short_lots"]), 8)
        by_cls[s["cls"]] = by_cls.get(s["cls"], 0.0) + s["net_value"]
        rows.append(s)
    rows.sort(key=lambda r: (-abs(r["net_value"]), -r["gross_value"]))
    gross = sum(abs(h.value) for h in holdings)                 # mọi chân (hedging tính cả 2 chân)
    net_abs = sum(abs(r["net_value"]) for r in rows)            # sau khi bù trừ trong từng mã
    long_v = sum(r["net_value"] for r in rows if r["net_value"] > 0)
    short_v = sum(r["net_value"] for r in rows if r["net_value"] < 0)
    eq = equity if equity and equity > 0 else None
    warns = []
    if margin_mode == "netting" and any(r["positions"] > 1 for r in rows):
        warns.append("Tài khoản netting nhưng có >1 vị thế/mã: kiểm tra dữ liệu snapshot")
    mode = margin_mode if margin_mode != "unknown" else ("hedging" if platform == "mt4" else "unknown")
    return {
        "mode": mode,
        "positions": len(holdings),
        "gross_notional": gross, "net_notional_abs": net_abs, "long_value": long_v, "short_value": short_v,
        "leverage_gross": gross / eq if eq else None, "leverage_net": net_abs / eq if eq else None,
        "hedged_notional": gross - net_abs,
        "by_symbol": rows,
        "by_currency": sorted(({"ccy": k, "net_value": v, "pct_equity": (v / eq * 100 if eq else None)} for k, v in by_ccy.items()),
                              key=lambda r: -abs(r["net_value"])),
        "by_class": sorted(({"cls": k, "net_value": v, "pct_equity": (v / eq * 100 if eq else None)} for k, v in by_cls.items()),
                           key=lambda r: -abs(r["net_value"])),
        "max_ccy_conc_pct": max((abs(v) / eq * 100 for v in by_ccy.values()), default=0.0) if eq else None,
        "warnings": warns,
    }


def margin_metrics(equity: float | None, balance: float | None, margin: float | None, gross: float, net_abs: float,
                   nominal_leverage: int | None, stop_out_pct: float, margin_call_pct: float, warn_pct: float) -> dict:
    """Mức margin, margin tự do, khoảng cách tới stop-out. Giả định margin yêu cầu KHÔNG đổi khi giá chạy (xấp xỉ)."""
    eq = float(equity or 0.0)
    mg = float(margin or 0.0)
    level = eq / mg * 100.0 if mg > 0 else None
    out = {
        "equity": eq, "balance": balance, "margin_used": mg, "free_margin": eq - mg,
        "margin_level_pct": level, "nominal_leverage": nominal_leverage or None,
        "margin_used_pct_equity": (mg / eq * 100.0 if eq > 0 else None),
        "stop_out_pct": stop_out_pct, "margin_call_pct": margin_call_pct,
    }
    if mg <= 0:
        out.update(status="no_position", stop_out_equity=0.0, distance_to_stop_out=eq,
                   distance_pct_equity=100.0 if eq > 0 else None, adverse_move_pct_gross=None, adverse_move_pct_net=None)
        return out
    so_eq = mg * stop_out_pct / 100.0
    dist = eq - so_eq
    out.update(
        stop_out_equity=so_eq, distance_to_stop_out=dist,
        distance_pct_equity=(dist / eq * 100.0 if eq > 0 else None),
        # mọi vị thế cùng bất lợi (xấu nhất) / chỉ phần net sau bù trừ
        adverse_move_pct_gross=(max(dist, 0.0) / gross * 100.0 if gross > 0 else None),
        adverse_move_pct_net=(max(dist, 0.0) / net_abs * 100.0 if net_abs > 0 else None),
    )
    if level <= stop_out_pct:
        out["status"] = "stop_out"
    elif level <= margin_call_pct:
        out["status"] = "margin_call"
    elif level <= warn_pct:
        out["status"] = "warn"
    else:
        out["status"] = "ok"
    return out
