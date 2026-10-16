"""UX-S2-1 / UX-C2: 200 rỗng thay vì 404 (backtest summary, risk/journal tài khoản chưa có dữ liệu EA); tài khoản của người khác vẫn bị chặn."""
import json

from fastapi.testclient import TestClient

from api_gateway import journal_routes, pattern_scan_routes, riskmon_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

SECRET = "trust-secret-xyz"


def hdr(role, accs=""):
    return {"X-API-Key": "tok1", "X-User-Id": "u1", "X-Role": role, "X-Auth-Secret": SECRET, "X-Accounts": accs}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET), repo=InMemoryRepo(), redis=object()))


def test_backtest_summary_404_becomes_empty(monkeypatch):
    monkeypatch.setattr(pattern_scan_routes, "_fetch", lambda url: (404, b'{"detail":"x"}', "application/json"))
    r = client().get("/v1/patterns/backtest/summary", headers=hdr("master"))
    assert r.status_code == 200 and r.json()["available"] is False
    assert client().get("/v1/patterns/backtest/summary", headers=hdr("client")).status_code == 403


def test_risk_and_journal_empty_for_own_account_only(monkeypatch):
    monkeypatch.setattr(riskmon_routes, "_fetch", lambda url: (404, b'{"detail":"none"}'))
    monkeypatch.setattr(journal_routes, "_call", lambda m, u, b: (404, b'{"detail":"none"}'))
    c = client()
    for p in ("/v1/risk/accounts/mt5:777", "/v1/journal/mt5:777/summary"):
        r = c.get(p, headers=hdr("client", "mt5:777"))
        assert r.status_code == 200 and r.json().get("account_id") == "mt5:777", p
        assert c.get(p, headers=hdr("client", "mt5:888")).status_code in (403, 404), p   # không phải của người gọi
        assert c.get(p, headers=hdr("client", "mt5:888")).json().get("account_id") is None
