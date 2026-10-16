"""Toạ độ pivot `points` trong pattern.signal (chỉ để vẽ ảnh/biểu đồ; không đổi logic phát hiện)."""
from __future__ import annotations

from datetime import datetime

import pytest

from pattern_engine.detector import Detector

EXPECT_LABELS = {"KB-1": ["", "(1)", "(2)", "(3)", "(4)"], "KB-2": ["", "(1)", "(2)"], "KB-3": ["LS", "", "H", "", "RS"]}


@pytest.fixture(scope="module")
def events(xau_bars, specs):
    return Detector("XAUUSD", "M15", specs).feed_many(xau_bars)


def test_every_signal_has_points_not_in_future(events):
    assert events
    for e in events:
        p = e.to_payload()
        assert isinstance(p["points"], list) and p["points"], e.setup_id
        ts = [datetime.fromisoformat(x["t"]) for x in p["points"]]
        assert all(t <= e.bar_ts for t in ts), "điểm cấu trúc phải thuộc nến đã đóng <= nến tín hiệu"
        assert ts == sorted(ts), "điểm theo thứ tự thời gian"
        assert all(isinstance(x["p"], float) and isinstance(x["label"], str) for x in p["points"])


def test_triggered_points_labels_and_prices(events, xau_bars):
    by_ts = {b.ts: b for b in xau_bars}
    trig = [e for e in events if e.state == "triggered"]
    assert {e.pattern for e in trig} >= {"KB-1", "KB-2", "KB-3"}
    for e in trig:
        labels = [x["label"] for x in e.points]
        assert labels[: len(EXPECT_LABELS[e.pattern])] == EXPECT_LABELS[e.pattern]
        for x in e.points:          # mỗi điểm là đỉnh (high) hoặc đáy (low) thật của nến tại t
            b = by_ts[datetime.fromisoformat(x["t"])]
            assert x["p"] == pytest.approx(b.h) or x["p"] == pytest.approx(b.l)
        if e.pattern in ("KB-1", "KB-2"):
            assert e.points[0]["p"] == pytest.approx(e.levels["wave_high"]) and e.points[1]["p"] == pytest.approx(e.levels["wave_low"])
        if e.pattern == "KB-3":
            assert e.points[2]["p"] == pytest.approx(e.levels["head"])


def test_points_do_not_change_detection(events, xau_bars, specs):
    """Bỏ points khỏi so sánh: chuỗi sự kiện giống hệt chạy lại (points là thông tin thêm, xác định)."""
    from .conftest import sig_key
    again = Detector("XAUUSD", "M15", specs).feed_many(xau_bars)
    assert [sig_key(s) for s in again] == [sig_key(s) for s in events]
    assert [s.points for s in again] == [s.points for s in events]


def test_kb4_points(specs):
    from .test_kb4_synthetic import build
    bars, _ = build()
    trig = [e for e in Detector("SYNTH", "M15", specs, ["KB-4"]).feed_many(bars) if e.state == "triggered"]
    assert trig
    labels = [x["label"] for x in trig[0].points]
    assert labels[:2] == ["", "(1)"] and labels[2:] == [f"H{n + 1}" for n in range(len(labels) - 2)] and len(labels) >= 5
    hs = [x["p"] for x in trig[0].points[2:]]
    assert hs == sorted(hs, reverse=True), "3 đỉnh giảm dần"
