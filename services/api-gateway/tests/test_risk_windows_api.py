from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.calendar_view import hide_superseded
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
H = {"X-API-Key": "tok1"}


def ev(i, title, minutes, country="USD", impact="high", source="faireconomy", **kw):
    return {"event_id": str(i), "source": source, "country": country, "title": title, "impact": impact,
            "ts": NOW + timedelta(minutes=minutes), "forecast": None, "previous": None, "actual": None, **kw}


def client(events):
    repo = InMemoryRepo(calendar_events=events, quotes=[{"symbol": "EURUSD", "ts": NOW, "bid": 1.1, "ask": 1.2, "source": "t"}])
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=repo, redis=object())
    return TestClient(app)


def test_symbol_state_active_and_minutes_left():
    with client([ev(1, "CPI m/m", 5), ev(2, "Unemployment Rate", 600, country="AUD")]) as c:
        r = c.get("/v1/risk-windows", params={"symbol": "EURUSD"}, headers=H).json()
        assert r["state"] == "active" and r["in_window"] and 33 <= r["minutes_to_end"] <= 36  # T+30 - (-5) = 35
        assert [e["title"] for e in r["current"]] == ["CPI m/m"]
        aud = c.get("/v1/risk-windows", params={"symbol": "AUDJPY"}, headers=H).json()
        assert aud["state"] == "clear" and aud["next_window"] and aud["upcoming"][0]["title"] == "Unemployment Rate"
        eg = c.get("/v1/risk-windows", params={"symbol": "EURGBP"}, headers=H).json()
        assert eg["state"] == "clear" and eg["current"] == [] and eg["upcoming"] == []


def test_imminent_and_all_symbols_and_status():
    with client([ev(1, "FOMC Rate Decision", 25, country="US", source="fed")]) as c:
        one = c.get("/v1/risk-windows", params={"symbol": "XAUUSD"}, headers=H).json()
        assert one["state"] == "imminent" and 9 <= one["minutes_to_start"] <= 10
        allr = c.get("/v1/risk-windows", headers=H).json()
        by = {s["symbol"]: s for s in allr["symbols"]}
        assert by["EURUSD"]["state"] == "imminent" and by["EURGBP"]["state"] == "clear" and "XAUUSD" in by
        st = c.get("/v1/risk-windows/status", headers=H).json()
        assert not st["any_active"] and "EURUSD" in st["imminent_symbols"] and st["next_window"]["title"] == "FOMC Rate Decision"
        assert st["config"]["default"]["after_min"] == 30 and st["config"]["overrides"][0]["after_min"] == 45


def test_auth_and_validation():
    with client([]) as c:
        assert c.get("/v1/risk-windows").status_code == 401
        assert c.get("/v1/risk-windows", params={"symbol": "bad symbol!"}, headers=H).status_code == 422
        assert c.get("/v1/risk-windows/status", headers=H).json()["any_active"] is False


def test_calendar_hides_official_row_when_ff_same_group_and_returns_extra():
    g = {"group": "us_cpi", "surprise": {"verdict": "good", "value": 0.1, "z": 1.0}}
    rows = [ev(1, "Consumer Price Index", 60, country="US", source="bls", extra={"group": "us_cpi"}),
            ev(2, "CPI m/m", 60, source="faireconomy", forecast="0.3%", actual="0.4%", extra=g),
            ev(3, "Real Earnings", 60, country="US", impact="med", source="bls")]
    out = hide_superseded([{**r, "ts": r["ts"]} for r in rows])
    assert [r["event_id"] for r in out] == ["2", "3"]
    with client(rows) as c:
        items = c.get("/v1/calendar", headers=H).json()["items"]
        assert {i["event_id"] for i in items} == {"2", "3"}
        assert next(i for i in items if i["event_id"] == "2")["extra"]["surprise"]["verdict"] == "good"
