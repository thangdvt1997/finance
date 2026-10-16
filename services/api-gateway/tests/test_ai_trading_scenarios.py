"""/v1/ai-trading/scenarios*: nạp kịch bản + job nền = CHỈ master (Origin + CSRF), giới hạn kích thước, whitelist trường, regex id/tên ảnh."""
import json
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from api_gateway import ai_trading_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

KEY = {"X-API-Key": "tok1"}
SECRET = "trust-secret-xyz"
JH = {"Content-Type": "application/json"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def hdr(role, uid="u1"):
    return {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET),
                                 repo=InMemoryRepo(), redis=object()))


def fake(seen, status=None, ctype="application/json", body=None):
    def f(method, url, b=None):
        seen.append((method, url, b))
        path = urlparse(url).path
        if "/images/" in path:
            return 200, body if body is not None else PNG, ctype if ctype != "application/json" else "image/png"
        if status:
            return status, json.dumps({"detail": "x"}).encode(), "application/json"
        if method == "POST":
            return (201 if path == "/ai/scenarios" else 202), json.dumps({"id": "SC-A1", "status": "queued"}).encode(), "application/json"
        return 200, json.dumps({"path": path}).encode(), "application/json"
    return f


def csrf(c):
    return {**hdr("master"), **JH, "X-CSRF-Token": c.get("/v1/user/csrf", headers=hdr("master")).json()["token"]}


def test_only_master_writes(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    for role in ("client", "analyst"):
        h = {**hdr(role), **JH}
        assert c.post("/v1/ai-trading/scenarios", content=b'{"yaml":"x"}', headers=h).status_code == 403
        assert c.post("/v1/ai-trading/scenarios/SC-A1/jobs", content=b'{"type":"backtest"}', headers=h).status_code == 403
        assert c.get("/v1/ai-trading/scenarios/SC-A1/jobs", headers=hdr(role)).status_code == 403
        assert c.get("/v1/ai-trading/scenarios/SC-A1/images/a.png", headers=hdr(role)).status_code == 403
    assert c.post("/v1/ai-trading/scenarios", content=b"{}", headers=JH).status_code in (401, 403)       # ẩn danh
    assert not seen


def test_csrf_origin_and_limits(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    m = {**hdr("master"), **JH}
    assert c.post("/v1/ai-trading/scenarios", content=b'{"yaml":"x"}', headers=m).status_code == 403      # thiếu CSRF
    h = csrf(c)
    assert c.post("/v1/ai-trading/scenarios", content=b'{"yaml":"x"}', headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/v1/ai-trading/scenarios", content=b'{"yaml":"x"}', headers={**h, "Content-Type": "text/plain"}).status_code == 415
    assert c.post("/v1/ai-trading/scenarios", content=b"[1]", headers=h).status_code == 400
    assert c.post("/v1/ai-trading/scenarios", content=b'{"yaml":"' + b"a" * (6 * 1024 * 1024 + 10) + b'"}', headers=h).status_code == 413
    assert not seen
    r = c.post("/v1/ai-trading/scenarios", content=json.dumps({"yaml": "id: x", "images": {"a.png": "QQ=="}, "evil": 1, "role": "master"}), headers=h)
    assert r.status_code == 201
    assert set(json.loads(seen[-1][2])) == {"yaml", "images"}                                              # chỉ trường whitelist


def test_job_routes(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    h = csrf(c)
    r = c.post("/v1/ai-trading/scenarios/SC-A1/jobs", content=json.dumps({"type": "final_test", "confirm": "SC-A1", "x": 1}), headers=h)
    assert r.status_code == 202 and json.loads(seen[-1][2]) == {"type": "final_test", "confirm": "SC-A1"}
    for bad in ("..%2Fx", "a", "SC A1", "9bad", "A" * 40):
        assert c.post(f"/v1/ai-trading/scenarios/{bad}/jobs", content=b'{"type":"backtest"}', headers=h).status_code in (404, 422), bad
    # 409/429 từ upstream giữ nguyên
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen, status=409))
    assert c.post("/v1/ai-trading/scenarios/SC-A1/jobs", content=b'{"type":"final_test","confirm":"SC-A1"}', headers=h).status_code == 409
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen, status=429))
    assert c.post("/v1/ai-trading/scenarios/SC-A1/jobs", content=b'{"type":"backtest"}', headers=h).status_code == 429


def test_images(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    m = hdr("master")
    r = c.get("/v1/ai-trading/scenarios/SC-A1/images/mau-1.png", headers=m)
    assert r.status_code == 200 and r.content == PNG and r.headers["x-content-type-options"] == "nosniff" and "sandbox" in r.headers["content-security-policy"]
    for bad in ("x.svg", "x.html", "..%2F..%2Fetc%2Fpasswd", "a%2Fb.png", ".hidden.png"):
        assert c.get(f"/v1/ai-trading/scenarios/SC-A1/images/{bad}", headers=m).status_code in (404, 422), bad
    # upstream trả nội dung không phải ảnh -> 404 (không chuyển tiếp HTML/SVG)
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen, body=b"<svg onload=alert(1)>", ctype="image/png"))
    assert c.get("/v1/ai-trading/scenarios/SC-A1/images/a.png", headers=m).status_code == 404


def test_ledger_dev_source(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    assert c.get("/v1/ai-trading/ledger.csv?strategy=SC-A1&source=backtest_dev", headers=hdr("master")).status_code in (200, 502)
    assert c.get("/v1/ai-trading/ledger.csv?strategy=SC-A1&source=backtest_dev", headers=hdr("client")).status_code == 403
    assert c.get("/v1/ai-trading/ledger.csv?strategy=SC-A1&source=x", headers=hdr("master")).status_code == 422
