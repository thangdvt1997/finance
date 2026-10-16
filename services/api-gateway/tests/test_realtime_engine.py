"""QuoteEngine/hub voi ~170 ma MT5 (feed mo rong): moi ma co quote chuan, khong lo ten nguon, nguon 'mt' thang nguon cu."""
from api_gateway.realtime import QuoteEngine, RtSettings


def test_engine_handles_170_symbols_and_priority():
    st = RtSettings()
    e = QuoteEngine(st.prio, st.stale_s, st.silent_s, st.max_symbols)
    now = 1_000_000.0
    syms = [f"AB{i:04d}" for i in range(170)]
    for s in syms:
        assert e.update(s, "dukascopy", 1.0, 1.1, now, now)
        assert e.update(s, "mt:mt5:100000001", 1.2, 1.3, now, now + 1)    # nguon mt uu tien hon dukascopy
    assert len(e.cur) == 170
    assert all(q["b"] == 1.2 and q["q"] == 0 and set(q) == {"s", "b", "a", "t", "q"} for q in e.cur.values())   # khong co truong source
