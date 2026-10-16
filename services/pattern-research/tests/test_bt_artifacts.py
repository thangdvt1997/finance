"""Test sinh so lenh/anh: cot day du, checksum, tai dung R khop, chon vi du, anh <= 150KB (khong can du lieu that)."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest

from pattern_research.backtest import Bars, simulate_sell

SPLITS = {"train": [None, "2025-07-27T00:00:00+00:00"], "val": ["2025-08-01T00:00:00+00:00", "2026-03-06T00:00:00+00:00"],
          "test": ["2026-03-11T00:00:00+00:00", None]}


@pytest.fixture()
def art(tmp_path, monkeypatch):
    (tmp_path / "splits.json").write_text(json.dumps(SPLITS))
    monkeypatch.setenv("PATTERN_DATA", str(tmp_path))
    import pattern_research.bt_run as m
    importlib.reload(m)
    import pattern_research.bt_artifacts as a
    return importlib.reload(a)


def _bars(n=80):
    rng = np.random.default_rng(1)
    c = 1.1 + np.cumsum(rng.normal(0, 0.0005, n))
    ts = pd.date_range("2020-01-01", periods=n, freq="15min").to_numpy()
    return Bars.from_arrays("EURUSD", "M15", ts, c, c + 0.0004, c - 0.0004, c, np.full(n, 8))


def test_enrich_columns_and_recompute(art, monkeypatch):
    b = _bars()
    tr = simulate_sell(b, 30, float(b.o[30] + 0.003), 2.0, art.B.MAX_HOLD)
    assert tr is not None
    row = pd.DataFrame([{"key": "k", "sig_i": 29, "entry_i": tr.entry_i, "exit_i": tr.exit_i, "entry_ts": b.ts[30], "exit_ts": b.ts[tr.exit_i],
                         "entry": tr.entry, "sl": tr.sl, "tp": tr.tp, "r": tr.r, "r_gross": tr.r_gross, "outcome": tr.outcome, "tp_r_used": 2.0}])
    monkeypatch.setattr(art, "_bars", lambda k, mode: ({"symbol": "EURUSD"}, b))
    e, bad = art.enrich(row, "dev")
    assert bad == 0
    for c in ("signal_time", "spread", "slip", "mae_r", "mfe_r", "bars_held"):
        assert c in e
    assert e.bars_held.iloc[0] == tr.exit_i - 30 + 1 and e.mae_r.iloc[0] >= -1
    row.loc[0, "r"] += 0.01                      # so lenh bi sua -> phai bi phat hien
    assert art.enrich(row, "dev")[1] == 1


def test_params_hash_and_checksum(art, tmp_path):
    assert art.params_hash(2.0, 80.0) == art.params_hash(2, 80) != art.params_hash(1.5, 80)
    f = tmp_path / "x"
    f.write_bytes(b"abc")
    assert art.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert len(art.COLS) == 23 and art.COLS[0] == "id" and art.COLS[-1] == "snapshot_sha"


def test_pick_examples_counts_and_worst_excluded(art):
    rng = np.random.default_rng(0)
    n = 300
    r = rng.normal(-0.1, 1, n)
    d = pd.DataFrame({"id": [f"D{i}" for i in range(n)], "kb": "KB-1", "R_net": r, "entry_time": pd.date_range("2020", periods=n, freq="h"),
                      "exit_reason": np.where(r > 0, "tp", "sl")})
    s = art.pick_examples(d, "KB-1", rng)
    assert s.pick.value_counts().to_dict() == {"thang": 20, "thua": 20, "te-nhat": 10}
    assert not set(s[s.pick != "te-nhat"].id) & set(s[s.pick == "te-nhat"].id)
    assert (s[s.pick == "te-nhat"].R_net <= d.R_net.nsmallest(10).max()).all()


def test_save_png_size_limit(art, tmp_path):
    plt = art._plt()
    f, ax = plt.subplots(figsize=(12, 6))
    ax.plot(np.random.default_rng(0).normal(size=5000).cumsum())
    p = tmp_path / "a.png"
    art.save_png(f, p)
    assert 0 < p.stat().st_size <= 150 * 1024
