from fastapi.testclient import TestClient

from api_gateway import datasources_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


def test_data_sources_aggregates_and_isolates_errors(monkeypatch):
    def fake(url):
        if url.endswith("/providers") and "market" in url:
            return {"providers": [{"provider": "oanda", "state": "needs_key", "needs_env": ["OANDA_PRACTICE_TOKEN"]}]}
        if url.endswith("/reconcile"):
            return {"results": [{"pair": "EURUSD", "source": "oanda", "status": "ok"}], "summary": {"ok": 1}}
        raise OSError("news down")
    monkeypatch.setattr(datasources_routes, "_get", fake)
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, hide_sources=False), repo=InMemoryRepo(), redis=object())
    with TestClient(app) as c:
        assert c.get("/v1/data-sources").status_code == 401
        d = c.get("/v1/data-sources", headers=H).json()
    assert d["market"][0]["state"] == "needs_key" and d["reconcile"]["summary"] == {"ok": 1}
    assert d["news"] == [] and d["news_error"] == "OSError"
