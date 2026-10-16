import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from scenario import T0, make_cfg  # noqa: E402

from mtbridge.accounts import BridgeConfig  # noqa: E402
from mtbridge.service import BridgeService, Settings, create_app  # noqa: E402


class FakePub:
    def __init__(self):
        self.events: list[tuple[str, object]] = []

    async def publish(self, stream, event):
        self.events.append((stream, event))

    def on(self, stream):
        return [e for s, e in self.events if s == stream]


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    for a in ("a4", "a5", "a5d", "h1"):
        monkeypatch.setenv(f"TOK_{a}", f"secret-token-{a}-xxxxxxxx")
    monkeypatch.setenv("HMAC_h1", "hmac-secret-h1")


@pytest.fixture
def env():
    cfgs = [make_cfg("a4", "mt4"), make_cfg("a5", "mt5"), make_cfg("h1", "mt4", hmac_secret_env="HMAC_h1")]
    clock = Clock(T0)
    pub = FakePub()
    svc = BridgeService(BridgeConfig(accounts=cfgs), pub, settings=Settings(admin_token="adm"), clock=clock)
    client = TestClient(create_app(svc))
    return svc, client, pub, clock
