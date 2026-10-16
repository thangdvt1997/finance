"""Guardrail rủi ro (mô-đun 7): cỡ vị thế, lỗ ngày, cửa sổ tin, kill-switch, hash-chain + neo."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from pattern_scan import paper
from pattern_scan.config import DEFAULTS
from pattern_scan.guardrail import KILL_KEY, Guardrail, daily_loss_r, news_blocked, position_size, sizing_table
from pattern_scan.store import MemoryStore
from pattern_scan.worker import Scanner

from .conftest import DT, make_bars, payload, ts

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_size_by_sl_and_never_exceeds_risk():
    r = position_size(10000, 0.5, entry=100.0, sl=101.0)           # rủi ro 50, khoảng dừng 1
    assert r["ok"] and r["units"] == 50.0 and r["risk_amount"] == 50.0
    r = position_size(10000, 1.0, atr=0.0007, atr_mult=1.5, lot_step=0.01)
    assert r["ok"] and r["risk_amount"] <= 100.0 + 1e-9 and r["stop_distance"] == pytest.approx(0.00105)


def test_size_caps_and_bad_input():
    assert position_size(10000, 50, entry=1, sl=2, max_risk_pct=2.0)["risk_pct"] == 2.0       # trần cứng
    for bad in (dict(equity=0, risk_pct=1, atr=1), dict(equity=1000, risk_pct=0, atr=1), dict(equity=1000, risk_pct=1),
                dict(equity=1000, risk_pct=1, atr=float("nan")), dict(equity="x", risk_pct=1, atr=1)):
        assert position_size(**bad)["units"] == 0.0
    assert not position_size(100, 0.1, atr=1000)["ok"]            # dưới bước tối thiểu


def test_sizing_table_monotonic_and_bounded():
    tb = sizing_table(10000)
    assert len(tb) == 16
    for row in tb:
        assert row["risk_amount"] <= 10000 * row["risk_pct"] / 100 + 1e-9
    a = [r for r in tb if r["atr"] == 1.0]
    assert [r["units"] for r in a] == sorted(r["units"] for r in a)       # risk% tăng -> cỡ tăng


def test_daily_loss_only_today_closed_non_replay():
    tr = [{"status": "closed", "result_r": -1.2, "closed_at": NOW - timedelta(hours=2)},
          {"status": "closed", "result_r": -2.0, "closed_at": NOW - timedelta(days=1)},
          {"status": "closed", "result_r": -9.0, "closed_at": NOW - timedelta(hours=1), "replay": True},
          {"status": "open", "result_r": None, "closed_at": None},
          {"status": "closed", "result_r": 0.5, "closed_at": NOW.isoformat()}]
    assert daily_loss_r(tr, NOW) == -0.7


def test_news_window_blocks_around_high_impact():
    ev = [{"event_id": "e1", "title": "Non-Farm Payrolls", "country": "US", "impact": "high", "ts": NOW + timedelta(minutes=5)}]
    cfg = None
    from tscommon.risk_windows import load_config
    cfg = load_config()
    assert news_blocked(ev, "EURUSD", NOW, cfg) is not None
    assert news_blocked(ev, "EURUSD", NOW - timedelta(hours=3), cfg) is None


async def _guard(kill=None, trades=None, events=None, **c):
    async def kr():
        return kill
    async def tr():
        return trades or []
    async def ev(now):
        return events or []
    return Guardrail({"guardrail": c}, kill_reader=kr, events_reader=ev, trades_reader=tr)


async def test_kill_switch_blocks_and_default_is_open():
    p = {"symbol": "EURUSD", "pattern": "KB-1", "tf": "H1", "setup_id": "KB-1:a", "levels": {"entry": 1.1, "sl": 1.101}}
    g = await _guard()
    d = await g.check(p, NOW)
    assert d["allow"] and d["size"]["units"] > 0
    g = await _guard(kill=json.dumps({"on": True, "by": "master", "at": NOW.isoformat()}))
    d = await g.check(p, NOW)
    assert not d["allow"] and d["kind"] == "kill_switch" and g.counts["kill_switch"] == 1
    await g.check(p, NOW)                                              # trùng setup -> không đếm lại
    assert g.counts["kill_switch"] == 1 and len(g.recent) == 1
    g = await _guard(kill="{rác")                                      # cờ hỏng -> an toàn: coi như BẬT
    assert not (await g.check(p, NOW))["allow"]


async def test_daily_loss_blocks():
    p = {"symbol": "EURUSD", "pattern": "KB-1", "tf": "H1", "setup_id": "x", "levels": {"entry": 1.1, "sl": 1.101}}
    g = await _guard(trades=[{"status": "closed", "result_r": -3.2, "closed_at": NOW - timedelta(hours=1)}])
    assert (await g.check(p, NOW))["kind"] == "daily_loss"
    st = await g.state(NOW)
    assert st["daily_blocked"] and st["daily_loss_r"] == -3.2


async def test_disabled_and_redis_error_failopen_flagged():
    p = {"symbol": "EURUSD", "pattern": "KB-1", "tf": "H1", "setup_id": "x", "levels": {"entry": 1.1, "sl": 1.101}}
    g = await _guard(enabled=False, kill=json.dumps({"on": True}))
    assert (await g.check(p, NOW))["allow"]
    async def boom():
        raise RuntimeError("redis down")
    g = Guardrail({}, kill_reader=boom)
    assert (await g.check(p, NOW))["allow"] and "kill_switch" in g.degraded


async def test_scanner_blocks_paper_trade_when_kill_switch_on():
    rows = make_bars()
    st = MemoryStore({("XAUUSD", "M15"): rows})
    sc = Scanner(DEFAULTS | {}, st, None, clock=lambda: ts(200) + DT + timedelta(seconds=5))
    async def on():
        return json.dumps({"on": True})
    sc.kill_get = on
    out = await sc.handle(payload("triggered", 200, rows))
    assert out.get("blocked") and "trade_id" not in out and st.tr == [] and sc.guard.counts["kill_switch"] == 1
    await sc.repair()                                                  # repair không được lách guardrail
    assert st.tr == []
    sc.kill_get = None
    sc2 = Scanner(DEFAULTS | {}, MemoryStore({("XAUUSD", "M15"): rows}), None, clock=lambda: ts(200) + DT + timedelta(seconds=5))
    out = await sc2.handle(payload("triggered", 200, rows))
    assert out["trade_id"] == 1 and sc2.store.led[0]["content"]["guard"]["units"] > 0   # cỡ vị thế nằm trong bản ghi sổ cái


# ---- hash-chain: phát hiện sửa/xoá/chèn/cắt đuôi ----
def _chain(n=5):
    rows, prev = [], paper.GENESIS
    for i in range(n):
        c = {"id": i, "result_r": 0.5 * i}
        h = paper.chain_hash(prev, "close", str(i), c)
        rows.append({"seq": i + 1, "kind": "close", "ref": str(i), "content": c, "prev_hash": prev, "hash": h})
        prev = h
    return rows


def test_chain_ok_and_anchor():
    rows = _chain()
    v = paper.verify(rows)
    assert v["ok"] and v["n"] == 5
    assert paper.verify(rows, {"n": 5, "hash": rows[-1]["hash"]})["anchored"]


def test_chain_detects_edit():
    rows = _chain()
    rows[2]["content"] = {**rows[2]["content"], "result_r": 99}
    v = paper.verify(rows)
    assert not v["ok"] and v["broken_at"] == 3


def test_chain_detects_delete_middle_and_insert():
    rows = _chain()
    assert paper.verify(rows[:2] + rows[3:])["ok"] is False
    ins = _chain()
    ins.insert(2, dict(ins[2], seq=3))
    assert paper.verify(ins)["ok"] is False


def test_chain_detects_tail_truncation_only_with_anchor():
    rows = _chain()
    anchor = {"n": 5, "hash": rows[-1]["hash"]}
    cut = rows[:3]
    assert paper.verify(cut)["ok"] is True                              # không neo: không thể biết
    v = paper.verify(cut, anchor)
    assert not v["ok"] and "cắt đuôi" in v["reason"]


def test_chain_detects_full_rewrite_with_anchor():
    rows = _chain()
    anchor = {"n": 5, "hash": rows[-1]["hash"]}
    rewritten, prev = [], paper.GENESIS
    for r in rows:                                                     # kẻ tấn công tính lại toàn chuỗi sau khi sửa
        c = dict(r["content"]); c["result_r"] = 7 if r["seq"] == 2 else c["result_r"]
        h = paper.chain_hash(prev, r["kind"], r["ref"], c)
        rewritten.append(dict(r, content=c, prev_hash=prev, hash=h)); prev = h
    assert paper.verify(rewritten)["ok"] is True
    assert not paper.verify(rewritten, anchor)["ok"]


def test_http_verify_and_guardrail_endpoints():
    from fastapi.testclient import TestClient
    from pattern_scan.app import create_app
    sc = Scanner(DEFAULTS | {}, MemoryStore(), None)
    c = TestClient(create_app(scanner=sc))
    v = c.get("/scan/ledger/verify").json()                      # không tham số neo: phải 200 (đã từng 422 vì mặc định "")
    assert v["ok"] and v["n"] == 0
    assert c.get("/scan/ledger/verify?anchor_n=3&anchor_hash=" + "a" * 64).json()["ok"] is False
    assert c.get("/scan/ledger/verify?anchor_n=3&anchor_hash=zz").status_code == 422
    g = c.get("/scan/guardrail").json()
    assert g["enabled"] and g["kill_switch"]["on"] is False and len(g["sizing_table"]) == 16
