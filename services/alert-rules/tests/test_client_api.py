"""Giới hạn/mục tiêu (siết áp ngay, nới 24h), thông báo, cài đặt đồng bộ, thiết bị push, ticket — kèm IDOR giữa 2 client."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from alert_rules.app import create_app
from alert_rules.limits import LimitError, decide, progress_for, validate
from alert_rules.store import MemStore
from alert_rules.webpush import PushService

T0 = datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc).timestamp()      # 10h sáng giờ VN
UA, UB = "user-aaaaaaaa", "user-bbbbbbbb"


def sc(user, accounts="", role="client"):
    h = {"X-Owner-Role": role, "X-Owner-User": user}
    if role == "client":
        h["X-Owner-Accounts"] = accounts
    return h


A, B = sc(UA, "mt5:1"), sc(UB, "mt5:2")
MASTER = sc("master-uid-0001", role="master")


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Prov:
    def __init__(self, clk):
        self.clk = clk
        self.m = {}

    def default(self, **kw):
        return {"as_of": self.clk.t - 30, "equity": 9000.0, "margin": 1000.0, "equity_day_start": 10000.0, "equity_month_start": 10000.0,
                "peak_equity": 10000.0, "flows_day": 0.0, "flows_month": 0.0, "orders_today": 3, **kw}

    async def limit_metrics(self, account_id, now):
        return self.m.get(account_id)

    async def latest_price(self, s):
        return None

    async def accounts(self):
        return []

    async def bar_closes(self, *a):
        return []

    async def analytics(self, *a):
        return None, 0

    async def calendar(self, *a):
        return []

    async def sentiment(self, *a):
        return None, 0


class Sender:
    def __init__(self):
        self.calls = []

    def __call__(self, info, data, vapid_private, subject, ttl):
        self.calls.append((info, data))


def mk():
    clk, store, sender = Clock(), MemStore(), Sender()
    push = PushService(store, "priv", "pub", "mailto:a@b.c", Fernet.generate_key().decode(), send_fn=sender, clock=clk)
    prov = Prov(clk)
    app = create_app(store=store, provider=prov, redis=fakeredis.aioredis.FakeRedis(decode_responses=True), start_background=False, push=push, clock=clk)
    return TestClient(app), store, clk, prov, sender, app


def put(c, h, key, value, acc="mt5:1"):
    return c.put("/limits", json={"account_id": acc, "key": key, "value": value}, headers=h)


def items(c, h, acc="mt5:1"):
    return {i["key"]: i for i in c.get(f"/limits?account_id={acc}", headers=h).json()["items"]}


# ------------------------------------------------------------------ logic thuần
def test_validate_domains():
    assert validate("daily_loss_pct", 5) == 5.0 and validate("max_orders_day", 10) == 10.0 and validate("max_dd_pct", None) is None
    for k, v in (("daily_loss_pct", 0.01), ("daily_loss_pct", 51), ("max_dd_pct", 0.5), ("max_dd_pct", 91), ("min_margin_level", 49), ("min_margin_level", 5001),
                 ("max_orders_day", 0), ("max_orders_day", 501), ("max_orders_day", 2.5), ("monthly_target_pct", 0.05), ("monthly_target_pct", 1001),
                 ("daily_loss_pct", True), ("daily_loss_pct", "5"), ("daily_loss_pct", float("nan")), ("nope", 1)):
        with pytest.raises(LimitError):
            validate(k, v)


def test_progress_unknown_when_stale_or_missing():
    now = datetime.fromtimestamp(T0, timezone.utc)
    fresh = {"as_of": T0 - 10, "equity": 9000.0, "margin": 1000.0, "equity_day_start": 10000.0, "equity_month_start": 10000.0, "peak_equity": 10000.0,
             "flows_day": 0.0, "flows_month": 0.0, "orders_today": 3}
    p = progress_for("daily_loss_pct", 10.0, fresh, now)
    assert p["level"] == "danger" and abs(p["current"] - 10.0) < 1e-6 or p["level"] == "hit"
    assert progress_for("daily_loss_pct", 10.0, {**fresh, "as_of": T0 - 3600}, now)["level"] == "unknown"       # dữ liệu cũ
    assert progress_for("daily_loss_pct", 10.0, None, now)["level"] == "unknown"
    assert progress_for("daily_loss_pct", 10.0, {**fresh, "equity_day_start": None}, now)["level"] == "unknown"
    assert progress_for("max_orders_day", 3, fresh, now)["level"] == "hit"
    assert progress_for("min_margin_level", 800, fresh, now)["level"] in ("danger", "warn")                     # margin 900% vs 800%
    assert progress_for("min_margin_level", 100, {**fresh, "margin": 0.0}, now)["level"] == "ok"
    # nạp/rút tiền không tính là lỗ
    assert progress_for("daily_loss_pct", 10.0, {**fresh, "flows_day": -1000.0}, now)["current"] == 0.0


def test_decide_rules():
    now = datetime.fromtimestamp(T0, timezone.utc)
    row = {"value": 5.0, "pending_value": None, "pending_remove": False, "pending_effective_at": None}
    assert decide("daily_loss_pct", None, 5.0, now).applied == "now"                       # đặt mới = siết
    assert decide("daily_loss_pct", row, 3.0, now).applied == "now"                        # giảm = siết
    d = decide("daily_loss_pct", row, 8.0, now)
    assert d.applied == "pending" and d.value == 5.0 and d.effective_at == now + timedelta(hours=24)
    assert decide("min_margin_level", {**row, "value": 200.0}, 300.0, now).applied == "now"      # tăng margin = siết
    assert decide("min_margin_level", {**row, "value": 200.0}, 150.0, now).applied == "pending"  # giảm margin = nới
    assert decide("daily_loss_pct", row, None, now).applied == "pending"                   # xoá = nới
    assert decide("daily_loss_pct", row, 5.0, now).applied == "noop"
    assert decide("monthly_target_pct", {**row, "value": 10.0}, 50.0, now).applied == "now"      # mục tiêu: luôn ngay
    assert decide("monthly_target_pct", {**row, "value": 10.0}, None, now).applied == "now"


# ------------------------------------------------------------------ giới hạn qua API (đồng hồ giả)
def test_tighten_now_loosen_after_24h_cancel_and_history():
    c, store, clk, prov, _, _ = mk()
    with c:
        r = put(c, A, "daily_loss_pct", 5).json()
        assert r["applied"] == "now" and r["value"] == 5.0
        # nới lỏng -> pending, giá trị hiện hành giữ nguyên
        r = put(c, A, "daily_loss_pct", 8).json()
        assert r["applied"] == "pending" and r["value"] == 5.0 and r["pending_value"] == 8.0 and r["effective_at"]
        it = items(c, A)["daily_loss_pct"]
        assert it["value"] == 5.0 and it["pending_value"] == 8.0 and it["pending_effective_at"]
        clk.t += 23 * 3600
        assert items(c, A)["daily_loss_pct"]["value"] == 5.0                                  # chưa đủ 24h
        clk.t += 2 * 3600
        it = items(c, A)["daily_loss_pct"]
        assert it["value"] == 8.0 and it["pending_value"] is None                             # đã hiệu lực
        # huỷ pending bằng cách đặt lại đúng giá trị hiện tại
        assert put(c, A, "daily_loss_pct", 12).json()["applied"] == "pending"
        r = put(c, A, "daily_loss_pct", 8).json()
        assert r["applied"] == "cancelled" and r["pending_value"] is None
        assert put(c, A, "daily_loss_pct", 8).json()["applied"] == "noop"
        # siết khi đang pending -> áp ngay và huỷ pending
        put(c, A, "daily_loss_pct", 12)
        r = put(c, A, "daily_loss_pct", 4).json()
        assert r["applied"] == "now" and r["value"] == 4.0 and r["pending_value"] is None
        assert items(c, A)["daily_loss_pct"]["pending_value"] is None
        # xoá = pending 24h; tới hạn thì mất giới hạn
        r = put(c, A, "daily_loss_pct", None).json()
        assert r["applied"] == "pending" and r["value"] == 4.0
        assert items(c, A)["daily_loss_pct"]["pending_remove"] is True
        clk.t += 25 * 3600
        assert "daily_loss_pct" not in items(c, A)
        # mục tiêu: đổi/xoá có hiệu lực ngay
        assert put(c, A, "monthly_target_pct", 10).json()["applied"] == "now"
        assert put(c, A, "monthly_target_pct", 20).json()["applied"] == "now"
        assert put(c, A, "monthly_target_pct", None).json()["applied"] == "now"
        assert "monthly_target_pct" not in items(c, A)
        h = c.get("/limits/history?account_id=mt5:1&limit=50", headers=A).json()["items"]
        assert {x["applied"] for x in h} >= {"now", "pending", "cancelled", "matured"}
        assert all(x["by"] in ("client", "system") for x in h)
        assert c.get("/limits/history?account_id=mt5:1&limit=2", headers=A).json()["items"].__len__() == 2


def test_limit_domain_errors_422():
    c, *_ = mk()
    with c:
        for k, v in (("daily_loss_pct", 80), ("max_dd_pct", 0), ("min_margin_level", 10), ("max_orders_day", 3.5), ("daily_loss_pct", "x"), ("bogus", 1)):
            assert put(c, A, k, v).status_code == 422, (k, v)
        assert c.put("/limits", json={"account_id": "mt5:1", "key": "daily_loss_pct", "value": 5, "extra": 1}, headers=A).status_code == 422


def test_limit_progress_levels_and_unknown():
    c, store, clk, prov, _, _ = mk()
    with c:
        put(c, A, "daily_loss_pct", 20)
        put(c, A, "max_orders_day", 10)
        j = c.get("/limits?account_id=mt5:1", headers=A).json()
        assert j["progress"]["daily_loss_pct"]["level"] == "unknown" and j["progress"]["daily_loss_pct"]["current"] is None      # chưa có dữ liệu
        prov.m["mt5:1"] = prov.default()
        p = c.get("/limits?account_id=mt5:1", headers=A).json()["progress"]
        assert p["daily_loss_pct"]["level"] == "ok" and abs(p["daily_loss_pct"]["current"] - 10.0) < 1e-6 and p["daily_loss_pct"]["unit"] == "%"
        assert p["max_orders_day"]["current"] == 3 and p["max_orders_day"]["remaining"] == 7 and p["max_orders_day"]["level"] == "ok"
        prov.m["mt5:1"] = prov.default(orders_today=9, equity=7800.0)
        p = c.get("/limits?account_id=mt5:1", headers=A).json()["progress"]
        assert p["max_orders_day"]["level"] == "danger" and p["daily_loss_pct"]["level"] == "hit" or p["daily_loss_pct"]["level"] == "danger"
        prov.m["mt5:1"] = prov.default(as_of=clk.t - 7200)
        assert c.get("/limits?account_id=mt5:1", headers=A).json()["progress"]["daily_loss_pct"]["level"] == "unknown"


def test_limits_idor():
    c, *_ = mk()
    with c:
        put(c, A, "daily_loss_pct", 5)
        # B không đọc/sửa tài khoản của A; tài khoản không thuộc phiên -> 404 đồng nhất (kể cả tài khoản không tồn tại)
        for acc in ("mt5:1", "mt5:999"):
            assert c.get(f"/limits?account_id={acc}", headers=B).status_code == 404
            assert c.get(f"/limits/history?account_id={acc}", headers=B).status_code == 404
            assert put(c, B, "daily_loss_pct", 5, acc).status_code == 404
        assert items(c, B, "mt5:2") == {}
        # cùng tài khoản nhưng khác chủ (phiên của người khác có mt5:1): dữ liệu vẫn tách theo chủ
        other = sc("user-cccccccc", "mt5:1")
        assert items(c, other) == {}
        assert put(c, other, "daily_loss_pct", 9).json()["applied"] == "now" and items(c, A)["daily_loss_pct"]["value"] == 5.0
        # master chỉ đọc
        assert c.get("/limits?account_id=mt5:1", headers=MASTER).status_code == 200
        assert put(c, MASTER, "daily_loss_pct", 1).status_code == 403
        assert c.put("/limits", json={"account_id": "mt5:1", "key": "daily_loss_pct", "value": 1}).status_code == 403          # service không đặt hộ
        assert c.get("/limits").status_code == 422


# ------------------------------------------------------------------ nhắc giới hạn -> thông báo + push chung
def sub(c, h, n=1):
    import base64, os
    b = lambda k: base64.urlsafe_b64encode(os.urandom(k)).rstrip(b"=").decode()   # noqa: E731
    return c.post("/push/subscribe", json={"endpoint": f"https://fcm.googleapis.com/fcm/send/dev{n}", "keys": {"p256dh": b(65), "auth": b(16)}, "user_agent": f"UA{n}"}, headers=h)


def test_watcher_notifies_once_per_threshold_per_cycle_and_push_is_generic():
    c, store, clk, prov, sender, app = mk()
    with c:
        assert sub(c, A).status_code == 201
        put(c, A, "daily_loss_pct", 10)
        w = app.state.watcher
        run = lambda: asyncio.new_event_loop().run_until_complete(w.tick())    # noqa: E731
        prov.m["mt5:1"] = prov.default(equity=9200.0)                           # lỗ 8% / 10% = 80% -> ngưỡng 70
        assert run() == 1 and run() == 0                                        # 1 lần
        n = c.get("/notifications", headers=A).json()
        assert n["unread"] == 1 and n["items"][0]["kind"] == "limit" and n["items"][0]["severity"] == "warn" and n["items"][0]["account_id"] == "mt5:1"
        prov.m["mt5:1"] = prov.default(equity=9050.0, as_of=clk.t - 5)          # 95% -> ngưỡng 90
        assert run() == 1
        prov.m["mt5:1"] = prov.default(equity=8900.0, as_of=clk.t - 5)          # 110% -> ngưỡng 100
        assert run() == 1 and run() == 0
        assert len(c.get("/notifications?kind=limit", headers=A).json()["items"]) == 3
        assert sender.calls and all("10000" not in d and "mt5" not in d and "9" not in json.loads(d)["body"] for _, d in sender.calls)       # push chung
        for _, d in sender.calls:
            assert set(json.loads(d)) == {"title", "body", "url"} and "mt5" not in d
        # sang ngày mới (giờ VN) -> chu kỳ mới, nhắc lại được
        clk.t += 24 * 3600
        prov.m["mt5:1"] = prov.default(equity=8900.0, as_of=clk.t - 5)
        assert run() == 1
        # dữ liệu cũ -> không nhắc (không báo sai)
        clk.t += 24 * 3600
        prov.m["mt5:1"] = prov.default(equity=8000.0, as_of=clk.t - 7200)
        assert run() == 0
        # B không nhận gì
        assert c.get("/notifications", headers=B).json() == {"items": [], "unread": 0}


def test_watcher_matured_limit_notification_and_target_info():
    c, store, clk, prov, sender, app = mk()
    with c:
        put(c, A, "monthly_target_pct", 5)
        prov.m["mt5:1"] = prov.default(equity=10600.0)
        w = app.state.watcher
        assert asyncio.new_event_loop().run_until_complete(w.tick()) == 1
        n = c.get("/notifications", headers=A).json()["items"][0]
        assert n["severity"] == "info" and n["kind"] == "limit"
        put(c, A, "max_orders_day", 5)
        put(c, A, "max_orders_day", 9)
        clk.t += 25 * 3600
        prov.m["mt5:1"] = prov.default(equity=10600.0)
        asyncio.new_event_loop().run_until_complete(w.tick())
        assert any("hiệu lực" in x["title"] for x in c.get("/notifications", headers=A).json()["items"])


# ------------------------------------------------------------------ thông báo: chủ sở hữu, đọc, tôn trọng cài đặt
def test_notifications_owner_only_read_and_internal():
    c, store, clk, prov, sender, app = mk()
    with c:
        sub(c, A)
        body = {"owner_user_id": UA, "kind": "report", "severity": "info", "title": "Báo cáo tuần", "body": "Đã sẵn sàng", "link": "/c/#/bao-cao", "dedupe_key": "wk-1"}
        assert c.post("/internal/notifications", json=body).status_code == 201
        assert c.post("/internal/notifications", json=body).json() == {"created": 0}            # dedupe
        assert c.post("/internal/notifications", json={**body, "owner_user_id": UB, "dedupe_key": "wk-1b", "link": "http://evil"}).status_code == 201
        assert c.post("/internal/notifications", json=body, headers=A).status_code == 403       # đi qua gateway (có X-Owner-*) -> từ chối
        assert c.post("/internal/notifications", json={**body, "kind": "bogus"}).status_code == 422
        assert c.post("/internal/notifications", json={"kind": "report", "title": "x"}).status_code == 422
        na = c.get("/notifications", headers=A).json()
        nb = c.get("/notifications", headers=B).json()
        assert na["unread"] == 1 and [i["title"] for i in na["items"]] == ["Báo cáo tuần"] and na["items"][0]["read"] is False
        assert nb["items"][0]["link"] is None                                                 # link lạ bị bỏ
        assert sender.calls and "Báo cáo" not in sender.calls[0][1]
        nid = na["items"][0]["id"]
        # B không đánh dấu đọc được thông báo của A
        assert c.post("/notifications/read", json={"ids": [nid]}, headers=B).json()["marked"] == 0
        assert c.get("/notifications?unread=1", headers=A).json()["unread"] == 1
        assert c.post("/notifications/read", json={"ids": [nid]}, headers=A).json() == {"marked": 1, "unread": 0}
        assert c.get("/notifications?unread=1", headers=A).json()["items"] == []
        assert c.get("/notifications?kind=limit", headers=A).json()["items"] == []
        assert c.post("/notifications/read", json={}, headers=A).status_code == 422
        assert c.post("/notifications/read", json={"all": True}, headers=B).json()["unread"] == 0
        assert c.get("/notifications").status_code == 403                                     # service không có chủ
        assert c.get("/notifications?before=abc", headers=A).status_code == 422


def test_rule_event_creates_one_notification_and_push_respects_prefs():
    c, store, clk, prov, sender, app = mk()
    with c:
        sub(c, A)
        rule = {"name": "EUR", "channels": ["app", "push"], "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]}
        rid = c.post("/rules", json=rule, headers=A).json()["id"]
        now = datetime.fromtimestamp(clk.t, timezone.utc)
        r = app.state.runner
        loop = asyncio.new_event_loop()
        spec = store.rules[rid]["spec"]

        class _R:                   # kết quả điều kiện giả
            ok, text = True, "giá đạt"

            def as_dict(self):
                return {"ok": True, "text": "giá đạt"}
        loop.run_until_complete(r._fire(store.rules[rid], spec, [_R()], now))
        items_ = c.get("/notifications", headers=A).json()["items"]
        assert [i["kind"] for i in items_] == ["rule"] and len(sender.calls) == 1
        # tắt push cho kind rule -> vẫn có thông báo trong app nhưng không gửi push
        r2 = c.put("/client-prefs", json={"rev": 0, "data": {"notif": {"rule": {"app": True, "push": False}}}}, headers=A)
        assert r2.status_code == 200
        store.rules[rid].update(last_fired_at=None, once_done=False)
        clk.t += 600
        loop.run_until_complete(r._fire(store.rules[rid], spec, [_R()], datetime.fromtimestamp(clk.t, timezone.utc)))
        assert len(c.get("/notifications", headers=A).json()["items"]) == 2 and len(sender.calls) == 1
        # tắt app -> không tạo thông báo
        c.put("/client-prefs", json={"rev": 1, "data": {"notif": {"rule": {"app": False, "push": False}}}}, headers=A)
        store.rules[rid].update(last_fired_at=None, once_done=False)
        clk.t += 600
        loop.run_until_complete(r._fire(store.rules[rid], spec, [_R()], datetime.fromtimestamp(clk.t, timezone.utc)))
        assert len(c.get("/notifications", headers=A).json()["items"]) == 2
        loop.close()


# ------------------------------------------------------------------ cài đặt đồng bộ + thiết bị push
def test_client_prefs_rev_whitelist_isolation():
    c, *_ = mk()
    with c:
        assert c.get("/client-prefs", headers=A).json() == {"rev": 0, "data": {}}
        ok = c.put("/client-prefs", json={"rev": 0, "data": {"lang": "vi", "theme": "dark", "watchlist": ["EURUSD", "XAUUSD"], "notif": {"rule": {"app": True, "push": False}}}}, headers=A)
        assert ok.status_code == 200 and ok.json()["rev"] == 1
        stale = c.put("/client-prefs", json={"rev": 0, "data": {"lang": "en"}}, headers=A)
        assert stale.status_code == 409 and stale.json()["rev"] == 1 and stale.json()["data"]["lang"] == "vi"
        assert c.put("/client-prefs", json={"rev": 1, "data": {"lang": "en"}}, headers=A).json()["rev"] == 2
        assert c.get("/client-prefs", headers=B).json() == {"rev": 0, "data": {}}                 # tách theo người dùng
        for bad in ({"evil": 1}, {"notif": {"bogus": {"app": True}}}, {"notif": {"rule": {"app": "yes"}}}, {"notif": {"rule": {"x": True}}},
                    {"watchlist": ["EUR USD"]}, {"watchlist": "EURUSD"}, {"lang": 5}, {"layout": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}}}):
            assert c.put("/client-prefs", json={"rev": 2, "data": bad}, headers=A).status_code == 422, bad
        assert c.put("/client-prefs", json={"rev": 2, "data": {"layout": {"x": "y" * 9000}}}, headers=A).status_code in (413, 422)
        assert c.put("/client-prefs", json={"rev": 2, "data": {"layout": [1, 2]}, "extra": 1}, headers=A).status_code == 422
        g = {"active": "main", "groups": [{"id": "main", "name": "Ưu tiên", "symbols": ["EURUSD", "CRYPTO:BTCUSDT"]}]}  # định dạng nhiều nhóm của client-ui
        assert c.put("/client-prefs", json={"rev": 2, "data": {"watchlist": g}}, headers=A).status_code == 200
        assert c.put("/client-prefs", json={"rev": 3, "data": {"watchlist": {"groups": [{"id": "m", "name": "x", "symbols": ["a b"]}]}}}, headers=A).status_code == 422
        assert c.get("/client-prefs").status_code == 403                                           # service không có chủ


def test_push_devices_list_delete_owner_only():
    c, store, *_ = mk()
    with c:
        sub(c, A, 1), sub(c, A, 2), sub(c, B, 3)
        da = c.get("/push/devices", headers=A).json()
        assert len(da) == 2 and set(da[0]) == {"id", "user_agent", "created_at", "last_ok_at"} and len(da[0]["id"]) == 16
        assert "fcm" not in json.dumps(da)                                                         # không lộ endpoint
        db = c.get("/push/devices", headers=B).json()
        assert len(db) == 1
        assert c.delete(f"/push/devices/{da[0]['id']}", headers=B).status_code == 404            # B không xoá được thiết bị của A
        assert len(c.get("/push/devices", headers=A).json()) == 2
        assert c.delete(f"/push/devices/{db[0]['id']}", headers=A).status_code == 404
        assert c.delete(f"/push/devices/{da[0]['id']}", headers=A).status_code == 200
        assert len(c.get("/push/devices", headers=A).json()) == 1
        assert c.delete("/push/devices/zzzz", headers=A).status_code == 404


# ------------------------------------------------------------------ ticket
def ticket(c, h, **kw):
    return c.post("/tickets", json={"category": "stale_data", "account_id": "mt5:1", "message": "dữ liệu cũ", **kw}, headers=h)


def test_tickets_create_merge_ratelimit_idor_and_master_reply():
    c, store, clk, prov, sender, app = mk()
    with c:
        sub(c, A)
        r = ticket(c, A, context={"ea_state": "offline", "age_s": 120, "latency_ms": 55, "password": "x"})
        assert r.status_code == 201 and r.json()["status"] == "open"
        tid = r.json()["id"]
        d = ticket(c, A)                                                    # gộp trùng category đang mở
        assert d.status_code == 200 and d.json()["id"] == tid and d.json()["merged"] is True
        t = c.get("/tickets", headers=A).json()["items"][0]
        assert t["context"] == {"ea_state": "offline", "age_s": 120, "latency_ms": 55} or t["context"] == {}       # khoá lạ bị bỏ
        assert "owner_user_id" not in t
        # tài khoản không thuộc phiên -> 404
        assert ticket(c, A, account_id="mt5:2").status_code == 404
        assert c.post("/tickets", json={"category": "bogus"}, headers=A).status_code == 422
        assert c.post("/tickets", json={"category": "other", "message": ""}, headers=A).status_code == 422
        assert c.post("/tickets", json={"category": "other", "message": "x" * 1001}, headers=A).status_code == 422
        # B thấy ticket của mình; không thấy của A
        tb = ticket(c, B, account_id="mt5:2").json()
        assert [x["id"] for x in c.get("/tickets", headers=B).json()["items"]] == [tb["id"]]
        # client không được cập nhật ticket (kể cả của mình); master thì được
        for h in (A, B):
            assert c.put(f"/tickets/{tid}", json={"status": "ack"}, headers=h).status_code == 403
        allr = c.get("/tickets", headers=MASTER).json()["items"]
        assert {x["owner_user_id"] for x in allr} == {UA, UB} and len(c.get("/tickets").json()["items"]) == 2
        assert c.put("/tickets/999", json={"status": "ack"}, headers=MASTER).status_code == 404
        assert c.put(f"/tickets/{tid}", json={"status": "weird"}, headers=MASTER).status_code == 422
        n_before = len(sender.calls)
        ok = c.put(f"/tickets/{tid}", json={"status": "resolved", "reply": "Đã khởi động lại bridge"}, headers=MASTER)
        assert ok.status_code == 200 and ok.json()["status"] == "resolved"
        na = c.get("/notifications?kind=support", headers=A).json()
        assert len(na["items"]) == 1 and "bridge" in na["items"][0]["body"]
        assert c.get("/notifications?kind=support", headers=B).json()["items"] == []                # chỉ chủ ticket nhận
        assert len(sender.calls) == n_before + 1 and "bridge" not in sender.calls[-1][1]
        # sau khi resolved: báo cùng loại tạo ticket MỚI (không gộp)
        assert ticket(c, A).status_code == 201


def test_ticket_rate_limit_5_per_hour():
    c, store, clk, *_ = mk()
    with c:
        cats = ["ea_disconnected", "stale_data", "wrong_data", "other"]
        ids = []
        for i in range(5):
            r = c.post("/tickets", json={"category": cats[i % 4], "message": f"msg {i} xxx", "account_id": None if i % 2 else "mt5:1"}, headers=A)
            if r.status_code == 201:
                ids.append(r.json()["id"])
                c.put(f"/tickets/{r.json()['id']}", json={"status": "resolved"}, headers=MASTER)     # đóng để không bị gộp
        assert len(ids) == 5
        r = c.post("/tickets", json={"category": "other", "message": "lại nữa nhé"}, headers=A)
        assert r.status_code == 429
        assert c.post("/tickets", json={"category": "other", "message": "người khác"}, headers=B).status_code == 201     # giới hạn theo người
        clk.t += 3700
        assert c.post("/tickets", json={"category": "other", "message": "sau 1 giờ"}, headers=A).status_code == 201
