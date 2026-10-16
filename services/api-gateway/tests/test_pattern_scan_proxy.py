"""/v1/patterns/{live,setup,media,trades,stats,examples}: proxy GET tới pattern-scan; client bị ép audience=client, ảnh chỉ PNG thật."""
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from api_gateway import pattern_scan_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

KEY = {"X-API-Key": "tok1"}
SECRET = "trust-secret-xyz"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def hdr(role, uid="u1"):
    return {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET),
                                 repo=InMemoryRepo(), redis=object()))


def fake(seen, png_ok=True):
    def f(url):
        seen.append(url)
        path = urlparse(url).path
        if path.endswith(".png"):
            return (200, PNG, "image/png") if png_ok else (200, b"<html>", "text/html")
        if path == "/scan/setup" and parse_qs(urlparse(url).query).get("setup_id") == ["KB-9:x"]:
            return 404, json.dumps({"detail": "không tìm thấy"}).encode(), "application/json"
        return 200, json.dumps({"items": [], "path": path}).encode(), "application/json"
    return f


def q(url):
    return parse_qs(urlparse(url).query)


def test_client_forced_audience(monkeypatch):
    seen = []
    monkeypatch.setattr(pattern_scan_routes, "_fetch", fake(seen))
    c = client()
    assert c.get("/v1/patterns/live?view=all&audience=master", headers=hdr("client")).status_code == 200
    assert q(seen[-1])["audience"] == ["client"]
    assert c.get("/v1/patterns/live", headers=hdr("master")).status_code == 200
    assert q(seen[-1])["audience"] == ["master"]
    r = c.get("/v1/patterns/setup?setup_id=KB-2:20261001T0000&symbol=XAUUSD&tf=M15", headers=hdr("client"))
    assert r.status_code == 200 and q(seen[-1])["audience"] == ["client"]
    assert c.get("/v1/patterns/setup?setup_id=KB-9:x&symbol=XAUUSD&tf=M15", headers=hdr("client")).status_code == 404


def test_media_png_only(monkeypatch):
    seen = []
    monkeypatch.setattr(pattern_scan_routes, "_fetch", fake(seen))
    c = client()
    r = c.get("/v1/patterns/media/12.png", headers=hdr("client"))
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG
    assert q(seen[-1])["audience"] == ["client"]
    assert c.get("/v1/patterns/examples/kb2-golden.png", headers=hdr("client")).status_code == 200
    assert c.get("/v1/patterns/media/abc.png", headers=hdr("client")).status_code in (403, 422)
    monkeypatch.setattr(pattern_scan_routes, "_fetch", fake(seen, png_ok=False))
    assert c.get("/v1/patterns/media/12.png", headers=hdr("master")).status_code == 404


def test_client_allowlist_paths(monkeypatch):
    seen = []
    monkeypatch.setattr(pattern_scan_routes, "_fetch", fake(seen))
    c = client()
    for p in ("/v1/patterns/trades", "/v1/patterns/stats", "/v1/patterns/examples", "/v1/patterns/live?view=history"):
        assert c.get(p, headers=hdr("client")).status_code == 200, p
    assert c.get("/v1/patterns/examples/..x.png", headers=hdr("client")).status_code in (403, 404)


def test_backend_down_502(monkeypatch):
    def boom(url):
        raise OSError("down")
    monkeypatch.setattr(pattern_scan_routes, "_fetch", boom)
    assert client().get("/v1/patterns/stats", headers=hdr("master")).status_code == 502


def test_backtest_master_only(monkeypatch):
    seen = []
    monkeypatch.setattr(pattern_scan_routes, "_fetch", fake(seen))
    c = client()
    paths = ["/v1/patterns/backtest/summary", "/v1/patterns/backtest/charts/a1_equity.png",
             "/v1/patterns/backtest/examples/KB-1_thang_D1_XAUUSD_M5.png", "/v1/patterns/backtest/download/ledger_summary.csv"]
    for p in paths:
        for role in ("client", "analyst", "support", "auditor"):
            n = len(seen)
            assert c.get(p, headers=hdr(role)).status_code == 403, (p, role)
            assert len(seen) == n                                           # không chạm pattern-scan
    assert c.get(paths[0], headers=hdr("master")).status_code == 200
    r = c.get(paths[1], headers=hdr("master"))
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    r = c.get(paths[3], headers=hdr("master"))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and q(seen[-1]) == {}
    assert urlparse(seen[-1]).path == "/scan/backtest/download/ledger_summary.csv"
    assert c.get("/v1/patterns/backtest/download/other.csv", headers=hdr("master")).status_code in (404, 502)
    assert c.get("/v1/patterns/backtest/charts/..%2Fx.png", headers=hdr("master")).status_code in (404, 422)
    assert c.get("/v1/patterns/backtest/summary").status_code in (401, 403)  # thiếu API key
