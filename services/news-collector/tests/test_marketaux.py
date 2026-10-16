"""Marketaux Free: parse entity/sentiment, tiet kiem hang muc, khong ro ri token, trang thai 'can key'."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from news_collector.app import build_sources, create_app
from news_collector.settings import NewsSettings
from news_collector.sources.marketaux import MarketauxSource, parse_articles

BODY = {"meta": {"found": 2, "returned": 2, "limit": 3, "page": 1}, "data": [
    {"uuid": "a1", "title": "Apple beats expectations as dollar slips", "description": "AAPL rallied; EUR/USD firmer.",
     "url": "https://ex.com/a1", "language": "en", "published_at": "2026-10-11T11:30:00.000000Z", "source": "ex.com",
     "entities": [{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "type": "equity", "sentiment_score": 0.6},
                  {"symbol": "XYZ", "name": "Other", "exchange": "LSE", "type": "equity", "sentiment_score": 0.2}]},
    {"uuid": "a2", "title": "Fed holds rates", "description": None, "snippet": "The Federal Reserve held.", "url": "https://ex.com/a2",
     "language": "en", "published_at": "2026-10-11T11:45:00.000000Z", "source": "ex2.com", "entities": []},
]}


def test_parse_entities_and_sentiment(make_ctx):
    ctx = make_ctx(lambda r: httpx.Response(200))
    emits, newest = parse_articles(json.dumps(BODY).encode(), ctx, "q")
    a1, a2 = emits[0].payload, emits[1].payload
    assert a1["sentiment"] == pytest.approx(0.4) and "US:AAPL" in a1["symbols"] and not any(s.endswith("XYZ") for s in a1["symbols"])
    assert a1["source"] == "marketaux:ex.com" and a2["sentiment"] is None and a2["summary"] == "The Federal Reserve held."
    assert emits[0].dedupe_key == "news:https://ex.com/a1" and newest.hour == 11 and newest.minute == 45


async def test_fetch_rotates_queries_budget_and_published_after(make_ctx):
    seen = []

    def h(req: httpx.Request):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json=BODY)

    ctx = make_ctx(h)
    src = MarketauxSource("SECRET", interval=1200, daily_budget=3)
    for _ in range(5):
        await src.fetch(ctx)
    assert len(seen) == 3 and src.calls_today == 3                       # tran ngay
    assert seen[0]["symbols"].startswith("AAPL") and "search" in seen[1] and seen[0]["limit"] == "3"
    assert seen[0]["filter_entities"] == "true" and seen[1]["filter_entities"] == "false"
    assert "published_after" in seen[0] and src.info()["calls_today"] == 3


async def test_quota_402_stops_for_the_day_and_no_token_leak(make_ctx):
    n = {"c": 0}

    def h(req):
        n["c"] += 1
        return httpx.Response(402, json={"error": {"code": "usage_limit_reached"}})

    ctx = make_ctx(h)
    src = MarketauxSource("SECRETTOKEN")
    assert await src.fetch(ctx) == [] and await src.fetch(ctx) == [] and n["c"] == 1 and src.info()["exhausted"]

    def boom(req):
        return httpx.Response(500, text="x")

    ctx2 = make_ctx(boom)
    ctx2.client.max_retries = 0
    with pytest.raises(RuntimeError) as ei:
        await MarketauxSource("SECRETTOKEN").fetch(ctx2)
    assert "SECRETTOKEN" not in str(ei.value)


def test_enabled_only_with_token_and_status_needs_key(monkeypatch):
    for k in ("MARKETAUX_TOKEN", "FMP_API_KEY", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert "news_marketaux" not in {s.name for s in build_sources(NewsSettings())}
    monkeypatch.setenv("MARKETAUX_TOKEN", "tok")
    assert "news_marketaux" in {s.name for s in build_sources(NewsSettings())}
    monkeypatch.setenv("NC_SRC_NEWS_MARKETAUX", "false")
    assert "news_marketaux" not in {s.name for s in build_sources(NewsSettings())}


def test_providers_endpoint(bus, monkeypatch):
    for k in ("MARKETAUX_TOKEN", "FMP_API_KEY", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(create_app(NewsSettings(), bus=bus, start_runner=False)) as c:
        d = {p["provider"]: p for p in c.get("/providers").json()["providers"]}
    assert d["news_marketaux"]["state"] == "needs_key" and d["news_marketaux"]["needs_env"] == ["MARKETAUX_TOKEN"]
    assert d["cal_fmp"]["state"] == "disabled" and d["cal_actuals:fred"]["state"] == "needs_key"
    monkeypatch.setenv("MARKETAUX_TOKEN", "tok")
    with TestClient(create_app(NewsSettings(), bus=bus, start_runner=False)) as c:
        d = {p["provider"]: p for p in c.get("/providers").json()["providers"]}
    assert d["news_marketaux"]["state"] == "active" and d["news_marketaux"]["usage"]["calls_today"] == 0
    assert "tok" not in json.dumps(d)
