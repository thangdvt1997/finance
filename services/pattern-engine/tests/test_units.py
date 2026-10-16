from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pattern_engine.common import Ctx, bear_engulf, linfit, small_cluster
from pattern_engine.series import Bar, Series
from pattern_engine.specs import load_specs
from pattern_engine.zigzag import ZigZag

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)


def mk(rows):
    s = Series(14, 0.8)
    for n, (o, h, l, c) in enumerate(rows):
        s.append(Bar(T0 + timedelta(minutes=15 * n), o, h, l, c))
    return s


def flat(n, base=100.0, rng=1.0):
    """n nến nhỏ quanh `base` (ATR ~ rng)."""
    return [(base, base + rng / 2, base - rng / 2, base + (0.1 if k % 2 else -0.1)) for k in range(n)]


@pytest.fixture(scope="module")
def P():
    return next(iter(load_specs().values()))["params"]


def test_atr_wilder_matches_reference():
    rows = [(10, 11, 9, 10.5), (10.5, 12, 10, 11), (11, 11.5, 10.2, 10.4), (10.4, 10.9, 9.5, 9.8)]
    s = mk(rows)
    tr = [2, 2.0, 1.3, 1.4]   # TR1 dùng đóng cửa trước: max(2, |12-10.5|, |10-10.5|)=2 ; ...
    # đến i<14 ATR = trung bình TR tích luỹ
    assert s.atr[0] == pytest.approx(2.0)
    assert s.atr[1] == pytest.approx((2.0 + 2.0) / 2)
    assert s.atr[3] == pytest.approx((2.0 + 2.0 + 1.3 + 1.4) / 4)
    _ = tr


def test_bear_engulf_requires_body_cover_and_close_below_prev_low(P):
    base = flat(30)
    atr = 1.0
    # nến trước: xanh nhỏ 100.0 -> 100.4 ; nến nhấn chìm: mở 100.45 đóng 98.0 (thân ~2.45 ATR)
    s = mk(base + [(100.0, 100.5, 99.9, 100.4), (100.45, 100.5, 97.9, 98.0)])
    ok, info = bear_engulf(s, len(s) - 1, P)
    assert ok and info["body_atr"] > 1.5
    # thân quá ngắn -> không phải
    s2 = mk(base + [(100.0, 100.5, 99.9, 100.4), (100.45, 100.5, 99.5, 99.6)])
    assert not bear_engulf(s2, len(s2) - 1, P)[0]
    # đóng cửa không dưới đáy nến trước -> không phải
    s3 = mk(base + [(100.0, 100.5, 96.0, 100.4), (100.45, 100.5, 98.0, 98.2)])
    assert not bear_engulf(s3, len(s3) - 1, P)[0]
    _ = atr


def test_small_cluster(P):
    s = mk(flat(30) + [(100.0, 100.3, 99.8, 100.1), (100.1, 100.3, 99.9, 100.0), (100.0, 100.2, 99.8, 100.05)])
    ok, info = small_cluster(s, len(s) - 1, P)
    assert ok and info["range_atr"] <= P["cluster_range_atr"]
    s2 = mk(flat(30) + [(100.0, 103, 99.8, 102.5), (102.5, 103, 99.9, 100.0), (100.0, 100.2, 99.8, 100.05)])
    assert not small_cluster(s2, len(s2) - 1, P)[0]


def test_zigzag_adaptive_threshold_scales_with_atr():
    """Cùng dao động tuyệt đối nhưng ATR lớn hơn -> ít pivot hơn (ngưỡng theo ATR, không theo pip)."""
    def pivots(scale):
        z = ZigZag(2.0)
        s = Series(14, 0.8)
        px = 100.0
        for n in range(200):
            px += scale * (3 if (n // 10) % 2 == 0 else -3) / 3
            b = Bar(T0 + timedelta(minutes=15 * n), px, px + scale, px - scale, px)
            i = s.append(b)
            z.update(i, b.o, b.h, b.l, b.c, s.atr[i])
        return len(z.pivots)
    assert pivots(1.0) >= pivots(8.0)


def test_linfit_exact_line():
    b, a, x0 = linfit([(10, 5.0), (12, 7.0), (20, 15.0)])
    assert b == pytest.approx(1.0) and a == pytest.approx(5.0) and x0 == 10


def test_specs_complete():
    sp = load_specs()
    assert set(sp) == {"KB-1", "KB-2", "KB-3", "KB-4"}
    for k, v in sp.items():
        assert v["side"] == "sell" and v["steps"] and v["params"]["lead_min_atr"] > 0
        n = max(int(i) for i in v["steps"])
        assert sorted(int(i) for i in v["steps"]) == list(range(1, n + 1)), k   # bước liên tục 1..n


def test_overrides_apply():
    sp = load_specs(overrides={"common": {"lead_min_atr": 9.0}, "KB-2": {"retr_max": 0.9}})
    assert sp["KB-1"]["params"]["lead_min_atr"] == 9.0 and sp["KB-2"]["params"]["retr_max"] == 0.9
    assert sp["KB-1"]["params"].get("retr_max") != 0.9


def test_ctx_dataclass_defaults():
    s = mk(flat(5))
    c = Ctx(s, [], 4)
    assert c.fine is None and c.cache == {}
