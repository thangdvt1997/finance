import json

from fastapi.testclient import TestClient

from api_gateway import journal_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object()))


def stub(monkeypatch):
    seen = []

    def fake(method, url, body):
        seen.append((method, url, body))
        return 200, json.dumps({"ok": True}).encode()
    monkeypatch.setattr(journal_routes, "_call", fake)
    return seen


def csrf(c):
    return c.get("/v1/user/csrf", headers=H).json()["token"]


def test_get_whitelist_and_query_filter(monkeypatch):
    seen = stub(monkeypatch)
    with client() as c:
        assert c.get("/v1/journal/accounts").status_code == 401
        assert c.get("/v1/journal/accounts", headers=H).status_code == 200
        r = c.get("/v1/journal/demo-mt5-01/summary?from=2026-10-01&tz=Asia/Ho_Chi_Minh&evil=1&symbol=EUR;USD", headers=H)
        assert r.status_code == 200
        url = seen[-1][1]
        assert url.startswith("http://journal:8000/journal/demo-mt5-01/summary?") and "evil" not in url and "EUR%3BUSD" not in url and "tz=Asia%2FHo_Chi_Minh" in url
        for bad in ("/v1/journal/secret", "/v1/journal/demo/orders", "/v1/journal/demo/notes/deal", "/v1/journal/demo%2F..%2Fpaper/summary"):
            assert c.get(bad, headers=H).status_code == 404, bad


def test_write_only_notes_with_csrf_and_origin(monkeypatch):
    seen = stub(monkeypatch)
    body = {"tags": ["setup:breakout"], "note": "x"}
    path = "/v1/journal/demo-mt5-01/notes/deal/123"
    with client() as c:
        assert c.put(path, json=body, headers=H).status_code == 403                                             # thieu CSRF
        h = {**H, "X-CSRF-Token": csrf(c)}
        assert c.put(path, json=body, headers={**h, "Origin": "http://evil.example"}).status_code == 403          # Origin la
        assert c.put(path, json=body, headers={**h, "Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert c.put(path, content=b"x", headers={**h, "Content-Type": "text/plain"}).status_code == 415
        assert c.put(path, content=b"{" + b" " * 20000 + b"}", headers={**h, "Content-Type": "application/json"}).status_code == 413
        assert not seen
        assert c.put(path, json=body, headers=h).status_code == 200 and seen[-1][0] == "PUT" and seen[-1][1].endswith("/journal/demo-mt5-01/notes/deal/123")
        assert c.delete(path, headers=h).status_code == 200
        for method, p in [("POST", path), ("PUT", "/v1/journal/demo-mt5-01/summary"), ("DELETE", "/v1/journal/demo-mt5-01/deals"),
                          ("PUT", "/v1/journal/demo-mt5-01/notes/other/1"), ("PUT", "/v1/journal/demo-mt5-01/notes/deal/a/b"), ("POST", "/v1/journal/accounts")]:
            assert c.request(method, p, json={}, headers=h).status_code in (404, 405), (method, p)
