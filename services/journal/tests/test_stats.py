"""So hoc tay: profit factor, expectancy, drawdown, R, chuoi, ... tren tap lenh nho de kiem tra bang tay."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from conftest import dt, five_trades, mk

from journal import stats

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def test_summary_hand_computed():
    s = stats.summarize(five_trades())
    # net: 100, -50, 30, -20, 60 -> tong 120; thang 3 (190), thua 2 (70)
    assert s["n"] == 5 and s["wins"] == 3 and s["losses"] == 2 and s["breakeven"] == 0
    assert s["net"] == 120.0 and s["gross_profit"] == 190.0 and s["gross_loss"] == 70.0
    assert s["win_rate"] == 0.6
    assert s["profit_factor"] == pytest.approx(190 / 70, abs=1e-4)  # 2.7143
    assert s["expectancy"] == 24.0  # 120/5 == 0.6*63.333 - 0.4*35
    assert s["avg_win"] == pytest.approx(63.33, abs=0.01) and s["avg_loss"] == 35.0
    assert s["payoff"] == pytest.approx(63.3333 / 35, abs=1e-3)
    assert s["best"] == 100.0 and s["worst"] == -50.0


def test_net_includes_swap_and_commission():
    t = mk(1, profit=100, swap=-3, comm=-2)
    assert t.net == 95.0
    assert stats.summarize([mk(2, profit=2, comm=-3)])["losses"] == 1  # lai gop 2 nhung phi 3 -> net -1 = thua


def test_profit_factor_none_without_losses_and_empty():
    assert stats.summarize([mk(1, profit=10)])["profit_factor"] is None
    e = stats.summarize([])
    assert e["n"] == 0 and e["win_rate"] is None and e["net"] == 0.0


def test_breakeven_not_counted_as_win():
    s = stats.summarize([mk(1, profit=10), mk(2, profit=0), mk(3, profit=-5)])
    assert s["breakeven"] == 1 and s["win_rate"] == pytest.approx(1 / 3, abs=1e-4)


def test_equity_curve_and_max_drawdown():
    c = stats.equity_curve(five_trades(), base=1000.0)
    # theo thoi gian dong: 1100, 1050, 1080, 1060, 1120 -> dinh 1100; DD toi da 50 (4.5455%)
    assert [p["equity"] for p in c["points"]] == [1100.0, 1050.0, 1080.0, 1060.0, 1120.0]
    assert c["max_dd"] == 50.0 and c["max_dd_pct"] == pytest.approx(50 / 1100 * 100, abs=1e-3)
    assert c["start"] == 1000.0 and c["end"] == 1120.0 and c["current_dd"] == 0.0
    assert c["max_dd_from"].startswith("2026-10-01T09") and c["max_dd_to"].startswith("2026-10-01T11")


def test_deposit_and_withdrawal_do_not_count_as_drawdown():
    rows = [mk(1, profit=100, to=dt(1, 8), tc=dt(1, 9)),
            mk(2, kind="balance", side="balance", profit=-500, to=dt(1, 10), tc=dt(1, 10), symbol=""),  # rut 500
            mk(3, profit=-20, to=dt(1, 11), tc=dt(1, 12)),
            mk(4, kind="balance", side="balance", profit=300, to=dt(1, 13), tc=dt(1, 13), symbol="")]  # nap 300
    c = stats.equity_curve(rows, base=1000.0)
    assert [p["equity"] for p in c["points"]] == [1100.0, 600.0, 580.0, 880.0]
    assert c["max_dd"] == 20.0  # chi lenh -20 gay DD, khong phai rut 500


def test_equity_curve_unknown_base_has_no_pct():
    c = stats.equity_curve(five_trades(), base=None)
    assert c["max_dd"] == 50.0 and c["max_dd_pct"] is None


def test_streaks():
    nets = [10, 5, 7, -3, -4, 0, -1, 2]
    rows = [mk(i, profit=n, to=dt(1, 1, i), tc=dt(1, 2, i)) for i, n in enumerate(nets)]
    st = stats.streaks(rows)
    assert st["max_win_streak"] == 3 and st["max_loss_streak"] == 2  # hoa ngat chuoi: -1 chi la chuoi 1
    assert st["current"] == {"type": "win", "len": 1}
    assert st["worst_loss_run"] == -7.0


def test_r_multiple_by_price():
    b = mk(1, side="buy", po=1.1000, pc=1.1030, sl=1.0990)
    s = mk(2, side="sell", po=1.2000, pc=1.2020, sl=1.2010)
    assert b.r_multiple == pytest.approx(3.0) and s.r_multiple == pytest.approx(-2.0)
    assert mk(3, sl=0.0).r_multiple is None
    d = stats.r_distribution([b, s, mk(3)])
    assert d["n"] == 2 and d["avg"] == pytest.approx(0.5) and d["pct_with_sl"] == pytest.approx(66.7, abs=0.05)
    assert sum(x["n"] for x in d["bins"]) == 2


def test_hold_and_costs():
    rows = [mk(1, to=dt(1, 8), tc=dt(1, 8, 4), profit=10, comm=-1, swap=-1), mk(2, to=dt(1, 9), tc=dt(1, 12), profit=-5, comm=-1)]
    h = stats.hold_stats(rows)
    assert h["avg_s"] == (240 + 10800) // 2 and h["avg_win_s"] == 240 and h["avg_loss_s"] == 10800
    assert {b["bucket"]: b["n"] for b in h["buckets"]}["<5m"] == 1
    c = stats.costs(rows)
    assert c["commission"] == -2.0 and c["swap"] == -1.0 and c["gross_profit_before_costs"] == 5.0
    assert c["costs_pct_of_gross"] == pytest.approx(3 / 5 * 100)


def test_groups_hour_weekday_session_and_calendar_use_tz():
    # 2026-10-01 (thu 5) 18:30 UTC = 01:30 gio VN ngay 10-02; lenh vao 08:00 UTC = 15:00 VN
    t1 = mk(1, to=dt(1, 8), tc=dt(1, 18, 30), profit=10)
    t2 = mk(2, to=dt(1, 8, 30), tc=dt(1, 9), profit=-4, magic=5, symbol="XAUUSD", side="sell")
    g = stats.groups([t1, t2], VN)
    assert [r["key"] for r in g["hour"]] == [15] and g["hour"][0]["n"] == 2
    assert g["weekday"][0]["label"] == "T5" and g["weekday"][0]["n"] == 2
    assert g["session"][0]["key"] == "london" and g["session"][0]["n"] == 2
    assert {r["key"]: r["net"] for r in g["symbol"]} == {"EURUSD": 10.0, "XAUUSD": -4.0}
    cal = stats.calendar_days([t1, t2], VN)
    assert cal == [{"date": "2026-10-01", "net": -4.0, "n": 1, "wins": 0, "losses": 1}, {"date": "2026-10-02", "net": 10.0, "n": 1, "wins": 1, "losses": 0}]
    contrib = stats.contribution([t1, t2])
    assert {r["ea"]: r["share_pct"] for r in contrib} == {"manual": pytest.approx(166.67, abs=0.01), "magic:5": pytest.approx(-66.67, abs=0.01)}


def test_week_helpers():
    assert stats.iso_week_label(dt(12), VN) == "2026-W42"
    a, b = stats.week_range("2026-W42", VN)
    assert a.isoformat() == "2026-10-11T17:00:00+00:00" and (b - a).days == 7  # T2 12/10 00:00 VN


def test_contribution_share_is_none_when_total_near_zero():
    rows = stats.contribution([mk(1, profit=100, magic=1), mk(2, profit=-99, magic=2)])  # tong 1 << tong |net| 199
    assert all(r["share_pct"] is None for r in rows)
    assert {r["ea"]: r["abs_share_pct"] for r in rows} == {"magic:1": pytest.approx(50.25, abs=0.01), "magic:2": pytest.approx(49.75, abs=0.01)}
