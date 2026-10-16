"""/v1/patterns*: proxy GET chỉ-đọc tới pattern-engine; master xem mọi trạng thái, client chỉ armed|triggered; client không thấy tham số/lý do nội bộ."""
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from api_gateway import patterns_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

KEY = {"X-API-Key": "tok1"}
SECRET = "trust-secret-xyz"


def hdr(role, accounts="", uid="u1"):
    h = {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET}
    if accounts:
        h["X-Accounts"] = accounts
    return h


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET),
                                 repo=InMemoryRepo(), redis=object()))


ITEMS = [{"id": 1, "pattern": "KB-1", "state": "triggered", "reason": None},
         {"id": 2, "pattern": "KB-2", "state": "invalid", "reason": "nội bộ"}]


def fake_fetch(seen):
    def f(url):
        seen.append(url)
        if "/patterns/spec" in url:
            return 200, json.dumps({"items": [{"id": "KB-1", "name": "x", "params": {"lead_min_atr": 6.0}}]}).encode()
        return 200, json.dumps({"items": ITEMS}).encode()
    return f


def test_master_sees_all_states_client_only_armed_triggered(monkeypatch):
    seen = []
    monkeypatch.setattr(patterns_routes, "_fetch", fake_fetch(seen))
    with client() as c:
        assert c.get("/v1/patterns").status_code == 401
        r = c.get("/v1/patterns", headers=hdr("master", "*", "um"))
        assert r.status_code == 200 and parse_qs(urlparse(seen[-1]).query)["state"] == ["forming,armed,triggered,invalid"]
        assert r.json()["items"][1]["reason"] == "nội bộ"
        rc = c.get("/v1/patterns", headers=hdr("client", "mt5:1", "ua"), params={"state": "forming,invalid,triggered"})
        assert rc.status_code == 200
        assert parse_qs(urlparse(seen[-1]).query)["state"] == ["triggered"]       # client bị thu hẹp
        assert all("reason" not in i and "id" not in i for i in rc.json()["items"])
        # client chỉ xin trạng thái bị cấm -> rỗng, không gọi pattern-engine
        n = len(seen)
        assert c.get("/v1/patterns", headers=hdr("client", "mt5:1", "ua"), params={"state": "invalid"}).json()["items"] == []
        assert len(seen) == n


def test_spec_hides_params_from_client_and_validates_input(monkeypatch):
    monkeypatch.setattr(patterns_routes, "_fetch", fake_fetch([]))
    with client() as c:
        assert "params" in c.get("/v1/patterns/spec", headers=hdr("master", "*", "um")).json()["items"][0]
        assert "params" not in c.get("/v1/patterns/spec", headers=hdr("client", "mt5:1", "ua")).json()["items"][0]
        assert c.get("/v1/patterns", headers=hdr("master", "*", "um"), params={"symbol": "x y!"}).status_code == 422
        assert c.get("/v1/patterns", headers=hdr("master", "*", "um"), params={"tf": "M7"}).status_code == 422
        assert c.get("/v1/patterns", headers=hdr("master", "*", "um"), params={"limit": 501}).status_code == 422
        assert c.post("/v1/patterns", headers=hdr("master", "*", "um")).status_code in (403, 405)


def test_upstream_down_is_502(monkeypatch):
    def boom(url):
        raise OSError("down")
    monkeypatch.setattr(patterns_routes, "_fetch", boom)
    with client() as c:
        assert c.get("/v1/patterns", headers=hdr("master", "*", "um")).status_code == 502
