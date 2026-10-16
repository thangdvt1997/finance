from datetime import datetime, timezone

from data_keeper import sessions as S

U = timezone.utc
d = lambda *a: datetime(*a, tzinfo=U)  # noqa: E731


def test_groups():
    assert S.group_of("EURUSD") == "fx" and S.group_of("XAUUSD") == "metal" and S.group_of("DE40") == "index"
    assert S.group_of("CRYPTO:BTCUSDT") == "crypto"
    assert S.session_key("JPN225") == "index:jp" and S.session_key("US500") == "index:us"


def test_fx_week():
    assert not S.is_market_open("EURUSD", d(2026, 10, 17, 12))      # thứ 7
    assert not S.is_market_open("EURUSD", d(2026, 10, 16, 22, 30))  # T6 sau 22:00
    assert not S.is_market_open("EURUSD", d(2026, 10, 18, 21, 59))  # CN trước 22:00
    assert S.is_market_open("EURUSD", d(2026, 10, 18, 22, 0))
    assert S.is_market_open("EURUSD", d(2026, 10, 15, 22, 30))      # T5 22:30 FX mở
    assert not S.is_market_open("XAUUSD", d(2026, 10, 15, 22, 30))  # kim loại nghỉ ngày


def test_crypto_always():
    assert S.is_market_open("CRYPTO:BTCUSDT", d(2026, 10, 17, 3)) and S.is_market_open("CRYPTO:BTCUSDT", d(2026, 12, 25, 3))


def test_holiday():
    assert not S.is_market_open("EURUSD", d(2026, 12, 25, 10)) and not S.is_market_open("EURUSD", d(2027, 1, 1, 10))
    assert S.is_market_open("EURUSD", d(2026, 12, 24, 10)) and not S.is_market_open("EURUSD", d(2026, 12, 24, 22))


def test_index_regions_dst():
    # tháng 10 2026 (T5): DE40 theo Berlin (CEST=UTC+2): 08:55-17:40 local => 06:55-15:40 UTC
    assert S.is_market_open("DE40", d(2026, 10, 15, 8, 0)) and not S.is_market_open("DE40", d(2026, 10, 15, 16, 0))
    assert not S.is_market_open("DE40", d(2026, 10, 15, 6, 0))
    assert S.is_market_open("JPN225", d(2026, 10, 15, 1, 0)) and not S.is_market_open("JPN225", d(2026, 10, 15, 8, 0))
    assert not S.is_market_open("DE40", d(2026, 10, 17, 10))


def test_open_since_and_last_end():
    assert S.open_since("EURUSD", d(2026, 10, 18, 22, 10)) == 600
    assert S.open_since("EURUSD", d(2026, 10, 17, 10)) is None
    assert S.last_open_end("EURUSD", d(2026, 10, 17, 10)) == d(2026, 10, 16, 22)


def test_expected_slots_and_gaps():
    # T6 20:00 -> T7 00:00: M1 mở tới 22:00 => 120 nến
    assert S.expected_slots("EURUSD", "M1", d(2026, 10, 16, 20), d(2026, 10, 17, 0)) == 120
    g = S.session_gaps_expected("EURUSD", "H1", d(2026, 10, 16, 20), d(2026, 10, 17, 4))
    assert g == [(d(2026, 10, 16, 22), d(2026, 10, 17, 4))]
    assert S.expected_slots("CRYPTO:ETHUSDT", "H4", d(2026, 10, 15), d(2026, 10, 16)) == 6


def test_missing_slots():
    pres = {int(d(2026, 10, 15, 10, m).timestamp()) for m in range(0, 10) if m != 3}
    assert S.missing_slots("EURUSD", "M1", pres, d(2026, 10, 15, 10, 0), d(2026, 10, 15, 10, 10)) == [d(2026, 10, 15, 10, 3)]


def test_no_source_and_limited_hours():
    from datetime import datetime, timezone
    from data_keeper import sessions as S
    wed = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)
    assert S.is_market_open("EURUSD", wed)
    assert not S.is_market_open("AUDHUF", wed) and S.group_of("AUDHUF") == "nosource"
    assert S.is_market_open("USDBRL", wed) and not S.is_market_open("USDBRL", wed.replace(hour=3))
    assert S.group_of("USDBRL") == "fx"


def test_techde30_narrow_window():
    from datetime import datetime, timezone
    assert not S.is_market_open("TECHDE30", datetime(2026, 10, 16, 7, 30, tzinfo=timezone.utc))
    assert S.is_market_open("TECHDE30", datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc))
    assert not S.is_market_open("TECHDE30", datetime(2026, 10, 16, 15, 30, tzinfo=timezone.utc))
    assert S.group_of("TECHDE30") == "index"
