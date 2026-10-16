import logging

import httpx
import pytest

from news_collector.httpclient import HostCoolingDown, PoliteClient
from news_collector.sources.base import Context
from news_collector.sources.gdelt import GdeltSource
from news_collector.symbols import load_rules

from conftest import CONFIG, NOW, fx

HOST = "api.gdeltproject.org"


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    async def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def mk(handler, clock):
    client = PoliteClient("ua", {HOST: 6.0}, transport=httpx.MockTransport(handler), sleep=clock.sleep,
                          clock=clock.now, strict_hosts={HOST})
    return Context(client=client, rules=load_rules(CONFIG / "symbol_map.yaml"), config_dir=CONFIG,
                   user_agent="ua", now=lambda: NOW)


async def test_requests_are_spaced_globally():
    clock, times = Clock(), []

    def handler(req):
        times.append(clock.t)
        return httpx.Response(200, content=fx("gdelt.json"))

    await GdeltSource().fetch(mk(handler, clock))
    assert len(times) == 4
    assert all(b - a >= 5.99 for a, b in zip(times, times[1:]))


async def test_429_stops_cycle_cooldown_and_rotates(caplog):
    clock, seen = Clock(), []
    mode = {"429": True}

    def handler(req):
        seen.append(req.url.params["query"])
        if mode["429"] and len(seen) >= 2:
            return httpx.Response(429)
        return httpx.Response(200, content=fx("gdelt.json"))

    ctx, src = mk(handler, clock), GdeltSource()
    with caplog.at_level(logging.INFO, logger="news_collector.gdelt"):
        out = await src.fetch(ctx)
    assert len(seen) == 2 and out  # dung ngay sau 429, khong goi tiep
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) == 1  # 1 dong, khong spam
    assert ctx.client.cooldown_left(HOST) >= 60
    # dang cooldown -> vong sau khong gui request nao
    n = len(seen)
    assert await src.fetch(ctx) == [] and len(seen) == n
    # het cooldown -> tiep tuc tu truy van bi 429 (round-robin), khong bat dau lai tu dau
    clock.t += 200
    mode["429"] = False
    await src.fetch(ctx)
    assert seen[n] == seen[1]
    assert len(seen) - n == 4
    assert ctx.client.cooldown_left(HOST) == 0


async def test_cooldown_grows_and_respects_retry_after():
    clock = Clock()
    ctx = mk(lambda r: httpx.Response(429, headers={"Retry-After": "300"}), clock)
    with pytest.raises(HostCoolingDown) as e1:
        await ctx.client.get("https://api.gdeltproject.org/api/v2/doc/doc")
    assert e1.value.retry_in >= 300
    clock.t += 1000
    with pytest.raises(HostCoolingDown) as e2:
        await ctx.client.get("https://api.gdeltproject.org/api/v2/doc/doc")
    assert e2.value.retry_in >= 120  # streak 2 -> base*2
    with pytest.raises(HostCoolingDown):  # dang cooldown -> khong goi mang
        await ctx.client.get("https://api.gdeltproject.org/api/v2/doc/doc")


async def test_text_rate_limit_body_triggers_cooldown():
    clock = Clock()
    ctx = mk(lambda r: httpx.Response(200, content=b"Please limit requests to one every 5 seconds"), clock)
    assert await GdeltSource().fetch(ctx) == []
    assert ctx.client.cooldown_left(HOST) > 0


async def test_other_errors_logged_once_per_cycle(caplog):
    clock = Clock()
    ctx = mk(lambda r: httpx.Response(404), clock)
    with caplog.at_level(logging.WARNING, logger="news_collector.gdelt"):
        assert await GdeltSource().fetch(ctx) == []
    assert len([r for r in caplog.records if r.name == "news_collector.gdelt"]) == 1
