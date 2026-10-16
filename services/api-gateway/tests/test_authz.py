"""Phân quyền master/client + IDOR (authz.py). client A (mt5:1) KHÔNG đọc/ghi được dữ liệu của client B (mt5:2) bằng bất kỳ endpoint/tham số/WebSocket nào."""
import asyncio
import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from tscommon import make_event

from api_gateway import journal_routes, paper_routes, reports_routes, riskmon_routes, user_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
SECRET = "trust-secret-xyz"
KEY = {"X-API-Key": "tok1"}


USER_HDRS: list = []


def hdr(role: str, accounts: str = "", uid: str = "u1", secret: str = SECRET) -> dict:
    h = {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": secret}
    if accounts:
        h["X-Accounts"] = accounts
    return h


CLIENT_A = hdr("client", "mt5:1", "ua")
CLIENT_B = hdr("client", "mt5:2", "ub")
CLIENT_NONE = hdr("client", "", "uc")
MASTER = hdr("master", "*", "um")


def repo():
    snap = lambda acc, bal: {"account_id": acc, "platform": "mt5", "ts": NOW, "balance": bal, "equity": bal, "margin": 0}  # noqa: E731
    return InMemoryRepo(
        account_snapshots=[snap("mt5:1", 100), snap("mt5:2", 200), snap("demo-mt4-01", 300)],
        quotes=[{"symbol": "EURUSD", "ts": NOW, "bid": 1.1, "ask": 1.2, "source": "t"}],
        news_items=[{"url": "u", "title": "n", "published_at": NOW, "source": "rss", "symbols": ["EURUSD"]}],
        alerts=[{"id": 1, "ts": NOW, "level": "warn", "title": "w"}])


def make(monkeypatch, secret=SECRET, redis=None):
    calls = []

    def journal_call(method, url, body):
        calls.append((method, url))
        if url.endswith("/journal/accounts"):
            return 200, json.dumps({"items": [{"account_id": a} for a in ("mt5:1", "mt5:2", "demo-mt4-01")], "read_only": True}).encode()
        return 200, json.dumps({"ok": True, "url": url}).encode()

    def risk_fetch(url):
        calls.append(("GET", url))
        if url.endswith("/risk/accounts"):
            return 200, json.dumps({"read_only": True, "accounts": [{"account_id": a} for a in ("mt5:1", "mt5:2")]}).encode()
        return 200, json.dumps({"account_id": url.rsplit("/", 1)[-1]}).encode()

    def other_fetch(url):
        calls.append(("GET", url))
        return 200, b"{}"

    monkeypatch.setattr(journal_routes, "_call", journal_call)
    monkeypatch.setattr(user_routes, "_call", lambda m, u, b, h=None: (calls.append((m, u)) or USER_HDRS.append(h) or (200, b"{}")))
    monkeypatch.setattr(riskmon_routes, "_fetch", risk_fetch)
    monkeypatch.setattr(paper_routes, "_fetch", other_fetch)
    monkeypatch.setattr(reports_routes, "_fetch", other_fetch)
    st = GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=secret, ws_max_connections=5)
    return TestClient(create_app(st, repo=repo(), redis=redis if redis is not None else object())), calls


# ---------------------------------------------------------------- tin cậy header
def test_header_trust(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/me").status_code == 401                                              # vẫn cần API key
        assert c.get("/v1/me", headers=KEY).json()["kind"] == "service"                        # dịch vụ nội bộ: quyền master
        assert c.get("/v1/me", headers={**KEY, "X-Role": "master"}).status_code == 403         # giả mạo: thiếu secret
        assert c.get("/v1/me", headers={**KEY, "X-Accounts": "mt5:2"}).status_code == 403
        assert c.get("/v1/me", headers={**KEY, "X-User-Id": "x"}).status_code == 403
        assert c.get("/v1/me", headers=hdr("master", secret="sai")).status_code == 403         # secret sai
        assert c.get("/v1/me", headers=hdr("anon")).status_code == 403                         # role lạ
        assert c.get("/v1/me", headers=hdr("admin")).status_code == 403
        assert c.get("/v1/me", headers=MASTER).json()["role"] == "master"
    c2, _ = make(monkeypatch, secret="")                                                       # chưa cấu hình secret: từ chối mọi header người dùng
    with c2:
        assert c2.get("/v1/me", headers=MASTER).status_code == 403
        assert c2.get("/v1/me", headers={**KEY, "X-Auth-Secret": ""}).json()["kind"] == "service"


def test_me_and_wildcard_stripped(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        me = c.get("/v1/me", headers=CLIENT_A).json()
        assert me["role"] == "client" and me["accounts"] == ["mt5:1"] and me["all_accounts"] is False
        star = c.get("/v1/me", headers=hdr("client", "*,mt5:1")).json()                        # "*" không cấp quyền cho client
        assert star["accounts"] == ["mt5:1"]
        assert c.get("/v1/accounts", headers=hdr("client", "*")).json() == []
        m = c.get("/v1/me", headers=MASTER).json()
        assert m["all_accounts"] is True and set(m["accounts"]) == {"mt5:1", "mt5:2", "demo-mt4-01"}


# ---------------------------------------------------------------- lọc theo tài khoản
def test_accounts_overview_filtered(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        ids = lambda r: sorted(a["account_id"] for a in r)  # noqa: E731
        assert ids(c.get("/v1/accounts", headers=CLIENT_A).json()) == ["mt5:1"]
        assert ids(c.get("/v1/accounts", headers=CLIENT_B).json()) == ["mt5:2"]
        assert c.get("/v1/accounts", headers=CLIENT_NONE).json() == []
        assert ids(c.get("/v1/accounts", headers=MASTER).json()) == ["demo-mt4-01", "mt5:1", "mt5:2"]
        assert ids(c.get("/v1/accounts", headers=KEY).json()) == ["demo-mt4-01", "mt5:1", "mt5:2"]
        ov = c.get("/v1/overview", headers=CLIENT_A).json()
        assert ids(ov["accounts"]) == ["mt5:1"] and "mt5:2" not in json.dumps(ov)
        assert len(c.get("/v1/overview", headers=MASTER).json()["accounts"]) == 3


def test_equity_history_idor(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/equity-history?account_id=mt5:1", headers=CLIENT_A).status_code == 200
        for bad in ("mt5:2", "demo-mt4-01", "mt5:999", "MT5:1", "mt5:1%20", "mt5:1.", ""):
            r = c.get("/v1/equity-history", params={"account_id": bad}, headers=CLIENT_A)
            assert r.status_code in (403, 422), (bad, r.status_code)
        # không có oracle: tài khoản không tồn tại và tài khoản của người khác trả CÙNG mã
        assert c.get("/v1/equity-history?account_id=mt5:2", headers=CLIENT_A).status_code == c.get("/v1/equity-history?account_id=mt5:77", headers=CLIENT_A).status_code == 403
        # tham số lặp: cố lách bằng 2 giá trị
        assert c.get("/v1/equity-history?account_id=mt5:1&account_id=mt5:2", headers=CLIENT_A).status_code == 403
        assert c.get("/v1/equity-history?account_id=mt5:2&account_id=mt5:1", headers=CLIENT_A).status_code == 403
        assert c.get("/v1/equity-history?account_id=mt5:2", headers=MASTER).status_code == 200
        assert c.get("/v1/equity-history?account_id=mt5:2", headers=CLIENT_B).status_code == 200


def test_risk_idor_and_filter(monkeypatch):
    c, calls = make(monkeypatch)
    with c:
        assert [a["account_id"] for a in c.get("/v1/risk/accounts", headers=CLIENT_A).json()["accounts"]] == ["mt5:1"]
        assert len(c.get("/v1/risk/accounts", headers=MASTER).json()["accounts"]) == 2
        assert c.get("/v1/risk/accounts/mt5:1", headers=CLIENT_A).status_code == 200
        calls.clear()
        for bad in ("/v1/risk/accounts/mt5:2", "/v1/risk/accounts/mt5:2/", "/v1/risk/accounts/mt5:1%2F..%2Fmt5:2", "/v1/risk/accounts/mt5:1/../mt5:2",
                    "/v1/risk/accounts/MT5:1", "/v1/risk/accounts/mt5:3"):
            r = c.get(bad, headers=CLIENT_A)
            assert r.status_code in (403, 404), (bad, r.status_code)
        assert not any("mt5:2" in u or "mt5:3" in u for _, u in calls), calls   # không một request nào tới risk-monitor cho tài khoản người khác
        assert c.get("/v1/risk/config", headers=CLIENT_A).status_code == 200


def test_journal_idor_read_and_write(monkeypatch):
    c, calls = make(monkeypatch)
    csrf = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
    wh = {**CLIENT_A, "X-CSRF-Token": csrf}
    with c:
        assert [a["account_id"] for a in c.get("/v1/journal/accounts", headers=CLIENT_A).json()["items"]] == ["mt5:1"]
        assert len(c.get("/v1/journal/accounts", headers=MASTER).json()["items"]) == 3
        for sub in ("summary", "deals", "discipline", "excursions", "review", "notes"):
            assert c.get(f"/v1/journal/mt5:1/{sub}", headers=CLIENT_A).status_code == 200, sub
        calls.clear()
        for sub in ("summary", "deals", "discipline", "excursions", "review", "notes"):
            assert c.get(f"/v1/journal/mt5:2/{sub}", headers=CLIENT_A).status_code == 403, sub
        for bad in ("/v1/journal/mt5:2/summary", "/v1/journal/MT5:1/summary", "/v1/journal/mt5:1%2F..%2Fmt5:2/summary", "/v1/journal/mt5:1/../mt5:2/summary",
                    "/v1/journal/mt5:1%2e%2e/mt5:2/summary", "/v1/journal//mt5:2/summary"):
            r = c.get(bad, headers=CLIENT_A)
            assert r.status_code in (403, 404), (bad, r.status_code)
        # ghi ghi chú của tài khoản người khác bị chặn TRƯỚC cả CSRF; của mình thì được
        assert c.put("/v1/journal/mt5:2/notes/deal/123", json={"note": "x"}, headers=wh).status_code == 403
        assert c.delete("/v1/journal/mt5:2/notes/deal/123", headers=wh).status_code == 403
        assert c.put("/v1/journal/mt5:2/notes/deal/123", json={"note": "x"}, headers=CLIENT_A).status_code == 403
        assert not any("mt5:2" in u for _, u in calls), calls
        assert c.put("/v1/journal/mt5:1/notes/deal/123", json={"note": "x"}, headers=wh).status_code == 200
        assert c.put("/v1/journal/mt5:1/notes/deal/123", json={"note": "x"}, headers=CLIENT_A).status_code == 403   # thiếu CSRF
        assert c.get("/v1/journal/mt5:2/summary", headers=MASTER).status_code == 200
        assert c.get("/v1/journal/mt5:2/summary", headers=CLIENT_B).status_code == 200


# ---------------------------------------------------------------- mặc định từ chối cho client
MASTER_ONLY_GET = ["/v1/system", "/v1/alerts", "/v1/data-sources", "/v1/reports", "/v1/reports/daily/2026-10-01.html", "/v1/paper/overview",
                   "/v1/paper/accounts", "/v1/paper/accounts/demo/equity", "/v1/user/prefs"]
PUBLIC_GET = ["/v1/quotes/latest", "/v1/news", "/v1/calendar", "/v1/experts", "/v1/expert-signals", "/v1/expert-positions", "/v1/symbols",
              "/v1/risk-windows", "/v1/analytics/overview", "/v1/analytics/sessions", "/v1/vn/overview", "/v1/user/csrf"]


def test_master_only_denied_for_client(monkeypatch):
    c, calls = make(monkeypatch)
    with c:
        for p in MASTER_ONLY_GET:
            assert c.get(p, headers=CLIENT_A).status_code == 403, p
            assert c.get(p, headers=CLIENT_NONE).status_code == 403, p
        assert not calls
        # prefs toàn cục (ghi/đọc): chỉ master. Quy tắc cảnh báo cá nhân: client được phép (alert-rules lọc theo chủ sở hữu) -> test_user_rules_scope
        csrf = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        h = {**CLIENT_A, "X-CSRF-Token": csrf}
        assert c.put("/v1/user/prefs", json={}, headers=h).status_code == 403
        assert c.get("/v1/user/prefs", headers=CLIENT_A).status_code == 403
        assert c.get("/v1/user/nope", headers=CLIENT_A).status_code == 403
        # master/service vẫn vào được
        for p in ("/v1/system", "/v1/alerts", "/v1/paper/overview", "/v1/user/rules", "/v1/reports"):
            assert c.get(p, headers=MASTER).status_code != 403, p
            assert c.get(p, headers=KEY).status_code != 403, p
        # route lạ/không có trong whitelist role client: 403 (không lộ có tồn tại hay không)
        assert c.get("/v1/does-not-exist", headers=CLIENT_A).status_code in (403, 404)   # route không tồn tại: 404 của FastAPI (không tới được handler)
        assert c.get("/v1/does-not-exist", headers=MASTER).status_code == 404


def test_public_data_for_client(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        for p in PUBLIC_GET:
            assert c.get(p, headers=CLIENT_A).status_code not in (401, 403), p
        assert c.get("/v1/news", headers=CLIENT_A).json()["count"] == 1
        assert c.get("/v1/quotes/latest", headers=CLIENT_A).status_code == 200


def test_client_cannot_use_non_get_on_readonly(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        for m in ("post", "put", "delete", "patch"):
            assert getattr(c, m)("/v1/accounts", headers=CLIENT_A).status_code in (403, 405)
            assert getattr(c, m)("/v1/equity-history?account_id=mt5:1", headers=CLIENT_A).status_code in (403, 405)


# ---------------------------------------------------------------- WebSocket
class _Redis:
    def __init__(self, events):
        self.events = list(events)
        self.n = 0                                   # id tăng dần: app cache JSON theo (stream, id) dùng chung giữa kết nối

    async def xread(self, streams, count=None, block=None):
        if self.events:
            st, ev = self.events.pop(0)
            self.n += 1
            return [(st, [(f"{self.n}-0", {"e": ev.model_dump_json()})])]
        await asyncio.sleep(0.05)
        return []


def _wait_closed(app):
    deadline = time.monotonic() + 5
    while app.state.ws_count != 0 and time.monotonic() < deadline:
        time.sleep(0.01)


def _evs():
    return [("account.snapshots", make_event("account", "t", {"account_id": a, "balance": b})) for a, b in (("mt5:2", 200), ("mt5:1", 100), ("demo-mt4-01", 3))] + [
        ("account.snapshots", make_event("account", "t", {"balance": 9})),                                       # không nêu tài khoản
        ("md.quotes", make_event("quote", "t", {"symbol": "EURUSD", "bid": 1, "ask": 2, "source": "t"}))]


def test_ws_client_sees_only_own_account(monkeypatch):
    c, _ = make(monkeypatch, redis=_Redis(_evs()))
    with c.websocket_connect("/v1/stream?streams=account.snapshots,md.quotes", headers=CLIENT_A) as ws:
        assert ws.receive_json()["type"] == "ready"
        got = [ws.receive_json(), ws.receive_json()]
    assert [(m["stream"], m["event"]["payload"].get("account_id") or m["event"]["payload"].get("symbol")) for m in got] == [
        ("account.snapshots", "mt5:1"), ("md.quotes", "EURUSD")]            # mt5:2 / demo / không-nêu-tài-khoản đều bị lọc


def test_ws_master_sees_all_and_forbidden_cases(monkeypatch):
    c, _ = make(monkeypatch, redis=_Redis(_evs()))
    with c.websocket_connect("/v1/stream?streams=account.snapshots", headers=MASTER) as ws:
        assert ws.receive_json()["type"] == "ready"
        assert [ws.receive_json()["event"]["payload"].get("account_id") for _ in range(4)] == ["mt5:2", "mt5:1", "demo-mt4-01", None]
    for h, q in ((CLIENT_A, "alerts.out"), (CLIENT_A, "md.quotes,alerts.out")):          # stream chỉ master
        with pytest.raises(Exception):
            with c.websocket_connect(f"/v1/stream?streams={q}", headers=h):
                pass
    with pytest.raises(Exception):                                                       # giả mạo: header người dùng mà thiếu secret
        with c.websocket_connect("/v1/stream", headers={**KEY, "X-Role": "master"}):
            pass


def test_ws_default_streams_exclude_alerts_for_client(monkeypatch):
    c, _ = make(monkeypatch, redis=_Redis([]))
    with c.websocket_connect("/v1/stream", headers=CLIENT_A) as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready" and "alerts.out" not in ready["streams"] and "account.snapshots" in ready["streams"]


# ---------------------------------------------------------------- cảnh báo cá nhân + lệnh chờ + push (client)
UUID0 = "00000000-0000-0000-0000-000000000000"
RULE_BODY = {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]}


def test_user_rules_scope_headers_and_whitelist(monkeypatch):
    c, calls = make(monkeypatch)
    with c:
        csrf = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        h = {**CLIENT_A, "X-CSRF-Token": csrf}
        USER_HDRS.clear()
        assert c.get("/v1/user/rules", headers=CLIENT_A).status_code == 200
        assert USER_HDRS[-1] == {"X-Owner-Role": "client", "X-Owner-User": "ua", "X-Owner-Accounts": "mt5:1"} or USER_HDRS[-1]["X-Owner-User"] == "ua"
        # client không tự đặt được danh tính chủ sở hữu: header giả bị bỏ qua, luôn dùng danh tính do nginx xác thực
        spoof = {**CLIENT_A, "X-Owner-User": "ub", "X-Owner-Accounts": "mt5:2", "X-Owner-Role": "master"}
        assert c.get("/v1/user/rules", headers=spoof).status_code == 200
        assert USER_HDRS[-1]["X-Owner-User"] == "ua" and USER_HDRS[-1]["X-Owner-Accounts"] == "mt5:1" and USER_HDRS[-1]["X-Owner-Role"] == "client"
        # ghi: có CSRF -> tới alert-rules kèm phạm vi
        for method, path in (("POST", "/v1/user/rules"), ("POST", "/v1/user/rules/preview"), ("PUT", f"/v1/user/rules/{UUID0}"),
                             ("DELETE", f"/v1/user/rules/{UUID0}"), ("POST", f"/v1/user/rules/{UUID0}/preview"),
                             ("POST", "/v1/user/push/subscribe"), ("POST", "/v1/user/push/unsubscribe")):
            USER_HDRS.clear()
            assert c.request(method, path, json=RULE_BODY, headers=h).status_code == 200, (method, path)
            assert USER_HDRS[-1]["X-Owner-User"] == "ua", (method, path)
        assert c.get("/v1/user/push", headers=CLIENT_A).status_code == 200
        assert c.get("/v1/user/rule-events", headers=CLIENT_A).status_code == 200
        # ngoài whitelist client: 403/404/405
        for method, path in (("PUT", "/v1/user/prefs"), ("GET", "/v1/user/prefs"), ("POST", "/v1/user/push"), ("DELETE", "/v1/user/push/subscribe"),
                             ("DELETE", "/v1/user/rule-events"), ("POST", "/v1/user/orders")):
            assert c.request(method, path, json={}, headers=h).status_code in (403, 404, 405), (method, path)
        # thiếu CSRF vẫn chặn
        assert c.post("/v1/user/rules", json=RULE_BODY, headers=CLIENT_A).status_code == 403
        # client không có user_id hợp lệ -> 403 (không thể gắn chủ sở hữu)
        assert c.get("/v1/user/rules", headers=hdr("client", "mt5:1", "x")).status_code == 403
        # master/service: KHÔNG có header phạm vi client (thấy tất cả); master có user_id chỉ gửi vai trò master
        USER_HDRS.clear()
        assert c.get("/v1/user/rules", headers=KEY).status_code == 200 and USER_HDRS[-1] is None
        assert c.get("/v1/user/rules", headers=hdr("master", "*", "um-12345678")).status_code == 200
        assert USER_HDRS[-1] == {"X-Owner-Role": "master", "X-Owner-User": "um-12345678"}


def test_account_orders_idor(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/accounts/mt5:1/orders", headers=CLIENT_A).status_code == 200
        assert c.get("/v1/accounts/mt5:1/orders", headers=CLIENT_B).status_code == 403
        assert c.get("/v1/accounts/mt5:2/orders", headers=CLIENT_A).status_code == 403
        assert c.get("/v1/accounts/zzz/orders", headers=CLIENT_A).status_code == 403          # không tồn tại == của người khác (không oracle)
        assert c.get("/v1/accounts/mt5:1/orders", headers=CLIENT_NONE).status_code == 403
        assert c.get("/v1/accounts/mt5%3A2/orders", headers=CLIENT_A).status_code == 403      # mã hoá %3A không lách được
        assert c.get("/v1/accounts/mt5:1/orders?status=bad", headers=CLIENT_A).status_code == 422
        for m in ("post", "put", "delete"):
            assert getattr(c, m)("/v1/accounts/mt5:1/orders", headers=CLIENT_A).status_code in (403, 405)
        assert c.get("/v1/accounts/mt5:2/orders", headers=MASTER).status_code == 200
        assert c.get("/v1/accounts/mt5:2/orders", headers=KEY).status_code == 200


def test_orders_and_currency_in_accounts(monkeypatch):
    t = datetime.now(timezone.utc)
    r = InMemoryRepo(
        account_snapshots=[{"account_id": "mt5:1", "platform": "mt5", "ts": t, "balance": 1, "equity": 1, "margin": 0, "currency": "EUR"},
                           {"account_id": "mt5:2", "platform": "mt5", "ts": t, "balance": 2, "equity": 2, "margin": 0, "currency": "USD"}],
        account_orders=[{"account_id": "mt5:1", "order_id": "7001", "symbol": "EURUSD", "kind": "buy_limit", "volume": 0.3, "price": 1.07, "sl": 1.0, "tp": 1.2,
                         "time_setup": t, "status": "open"},
                        {"account_id": "mt5:1", "order_id": "7000", "symbol": "XAUUSD", "kind": "sell_stop", "volume": 0.1, "price": 2600, "status": "removed", "time_setup": t},
                        {"account_id": "mt5:2", "order_id": "9001", "symbol": "GBPUSD", "kind": "buy_stop", "volume": 1, "price": 1.3, "status": "open", "time_setup": t}])
    monkeypatch.setattr(user_routes, "_call", lambda *a, **k: (200, b"{}"))
    st = GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET, ws_max_connections=5)
    c = TestClient(create_app(st, repo=r, redis=object()))
    with c:
        a = c.get("/v1/accounts", headers=CLIENT_A).json()
        assert [x["account_id"] for x in a] == ["mt5:1"] and a[0]["currency"] == "EUR"
        assert [o["order_id"] for o in a[0]["orders"]] == ["7001"]                              # chỉ lệnh đang mở của tài khoản mình
        assert [x["currency"] for x in c.get("/v1/accounts", headers=MASTER).json()] == ["EUR", "USD"]
        assert [o["order_id"] for o in c.get("/v1/accounts/mt5:1/orders", headers=CLIENT_A).json()] == ["7001"]
        assert {o["order_id"] for o in c.get("/v1/accounts/mt5:1/orders?status=all", headers=CLIENT_A).json()} == {"7001", "7000"}
        assert [o["order_id"] for o in c.get("/v1/accounts/mt5:1/orders?status=removed", headers=CLIENT_A).json()] == ["7000"]
        assert [o["order_id"] for o in c.get("/v1/accounts/mt5:2/orders", headers=CLIENT_B).json()] == ["9001"]
        ov = c.get("/v1/overview", headers=CLIENT_B).json()["accounts"]
        assert [x["account_id"] for x in ov] == ["mt5:2"] and ov[0]["currency"] == "USD" and ov[0]["orders"][0]["order_id"] == "9001"


# ---------------------------------------------------------------- giới hạn/thông báo/prefs/thiết bị/ticket (2026-10-12)
def test_client_limits_notifications_prefs_tickets_whitelist(monkeypatch):
    c, calls = make(monkeypatch)
    with c:
        csrf = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        h = {**CLIENT_A, "X-CSRF-Token": csrf}
        USER_HDRS.clear()
        urls = []
        monkeypatch.setattr(user_routes, "_call", lambda m, u, b, hh=None: (urls.append((m, u)) or USER_HDRS.append(hh) or (200, b"{}")))
        # đọc: tài khoản của mình qua; tài khoản người khác -> 403 ngay ở gateway; thiếu account_id -> 403
        assert c.get("/v1/user/limits?account_id=mt5:1", headers=CLIENT_A).status_code == 200
        assert urls[-1] == ("GET", "http://alert-rules:8000/limits?account_id=mt5%3A1")
        assert c.get("/v1/user/limits/history?account_id=mt5:1&limit=20", headers=CLIENT_A).status_code == 200
        for p in ("/v1/user/limits?account_id=mt5:2", "/v1/user/limits/history?account_id=mt5:2", "/v1/user/limits"):
            assert c.get(p, headers=CLIENT_A).status_code == 403, p
        n = len(urls)
        assert c.get("/v1/user/notifications?kind=limit&unread=1&limit=30&before=99&evil=1&kind=x", headers=CLIENT_A).status_code == 200
        assert urls[n][1] == "http://alert-rules:8000/notifications?kind=limit&unread=1&limit=30&before=99"      # khoá lạ/giá trị lạ bị bỏ
        for p in ("/v1/user/client-prefs", "/v1/user/push/devices", "/v1/user/tickets"):
            assert c.get(p, headers=CLIENT_A).status_code == 200, p
        # ghi cần CSRF; có CSRF thì tới alert-rules kèm phạm vi chủ sở hữu
        body = {"account_id": "mt5:1", "key": "daily_loss_pct", "value": 5}
        assert c.put("/v1/user/limits", json=body, headers=CLIENT_A).status_code == 403
        for method, path, b in (("PUT", "/v1/user/limits", body), ("POST", "/v1/user/notifications/read", {"all": True}),
                                ("PUT", "/v1/user/client-prefs", {"rev": 0, "data": {}}), ("POST", "/v1/user/tickets", {"category": "other", "message": "xin chào"}),
                                ("DELETE", "/v1/user/push/devices/0123456789abcdef", None)):
            USER_HDRS.clear()
            r = c.request(method, path, json=b, headers=h) if b is not None else c.request(method, path, headers=h)
            assert r.status_code == 200, (method, path, r.status_code)
            assert USER_HDRS[-1]["X-Owner-User"] == "ua" and USER_HDRS[-1]["X-Owner-Accounts"] == "mt5:1"
        # client KHÔNG cập nhật ticket, không gọi đường nội bộ, không method lạ
        for method, path in (("PUT", "/v1/user/tickets/5"), ("DELETE", "/v1/user/tickets/5"), ("POST", "/v1/user/internal/notifications"), ("GET", "/v1/user/internal/notifications"),
                             ("DELETE", "/v1/user/push/devices/zz"), ("DELETE", "/v1/user/limits"), ("POST", "/v1/user/limits"), ("PUT", "/v1/user/notifications/read")):
            assert c.request(method, path, json={"status": "ack"}, headers=h).status_code in (403, 404, 405), (method, path)
        # master cập nhật ticket qua đường master (có CSRF)
        mh = {**MASTER, "X-CSRF-Token": c.get("/v1/user/csrf", headers=MASTER).json()["token"]}
        assert c.put("/v1/user/tickets/5", json={"status": "ack"}, headers=mh).status_code == 200
        assert urls[-1] == ("PUT", "http://alert-rules:8000/tickets/5")
        assert c.get("/v1/user/tickets", headers=MASTER).status_code == 200


# ---------------------------------------------------------------- CSRF gắn phiên (pentest 2026-10-14)
def test_csrf_bound_to_session(monkeypatch):
    c, _ = make(monkeypatch)
    body = {"name": "r", "account_id": "mt5:1"}
    with c:
        ta = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        tb = c.get("/v1/user/csrf", headers=CLIENT_B).json()["token"]
        assert ta != tb
        # token của phiên B KHÔNG dùng được cho phiên A (trước đây dùng chung toàn hệ thống)
        assert c.post("/v1/user/rules", json=body, headers={**CLIENT_A, "X-CSRF-Token": tb}).status_code == 403
        assert c.post("/v1/user/rules", json=body, headers={**CLIENT_A, "X-CSRF-Token": ta}).status_code != 403
        # cùng user nhưng cookie phiên khác -> token khác
        c.cookies.set("ts_session", "sid-1")
        t1 = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        c.cookies.set("ts_session", "sid-2")
        assert c.post("/v1/user/rules", json=body, headers={**CLIENT_A, "X-CSRF-Token": t1}).status_code == 403
        t2 = c.get("/v1/user/csrf", headers=CLIENT_A).json()["token"]
        assert t2 != t1 and c.post("/v1/user/rules", json=body, headers={**CLIENT_A, "X-CSRF-Token": t2}).status_code != 403
        # token toàn cục kiểu cũ không còn hợp lệ ở chế độ session
        legacy = user_routes.csrf_token("tok1", int(time.time() // 3600))
        assert c.post("/v1/user/rules", json=body, headers={**CLIENT_A, "X-CSRF-Token": legacy}).status_code == 403


def test_csrf_global_rollback(monkeypatch):
    monkeypatch.setattr(user_routes, "CSRF_BIND", "global")
    c, _ = make(monkeypatch)
    with c:
        tb = c.get("/v1/user/csrf", headers=CLIENT_B).json()["token"]
        assert tb == user_routes.csrf_token("tok1", int(time.time() // 3600))
        assert c.post("/v1/user/rules", json={"name": "r"}, headers={**CLIENT_A, "X-CSRF-Token": tb}).status_code != 403
