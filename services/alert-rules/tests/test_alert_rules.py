from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tscommon import Bus

from alert_rules.app import create_app
from alert_rules.evaluator import Evaluator, MarketState, combine
from alert_rules.models import Prefs, RuleIn
from alert_rules.runner import Runner
from alert_rules.store import MemStore

NOW = 1_800_000_000.0


class FakeProvider:
    def __init__(self):
        self.price = {"mid": 1.1, "ts": NOW, "source": "t"}
        self.an = ({"rsi": 75.0, "trend": "up", "heat": 50}, NOW - 60)
        self.cal = []
        self.sent = (0.4, 5)
        self.prev_sent = (-0.4, 5)
        self.acct = [{"account_id": "A1", "balance": 1000.0, "equity": 900.0, "margin": 400.0, "ts": NOW, "peak24": 1100.0}]
        self.closes = []

    async def latest_price(self, symbol):
        return self.price

    async def bar_closes(self, symbol, minutes):
        return self.closes

    async def analytics(self, symbol, tf):
        return self.an

    async def calendar(self, impacts, start, end, country):
        return self.cal

    async def sentiment(self, symbol, start, end):
        return self.sent if end.timestamp() > NOW - 10 else self.prev_sent

    async def accounts(self):
        return self.acct


def mk(prov=None, clock=None):
    prov = prov or FakeProvider()
    c = clock or (lambda: NOW)
    return prov, Evaluator(prov, MarketState(c), c)


def rule(**kw):
    base = {"name": "r", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.0}]}
    base.update(kw)
    return RuleIn.model_validate(base)


def test_combine_tristate():
    assert combine("and", [True, None]) is None and combine("and", [True, False, None]) is False
    assert combine("or", [False, None]) is None and combine("or", [None, True]) is True
    assert combine("and", [True, True]) is True and combine("or", [False, False]) is False


def test_validation_rejects_bad_input():
    for bad in [
        {"name": "", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1}]},
        {"name": "x", "conditions": []},
        {"name": "x", "conditions": [{"type": "price", "symbol": "EUR USD", "op": "gte", "value": 1}]},
        {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": float("inf")}]},
        {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "buy", "value": 1}]},
        {"name": "x", "conditions": [{"type": "order", "symbol": "EURUSD"}]},
        {"name": "x", "conditions": [{"type": "state", "symbol": "EURUSD", "tf": "H1", "field": "trend", "is": "overbought"}]},
        {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1}] * 9},
        {"name": "x", "extra": 1, "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1}]},
    ]:
        with pytest.raises(Exception):
            RuleIn.model_validate(bad)
    r = rule(expires_at="2030-01-01T00:00:00", channels=["log", "log"])
    assert r.expires_at.tzinfo is not None and r.channels == ["log"]


def test_prefs_sanitized():
    p = Prefs.model_validate({"theme": "light", "evil": 1, "active_watchlist": "zz",
                              "watchlists": [{"id": "a", "name": "A", "symbols": ["EURUSD", "EURUSD"], "tf": "H4"}]})
    assert p.active_watchlist == "a" and p.watchlists[0].symbols == ["EURUSD"] and not hasattr(p, "evil")
    with pytest.raises(Exception):
        Prefs.model_validate({"watchlists": [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}]})
    with pytest.raises(Exception):
        Prefs.model_validate({"watchlists": [{"id": "a", "name": "A", "symbols": ["a b"]}]})


def test_prefs_chart_section():
    p = Prefs.model_validate({"chart": {"draw": {"EURUSD|H1": {"u": 1, "d": []}}, "tpl": {}, "evil": {"x": 1}, "layout": "bad"}})
    assert set(p.chart) == {"draw", "tpl"} and p.chart["draw"]["EURUSD|H1"]["u"] == 1
    assert Prefs.model_validate({}).chart == {}
    with pytest.raises(Exception):
        Prefs.model_validate({"chart": {"draw": {"k": "x" * 17000}}})


def test_prefs_ux_section():
    p = Prefs.model_validate({"ux": {"theme": "auto", "accent": "blue", "fontScale": 110, "sound": True, "notifCats": {"alert": True, "x": 0}, "evil": {"a": 1}, "tz": "x" * 99}})
    assert p.ux["theme"] == "auto" and p.ux["fontScale"] == 110 and p.ux["sound"] is True
    assert "evil" not in p.ux and "tz" not in p.ux and p.ux["notifCats"] == {"alert": True, "x": False}
    assert Prefs.model_validate({}).ux == {}


def test_prefs_tm_section():
    ok = {"v": 1, "a": "w1", "o": ["w1", "ghost"], "w": {"w1": {"n": "Forex", "l": True, "c": {"red": "EURUSD", "pink": "X"}, "evil": 1,
          "x": [{"i": "a1", "t": "watchlist", "x": 0, "y": 0, "w": 8, "h": 16, "c": {"cols": ["price"]}, "k": "red", "n": "BG"},
                {"i": "a1", "t": "dup", "x": 0, "y": 0, "w": 1, "h": 1},                      # trùng id -> bỏ
                {"i": "b2", "t": "clocks", "x": 99, "y": 0, "w": 4, "h": 4},                   # ngoài lưới -> bỏ
                {"i": "c3", "t": "notes", "x": 8, "y": 0, "w": 4, "h": 4, "k": "pink"}]}}}
    t = Prefs.model_validate({"tm": ok}).tm
    assert t["a"] == "w1" and t["o"] == ["w1"] and t["w"]["w1"]["l"] is True and t["w"]["w1"]["c"] == {"red": "EURUSD"}
    assert [w["i"] for w in t["w"]["w1"]["x"]] == ["a1", "c3"] and t["w"]["w1"]["x"][0]["k"] == "red" and "k" not in t["w"]["w1"]["x"][1]
    assert "evil" not in t["w"]["w1"]
    assert Prefs.model_validate({}).tm == {} and Prefs.model_validate({"tm": {"w": "bad"}}).tm == {}


async def test_price_and_cross():
    prov, ev = mk()
    spec = rule(conditions=[{"type": "price", "symbol": "EURUSD", "op": "cross_up", "value": 1.2}]).spec()
    assert (await ev.evaluate_rule("r1", spec))[0] is False       # mốc đầu: chưa có phía trước
    prov.price = {"mid": 1.25, "ts": NOW, "source": "t"}
    ev._cache.clear()
    assert (await ev.evaluate_rule("r1", spec))[0] is True        # cắt lên
    assert (await ev.evaluate_rule("r1", spec))[0] is False       # không lặp lại khi vẫn ở trên
    ok, res = await ev.evaluate_rule("p", rule(conditions=[{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]).spec(), commit=False)
    assert ok is True and "EURUSD" in res[0].text


async def test_stale_price_is_unknown():
    prov, ev = mk()
    prov.price = {"mid": 5.0, "ts": NOW - 3600, "source": "t"}
    ok, res = await ev.evaluate_rule("r", rule().spec())
    assert ok is None and res[0].stale


async def test_indicator_state_news_sentiment_account():
    prov, ev = mk()
    cond = [{"type": "indicator", "symbol": "EURUSD", "tf": "H1", "field": "rsi", "op": "gte", "value": 70},
            {"type": "state", "symbol": "EURUSD", "tf": "H1", "field": "trend", "is": "up"}]
    assert (await ev.evaluate_rule("a", rule(conditions=cond).spec()))[0] is True
    prov.an = ({"rsi": 75.0}, NOW - 99999)                           # dữ liệu cũ -> không rõ
    ev._cache.clear()
    assert (await ev.evaluate_rule("a", rule(conditions=cond).spec()))[0] is None
    prov.cal = [{"title": "NFP", "country": "US", "impact": "high", "ts": datetime.fromtimestamp(NOW + 600, timezone.utc)}]
    assert (await ev.evaluate_rule("n", rule(conditions=[{"type": "news_window", "impact": "high", "within_min": 30}]).spec()))[0] is True
    prov.cal = []
    ev._cache.clear()
    assert (await ev.evaluate_rule("n", rule(conditions=[{"type": "news_window", "impact": "high", "within_min": 30}]).spec()))[0] is False
    fl = rule(conditions=[{"type": "sentiment", "symbol": "EURUSD", "window_h": 6, "op": "flip_up"}]).spec()
    assert (await ev.evaluate_rule("s", fl))[0] is True
    ac = rule(conditions=[{"type": "account", "metric": "margin_level", "op": "lte", "value": 300}]).spec()
    ok, res = await ev.evaluate_rule("m", ac)       # 900/400 = 225%
    assert ok is True and "225" in res[0].text
    dd = rule(conditions=[{"type": "account", "metric": "equity_drawdown_24h", "op": "gte", "value": 15}]).spec()
    assert (await ev.evaluate_rule("d", dd))[0] is True  # (1100-900)/1100 = 18%


async def test_pct_change_needs_history():
    prov, ev = mk()
    spec = rule(conditions=[{"type": "pct_change", "symbol": "EURUSD", "window_min": 60, "op": "abs_gte", "value": 1.0}]).spec()
    assert (await ev.evaluate_rule("p", spec))[0] is None
    prov.closes = [(NOW - 3600, 1.0), (NOW - 1800, 1.05)]
    ev.state.seeded.clear()
    ev._cache.clear()
    ok, res = await ev.evaluate_rule("p", spec)       # 1.0 -> 1.1 = +10%
    assert ok is True and res[0].value == pytest.approx(10.0, abs=0.01)


async def test_runner_once_and_repeat_fire_and_publish():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(r)
    t = [NOW]
    prov, ev = mk(clock=lambda: t[0])
    store = MemStore()
    run = Runner(store, ev, bus, clock=lambda: t[0])
    once = await store.create_rule(rule(name="once", level="crit", channels=["ntfy", "log"], note="n"))
    await store.create_rule(rule(name="rep", mode="repeat", cooldown_min=10))
    prov.price = {"mid": 1.1, "ts": NOW, "source": "t"}
    # created_at/now: dùng thời gian thật cho rule, nên chỉnh clock gần 'now' thật để cooldown tính đúng
    real = datetime.now(timezone.utc).timestamp()
    t[0] = real
    prov.price = {"mid": 1.1, "ts": real, "source": "t"}
    assert await run.tick() == 2
    assert await run.tick() == 0                          # once đã xong; repeat đang cooldown
    t[0] = real + 11 * 60
    prov.price = {"mid": 1.1, "ts": t[0], "source": "t"}
    ev._cache.clear()
    assert await run.tick() == 1                          # chỉ repeat bắn lại
    assert [e["rule_name"] for e in store.events].count("once") == 1 and [e["rule_name"] for e in store.events].count("rep") == 2
    msgs = await r.xrange("alerts.out")
    assert len(msgs) == 3
    import json
    p = json.loads(msgs[0][1]["e"])["payload"]
    assert p["level"] in ("crit", "warn") and "user-rule" in p["tags"] and "ch:ntfy" in p["tags"] or "ch:log" in p["tags"]
    assert (await store.get_rule(str(once["id"])))["once_done"] is True


async def test_runner_expired_and_disabled_skip():
    prov, ev = mk()
    store = MemStore()
    run = Runner(store, ev, None)
    real = datetime.now(timezone.utc)
    await store.create_rule(rule(name="exp", expires_at=(real - timedelta(hours=1)).isoformat()))
    await store.create_rule(rule(name="off", enabled=False))
    ev.clock = run.clock = lambda: real.timestamp()
    ev.state.clock = ev.clock
    prov.price = {"mid": 1.1, "ts": real.timestamp(), "source": "t"}
    assert await run.tick() == 0 and not store.events


def client():
    store = MemStore()
    app = create_app(store=store, provider=FakeProvider(), redis=fakeredis.aioredis.FakeRedis(decode_responses=True), start_background=False)
    return TestClient(app), store


def test_api_crud_preview_prefs():
    c, _ = client()
    with c:
        body = {"name": "EUR trên 1.2", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}], "mode": "repeat"}
        r = c.post("/rules", json=body)
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert r.json()["status"] == "active" and r.json()["mode"] == "repeat"
        assert c.post("/rules", json={**body, "conditions": [{"type": "place_order"}]}).status_code == 422
        assert c.post("/rules/preview", json=body).json()["conditions"][0]["ok"] is False
        assert c.post(f"/rules/{rid}/preview").status_code == 200
        r = c.put(f"/rules/{rid}", json={**body, "enabled": False})
        assert r.json()["status"] == "disabled"
        assert c.get("/rules").json()["items"][0]["id"] == rid
        assert c.get("/rule-events").json() == {"items": []}
        assert c.put("/rules/not-a-uuid", json=body).status_code == 404
        assert c.delete(f"/rules/{rid}").json() == {"ok": True}
        assert c.delete(f"/rules/{rid}").status_code == 404
        g = c.get("/prefs").json()
        assert g["rev"] == 0
        p = c.put("/prefs", json={"rev": 0, "prefs": {"theme": "light", "watchlists": [{"id": "fx", "name": "FX", "symbols": ["EURUSD"]}]}})
        assert p.status_code == 200 and p.json()["rev"] == 1
        assert c.put("/prefs", json={"rev": 0, "prefs": {}}).status_code == 409
        assert c.put("/prefs", json={"rev": 1, "prefs": {"theme": "pink"}}).status_code == 422
        assert c.get("/prefs").json()["prefs"]["watchlists"][0]["id"] == "fx"


def test_api_rule_limit():
    c, store = client()
    from alert_rules.models import MAX_RULES
    body = {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]}
    with c:
        for _ in range(MAX_RULES):
            assert c.post("/rules", json=body).status_code == 201
        assert c.post("/rules", json=body).status_code == 422
