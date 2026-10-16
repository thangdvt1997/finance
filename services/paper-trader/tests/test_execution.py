"""Khớp lệnh/phí/slippage/PnL so với giá trị TÍNH TAY."""
from __future__ import annotations

import pytest

from paper_trader import portfolio as pf
from paper_trader.execution import simulate_fill
from paper_trader.models import AccountState, Bar, Instrument, Order

from .conftest import START, fx_inst


def order(side, qty, sym="EURUSD"):
    return Order("c1", "a", sym, side, qty, START, START)


def bar(o, h=None, l=None):
    return Bar(START, o, h or o, l or o, o)


def test_buy_fill_hand_calc():
    inst = fx_inst("EURUSD", spread_bps=2.0, slippage_bps=1.0, commission_bps=0.5)
    f = simulate_fill(order("buy", 10_000), bar(1.1000), inst, 1.0)
    # giá = 1.1 * (1 + (2/2 + 1)/1e4) = 1.1 * 1.0002 = 1.10022
    assert f.price == pytest.approx(1.10022)
    assert f.spread_cost == pytest.approx(10_000 * 1.1 * 1e-4)          # 1.10
    assert f.slippage_cost == pytest.approx(10_000 * 1.1 * 1e-4)        # 1.10
    assert f.commission == pytest.approx(0.5e-4 * 10_000 * 1.10022)     # 0.55011
    assert f.tax == 0.0 and f.ts == START and f.ref_price == 1.1


def test_sell_fill_is_worse_for_seller():
    inst = fx_inst("EURUSD", spread_bps=2.0, slippage_bps=1.0)
    f = simulate_fill(order("sell", 10_000), bar(1.1000), inst, 1.0)
    assert f.price == pytest.approx(1.1 * (1 - 2e-4)) == pytest.approx(1.09978)


def test_range_slippage_scales_with_bar_range():
    inst = fx_inst("EURUSD", spread_bps=0.0, slippage_bps=0.0, slip_range_frac=0.1)
    f = simulate_fill(order("buy", 1000), bar(1.1000, h=1.1110, l=1.1000), inst, 1.0)
    assert f.price == pytest.approx(1.1 * (1 + 0.1 * 0.0110 / 1.1))      # +0.001 tương đối


def test_vn_equity_sell_has_tax_and_commission():
    inst = Instrument("VN:VNM", kind="equity", quote="VND", lot=100, spread_bps=10, slippage_bps=5, commission_bps=15, sell_tax_bps=10, shortable=False)
    f = simulate_fill(order("sell", 1000, "VN:VNM"), bar(50_000), inst, 1.0)
    assert f.price == pytest.approx(50_000 * (1 - (5e-4 + 5e-4))) == pytest.approx(49_950)
    notional = 1000 * 49_950
    assert f.commission == pytest.approx(15e-4 * notional)               # 74_925
    assert f.tax == pytest.approx(10e-4 * notional)                      # 49_950
    b = simulate_fill(order("buy", 1000, "VN:VNM"), bar(50_000), inst, 1.0)
    assert b.tax == 0.0 and b.price == pytest.approx(50_050)


def test_min_fee():
    inst = fx_inst("EURUSD", commission_bps=0.1, min_fee=2.0)
    assert simulate_fill(order("buy", 100), bar(1.1), inst, 1.0).commission == 2.0


def test_q2b_variants():
    px = {"USDJPY": 150.0, "EURUSD": 1.2}.get
    assert pf.q2b("USD", "USD", px) == 1.0
    assert pf.q2b("JPY", "USD", px) == pytest.approx(1 / 150)           # tài khoản USD, giá JPY
    assert pf.q2b("EUR", "USD", px) == pytest.approx(1.2)
    assert pf.q2b("CHF", "USD", px) is None


def test_position_pnl_long_close_and_flip():
    st = AccountState(cash=10_000, initial_capital=10_000)
    inst = fx_inst("EURUSD")

    def fill(side, qty, price):
        f = simulate_fill(order(side, qty), bar(price), inst, 1.0)
        pf.apply_fill(st, f)
        return f

    fill("buy", 10, 100.0)
    f = fill("sell", 4, 110.0)
    assert f.realized_pnl == pytest.approx(40.0)
    assert st.positions["EURUSD"].qty == 6 and st.positions["EURUSD"].avg_price == pytest.approx(100.0)
    f = fill("sell", 10, 105.0)                                           # đóng 6 (lãi 30) rồi mở short 4
    assert f.realized_pnl == pytest.approx(30.0)
    assert st.positions["EURUSD"].qty == pytest.approx(-4) and st.positions["EURUSD"].avg_price == pytest.approx(105.0)
    f = fill("buy", 4, 100.0)                                              # đóng short: (105-100)*4 = 20
    assert f.realized_pnl == pytest.approx(20.0) and st.positions["EURUSD"].qty == 0
    assert st.cash == pytest.approx(10_000 + 40 + 30 + 20)


def test_usdjpy_pnl_converted_to_usd():
    st = AccountState(cash=10_000, initial_capital=10_000)
    inst = fx_inst("USDJPY")
    pf.apply_fill(st, simulate_fill(order("buy", 10_000, "USDJPY"), bar(150.0), inst, 1 / 150))
    f = simulate_fill(order("sell", 10_000, "USDJPY"), bar(151.0), inst, 1 / 151)
    pf.apply_fill(st, f)
    assert f.realized_pnl == pytest.approx(10_000 * 1.0 / 151)            # 10.000 JPY -> USD tại 151
    eq, gross, net, _ = pf.mark(st, "USD", {"USDJPY": inst}, {"USDJPY": 151.0}.get)
    assert eq == pytest.approx(10_000 + 10_000 / 151) and gross == 0


def test_mark_unrealized_and_exposure():
    st = AccountState(cash=1000, initial_capital=1000)
    inst = fx_inst("EURUSD")
    pf.apply_fill(st, simulate_fill(order("sell", 1000), bar(1.2), inst, 1.0))       # short 1000 @ 1.2
    eq, gross, net, det = pf.mark(st, "USD", {"EURUSD": inst}, {"EURUSD": 1.1}.get)
    assert eq == pytest.approx(1000 + 1000 * (1.2 - 1.1))                             # +100
    assert gross == pytest.approx(1100) and net == pytest.approx(-1100)
    assert det["EURUSD"]["unrealized"] == pytest.approx(100)
