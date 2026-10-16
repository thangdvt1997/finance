from __future__ import annotations

from datetime import timedelta

from conftest import T0, walk
from track_record.pricing import PriceBook


def book(n=200, seed=1):
    return PriceBook.build({"EURUSD": walk(n, seed)})


def test_entry_is_open_of_first_candle_starting_after_observed():
    pb = book()
    obs = T0 + timedelta(days=10, hours=5)             # giua nen ngay 10
    f = pb.fill("EURUSD", obs, "1D")
    assert f.entry_ts == T0 + timedelta(days=11)       # KHONG dung nen chua observed_at
    assert f.entry_px == pb.series["EURUSD"].o[11] and f.exit_px == pb.series["EURUSD"].c[11]
    f0 = pb.fill("EURUSD", T0 + timedelta(days=10), "1D")   # dung ts_open: van phai la nen SAU
    assert f0.entry_ts == T0 + timedelta(days=11)


def test_horizons_use_kth_candle_from_entry():
    pb = book()
    s = pb.series["EURUSD"]
    obs = T0 + timedelta(days=20, hours=1)
    assert pb.fill("EURUSD", obs, "1W").exit_px == s.c[21 + 4]
    assert pb.fill("EURUSD", obs, "1M").exit_px == s.c[21 + 20]


def test_pending_when_not_enough_candles():
    pb = book(30)
    assert pb.fill("EURUSD", T0 + timedelta(days=15), "1M") == "pending"
    assert pb.fill("EURUSD", T0 + timedelta(days=15), "1D") != "pending"
    assert pb.fill("EURUSD", T0 + timedelta(days=40), "1D") == "pending"
    assert pb.fill("NOPE", T0, "1D") is None


def test_no_lookahead_future_prices_dont_change_result():
    a, b = book(200), book(200)
    obs = T0 + timedelta(days=50, hours=3)
    fa = a.fill("EURUSD", obs, "1W")
    exit_idx = 51 + 4
    sb = b.series["EURUSD"]
    for i in range(exit_idx + 1, 200):                 # pha huy moi gia SAU nen thoat
        sb.o[i] *= 3
        sb.c[i] *= 0.2
    fb = b.fill("EURUSD", obs, "1W")
    assert fa.ret_log == fb.ret_log and fa.entry_px == fb.entry_px
    sb.o[50] *= 2                                      # nen CHUA observed_at (nen 50) khong anh huong entry/exit
    sb.c[50] *= 2
    assert b.fill("EURUSD", obs, "1W").ret_log == fa.ret_log


def test_regime_uses_only_closed_candles_before_observed():
    a, b = book(300), book(300)
    obs = T0 + timedelta(days=200, hours=4)
    ra = a.regime("EURUSD", obs)
    sb = b.series["EURUSD"]
    for i in range(200, 300):                          # nen 200 tro di: chua dong tai observed
        sb.c[i] *= 5
        sb.o[i] *= 5
    sb._vol = None
    assert ra in ("trend", "range", "high_vol", "low_vol") and b.regime("EURUSD", obs) == ra
    assert a.regime("EURUSD", T0 + timedelta(days=10)) is None


def test_proxy_symbol():
    pb = PriceBook.build({"US:SPY": walk(100, 3)})
    assert pb.has("US:SPX") and not pb.has("US:XYZ")
