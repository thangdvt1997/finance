import json

from fastapi.testclient import TestClient

from api_gateway import riskmon_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object()))


def test_risk_proxy_get_only_whitelist(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        return 200, json.dumps({"read_only": True, "accounts": []}).encode()
    monkeypatch.setattr(riskmon_routes, "_fetch", fake)
    with client() as c:
        assert c.get("/v1/risk/accounts").status_code == 401
        assert c.get("/v1/risk/accounts", headers=H).json()["read_only"] is True
        assert c.get("/v1/risk/accounts/demo-mt4-01", headers=H).status_code == 200
        assert seen[-1].endswith("/risk/accounts/demo-mt4-01")
        assert c.get("/v1/risk/../x", headers=H).status_code in (404, 422)
        assert c.get("/v1/risk/admin", headers=H).status_code == 404
        assert c.post("/v1/risk/accounts", headers=H).status_code in (403, 405)
