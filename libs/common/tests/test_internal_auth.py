"""X-Internal-Token: middleware (off/log/enforce, miễn health/metrics, token cũ khi xoay) + handler urllib (chỉ host allowlist)."""
from __future__ import annotations

import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tscommon.internal_auth import HEADER, InternalTokenHandler, check_token, install_internal_auth, internal_headers, load_tokens

TOK, OLD = "a" * 64, "b" * 64


def mk(mode, tokens):
    app = FastAPI()

    @app.get("/healthz")
    def h():
        return {"ok": 1}

    @app.get("/metrics")
    def m():
        return "m"

    @app.get("/journal/x")
    def j():
        return {"data": 1}

    install_internal_auth(app, "t", mode=mode, tokens=tokens)
    return TestClient(app)


def test_enforce_blocks_missing_and_wrong():
    c = mk("enforce", [TOK])
    assert c.get("/journal/x").status_code == 401
    assert c.get("/journal/x", headers={HEADER: "sai"}).status_code == 401
    assert c.get("/journal/x", headers={HEADER: TOK[:-1]}).status_code == 401
    assert c.get("/journal/x", headers={HEADER: TOK}).status_code == 200
    assert c.get("/journal/x", headers={HEADER.lower(): TOK}).status_code == 200


def test_enforce_exempts_health_and_metrics():
    c = mk("enforce", [TOK])
    assert c.get("/healthz").status_code == 200
    assert c.get("/metrics").status_code == 200
    # chỉ khớp chính xác đường, không tiền tố
    assert c.get("/healthz/../journal/x").status_code in (401, 404)


def test_log_mode_passes_through():
    c = mk("log", [TOK])
    assert c.get("/journal/x").status_code == 200
    assert c.get("/journal/x", headers={HEADER: "sai"}).status_code == 200


def test_off_mode():
    assert mk("off", []).get("/journal/x").status_code == 200


def test_enforce_without_token_fails_closed():
    c = mk("enforce", [])
    assert c.get("/journal/x").status_code == 503
    assert c.get("/journal/x", headers={HEADER: ""}).status_code == 503
    assert c.get("/healthz").status_code == 200


def test_rotation_accepts_prev(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", TOK)
    monkeypatch.setenv("INTERNAL_TOKEN_PREV", OLD)
    assert load_tokens() == [TOK, OLD]
    c = mk("enforce", None)
    assert c.get("/journal/x", headers={HEADER: OLD}).status_code == 200
    assert c.get("/journal/x", headers={HEADER: TOK}).status_code == 200
    assert internal_headers() == {HEADER: TOK}


def test_token_file(monkeypatch, tmp_path):
    p = tmp_path / "tok"
    p.write_text(TOK + "\n")
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    monkeypatch.delenv("INTERNAL_TOKEN_PREV", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN_FILE", str(p))
    assert load_tokens() == [TOK]


def test_check_token_edge():
    assert not check_token(None, [TOK])
    assert not check_token("", [TOK])
    assert not check_token(TOK, [])
    assert check_token(TOK.encode(), [OLD, TOK])


@pytest.mark.parametrize("url,expect", [("http://journal:8000/journal/accounts", True), ("http://alert-rules:8000/rules", True),
                                        ("http://evil.example:8000/x", False), ("http://prometheus:9090/api", False)])
def test_urllib_handler_allowlist(url, expect):
    h = InternalTokenHandler({"journal", "alert-rules"}, token=TOK)
    req = h.http_request(urllib.request.Request(url))
    assert (req.get_header(HEADER.capitalize()) == TOK) is expect
    # unredirected: không theo redirect sang host khác
    assert HEADER.capitalize() not in req.headers


def test_urllib_handler_no_token():
    h = InternalTokenHandler({"journal"}, token="")
    req = h.http_request(urllib.request.Request("http://journal:8000/x"))
    assert req.get_header(HEADER.capitalize()) is None
