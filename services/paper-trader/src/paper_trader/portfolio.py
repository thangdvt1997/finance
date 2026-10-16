"""Sổ vị thế/tiền mặt theo kiểu 'margin': tiền mặt chỉ đổi theo lãi/lỗ đã chốt, phí, thuế, swap;
equity = tiền mặt + Σ lãi/lỗ chưa chốt (quy đổi về tiền tài khoản). Dùng chung cho FX/vàng/cổ phiếu."""
from __future__ import annotations

from typing import Callable

from .models import AccountState, Fill, Instrument, Position

PriceOf = Callable[[str], float | None]


def q2b(quote: str, base: str, price_of: PriceOf) -> float | None:
    """Tỷ giá quote -> tiền tài khoản. USDJPY với tài khoản USD: 1/giá(USDJPY). None nếu không có cặp quy đổi."""
    if quote == base:
        return 1.0
    p = price_of(f"{base}{quote}")           # vd USDJPY: JPY trên 1 USD
    if p:
        return 1.0 / p
    p = price_of(f"{quote}{base}")           # vd EURUSD: USD trên 1 EUR
    return p if p else None


def apply_fill(st: AccountState, f: Fill) -> None:
    pos = st.positions.setdefault(f.symbol, Position())
    signed = f.qty if f.side == "buy" else -f.qty
    old = pos.qty
    realized = 0.0
    if old != 0 and (old > 0) != (signed > 0):
        closed = min(abs(old), abs(signed))
        realized = closed * (f.price - pos.avg_price) * (1 if old > 0 else -1) * f.q2b
    new = old + signed
    if abs(new) < 1e-9:
        pos.qty, pos.avg_price = 0.0, 0.0
    elif old == 0 or (old > 0) == (signed > 0):
        pos.avg_price = (abs(old) * pos.avg_price + abs(signed) * f.price) / abs(new)
        pos.qty = new
    elif (new > 0) != (old > 0):             # đảo chiều: phần còn lại mở mới ở giá khớp
        pos.avg_price, pos.qty = f.price, new
    else:
        pos.qty = new
    f.realized_pnl = realized
    st.cash += realized - f.commission - f.tax
    st.costs["spread"] += f.spread_cost
    st.costs["slippage"] += f.slippage_cost
    st.costs["commission"] += f.commission
    st.costs["tax"] += f.tax
    st.traded_notional += f.qty * f.price * f.q2b
    st.n_fills += 1


def mark(st: AccountState, base: str, instruments: dict[str, Instrument], price_of: PriceOf) -> tuple[float, float, float, dict]:
    """Trả (equity, gross_notional, net_notional, positions_detail) theo giá `price_of` (đóng cửa)."""
    equity, gross, net = st.cash, 0.0, 0.0
    detail: dict[str, dict] = {}
    for sym, pos in st.positions.items():
        if pos.qty == 0:
            detail[sym] = {"qty": 0.0, "avg_price": 0.0, "mark": price_of(sym) or 0.0, "unrealized": 0.0, "notional": 0.0}
            continue
        px = price_of(sym)
        if px is None:
            px = pos.avg_price
        conv = q2b(instruments[sym].quote, base, price_of) or 1.0
        unreal = pos.qty * (px - pos.avg_price) * conv
        notional = pos.qty * px * conv
        equity += unreal
        gross += abs(notional)
        net += notional
        detail[sym] = {"qty": pos.qty, "avg_price": pos.avg_price, "mark": px, "unrealized": unreal, "notional": notional}
    return equity, gross, net, detail


def symbol_ccys(sym: str) -> list[str]:
    if sym.startswith("VN:"):
        return ["VND"]
    if len(sym) == 6 and sym.isalpha():
        return [sym[:3], sym[3:]]
    return [sym]


def conversion_candidates(quote: str, base: str) -> list[str]:
    return [] if quote == base else [f"{base}{quote}", f"{quote}{base}"]
