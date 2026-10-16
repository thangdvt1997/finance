import json

from fastapi.testclient import TestClient

from api_gateway import briefing_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}
BID = "7febad89-5e81-4535-813e-8395fcfa1e09"


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object()))


def stub(monkeypatch, payload=None, code=200):
    seen = []

    def fake(method, url, body):
        seen.append((method, url, body))
        return code, json.dumps(payload or {"items": []}).encode()
    monkeypatch.setattr(briefing_routes, "_call", fake)
    return seen


def test_read_whitelist_and_query_filter(monkeypatch):
    seen = stub(monkeypatch)
    with client() as c:
        assert c.get("/v1/briefing/latest").status_code == 401
        assert c.get("/v1/briefing/latest?scope=vn&edition=morning&evil=1", headers=H).status_code == 200
        assert seen[-1][0] == "GET" and seen[-1][1] == "http://briefing:8000/briefing/latest?scope=vn&edition=morning"
        assert c.get("/v1/briefing/list?limit=5&scope=bad", headers=H).status_code == 200 and seen[-1][1] == "http://briefing:8000/briefing/list?limit=5"
        assert c.get(f"/v1/briefing/{BID}", headers=H).status_code == 200 and seen[-1][1].endswith(f"/briefing/{BID}")
        for bad in ("/v1/briefing/internal/run", "/v1/briefing/..%2Finternal%2Fstatus", "/v1/briefing/latest/x", "/v1/briefing/zzz"):
            assert c.get(bad, headers=H).status_code == 404, bad


def test_read_only_no_write_methods(monkeypatch):
    seen = stub(monkeypatch)
    with client() as c:
        for m in ("post", "put", "delete", "patch"):
            assert getattr(c, m)("/v1/briefing/latest", headers=H).status_code in (403, 405), m
        assert seen == []


def test_upstream_failure_is_502(monkeypatch):
    def boom(*a):
        raise ConnectionError("x")
    monkeypatch.setattr(briefing_routes, "_call", boom)
    with client() as c:
        assert c.get("/v1/briefing/latest", headers=H).status_code == 502
