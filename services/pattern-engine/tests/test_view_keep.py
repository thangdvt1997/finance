"""Giới hạn ZigZag.VIEW_KEEP (chống O(n^2) khi backtest nhiều năm) không đổi kết quả: mẫu hình chỉ nhìn ~30 pivot gần nhất."""
from pattern_engine.detector import Detector
from pattern_engine.zigzag import ZigZag

from .conftest import sig_key


def test_view_keep_does_not_change_signals(xau_bars, specs, monkeypatch):
    monkeypatch.setattr(ZigZag, "VIEW_KEEP", 10**9)
    full = [sig_key(s) for s in Detector("XAUUSD", "M15", specs).feed_many(xau_bars)]
    monkeypatch.setattr(ZigZag, "VIEW_KEEP", 48)
    cut = [sig_key(s) for s in Detector("XAUUSD", "M15", specs).feed_many(xau_bars)]
    assert full and full == cut
