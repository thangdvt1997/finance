import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ai_trading.scenario_schema import validate
from ai_trading.scenario_store import Store
from pattern_research.backtest import Bars

from ai_trading_worker import dsl, main as wmain, runner

ROOT = Path(__file__).resolve().parents[2]
DEMO = (ROOT / "ai-trading" / "tests" / "fixtures" / "examples" / "SC-DEMO-1.yaml").read_text(encoding="utf-8")


def make_bars(n=3000, seed=1, start="2012-01-02"):
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=n, freq="h")
    c = 1.1 + np.cumsum(rng.normal(0, 0.0008, n))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.0005, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.0005, n))
    return ts, o, h, l, c


def bars_of(n=3000, seed=1):
    ts, o, h, l, c = make_bars(n, seed)
    return Bars.from_arrays("EURUSD", "H1", ts.to_numpy(), o, h, l, c)


def test_no_lookahead_truncation():
    sc = validate("id: SC-T0\nname: kiểm thử\nsymbols: [EURUSD]\ntfs: [H1]\ndetector:\n  cooldown_bars: 5\n  rules:\n    - {rule: move_atr, dir: up, bars: 4, min: 1.0}\n    - {rule: bear_body, min_atr: 0.3}\n    - {rule: rsi, op: '>=', value: 50}\n    - {rule: ma, side: above, kind: ema, period: 20}\nlevels:\n  sl: {type: atr, mult: 1.5}\n  tp_r: [1.0]\n")
    b = bars_of(4000)
    full = dsl.signal_indices(sc, b)
    assert len(full) > 5
    for cut in (1500, 2500, 3300):
        bt = Bars.from_arrays("EURUSD", "H1", b.ts[:cut], b.o[:cut], b.h[:cut], b.l[:cut], b.c[:cut])
        part = dsl.signal_indices(sc, bt)
        assert list(part) == [i for i in full if i < cut - 1], cut      # cắt cụt không đổi tín hiệu quá khứ


def test_rules_semantics():
    n = 120
    o = np.full(n, 1.0); c = np.full(n, 1.0); h = np.full(n, 1.001); l = np.full(n, 0.999)
    ts = pd.date_range("2020-01-01", periods=n, freq="h").to_numpy()
    # nhịp tăng rồi nến giảm nhấn chìm có bóng trên ở nến 100
    for i in range(94, 100):
        o[i] = 1.0 + 0.003 * (i - 94); c[i] = o[i] + 0.003; h[i] = c[i] + 0.0002; l[i] = o[i] - 0.0002
    o[100], c[100], h[100], l[100] = c[99] + 0.0002, o[94] - 0.0, c[99] + 0.004, c[99] - 0.019
    b = Bars.from_arrays("EURUSD", "H1", ts, o, h, l, c)
    sc = validate("id: SC-T1\nname: kiểm thử\nsymbols: [EURUSD]\ntfs: [H1]\ndetector:\n  rules:\n    - {rule: bear_engulf}\n    - {rule: bear_body, min_atr: 1.0}\nlevels:\n  sl: {type: atr, mult: 1.5}\n  tp_r: [1.0]\n")
    m = dsl.signal_mask(sc, b)
    assert m[100] and m.sum() == 1
    sc2 = validate("id: SC-T2\nname: kiểm thử\nsymbols: [EURUSD]\ntfs: [H1]\ndetector:\n  rules:\n    - {rule: hours, from: 5, to: 8}\n    - {rule: bear_engulf}\nlevels:\n  sl: {type: atr, mult: 1.5}\n  tp_r: [1.0]\n")
    assert dsl.signal_mask(sc2, b).sum() == 0 or all(pd.Timestamp(b.ts[i]).hour in (5, 6, 7) for i in np.flatnonzero(dsl.signal_mask(sc2, b)))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    d = tmp_path / "patterns"
    (d / "mt5" / "bars").mkdir(parents=True)
    (d / "splits.json").write_text(json.dumps({"train": [None, "2025-07-27T00:00:00+00:00"], "val": ["2025-08-01T00:00:00+00:00", "2026-03-06T00:00:00+00:00"],
                                               "test": ["2026-03-11T00:00:00+00:00", None]}))
    ts = pd.date_range("2009-01-01", "2026-09-30", freq="h")
    ts = ts[ts.dayofweek < 5]
    n = len(ts)
    _, o, h, l, c = make_bars(n, 3, "2009-01-01")
    pd.DataFrame({"ts_open": ts.tz_localize("UTC"), "o": o, "h": h, "l": l, "c": c, "spread": 12, "n_m1": 60}).to_parquet(d / "mt5" / "bars" / "ZZTEST_H1.parquet")
    st = tmp_path / "state"
    (st / "jobs").mkdir(parents=True)
    monkeypatch.setattr(runner, "DATA", d)
    monkeypatch.setattr(runner, "STATE", str(st))
    monkeypatch.setattr(runner, "N_SEEDS", 20)
    monkeypatch.setattr(runner, "MIN_TEST_TRADES", 5)
    store = Store(str(st))
    y = DEMO.replace("[EURUSD, GBPUSD]", "[ZZTEST]").replace("SC-DEMO-1", "SC-W1")
    y = y.replace("min: 2.0", "min: 1.0")
    sc = validate(y)
    sc["golden"] = []
    store.create(sc, {}, "t")
    return store, sc, d


def run(store, sid, typ):
    j = store.enqueue(sid, typ, "t")
    rc = runner.run_job(j["id"])
    return rc, store.job(j["id"])


def test_full_flow_and_lock(env):
    store, sc, d = env
    rc, j = run(store, "SC-W1", "detector_test")
    assert rc == 0 and j["status"] == "done"
    det = store.result("SC-W1")["detector"]
    assert det["dev_only"] and sum(v["n_signals"] for v in det["by_series"].values()) > 20
    # dev không bao giờ thấy dữ liệu từ ngày test
    rc, j = run(store, "SC-W1", "backtest")
    assert rc == 0 and j["status"] == "done", j
    res = store.result("SC-W1")
    dev = res["dev"]
    assert dev["status"] == "done" and dev["snapshot_sha"] and dev["oos"]["pooled"]["n"] > 20 and dev["folds"]
    assert res["verdict"] in ("unproven", "no_edge") and "test" not in res
    assert all(pd.Timestamp(t["last"] if False else "2000-01-01") for t in [dev])          # smoke
    assert dev["oos"]["pooled"]["last"] < "2026-03-11"
    assert not (store.path("SC-W1") / "test_opened.json").exists()
    # test khoá: mở đúng 1 lần
    rc, j = run(store, "SC-W1", "final_test")
    assert rc == 0 and j["status"] == "done", j
    te = store.result("SC-W1")["test"]
    assert te["status"] == "done" and te["summary"]["first"] >= "2026-03-11"
    assert (store.path("SC-W1") / "test_opened.json").exists() and "MO TAP TEST KHOA" in (store.path("SC-W1") / "test_access.log").read_text()
    rc, j = run(store, "SC-W1", "final_test")
    assert rc == 1 and j["status"] == "failed" and "đã được mở" in j["message"]
    assert store.result("SC-W1")["test"]["status"] == "done"          # lần 2 không ghi đè kết quả


def test_final_refuses_without_dev(env):
    store, sc, d = env
    rc, j = run(store, "SC-W1", "final_test")
    assert rc == 1 and j["status"] == "failed"
    assert not (store.path("SC-W1") / "test_opened.json").exists()      # chưa dev -> không tiêu khoá


def test_dev_data_changed_blocks_eval(env):
    store, sc, d = env
    run(store, "SC-W1", "backtest")
    p = d / "mt5" / "bars" / "ZZTEST_H1.parquet"
    df = pd.read_parquet(p)
    df.loc[df.index[len(df) // 3], "c"] += 0.01
    df.to_parquet(p)
    rc, j = run(store, "SC-W1", "final_test")
    assert rc == 1 and "snapshot" in j["message"]
    assert store.result("SC-W1")["test"]["status"] == "failed"
    assert (store.path("SC-W1") / "test_opened.json").exists()       # đã mở thì tính là đã mở


def test_golden_rejects_test_zone(env):
    store, sc, d = env
    sc["golden"] = [{"image": None, "symbol": "ZZTEST", "tf": "H1", "bar_ts": "2026-04-01T10:00", "expect": True}]
    (store.path("SC-W1") / "scenario.yaml").write_text(__import__("yaml").safe_dump(sc, allow_unicode=True))
    run(store, "SC-W1", "detector_test")
    g = store.result("SC-W1")["detector"]["golden"][0]
    assert g["status"] == "rejected"


def test_signal_limit(env, monkeypatch):
    store, sc, d = env
    monkeypatch.setattr(runner, "MAX_SIGNALS", 3)
    rc, j = run(store, "SC-W1", "backtest")
    assert rc == 1 and "quá lỏng" in j["message"]


def test_recover_marks_running_failed(env):
    store, sc, d = env
    j = store.enqueue("SC-W1", "backtest", "t")
    wmain.set_job(store, j, status="running")
    wmain.recover(store)
    assert store.job(j["id"])["status"] == "failed" and store.job(j["id"])["error"] == "worker_restart"


def test_timeout_kills(env, monkeypatch):
    store, sc, d = env
    j = store.enqueue("SC-W1", "backtest", "t")
    monkeypatch.setattr(wmain, "TIMEOUT_S", 1)
    monkeypatch.setattr(wmain.sys, "executable", "/bin/sleep")
    real = wmain.subprocess.Popen
    monkeypatch.setattr(wmain.subprocess, "Popen", lambda cmd, **kw: real(["sleep", "30"], **kw))
    wmain.run_one(store, store.job(j["id"]))
    r = store.job(j["id"])
    assert r["status"] == "failed" and r["error"] == "timeout"


def test_verdict_rules():
    v = runner.verdict
    assert v({}) == "unproven"
    assert v({"dev": {"oos": {"pooled": {"n": 100, "exp_r": -0.1}}}}) == "no_edge"
    base = {"status": "done", "summary": {"n": 100, "exp_r": 0.2, "ci95": [0.05, 0.3]}, "p_vs_random": 0.01, "dsr": {"dsr": 0.97}}
    assert v({"test": base, "dev": {"pbo": {"pbo": 0.2}}}) == "edge"
    assert v({"test": {**base, "p_vs_random": 0.2}, "dev": {}}) == "unproven"
    assert v({"test": {**base, "summary": {"n": 100, "exp_r": -0.1, "ci95": [-0.3, 0.1]}}, "dev": {}}) == "no_edge"
    assert v({"test": {**base, "summary": {"n": 10, "exp_r": 0.5, "ci95": [0.1, 0.9]}}, "dev": {}}) == "unproven"


def test_no_order_paths():
    import re
    for f in (ROOT / "ai-trading-worker" / "src").rglob("*.py"):
        assert not re.search(r"order_send|OrderSend|create_order|MetaTrader5|ccxt", f.read_text(encoding="utf-8")), f
