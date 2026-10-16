import httpx
import pytest

from news_collector.httpclient import PoliteClient
from news_collector.symbols import build_rules, fold, tag_symbols

from conftest import CONFIG
from news_collector.symbols import load_rules

RULES = load_rules(CONFIG / "symbol_map.yaml")


def test_fold_vietnamese():
    assert fold("Giá VÀNG Đà Nẵng") == "gia vang da nang"


def test_tag_basic_and_defaults():
    syms = tag_symbols("ECB holds rates, euro firms", RULES, ["USDJPY"])
    assert syms == ["USDJPY", "EURUSD"]


def test_tag_fed_expands_group():
    syms = tag_symbols("Powell signals pause", RULES)
    assert {"EURUSD", "XAUUSD", "USDJPY", "GBPUSD"} <= set(syms)


def test_tag_vietnamese_accent_insensitive_and_case_sensitive_tickers():
    syms = tag_symbols("Giá vàng tăng, VN-Index giảm; VNM đi ngang", RULES)
    assert "XAUUSD" in syms and "VN:VNINDEX" in syms and "VN:VNM" in syms
    assert "VN:VNM" not in tag_symbols("vnm is lowercase", RULES)


def test_word_boundary_no_false_positive():
    assert "XAUUSD" not in tag_symbols("Goldman Sachs reports earnings", RULES)


def test_no_duplicates_and_empty():
    assert tag_symbols("", RULES) == []
    r = build_rules({"rules": [{"keywords": ["a"], "symbols": ["X"]}, {"keywords": ["a"], "symbols": ["X"]}]})
    assert tag_symbols("a", r) == ["X"]


async def test_client_user_agent_and_etag_cache():
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=b"body", headers={"etag": '"v1"'})

    async def nosleep(_):
        pass

    c = PoliteClient("UA-test (contact: a@b.c)", default_interval=0, transport=httpx.MockTransport(handler), sleep=nosleep)
    b1, nm1 = await c.get("https://x.test/f")
    b2, nm2 = await c.get("https://x.test/f")
    assert (b1, nm1) == (b"body", False) and (b2, nm2) == (b"body", True)
    assert calls[0].headers["user-agent"] == "UA-test (contact: a@b.c)"
    await c.aclose()


async def test_client_rate_limit_waits_and_retries_429():
    sleeps, n = [], {"i": 0}
    t = {"now": 0.0}

    async def fake_sleep(s):
        sleeps.append(s)
        t["now"] += s

    def handler(req):
        n["i"] += 1
        return httpx.Response(429, headers={"Retry-After": "3"}) if n["i"] == 1 else httpx.Response(200, content=b"ok")

    c = PoliteClient("ua", {"h.test": 5.0}, transport=httpx.MockTransport(handler), sleep=fake_sleep, clock=lambda: t["now"])
    body, _ = await c.get("https://h.test/a")
    assert body == b"ok" and 3 in sleeps
    await c.get("https://h.test/b")
    assert any(s >= 4.9 for s in sleeps)  # khoang cach toi thieu theo host
    await c.aclose()


async def test_client_raises_after_retries():
    async def nosleep(_):
        pass
    c = PoliteClient("ua", default_interval=0, transport=httpx.MockTransport(lambda r: httpx.Response(500)), sleep=nosleep)
    with pytest.raises(httpx.HTTPStatusError):
        await c.get("https://h.test/a")
    await c.aclose()
