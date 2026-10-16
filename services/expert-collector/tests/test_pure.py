from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from expert_collector.consensus import compute_consensus
from expert_collector.diff import diff_net, net_positions
from expert_collector.models import PositionInfo, normalize_symbol
from expert_collector.reputation import (Thresholds, detect_grid, detect_history_wipe, detect_martingale,
                                         reputation_score)
from expert_collector.sources import mql5, myfxbook, rss_ideas, static_json

FX = Path(__file__).parent / "fixtures"
GOOD = {"gain_pct": 80, "max_drawdown_pct": 15, "months_active": 24, "followers": 500}


def test_normalize():
    assert normalize_symbol("eur/usd") == "EURUSD"
    assert normalize_symbol("EURUSD.m") == "EURUSD"
    assert normalize_symbol("vn:vnm") == "VN:VNM"


def test_reputation_pass_and_fail():
    th = Thresholds()
    assert reputation_score(GOOD, th).qualified
    assert not reputation_score({**GOOD, "months_active": 3}, th).qualified
    r = reputation_score({**GOOD, "max_drawdown_pct": 70}, th)
    assert not r.qualified and any("drawdown" in x for x in r.reasons)
    assert not reputation_score({**GOOD, "max_drawdown_pct": None}, th).qualified
    assert not reputation_score(GOOD, th, martingale=True).qualified
    assert not reputation_score(GOOD, th, history_wiped=True).qualified


def test_martingale_and_grid():
    trades = [{"volume": 0.1, "profit": -1}, {"volume": 0.2, "profit": -1}, {"volume": 0.4, "profit": -1},
              {"volume": 0.8, "profit": -1}, {"volume": 1.6, "profit": 5}]
    assert detect_martingale(trades)
    assert not detect_martingale([{"volume": 0.1, "profit": -1}, {"volume": 0.1, "profit": 1}] * 5)
    grid = [{"symbol": "EURUSD", "side": "buy", "entry": 1.10 - i * 0.005} for i in range(6)]
    assert detect_grid(grid)
    assert not detect_grid(grid[:3])
    rnd = [{"symbol": "EURUSD", "side": "buy", "entry": e} for e in (1.1, 1.101, 1.15, 1.152, 1.3, 1.31)]
    assert not detect_grid(rnd)


def test_history_wipe():
    hist = [{"months_active": 14, "trades": 400}]
    assert detect_history_wipe(hist, {"months_active": 2, "trades": 20})
    assert detect_history_wipe(hist, {"months_active": 14, "trades": 100})
    assert not detect_history_wipe(hist, {"months_active": 15, "trades": 420})
    assert not detect_history_wipe([], {"months_active": 1})


def _p(sym, side, vol, entry=1.0):
    return PositionInfo(symbol=sym, side=side, volume=vol, entry=entry)


def test_net_and_diff():
    a = net_positions([_p("EURUSD", "buy", 0.3), _p("EURUSD", "sell", 0.1), _p("XAUUSD", "buy", 1), _p("XAUUSD", "sell", 1)])
    assert a["EURUSD"]["side"] == "buy" and a["EURUSD"]["net_volume"] == pytest.approx(0.2)
    assert "XAUUSD" not in a  # hedge hoan toan
    b = net_positions([_p("EURUSD", "sell", 0.2), _p("GBPUSD", "buy", 0.1)])
    kinds = {(c.kind, c.symbol) for c in diff_net(a, b)}
    assert kinds == {("reverse", "EURUSD"), ("open", "GBPUSD")}
    assert [(c.kind) for c in diff_net(b, {})] == ["close", "close"]
    assert diff_net(a, a) == []


def test_consensus():
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    ts = now.isoformat()
    old = (now - timedelta(days=10)).isoformat()
    st = {"a": {"EURUSD": {"side": "buy", "ts": ts}}, "b": {"EURUSD": {"side": "buy", "ts": ts}},
          "c": {"EURUSD": {"side": "buy", "ts": ts}}, "d": {"EURUSD": {"side": "sell", "ts": ts}},
          "e": {"GBPUSD": {"side": "buy", "ts": old}}, "f": {"GBPUSD": {"side": "buy", "ts": old}},
          "g": {"GBPUSD": {"side": "buy", "ts": old}}}
    res = compute_consensus(st, now, timedelta(hours=72), 3, 0.7)  # EURUSD 3/4=.75; GBPUSD qua han
    assert [(c.symbol, c.side, c.experts) for c in res] == [("EURUSD", "buy", ["a", "b", "c"])]
    assert compute_consensus(st, now, timedelta(hours=72), 3, 0.8) == []
    assert compute_consensus(st, now, timedelta(hours=72), 4, 0.5) == []


def test_rss_parser():
    sigs = rss_ideas.parse_feed((FX / "feed.xml").read_text(encoding="utf-8"), "rss:x")
    got = {(s.symbol, s.side) for s in sigs}
    assert got == {("EURUSD", "buy"), ("VN:VNM", "buy"), ("VN:HPG", "sell"), ("XAUUSD", "sell")}
    vnm = next(s for s in sigs if s.symbol == "VN:VNM")
    assert vnm.tp == 78000 and vnm.opened_at.year == 2026
    eur = next(s for s in sigs if s.symbol == "EURUSD")
    assert eur.tp == 1.105 and eur.url.endswith("/1")


def test_classify():
    assert rss_ideas.classify_side("KEM KHA QUAN".lower().replace("kem kha quan", "kém khả quan")) == "sell"
    assert rss_ideas.classify_side("nothing") is None
    assert rss_ideas.extract_symbol_and_side("Weekly outlook") is None


def test_mql5_parser():
    html = (FX / "mql5_signal.html").read_text(encoding="utf-8")
    e = mql5.parse_signal_page(html, "https://x/s/12345")
    assert e.expert_id == "mql5:12345" and e.reputation["gain_pct"] == 85.2
    assert e.reputation["followers"] == 1340 and e.reputation["months_active"] == pytest.approx(23.9, abs=0.1)
    pos = mql5.parse_open_positions(html)
    assert [(p.symbol, p.side, p.volume) for p in pos] == [("EURUSD", "buy", 0.1), ("XAUUSD", "sell", 0.05)]
    assert pos[0].sl == 1.08 and pos[1].sl is None
    assert mql5.parse_closed_trades(html) == [{"volume": 0.1, "profit": -20}, {"volume": 0.2, "profit": -30}]
    assert mql5.parse_signal_page("<html></html>") is None


def test_myfxbook_parsers():
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    accs = myfxbook.parse_accounts(
        '{"error":false,"accounts":[{"id":7,"name":"A","username":"u","gain":50.5,"drawdown":9.9,'
        '"firstTradeDate":"10/01/2025 00:00","demo":false}]}', now)
    assert accs[0].expert_id == "myfxbook:7" and accs[0].reputation["months_active"] == pytest.approx(12.3, abs=0.2)
    tr = myfxbook.parse_open_trades(
        '{"error":false,"openTrades":[{"openTime":"10/05/2026 08:00","symbol":"EURUSD","action":"Buy",'
        '"sizing":{"type":"lots","value":0.2},"openPrice":1.09,"tp":0,"sl":1.08,"openOrderId":"9"}]}')
    assert tr[0].side == "buy" and tr[0].volume == 0.2 and tr[0].tp is None and tr[0].sl == 1.08
    assert myfxbook.parse_login('{"error":false,"session":"abc"}') == "abc"
    with pytest.raises(myfxbook.MyfxbookError):
        myfxbook.parse_login('{"error":true,"message":"Invalid"}')


def test_static_doc():
    d = static_json.parse_document({"experts": [{"expert_id": "e1", "reputation": GOOD,
                                                 "positions": [{"symbol": "eur/usd", "side": "buy", "volume": 0.1}]}]})
    assert d["e1"]["positions"][0].symbol == "EURUSD"
