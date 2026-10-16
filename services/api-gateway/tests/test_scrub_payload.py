from api_gateway.app import _scrub_payload
from tscommon.sources import scrub_obj


def test_scrub_payload_tuong_duong_scrub_obj():
    for p in ({"symbol": "EURUSD", "bid": 1.1, "ask": 1.2, "ts": "2026-10-15T10:00:00Z", "source": "dukascopy", "provider": "x", "v": 3},
              {"symbol": "XAUUSD", "bid": 2, "ask": 3, "source": "mt5", "n": None},
              {"symbol": "A", "x": {"source": "yahoo"}}):
        for _ in range(2):   # lần 2 đi qua memo
            assert _scrub_payload(p) == scrub_obj(p)
    # cùng chữ ký, số khác -> số mới, không dính memo cũ
    assert _scrub_payload({"symbol": "EURUSD", "bid": 9.0})["bid"] == 9.0
