"""Đối chiếu chỉ báo với giá trị tham chiếu đã biết + cài đặt thuần Python độc lập."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.indicators import compute, percentile_rank, pivots, resample, to_frame

from .conftest import make_bars

# Dữ liệu RSI(14) kinh điển (Wilder; bảng ví dụ ChartSchool/StockCharts): RSI đầu tiên ~70.53
WILDER = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
          46.00, 46.03, 46.41, 46.22, 45.64]
WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def _frame(close: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(close), freq="1h", tz="UTC")
    c = pd.Series(close, index=idx)
    return pd.DataFrame({"o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": 1.0})


def wilder_rsi(close, n=14):
    d = np.diff(close)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = up[:n].mean(), dn[:n].mean()
    out = [100 - 100 / (1 + au / ad)]
    for i in range(n, len(d)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
        out.append(100 - 100 / (1 + au / ad) if ad else 100.0)
    return out


def sma_seeded_ema(x, n):
    k = 2 / (n + 1)
    e = [np.mean(x[:n])]
    for v in x[n:]:
        e.append(e[-1] + k * (v - e[-1]))
    return np.array(e)


def test_rsi_matches_wilder_reference_values():
    ind = compute(_frame(WILDER))
    got = ind["rsi"][14:]
    assert len(got) == len(WILDER_RSI)
    # bảng gốc làm tròn các bước trung gian nên lệch <= 0.1 so với giá trị chính xác (70.46...)
    assert got == pytest.approx(WILDER_RSI, abs=0.1)


def test_rsi_matches_independent_wilder_implementation():
    rows = make_bars(300, seed=11)
    df = to_frame(rows)
    ind = compute(df)
    ref = wilder_rsi(df["c"].to_numpy())
    assert ind["rsi"][14:] == pytest.approx(ref, abs=1e-6)


def test_ema_matches_sma_seeded_reference():
    df = to_frame(make_bars(300, seed=12))
    ind = compute(df)
    c = df["c"].to_numpy()
    for n, key in ((20, "ema20"), (50, "ema50"), (200, "ema200")):
        ref = sma_seeded_ema(c, n)
        assert ind[key][n - 1:] == pytest.approx(ref, rel=1e-9)
        assert np.isnan(ind[key][n - 2])


def test_bollinger_matches_rolling_mean_std():
    df = to_frame(make_bars(120, seed=13))
    ind = compute(df)
    c = df["c"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    assert ind["bb_mid"][19:] == pytest.approx(mid.to_numpy()[19:], rel=1e-9)
    assert ind["bb_upper"][19:] == pytest.approx((mid + 2 * sd).to_numpy()[19:], rel=1e-9)
    assert ind["bb_lower"][19:] == pytest.approx((mid - 2 * sd).to_numpy()[19:], rel=1e-9)


def test_atr_matches_wilder_reference():
    df = to_frame(make_bars(120, seed=14))
    ind = compute(df)
    h, l, c = (df[k].to_numpy() for k in "hlc")
    tr = np.maximum.reduce([h[1:] - l[1:], abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])])
    atr = [tr[:14].mean()]
    for t in tr[14:]:
        atr.append((atr[-1] * 13 + t) / 14)
    assert ind["atr"][14:] == pytest.approx(atr, rel=1e-9)


def test_macd_is_ema12_minus_ema26_and_histogram_consistent():
    df = to_frame(make_bars(200, seed=15))
    ind = compute(df)
    c = df["c"].to_numpy()
    # TA-Lib MACD dùng EMA kiểu chuẩn; kiểm tra quan hệ cấu trúc ổn định ở đoạn đã hội tụ
    e12 = pd.Series(c).ewm(span=12, adjust=False).mean().to_numpy()
    e26 = pd.Series(c).ewm(span=26, adjust=False).mean().to_numpy()
    assert ind["macd"][-1] == pytest.approx((e12 - e26)[-1], rel=2e-2, abs=1e-3)
    assert ind["macd_hist"][-1] == pytest.approx(ind["macd"][-1] - ind["macd_signal"][-1], abs=1e-9)


def test_monotone_rise_gives_rsi_100_and_adx_high():
    ind = compute(_frame([100 + i for i in range(80)]))
    assert ind["rsi"][-1] == pytest.approx(100.0)
    assert ind["adx"][-1] > 50
    assert ind["plus_di"][-1] > ind["minus_di"][-1]
    assert ind["stoch_k"][-1] > 80


def test_pivots_classic_formula():
    p = pivots(h=110.0, l=100.0, c=105.0)
    assert p["p"] == pytest.approx(105.0)
    assert p["r1"] == pytest.approx(110.0)
    assert p["s1"] == pytest.approx(100.0)
    assert p["r2"] == pytest.approx(115.0)
    assert p["s2"] == pytest.approx(95.0)


def test_percentile_rank():
    a = np.arange(1.0, 101.0)
    assert percentile_rank(a, 100.0) == pytest.approx(100.0)
    assert percentile_rank(a, 50.0) == pytest.approx(50.0)
    assert percentile_rank(np.arange(10.0), 5.0) is None  # < 30 mẫu


def test_to_frame_drops_duplicates_and_bad_bars():
    rows = make_bars(5)
    rows.append(dict(rows[-1], c=999.0))        # trùng ts_open: giữ bản sau
    rows.append({**rows[0], "ts_open": rows[0]["ts_open"] - pd.Timedelta(hours=9), "o": float("nan")})
    rows.append({**rows[0], "ts_open": rows[0]["ts_open"] - pd.Timedelta(hours=8), "c": 0.0})
    df = to_frame(rows)
    assert len(df) == 5
    assert df["c"].iloc[-1] == 999.0
    assert df.index.is_monotonic_increasing


def test_resample_h1_to_h4_and_d1():
    rows = make_bars(48, "H1", end=pd.Timestamp("2026-03-03", tz="UTC").to_pydatetime())  # đúng 2 ngày, căn 00:00
    h1 = to_frame(rows)
    h4 = resample(h1, "H4")
    d1 = resample(h1, "D1")
    assert len(h4) == 12 and len(d1) == 2
    first = h1.iloc[:24]
    assert d1["o"].iloc[0] == first["o"].iloc[0]
    assert d1["c"].iloc[0] == first["c"].iloc[-1]
    assert d1["h"].iloc[0] == first["h"].max()
    assert d1["l"].iloc[0] == first["l"].min()
    assert d1["v"].iloc[0] == pytest.approx(first["v"].sum())
