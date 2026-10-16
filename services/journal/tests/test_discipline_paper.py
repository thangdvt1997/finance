from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import dt, mk
from tscommon import risk_windows as rw

from journal import discipline, excursions
from journal.paper import fills_to_trades

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def rules(res: dict) -> dict[str, list[str]]:
    return res["tickets"]


def test_reentry_and_size_up_after_loss():
    rows = [
        mk(1, to=dt(1, 10), tc=dt(1, 10, 30), profit=-10, vol=0.1, sl=1.09),         # thua
        mk(2, to=dt(1, 10, 45), tc=dt(1, 11, 30), profit=5, vol=0.2, sl=1.09),         # 15 phut sau thua, x2 khoi luong
        mk(3, to=dt(1, 13), tc=dt(1, 14), profit=5, vol=0.2, sl=1.09),                 # xa hon 30 phut -> sach
    ]
    d = discipline.check(rows, VN)
    assert rules(d) == {"2": ["reentry_after_loss", "size_up_after_loss"]}
    assert d["n_flagged"] == 1 and d["score"] == pytest.approx(66.7, abs=0.05)
    assert d["net_flagged"] == 5.0 and d["net_clean"] == -5.0
    # khong tang khoi luong -> chi reentry
    rows[1].volume = 0.1
    assert rules(discipline.check(rows, VN)) == {"2": ["reentry_after_loss"]}


def test_averaging_down_only_when_price_is_worse_and_earlier_open():
    rows = [
        mk(1, to=dt(1, 8), tc=dt(1, 12), po=1.1000, pc=1.1010, profit=1, sl=1.09),
        mk(2, to=dt(1, 9), tc=dt(1, 11), po=1.0950, pc=1.1000, profit=1, sl=1.09),   # buy thap hon khi lenh 1 con mo -> nhoi lenh
        mk(3, to=dt(1, 9, 30), tc=dt(1, 10), po=1.1050, pc=1.1060, profit=1, sl=1.09),  # gia cao hon -> pyramiding, khong co
        mk(4, to=dt(1, 9, 40), tc=dt(1, 10), side="sell", po=1.1100, pc=1.1090, profit=1, sl=1.12),  # khac huong
    ]
    assert rules(discipline.check(rows, VN)) == {"2": ["averaging_down"]}
    s = [mk(1, side="sell", to=dt(1, 8), tc=dt(1, 12), po=1.1000, sl=1.12), mk(2, side="sell", to=dt(1, 9), tc=dt(1, 11), po=1.1050, sl=1.12)]
    assert rules(discipline.check(s, VN)) == {"2": ["averaging_down"]}  # sell o gia cao hon = xau hon


def test_overtrading_day_and_hour_and_no_sl():
    day = [mk(i, to=dt(1, 8) + timedelta(minutes=i * 70), tc=dt(1, 8) + timedelta(minutes=i * 70 + 10), profit=1, sl=1.09) for i in range(12)]
    d = discipline.check(day, ZoneInfo("UTC"))  # tz UTC de 12 lenh cung 1 ngay
    assert sorted(rules(d)) == ["10", "11"] and all(v == ["overtrading_day"] for v in d["tickets"].values())
    burst = [mk(i, to=dt(1, 8, i), tc=dt(1, 8, i + 1), profit=1, sl=1.09) for i in range(7)]  # 7 lenh trong 7 phut
    assert rules(discipline.check(burst, VN)) == {"5": ["overtrading_hour"], "6": ["overtrading_hour"]}
    assert rules(discipline.check([mk(1, sl=0.0)], VN)) == {"1": ["no_sl"]}
    assert discipline.check([mk(1, sl=0.0)], VN, params={"require_sl": False})["n_flagged"] == 0


def test_news_window_flag_uses_risk_windows():
    cfg = rw.load_config()
    ev = [{"event_id": "nfp", "source": "ff", "country": "US", "title": "Non-Farm Employment Change", "impact": "high", "ts": dt(2, 12, 30), "extra": None}]
    near = mk(1, to=dt(2, 12, 25), tc=dt(2, 12, 40), po=1.1, sl=1.09)       # 5 phut truoc tin: trong cua so
    far = mk(2, to=dt(2, 15), tc=dt(2, 16), sl=1.09)                           # 2.5 gio sau
    other = mk(3, to=dt(2, 12, 25), tc=dt(2, 12, 40), symbol="AUDNZD", sl=1.09)  # khong phoi nhiem USD
    d = discipline.check([near, far, other], VN, events=ev, rw_cfg=cfg)
    assert rules(d) == {"1": ["news_window"]}
    assert d["flagged"][0]["flags"][0]["event"].startswith("Non-Farm") and d["flagged"][0]["flags"][0]["min_from_event"] == -5


def test_daily_loss_breach_needs_base_equity():
    rows = [mk(1, profit=-400, to=dt(1, 8), tc=dt(1, 9), sl=1.09), mk(2, profit=-200, to=dt(1, 10), tc=dt(1, 11), sl=1.09)]
    assert discipline.check(rows, VN, base_equity=10000)["day_breaches"][0]["net"] == -600.0  # han muc 3% = -300
    assert discipline.check(rows, VN)["day_breaches"] == []


# ---------------- paper fills -> trades ----------------
def fill(i, side, qty, price, ts, real=0.0, comm=0.0, tax=0.0, sp=0.0, sl=0.0, sym="SPY"):
    return dict(fill_id=i, symbol=sym, side=side, qty=qty, price=price, ts=ts, realized_pnl=real, commission=comm, tax=tax, spread_cost=sp, slippage_cost=sl)


def test_paper_partial_closes_allocate_costs_pro_rata():
    fills = [fill(1, "buy", 10, 100, dt(1, 10), comm=1.0, sp=2.0),
             fill(2, "sell", 4, 110, dt(2, 10), real=40.0, comm=0.5),
             fill(3, "sell", 6, 120, dt(3, 10), real=120.0, comm=0.5)]
    ts = fills_to_trades(fills, account_id="p1", strategy="trend")
    assert [t.ticket for t in ts] == ["P2", "P3"] and [t.volume for t in ts] == [4, 6]
    assert ts[0].side == "buy" and ts[0].price_open == 100 and ts[0].price_close == 110 and ts[0].profit == 40.0
    assert ts[0].commission == pytest.approx(-(1.0 * 0.4 + 0.5)) and ts[1].commission == pytest.approx(-(1.0 * 0.6 + 0.5))
    assert ts[0].spread_cost == pytest.approx(0.8) and ts[1].spread_cost == pytest.approx(1.2)
    assert ts[0].time_open == dt(1, 10) == ts[1].time_open and ts[1].group == "trend" and ts[0].source == "paper:p1"
    assert sum(t.commission for t in ts) == pytest.approx(-(1.0 + 0.5 + 0.5))  # tong phi duoc bao toan


def test_paper_reversal_opens_new_leg_and_short_profit():
    fills = [fill(1, "buy", 5, 100, dt(1, 10)),
             fill(2, "sell", 8, 90, dt(2, 10), real=-50.0, comm=0.8),     # dong 5 long (lo 50), mo short 3 @90
             fill(3, "buy", 3, 80, dt(3, 10), real=30.0)]
    ts = fills_to_trades(fills, account_id="p1")
    assert [(t.side, t.volume, t.profit) for t in ts] == [("buy", 5, -50.0), ("sell", 3, 30.0)]
    assert ts[1].price_open == 90 and ts[1].time_open == dt(2, 10)
    assert ts[0].commission == pytest.approx(-0.5) and ts[1].commission == pytest.approx(-0.3)  # 0.8 chia 5/8 : 3/8


# ---------------- MAE / MFE ----------------
def test_excursion_long_and_short():
    t = mk(1, side="buy", po=1.1000, pc=1.1020, to=dt(1, 8, 0), tc=dt(1, 8, 4), sl=1.0990, profit=20)
    bars = [{"ts": dt(1, 8, m), "h": h, "l": l} for m, h, l in [(0, 1.1010, 1.0995), (1, 1.1030, 1.1000), (2, 1.1025, 1.1015), (3, 1.1022, 1.1018), (9, 9.0, 0.1)]]
    e = excursions.excursion(t, bars, "M1")
    assert e["bars"] == 4  # nen 8:09 nam ngoai lenh
    assert e["mfe"] == pytest.approx(0.0030) and e["mae"] == pytest.approx(0.0005)
    assert e["mae_r"] == pytest.approx(0.5) and e["mfe_r"] == pytest.approx(3.0)
    assert e["capture"] == pytest.approx(0.0020 / 0.0030, abs=1e-3)
    s = mk(2, side="sell", po=1.1000, pc=1.0990, to=dt(1, 8, 0), tc=dt(1, 8, 2), profit=10)
    e2 = excursions.excursion(s, bars, "M1")
    assert e2["mfe"] == pytest.approx(0.0005) and e2["mae"] == pytest.approx(0.0030) and e2["mae_r"] is None
    assert excursions.excursion(t, [], "M1") is None
    assert excursions.pick_tf(600) == "M1" and excursions.pick_tf(86400) == "M5" and excursions.pick_tf(5 * 86400) == "H1"
