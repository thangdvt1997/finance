import json
import time

from fastapi.testclient import TestClient

from api_gateway import user_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}
RID = "123e4567-e89b-12d3-a456-426614174000"
BODY = {"name": "x", "conditions": [{"type": "price", "symbol": "EURUSD", "op": "gte", "value": 1.2}]}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object()))


def csrf(c):
    return c.get("/v1/user/csrf", headers=H).json()["token"]


def stub(monkeypatch):
    seen = []

    def fake(method, url, body):
        seen.append((method, url, body))
        return 200, json.dumps({"ok": True}).encode()
    monkeypatch.setattr(user_routes, "_call", fake)
    return seen


def test_requires_api_key_and_csrf(monkeypatch):
    seen = stub(monkeypatch)
    with client() as c:
        assert c.get("/v1/user/rules").status_code == 401
        assert c.get("/v1/user/rules", headers=H).status_code == 200
        assert c.post("/v1/user/rules", json=BODY, headers=H).status_code == 403            # thiếu CSRF
        assert c.post("/v1/user/rules", json=BODY, headers={**H, "X-CSRF-Token": "bad"}).status_code == 403
        n = len(seen)
        r = c.post("/v1/user/rules", json=BODY, headers={**H, "X-CSRF-Token": csrf(c)})
        assert r.status_code == 200 and seen[n][0] == "POST" and seen[n][1].endswith("/rules")


def test_whitelist_only(monkeypatch):
    seen = stub(monkeypatch)
    with client() as c:
        h = {**H, "X-CSRF-Token": csrf(c)}
        for method, path in [("POST", "/v1/user/orders"), ("POST", "/v1/user/rules/x"), ("DELETE", "/v1/user/prefs"),
                             ("PUT", "/v1/user/rules"), ("POST", "/v1/user/../paper/accounts"), ("PUT", f"/v1/user/rules/{RID}/preview"),
                             ("DELETE", "/v1/user/rule-events"), ("POST", "/v1/user/csrf")]:
            r = c.request(method, path, json={}, headers=h)
            assert r.status_code in (404, 405), (method, path, r.status_code)
        assert c.get("/v1/user/secret", headers=H).status_code == 404
        assert not seen
        for method, path in [("PUT", f"/v1/user/rules/{RID}"), ("DELETE", f"/v1/user/rules/{RID}"), ("POST", f"/v1/user/rules/{RID}/preview"),
                             ("POST", "/v1/user/rules/preview"), ("PUT", "/v1/user/prefs")]:
            assert c.request(method, path, json=BODY, headers=h).status_code == 200, (method, path)


def test_origin_content_type_and_size(monkeypatch):
    stub(monkeypatch)
    with client() as c:
        h = {**H, "X-CSRF-Token": csrf(c)}
        assert c.post("/v1/user/rules", json=BODY, headers={**h, "Origin": "https://evil.example"}).status_code == 403
        assert c.post("/v1/user/rules", json=BODY, headers={**h, "Origin": "http://testserver"}).status_code == 200
        assert c.post("/v1/user/rules", json=BODY, headers={**h, "Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert c.post("/v1/user/rules", content=b"x=1", headers={**h, "Content-Type": "text/plain"}).status_code == 415
        assert c.post("/v1/user/rules", content=b"{bad", headers={**h, "Content-Type": "application/json"}).status_code == 400
        big = json.dumps({"name": "x" * 20000})
        assert c.post("/v1/user/rules", content=big, headers={**h, "Content-Type": "application/json"}).status_code == 413


def test_csrf_expiry_and_query_filter(monkeypatch):
    seen = stub(monkeypatch)
    assert user_routes.csrf_ok("s", user_routes.csrf_token("s", int(time.time() // 3600) - 1))
    assert not user_routes.csrf_ok("s", user_routes.csrf_token("s", int(time.time() // 3600) - 2))
    assert not user_routes.csrf_ok("", "x") and not user_routes.csrf_ok("s", None)
    with client() as c:
        c.get(f"/v1/user/rule-events?rule_id={RID}&limit=20&evil=1&x=%3Bdrop", headers=H)
        assert seen[-1][1].endswith(f"/rule-events?rule_id={RID}&limit=20")
