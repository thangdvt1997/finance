"""GOLDEN TEST: 3 ảnh mẫu XAUUSD M15 (plan1/Lệnh Sell.docx) -> detector phải bắt đúng nến kích hoạt (dung sai ±2 nến).

Dữ liệu: tests/fixtures/xauusd_m15_gcf.csv (UTC). Giờ trên ảnh là giờ sàn = UTC+3 (xác định bằng đối chiếu các đỉnh/đáy ảnh với dữ liệu).
Nến kích hoạt kỳ vọng (ts_open UTC) đọc từ ảnh:
  KB-2 (ảnh 1, nêm)        : nến đỏ nhấn chìm phá cạnh dưới  2026-10-02 00:00 UTC (= 2 Oct 03:00 giờ sàn)
  KB-1 (ảnh 2)             : nến nhấn chìm tại đỉnh (5)      2026-10-05 11:30 UTC (= 5 Oct 14:30 giờ sàn)
  KB-3 (ảnh 3, vai-đầu-vai): cụm 3 nến nén ở đường cổ        2026-09-27 23:45 UTC (= 28 Sep 02:45 giờ sàn), mở cửa tuần sau cuối tuần
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pattern_engine.detector import Detector

TOL_BARS = 2
STEP = timedelta(minutes=15)

GOLDEN = [
    ("KB-3", datetime(2026, 9, 27, 23, 45, tzinfo=timezone.utc), "ảnh 3: vai-đầu-vai"),
    ("KB-2", datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc), "ảnh 1: nêm"),
    ("KB-1", datetime(2026, 10, 5, 11, 30, tzinfo=timezone.utc), "ảnh 2"),
]


@pytest.fixture(scope="module")
def events(xau_bars, specs):
    d = Detector("XAUUSD", "M15", specs)
    return d.feed_many(xau_bars)


@pytest.mark.parametrize("pattern,expected,note", GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_trigger(events, xau_bars, pattern, expected, note):
    idx = {b.ts: n for n, b in enumerate(xau_bars)}
    assert expected in idx, "fixture thiếu nến kỳ vọng"
    hits = [e for e in events if e.pattern == pattern and e.state == "triggered"
            and abs(idx[e.bar_ts] - idx[expected]) <= TOL_BARS]
    assert hits, f"{pattern} ({note}) không kích hoạt trong ±{TOL_BARS} nến quanh {expected}: " \
                 f"{[(e.pattern, e.bar_ts.isoformat()) for e in events if e.state == 'triggered']}"
    e = hits[0]
    assert all(s["ok"] for s in e.steps), "checklist phải thoả toàn bộ khi kích hoạt"
    assert e.levels["sl"] > e.levels["entry"] > e.levels["tp_1r"], "SL trên giá vào, TP dưới (Sell)"
    assert e.levels["tp_2r"] < e.levels["tp_1r"] and e.levels["tp_3r"] < e.levels["tp_2r"]
    assert e.ts == e.bar_ts + STEP, "ts = lúc nến đóng"


def test_triggered_is_preceded_by_armed(events):
    """Mỗi triggered phải có armed trước đó cùng họ setup (vòng đời forming/armed -> triggered)."""
    for t in (e for e in events if e.state == "triggered"):
        fam = ":".join(t.setup_id.split(":")[:2])
        prior = [e for e in events if e.state == "armed" and ":".join(e.setup_id.split(":")[:2]) == fam and e.bar_index < t.bar_index]
        assert prior, f"{t.setup_id} không có armed trước"


def test_signals_are_info_only(events):
    for e in events:
        p = e.to_payload()
        assert p["info_only"] is True and p["side"] == "sell" and "disclaimer" in p
        assert p["state"] in ("forming", "armed", "triggered", "invalid")


def test_report_false_positives_in_sample_windows(events, xau_bars):
    """Không khẳng định 0 FP (mẫu quá nhỏ) — ghi nhận số trigger NGOÀI nến kỳ vọng để theo dõi; phải ít (<= 3 trên ~1290 nến)."""
    exp = {(p, t) for p, t, _ in GOLDEN}
    idx = {b.ts: n for n, b in enumerate(xau_bars)}
    extra = [e for e in events if e.state == "triggered"
             and not any(e.pattern == p and abs(idx[e.bar_ts] - idx[t]) <= TOL_BARS for p, t in exp)]
    assert len(extra) <= 3, [(e.pattern, e.bar_ts.isoformat()) for e in extra]
