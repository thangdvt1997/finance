"""Engine: chống look-ahead, lịch rebalance, swap, kill-switch, idempotency, plugin."""
from __future__ import annotations

import pytest

from paper_trader.models import Targets
from paper_trader.strategy import Strategy, StrategyContext, load_plugins, register

from .conftest import DAY, START, fx_inst, make_engine, rows_from_closes, view_of


def run_all(eng, view, syms=None):
    out = []
    for T in view.step_times(eng.state.last_close, syms or eng.universe):
        out.append(eng.step(T, view))
    return out


def test_buy_and_hold_fills_at_next_bar_open_not_signal_bar():
    closes = [1.10, 1.11, 1.12, 1.13]
    opens = [1.10, 1.105, 1.115, 1.125]
    v = view_of({"EURUSD": rows_from_closes(closes, opens=opens)})
    eng = make_engine(risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0})
    r0, r1 = eng.step(START, v), eng.step(START + DAY, v)
    assert len(r0.new_orders) == 1 and not r0.fills                         # quyết định ở đóng cửa bar0, CHƯA khớp
    o = r0.new_orders[0]
    assert o.decision_ts == START + DAY and o.eligible_from == START + DAY
    assert len(r1.fills) == 1
    f = r1.fills[0]
    assert f.ts == START + DAY and f.ref_price == 1.105                    # khớp ở GIÁ MỞ CỬA bar1, không phải close bar0 (1.10)
    qty = int(10_000 * 1.0 / 1.10)                                          # sizing theo close bar tín hiệu, lot=1
    assert f.qty == qty == o.qty


def test_no_lookahead_future_data_cannot_change_past_decisions():
    base = [1.0 + 0.01 * i for i in range(40)]
    poison = base[:25] + [50.0, 0.01, 99.0] + base[28:]
    seen = {}

    @register("probe_lookahead")
    class Probe(Strategy):
        def targets(self, ctx: StrategyContext) -> Targets:
            seen.setdefault(self.params["tag"], []).append((ctx.now, {s: df.index[-1] for s, df in ctx.history.items()}, float(ctx.history["EURUSD"]["c"].iloc[-1])))
            return Targets(weights={"EURUSD": 0.5 if ctx.history["EURUSD"]["c"].iloc[-1] > ctx.history["EURUSD"]["c"].iloc[0] else 0.0})

    res = {}
    for tag, closes in (("a", base), ("b", poison)):
        eng = make_engine("probe_lookahead", {"tag": tag}, rebalance="daily", risk={"max_leverage": 5, "max_weight": 5, "min_trade_weight": 0.0})
        v = view_of({"EURUSD": rows_from_closes(closes)})
        res[tag] = run_all(eng, v)
    # (1) chiến lược không bao giờ thấy bar sau thời điểm quyết định
    for now, last_idx, _ in seen["a"] + seen["b"]:
        assert all(ts + DAY <= now for ts in last_idx.values())
    # (2) bar 0..24 giống nhau -> quyết định/lệnh/fill/equity tới bar 24 giống hệt, dù tương lai bị đầu độc
    for i in range(25):
        a, b = res["a"][i], res["b"][i]
        assert [(o.client_order_id, o.side, o.qty) for o in a.new_orders] == [(o.client_order_id, o.side, o.qty) for o in b.new_orders]
        assert [(f.price, f.qty) for f in a.fills] == [(f.price, f.qty) for f in b.fills]
        assert a.equity == pytest.approx(b.equity)


def test_view_drops_unclosed_bar():
    rows = rows_from_closes([1.0, 1.1, 1.2])
    now = START + DAY * 2 + DAY / 2                                            # bar thứ 3 (ts_open = START+2d) chưa đóng
    v = view_of({"EURUSD": rows}, now=now)
    assert [t for t in v.step_times(None, ["EURUSD"])] == [START, START + DAY]
    assert v.latest_close_ts(["EURUSD"]) == START + DAY * 2


def test_monthly_rebalance_only_when_month_changes():
    closes = [1.0 + 0.001 * i for i in range(70)]
    eng2 = make_engine("slow_trend_simple", {"momentum_days": 3, "skip_days": 1, "ma_days": 3, "allow_short": False},
                       rebalance="monthly", risk={"max_leverage": 5, "max_weight": 5, "min_trade_weight": 0.0})
    rs2 = run_all(eng2, view_of({"EURUSD": rows_from_closes(closes)}))
    months = [(r.bar_ts.year, r.bar_ts.month) for r in rs2 if any(e["type"] == "rebalance" for e in r.events)]
    assert months == [(2026, 1), (2026, 2), (2026, 3)]                         # đúng 1 lần/tháng, ở bar đầu tiên đủ dữ liệu của tháng
    first = {m: [r.bar_ts for r in rs2 if (r.bar_ts.year, r.bar_ts.month) == m and any(e["type"] == "rebalance" for e in r.events)][0] for m in months}
    assert first[(2026, 2)].day == 1 and first[(2026, 3)].day == 1


def test_warmup_when_history_too_short_stays_flat():
    eng = make_engine("slow_trend_simple", {"momentum_days": 252, "skip_days": 21, "ma_days": 200}, rebalance="monthly")
    rs = run_all(eng, view_of({"EURUSD": rows_from_closes([1.0 + 0.001 * i for i in range(30)])}))
    assert all(not r.new_orders and not r.fills for r in rs)
    assert any(e["type"] == "warmup" for r in rs for e in r.events)
    assert rs[-1].equity == pytest.approx(10_000)


def test_swap_accrual_hand_calc():
    # swap_long 3650 bps/năm = 36,5%/năm = 0,1%/ngày; vị thế danh nghĩa 10.000 USD, mỗi bar D1 = 1 ngày -> 10 USD/ngày
    inst = {"EURUSD": fx_inst("EURUSD", swap_long_bps=3650)}
    eng = make_engine(instruments=inst, risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0})
    v = view_of({"EURUSD": rows_from_closes([1.0] * 6, opens=[1.0] * 6)})
    rs = run_all(eng, v)
    assert rs[0].swap_step == 0 and rs[1].swap_step == pytest.approx(10.0)    # vị thế mở ở open bar1 -> tính cả bar1
    assert eng.state.costs["swap"] == pytest.approx(10.0 * 5)
    assert rs[-1].equity == pytest.approx(10_000 - 50.0)


def test_swap_charged_over_weekend_gap():
    rows = rows_from_closes([1.0] * 6, opens=[1.0] * 6)
    rows = [r for i, r in enumerate(rows) if i != 3]                           # thiếu bar ngày 4 -> khoảng nghỉ 1 ngày
    eng = make_engine(instruments={"EURUSD": fx_inst("EURUSD", swap_long_bps=3650)},
                      risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0})
    rs = run_all(eng, view_of({"EURUSD": rows}))
    gap = [r for r in rs if r.bar_ts == START + DAY * 4][0]
    assert gap.swap_step == pytest.approx(20.0)                                # 1 ngày nghỉ + 1 ngày bar


def test_daily_loss_kill_switch_halts_flattens_and_resumes_next_day():
    closes = [1.0, 1.0, 0.95, 0.95, 0.95, 0.95]
    opens = [1.0, 1.0, 1.0, 0.95, 0.95, 0.95]
    eng = make_engine(risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0, "max_daily_loss": 0.03,
                            "max_weekly_loss": 0.5, "max_drawdown": 0.5}, rebalance="daily")
    rs = run_all(eng, view_of({"EURUSD": rows_from_closes(closes, opens=opens)}))
    ks = [r for r in rs if any(e["type"] == "kill_switch" for e in r.events)]
    assert len(ks) == 1 and ks[0].bar_ts == START + DAY * 2                    # lỗ 5% trong ngày > 3%
    assert [o.kind for o in ks[0].new_orders] == ["flatten"] and ks[0].new_orders[0].side == "sell"
    assert any(e["type"] == "kill_switch" and e["severity"] == "crit" for e in ks[0].events)
    nxt = rs[3]                                                               # flatten khớp ở open bar kế, KHÔNG có lệnh mới khi đang halted
    assert nxt.fills and nxt.fills[0].side == "sell"
    assert nxt.positions["EURUSD"]["qty"] == 0
    # sang ngày kế tiếp (bar 3 cùng bar flatten khớp: halt_until = đầu ngày bar 3) -> mở khoá + quyết định lại
    assert any(e["type"] == "halt_released" for r in rs for e in r.events)
    assert eng.state.status == "active"


def test_drawdown_hard_lock_requires_manual_reset():
    closes = [1.0, 1.0, 0.8, 0.8, 0.8, 1.2, 1.2]
    opens = [1.0, 1.0, 1.0, 0.8, 0.8, 0.8, 1.2]
    eng = make_engine(risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0, "max_daily_loss": 0.9,
                            "max_weekly_loss": 0.9, "max_drawdown": 0.10}, rebalance="daily")
    v = view_of({"EURUSD": rows_from_closes(closes, opens=opens)})
    rs = run_all(eng, v)
    assert eng.state.status == "locked"
    assert not any(r.new_orders for r in rs[3:])                               # khoá cứng: không còn lệnh mới dù giá hồi
    ev = eng.manual_reset(START + DAY * 10)
    assert ev["type"] == "kill_switch_reset" and eng.state.status == "active"


def test_step_is_not_replayable_twice():
    eng = make_engine()
    v = view_of({"EURUSD": rows_from_closes([1.0, 1.0])})
    eng.step(START, v)
    with pytest.raises(ValueError):
        eng.step(START, v)


def test_client_order_ids_unique_and_deterministic():
    closes = [1.0 + 0.01 * i for i in range(30)]
    ids = []
    for _ in range(2):
        eng = make_engine("slow_trend_simple", {"momentum_days": 3, "skip_days": 1, "ma_days": 3}, rebalance="daily",
                          risk={"max_leverage": 5, "max_weight": 5, "min_trade_weight": 0.0})
        ids.append([o.client_order_id for r in run_all(eng, view_of({"EURUSD": rows_from_closes(closes)})) for o in r.new_orders])
    assert ids[0] == ids[1] and len(ids[0]) == len(set(ids[0]))


def test_strategy_exception_does_not_crash_engine():
    @register("boom")
    class Boom(Strategy):
        def targets(self, ctx):
            raise RuntimeError("lỗi giả lập")

    eng = make_engine("boom")
    r = eng.step(START, view_of({"EURUSD": rows_from_closes([1.0, 1.0])}))
    assert any(e["type"] == "strategy_error" for e in r.events) and not r.new_orders


def test_plugin_directory_loading(tmp_path):
    (tmp_path / "my_method.py").write_text(
        "from paper_trader.strategy import Strategy, register\nfrom paper_trader.models import Targets\n"
        "@register('my_method')\nclass M(Strategy):\n    def targets(self, ctx):\n        return Targets(weights={'EURUSD': 0.1})\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("raise ImportError('x')\n", encoding="utf-8")
    reg = load_plugins(str(tmp_path))
    assert "my_method" in reg and "buy_and_hold" in reg and "slow_trend_multiasset" in reg and "slow_trend_simple" in reg
