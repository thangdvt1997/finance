"""Trang Dữ liệu (datakeeper_routes.py): chỉ master/service; client/vai trò phụ 403; whitelist đường dẫn; recheck cần CSRF; không rò tên nguồn."""
import json

from api_gateway import datakeeper_routes as dk
from test_authz import CLIENT_A, KEY, MASTER, hdr, make

SUP = hdr("support", "mt5:1", "us")


def setup(monkeypatch):
    c, _ = make(monkeypatch)
    calls = []

    def _call(method, url, body=None, extra=None):
        calls.append((method, url))
        return 200, json.dumps({"summary": {"total": 162}, "note": "ok", "detail": "nguồn dukascopy"}).encode()
    monkeypatch.setattr(dk, "_call", _call)
    return c, calls


def csrf(c, h):
    return {**h, "X-CSRF-Token": c.get("/v1/user/csrf", headers=h).json()["token"]}


def test_master_read_whitelist(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        r = c.get("/v1/data/health", headers=MASTER)
        assert r.status_code == 200 and "dukascopy" not in r.text.lower()
        assert calls[-1] == ("GET", "http://data-keeper:8000/v1/data/health")
        assert c.get("/v1/data/decisions?limit=20&x=1", headers=MASTER).status_code == 200 and calls[-1][1].endswith("/v1/data/decisions?limit=20")
        assert c.get("/v1/data/report/daily", headers=KEY).status_code == 200      # service
        for bad in ("/v1/data/recheck", "/v1/data/internal", "/v1/data/..%2Fx"):
            assert c.get(bad, headers=MASTER).status_code in (404, 405), bad


def test_client_and_staff_denied(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        for h in (CLIENT_A, SUP):
            assert c.get("/v1/data/health", headers=h).status_code == 403
            assert c.post("/v1/data/recheck", headers={**h, "X-CSRF-Token": "x"}).status_code == 403
        assert calls == []


def test_recheck_needs_csrf(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        assert c.post("/v1/data/recheck", headers=MASTER).status_code == 403
        assert calls == []
        assert c.post("/v1/data/recheck", headers=csrf(c, MASTER)).status_code == 200
        assert calls[-1] == ("POST", "http://data-keeper:8000/v1/data/recheck")
