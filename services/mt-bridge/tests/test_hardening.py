"""S-6: nonce lưu Redis (SET NX EX) chống replay xuyên restart; MT_REQUIRE_HMAC fail-closed cho tài khoản agent không có HMAC."""
import fakeredis
from fastapi.testclient import TestClient
from scenario import T0, make_cfg, post, to_ea_batch

from mtbridge.accounts import BridgeConfig
from mtbridge.service import BridgeService, Settings, create_app

TOK = "secret-token-a4-xxxxxxxx"


class RedisPub:
    """Publisher giả có thuộc tính .r giống tscommon.Bus."""

    def __init__(self, r):
        self.r = r
        self.events = []

    async def publish(self, stream, event):
        self.events.append((stream, event))


def _client(r, settings=None):
    svc = BridgeService(BridgeConfig(accounts=[make_cfg("a4", "mt4")]), RedisPub(r),
                        settings=settings or Settings(admin_token="adm"), clock=lambda: T0)
    return TestClient(create_app(svc))


def test_nonce_survives_restart_via_redis():
    r = fakeredis.FakeAsyncRedis(decode_responses=True)
    b = to_ea_batch("a4", "mt4", nonce="nonce-restart-0001")
    assert post(_client(r), TOK, b).status_code == 200
    # "restart": service mới (cache RAM rỗng) nhưng cùng Redis -> vẫn chặn replay
    resp = post(_client(r), TOK, b)
    assert resp.status_code == 409 and resp.json()["error"] == "replay"


def test_require_hmac_rejects_account_without_hmac(monkeypatch):
    r = fakeredis.FakeAsyncRedis(decode_responses=True)
    c = _client(r, Settings(admin_token="adm", require_hmac=True))
    assert post(c, TOK, to_ea_batch("a4", "mt4")).status_code == 401
