from datetime import datetime, timezone
from pathlib import Path

import fakeredis
import httpx
import pytest
from tscommon.bus import Bus

from news_collector.httpclient import PoliteClient
from news_collector.sources.base import Context
from news_collector.symbols import load_rules

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


@pytest.fixture
def make_ctx():
    clients = []

    def _make(handler, user_agent="test/1.0 (contact: t@example.com)", now=NOW):
        async def nosleep(_):
            return None
        client = PoliteClient(user_agent, default_interval=0, transport=httpx.MockTransport(handler), sleep=nosleep)
        clients.append(client)
        return Context(client=client, rules=load_rules(CONFIG / "symbol_map.yaml"), config_dir=CONFIG,
                       user_agent=user_agent, now=lambda: now)
    yield _make


@pytest.fixture
async def bus():
    r = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()
