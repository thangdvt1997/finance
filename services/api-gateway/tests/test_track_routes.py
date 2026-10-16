"""/v1/experts/{leaderboard,consensus,feed,methodology,chain/verify,{id}/track-record} -> track-record (upstream gia)."""
import json

import pytest
from fastapi.testclient import TestClient

from api_gateway import track_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

SECRET = "s3cret-trust"
KEY = {"X-API-Key": "tok1"}
BANNED = ("dukascopy", "yahoo", "frankfurter", "faireconomy", "vietstock", "reuters", "actionforex", "cafef")


def hdr(role, accounts="", uid="u1"):
    return {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET, "X-Accounts": accounts}


def mk():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET, hide_sources=True),
                                 repo=InMemoryRepo(), redis=object()))


@pytest.fixture
def seen(monkeypatch):
    calls = []

    def fake(method, url, body, extra=None):
        calls.append((method, url, body, extra))
        return 200, json.dumps({"method_version": "1", "rows": [{"entity_id": "e1", "label": "Luồng tin #1", "score": 61, "source": "dukascopy",
                                                                 "note": "theo dukascopy và reuters"}]}).encode()
    monkeypatch.setattr(track_routes, "_call", fake)
    return calls


PUBLIC = ["/v1/experts/leaderboard", "/v1/experts/consensus", "/v1/experts/feed", "/v1/experts/methodology", "/v1/experts/e1/track-record"]


def test_auth_required(seen):
    with mk() as c:
        for p in PUBLIC + ["/v1/experts/chain/verify"]:
            assert c.get(p).status_code == 401, p
        assert not seen


@pytest.mark.parametrize("role", ["client", "master"])
def test_public_routes_ok_for_client_and_master(seen, role):
    with mk() as c:
        for p in PUBLIC:
            r = c.get(p, headers=hdr(role, "a1"))
            assert r.status_code == 200, (p, r.text)
    assert seen[0][1] == "http://track-record:8000/track/leaderboard"
    assert seen[-1][1] == "http://track-record:8000/track/experts/e1/track-record"


def test_service_key_ok_and_chain_verify_master_only(seen):
    with mk() as c:
        assert c.get("/v1/experts/chain/verify", headers=KEY).status_code == 200                      # service
        assert c.get("/v1/experts/chain/verify", headers=hdr("master")).status_code == 200
        n = len(seen)
        assert c.get("/v1/experts/chain/verify", headers=hdr("client", "a1")).status_code == 403
        assert c.get("/v1/experts/chain/verify", headers=hdr("support", "a1")).status_code == 403
        assert len(seen) == n


def test_staff_roles(seen):
    with mk() as c:
        assert c.get("/v1/experts/leaderboard", headers=hdr("analyst")).status_code == 200
        assert c.get("/v1/experts/leaderboard", headers=hdr("auditor")).status_code == 403
        assert c.get("/v1/experts/leaderboard", headers={**KEY, "X-Role": "client"}).status_code == 403    # thieu secret


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_only_get(seen, method):
    with mk() as c:
        for role in ("client", "master"):
            for p in PUBLIC + ["/v1/experts/chain/verify"]:
                r = c.request(method, p, json={}, headers=hdr(role, "a1"))
                assert r.status_code in (403, 405), (role, method, p, r.status_code)
        assert not seen


def test_bad_entity_and_traversal(seen):
    with mk() as c:
        h = hdr("client", "a1")
        for bad in ("/v1/experts/..%2F..%2Fjournal/track-record", "/v1/experts/a%2Fb/track-record", "/v1/experts/a b/track-record",
                    "/v1/experts/" + "a" * 97 + "/track-record", "/v1/experts/%3Cscript%3E/track-record", "/v1/experts/a;b/track-record",
                    "/v1/experts/e1/track-record/x", "/v1/experts/e1/secret"):
            assert c.get(bad, headers=h).status_code in (403, 404, 422), bad
        assert c.get("/v1/experts/../track-record", headers=hdr("master")).status_code in (404, 422)
        assert c.get("/v1/experts/....../track-record", headers=hdr("master")).status_code == 422
        assert not seen


def test_query_validation(seen):
    with mk() as c:
        h = hdr("client", "a1")
        for bad in ("horizon=2D", "scope=evil", "limit=500", "limit=0", "limit=abc", "scope=sym:EUR;USD", "min_n=-1", "kind=x", "horizon=1D&horizon=1W"):
            assert c.get(f"/v1/experts/leaderboard?{bad}", headers=h).status_code == 422, bad
        assert c.get("/v1/experts/consensus?window_days=91", headers=h).status_code == 422
        assert c.get("/v1/experts/consensus?window_days=90&scope=forex&min_experts=3", headers=h).status_code == 200
        for bad in ("before=notadate", "limit=201", "direction=up", "symbol=a/b", "entity_id=../x"):
            assert c.get(f"/v1/experts/feed?{bad}", headers=h).status_code == 422, bad
        assert c.get("/v1/experts/feed?limit=200&symbol=EURUSD&direction=bullish&before=2026-10-01T00:00:00Z", headers=h).status_code == 200
        assert c.get("/v1/experts/e1/track-record?horizon=1M&scope=sym:EURUSD", headers=h).status_code == 200
        assert c.get("/v1/experts/e1/track-record?horizon=1Y", headers=h).status_code == 422


def test_no_idor_account_params_and_headers_not_forwarded(seen):
    with mk() as c:
        h = {**hdr("client", "a1", uid="victim-attacker"), "X-Owner-User": "x", "X-Forwarded-For": "1.2.3.4", "Authorization": "Bearer z"}
        r = c.get("/v1/experts/leaderboard?account_id=other-acc&user_id=u9&horizon=1D&token=abc", headers=h)
        assert r.status_code == 200
        m, url, body, extra = seen[-1]
        assert m == "GET" and body is None and not extra
        assert url == "http://track-record:8000/track/leaderboard?horizon=1D"
        assert "other-acc" not in url and "account" not in url and "u9" not in url
        for p in ("/v1/experts/consensus", "/v1/experts/feed", "/v1/experts/e1/track-record"):
            c.get(p + "?account_id=zzz&accounts=a2&X-Accounts=a2", headers=h)
            assert "zzz" not in seen[-1][1] and "a2" not in seen[-1][1]
        # client khong doc duoc bat ky route tai khoan nao nho route nay
        assert c.get("/v1/accounts/other-acc/orders", headers=hdr("client", "a1")).status_code == 403


def test_upstream_down_clean_502(monkeypatch):
    def boom(*a, **k):
        raise ConnectionRefusedError("track-record:8000 secret-host")
    monkeypatch.setattr(track_routes, "_call", boom)
    with mk() as c:
        for p in PUBLIC:
            r = c.get(p, headers=hdr("client", "a1"))
            assert r.status_code == 503 and r.headers.get("retry-after") == "15", p
            assert "Traceback" not in r.text and "secret-host" not in r.text
            assert r.json()["detail"].startswith("track-record không khả dụng")


def test_upstream_5xx_and_garbage(monkeypatch):
    monkeypatch.setattr(track_routes, "_call", lambda *a, **k: (500, b"Traceback: boom"))
    with mk() as c:
        r = c.get("/v1/experts/leaderboard", headers=KEY)
        assert r.status_code == 503 and "Traceback" not in r.text
    monkeypatch.setattr(track_routes, "_call", lambda *a, **k: (200, b"<html>"))
    with mk() as c:
        assert c.get("/v1/experts/leaderboard", headers=KEY).status_code == 503
    monkeypatch.setattr(track_routes, "_call", lambda *a, **k: (404, b'{"detail":"entity not found"}'))
    with mk() as c:
        assert c.get("/v1/experts/e9/track-record", headers=KEY).status_code == 404


def test_hide_sources_scrubs_but_keeps_expert_label(seen):
    with mk() as c:
        for p in PUBLIC:
            r = c.get(p, headers=hdr("client", "a1"))
            low = r.text.lower()
            assert not any(b in low for b in BANNED), (p, r.text)
        row = c.get("/v1/experts/leaderboard", headers=hdr("client", "a1")).json()["rows"][0]
        assert row["label"] == "Luồng tin #1" and row["entity_id"] == "e1" and row["score"] == 61 and "source" not in row


def test_existing_experts_list_still_works():
    with mk() as c:
        assert c.get("/v1/experts", headers=hdr("client", "a1")).status_code == 200
