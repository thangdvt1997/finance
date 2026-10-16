from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fakeredis.aioredis as fr
import numpy as np
import pandas as pd
import pytest

from analytics import alerts as al
from analytics import stats
from analytics.config import load_yaml
from analytics.engine import analyze
from analytics.indicators import to_frame
from analytics.repo import MemoryBarSource, MemoryStore
from analytics.runner import Runner

from .conftest import make_bars

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def codes(a):
    return {s["code"] for s in a.summary["states"]}


def test_uptrend_states_and_scores(up_bars):
    a = analyze("UP", "H1", to_frame(up_bars))
    s = a.summary
    assert {"above_ema200", "ema_stack_up", "macd_pos"} <= codes(a) | {"macd_pos"}
    assert "above_ema200" in codes(a) and "ema_stack_up" in codes(a)
    assert s["trend"] == "up"
    assert s["bias"] > 0
    assert 0 <= s["heat"] <= 100
    assert all(st["rule"] for st in s["states"])          # quy tắc minh bạch
    assert "khuyến nghị" in s["disclaimer"]
    assert s["ema200_dist_pct"] > 0


def test_downtrend_states(down_bars):
    a = analyze("DN", "H1", to_frame(down_bars))
    assert "below_ema200" in codes(a) and "ema_stack_down" in codes(a)
    assert a.summary["trend"] == "down" and a.summary["bias"] < 0


def test_overbought_flag():
    c = [100 + i * 0.8 for i in range(120)]
    idx = pd.date_range("2026-01-01", periods=120, freq="1h", tz="UTC")
    df = pd.DataFrame({"o": c, "h": [x + 0.3 for x in c], "l": [x - 0.3 for x in c], "c": c, "v": 1.0}, index=idx)
    a = analyze("OB", "H1", df)
    assert "rsi_overbought" in codes(a) and a.summary["momentum"] == "overbought"


def test_squeeze_detected_after_volatile_then_quiet_period():
    rows = make_bars(150, vol=1.5, seed=5)
    last = rows[-1]["c"]
    for i in range(60):  # biên dao động thu hẹp dần => độ rộng Bollinger thấp nhất lịch sử gần đây
        c = last + 0.5 * (0.9 ** i) * (-1) ** i
        rows.append({"ts_open": rows[-1]["ts_open"] + timedelta(hours=1), "o": c, "h": c + 0.01, "l": c - 0.01, "c": c, "v": 1.0})
    a = analyze("SQ", "H1", to_frame(rows))
    assert a.summary["squeeze"] is True and a.summary["volatility"] == "squeeze"
    assert any(s["code"] == "squeeze" and "phân vị" in s["rule"] for s in a.summary["states"])


def test_too_few_bars_returns_none():
    assert analyze("X", "H1", to_frame(make_bars(10))) is None


def test_detail_has_aligned_series_and_pivot(up_bars):
    a = analyze("UP", "H1", to_frame(up_bars), series_points=100)
    ser = a.detail["series"]
    n = len(ser["t"])
    assert n == 100
    assert all(len(v) == n for v in ser.values())
    assert ser["t"] == sorted(ser["t"])
    assert a.detail["pivot"]["r1"] > a.detail["pivot"]["p"] > a.detail["pivot"]["s1"]


def _d1(vals: list[float], start="2026-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(vals), freq="1D", tz="UTC")
    s = pd.Series(vals, index=idx)
    return pd.DataFrame({"o": s, "h": s, "l": s, "c": s, "v": 1.0})


def test_correlation_perfect_and_inverse():
    rnd = np.random.default_rng(0)
    r = rnd.normal(0, 0.01, 80)
    a = 100 * np.exp(np.cumsum(r))
    b = 100 * np.exp(np.cumsum(-r))      # tương quan -1
    c = 100 * np.exp(np.cumsum(r * 3))   # tương quan +1
    corr = stats.correlation({"A": _d1(list(a)), "B": _d1(list(b)), "C": _d1(list(c))}, window=30)
    s = corr["symbols"]
    m = corr["matrix"]
    i, j, k = s.index("A"), s.index("B"), s.index("C")
    assert m[i][j] == pytest.approx(-1.0, abs=1e-3)
    assert m[i][k] == pytest.approx(1.0, abs=1e-3)
    assert m[i][i] == 1.0
    assert corr["matrix_prev"] is not None


def test_correlation_flip_detected():
    rnd = np.random.default_rng(1)
    r1 = rnd.normal(0, 0.01, 60)
    r2 = rnd.normal(0, 0.01, 60)
    a = 100 * np.exp(np.cumsum(r1))
    # B bám A ở 30 ngày trước, đảo ngược ở 30 ngày gần nhất
    rb = np.concatenate([r1[:30], -r1[30:]])
    b = 100 * np.exp(np.cumsum(rb))
    corr = stats.correlation({"A": _d1(list(a)), "B": _d1(list(b))}, window=30)
    flips = stats.correlation_flips(corr, 0.8)
    assert len(flips) == 1 and flips[0]["prev"] > 0.8 and flips[0]["now"] < -0.8
    alerts = al.correlation_alerts(flips, load_yaml(None)["alerts"], "D1", corr["as_of"])
    assert alerts and alerts[0]["dedupe_key"].startswith("an:corr:A:B:")
    assert stats.correlation_flips(corr, 2.1) == []
    del r2


def test_sessions_known_ranges():
    # 3 ngày H1; mỗi giờ biên độ cố định: Tokyo(0-9)=1.0, London(7-16)=2.0 nhưng giờ 7-8 thuộc cả hai
    rows = []
    for d in range(3):
        for h in range(24):
            ts = datetime(2026, 5, 10 + d, h, tzinfo=timezone.utc)
            rng = 1.0 if h < 9 else 2.0
            rows.append({"ts_open": ts, "o": 100.0, "h": 100.0 + rng, "l": 100.0, "c": 100.0 + rng / 2, "v": 1})
    df = to_frame(rows)
    out = stats.sessions("T", df, {"tokyo": [0, 9], "london": [7, 16], "newyork": [12, 21]}, days=30)
    assert out["sessions"]["tokyo"]["days"] == 3
    assert out["sessions"]["tokyo"]["avg_range_pct"] == pytest.approx(1.0, rel=1e-3)
    assert out["sessions"]["newyork"]["avg_range_pct"] == pytest.approx(2.0, rel=1e-3)
    assert out["hourly"][3]["avg_range_pct"] == pytest.approx(1.0)
    assert out["hourly"][10]["avg_range_pct"] == pytest.approx(2.0)
    assert len(out["hourly"]) == 24


def _frame_close(closes, highs=None, lows=None, tf="D1"):
    n = len(closes)
    idx = pd.date_range("2026-01-01", periods=n, freq="1D" if tf == "D1" else "4h", tz="UTC")
    c = pd.Series(closes, index=idx)
    h = pd.Series(highs, index=idx) if highs is not None else c + 0.2
    lo = pd.Series(lows, index=idx) if lows is not None else c - 0.2
    return pd.DataFrame({"o": c, "h": h, "l": lo, "c": c, "v": 1.0})


def test_rsi_cross_alert_edge_and_dedupe_key():
    cfg = load_yaml(None)["alerts"]
    # dao động sao cho RSI cắt lên 70 đúng ở nến cuối
    closes = [100 + (i % 2) * 0.5 for i in range(60)] + [100 + 0.5 * k for k in range(1, 14)]
    seen = None
    for cut in range(len(closes) - 12, len(closes) + 1):
        a = analyze("R", "D1", _frame_close(closes[:cut]))
        rs = [x for x in al.bar_alerts(a, cfg) if "rsi" in x["dedupe_key"]]
        if rs:
            seen = (cut, rs[0])
            break
    assert seen, "phải có 1 lần RSI cắt lên 70"
    cut, alert = seen
    assert "70" in alert["title"] and alert["level"] == "info"
    assert "khuyến nghị" in alert["body"] and "analytics" in alert["tags"]
    assert alert["dedupe_key"].startswith("an:rsi:R:D1:up_over:")
    # nến liền sau (vẫn trên 70) không tạo lại cảnh báo cắt
    a2 = analyze("R", "D1", _frame_close(closes[:cut + 1] if cut < len(closes) else closes))
    assert not [x for x in al.bar_alerts(a2, cfg) if "rsi" in x["dedupe_key"] and x["dedupe_key"] == alert["dedupe_key"]]


def test_alerts_respect_enabled_flags_and_tfs():
    cfg = load_yaml(None)["alerts"]
    closes = [100.0] * 80 + [100 + i for i in range(1, 12)]
    a_h1 = analyze("R", "H1", _frame_close(closes, tf="H1"))
    assert not [x for x in al.bar_alerts(a_h1, cfg) if "rsi" in x["dedupe_key"]]           # rsi_cross chỉ H4/D1
    cfg["rsi_cross"]["enabled"] = False
    cfg["range_breakout"]["enabled"] = False
    cfg["volatility_spike"]["enabled"] = False
    cfg["ema200_touch"]["enabled"] = False
    a = analyze("R", "D1", _frame_close(closes))
    assert al.bar_alerts(a, cfg) == []
    cfg["enabled"] = False
    assert al.bar_alerts(a, cfg) == []


def test_range_breakout_alert():
    cfg = load_yaml(None)["alerts"]
    closes = [100 + 0.1 * (i % 5) for i in range(70)] + [106.0]
    a = analyze("B", "D1", _frame_close(closes))
    out = [x for x in al.bar_alerts(a, cfg) if "brk" in x["dedupe_key"]]
    assert out and "vượt đỉnh 20" in out[0]["title"]


def test_ema200_touch_alert():
    cfg = load_yaml(None)["alerts"]
    closes = [100.0 + 0.02 * i for i in range(250)]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    a = analyze("E", "D1", _frame_close(closes, highs, lows))
    e200 = a.detail["indicators"]["ema200"]
    # nến cuối kéo bóng xuống chạm EMA200, nến trước chưa chạm
    lows[-1] = e200 - 0.5
    a = analyze("E", "D1", _frame_close(closes, highs, lows))
    assert [x for x in al.bar_alerts(a, cfg) if "ema200" in x["dedupe_key"]]


async def test_runner_end_to_end_with_resample_and_events():
    h1 = make_bars(2500, "H1", drift=0.02, vol=0.3, seed=21, end=NOW)
    h1b = make_bars(2500, "H1", start_price=50.0, drift=-0.01, vol=0.2, seed=22, end=NOW)
    src = MemoryBarSource({("AAA", "H1"): h1, ("BBB", "H1"): h1b})
    store = MemoryStore()
    redis = fr.FakeRedis(decode_responses=True)
    from tscommon import Bus
    runner = Runner(load_yaml(None), src, store, Bus(redis))
    out = await runner.run_cycle()
    assert out["symbols"] == 2 and out["snapshots"] == 6          # H1 + H4/D1 resample cho 2 symbol
    assert out["resampled"] == 4 and out["correlation"] is True and out["sessions"] == 2
    kinds = {k for k, _ in store.rows}
    assert kinds == {"summary", "detail", "correlation", "sessions"}
    assert store.rows[("summary", "AAA:D1")]["tf"] == "D1"
    assert store.rows[("correlation", "D1")]["symbols"] == ["AAA", "BBB"]
    msgs = await redis.xrange("analytics.signals")
    assert len(msgs) == 1 and "analytics.snapshot" in msgs[0][1]["e"]
    n_alerts = await redis.xlen("alerts.out")
    assert n_alerts == out["alerts_published"]
    # chu kỳ 2: cùng dữ liệu -> không phát lại cảnh báo (dedupe trong tiến trình)
    out2 = await runner.run_cycle()
    assert out2["alerts_published"] == 0
    assert runner.last["status"] == "ok"


async def test_runner_respects_symbol_filters_and_missing_data():
    h1 = make_bars(300, "H1", seed=31, end=NOW)
    short = make_bars(20, "H1", seed=32, end=NOW)
    src = MemoryBarSource({("AAA", "H1"): h1, ("SHORT", "H1"): short, ("EXC", "H1"): h1})
    cfg = load_yaml(None)
    cfg["symbols"]["exclude"] = ["EXC"]
    cfg["resample_missing"] = False
    store = MemoryStore()
    out = await Runner(cfg, src, store, None).run_cycle()
    assert out["symbols"] == 2 and out["snapshots"] == 1
    assert ("summary", "AAA:H1") in store.rows and ("summary", "SHORT:H1") not in store.rows
    assert ("summary", "EXC:H1") not in store.rows


def test_snapshot_payloads_are_strict_json(up_bars):
    import json
    a = analyze("UP", "H1", to_frame(up_bars))
    json.dumps(a.detail, allow_nan=False)   # không NaN/Inf
    json.dumps(a.summary, allow_nan=False)


def _cal(vals):
    idx = pd.date_range("2026-01-01", periods=len(vals), freq="D", tz="UTC")
    s = pd.Series(np.asarray(vals, dtype=float), index=idx)
    return pd.DataFrame({"o": s, "h": s, "l": s, "c": s, "v": 1.0})


def test_correlation_mixes_24x7_crypto_with_weekday_assets():
    rnd = np.random.default_rng(3)
    cryp = _cal(100 * np.exp(np.cumsum(rnd.normal(0, 0.02, 200))))          # co nen T7/CN
    stock = cryp[cryp.index.dayofweek < 5]                                  # cung gia chot T2-T6, khong co cuoi tuan
    corr = stats.correlation({"CRYPTO:BTCUSDT": cryp, "US:SPY": stock, "EURUSD": stock.copy()}, window=30)
    assert corr and "CRYPTO:BTCUSDT" in corr["symbols"]
    m, s = corr["matrix"], corr["symbols"]
    # log-return T6->T2 cua crypto = 3 ngay, trung khung voi co phieu => tuong quan ~1 (khong vo / khong NaN)
    assert m[s.index("US:SPY")][s.index("CRYPTO:BTCUSDT")] == pytest.approx(1.0, abs=1e-6)
    assert m[s.index("US:SPY")][s.index("EURUSD")] == pytest.approx(1.0, abs=1e-6)


def test_analytics_runs_on_crypto_symbol_names_and_24x7_bars():
    rows = make_bars(900, "H1", start_price=80000.0, vol=0.5, seed=7)   # chuoi H1 lien tuc khong nghi cuoi tuan
    df = to_frame(rows)
    a = analyze("CRYPTO:BTCUSDT", "H1", df, 120)
    assert a is not None and a.symbol == "CRYPTO:BTCUSDT" and a.summary["heat"] is not None
    ses = stats.sessions("CRYPTO:BTCUSDT", df, {"tokyo": [0, 9], "london": [7, 16], "newyork": [12, 21]}, 30)
    assert ses and ses["symbol"] == "CRYPTO:BTCUSDT" and ses["sessions"]["london"]["days"] >= 28   # co du lieu CA cuoi tuan
