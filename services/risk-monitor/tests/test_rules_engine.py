from datetime import datetime, timedelta, timezone

import pytest

from risk_monitor.rules_engine import day_bounds, evaluate, resolve_tz

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def T(day: int, h: int = 0, m: int = 0, mon: int = 10) -> datetime:
    return datetime(2026, mon, day, h, m, tzinfo=timezone.utc)


def snap(eq=10_000.0, margin=0.0, **kw):
    return {"equity": eq, "balance": eq, "margin": margin, **kw}


# ---------- múi giờ / mốc reset ----------
def test_resolve_tz_variants():
    assert resolve_tz("UTC+3")[0].utcoffset(None) == timedelta(hours=3)
    assert resolve_tz("utc-5:30")[0].utcoffset(None) == -timedelta(hours=5, minutes=30)
    assert resolve_tz(None)[0] is timezone.utc
    tz, note = resolve_tz("Khong/Co")
    assert tz is timezone.utc and note
    assert resolve_tz("Asia/Ho_Chi_Minh")[0].utcoffset(NOW) == timedelta(hours=7)   # IANA hoặc offset dự phòng đều ra +7


def test_day_bounds_utc3_boundary():
    tz = resolve_tz("UTC+3")[0]
    # 20:59Z = 23:59 địa phương: vẫn ngày 14 (mốc 21:00Z của hôm 13)
    s, n = day_bounds(T(14, 20, 59), tz, 0)
    assert s == T(13, 21) and n == T(14, 21)
    # 21:00Z = 00:00 địa phương: sang ngày mới
    s, n = day_bounds(T(14, 21, 0), tz, 0)
    assert s == T(14, 21) and n == T(15, 21)


def test_day_bounds_reset_hour():
    s, n = day_bounds(T(14, 3), timezone.utc, 5)           # trước 05:00 -> ngày bắt đầu 05:00 hôm trước
    assert s == T(13, 5) and n == T(14, 5)
    s, _ = day_bounds(T(14, 6), timezone.utc, 5)
    assert s == T(14, 5)


# ---------- daily_loss ----------
DL = {"limit_pct": 5, "basis": "day_start_equity", "tz": "UTC", "reset_hour": 0}
SER_DL = [(T(13, 12), 10_000.0), (T(13, 23, 55), 10_000.0), (T(14, 6), 9_900.0)]


@pytest.mark.parametrize("eq,status", [(9_800.0, "green"), (9_650.0, "yellow"), (9_400.0, "red")])
def test_daily_loss_bands(eq, status):
    r = evaluate("daily_loss", DL, series=SER_DL, snapshot=snap(eq), now=NOW)
    assert r["status"] == status
    assert r["limit"] == pytest.approx(500.0) and r["unit"] == "ccy"
    assert r["headroom"] == pytest.approx(500.0 - (10_000.0 - eq))
    assert r["reset_at"] == T(15).isoformat()


def test_daily_loss_gain_is_zero_usage():
    r = evaluate("daily_loss", DL, series=SER_DL, snapshot=snap(10_300.0), now=NOW)
    assert r["status"] == "green" and r["usage_pct"] == 0 and r["value"] == 0


def test_daily_loss_initial_balance_basis():
    p = {**DL, "basis": "initial_balance", "initial_balance": 20_000}
    r = evaluate("daily_loss", p, series=SER_DL, snapshot=snap(9_400.0), now=NOW)       # hạn mức 5% x 20000 = 1000, lỗ 600
    assert r["limit"] == pytest.approx(1000.0) and r["status"] == "green" and r["usage_pct"] == pytest.approx(60.0)


def test_daily_loss_tz_utc3_uses_local_day_start():
    now = T(14, 21, 10)                                      # 00:10 địa phương ngày 15
    ser = [(T(14, 20, 55), 10_000.0), (T(14, 21, 5), 9_000.0)]
    p = {**DL, "tz": "UTC+3"}
    r = evaluate("daily_loss", p, series=ser, snapshot=snap(9_000.0), now=now)
    assert r["status"] == "red" and r["value"] == pytest.approx(1000.0)                  # mốc 21:00Z: equity đầu ngày = 10000
    # cùng dữ liệu nhưng now=20:59Z (23:59 địa phương): chưa qua mốc reset -> equity đầu ngày là điểm hôm trước
    ser2 = [(T(13, 22), 11_000.0), (T(14, 20, 55), 10_000.0)]
    r2 = evaluate("daily_loss", p, series=ser2, snapshot=snap(10_000.0), now=T(14, 20, 59))
    assert r2["value"] == pytest.approx(1000.0) and r2["reset_at"] == T(14, 21).isoformat()
    assert r["reset_at"] == T(15, 21).isoformat()


def test_daily_loss_na():
    assert evaluate("daily_loss", DL, series=[], snapshot=None, now=NOW)["status"] == "na"
    assert evaluate("daily_loss", {"tz": "UTC"}, series=SER_DL, snapshot=snap(), now=NOW)["status"] == "na"   # thiếu limit_pct


def test_custom_warn_usage():
    r = evaluate("daily_loss", {**DL, "warn_usage_pct": 40}, series=SER_DL, snapshot=snap(9_790.0), now=NOW)   # 210/500 = 42%
    assert r["status"] == "yellow"


# ---------- max_drawdown ----------
@pytest.mark.parametrize("eq,status", [(9_500.0, "green"), (9_300.0, "yellow"), (8_900.0, "red")])
def test_max_dd_static(eq, status):
    r = evaluate("max_drawdown", {"limit_pct": 10, "mode": "static", "initial_balance": 10_000}, series=SER_DL, snapshot=snap(eq), now=NOW)
    assert r["status"] == status and r["limit"] == pytest.approx(1000.0)


def test_max_dd_static_needs_initial_balance():
    assert evaluate("max_drawdown", {"limit_pct": 10, "mode": "static"}, series=SER_DL, snapshot=snap(), now=NOW)["status"] == "na"


SER_PEAK = [(T(12, 10), 10_800.0), (T(12, 23, 55), 11_000.0), (T(13, 10), 12_000.0), (T(13, 23, 55), 11_200.0), (T(14, 6), 11_100.0)]


def test_max_dd_trailing_eod_vs_intraday():
    p = {"limit_pct": 10, "tz": "UTC"}
    eod = evaluate("max_drawdown", {**p, "mode": "trailing_eod"}, series=SER_PEAK, snapshot=snap(10_500.0), now=NOW)
    intra = evaluate("max_drawdown", {**p, "mode": "trailing_intraday"}, series=SER_PEAK, snapshot=snap(10_500.0), now=NOW)
    assert eod["limit"] == pytest.approx(1120.0) and eod["value"] == pytest.approx(700.0) and eod["status"] == "green"   # đỉnh cuối ngày 11200
    assert intra["limit"] == pytest.approx(1200.0) and intra["value"] == pytest.approx(1500.0) and intra["status"] == "red"  # đỉnh trong ngày 12000


def test_max_dd_trailing_eod_ignores_today_peak():
    ser = SER_PEAK + [(T(14, 9), 13_000.0)]                  # đỉnh hôm nay chưa tính cho eod đến khi hết ngày
    eod = evaluate("max_drawdown", {"limit_pct": 10, "tz": "UTC", "mode": "trailing_eod"}, series=ser, snapshot=snap(12_900.0), now=NOW)
    assert eod["limit"] == pytest.approx(1120.0) and eod["value"] == 0


def test_max_dd_na_without_equity():
    assert evaluate("max_drawdown", {"limit_pct": 10, "mode": "trailing_intraday"}, series=[], snapshot={}, now=NOW)["status"] == "na"


# ---------- margin_level ----------
@pytest.mark.parametrize("margin,status", [(3_000.0, "green"), (5_000.0, "yellow"), (8_000.0, "red")])
def test_margin_level_bands(margin, status):
    r = evaluate("margin_level", {"min_level_pct": 150}, series=[], snapshot=snap(10_000.0, margin), now=NOW)
    assert r["status"] == status and r["unit"] == "%"


def test_margin_level_no_positions_and_na():
    assert evaluate("margin_level", {"min_level_pct": 150}, series=[], snapshot=snap(10_000.0, 0.0), now=NOW)["status"] == "green"
    assert evaluate("margin_level", {"min_level_pct": 150}, series=[], snapshot={}, now=NOW)["status"] == "na"
    assert evaluate("margin_level", {}, series=[], snapshot=snap(10_000.0, 100.0), now=NOW)["status"] == "na"


# ---------- best_day ----------
SER_BD = [(T(10, 0), 10_000.0), (T(10, 23), 10_100.0), (T(11, 23), 10_700.0), (T(12, 23), 10_800.0), (T(13, 23), 11_000.0)]


@pytest.mark.parametrize("mx,status", [(150, "green"), (80, "yellow"), (40, "red")])
def test_best_day_bands(mx, status):
    r = evaluate("best_day", {"max_share_pct": mx, "tz": "UTC"}, series=SER_BD, snapshot=snap(11_000.0), now=NOW)
    assert r["status"] == status and r["value"] == pytest.approx(60.0)                  # 600 / 1000
    assert "Xấp xỉ" in r["detail"]


def test_best_day_not_applicable_and_na():
    losing = [(T(10, 0), 10_000.0), (T(10, 23), 9_000.0)]
    assert evaluate("best_day", {"max_share_pct": 40}, series=losing, snapshot=snap(9_000.0), now=NOW)["status"] == "green"
    r = evaluate("best_day", {"max_share_pct": 40, "min_total_profit": 5_000}, series=SER_BD, snapshot=snap(11_000.0), now=NOW)
    assert r["status"] == "green"
    assert evaluate("best_day", {"max_share_pct": 40}, series=[], snapshot=None, now=NOW)["status"] == "na"


# ---------- max_trades_day ----------
def test_max_trades_bands_and_reset():
    deals = [T(14, 1 + i % 10, i) for i in range(12)] + [T(13, 10, i) for i in range(5)]
    base = {"tz": "UTC"}
    assert evaluate("max_trades_day", {**base, "limit": 20}, series=[], snapshot=None, deal_times=deals, now=NOW)["status"] == "green"
    y = evaluate("max_trades_day", {**base, "limit": 15}, series=[], snapshot=None, deal_times=deals, now=NOW)
    assert y["status"] == "yellow" and y["value"] == 12 and y["headroom"] == 3
    assert evaluate("max_trades_day", {**base, "limit": 10}, series=[], snapshot=None, deal_times=deals, now=NOW)["status"] == "red"
    # UTC+3: mốc 21:00Z hôm 13 -> 5 deal 10:xx hôm 13 vẫn KHÔNG tính (trước mốc), nhưng deal 23:30Z hôm 13 thì tính
    late = deals + [T(13, 23, 30)]
    r = evaluate("max_trades_day", {"tz": "UTC+3", "limit": 100}, series=[], snapshot=None, deal_times=late, now=NOW)
    assert r["value"] == 13
    assert evaluate("max_trades_day", {"limit": 10}, series=[], snapshot=None, deal_times=None, now=NOW)["status"] == "na"


# ---------- không bao giờ ném lỗi ----------
def test_never_raises():
    for k in ("daily_loss", "max_drawdown", "margin_level", "best_day", "max_trades_day", "weird"):
        for params in (None, "x", {}, {"limit_pct": "abc", "limit": None, "tz": 5, "reset_hour": "x"}):
            r = evaluate(k, params, series=[("bad", 1), (None, None), (T(1), float("nan"))], snapshot={"equity": "zzz"}, deal_times=["x"], now=NOW)
            assert r["status"] in ("green", "yellow", "red", "na")
    assert set(evaluate("daily_loss", DL, series=SER_DL, snapshot=snap(), now=NOW)) == {
        "status", "usage_pct", "value", "limit", "headroom", "unit", "detail", "reset_at"}
