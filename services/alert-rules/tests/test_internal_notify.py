"""POST /internal/notify (risk-monitor -> push chung cho khách opt-in): xác thực Bearer, UUID, thiếu token -> 503, nội dung push không lộ số liệu."""
import json

from test_owner_push import mk, sc, sub_body

UID = "11111111-1111-4111-8111-111111111111"
TOK = "tok-test-123"
H = {"Authorization": f"Bearer {TOK}"}


def test_notify_requires_token_config(monkeypatch):
    monkeypatch.delenv("FLEET_INTERNAL_TOKEN", raising=False)
    c, *_ = mk()
    with c:
        assert c.post("/internal/notify", json={"owner": UID, "kind": "rule"}, headers=H).status_code == 503


def test_notify_auth_and_validation(monkeypatch):
    monkeypatch.setenv("FLEET_INTERNAL_TOKEN", TOK)
    c, *_ = mk()
    with c:
        assert c.post("/internal/notify", json={"owner": UID}).status_code == 401
        assert c.post("/internal/notify", json={"owner": UID}, headers={"Authorization": "Bearer sai"}).status_code == 401
        assert c.post("/internal/notify", json={"owner": "khong-phai-uuid"}, headers=H).status_code == 422
        assert c.post("/internal/notify", json={"owner": UID, "kind": "khac"}, headers=H).status_code == 422
        assert c.post("/internal/notify", json={"owner": UID, "x": 1}, headers=H).status_code == 422
        assert c.post("/internal/notify", json={"owner": UID}, headers=H).json() == {"sent": 0}      # chưa có thiết bị


def test_notify_sends_generic_push(monkeypatch):
    monkeypatch.setenv("FLEET_INTERNAL_TOKEN", TOK)
    c, _store, sender, _push = mk()
    with c:
        assert c.post("/push/subscribe", json=sub_body(), headers=sc(UID, "mt5:1")).status_code == 201
        r = c.post("/internal/notify", json={"owner": UID, "kind": "rule"}, headers=H)
        assert r.status_code == 200 and r.json() == {"sent": 1}
        data = json.loads(sender.calls[0][1])
        assert set(data) == {"title", "body", "url"} and not any(ch.isdigit() for ch in data["title"] + data["body"])
