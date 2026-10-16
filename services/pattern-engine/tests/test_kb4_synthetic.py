"""KB-4 (6 mục trong conversation.txt) chưa có ảnh mẫu -> kiểm tra bằng chuỗi nến TỔNG HỢP tất định dựng đúng 6 mục:
1 đi ngang  2 nến thân rất dài phá đáy  3 chuỗi nến đỏ  4 đi ngang mới  5 ba đỉnh giảm dần  6 cụm nến thân nhỏ nén -> Sell."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from pattern_engine.detector import Detector
from pattern_engine.series import Bar

T0 = datetime(2026, 3, 2, tzinfo=timezone.utc)


def build(trend: bool = False) -> tuple[list[Bar], dict]:
    px: list[tuple[float, float, float, float]] = []   # o,h,l,c

    def add(o, c, wick=0.25):
        px.append((o, max(o, c) + wick, min(o, c) - wick, c))

    # (1) đi ngang 70 nến quanh 100 (biên ±0.5)
    for k in range(70):
        if trend:       # biến thể phủ định: thay vùng đi ngang bằng xu hướng tăng đều (mục 1 không thoả)
            add(70 + 0.43 * k, 70 + 0.43 * (k + 1))
        else:
            a, b = 100 + 0.5 * math.sin(k * math.pi / 4), 100 + 0.5 * math.sin((k + 1) * math.pi / 4)
            add(a, b)
    idx = {"break": len(px)}
    add(100.0, 96.0, 0.1)                                   # (2) nến thân rất dài phá đáy hộp
    c = 96.0
    for _ in range(6):                                      # (3) chuỗi nến đỏ liên tiếp
        add(c, c - 1.7, 0.15)
        c -= 1.7
    low = c                                                 # ~85.8
    for _ in range(5):                                      # hồi lên (4)
        add(c, c + 1.3, 0.2)
        c += 1.3
    # (4)(5) đi ngang mới: đỉnh 1 = đỉnh cuối nhịp hồi (c); thêm 2 đỉnh thấp dần; đáy giữ trên đáy sóng dẫn
    def walk(target: float, n: int):
        nonlocal c
        step = (target - c) / n
        for _ in range(n):
            add(c, c + step, 0.2)
            c += step

    walk(low + 2.4, 4)           # xuống đáy giữa 1
    top2 = low + 5.8
    walk(top2, 4)                # lên đỉnh 2 (thấp hơn đỉnh 1 ~ 0.7)
    walk(low + 2.4, 4)           # xuống đáy giữa 2
    walk(low + 5.1, 3)           # lên đỉnh 3 (thấp hơn đỉnh 2 ~ 0.7) — đỉnh tạm thời
    idx["top3"] = len(px) - 1
    for k in range(3):                                      # (6) cụm 3 nến thân nhỏ
        add(c, c + (0.04 if k % 2 else -0.04), 0.12)
    idx["cluster_end"] = len(px) - 1
    bars = [Bar(T0 + timedelta(minutes=15 * i), o, h, l, cc, 100.0) for i, (o, h, l, cc) in enumerate(px)]
    return bars, idx


def test_kb4_synthetic_triggers_on_third_compression_bar(specs):
    bars, idx = build()
    d = Detector("SYNTH", "M15", specs, ["KB-4"])
    ev = d.feed_many(bars)
    trig = [e for e in ev if e.state == "triggered"]
    assert trig, [(e.state, e.bar_index, e.reason) for e in ev]
    assert abs(trig[0].bar_index - idx["cluster_end"]) <= 1
    assert all(s["ok"] for s in trig[0].steps)
    assert trig[0].levels["sl"] > trig[0].levels["entry"] > trig[0].levels["tp_1r"]


def test_kb4_does_not_fire_without_sideways_box(specs):
    """Mục 1 không thoả (xu hướng tăng thay vì đi ngang) -> KB-4 không được kích hoạt."""
    bars, _ = build(trend=True)
    d = Detector("SYNTH", "M15", specs, ["KB-4"])
    assert not [e for e in d.feed_many(bars) if e.state == "triggered"]


def test_kb4_does_not_fire_without_compression_cluster(specs):
    """Thiếu mục 6 (nến cuối thân lớn, không nén) -> chỉ armed, không triggered."""
    bars, idx = build()
    k = idx["cluster_end"]
    for j in range(k - 2, k + 1):
        b = bars[j]
        bars[j] = Bar(b.ts, b.o, b.h + 1.0, b.l - 1.0, b.o + (1.4 if j % 2 else -1.4), b.v)
    d = Detector("SYNTH", "M15", specs, ["KB-4"])
    assert not [e for e in d.feed_many(bars) if e.state == "triggered"]
