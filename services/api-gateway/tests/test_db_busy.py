"""RS-2: loi DB tam thoi (statement_timeout...) -> 503 JSON + Retry-After, khong 500 tho."""
import asyncpg
from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

H = {"X-API-Key": "tok1"}


class Slow(InMemoryRepo):
    exc: Exception = asyncpg.QueryCanceledError("canceling statement due to statement timeout")

    async def bars(self, *a, **k):
        raise self.exc


def mk(exc):
    Slow.exc = exc
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=Slow(), redis=object())
    return TestClient(app, raise_server_exceptions=False)


def test_statement_timeout_is_503_json():
    with mk(asyncpg.QueryCanceledError("statement timeout")) as c:
        r = c.get("/v1/bars?symbol=EURUSD&tf=D1", headers=H)
        assert r.status_code == 503, r.text
        assert r.headers["retry-after"] == "3"
        assert r.json()["code"] == "db_busy"


def test_other_error_is_500():
    with mk(RuntimeError("boom")) as c:
        r = c.get("/v1/bars?symbol=EURUSD&tf=D1", headers=H)
        assert r.status_code == 500
