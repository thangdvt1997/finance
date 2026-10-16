"""Test mo phong backtest Kich ban Sell (khong can du lieu that)."""
import numpy as np
import pytest

from pattern_research.backtest import (Bars, deflated_sharpe, max_drawdown, p_value_vs_random, random_baseline,
                                       simulate_sell, summarize, wilder_atr)


def mk(o, h, l, c, symbol="ZZZ", zero_cost=True):
    n = len(o)
    ts = np.arange(n).astype("datetime64[h]")
    return Bars.from_arrays(symbol, "H1", ts, o, h, l, c, None, zero_cost)


def flat(n=20, p=100.0):
    return [p] * n, [p + 0.5] * n, [p - 0.5] * n, [p] * n


def test_tp_hit():
    o, h, l, c = flat()
    l[5] = 90.0
    tr = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=50)
    assert tr.outcome == "tp" and tr.exit_i == 5 and tr.r == pytest.approx(2.0)


def test_sl_hit_and_same_bar_is_pessimistic():
    o, h, l, c = flat()
    h[6], l[6] = 103.0, 90.0                     # cung nen cham SL va TP -> SL
    tr = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=50)
    assert tr.outcome == "sl" and tr.exit_i == 6 and tr.r == pytest.approx(-1.0)


def test_gap_through_sl_fills_at_open():
    o, h, l, c = flat()
    o[6], h[6], l[6], c[6] = 105.0, 106.0, 104.0, 105.0
    tr = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=50)
    assert tr.outcome == "sl" and tr.r == pytest.approx(-2.5)


def test_entry_open_above_sl_is_skipped():
    o, h, l, c = flat()
    assert simulate_sell(mk(o, h, l, c), 3, sl=99.0, tp_r=2.0, max_hold=50) is None


def test_time_exit_and_end_of_data():
    o, h, l, c = flat()
    tr = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=5)
    assert tr.outcome == "time" and tr.exit_i == 7 and tr.r == pytest.approx(0.0)
    tr = simulate_sell(mk(o, h, l, c), 17, sl=102.0, tp_r=2.0, max_hold=50)
    assert tr.outcome == "end" and tr.exit_i == 19


def test_costs_reduce_r_and_sl_triggers_on_ask():
    o, h, l, c = flat()
    l[5] = 90.0
    gross = simulate_sell(mk(o, h, l, c, "EURUSD", True), 3, sl=102.0, tp_r=2.0, max_hold=50)
    o2, h2, l2, c2 = flat(p=1.1)
    b = mk(o2, h2, l2, c2, "EURUSD", zero_cost=False)
    assert b.spread[0] == pytest.approx(0.0001)
    # SL 1.1004 + ask: high bid 1.6? -> dung chuoi rieng nho
    o3 = [1.1] * 10; h3 = [1.1002] * 10; l3 = [1.0998] * 10; c3 = [1.1] * 10
    h3[5] = 1.10035                                 # bid chua cham SL 1.1004 nhung ask = +1 pip -> cham
    tr = simulate_sell(mk(o3, h3, l3, c3, "EURUSD", zero_cost=False), 2, sl=1.1004, tp_r=2.0, max_hold=50)
    assert tr.outcome == "sl" and tr.r < -1.0
    assert gross.r > 0


def test_future_bars_do_not_change_closed_trade():
    o, h, l, c = flat(40)
    l[5] = 90.0
    a = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=50)
    h[30] = 500.0
    b = simulate_sell(mk(o, h, l, c), 3, sl=102.0, tp_r=2.0, max_hold=50)
    assert a.r == b.r and a.exit_i == b.exit_i


def test_wilder_atr_matches_engine_series():
    pe = pytest.importorskip("pattern_engine.series")
    from datetime import datetime, timedelta, timezone
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(300)
    l = np.minimum(o, c) - rng.random(300)
    s = pe.Series(14)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(300):
        s.append(pe.Bar(t0 + timedelta(hours=i), o[i], h[i], l[i], c[i]))
    assert np.allclose(wilder_atr(h, l, c), s.atr)


def test_random_baseline_reproducible_and_pvalue():
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 2000))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(2000)
    l = np.minimum(o, c) - rng.random(2000)
    b = mk(o, h, l, c)
    d = np.array([1.0, 1.5, 2.0, 1.2])
    r1 = random_baseline(b, d, 100, 1800, 2.0, 50, n_seeds=20, seed=9)
    r2 = random_baseline(b, d, 100, 1800, 2.0, 50, n_seeds=20, seed=9)
    assert r1.shape == (20, 4) and np.array_equal(r1, r2, equal_nan=True)
    p, m = p_value_vs_random(10.0, r1)
    assert p == pytest.approx(1 / 21, abs=1e-4)
    p, _ = p_value_vs_random(-10.0, r1)
    assert p == 1.0


def test_summary_and_drawdown():
    rs = np.array([1, -1, -1, 2, -1, 3.0])
    s = summarize(rs)
    assert s["n"] == 6 and s["win"] == pytest.approx(0.5) and s["pf"] == pytest.approx(2.0) and s["max_lose_streak"] == 2
    assert max_drawdown(np.array([1, -1, -1, 2])) == 2
    d = deflated_sharpe(np.r_[rs, rs, rs], n_trials=8)
    assert d["dsr"] <= d["psr0"]


def test_pbo_cscv_noise_vs_true_skill():
    from pattern_research.backtest import pbo_cscv
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, (64, 8))
    assert 0.3 <= pbo_cscv(noise, 8)["pbo"] <= 0.8          # cau hinh vo dung: chon IS ~ ngau nhien OOS
    skill = noise.copy()
    skill[:, 3] += 1.5                                        # 1 cau hinh tot that
    assert pbo_cscv(skill, 8)["pbo"] < 0.05
