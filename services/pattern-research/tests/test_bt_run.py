"""Test quy trinh bt_run (khong can du lieu that): loc QC, walk-forward khong dung lenh chua dong, khoa tap test, kiem nhan qua."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest

SPLITS = {"train": [None, "2025-07-27T00:00:00+00:00"], "val": ["2025-08-01T00:00:00+00:00", "2026-03-06T00:00:00+00:00"],
          "test": ["2026-03-11T00:00:00+00:00", None]}


@pytest.fixture()
def bt(tmp_path, monkeypatch):
    (tmp_path / "splits.json").write_text(json.dumps(SPLITS))
    monkeypatch.setenv("PATTERN_DATA", str(tmp_path))
    import pattern_research.bt_run as m
    return importlib.reload(m)


def test_load_df_applies_qc_start_fill_and_hides_test(bt, tmp_path):
    ts = pd.date_range("1999-01-01", "2026-06-01", freq="30D")
    df = pd.DataFrame({"ts_open": ts, "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0, "spread": 10, "n_m1": 60})
    df.loc[200, "n_m1"] = 10                     # nen thieu du lieu (< 50% so phut)
    p = tmp_path / "x.parquet"
    df.to_parquet(p)
    x = {"src": "mt5", "symbol": "EURUSD", "tf": "H1", "path": str(p)}
    dev = bt.load_df(x, "dev")
    assert dev.ts_open.min() >= pd.Timestamp("2001-01-01")
    assert dev.ts_open.max() < bt.TEST_START, "che do dev KHONG duoc thay nen tap test"
    assert (dev.n_m1 >= 30).all() and df.ts_open[200] not in set(dev.ts_open)
    fin = bt.load_df(x, "final")
    assert fin.ts_open.max() >= bt.TEST_START
    xau = {"src": "mt5", "symbol": "XAUUSD", "tf": "M15", "path": str(p)}
    assert bt.start_of(xau) == pd.Timestamp("2009-01-01")
    assert bt.start_of({**xau, "tf": "H1"}) == pd.Timestamp("2007-01-01")


def test_choose_only_sees_trades_closed_before_cutoff(bt):
    cut = pd.Timestamp("2015-01-01")
    n = 40
    base = pd.DataFrame({"entry_ts": pd.date_range("2014-01-01", periods=n, freq="D")})
    good_past = base.assign(exit_ts=base.entry_ts + pd.Timedelta(days=1), r=0.5)
    # tham so 'tuong lai' cuc tot nhung lenh dong SAU cutoff -> khong duoc chon
    fut = base.assign(entry_ts=base.entry_ts, exit_ts=pd.Timestamp("2015-06-01"), r=50.0)
    tr = {0: good_past, 1: fut}
    gi, info = bt.choose(tr, cut)
    assert gi == 0 and info[1][0] == 0
    # it hon MIN_IS_TRADES -> mac dinh
    gi, _ = bt.choose({0: good_past.head(5), 1: fut}, cut)
    assert gi == bt.GRID.index(bt.DEFAULT)


def test_test_set_runs_only_once(bt, tmp_path):
    out = tmp_path / "backtest"
    out.mkdir()
    (out / "wf_report.json").write_text(json.dumps({"final_params": bt.DEFAULT}))
    (out / "test_report.json").write_text("{}")
    with pytest.raises(SystemExit, match="1 lan"):
        bt.cmd_test()
    assert not (tmp_path / "test_access.log").exists(), "khong mo test khi da chay"


def test_prefix_check_flags_repainted_signal(bt, tmp_path):
    def put(mode, sigs):
        d = tmp_path / "backtest" / mode / "signals"
        d.mkdir(parents=True, exist_ok=True)
        (d / "k.json").write_text(json.dumps({"key": "mt5:EURUSD:H1", "signals": sigs}))
    s1 = {"pattern": "KB-2", "bar_ts": "2020-01-01T00:00:00+00:00", "setup_id": "a"}
    s2 = {"pattern": "KB-2", "bar_ts": "2026-05-01T00:00:00+00:00", "setup_id": "b"}
    put("dev", [s1])
    put("final", [s1, s2])
    assert bt._prefix_check() == {"series_checked": 1, "mismatch": []}
    put("final", [{**s1, "setup_id": "khac"}, s2])
    assert bt._prefix_check()["mismatch"] == ["mt5:EURUSD:H1"]


def test_random_baseline_detects_real_edge_but_not_noise():
    """Chien luoc co loi the that (vao truoc nhip giam) -> p nho; vao ngau nhien -> p khong nho."""
    from pattern_research.backtest import Bars, p_value_vs_random, random_baseline, simulate_sell
    rng = np.random.default_rng(5)
    n = 6000
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    drops = np.arange(300, n - 200, 150)
    for d in drops:                                  # cai 'nhip giam' 20 nen sau moi diem drop
        c[d:d + 20] -= np.linspace(0, 6, 20)
        c[d + 20:] -= 6
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.2
    l = np.minimum(o, c) - 0.2
    b = Bars.from_arrays("ZZZ", "H1", np.arange(n).astype("datetime64[h]"), o, h, l, c, None, True)
    sl_atr = np.full(len(drops), 2.0)
    real = [simulate_sell(b, int(e), b.o[e] + 2.0 * b.atr[e - 1], 2.0, 50) for e in drops]
    real_mean = np.mean([t.r for t in real if t])
    rand = random_baseline(b, sl_atr, 300, n - 200, 2.0, 50, n_seeds=200, seed=1)
    p, m = p_value_vs_random(real_mean, rand)
    assert real_mean > m and p < 0.01
    noise = rand[0][np.isfinite(rand[0])].mean()
    p2, _ = p_value_vs_random(noise, rand[1:])
    assert p2 > 0.01
