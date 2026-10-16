from datetime import datetime, timezone

import pytest

from data_keeper import histload as hl


def test_source_for_dung_chuoi():
    assert hl.source_for("EURUSD") == "canon:mt5:100000001"
    assert hl.source_for("us500") == "canon:mt5:100000001"
    assert hl.source_for("AUDCAD") == "canon:mt5:100000001-feed"
    assert hl.source_for("NZDMXN") == "canon:mt5:100000001-feed"


def test_parse_retention():
    r = hl.parse_retention("M1=30,D1=all")
    assert r["M1"] == 30 and r["D1"] is None and r["M5"] == hl.RETENTION_DAYS["M5"]
    with pytest.raises(ValueError):
        hl.parse_retention("X9=1")


def test_window_start_and_lowest_tf():
    last = datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert hl.window_start(last, None) is None
    assert (last - hl.window_start(last, 60)).days == 60
    assert hl.lowest_tf("AUDCAD", {"M1", "M5", "H1"}) == "M1"
    assert hl.lowest_tf("NZDMXN", {"M5", "H1", "D1"}) == "M5"


def test_guard_tam_dung_khi_p95_xau():
    seq = iter([0.9, 0.7, 0.3])
    sleeps = []
    g = hl.Guard(every=0, measure=lambda: next(seq), sleep=sleeps.append)
    g.wait_ok()
    assert g.pauses == 2 and sleeps == [60, 60] and g.last == 0.3


def test_guard_tat_hoac_khong_do_duoc():
    hl.Guard(enabled=False, measure=lambda: 9).wait_ok()
    g = hl.Guard(every=0, measure=lambda: None)
    g.wait_ok()
    assert g.pauses == 0


def _h1(start, n):
    pd = pytest.importorskip("pandas")
    ts = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts_open": ts, "o": range(n), "h": [i + 2 for i in range(n)], "l": [i - 1 for i in range(n)],
                         "c": [i + 1 for i in range(n)], "v": [1.0] * n})


def test_resample_h4_d1_moc_utc_va_bo_bucket_chua_du():
    pytest.importorskip("pandas")
    h1 = _h1("2026-10-12 22:00", 30)  # 22:00 ngay 12 -> 03:00 ngay 14 (cuoi = 04:00 ngay 14)
    h4 = hl.resample_utc(h1, "H4")
    assert [t.hour for t in h4["ts_open"]] == [20, 0, 4, 8, 12, 16, 20, 0]  # bucket 04:00 ngay 14 chua du (ket thuc 08:00 > 04:00)
    assert h4.iloc[0]["o"] == 0 and h4.iloc[0]["h"] == 3 + 0  # 20:00 bucket chi co nen 22:00,23:00
    d1 = hl.resample_utc(h1, "D1")
    assert [t.day for t in d1["ts_open"]] == [12, 13]  # ngay 14 chua dong -> bo
    assert d1.iloc[1]["v"] == 24.0


def test_resample_w1_mn1():
    pytest.importorskip("pandas")
    h1 = _h1("2026-09-28 00:00", 24 * 40)
    w1 = hl.resample_utc(h1, "W1")
    assert all(t.weekday() == 0 for t in w1["ts_open"])
    mn = hl.resample_utc(h1, "MN1")
    assert [t.month for t in mn["ts_open"]] == [9, 10]
