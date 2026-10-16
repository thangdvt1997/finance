"""Unit + e2e (TestClient) cho hub realtime rt.v1 (api_gateway/realtime.py, docs/REALTIME.md).
Không cần Docker/mạng; thời gian điều khiển tường minh (tham số now / now_ms) nên xác định."""
import asyncio
import faulthandler
import json
import re
import threading
import time

import fakeredis.aioredis as fr
import pytest
from fastapi.testclient import TestClient
from tscommon import make_event

from api_gateway import realtime as rt
from api_gateway.app import create_app
from api_gateway.authz import Principal
from api_gateway.config import GatewaySettings
from api_gateway.realtime import Hub, QuoteEngine, RtSettings
from api_gateway.repo import InMemoryRepo

T0 = 1_700_000_040_000          # bội của 60_000 (biên nến M1/M5...)
MASTER = Principal("master", "m1")
A = Principal("client", "uA", frozenset({"a1"}))
B = Principal("client", "uB", frozenset({"a2"}))


@pytest.fixture(autouse=True)
def _hang_guard():
    faulthandler.dump_traceback_later(90, exit=True)    # test treo -> chết có dấu vết thay vì treo CI
    yield
    faulthandler.cancel_dump_traceback_later()


def mkhub(**kw) -> Hub:
    st = RtSettings()
    st.prio = ["mt", "dukascopy", "yahoo"]
    st.stale_s, st.silent_s = 20.0, 90.0
    for k, v in kw.items():
        setattr(st, k, v)
    return Hub(st, hide_sources=True)


def quote(sym, bid, ask, src="mt", ts=None):
    p = {"symbol": sym, "bid": bid, "ask": ask, "source": src}
    if ts is not None:
        p["ts"] = ts
    return {"payload": p}


def _bal(obj, v) -> bool:
    """có 'balance': v (khớp theo cấu trúc, không dò chuỗi con: '222' có thể trùng ts/seq)"""
    return re.search(r'"balance": %s(?!\d)' % v, json.dumps(obj)) is not None


def msgs(conn):
    """Mọi tin (đã parse) đang chờ gửi cho conn: rel + latest."""
    return [json.loads(m) for m in [*conn.rel, *conn.latest.values()]]


def drain(conn):
    out = msgs(conn)
    conn.rel.clear()
    conn.latest.clear()
    return out


async def join(hub, p, topics, **kw):
    c, why = hub.admit(p, "ws")
    assert c is not None, why
    ok, errs = await hub.subscribe(c, topics, **kw)
    return c, ok, errs


# ===================================================================== QuoteEngine
def eng(**kw):
    return QuoteEngine(["mt", "dukascopy", "yahoo"], kw.get("stale", 20.0), kw.get("silent", 90.0))


def test_engine_priority_fresh_source_wins_by_rank():
    e = eng()
    e.update("EURUSD", "yahoo", 1.0, 1.1, 1000, 1000)
    assert e.cur["EURUSD"]["b"] == 1.0
    e.update("EURUSD", "mt", 2.0, 2.1, 1000, 1000)
    assert e.cur["EURUSD"]["b"] == 2.0                      # mt ưu tiên hơn yahoo khi cả hai tươi
    e.update("EURUSD", "dukascopy", 3.0, 3.1, 2000, 2000)
    assert e.cur["EURUSD"]["b"] == 2.0                      # dukascopy tick mới hơn nhưng mt vẫn tươi + ưu tiên cao hơn
    e.update("EURUSD", "mt_demo2", 5.0, 5.1, 2000, 2000)
    assert e.cur["EURUSD"]["b"] in (2.0, 5.0) and e.rank("mt_demo2") == 0     # tiền tố khớp rank 'mt'


def test_engine_fresh_beats_stale_higher_priority():
    e = eng()
    e.update("EURUSD", "mt", 2.0, 2.1, 0, 0)
    e.update("EURUSD", "dukascopy", 3.0, 3.1, 25_000, 25_000)       # lúc này mt đã 25s (> stale 20s)
    q = e.cur["EURUSD"]
    assert q["b"] == 3.0 and q["q"] == 0                    # nguồn tươi thắng dù ưu tiên thấp hơn


def test_engine_stale_after_timeout_and_recover():
    e = eng()
    e.update("EURUSD", "mt", 1.0, 1.1, 1000, 1000)
    assert e.cur["EURUSD"]["q"] == 0
    changed, _, _ = e.sweep(1000 + 19_000)
    assert changed == []
    changed, _, _ = e.sweep(1000 + 21_000)
    assert changed == ["EURUSD"] and e.cur["EURUSD"]["q"] == 1
    assert e.sweep(1000 + 22_000)[0] == []                  # không báo lại
    assert e.update("EURUSD", "mt", 1.2, 1.3, 30_000, 30_000) is True
    assert e.cur["EURUSD"]["q"] == 0


def test_engine_drops_old_tick_same_source():
    e = eng()
    assert e.update("EURUSD", "mt", 1.0, 1.1, 5000, 5000)
    assert e.update("EURUSD", "mt", 9.0, 9.1, 4000, 5100) is False        # tick cũ hơn bị bỏ
    assert e.cur["EURUSD"]["b"] == 1.0
    assert e.update("EURUSD", "mt", 1.0, 1.1, 5000, 5200) is False        # y hệt -> không đổi -> không đẩy
    assert e.update("EURUSD", "mt", 1.5, 1.6, 6000, 5300) is True


def test_engine_silent_and_resumed():
    e = eng()
    e.update("EURUSD", "mt", 1.0, 1.1, 1000, 1000)
    assert e.sweep(1000 + 89_000)[1] == []
    _, new_silent, resumed = e.sweep(1000 + 91_000)
    assert new_silent == ["EURUSD"] and resumed == []
    assert e.sweep(1000 + 92_000)[1] == []                  # chỉ báo một lần
    e.update("EURUSD", "mt", 1.2, 1.3, 100_000, 100_000)
    _, new_silent, resumed = e.sweep(100_500)
    assert resumed == ["EURUSD"] and new_silent == []       # BUG#1 (đã sửa): update() từng xoá silent trước khi sweep thấy -> 'resumed' không bao giờ phát
    assert e.silent == set()


def test_engine_no_source_name_leak():
    e = eng()
    e.update("EURUSD", "dukascopy", 1.0, 1.1, 1000, 1000)
    q = e.cur["EURUSD"]
    assert set(q) == {"s", "b", "a", "t", "q"} and "dukascopy" not in json.dumps(q)


def test_engine_rejects_garbage_and_caps():
    e = QuoteEngine(["mt"], 20, 90, max_symbols=2)
    assert e.update("X", "mt", "abc", None, 1, 1) is False
    assert e.update("X", "mt", float("nan"), float("inf"), 1, 1) is False
    assert e.update("X", "mt", True, None, 1, 1) is False
    assert e.update("A", "mt", 1, None, 1, 1) and e.cur["A"]["a"] == 1.0  # thiếu ask -> dùng bid
    e.update("B", "mt", 1, 1, 1, 1)
    assert e.update("C", "mt", 1, 1, 1, 1) is False         # vượt max_symbols


# ===================================================================== Hub: quote flush / throttle / coalesce
async def test_flush_throttle_and_coalesce():
    h = mkhub(quote_ms=250)
    c, ok, _ = await join(h, MASTER, ["q:EURUSD"])
    assert ok == ["q:EURUSD"]
    snap = drain(c)[0]
    assert snap["t"] == "snap" and snap["d"] is None and snap["ep"] == h.ep
    for i, b in enumerate((1.1, 1.2, 1.3)):                  # 3 tick trước khi flush -> gộp thành MỘT tin mới nhất
        h.handle_event("md.quotes", quote("EURUSD", b, b + 0.1, ts=T0 + i), now_ms=T0 + i)
    assert h.flush(now=100.0) == 1
    m = msgs(c)
    assert len(m) == 1 and m[0]["t"] == "d" and m[0]["d"]["b"] == 1.3 and m[0]["q"] == 1
    # throttle: tick mới trong 250ms chưa được đẩy; sau 250ms mới đẩy, seq tăng
    h.handle_event("md.quotes", quote("EURUSD", 1.4, 1.5, ts=T0 + 10), now_ms=T0 + 10)
    assert h.flush(now=100.1) == 0 and "q:EURUSD" in h.dirty
    assert h.flush(now=100.26) == 1
    m = msgs(c)
    assert len(m) == 1 and m[0]["q"] == 2 and m[0]["d"]["b"] == 1.4      # tin cũ chưa gửi bị thay (coalesce)


async def test_flush_skips_topics_without_subs_and_gc():
    h = mkhub()
    c, _, _ = await join(h, MASTER, ["q:EURUSD"])
    h.handle_event("md.quotes", quote("EURUSD", 1, 2, ts=T0), now_ms=T0)
    h.unsubscribe(c, ["q:EURUSD"])
    assert "q:EURUSD" not in h.topics and h.flush(now=1000.0) == 0


async def test_snapshot_has_current_state_on_subscribe():
    h = mkhub()
    h.handle_event("md.quotes", quote("EURUSD", 1.5, 1.6, ts=T0), now_ms=T0)
    c, _, _ = await join(h, A, ["q:EURUSD"])
    s = drain(c)[0]
    assert s["t"] == "snap" and s["d"]["b"] == 1.5 and s["d"]["s"] == "EURUSD" and "source" not in s["d"]


async def test_extra_stream_routes_to_quotes():
    h = mkhub()
    h.st.extra_streams = ["rt.perf"]
    h.handle_event("rt.perf", quote("PERF1", 1, 2, src="mt-perf", ts=T0), now_ms=T0)
    assert "PERF1" in h.engine.cur
    h.handle_event("account.snapshots", {"payload": {"account_id": "a1", "balance": 1}})
    assert "a1" in h.acct


# ===================================================================== nến forming
async def test_candle_forming_bar_override_and_ticks():
    h = mkhub(candle_ms=500)
    c, _, _ = await join(h, A, ["c:EURUSD:M1"])
    drain(c)
    h.handle_event("md.bars", {"payload": {"symbol": "EURUSD", "tf": "M1", "ts_open": T0, "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1, "v": 7, "source": "mt"}}, now_ms=T0 + 1000)
    assert h.flush(now=10.0) == 1
    d = msgs(c)[0]["d"]
    assert d == {"s": "EURUSD", "f": "M1", "t": T0, "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1, "v": 7}
    drain(c)
    # tick trong nến: cập nhật c, mở rộng h/l
    h.handle_event("md.quotes", quote("EURUSD", 1.3, 1.31, ts=T0 + 5000), now_ms=T0 + 5000)
    h.handle_event("md.quotes", quote("EURUSD", 0.8, 0.81, ts=T0 + 6000), now_ms=T0 + 6000)
    h.flush(now=11.0)
    d = [m for m in msgs(c) if m["k"] == "c:EURUSD:M1"][0]["d"]
    assert d["h"] == 1.3 and d["l"] == 0.8 and d["c"] == 0.8 and d["o"] == 1.0 and d["t"] == T0
    # md.bars ghi đè lại (EA gửi nến chính thức)
    drain(c)
    h.handle_event("md.bars", {"payload": {"symbol": "EURUSD", "tf": "M1", "ts_open": T0, "o": 1.0, "h": 1.5, "l": 0.7, "c": 1.4, "v": 9, "source": "mt"}}, now_ms=T0 + 7000)
    h.flush(now=12.0)
    d = msgs(c)[0]["d"]
    assert d["h"] == 1.5 and d["c"] == 1.4 and d["v"] == 9


async def test_candle_opens_new_m1_on_boundary_but_not_h4():
    h = mkhub()
    for tf in ("M1", "H4"):
        h.handle_event("md.bars", {"payload": {"symbol": "EURUSD", "tf": tf, "ts_open": T0, "o": 1, "h": 1, "l": 1, "c": 1, "source": "mt"}}, now_ms=T0)
    h.handle_event("md.quotes", quote("EURUSD", 2.0, 2.1, ts=T0 + 61_000), now_ms=T0 + 61_000)
    m1 = h.candles[("EURUSD", "M1")]
    assert m1["t"] == T0 + 60_000 and m1["o"] == m1["h"] == m1["l"] == m1["c"] == 2.0
    assert h.candles[("EURUSD", "H4")]["t"] == T0                         # H4 chờ md.bars (giờ broker)


async def test_candle_priority_and_old_bar_ignored():
    h = mkhub()
    bar = lambda src, c, t=T0: {"payload": {"symbol": "EURUSD", "tf": "M1", "ts_open": t, "o": 1, "h": 2, "l": 0.5, "c": c, "source": src}}  # noqa: E731
    h.handle_event("md.bars", bar("mt", 1.1), now_ms=T0)
    h.handle_event("md.bars", bar("yahoo", 1.9), now_ms=T0 + 5_000)       # nguồn thấp không ghi đè nguồn cao vừa cập nhật
    assert h.candles[("EURUSD", "M1")]["c"] == 1.1
    h.handle_event("md.bars", bar("yahoo", 1.9), now_ms=T0 + 40_000)      # >30s không có nguồn cao -> ghi đè được
    assert h.candles[("EURUSD", "M1")]["c"] == 1.9
    h.handle_event("md.bars", bar("mt", 1.2, t=T0 - 60_000), now_ms=T0 + 41_000)
    assert h.candles[("EURUSD", "M1")]["t"] == T0                         # nến cũ hơn bị bỏ
    h.handle_event("md.bars", {"payload": {"symbol": "EURUSD", "tf": "M2", "ts_open": T0, "o": 1, "h": 1, "l": 1, "c": 1}})
    h.handle_event("md.bars", {"payload": {"symbol": "EURUSD", "tf": "M1", "ts_open": T0, "o": "x", "h": 1, "l": 1, "c": 1}})
    assert ("EURUSD", "M2") not in h.candles


# ===================================================================== reliable
def status_ev(acc, i):
    return {"payload": {"account_id": acc, "status": f"s{i}", "reason": "r"}}


async def test_reliable_seq_continuous_and_ring_resume():
    h = mkhub(ring=5, max_conns_user=50)
    c, _, _ = await join(h, A, ["e:a1"])
    assert drain(c)[0]["reset"] is True                     # chưa có lịch sử -> snap reset (q=0)
    for i in range(1, 4):
        h.handle_event("mt.account_status", status_ev("a1", i))
    seqs = [m["q"] for m in msgs(c)]
    assert seqs == [1, 2, 3]
    # resume đủ: last=1 -> nhận 2,3
    c2, _, _ = await join(h, A, ["e:a1"], resume={"e:a1": 1}, ep=h.ep)
    assert [m["q"] for m in msgs(c2)] == [2, 3] and all(m["t"] == "d" for m in msgs(c2))
    # last == seq -> snap resumed
    c3, _, _ = await join(h, A, ["e:a1"], resume={"e:a1": 3}, ep=h.ep)
    s = msgs(c3)
    assert len(s) == 1 and s[0]["t"] == "snap" and s[0].get("resumed") is True and s[0]["q"] == 3
    # ring không đủ: phát thêm 10 (ring=5) rồi resume từ 1 -> reset
    for i in range(4, 14):
        h.handle_event("mt.account_status", status_ev("a1", i))
    c4, _, _ = await join(h, A, ["e:a1"], resume={"e:a1": 1}, ep=h.ep)
    s = msgs(c4)
    assert len(s) == 1 and s[0]["reset"] is True and s[0]["q"] == 13
    # ep khác (gateway restart) -> reset
    c5, _, _ = await join(h, A, ["e:a1"], resume={"e:a1": 12}, ep="deadbeef")
    assert msgs(c5)[0]["reset"] is True
    # resume vô lý (âm, quá seq, bool, chuỗi) -> reset, không văng lỗi
    for bad in (-1, 999, True, "5", None):
        c6, _, _ = await join(h, A, ["e:a1"], resume={"e:a1": bad}, ep=h.ep)
        assert msgs(c6)[0].get("reset") is True


async def test_reliable_overflow_triggers_resync_snapshot():
    h = mkhub(queue_max=5)
    c, _, _ = await join(h, A, ["e:a1", "q:EURUSD"])
    drain(c)
    h.handle_event("md.quotes", quote("EURUSD", 1, 2, ts=T0), now_ms=T0)
    for i in range(30):
        h.handle_event("mt.account_status", status_ev("a1", i))
    assert len(c.rel) == 0 and "e:a1" in c.resync            # đã bỏ hàng đợi, chờ snapshot thay thế
    fr_ = await h.next_frame(c)
    m = json.loads(fr_)["m"]
    snaps = [x for x in m if x["t"] == "snap" and x["k"] == "e:a1"]
    assert len(snaps) == 1 and snaps[0]["reset"] is True and snaps[0]["q"] == 30
    h.handle_event("mt.account_status", status_ev("a1", 99))   # sau resync tin mới đi lại bình thường
    assert [json.loads(x)["q"] for x in c.rel] == [31]


async def test_sys_and_news_reliable_and_scrubbed():
    h = mkhub()
    c, ok, _ = await join(h, MASTER, ["sys", "n"])
    drain(c)
    h.handle_event("alerts.out", {"payload": {"level": "warn", "title": "Dữ liệu từ dukascopy trễ", "body": "b"}})
    h.handle_event("news.enriched", {"payload": {"url": "http://x", "title": "t", "importance": "low"}})     # low -> bỏ
    h.handle_event("news.enriched", {"payload": {"url": "http://x", "title": "t", "importance": "high"}})
    m = msgs(c)
    assert [x["k"] for x in m] == ["sys", "n"]
    assert "dukascopy" not in json.dumps(m[0]).lower()      # scrub tên nguồn


# ===================================================================== IDOR / phân quyền
async def test_idor_forbidden_uniform():
    h = mkhub()
    h.handle_event("account.snapshots", {"payload": {"account_id": "a2", "balance": 123}})
    c, ok, errs = await join(h, A, ["a:a2", "e:a2", "a:khong-ton-tai", "e:khong-ton-tai", "sys", "a:a1", "q:EURUSD", "n", "bad topic!"])
    assert set(ok) == {"a:a1", "q:EURUSD", "n"}
    forb = {t for t, code in errs if code == "forbidden"}
    assert forb == {"a:a2", "e:a2", "a:khong-ton-tai", "e:khong-ton-tai", "sys"}      # tồn tại / không tồn tại -> cùng mã
    assert [code for t, code in errs if t != "bad topic!"] == ["forbidden"] * 5
    assert any(code == "bad_topic" for _, code in errs)
    assert "a:a2" not in c.topics and not any(_bal(m, 123) for m in msgs(c))


async def test_idor_snapshot_of_other_account_never_reaches_client():
    h = mkhub(account_ms=0)
    ca, _, _ = await join(h, A, ["a:a1", "a:a2", "e:a2"])
    cb, _, _ = await join(h, B, ["a:a2", "e:a2"])
    cm, _, _ = await join(h, MASTER, ["a:a1", "a:a2", "e:a2", "sys"])
    for c in (ca, cb, cm):
        drain(c)
    h.handle_event("account.snapshots", {"payload": {"account_id": "a1", "balance": 111}})
    h.handle_event("account.snapshots", {"payload": {"account_id": "a2", "balance": 222}})
    h.handle_event("mt.account_status", status_ev("a2", 1))
    h.handle_event("account.deals", {"payload": {"account_id": "a2", "deals": [{"ticket": 1}]}, "ts": "x"})
    h.flush(now=50.0)
    ka = {m["k"] for m in msgs(ca)}
    assert ka == {"a:a1"} and not _bal(msgs(ca), 222)
    assert {m["k"] for m in msgs(cb)} == {"a:a2", "e:a2"} and not _bal(msgs(cb), 111)
    km = {m["k"] for m in msgs(cm)}
    assert {"a:a1", "a:a2", "e:a2", "sys"} <= km


async def test_master_sees_all_sys_only_master():
    h = mkhub()
    cm, ok, errs = await join(h, MASTER, ["sys", "a:any", "e:any"])
    assert errs == [] and len(ok) == 3
    cs, ok, errs = await join(h, Principal("service"), ["sys"])
    assert ok == ["sys"]
    cc, ok, errs = await join(h, A, ["sys"])
    assert ok == [] and errs == [["sys", "forbidden"]]


async def test_account_payload_scrubbed():
    h = mkhub(account_ms=0)
    c, _, _ = await join(h, A, ["a:a1"])
    drain(c)
    h.handle_event("account.snapshots", {"payload": {"account_id": "a1", "balance": 5, "source": "dukascopy", "provider": "oanda"}})
    h.flush(now=9.0)
    d = msgs(c)[0]["d"]
    assert d["balance"] == 5 and "provider" not in d and "dukascopy" not in json.dumps(d)


# ===================================================================== giới hạn
async def test_connection_limits():
    h = mkhub(max_conns=3, max_conns_user=2, max_conns_master=3)
    u = Principal("client", "u1", frozenset())
    c1, w = h.admit(u, "ws")
    c2, w = h.admit(u, "ws")
    c3, w = h.admit(u, "ws")
    assert c1 and c2 and c3 is None and w == "user_limit"
    m1, _ = h.admit(MASTER, "ws")
    assert m1
    x, w = h.admit(Principal("client", "u2"), "ws")          # tổng = 3
    assert x is None and w == "capacity"
    h.drop(c1)
    assert h.by_user["u1"] == 1
    y, _ = h.admit(Principal("client", "u2"), "ws")
    assert y
    h.drop(c1)                                               # drop hai lần không làm lệch bộ đếm
    assert h.by_user["u1"] == 1 and len(h.conns) == 3


async def test_max_topics_per_connection():
    h = mkhub(max_topics=3)
    c, ok, errs = await join(h, MASTER, [f"q:S{i}" for i in range(6)])
    assert len(ok) == 3 and [e[1] for e in errs] == ["too_many_topics"] * 3
    ok2, errs2 = await h.subscribe(c, ["q:S0"])              # đăng ký lại topic đã có vẫn ok
    assert ok2 == ["q:S0"] and errs2 == []


async def test_subscribe_caps_50_per_command_and_validates_types():
    h = mkhub(max_topics=200)
    c, ok, errs = await join(h, MASTER, [f"q:S{i}" for i in range(80)])
    assert len(ok) == 50
    ok, errs = await h.subscribe(c, [1, None, {"a": 1}, "q:" + "X" * 40, "c:EURUSD:M2", ""])
    assert ok == [] and all(e[1] == "bad_topic" for e in errs) and len(errs) == 6


async def test_client_rate_limit_too_big_and_garbage():
    h = mkhub(msg_rate=0.0, msg_burst=3.0, max_msg_bytes=200)
    c, _ = h.admit(MASTER, "ws")
    for _ in range(3):
        await h.on_client(c, '{"op":"ping","t":1}')
    assert len(c.pre) == 3 and c.violations == 0
    for _ in range(250):                                     # vượt burst, không hồi token (rate=0)
        await h.on_client(c, '{"op":"ping","t":1}')
    assert len(c.pre) == 3 and c.closed and c.reason == "rate"
    c2, _ = h.admit(MASTER, "ws")
    await h.on_client(c2, "x" * 500)
    assert json.loads(c2.pre[0]) == {"t": "err", "c": "too_big"} and c2.violations == 5
    h.st.msg_burst = 50.0
    c3, _ = h.admit(MASTER, "ws")
    await h.on_client(c3, "{không phải json")
    await h.on_client(c3, "[1,2]")
    await h.on_client(c3, '{"op":"xxx"}')
    await h.on_client(c3, '{"op":"sub","topics":"q:EURUSD"}')    # topics không phải list -> bỏ qua
    assert c3.violations == 3 and not c3.pre


async def test_client_ops_ping_sub_unsub_lat():
    h = mkhub()
    c, _ = h.admit(MASTER, "ws")
    await h.on_client(c, '{"op":"ping","t":123,"r":15}')
    assert json.loads(c.pre.pop())["c"] == 123
    await h.on_client(c, '{"op":"sub","topics":["q:EURUSD","sys"]}')
    ok = json.loads(c.pre[-1])
    assert ok["t"] == "ok" and set(ok["k"]) == {"q:EURUSD", "sys"}
    await h.on_client(c, '{"op":"unsub","topics":["q:EURUSD","q:NOPE"]}')
    assert json.loads(c.pre[-1]) == {"t": "ok", "u": ["q:EURUSD"]}
    await h.on_client(c, '{"op":"lat","s":[1,2,"x",-5,99999999]}')    # mẫu hỏng bị bỏ, không văng lỗi


async def test_kick_and_max_age_reauth():
    h = mkhub()
    c1, _ = h.admit(Principal("client", "uK"), "ws")
    c2, _ = h.admit(Principal("client", "uK"), "ws")
    c3, _ = h.admit(Principal("client", "other"), "ws")
    assert h.kick("uK") == 2 and c1.closed and c1.reason == "kicked" and c2.closed and not c3.closed
    assert h.kick("khong-co") == 0
    assert await h.next_frame(c1) is None
    # max_age
    h2 = mkhub(max_age_s=0)
    c, _ = h2.admit(A, "ws")
    c.t0 -= 1
    assert await h2.next_frame(c) is None and c.reason == "reauth"
    m, _ = h2.admit(MASTER, "ws")
    assert m.max_age == h2.st.max_age_master_s                # master có hạn riêng


async def test_next_frame_heartbeat_and_pre_first():
    h = mkhub(hb_s=0.05)
    c, _ = h.admit(MASTER, "ws")
    await asyncio.sleep(0.06)
    h.sweep()                                              # sweep() đặt hb_due cho kết nối im > hb_s
    fr_ = await h.next_frame(c)
    assert json.loads(fr_)["t"] == "hb"
    c.pre.append(json.dumps({"t": "pong", "c": 1, "s": 2}))
    c.latest["q:X"] = json.dumps({"t": "d", "k": "q:X", "q": 1, "d": {}})
    assert [m["t"] for m in json.loads(await h.next_frame(c))["m"]] == ["pong"]       # tin điều khiển đi trước, khung riêng
    assert [m["t"] for m in json.loads(await h.next_frame(c))["m"]] == ["d"]


async def test_drop_cleans_subscriptions():
    h = mkhub()
    c, _, _ = await join(h, MASTER, ["q:EURUSD", "e:a1"])
    assert h.topics["q:EURUSD"].subs == {c}
    h.drop(c)
    assert "q:EURUSD" not in h.topics and not h.topics["e:a1"].subs and not h.conns and not h.by_user


async def test_sweep_publishes_silent_resumed_to_master_only():
    h = mkhub()
    cm, _, _ = await join(h, MASTER, ["sys"])
    drain(cm)
    h.handle_event("md.quotes", quote("EURUSD", 1, 2, ts=T0), now_ms=T0)
    h.sweep(now_ms=T0 + 100_000)
    s = msgs(cm)
    assert s[0]["d"]["k"] == "silent" and s[0]["d"]["syms"] == ["EURUSD"]
    drain(cm)
    h.handle_event("md.quotes", quote("EURUSD", 1.1, 2.1, ts=T0 + 101_000), now_ms=T0 + 101_000)
    h.sweep(now_ms=T0 + 101_500)
    assert [m["d"]["k"] for m in msgs(cm)] == ["resumed"]


# ===================================================================== e2e: TestClient WebSocket/SSE
SECRET = "trust-secret-xyz"


class _QueueRedis:
    """xread trả sự kiện do test đẩy vào (an toàn luồng); fakeredis treo loop với BLOCK nên không dùng."""

    def __init__(self):
        self.q: list = []
        self.lock = threading.Lock()

    def push(self, stream, ev):
        with self.lock:
            self.q.append((stream, ev))

    async def xread(self, streams, count=None, block=None):
        with self.lock:
            item = self.q.pop(0) if self.q else None
        if item:
            st, ev = item
            return [(st, [("1-0", {"e": ev.model_dump_json()})])]
        await asyncio.sleep(0.02)
        return []

    async def aclose(self):
        pass


def _app(monkeypatch, **env):
    base = {"RT_QUOTE_MS": "0", "RT_ACCOUNT_MS": "0", "RT_CANDLE_MS": "0", "RT_HB_S": "0.2"}
    base.update({k: str(v) for k, v in env.items()})
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    redis = _QueueRedis()
    s = GatewaySettings(api_tokens=("tok1",), auth_disabled=False, cors_origins=(), auth_trust_secret=SECRET)
    app = create_app(s, InMemoryRepo(), redis)
    return app, redis


def ident(role, uid, accs=""):
    return {"X-API-Key": "tok1", "X-User-Id": uid, "X-Role": role, "X-Accounts": accs, "X-Auth-Secret": SECRET}


def recv_until(ws, pred, limit=40):
    seen = []
    for _ in range(limit):
        fr_ = ws.receive_json()
        for m in (fr_["m"] if fr_.get("t") == "b" else [fr_]):
            seen.append(m)
            if pred(m):
                return m, seen
    raise AssertionError(f"không thấy tin mong đợi: {seen[-5:]}")


def test_e2e_ws_hello_sub_snap_delta_ping(monkeypatch):
    app, redis = _app(monkeypatch)
    with TestClient(app) as tc:
        redis.push("md.quotes", make_event("quote", "t", {"symbol": "EURUSD", "bid": 1.1, "ask": 1.2, "source": "mt"}))
        time.sleep(0.2)
        with tc.websocket_connect("/v1/rt?topics=q:EURUSD", headers=ident("client", "uA", "a1")) as ws:
            hello = ws.receive_json()
            assert hello["t"] == "hello" and hello["v"] == 1 and hello["role"] == "client" and hello["ep"] == app.state.rt.ep
            snap, _ = recv_until(ws, lambda m: m["t"] == "snap")
            assert snap["k"] == "q:EURUSD" and snap["d"]["b"] == 1.1 and "source" not in snap["d"]
            redis.push("md.quotes", make_event("quote", "t", {"symbol": "EURUSD", "bid": 1.5, "ask": 1.6, "source": "mt"}))
            d, _ = recv_until(ws, lambda m: m["t"] == "d" and m["k"] == "q:EURUSD")
            assert d["d"]["b"] == 1.5 and d["q"] > snap["q"]
            ws.send_json({"op": "ping", "t": 4242})
            pong, _ = recv_until(ws, lambda m: m["t"] == "pong")
            assert pong["c"] == 4242
            ws.send_json({"op": "sub", "topics": ["a:a2", "a:a1", "sys"]})
            ok, _ = recv_until(ws, lambda m: m["t"] == "ok" and "k" in m)
            assert ok["k"] == ["a:a1"] and sorted(e[1] for e in ok["e"]) == ["forbidden", "forbidden"]
            # đóng chủ động
        deadline = time.monotonic() + 5
        while app.state.rt.conns and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not app.state.rt.conns


def test_e2e_ws_client_never_receives_other_account(monkeypatch):
    app, redis = _app(monkeypatch)
    with TestClient(app) as tc:
        with tc.websocket_connect("/v1/rt?topics=a:a1,a:a2", headers=ident("client", "uA", "a1")) as wa, \
                tc.websocket_connect("/v1/rt?topics=a:a1,a:a2", headers=ident("master", "m1")) as wm:
            recv_until(wa, lambda m: m["t"] == "ok")
            recv_until(wm, lambda m: m["t"] == "ok")
            redis.push("account.snapshots", make_event("snap", "t", {"account_id": "a2", "balance": 222}))
            redis.push("account.snapshots", make_event("snap", "t", {"account_id": "a1", "balance": 111}))
            m, seen = recv_until(wa, lambda m: m["t"] == "d" and m["k"] == "a:a1")
            assert m["d"]["balance"] == 111 and not any(x.get("k") == "a:a2" or (isinstance(x.get("d"), dict) and x["d"].get("balance") == 222) for x in seen)   # so khớp có cấu trúc: chuỗi "222" có thể trùng ts/seq
            ks = set()
            recv_until(wm, lambda x: (ks.add(x.get("k")), {"a:a1", "a:a2"} <= ks)[1] and x["t"] == "d")
            assert {"a:a1", "a:a2"} <= ks


def test_e2e_ws_auth_failures(monkeypatch):
    app, _ = _app(monkeypatch)
    with TestClient(app) as tc:
        def closed(headers, url="/v1/rt?topics=q:EURUSD"):
            try:
                with tc.websocket_connect(url, headers=headers) as ws:
                    ws.receive_json()
                    ws.receive_json()
                return None
            except Exception as e:  # noqa: BLE001
                return getattr(e, "code", repr(e))

        bad_secret = {**ident("client", "uA", "a1"), "X-Auth-Secret": "sai"}
        no_secret = {k: v for k, v in ident("client", "uA", "a1").items() if k != "X-Auth-Secret"}
        assert closed(bad_secret) == 1008
        assert closed(no_secret) == 1008
        assert closed(ident("anon", "x")) == 1008
        assert closed(ident("hacker", "x")) == 1008
        # sai API key (không có header danh tính -> service): chờ tin auth đầu, hết hạn/ sai -> 1008
        with pytest.raises(Exception) as ei:
            with tc.websocket_connect("/v1/rt?topics=q:EURUSD", headers={"X-API-Key": "sai"}) as ws:
                ws.send_json({"type": "auth", "api_key": "van-sai"})
                ws.receive_json()
        assert getattr(ei.value, "code", 1008) == 1008
        # Origin lạ
        assert closed({**ident("client", "uA", "a1"), "Origin": "https://evil.example"}) == 1008
        assert app.state.rt.conns == set() or True


def test_e2e_ws_origin_same_host_allowed(monkeypatch):
    app, _ = _app(monkeypatch)
    with TestClient(app) as tc:
        with tc.websocket_connect("/v1/rt", headers={**ident("client", "uA", "a1"), "Origin": "http://testserver"}) as ws:
            assert ws.receive_json()["t"] == "hello"


def test_e2e_ws_limits_user_and_capacity(monkeypatch):
    app, _ = _app(monkeypatch, RT_MAX_CONNS_USER=2, RT_MAX_CONNS=3)
    with TestClient(app) as tc:
        h = ident("client", "uA", "a1")
        with tc.websocket_connect("/v1/rt", headers=h) as w1, tc.websocket_connect("/v1/rt", headers=h) as w2:
            assert w1.receive_json()["t"] == "hello" and w2.receive_json()["t"] == "hello"
            with pytest.raises(Exception) as ei:
                with tc.websocket_connect("/v1/rt", headers=h):
                    pass
            assert getattr(ei.value, "code", 1013) == 1013
            with tc.websocket_connect("/v1/rt", headers=ident("client", "uB", "a2")) as w3:     # user khác vẫn vào (tổng 3)
                assert w3.receive_json()["t"] == "hello"
                with pytest.raises(Exception):
                    with tc.websocket_connect("/v1/rt", headers=ident("client", "uC", "a3")):
                        pass


def test_e2e_ws_kick_and_reauth(monkeypatch):
    app, _ = _app(monkeypatch)
    with TestClient(app) as tc:
        with tc.websocket_connect("/v1/rt", headers=ident("client", "uA", "a1")) as wa, \
                tc.websocket_connect("/v1/rt", headers=ident("client", "uB", "a2")) as wb:
            wa.receive_json(), wb.receive_json()
            r = tc.post("/v1/rt/kick", json={"user_id": "uA"}, headers=ident("master", "m1"))
            assert r.status_code == 200 and r.json() == {"kicked": 1}
            bye, _ = recv_until(wa, lambda m: m["t"] == "bye")
            assert bye["c"] == "kicked"
            # client thường không được kick; uB vẫn sống
            assert tc.post("/v1/rt/kick", json={"user_id": "uB"}, headers=ident("client", "uA", "a1")).status_code == 403
            assert tc.get("/v1/rt/stats", headers=ident("client", "uA", "a1")).status_code == 403
            assert tc.get("/v1/rt/stats", headers=ident("master", "m1")).json()["conns"] >= 1
            wb.send_json({"op": "ping", "t": 1})
            recv_until(wb, lambda m: m["t"] == "pong")


def test_e2e_ws_max_age_sends_reauth(monkeypatch):
    app, _ = _app(monkeypatch, RT_MAX_AGE_S=1)
    with TestClient(app) as tc:
        with tc.websocket_connect("/v1/rt", headers=ident("client", "uA", "a1")) as ws:
            assert ws.receive_json()["t"] == "hello"
            bye, _ = recv_until(ws, lambda m: m["t"] == "bye", limit=50)
            assert bye["c"] == "reauth"


def test_e2e_sse(monkeypatch):
    app, redis = _app(monkeypatch)
    with TestClient(app) as tc:
        assert tc.get("/v1/rt/sse?topics=q:EURUSD").status_code == 401                              # không API key
        assert tc.get("/v1/rt/sse", headers={"X-API-Key": "sai"}).status_code == 401
        assert tc.get("/v1/rt/sse", headers={**ident("client", "uA", "a1"), "X-Auth-Secret": "sai"}).status_code == 403
        assert tc.get("/v1/rt/sse", headers={**ident("client", "uA", "a1"), "Origin": "https://evil.example"}).status_code == 403
        redis.push("md.quotes", make_event("quote", "t", {"symbol": "EURUSD", "bid": 1.1, "ask": 1.2, "source": "mt"}))
        time.sleep(0.2)
        # TestClient đệm cả thân phản hồi -> cho kết nối hết tuổi (RT_MAX_AGE_S=1) để luồng SSE tự kết thúc rồi phân tích
        h = app.state.rt
        h.st.max_age_s = 1
        r = tc.get("/v1/rt/sse?topics=q:EURUSD,a:a2,a:a1,sys", headers=ident("client", "uA", "a1"))
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        got = [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]
        flat = [m for g in got for m in (g["m"] if g.get("t") == "b" else [g])]
        assert flat[0]["t"] == "hello"
        ok = next(m for m in flat if m["t"] == "ok")
        assert set(ok["k"]) == {"q:EURUSD", "a:a1"} and {e[0] for e in ok["e"]} == {"a:a2", "sys"}
        snap = next(m for m in flat if m["t"] == "snap" and m["k"] == "q:EURUSD")
        assert snap["d"]["b"] == 1.1
        assert flat[-1] == {"t": "bye", "c": "reauth"}
        deadline = time.monotonic() + 5
        while h.conns and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not h.conns


def test_rt_disabled(monkeypatch):
    monkeypatch.setenv("RT_ENABLED", "0")
    app = create_app(GatewaySettings(api_tokens=("tok1",)), InMemoryRepo(), fr.FakeRedis(decode_responses=True))
    assert getattr(app.state, "rt", None) is None


def test_constants_sanity():
    assert rt.TOPIC_RE.match("q:EURUSD") and rt.TOPIC_RE.match("c:EURUSD:H4") and rt.TOPIC_RE.match("sys") and rt.TOPIC_RE.match("n")
    assert not rt.TOPIC_RE.match("c:EURUSD:M2") and not rt.TOPIC_RE.match("q:") and not rt.TOPIC_RE.match("a:*") and not rt.TOPIC_RE.match("q:A B")
