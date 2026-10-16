import json

from fastapi.testclient import TestClient

from api_gateway import paper_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def client():
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object())
    return TestClient(app)


def test_paper_proxy_get_only_whitelist_and_query(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        return 200, json.dumps({"simulation": True, "items": []}).encode()
    monkeypatch.setattr(paper_routes, "_fetch", fake)
    with client() as c:
        assert c.get("/v1/paper/overview").status_code == 401                       # cần API key như mọi route /v1
        r = c.get("/v1/paper/accounts/slow_trend_fx/equity", params={"limit": 50}, headers=H)
        assert r.status_code == 200 and r.json()["simulation"] is True
        assert seen[-1].endswith("/paper/accounts/slow_trend_fx/equity?limit=50")
        assert c.get("/v1/paper/overview", headers=H).status_code == 200
        for path in ("accounts/a1/performance", "accounts/a1/tca", "accounts/a1/drift", "accounts/a1/card", "accounts/a1/verify",
                     "accounts/a1/config-versions", "verify", "governance"):                  # chất lượng/quản trị (chỉ-đọc)
            assert c.get(f"/v1/paper/{path}", headers=H).status_code == 200, path
        assert seen[-1].endswith("/paper/governance")
        assert c.get("/v1/paper/accounts/a1/verify/x", headers=H).status_code == 404
        assert c.get("/v1/paper/accounts/x/kill-switch/reset", headers=H).status_code == 404   # không chuyển tiếp lệnh quản trị
        assert c.get("/v1/paper/../../etc/passwd", headers=H).status_code == 404
        assert c.post("/v1/paper/overview", headers=H).status_code in (404, 405)              # chỉ GET


def test_paper_proxy_upstream_down_gives_502(monkeypatch):
    def boom(url):
        raise ConnectionError("x")
    monkeypatch.setattr(paper_routes, "_fetch", boom)
    with client() as c:
        r = c.get("/v1/paper/overview", headers=H)
        assert r.status_code == 502 and "paper-trader" in r.json()["detail"]
