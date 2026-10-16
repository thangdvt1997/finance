"""Risk engine chặn đúng + sizing + chiến lược mẫu."""
from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from paper_trader.market import frame_from_rows
from paper_trader.models import Order, Targets
from paper_trader.risk import RiskConfig, RiskEngine, blocked_symbols
from paper_trader.strategy import StrategyContext, build

from .conftest import DAY, START, rows_from_closes


def eng(**over):
    return RiskEngine(RiskConfig.build(over))


def test_gate_whitelist_short_cap_leverage():
    r = eng(whitelist=["A", "B", "C"], max_weight=0.4, max_leverage=1.0).gate(
        {"A": 0.9, "B": -0.8, "C": -0.3, "Z": 0.2}, ["A", "B", "C", "Z"], {"A": True, "B": True, "C": False})
    codes = {(n["code"], n.get("symbol")) for n in r.notes}
    assert ("not_whitelisted", "Z") in codes and ("short_not_allowed", "C") in codes and ("max_weight", "A") in codes and ("max_weight", "B") in codes
    # A=+0.4, B=-0.4, C=0 -> gross 0.8 <= 1 : không scale
    assert r.weights == {"A": 0.4, "B": -0.4, "C": 0.0}
    r2 = eng(max_weight=1.0, max_leverage=1.0).gate({"A": 0.8, "B": 0.8}, ["A", "B"], {})
    assert sum(abs(x) for x in r2.weights.values()) == pytest.approx(1.0) and r2.weights["A"] == pytest.approx(0.5)


def test_account_breaches_priority_and_thresholds():
    e = eng(max_daily_loss=0.03, max_weekly_loss=0.06, max_drawdown=0.15)
    assert e.check_account(10_000, 10_000, 10_000, 10_000) is None
    b = e.check_account(9_650, 10_000, 10_000, 10_000)                         # -3.5% ngày
    assert b.kind == "daily" and not b.hard
    b = e.check_account(9_300, 10_000, 9_600, 10_000)                          # tuần -7%, ngày -3,1%: tuần ưu tiên
    assert b.kind == "weekly" and not b.hard
    b = e.check_account(8_400, 10_000, 8_500, 8_500)                           # DD -16% -> khoá cứng
    assert b.kind == "drawdown" and b.hard
    assert e.check_account(8_501, 10_000, 8_501, 8_501) is None                # -14,99% còn trong giới hạn


def test_order_rate_limit_and_news_window_block_increases_only():
    e = eng(max_orders_per_minute=2)
    mk = lambda s, side, q, i: Order(f"c{i}", "a", s, side, q, START, START)    # noqa: E731
    orders = [mk("A", "buy", 10, 1), mk("B", "buy", 10, 2), mk("C", "sell", 5, 3)]
    ok, rej = e.filter_orders(orders, {"C": 10.0}, {})
    assert [o.symbol for o in ok] == ["C", "A"] and [(o.symbol, why) for o, why in rej] == [("B", "rate_limit")]   # lệnh giảm rủi ro được ưu tiên
    ok, rej = eng().filter_orders([mk("EURUSD", "buy", 10, 1), mk("EURUSD", "sell", 5, 2)], {"EURUSD": 8.0}, {"EURUSD": "NFP"})
    assert [o.client_order_id for o in ok] == ["c2"] and rej[0][1] == "risk_window:NFP"          # sell 5 từ 8 = giảm -> cho phép; buy tăng -> chặn


def test_blocked_symbols_window_edges():
    t = START + timedelta(hours=13, minutes=30)
    w = [{"start": t, "end": t + timedelta(minutes=5), "currencies": ["USD"], "title": "NFP"}]
    sym = ["EURUSD", "GBPJPY", "VN:FPT"]
    f = lambda ts: blocked_symbols(w, sym, ts, 15, 30, __import__("paper_trader.portfolio", fromlist=["x"]).symbol_ccys)  # noqa: E731
    assert f(t - timedelta(minutes=16)) == {}
    assert set(f(t - timedelta(minutes=14))) == {"EURUSD"}                    # T-15
    assert set(f(t + timedelta(minutes=34))) == {"EURUSD"}
    assert f(t + timedelta(minutes=36)) == {}


def _hist(closes_by_sym):
    return {s: frame_from_rows(rows_from_closes(c, spread=0.0)) for s, c in closes_by_sym.items()}


def test_vol_target_single_asset_hits_target():
    rng = np.random.default_rng(3)
    c = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 120))))
    h = _hist({"X": c})
    e = RiskEngine(RiskConfig.build({"sizing": {"mode": "vol_target", "target_vol": 0.10, "vol_window": 60, "max_scale": 10.0}}))
    r = e.size(Targets(weights={"X": 1.0}, kind="conviction"), h)
    sigma = float(np.log(pd.Series(c)).diff().tail(60).std(ddof=1) * math.sqrt(252))
    assert r.weights["X"] == pytest.approx(0.10 / sigma, rel=1e-6)
    short = e.size(Targets(weights={"X": -1.0}, kind="conviction"), h)
    assert short.weights["X"] == pytest.approx(-0.10 / sigma, rel=1e-6)
    flat = e.size(Targets(weights={"X": 0.0}, kind="conviction"), h)
    assert flat.weights["X"] == 0.0


def test_vol_target_portfolio_vol_equals_target_and_scale_cap():
    rng = np.random.default_rng(5)
    h = _hist({"A": list(100 * np.exp(np.cumsum(rng.normal(0, 0.012, 150)))), "B": list(50 * np.exp(np.cumsum(rng.normal(0, 0.006, 150))))})
    e = RiskEngine(RiskConfig.build({"sizing": {"mode": "vol_target", "target_vol": 0.10, "vol_window": 100, "max_scale": 50.0}}))
    w = e.size(Targets(weights={"A": 1.0, "B": 1.0}, kind="conviction"), h).weights
    rets = pd.DataFrame({s: np.log(h[s]["c"]).diff() for s in h}).tail(100).dropna()
    cov = rets.cov().to_numpy() * 252
    vec = np.array([w["A"], w["B"]])
    assert math.sqrt(vec @ cov @ vec) == pytest.approx(0.10, rel=1e-6)
    capped = RiskEngine(RiskConfig.build({"sizing": {"mode": "vol_target", "target_vol": 0.10, "vol_window": 100, "max_scale": 0.01}}))
    wc = capped.size(Targets(weights={"A": 1.0, "B": 1.0}, kind="conviction"), h).weights
    assert wc["A"] < w["A"]


def test_atr_risk_sizing_hand_calc():
    rows = [{"ts_open": START + DAY * i, "o": 100, "h": 102, "l": 98, "c": 100, "v": 1} for i in range(30)]
    h = {"X": frame_from_rows(rows)}
    e = RiskEngine(RiskConfig.build({"sizing": {"mode": "atr_risk", "atr_days": 14, "atr_mult": 2.0, "risk_per_trade": 0.01}}))
    w = e.size(Targets(weights={"X": 1.0}, kind="conviction"), h).weights["X"]
    # ATR = 4 ; weight = 0.01 * 100 / (2*4) = 0.125
    assert w == pytest.approx(0.125)


# ------------------------------------------------------------------ chiến lược mẫu
def ctx(history, equity=10_000.0, params=None):
    return StrategyContext(now=START + DAY * 1000, tf="D1", universe=tuple(history), history=history, equity=equity, positions={}, params=params or {})


def test_slow_trend_signals_up_down_flat_and_ma_filter():
    n = 300
    up = [100 + 0.2 * i for i in range(n)]
    down = [200 - 0.2 * i for i in range(n)]
    # giá hồi mạnh cuối chuỗi: momentum 12-1 dương nhưng giá < MA200 -> đứng ngoài
    dip = [100 + 0.3 * i for i in range(n - 30)] + [100 + 0.3 * (n - 30) - 3.0 * j for j in range(1, 31)]
    s = build("slow_trend_simple", {"allow_short": True})
    t = s.targets(ctx(_hist({"UP": up, "DN": down, "DIP": dip})))
    assert t.kind == "conviction" and t.weights["UP"] == 1.0 and t.weights["DN"] == -1.0
    mom = dip[-22] / dip[-22 - 252] - 1
    assert mom > 0 and dip[-1] < float(np.mean(dip[-200:])) and t.weights["DIP"] == 0.0
    long_only = build("slow_trend_simple", {"allow_short": False}).targets(ctx(_hist({"DN": down})))
    assert long_only.weights["DN"] == 0.0
    assert s.required_history == 274


def test_slow_trend_warming_up_when_short_history():
    t = build("slow_trend_simple", {}).targets(ctx(_hist({"A": [1.0 + 0.01 * i for i in range(100)]})))
    assert t.status == "warming_up" and t.meta["have_bars"] == {"A": 100} and t.meta["need_bars"] == 274


def test_buy_and_hold_equal_weight_and_explicit_weights():
    h = _hist({"A": [1, 1], "B": [1, 1], "C": [1, 1], "D": [1, 1]})
    assert build("buy_and_hold", {"gross": 1.0}).targets(ctx(h)).weights == {k: 0.25 for k in "ABCD"}
    assert build("buy_and_hold", {"weights": {"A": 0.6, "B": 0.4}}).targets(ctx(h)).weights == {"A": 0.6, "B": 0.4}
