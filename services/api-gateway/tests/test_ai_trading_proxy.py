"""/v1/ai-trading/*: master xem tất cả, client chỉ overview/strategies/arena (rút gọn), anon bị chặn, id lạ bị từ chối, POST jobs cần CSRF."""
import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from api_gateway import ai_trading_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

KEY = {"X-API-Key": "tok1"}
SECRET = "trust-secret-xyz"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JH = {"Content-Type": "application/json"}


def hdr(role, uid="u1"):
    return {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET),
                                 repo=InMemoryRepo(), redis=object()))


def fake(seen):
    def f(method, url, body=None):
        seen.append((method, url, body))
        path = urlparse(url).path
        if path.startswith("/ai/media/"):
            return 200, PNG, "image/png"
        if path == "/ai/ledger.csv":
            return 200, b"id,kb\n1,KB-1\n", "text/csv"
        if path == "/ai/strategies/nope":
            return 404, json.dumps({"detail": "không tìm thấy"}).encode(), "application/json"
        if method == "POST":
            return 202, json.dumps({"id": "a" * 32, "status": "queued"}).encode(), "application/json"
        return 200, json.dumps({"path": path}).encode(), "application/json"
    return f


def test_client_reduced_and_forced_audience(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    for p in ("overview", "strategies", "arena", "strategies/KB-1"):
        assert c.get(f"/v1/ai-trading/{p}", headers=hdr("client")).status_code == 200, p
    r = c.get("/v1/ai-trading/strategies/KB-1?audience=master", headers=hdr("client"))
    assert r.status_code == 200 and parse_qs(urlparse(seen[-1][1]).query)["audience"] == ["client"]
    c.get("/v1/ai-trading/overview", headers=hdr("master"))
    assert parse_qs(urlparse(seen[-1][1]).query)["audience"] == ["master"]


def test_client_denied_master_only(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    n = len(seen)
    for p in ("lab", "ledger.csv?strategy=KB-1", "media/charts/a1_equity_total.png", "jobs/" + "a" * 32, "strategies/KB-1/x"):
        assert c.get(f"/v1/ai-trading/{p}", headers=hdr("client")).status_code in (403, 404), p
        assert c.get(f"/v1/ai-trading/{p}", headers=hdr("analyst")).status_code in (403, 404), p
    assert c.post("/v1/ai-trading/jobs", json={"type": "backtest"}, headers=hdr("client")).status_code == 403
    assert len(seen) == n                                  # không chạm ai-trading


def test_anon_blocked(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    assert c.get("/v1/ai-trading/overview").status_code in (401, 403)
    assert c.get("/v1/ai-trading/overview", headers={**KEY, "X-Role": "master", "X-User-Id": "x"}).status_code == 403   # thiếu/giả auth secret
    assert not seen


def test_master_all(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    m = hdr("master")
    assert c.get("/v1/ai-trading/lab", headers=m).status_code == 200
    r = c.get("/v1/ai-trading/media/charts/a1_equity_total.png", headers=m)
    assert r.status_code == 200 and r.content == PNG
    r = c.get("/v1/ai-trading/ledger.csv?strategy=KB-1", headers=m)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert c.get("/v1/ai-trading/strategies/nope", headers=m).status_code == 404
    assert c.get("/v1/ai-trading/ledger.csv?strategy=../x", headers=m).status_code == 422
    assert c.get("/v1/ai-trading/media/charts/..%2Fsummary.json", headers=m).status_code in (404, 422)
    assert c.get("/v1/ai-trading/jobs/zzz", headers=m).status_code == 422
    assert c.get("/v1/ai-trading/jobs/" + "a" * 32, headers=m).status_code == 200


def test_jobs_post_csrf(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    m = {**hdr("master"), **JH}
    assert c.post("/v1/ai-trading/jobs", content=b'{"type":"backtest"}', headers=m).status_code == 403     # thiếu CSRF
    h = {**m, "X-CSRF-Token": c.get("/v1/user/csrf", headers=hdr("master")).json()["token"]}
    r = c.post("/v1/ai-trading/jobs", content=b'{"type":"backtest","strategy_id":"KB-1","evil":1}', headers=h)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert json.loads(seen[-1][2]) == {"type": "backtest", "strategy_id": "KB-1"}                           # chỉ trường whitelist
    assert c.post("/v1/ai-trading/jobs", content=b"[]", headers=h).status_code == 400
    # service (API key nội bộ) không cần CSRF
    assert c.post("/v1/ai-trading/jobs", content=b'{"type":"backtest"}', headers={**KEY, **JH}).status_code == 202


def test_backend_down_502(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(ai_trading_routes, "_call", boom)
    assert client().get("/v1/ai-trading/overview", headers=hdr("master")).status_code == 502


def test_c2_regime_consensus_client_reduced_analyst_master_only(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    for p in ("regime", "regime?symbol=EURUSD", "consensus", "consensus?symbol=XAUUSD"):
        assert c.get(f"/v1/ai-trading/{p}", headers=hdr("client")).status_code == 200, p
        assert parse_qs(urlparse(seen[-1][1]).query)["audience"] == ["client"]
    c.get("/v1/ai-trading/regime?audience=master", headers=hdr("client"))
    assert parse_qs(urlparse(seen[-1][1]).query)["audience"] == ["client"]
    c.get("/v1/ai-trading/regime", headers=hdr("master"))
    assert parse_qs(urlparse(seen[-1][1]).query)["audience"] == ["master"]
    n = len(seen)
    assert c.get("/v1/ai-trading/analyst?symbol=EURUSD", headers=hdr("client")).status_code == 403
    assert c.get("/v1/ai-trading/analyst?symbol=EURUSD").status_code in (401, 403)
    assert len(seen) == n                                                    # không chạm upstream
    r = c.get("/v1/ai-trading/analyst?symbol=EURUSD&wait=1", headers=hdr("master"))
    assert r.status_code == 200 and urlparse(seen[-1][1]).path == "/analyst" and parse_qs(urlparse(seen[-1][1]).query) == {"symbol": ["EURUSD"]}
    for bad in ("../x", "a b", "A" * 40, ""):
        assert c.get("/v1/ai-trading/analyst", params={"symbol": bad}, headers=hdr("master")).status_code == 422
    assert c.get("/v1/ai-trading/regime", params={"symbol": "x/../y"}, headers=hdr("master")).status_code == 422


def test_d1_guardrail_master_only_and_killswitch_csrf(monkeypatch):
    seen = []
    monkeypatch.setattr(ai_trading_routes, "_call", fake(seen))
    c = client()
    n = len(seen)
    for p in ("guardrail", "ledger/verify"):
        for role in ("client", "analyst"):
            assert c.get(f"/v1/ai-trading/{p}", headers=hdr(role)).status_code == 403, (p, role)
        assert c.get(f"/v1/ai-trading/{p}", headers=hdr("master")).status_code == 200
        assert c.get(f"/v1/ai-trading/{p}").status_code in (401, 403)                     # ẩn danh
    for role in ("client", "analyst"):
        assert c.post("/v1/ai-trading/guardrail/killswitch", json={"on": True}, headers=hdr(role)).status_code == 403
    assert len(seen) == n + 2                                                            # chỉ 2 GET của master chạm backend
    m = {**hdr("master"), **JH}
    assert c.post("/v1/ai-trading/guardrail/killswitch", content=b'{"on":true}', headers=m).status_code == 403          # thiếu CSRF
    bad = {**m, "X-CSRF-Token": "x" * 40}
    assert c.post("/v1/ai-trading/guardrail/killswitch", content=b'{"on":true}', headers=bad).status_code == 403
    h = {**m, "X-CSRF-Token": c.get("/v1/user/csrf", headers=hdr("master")).json()["token"]}
    assert c.post("/v1/ai-trading/guardrail/killswitch", content=b'{"on":true,"reason":"t","evil":1}', headers={**h, "Origin": "https://evil.example"}).status_code == 403
    r = c.post("/v1/ai-trading/guardrail/killswitch", content=b'{"on":true,"reason":"t","evil":1}', headers=h)
    assert r.status_code == 202 and json.loads(seen[-1][2]) == {"on": True, "reason": "t"}
