from datetime import datetime, timedelta, timezone

from data_keeper.config import Settings
from data_keeper.inventory import classify

U = timezone.utc
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=U)
C = Settings()


def k(**kw):
    base = dict(tf="M1", now=NOW, last_bar=NOW - timedelta(seconds=60), last_tick=NOW, market_open=True, open_since_s=99999, cfg=C)
    base.update(kw)
    return classify(**base)[0]


def test_ok():
    assert k() == "OK"


def test_closed_never_broken():
    assert k(market_open=False, last_bar=NOW - timedelta(days=2), last_tick=None) == "CLOSED"


def test_slow_vs_broken():
    assert k(last_bar=NOW - timedelta(seconds=60 + 400)) == "SLOW"
    assert k(last_bar=NOW - timedelta(hours=2), last_tick=None) == "BROKEN"
    assert k(last_bar=NOW - timedelta(hours=2), last_tick=NOW) == "SLOW"   # tick còn tươi


def test_open_grace_and_no_data():
    assert k(last_bar=NOW - timedelta(hours=9), last_tick=None, open_since_s=60) == "SLOW"
    assert k(last_bar=None, last_tick=None) == "BROKEN"
    assert k(last_bar=None, last_tick=None, market_open=False) == "CLOSED"


def test_thin_quotes_not_broken():
    assert classify(tf="M1", now=NOW, last_bar=NOW - timedelta(hours=2), last_tick=None, market_open=True, open_since_s=99999, cfg=C, thin=True)[0] == "OK"
    assert classify(tf="M1", now=NOW, last_bar=NOW - timedelta(hours=6), last_tick=None, market_open=True, open_since_s=99999, cfg=C, thin=True)[0] == "SLOW"
    assert classify(tf="M1", now=NOW, last_bar=None, last_tick=None, market_open=True, open_since_s=99999, cfg=C, thin=True)[0] == "SLOW"
    assert k(last_bar=NOW - timedelta(hours=2), last_tick=None) == "BROKEN"   # mã thường vẫn BROKEN


def test_closed_bar_grace():
    now = datetime(2026, 10, 15, 11, 10, 43, tzinfo=U)   # 43 s sau mốc M5: nến 11:05 chưa kịp về -> vẫn OK
    assert classify(tf="M5", now=now, last_bar=datetime(2026, 10, 15, 11, 0, tzinfo=U), last_tick=now, market_open=True, open_since_s=99999, cfg=C)[0] == "OK"


def test_open_off_schedule_is_ok():
    st, note = classify(tf="M1", now=NOW, last_bar=NOW - timedelta(minutes=1), last_tick=NOW - timedelta(seconds=5), market_open=False, open_since_s=None, cfg=C)
    assert (st, note) == ("OK", "open_off_schedule")
    assert classify(tf="M1", now=NOW, last_bar=NOW - timedelta(minutes=1), last_tick=None, market_open=False, open_since_s=None, cfg=C)[0] == "CLOSED"
