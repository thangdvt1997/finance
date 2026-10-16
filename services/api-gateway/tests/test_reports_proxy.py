import json

from fastapi.testclient import TestClient

from api_gateway import reports_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def client():
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=InMemoryRepo(), redis=object())
    return TestClient(app)


def test_reports_list_and_auth(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        return 200, json.dumps({"read_only": True, "items": [{"kind": "daily", "period": "2026-10-12"}]}).encode()
    monkeypatch.setattr(reports_routes, "_fetch", fake)
    with client() as c:
        assert c.get("/v1/reports").status_code == 401
        r = c.get("/v1/reports", headers=H)
        assert r.status_code == 200 and r.json()["items"][0]["period"] == "2026-10-12"
        assert seen[-1].endswith("/reports")


def test_reports_file_media_types_and_disposition(monkeypatch):
    def fake(url):
        return 200, (b"%PDF-1.7 x" if url.endswith(".pdf") else "<html>Báo cáo</html>".encode())
    monkeypatch.setattr(reports_routes, "_fetch", fake)
    with client() as c:
        r = c.get("/v1/reports/daily/2026-10-12.pdf", headers=H)
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert "attachment" in r.headers["content-disposition"] and r.content.startswith(b"%PDF")
        assert r.headers["cache-control"] == "no-store"
        h = c.get("/v1/reports/weekly/2026-10-11.html", headers=H)
        assert h.status_code == 200 and h.headers["content-type"].startswith("text/html") and h.headers["content-disposition"] == "inline"


def test_reports_regex_blocks_traversal_and_non_get(monkeypatch):
    monkeypatch.setattr(reports_routes, "_fetch", lambda url: (_ for _ in ()).throw(AssertionError("không được gọi upstream")))
    with client() as c:
        for p in ["/v1/reports/daily/..%2f..%2fetc%2fpasswd", "/v1/reports/daily/2026-10-12.exe", "/v1/reports/monthly/2026-10-12.html",
                  "/v1/reports/daily/2026-10-12.html.bak", "/v1/reports/daily/26-10-12.pdf", "/v1/reports/generate"]:
            assert c.get(p, headers=H).status_code in (404, 422), p
        assert c.post("/v1/reports", headers=H).status_code in (404, 405)
        assert c.post("/v1/reports/daily/2026-10-12.pdf", headers=H).status_code in (404, 405)


def test_reports_upstream_down_and_missing(monkeypatch):
    def boom(url):
        raise ConnectionError("x")
    monkeypatch.setattr(reports_routes, "_fetch", boom)
    with client() as c:
        assert c.get("/v1/reports", headers=H).status_code == 502
        assert c.get("/v1/reports/daily/2026-10-12.pdf", headers=H).status_code == 502
    monkeypatch.setattr(reports_routes, "_fetch", lambda u: (404, b"{}"))
    with client() as c:
        assert c.get("/v1/reports/daily/2026-10-12.pdf", headers=H).status_code == 404
