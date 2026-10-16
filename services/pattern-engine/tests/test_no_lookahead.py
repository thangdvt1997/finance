"""CHỨNG MINH không look-ahead / không repaint:
kết quả tại nến i KHÔNG đổi khi thêm (hoặc thay bằng rác) các nến tương lai.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from pattern_engine.detector import Detector
from pattern_engine.series import Bar

from .conftest import sig_key


def run(bars, specs, symbol="XAUUSD"):
    d = Detector(symbol, "M15", specs)
    return d.feed_many(bars), d


@pytest.mark.parametrize("cut", [250, 480, 700, 900, 1060, 1150])
def test_prefix_results_identical(xau_bars, specs, cut):
    """Chạy trên toàn chuỗi vs chạy chỉ trên prefix [:cut]: mọi sự kiện có bar_index < cut phải giống hệt nhau."""
    full, _ = run(xau_bars, specs)
    part, _ = run(xau_bars[:cut], specs)
    a = [sig_key(s) for s in full if s.bar_index < cut]
    b = [sig_key(s) for s in part]
    assert a == b
    assert len(part) > 0 or cut < 700   # đủ dữ liệu thì phải có sự kiện (tránh test rỗng vô nghĩa)


def test_future_garbage_does_not_change_past(xau_bars, specs):
    """Thay TOÀN BỘ nến sau mốc bằng dữ liệu ngẫu nhiên: sự kiện trước mốc không đổi."""
    cut = 1100
    rnd = random.Random(7)
    junk = []
    last = xau_bars[cut - 1]
    for b in xau_bars[cut:]:
        o = last.c * (1 + rnd.uniform(-0.01, 0.01))
        c = o * (1 + rnd.uniform(-0.01, 0.01))
        junk.append(Bar(b.ts, o, max(o, c) * 1.002, min(o, c) * 0.998, c, 1.0))
        last = junk[-1]
    full, _ = run(xau_bars, specs)
    alt, _ = run(xau_bars[:cut] + junk, specs)
    assert [sig_key(s) for s in full if s.bar_index < cut] == [sig_key(s) for s in alt if s.bar_index < cut]


def test_zigzag_pivots_append_only(xau_bars, specs):
    """Pivot đã xác nhận không bao giờ bị sửa/xoá khi có thêm nến (không repaint)."""
    d = Detector("XAUUSD", "M15", specs)
    snaps: list[tuple] = []
    for n, b in enumerate(xau_bars):
        d.feed(b)
        if n % 50 == 0:
            snaps.append(tuple((p.i, p.price, p.kind, p.conf_i) for z in d.zzs for p in z.pivots))
    for a, b in zip(snaps, snaps[1:]):
        # mỗi thang có danh sách riêng; prefix của từng thang phải được giữ nguyên -> kiểm tra theo từng phần tử tồn tại ở cả hai
        assert set(a) <= set(b)


def test_emitted_events_never_mutate(xau_bars, specs):
    """Sự kiện đã phát (state, score, levels...) là bất biến theo thời gian: replay hai lần cho cùng kết quả (tất định)."""
    a, _ = run(xau_bars, specs)
    b, _ = run(xau_bars, specs)
    assert [sig_key(s) for s in a] == [sig_key(s) for s in b]


def test_ignores_duplicate_and_out_of_order_bars(xau_bars, specs):
    d = Detector("XAUUSD", "M15", specs)
    d.feed_many(xau_bars[:300])
    n = len(d.s)
    assert d.feed(xau_bars[299]) == [] and d.feed(xau_bars[10]) == []
    assert len(d.s) == n


def test_invalid_bars_rejected(specs):
    d = Detector("XAUUSD", "M15", specs)
    b = Bar(datetime(2026, 1, 1, tzinfo=timezone.utc), 10, 9, 11, 10)  # high < low
    assert d.feed(b) == []
    assert len(d.s) == 0
