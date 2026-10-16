"""Mô phỏng khớp lệnh (BẢO THỦ, tất định). Khớp ở GIÁ MỞ CỬA của bar kế tiếp (đã quan sát được sau khi ra lệnh):
    giá = open * (1 ± (spread_bps/2 + slippage_bps)/1e4 ± slip_range_frac*(high-low)/open)     (+ khi mua, - khi bán)
Spread/trượt giá đã nằm trong giá khớp (thông tin chi phí chỉ để báo cáo, KHÔNG trừ lần hai). Phí và thuế trừ vào tiền mặt.
"""
from __future__ import annotations

from .models import Bar, Fill, Instrument, Order, utc


def fill_price(side: str, bar: Bar, inst: Instrument) -> tuple[float, float, float]:
    """Trả (giá khớp, spread_frac_mỗi_chiều, slip_frac). Mọi tỷ lệ theo giá mở cửa."""
    half = inst.spread_bps / 2.0 / 1e4
    slip = inst.slippage_bps / 1e4 + (inst.slip_range_frac * (bar.h - bar.l) / bar.o if bar.o > 0 else 0.0)
    sign = 1.0 if side == "buy" else -1.0
    return bar.o * (1.0 + sign * (half + slip)), half, slip


def simulate_fill(order: Order, bar: Bar, inst: Instrument, q2b: float) -> Fill:
    price, half, slip = fill_price(order.side, bar, inst)
    notional = order.qty * price * q2b
    commission = max(inst.commission_bps / 1e4 * notional, inst.min_fee) if order.qty > 0 else 0.0
    tax = inst.sell_tax_bps / 1e4 * notional if order.side == "sell" else 0.0
    return Fill(client_order_id=order.client_order_id, account_id=order.account_id, symbol=order.symbol, side=order.side,
                qty=order.qty, ts=utc(bar.ts_open), ref_price=bar.o, price=price,
                spread_cost=order.qty * bar.o * half * q2b, slippage_cost=order.qty * bar.o * slip * q2b,
                commission=commission, tax=tax, q2b=q2b)
