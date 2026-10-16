"""Cảnh báo cá nhân theo chủ sở hữu (chống IDOR/ghi chéo, giới hạn, tài khoản của chính họ) + Web Push (đăng ký theo chủ, nội dung chung, dọn 410)."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from alert_rules.app import create_app
from alert_rules.evaluator import Evaluator, MarketState
from alert_rules.models import MAX_RULES, MAX_RULES_USER, RuleIn
from alert_rules.runner import Runner
from alert_rules.store import MemStore
from alert_rules.webpush import PushService, PushStatusError

NOW = 1_800_000_000.0
UA, UB = "user-aaaaaaaa", "user-bbbbbbbb"


def b64(n: int) -> str:
    return base64.urlsafe_b64encode(os.urandom(n)).rstrip(b"=").decode()


def sc(user: str, accounts: str = "", role: str = "client") -> dict:
    h = {"X-Owner-Role": role, "X-Owner-User": user}
    if role == "client":
        h["X-Owner-Accounts"] = accounts
    return h


A = sc(UA, "mt5:1")
B = sc(UB, "mt5:2")
MASTER = sc("master-uid-0001", role="master")
PRICE = {"name": "EUR", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]}
MARGIN = {"name": "Margin", "conditions": [{"type": "account", "account_id": "mt5:1", "metric": "margin_level", "op": "lte", "value": 150}]}


class Prov:
    def __init__(self):
        self.acct = [{"account_id": "mt5:1", "balance": 1000.0, "equity": 900.0, "margin": 800.0, "ts": NOW, "peak24": 1100.0},
                     {"account_id": "mt5:2", "balance": 5000.0, "equity": 4900.0, "margin": 100.0, "ts": NOW, "peak24": 5100.0}]
        self.price = {"mid": 1.3, "ts": NOW, "source": "t"}

    async def latest_price(self, symbol):
        return self.price

    async def accounts(self):
        return self.acct

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
        self.calls: list[tuple] = []
        self.fail: Exception | None = None

    def __call__(self, info, data, vapid_private, subject, ttl):
        self.calls.append((info, data, ttl))
        if self.fail:
            raise self.fail


def mk(max_per_hour: int = 20):
    store = MemStore()
    sender = Sender()
    push = PushService(store, "priv", "pubkey", "mailto:a@b.c", Fernet.generate_key().decode(), send_fn=sender, max_per_hour=max_per_hour)
    app = create_app(store=store, provider=Prov(), redis=fakeredis.aioredis.FakeRedis(decode_responses=True), start_background=False, push=push)
    return TestClient(app), store, sender, push


def sub_body(host: str = "fcm.googleapis.com", path: str = "/fcm/send/abc") -> dict:
    return {"endpoint": f"https://{host}{path}", "keys": {"p256dh": b64(65), "auth": b64(16)}, "user_agent": "UA/1"}


# ------------------------------------------------------------------ quy tắc: chủ sở hữu / IDOR
def test_client_sees_only_own_rules_and_cannot_touch_others():
    c, store, _, _ = mk()
    with c:
        ra = c.post("/rules", json=PRICE, headers=A)
        assert ra.status_code == 201, ra.text
        rid = ra.json()["id"]
        assert "owner_user_id" not in ra.json()                                   # client không thấy trường chủ sở hữu
        rb = c.post("/rules", json={**PRICE, "name": "của B"}, headers=B).json()
        mr = c.post("/rules", json={**PRICE, "name": "toàn cục"}, headers=MASTER).json()
        assert [r["name"] for r in c.get("/rules", headers=A).json()["items"]] == ["EUR"]
        assert [r["name"] for r in c.get("/rules", headers=B).json()["items"]] == ["của B"]
        names = {r["name"]: r for r in c.get("/rules", headers=MASTER).json()["items"]}
        assert set(names) == {"EUR", "của B", "toàn cục"} and names["EUR"]["owner_user_id"] == UA and names["toàn cục"]["owner_user_id"] is None
        assert {r["name"] for r in c.get("/rules").json()["items"]} == set(names)  # service (không header) thấy tất cả
        # B không thể sửa/xoá/preview quy tắc của A (404 đồng nhất như không tồn tại)
        for method, path in (("put", f"/rules/{rid}"), ("delete", f"/rules/{rid}"), ("post", f"/rules/{rid}/preview")):
            kw = {"json": PRICE} if method == "put" else {}
            assert getattr(c, method)(path, headers=B, **kw).status_code == 404, (method, path)
        assert c.put(f"/rules/{mr['id']}", json=PRICE, headers=A).status_code == 404       # cũng không sửa được quy tắc của master
        assert c.delete(f"/rules/{mr['id']}", headers=A).status_code == 404
        assert c.delete(f"/rules/{rid}", headers=A).status_code == 200
        assert c.get("/rules", headers=B).json()["items"][0]["id"] == rb["id"]
        # master sửa được quy tắc của client nhưng KHÔNG đổi chủ sở hữu
        assert c.put(f"/rules/{rb['id']}", json={**PRICE, "name": "sửa bởi master"}, headers=MASTER).status_code == 200
        assert store.rules[rb["id"]]["owner_user_id"] == UB


def test_events_filtered_by_owner_and_rule_id_param():
    c, store, _, _ = mk()
    with c:
        ra = c.post("/rules", json=PRICE, headers=A).json()
        rb = c.post("/rules", json=PRICE, headers=B).json()
        now = datetime.now(timezone.utc)
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(store.add_event(ra["id"], "a", "warn", "ta", "ba", {}, ["app"], "e1", now, UA))
        loop.run_until_complete(store.add_event(rb["id"], "b", "warn", "tb", "bb", {}, ["app"], "e2", now, UB))
        loop.close()
        assert [e["title"] for e in c.get("/rule-events", headers=A).json()["items"]] == ["ta"]
        assert [e["title"] for e in c.get("/rule-events", headers=B).json()["items"]] == ["tb"]
        assert c.get(f"/rule-events?rule_id={rb['id']}", headers=A).json()["items"] == []        # hỏi thẳng id của B: rỗng
        assert len(c.get("/rule-events", headers=MASTER).json()["items"]) == 2


def test_bad_or_missing_scope_headers_fail_closed():
    c, _, _, _ = mk()
    with c:
        assert c.get("/rules", headers={"X-Owner-Role": "client"}).status_code == 403              # client không có user
        assert c.get("/rules", headers={"X-Owner-Role": "admin", "X-Owner-User": UA}).status_code == 403
        assert c.get("/rules", headers={"X-Owner-User": UA}).status_code == 403                    # có user mà không có vai trò
        assert c.get("/rules", headers={"X-Owner-Role": "client", "X-Owner-User": "a b'; drop"}).status_code == 403
        assert c.get("/rules", headers={"X-Owner-Accounts": "mt5:1"}).status_code == 403


def test_client_account_conditions_only_on_own_accounts():
    c, store, _, _ = mk()
    with c:
        # tài khoản của người khác -> 422; cả preview (không rò số liệu margin của tài khoản khác)
        other = {**MARGIN, "conditions": [{**MARGIN["conditions"][0], "account_id": "mt5:2"}]}
        assert c.post("/rules", json=other, headers=A).status_code == 422
        assert c.post("/rules/preview", json=other, headers=A).status_code == 422
        assert c.put(f"/rules/{c.post('/rules', json=PRICE, headers=A).json()['id']}", json=other, headers=A).status_code == 422
        # không nêu tài khoản: 1 tài khoản -> tự điền; nhiều tài khoản -> 422
        noacc = {**MARGIN, "conditions": [{k: v for k, v in MARGIN["conditions"][0].items() if k != "account_id"}]}
        r = c.post("/rules", json=noacc, headers=A)
        assert r.status_code == 201 and r.json()["conditions"][0]["account_id"] == "mt5:1" and r.json()["account_id"] == "mt5:1"
        assert c.post("/rules", json=noacc, headers=sc(UA, "mt5:1,mt5:3")).status_code == 422
        assert c.post("/rules", json=noacc, headers=sc(UA, "")).status_code == 422                 # không có tài khoản nào
        # master: được dùng mọi tài khoản hoặc không nêu (toàn bộ)
        assert c.post("/rules", json=other, headers=MASTER).status_code == 201
        assert c.post("/rules", json=noacc, headers=MASTER).status_code == 201


def test_client_channels_and_cooldown_are_forced():
    c, _, _, _ = mk()
    with c:
        r = c.post("/rules", json={**PRICE, "channels": ["ntfy", "telegram", "log", "push"], "cooldown_min": 1, "mode": "repeat"}, headers=A).json()
        assert r["channels"] == ["push"] and r["cooldown_min"] == 5                                # kênh toàn cục bị loại, cooldown tối thiểu 5 phút
        r = c.post("/rules", json={**PRICE, "channels": ["ntfy"]}, headers=A).json()
        assert r["channels"] == ["app"]
        m = c.post("/rules", json={**PRICE, "channels": ["ntfy", "log"]}, headers=MASTER).json()
        assert m["channels"] == ["ntfy", "log"]                                                    # master giữ nguyên


def test_per_user_limit_does_not_consume_global_or_other_users():
    c, store, _, _ = mk()
    with c:
        for _ in range(MAX_RULES_USER):
            assert c.post("/rules", json=PRICE, headers=A).status_code == 201
        assert c.post("/rules", json=PRICE, headers=A).status_code == 422
        assert c.post("/rules", json=PRICE, headers=B).status_code == 201                          # người khác vẫn tạo được
        for _ in range(MAX_RULES):
            assert c.post("/rules", json=PRICE, headers=MASTER).status_code == 201                 # quy tắc client không chiếm hạn mức master
        assert c.post("/rules", json=PRICE, headers=MASTER).status_code == 422
        assert c.get("/rules", headers=A).json()["limits"]["max_rules"] == MAX_RULES_USER


def test_prefs_are_master_only_and_unknown_fields_rejected():
    c, _, _, _ = mk()
    with c:
        assert c.get("/prefs", headers=A).status_code == 403
        assert c.put("/prefs", json={"rev": 0, "prefs": {}}, headers=A).status_code == 403
        assert c.get("/prefs", headers=MASTER).status_code == 200
        # owner/account_id không thể gán qua body (extra=forbid)
        assert c.post("/rules", json={**PRICE, "owner_user_id": UB}, headers=A).status_code == 422
        assert c.post("/rules", json={**PRICE, "account_id": "mt5:2"}, headers=A).status_code == 422


def test_sweep_disables_rules_for_accounts_no_longer_owned():
    c, store, _, _ = mk()
    with c:
        c.post("/rules", json=MARGIN, headers=A)
        c.post("/rules", json=PRICE, headers=A)
        r = c.get("/rules", headers=sc(UA, "mt5:9")).json()["items"]                              # còn tài khoản khác nhưng không còn mt5:1
        by = {x["name"]: x for x in r}
        assert by["Margin"]["enabled"] is False and by["EUR"]["enabled"] is True


# ------------------------------------------------------------------ runner: quy tắc cá nhân không lộ ra kênh toàn cục
async def test_runner_owner_rule_no_global_alert_and_generic_push():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    from tscommon import Bus
    store, sender = MemStore(), Sender()
    push = PushService(store, "priv", "pub", "", Fernet.generate_key().decode(), send_fn=sender)
    real = datetime.now(timezone.utc).timestamp()
    prov = Prov()
    prov.price = {"mid": 1.3, "ts": real, "source": "t"}
    prov.acct = [{**a, "ts": real} for a in prov.acct]
    ev = Evaluator(prov, MarketState(lambda: real), lambda: real)
    run = Runner(store, ev, Bus(r), clock=lambda: real, push=push)
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/xyz", b64(65), b64(16), "ua")
    mine = await store.create_rule(RuleIn.model_validate({**MARGIN, "channels": ["app", "push"], "mode": "once"}), UA)
    await store.create_rule(RuleIn.model_validate({**PRICE, "name": "global", "channels": ["ntfy"]}), None)
    assert await run.tick() == 2
    msgs = await r.xrange("alerts.out")
    assert len(msgs) == 1 and "global" in msgs[0][1]["e"] and "Margin" not in msgs[0][1]["e"]     # chỉ quy tắc toàn cục ra alerts.out (ntfy)
    evs = await store.list_events(None, 10, UA)
    assert len(evs) == 1 and evs[0]["owner_user_id"] == UA and "mt5:1" in evs[0]["body"]          # chi tiết chỉ có trong app (lọc theo chủ)
    assert await store.list_events(None, 10, UB) == []
    assert len(sender.calls) == 1
    pushed = json.loads(sender.calls[0][1])
    assert set(pushed) == {"title", "body", "url"} and pushed["url"] == "/c/#/thong-bao"
    for s in (pushed["title"], pushed["body"]):
        assert "mt5" not in s and not any(ch.isdigit() for ch in s) and "Margin" not in s          # không số dư/tài khoản/tên quy tắc
    assert str(mine["id"]) in store.rules


async def test_runner_owner_rule_without_account_is_skipped():
    store = MemStore()
    real = datetime.now(timezone.utc).timestamp()
    ev = Evaluator(Prov(), MarketState(lambda: real), lambda: real)
    run = Runner(store, ev, None, clock=lambda: real)
    row = await store.create_rule(RuleIn.model_validate({"name": "x", "conditions": [{"type": "account", "metric": "margin_level", "op": "lte", "value": 1e9}]}), UA)
    assert row["owner_user_id"] == UA
    assert await run.tick() == 0 and not store.events                                              # thiếu account_id: bỏ qua (không nhìn thấy mọi tài khoản)


async def test_runner_push_only_when_channel_selected():
    store, sender = MemStore(), Sender()
    push = PushService(store, "priv", "pub", "", Fernet.generate_key().decode(), send_fn=sender)
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/xyz", b64(65), b64(16), None)
    real = datetime.now(timezone.utc).timestamp()
    prov = Prov()
    prov.price = {"mid": 1.3, "ts": real, "source": "t"}
    run = Runner(store, Evaluator(prov, MarketState(lambda: real), lambda: real), None, clock=lambda: real, push=push)
    await store.create_rule(RuleIn.model_validate({**PRICE, "channels": ["app"]}), UA)
    assert await run.tick() == 1 and sender.calls == [] and len(store.events) == 1


# ------------------------------------------------------------------ Web Push
def test_push_subscribe_validation_and_ownership():
    c, store, _, push = mk()
    with c:
        assert c.get("/push", headers=A).json() == {"enabled": True, "public_key": "pubkey", "subscriptions": 0}
        assert c.get("/push").status_code == 403                                                   # service không có user: không dùng push
        s = sub_body()
        r = c.post("/push/subscribe", json=s, headers=A)
        assert r.status_code == 201 and r.json()["subscriptions"] == 1
        stored = list(store.subs.values())[0]
        assert s["endpoint"] not in json.dumps(stored) and s["keys"]["auth"] not in json.dumps(stored)   # đã mã hoá, không lưu rõ
        # B huỷ endpoint của A: ok nhưng KHÔNG xoá; A vẫn còn
        assert c.post("/push/unsubscribe", json={"endpoint": s["endpoint"]}, headers=B).json()["subscriptions"] == 0
        assert c.get("/push", headers=A).json()["subscriptions"] == 1
        # B đăng ký lại cùng endpoint (cùng trình duyệt, đổi tài khoản) -> chuyển chủ; A mất
        assert c.post("/push/subscribe", json=s, headers=B).status_code == 201
        assert c.get("/push", headers=A).json()["subscriptions"] == 0 and c.get("/push", headers=B).json()["subscriptions"] == 1
        assert c.post("/push/unsubscribe", json={"endpoint": s["endpoint"]}, headers=B).json()["subscriptions"] == 0
        # master có user cũng quản lý đăng ký của chính mình
        assert c.post("/push/subscribe", json=sub_body(), headers=MASTER).status_code == 201


@pytest.mark.parametrize("bad", [
    {"endpoint": "http://fcm.googleapis.com/x"},                       # không phải https
    {"endpoint": "https://evil.example/x"},                            # ngoài allowlist (SSRF)
    {"endpoint": "https://fcm.googleapis.com.evil.example/x"},         # giả hậu tố
    {"endpoint": "https://127.0.0.1/x"},
    {"endpoint": "https://169.254.169.254/latest"},
    {"endpoint": "https://user:pw@fcm.googleapis.com/x"},
    {"endpoint": "https://fcm.googleapis.com:8443/x"},
    {"endpoint": "https://fcm.googleapis.com/x#frag"},
    {"keys": {"p256dh": b64(10), "auth": b64(16)}},                    # khoá sai độ dài
    {"keys": {"p256dh": b64(65), "auth": b64(3)}},
])
def test_push_subscribe_rejects_bad(bad):
    c, store, _, _ = mk()
    with c:
        assert c.post("/push/subscribe", json={**sub_body(), **bad}, headers=A).status_code == 422
        assert not store.subs


def test_push_subscribe_allowed_services_and_limit_per_user():
    c, store, _, _ = mk()
    with c:
        for host in ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", "wns2-par02p.notify.windows.com"):
            assert c.post("/push/subscribe", json=sub_body(host), headers=A).status_code == 201, host
        for i in range(8):
            c.post("/push/subscribe", json=sub_body(path=f"/fcm/send/{i}"), headers=A)
        assert c.get("/push", headers=A).json()["subscriptions"] == 5                              # tối đa 5 thiết bị/người, giữ cái mới nhất
        assert c.post("/push/subscribe", json={**sub_body(), "extra": 1}, headers=A).status_code == 422


def test_push_disabled_without_keys():
    store = MemStore()
    app = create_app(store=store, provider=Prov(), redis=fakeredis.aioredis.FakeRedis(decode_responses=True), start_background=False,
                     push=PushService(store))
    with TestClient(app) as c:
        assert c.get("/push", headers=A).json() == {"enabled": False, "public_key": None, "subscriptions": 0}
        assert c.post("/push/subscribe", json=sub_body(), headers=A).status_code == 422
        assert c.post("/push/test", headers=A).status_code == 503


def test_push_test_sends_generic_to_own_devices_only_and_throttles():
    c, _, sender, _ = mk(max_per_hour=2)
    with c:
        c.post("/push/subscribe", json=sub_body(), headers=A)
        c.post("/push/subscribe", json=sub_body(path="/fcm/send/other"), headers=B)
        assert c.post("/push/test", headers=A).json() == {"sent": 1}
        assert len(sender.calls) == 1 and sender.calls[0][0]["endpoint"].endswith("/abc") and sender.calls[0][2] == 3600
        assert c.post("/push/test", headers=A).json() == {"sent": 1}
        assert c.post("/push/test", headers=A).json() == {"sent": 0}                               # vượt giới hạn/giờ
        assert c.post("/push/test", headers=B).json() == {"sent": 1}                               # hạn mức theo người dùng


async def test_push_gone_removes_and_errors_accumulate():
    store, sender = MemStore(), Sender()
    push = PushService(store, "priv", "pub", "", Fernet.generate_key().decode(), send_fn=sender, max_per_hour=100)
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/1", b64(65), b64(16), None)
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/2", b64(65), b64(16), None)
    sender.fail = PushStatusError(410)
    assert await push.notify(UA) == 0 and await store.count_subscriptions(UA) == 0               # 410 Gone: xoá
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/3", b64(65), b64(16), None)
    sender.fail = PushStatusError(500)
    for i in range(4):
        await push.notify(UA)
        assert await store.count_subscriptions(UA) == 1, i
    await push.notify(UA)                                                                         # lần lỗi thứ 5: xoá
    assert await store.count_subscriptions(UA) == 0
    sender.fail = None
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/4", b64(65), b64(16), None)
    assert await push.notify(UA) == 1 and (await store.list_subscriptions(UA))[0]["fail_count"] == 0


async def test_push_notify_never_raises_and_bad_ciphertext_removed():
    store, sender = MemStore(), Sender()
    push = PushService(store, "priv", "pub", "", Fernet.generate_key().decode(), send_fn=sender)
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/1", b64(65), b64(16), None)
    other = PushService(store, "priv", "pub", "", Fernet.generate_key().decode(), send_fn=sender)   # khoá mã hoá khác -> không giải mã được
    assert await other.notify(UA) == 0 and await store.count_subscriptions(UA) == 0
    sender.fail = RuntimeError("boom")
    await push.subscribe(UA, "https://fcm.googleapis.com/fcm/send/2", b64(65), b64(16), None)
    assert await push.notify(UA) == 0


def test_generate_keys_roundtrip():
    from alert_rules.webpush import b64u_decode, generate_keys
    k = generate_keys()
    assert len(b64u_decode(k["VAPID_PRIVATE_KEY"])) == 32 and len(b64u_decode(k["VAPID_PUBLIC_KEY"])) == 65
    Fernet(k["PUSH_ENC_KEY"].encode())
