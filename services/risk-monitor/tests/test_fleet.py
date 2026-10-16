from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from tscommon import Bus

from risk_monitor.app import create_app
from risk_monitor.config import Settings
from risk_monitor.fleet import FleetConfig, FleetEngine, budget_conditions

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
UID1, UID2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


class Src:
    def __init__(self):
        self.eq = {"a1": 10_000.0, "a2": 10_000.0}
        self.deals = {"a1": [NOW - timedelta(hours=i + 1) for i in range(3)]}

    async def mt_accounts(self):
        return [{"account_id": a, "platform": "mt5", "ts": NOW - timedelta(seconds=20), "balance": 10_000.0, "equity": e, "margin": 0.0,
                 "positions": "[]"} for a, e in self.eq.items()]

    async def mt_equity(self, account_id, days):
        return [(NOW - timedelta(days=1), 10_000.0), (NOW - timedelta(hours=6), 10_000.0)]

    async def deal_times(self, days=2):
        return self.deals


class Http:
    """Giả auth + alert-rules. Ghi lại mọi lời gọi (method, url, body)."""

    def __init__(self, rules=None, rules_status=200, post_status=200, notify_status=200):
        self.rules, self.rules_status, self.post_status, self.notify_status = rules, rules_status, post_status, notify_status
        self.calls: list[tuple[str, str, dict | None]] = []

    async def __call__(self, method, url, token, body=None, timeout=10.0):
        assert token == "tok"
        self.calls.append((method, url, body))
        if url.endswith("/internal/fleet/rules"):
            return self.rules_status, (self.rules if self.rules_status == 200 else None)
        if url.endswith("/internal/fleet/results"):
            return self.post_status, ({"accepted": len(body["results"]), "opened": 0, "closed": 0} if self.post_status == 200 else None)
        if url.endswith("/internal/notify"):
            return self.notify_status, ({"sent": 1} if self.notify_status == 200 else None)
        return 404, None

    def of(self, suffix):
        return [c for c in self.calls if c[1].endswith(suffix)]


def rules(notify=True, accounts=("a1", "a2"), push=None):
    return {"rev": 1, "assignments": [{"assignment_id": "as1", "template_id": "t1", "name": "Lỗ ngày 5%", "kind": "daily_loss",
                                       "params": {"limit_pct": 5, "tz": "UTC"}, "accounts": list(accounts), "notify_client": notify}],
            "client_push": push if push is not None else {"a1": UID1}}


def mk(http, **kw):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return FleetEngine(FleetConfig("http://auth:8000", "tok", "http://alert-rules:8000", **kw), r, Bus(r), http=http, clock=lambda: NOW), r


async def test_disabled_without_token():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    http = Http(rules())
    f = FleetEngine(FleetConfig("http://auth:8000", "", "http://alert-rules:8000"), r, Bus(r), http=http)
    assert f.enabled is False
    assert await f.run(Src(), []) == {} and http.calls == []
    assert f.status()["engine"] == "off"


async def test_run_evaluates_and_posts_results_with_conditions():
    http = Http(rules())
    f, _ = mk(http)
    src = Src()
    src.eq["a2"] = 9_400.0                                           # lỗ 600 / 500 -> đỏ
    conds = budget_conditions("a1", [{"key": "dd_pct", "label": "Drawdown từ đỉnh", "unit": "%", "value": 9.0, "limit": 10.0, "status": "warn"}])
    out = await f.run(src, conds)
    assert out["results"] == 2
    body = http.of("/internal/fleet/results")[0][2]
    by = {x["account_id"]: x for x in body["results"]}
    assert by["a1"]["status"] == "green" and by["a2"]["status"] == "red" and by["a2"]["assignment_id"] == "as1"
    assert {"usage_pct", "value", "limit", "headroom", "unit", "detail", "reset_at", "evaluated_at"} <= set(by["a2"])
    assert body["conditions"][0]["key"] == "budget:a1:dd_pct" and body["conditions"][0]["severity"] == "warning"
    assert body["conditions"][0]["cause_key"] == "budget:dd_pct" and body["conditions"][0]["kind"] == "budget"
    assert f.status()["counts"] == {"green": 1, "yellow": 0, "red": 1, "na": 0}


def test_budget_conditions_mapping():
    items = [{"key": "k1", "label": "L1", "unit": "%", "value": 1.0, "limit": 10.0, "status": "ok"},
             {"key": "k2", "label": "L2", "unit": "x", "value": 11.0, "limit": 10.0, "status": "crit"},
             {"key": "k3", "label": "L3", "unit": "", "value": None, "limit": 10.0, "status": "na"}]
    c = budget_conditions("acc", items)
    assert [x["severity"] for x in c] == ["ok", "critical"] and c[1]["cause_key"] == "budget:k2" and c[0]["account_id"] == "acc"


async def test_batches_of_500():
    http = Http(rules(accounts=[]))
    f, _ = mk(http)
    conds = [{"key": f"budget:x{i}:k", "account_id": f"x{i}", "severity": "ok", "kind": "budget", "title": "t", "detail": "d", "cause_key": "budget:k"}
             for i in range(1200)]
    await f.run(Src(), conds)
    posts = http.of("/internal/fleet/results")
    assert [len(p[2]["conditions"]) for p in posts] == [500, 500, 200]


async def test_sync_failure_keeps_cache_then_drops():
    http = Http(rules())
    f, _ = mk(http)
    assert (await f.run(Src(), []))["results"] == 2
    http.rules_status = 503                                          # auth chết: giữ bản cũ (<10 phút)
    out = await f.run(Src(), [])
    assert out["results"] == 2 and f.status()["last_sync_ok"] is False and "503" in f.status()["last_error"]
    f.cfg.cache_max_age = -1.0                                       # quá hạn cache -> bỏ bản cũ
    assert (await f.run(Src(), []))["results"] == 0


async def test_auth_404_does_not_break_cycle():
    http = Http(rules(), post_status=404)
    f, _ = mk(http)
    out = await f.run(Src(), [{"key": "k", "account_id": "a1", "severity": "ok", "kind": "budget", "title": "t", "detail": "d", "cause_key": "c"}])
    assert out["post"]["errors"] == 1 and out["post"]["batches"] == 1
    http2 = Http(None, rules_status=404, post_status=404)           # auth chưa có /internal/fleet/*
    f2, _ = mk(http2)
    assert (await f2.run(Src(), []))["results"] == 0


async def test_transition_emitted_once_and_recovery():
    http = Http(rules(notify=False))
    f, r = mk(http)
    src = Src()
    await f.run(src, [])
    assert await r.xlen("alerts.out") == 0                           # xanh lần đầu: không cảnh báo
    src.eq["a1"] = 9_650.0                                           # vàng
    o1 = await f.run(src, [])
    o2 = await f.run(src, [])
    assert o1["alerts"] == 1 and o2["alerts"] == 0 and await r.xlen("alerts.out") == 1
    src.eq["a1"] = 9_400.0                                           # đỏ
    assert (await f.run(src, []))["alerts"] == 1
    src.eq["a1"] = 9_900.0                                           # hồi phục
    assert (await f.run(src, []))["alerts"] == 1
    assert await r.xlen("alerts.out") == 3
    assert await r.hget("risk:rule_state", "as1:a1") == "green"
    msgs = await r.xrange("alerts.out")
    import json
    pay = [json.loads(m[1]["e"])["payload"] for m in msgs]
    assert [p["level"] for p in pay] == ["warn", "crit", "info"]
    assert "account:a1" in pay[0]["tags"] and "rule:as1" in pay[0]["tags"]
    blob = json.dumps(pay).lower()
    assert "dukascopy" not in blob and "yahoo" not in blob


async def test_push_only_for_opted_in_and_notify_client():
    http = Http(rules(notify=True, push={"a1": UID1}))
    f, _ = mk(http)
    src = Src()
    await f.run(src, [])
    src.eq["a1"] = src.eq["a2"] = 9_400.0                            # cả hai chuyển đỏ; chỉ a1 opt-in
    out = await f.run(src, [])
    pushes = http.of("/internal/notify")
    assert len(pushes) == 1 and pushes[0][2] == {"owner": UID1, "kind": "rule"} and out["pushes"] == 1
    await f.run(src, [])                                             # trạng thái không đổi: không push lại
    assert len(http.of("/internal/notify")) == 1


async def test_no_push_when_notify_client_false_or_recovery():
    http = Http(rules(notify=False))
    f, _ = mk(http)
    src = Src()
    await f.run(src, [])
    src.eq["a1"] = 9_400.0
    await f.run(src, [])
    assert http.of("/internal/notify") == []
    http2 = Http(rules(notify=True))
    f2, _ = mk(http2)
    src2 = Src()
    src2.eq["a1"] = 9_400.0
    await f2.run(src2, [])                                           # lần đầu đã đỏ -> push
    assert len(http2.of("/internal/notify")) == 1
    src2.eq["a1"] = 9_900.0
    await f2.run(src2, [])                                           # hồi phục: không push
    assert len(http2.of("/internal/notify")) == 1


async def test_max_trades_uses_deal_times():
    rl = {"rev": 1, "assignments": [{"assignment_id": "as2", "template_id": "t", "name": "Số lệnh", "kind": "max_trades_day",
                                     "params": {"limit": 4, "tz": "UTC"}, "accounts": ["a1"], "notify_client": False}], "client_push": {}}
    f, _ = mk(Http(rl))
    await f.run(Src(), [])
    assert f.results[0]["status"] == "yellow" and f.results[0]["value"] == 3          # 3/4 = 75%


async def test_status_route_off_without_engine():
    app = create_app(Settings(enabled=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        j = (await c.get("/risk/rules/status")).json()
        assert j["engine"] == "off" and j["results"] == []
