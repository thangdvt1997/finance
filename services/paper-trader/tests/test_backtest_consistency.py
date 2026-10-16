"""Test HỒI QUY QUAN TRỌNG: trọng số mục tiêu của plugin `slow_trend_multiasset` phải KHỚP trọng số của mã backtest
(research/multiasset/ma_engine.py; bản sao nguyên văn trong tests/ref_backtest.py) trên cùng dữ liệu lịch sử.
Dữ liệu tổng hợp tất định: 30 tài sản (6 lớp), niên đại khác nhau, ngày nghỉ riêng từng tài sản, vài tài sản lên sàn muộn."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from paper_trader.models import Targets
from paper_trader.strategies import slow_trend_multiasset as stm
from paper_trader.strategy import StrategyContext, build

from . import ref_backtest as ref

SYMS = ["US:SPY", "US:QQQ", "US:IWM", "US:EWG", "US:FEZ", "US:EWJ", "US:EWH", "US:INDA", "US:EWZ", "US:VNM",
        "US:SHY", "US:IEI", "US:IEF", "US:TLT", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
        "US:GLD", "US:SLV", "US:CPER", "US:USO", "US:BNO", "US:UNG", "US:CORN", "US:WEAT", "US:SOYB", "US:CANE"]
LATE = {"US:CPER": 700, "US:CORN": 600, "US:WEAT": 800, "US:SOYB": 800, "US:CANE": 800, "US:VNM": 400}   # chỉ số phiên bắt đầu
N_DAYS = 1500
CAL = pd.bdate_range("2018-01-01", periods=N_DAYS)


def make_data(seed=11):
    """-> (R_excess DataFrame như backtest [NaN trước khi bắt đầu, 0 ngày nghỉ], history dict giá D1 UTC cho plugin)."""
    rng = np.random.default_rng(seed)
    R = pd.DataFrame(np.nan, index=CAL, columns=SYMS)
    hist: dict[str, pd.DataFrame] = {}
    cls_vol = {"eq": 0.17, "bond": 0.06, "fx": 0.08, "metal": 0.20, "energy": 0.35, "agri": 0.25}
    for s in SYMS:
        vol = cls_vol[stm.asset_info(s)[0]] * rng.uniform(0.7, 1.3) / np.sqrt(252)
        drift = rng.normal(0, 0.12) / 252
        regime = np.repeat(rng.normal(0, 0.25, N_DAYS // 120 + 2) / 252, 120)[:N_DAYS]      # xu hướng đổi theo giai đoạn
        r = drift + regime + vol * rng.standard_normal(N_DAYS)
        k0 = LATE.get(s, 0)
        hol = rng.random(N_DAYS) < 0.03                                                       # ngày nghỉ riêng của tài sản
        r = np.where(hol, 0.0, r)
        col = pd.Series(np.nan, index=CAL)
        col.iloc[k0 + 1:] = r[k0 + 1:]          # r[k0] là NaN: giá đầu tiên tại k0 -> lợi suất đầu tại k0+1
        R[s] = col
        px = 100.0 * np.cumprod(1 + np.nan_to_num(col.values[k0:], nan=0.0))
        ser = pd.Series(px, index=CAL[k0:])
        keep = ~hol[k0:]
        keep[:2] = True
        ser = ser[keep]
        df = pd.DataFrame({"o": ser, "h": ser, "l": ser, "c": ser, "v": 0.0})
        df.index = df.index.tz_localize("UTC")
        hist[s] = df
    assert not (R.isna().all(axis=1) & (np.arange(N_DAYS) > 5)).any()
    return R, hist


def month_ends(idx, n=6):
    s = pd.Series(idx, index=idx)
    m = (s.dt.to_period("M") != s.shift(-1).dt.to_period("M")).values
    return list(idx[m][-n - 1:-1])


def ctx_at(hist, d, universe, params=None):
    cut = {s: df[df.index <= pd.Timestamp(d).tz_localize("UTC")] for s, df in hist.items()}
    return StrategyContext(now=pd.Timestamp(d).to_pydatetime(), tf="D1", universe=tuple(universe), history=cut, equity=100_000.0,
                           positions={}, params=params or {})


BT_PARAMS = {"adjust_carry": False, "max_stale_days": 10_000}     # khớp backtest: dữ liệu đã là excess, không thêm carry


def _expected(R, dates, allow_short=True):
    c = ref.Ctx(R, [stm.asset_info(s)[0] for s in R.columns])
    S = ref.sig_ens(c.I)
    if not allow_short:
        S = S.clip(lower=0)
    return ref.weights(c, S, pd.DatetimeIndex(dates)), S


def test_weights_match_backtest_exactly():
    R, hist = make_data()
    dates = month_ends(CAL)
    W, _ = _expected(R, dates)
    strat = build("slow_trend_multiasset", dict(BT_PARAMS))
    worst = 0.0
    for d in dates:
        t = strat.targets(ctx_at(hist, d, SYMS))
        assert isinstance(t, Targets) and t.status == "ok" and t.kind == "weight"
        got = np.array([t.weights[s] for s in SYMS])
        exp = W.loc[d].values
        assert np.abs(exp).sum() > 0.5, "backtest phải có vị thế (test vô nghĩa nếu toàn 0)"
        worst = max(worst, float(np.abs(got - exp).max()))
    assert worst < 1e-6, f"lệch tối đa {worst:.3e} so với backtest"


def test_signs_match_backtest_all_symbols_and_signals_match():
    R, hist = make_data(seed=5)
    dates = month_ends(CAL, 4)
    W, S = _expected(R, dates)
    strat = build("slow_trend_multiasset", dict(BT_PARAMS))
    for d in dates:
        t = strat.targets(ctx_at(hist, d, SYMS))
        for s in SYMS:
            sg = S.loc[d, s]
            assert (np.isnan(sg) and t.meta["signals"][s] is None) or t.meta["signals"][s] == pytest.approx(round(float(sg), 3), abs=1e-3)
        agree = [np.sign(t.weights[s]) == np.sign(W.loc[d, s]) for s in SYMS]
        assert np.mean(agree) == 1.0


def test_long_only_matches_backtest_long_flat():
    R, hist = make_data(seed=3)
    dates = month_ends(CAL, 3)
    W, _ = _expected(R, dates, allow_short=False)
    strat = build("slow_trend_multiasset", {**BT_PARAMS, "allow_short": False})
    for d in dates:
        t = strat.targets(ctx_at(hist, d, SYMS))
        got = np.array([t.weights[s] for s in SYMS])
        assert (got >= -1e-12).all()
        assert np.abs(got - W.loc[d].values).max() < 1e-6


def test_target_vol_and_leverage_caps_and_class_budgets():
    R, hist = make_data(seed=9)
    d = month_ends(CAL, 1)[0]
    strat = build("slow_trend_multiasset", {**BT_PARAMS, "target_vol": 0.10, "lmax": 50.0, "asset_cap": 50.0, "gross_cap": 500.0})
    t = strat.targets(ctx_at(hist, d, SYMS))
    # không bị chặn bởi trần -> vol ex-ante đúng mục tiêu 10%
    assert t.meta["L"] < 50.0 and t.meta["exante_vol"] == pytest.approx(0.10, rel=0.02)
    # cùng dữ liệu + trần bổ sung (cấu hình tài khoản v2): kỷ luật đòn bẩy
    caps = {"asset_cap": 0.5, "gross_cap": 2.0, "class_gross_cap": 0.6, "short_class_cap": {"bond": 0.25}}
    t2 = build("slow_trend_multiasset", {**BT_PARAMS, **caps}).targets(ctx_at(hist, d, SYMS))
    w = pd.Series(t2.weights)
    assert w.abs().sum() <= 2.0 + 1e-9 and w.abs().max() <= 0.5 + 1e-9
    for c, g in t2.meta["class_gross"].items():
        assert g <= 0.6 + 1e-9, (c, g)
    bonds = [s for s in SYMS if stm.asset_info(s)[0] == "bond"]
    assert -w[bonds].clip(upper=0).sum() <= 0.25 + 1e-9
    assert t2.meta["exante_vol"] <= 0.10 + 1e-6


def test_signs_unchanged_by_caps():
    R, hist = make_data(seed=9)
    d = month_ends(CAL, 1)[0]
    a = build("slow_trend_multiasset", dict(BT_PARAMS)).targets(ctx_at(hist, d, SYMS)).weights
    b = build("slow_trend_multiasset", {**BT_PARAMS, "asset_cap": 0.5, "gross_cap": 2.0, "class_gross_cap": 0.6}).targets(ctx_at(hist, d, SYMS)).weights
    assert all(np.sign(a[s]) == np.sign(b[s]) for s in SYMS)


def test_warming_up_when_history_short():
    R, hist = make_data()
    short = {s: df.iloc[:200] for s, df in hist.items()}
    ctx = StrategyContext(now=pd.Timestamp("2019-01-01").to_pydatetime(), tf="D1", universe=tuple(SYMS), history=short, equity=1e5, positions={})
    t = build("slow_trend_multiasset", {}).targets(ctx)
    assert t.status == "warming_up"


def test_carry_adjustment_directions():
    # SPY: cổ tức 2% - tiền mặt 4% => dịch -2%/năm; vàng/dầu: -4%; trái phiếu & FX: 0
    assert stm._net_carry("US:SPY", 0.04, None) == pytest.approx(-0.02)
    assert stm._net_carry("US:USO", 0.04, None) == pytest.approx(-0.04)
    assert stm._net_carry("US:IEF", 0.04, None) == 0.0 and stm._net_carry("EURUSD", 0.04, None) == 0.0
    assert stm._net_carry("US:SPY", 0.04, {"US:SPY": 0.01}) == 0.01
    # giá phẳng của hàng hoá + trừ tiền mặt => chuỗi excess giảm => tín hiệu âm (ETF hàng hoá giá thô đi ngang KHÔNG phải xu hướng tăng)
    idx = pd.date_range("2020-01-01", periods=400, freq="B", tz="UTC")
    df = pd.DataFrame({"c": 50.0}, index=idx)
    R, _ = stm.build_returns({"US:USO": df}, ["US:USO"], cash_rate=0.04)
    assert (R["US:USO"].dropna() < 0).all()


def test_ref_matches_research_if_available():
    """Nếu mã research import được (cần scipy + pq) thì so trực tiếp với ma_engine.weights; nếu không thì bỏ qua."""
    root = Path(__file__).resolve().parents[3] / "research"
    if not (root / "multiasset" / "ma_engine.py").is_file():
        pytest.skip("không có thư mục research")
    sys.path[:0] = [str(root), str(root / "multiasset")]
    try:
        me = importlib.import_module("ma_engine")
        ma_common = importlib.import_module("ma_common")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"không import được research ({e})")
    finally:
        for p in (str(root), str(root / "multiasset")):
            if p in sys.path:
                sys.path.remove(p)
    cols = [c for c in ma_common.CORE][:30]
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2015-01-01", periods=1200)
    R = pd.DataFrame(rng.standard_normal((1200, len(cols))) * 0.008 + rng.normal(0, 0.0004, len(cols)), index=idx, columns=cols)
    ctx = me.Ctx(R, pd.Series(0.0, index=idx), cols)
    S = me.sig_ens(ctx.I)
    reb = pd.DatetimeIndex(month_ends(idx, 3))
    W_real = me.weights(ctx, S, reb)
    c2 = ref.Ctx(R, [ma_common.ASSETS[c][0] for c in cols])
    W_ref = ref.weights(c2, ref.sig_ens(c2.I), reb)
    assert np.abs(W_real.values - W_ref.values).max() < 1e-9
