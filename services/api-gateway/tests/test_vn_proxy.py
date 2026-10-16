import json

from fastapi.testclient import TestClient

from api_gateway import vn_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object()))


def test_vn_proxy_get_only_whitelist_and_query(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        return 200, json.dumps({"as_of": "2026-10-09", "rows": []}).encode()
    monkeypatch.setattr(vn_routes, "_fetch", fake)
    with client() as c:
        assert c.get("/v1/vn/overview").status_code == 401                       # cần API key
        assert c.get("/v1/vn/overview", headers=H).json()["as_of"] == "2026-10-09"
        assert seen[-1] == "http://vn-market:8000/vn/overview"
        assert c.get("/v1/vn/movers?by=gainers&universe=vn30&n=10", headers=H).status_code == 200
        assert "by=gainers" in seen[-1] and "universe=vn30" in seen[-1]
        assert c.get("/v1/vn/screener?industry=Ngân hàng&pe_max=15", headers=H).status_code == 200
        assert "pe_max=15" in seen[-1]
        assert c.get("/v1/vn/symbol/VCB", headers=H).status_code == 200 and seen[-1].endswith("/vn/symbol/VCB")
        assert c.get("/v1/vn/index/VNINDEX", headers=H).status_code == 200
        n = len(seen)
        for bad in ("admin", "healthz", "metrics", "symbol/VCB/../x", "symbol/", "index/VN INDEX", "..%2Fmetrics"):
            assert c.get(f"/v1/vn/{bad}", headers=H).status_code in (404, 422), bad
        assert len(seen) == n                                                      # không có yêu cầu nào lọt xuống service
        assert c.get("/v1/vn/overview?bad key=1&x=" + "a" * 100, headers=H).status_code == 200
        assert "bad" not in seen[-1] and "x=" not in seen[-1]                     # khoá/giá trị không hợp lệ bị loại
        for m in ("post", "put", "delete", "patch"):
            assert getattr(c, m)("/v1/vn/overview", headers=H).status_code in (403, 405)


def test_vn_proxy_upstream_errors(monkeypatch):
    def boom(url):
        raise OSError("down")
    monkeypatch.setattr(vn_routes, "_fetch", boom)
    with client() as c:
        assert c.get("/v1/vn/overview", headers=H).status_code == 502
    monkeypatch.setattr(vn_routes, "_fetch", lambda u: (200, b"<html>"))
    with client() as c:
        assert c.get("/v1/vn/overview", headers=H).status_code == 502
