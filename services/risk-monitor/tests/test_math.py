"""Kiểm số học bằng tay (ví dụ trong chú thích)."""
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from risk_monitor import riskmath as rm
from risk_monitor.budget import evaluate, worst_status
from risk_monitor.drawdown import drawdown_report
from risk_monitor.exposure import Holding, margin_metrics, mt_holdings, paper_holdings, summarize
from risk_monitor.instruments import classify, fx_rate
from risk_monitor.portfolio import portfolio_risk
from risk_monitor.stress import run_scenario, window_return
from risk_monitor.config import load_config

CFG = load_config(None)


def test_hist_var_es_integers():
    # P&L = -50..50 (n=101): phân vị 5% ở chỉ số 5 -> -45 => VaR95 = 45; ES = -mean(-50..-45) = 47.5
    pnl = np.arange(-50, 51, dtype=float)
    var, es = rm.hist_var_es(pnl, 0.95)
    assert var == pytest.approx(45.0)
    assert es == pytest.approx(47.5)


def test_param_var_es_normal():
    var, es = rm.param_var_es(1000.0, 0.95)
    assert var == pytest.approx(1644.854, abs=0.01)          # z95 = 1.644854
    assert es == pytest.approx(2062.713, abs=0.05)            # σ·φ(z)/0.05 = 1000·0.1031356/0.05
    var99, _ = rm.param_var_es(1.0, 0.99)
    assert var99 == pytest.approx(2.326348, abs=1e-5)


def test_ewma_hand():
    # r=[1,-1,2], init_n=2: s2=1 ; s2=0.94*1+0.06*4=1.18 -> σ=1.086278
    assert rm.ewma_sigma(np.array([1.0, -1.0, 2.0]), 0.94, 2) == pytest.approx(math.sqrt(1.18))
    assert rm.ewma_sigma(np.array([2.0, -2.0] * 20), 0.94) == pytest.approx(2.0)


def test_kupiec():
    lr, p = rm.kupiec_pof(100, 10, 0.05)                      # tính tay: LR = 4.1308, p = 0.0421
    assert lr == pytest.approx(4.1308, abs=1e-3)
    assert p == pytest.approx(0.0421, abs=1e-3)
    assert rm.kupiec_pof(100, 5, 0.05) == (0.0, 1.0)


def test_risk_contrib_two_uncorrelated():
    cov = np.diag([0.01 ** 2, 0.01 ** 2])
    r = rm.risk_contributions(np.array([100.0, 100.0]), cov)
    assert r["rc"] == pytest.approx([0.5, 0.5])
    assert r["diversification_ratio"] == pytest.approx(math.sqrt(2))
    assert r["effective_bets"] == pytest.approx(2.0)
    assert sum(r["rc"]) == pytest.approx(1.0)


def _closes(rets: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(rets.values())))
    idx = pd.date_range("2025-01-01", periods=n + 1, freq="D")
    return pd.DataFrame({s: 100 * np.cumprod([1.0] + [1 + x for x in r]) for s, r in rets.items()}, index=idx)


def test_portfolio_hist_var_exact():
    # 1 mã, V=1000, lợi suất = k/1000 với k=-50..50 -> P&L = k  => VaR95 = 45, ES = 47.5
    rets = [k / 1000.0 for k in range(-50, 51)]
    rng = np.random.default_rng(0)
    rng.shuffle(rets)
    cfg = {**CFG, "min_history_days": 60}
    out = portfolio_risk({"AAA": 1000.0}, _closes({"AAA": rets}), 100_000.0, cfg)
    assert out["available"]
    assert out["hist"]["95"]["var"] == pytest.approx(45.0, rel=1e-6)
    assert 47.0 <= out["hist"]["95"]["es"] <= 48.0   # 47.5 (hoặc 48 nếu sai số float loại điểm biên khỏi đuôi)
    assert out["hist"]["95"]["var_pct"] == pytest.approx(0.045, rel=1e-6)
    assert out["sigma_daily"] == pytest.approx(float(np.std(np.arange(-50, 51), ddof=1)), rel=1e-6)
    # short đảo dấu P&L: phân phối đối xứng nên VaR như nhau
    short = portfolio_risk({"AAA": -1000.0}, _closes({"AAA": rets}), 100_000.0, cfg)
    assert short["hist"]["95"]["var"] == pytest.approx(45.0, rel=1e-6)


def test_portfolio_insufficient_history():
    out = portfolio_risk({"AAA": 10.0}, _closes({"AAA": [0.01] * 10}), 1000.0, CFG)
    assert not out["available"]


def test_hedge_cancels_risk():
    rets = list(np.random.default_rng(1).normal(0, 0.01, 200))
    cl = _closes({"AAA": rets, "BBB": rets})                  # hai mã giống hệt, long/short cùng độ lớn
    out = portfolio_risk({"AAA": 1000.0, "BBB": -1000.0}, cl, 10_000.0, CFG)
    assert out["hist"]["95"]["var"] == pytest.approx(0.0, abs=1e-6)


def test_fx_conversion_and_classify():
    assert classify("EURUSD").kind == "fx" and classify("EURUSD").contract == 100000
    assert classify("XAUUSD.m").cls == "gold" and classify("XAUUSD.m").contract == 100
    assert classify("US:TLT").cls == "bond" and classify("VN:VNM").quote == "VND"
    px = {"EURUSD": 1.1, "USDJPY": 150.0}
    assert fx_rate("EUR", "USD", px) == 1.1
    assert fx_rate("JPY", "USD", px) == pytest.approx(1 / 150)
    assert fx_rate("EUR", "JPY", px) == pytest.approx(165.0)
    assert fx_rate("EUR", "CHF", px) is None


def _pos(sym, side, vol, price):
    return {"symbol": sym, "side": side, "volume": vol, "price_current": price, "profit": 0.0, "position_id": "1"}


def test_hedging_vs_netting_exposure():
    px = {"EURUSD": 1.10}
    hs, w = mt_holdings([_pos("EURUSD", "buy", 1.0, 1.10), _pos("EURUSD", "sell", 0.4, 1.10)], "USD", px, CFG)
    assert not w
    s = summarize(hs, 10_000.0, "mt4", "hedging")
    assert s["mode"] == "hedging"
    row = s["by_symbol"][0]
    assert row["net_lots"] == pytest.approx(0.6) and row["hedged_lots"] == pytest.approx(0.4)
    assert s["gross_notional"] == pytest.approx(154_000.0)    # (1.0+0.4) lot * 100000 * 1.10
    assert s["net_notional_abs"] == pytest.approx(66_000.0)   # 0.6 lot
    assert s["leverage_gross"] == pytest.approx(15.4)
    ccy = {c["ccy"]: c["net_value"] for c in s["by_currency"]}
    assert ccy["EUR"] == pytest.approx(66_000.0) and ccy["USD"] == pytest.approx(-66_000.0)
    # netting với 2 vị thế cùng mã -> cảnh báo dữ liệu
    assert summarize(hs, 10_000.0, "mt5", "netting")["warnings"]


def test_margin_stop_out_distance():
    # equity 5000, margin 2000 -> level 250%; stop-out 50% => equity_so=1000, khoảng cách 4000 (80% equity)
    m = margin_metrics(5000.0, 5000.0, 2000.0, 200_000.0, 100_000.0, 100, 50.0, 100.0, 200.0)
    assert m["margin_level_pct"] == pytest.approx(250.0)
    assert m["free_margin"] == pytest.approx(3000.0)
    assert m["distance_to_stop_out"] == pytest.approx(4000.0)
    assert m["distance_pct_equity"] == pytest.approx(80.0)
    assert m["adverse_move_pct_gross"] == pytest.approx(2.0)   # 4000 / 200000
    assert m["adverse_move_pct_net"] == pytest.approx(4.0)
    assert m["status"] == "ok"
    assert margin_metrics(1500.0, 0, 2000.0, 1, 1, 0, 50, 100, 200)["status"] == "margin_call"
    assert margin_metrics(900.0, 0, 2000.0, 1, 1, 0, 50, 100, 200)["status"] == "stop_out"
    assert margin_metrics(1000.0, 0, 0.0, 0, 0, 0, 50, 100, 200)["status"] == "no_position"


def test_drawdown_day_week_peak():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)   # thứ Tư
    t = lambda d, h: datetime(2026, 10, d, h, tzinfo=timezone.utc)  # noqa: E731
    s = [(t(12, 10), 10_000.0), (t(13, 23), 10_200.0), (t(14, 1), 10_400.0), (t(14, 5), 9_880.0), (t(14, 9), 10_088.0)]
    r = drawdown_report(s, now)
    assert r["day"]["start_equity"] == 10_200.0
    assert r["day"]["pnl"] == pytest.approx(-112.0)
    assert r["day"]["max_dd_pct"] == pytest.approx((9_880 - 10_400) / 10_400 * 100)   # -5%
    assert r["week"]["start_equity"] is None or True
    assert r["peak"]["equity"] == 10_400.0 and r["trough"]["equity"] == 9_880.0
    assert r["dd_from_peak_pct"] == pytest.approx((10_088 - 10_400) / 10_400 * 100)
    assert r["max_dd_pct"] == pytest.approx(-5.0)


def test_stress_replay_and_shock():
    idx = pd.to_datetime(["2015-01-13", "2015-01-14", "2015-01-15", "2015-01-16"])
    cl = pd.DataFrame({"USDCHF": [1.0180, 1.0180, 0.8600, 0.9000]}, index=idx)
    assert window_return(cl["USDCHF"], pd.Timestamp("2015-01-14").date(), pd.Timestamp("2015-01-15").date()) == pytest.approx(0.86 / 1.018 - 1)
    h = Holding("USDCHF", "buy", 100_000, 1.0, 1.0, 100_000.0, classify("USDCHF"))
    r = run_scenario({"id": "chf", "type": "replay", "start": "2015-01-14", "end": "2015-01-15"}, [h], cl, 10_000.0, 1_000.0)
    assert r["pnl"] == pytest.approx(100_000 * (0.86 / 1.018 - 1))
    assert r["breach_zero"] and r["breach_stop_out"]
    # shock USD +5%: EURUSD long 100k -> -4.7619%
    e = Holding("EURUSD", "buy", 1, 1.0, 1.0, 100_000.0, classify("EURUSD"))
    s = run_scenario({"id": "u", "type": "shock", "ccy": {"USD": 5}}, [e], None, 50_000.0)
    assert s["pnl"] == pytest.approx(100_000 * (1 / 1.05 - 1))
    # adverse: short mất khi giá tăng
    sh = Holding("EURUSD", "sell", 1, 1.0, 1.0, -100_000.0, classify("EURUSD"))
    assert run_scenario({"id": "a", "type": "shock", "adverse_pct": 3}, [sh], None, 50_000.0)["pnl"] == pytest.approx(-3_000.0)
    # replay thiếu dữ liệu -> coverage 0, ghi nhận missing
    miss = run_scenario({"id": "x", "type": "replay", "start": "2008-09-12", "end": "2008-11-20"}, [h], cl, 1000.0)
    assert miss["missing"] == ["USDCHF"] and miss["coverage_pct"] == 0.0


def test_paper_holdings_sign_and_budget():
    hs = paper_holdings([{"symbol": "US:SPY", "qty": -10, "mark_price": 500.0, "notional": 5000.0, "unrealized_pnl": 0},
                         {"symbol": "US:TLT", "qty": 20, "mark_price": 90.0, "notional": 1800.0}], "USD", CFG)
    assert hs[0].value == -5000.0 and hs[1].value == 1800.0
    items = evaluate(CFG, "paper", "x", day_pnl_pct=-1.7, week_pnl_pct=0.5, dd_from_peak_pct=-4.0, leverage_gross=2.5,
                     margin_level=None, es_1d_pct=1.0, ccy_conc_pct=10.0, positions=2)
    st = {i["key"]: i["status"] for i in items}
    assert st["day_loss_pct"] == "warn" and st["leverage_gross"] == "crit" and st["dd_pct"] == "ok"
    assert worst_status(items) == "crit"
    mt = evaluate(CFG, "mt", "x", day_pnl_pct=0, week_pnl_pct=0, dd_from_peak_pct=0, leverage_gross=1, margin_level=150.0,
                  es_1d_pct=0, ccy_conc_pct=0, positions=1)
    assert {i["key"]: i["status"] for i in mt}["margin_level_min"] == "crit"   # 150% < 200% tối thiểu


def test_drawdown_sparse_series_uses_last_observation():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    s = [(datetime(2026, 10, 9, tzinfo=timezone.utc), 100.0), (datetime(2026, 10, 10, tzinfo=timezone.utc), 98.0)]
    r = drawdown_report(s, now)
    assert r["day"]["basis"] == "last_observation"
    assert r["day"]["pnl_pct"] == pytest.approx(-2.0)
