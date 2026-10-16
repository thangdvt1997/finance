"""Fixture lay tu RSS THAT (rut gon) ngay 2026-10-11 + cau hinh mac dinh."""
from pathlib import Path

import httpx
import pytest
import fakeredis.aioredis
from tscommon import Bus

from expert_collector.collector import Collector
from expert_collector.config import ECConfig
from expert_collector.default_feeds import DEFAULT_RSS_FEEDS
from expert_collector.httpclient import PoliteClient
from expert_collector.registry import build_sources
from expert_collector.reputation import Thresholds, reputation_score
from expert_collector.sources import rss_ideas
from .test_integration import T0, stream

FX = Path(__file__).parent / "fixtures"


def rd(n):
    return (FX / n).read_text(encoding="utf-8")


def test_actionforex_weekly_outlook_real():
    sigs = rss_ideas.parse_feed(rd("real_actionforex.xml"), "rss:actionforex_weekly", mode="technical_outlook")
    got = {s.symbol: s for s in sigs}
    assert set(got) == {"EURUSD", "USDJPY", "AUDUSD"}  # bai 'Has the Dollar Rally Stalled' (khong phai outlook) bi bo
    assert got["EURUSD"].side == "sell" and got["EURUSD"].sl is None  # 'further decline is expected'
    assert got["USDJPY"].side == "buy" and got["USDJPY"].sl == 156.36  # 'further rise ... as long as 156.36 support holds'
    assert got["AUDUSD"].side == "sell" and got["AUDUSD"].sl == 0.7038
    assert got["USDJPY"].opened_at.year == 2026 and got["USDJPY"].url.startswith("https://www.actionforex.com/")
    assert got["USDJPY"].raw["kind"] == "technical_outlook"


def test_generic_parser_no_false_positives_on_real_feeds():
    # Truoc khi siet: 'Long-Term' -> buy, 'giá' -> VN:GIA, 'long/short' trong than bai -> tin hieu rac
    assert rss_ideas.parse_feed(rd("real_babypips.xml"), "x") == []
    assert rss_ideas.parse_feed(rd("real_fxstreet_analysis.xml"), "x") == []
    assert rss_ideas.parse_feed(rd("real_vietstock_ptkt.xml"), "x") == []
    assert rss_ideas.extract_symbol_and_side("Phân tích kỹ thuật: giá bán lẻ tăng") is None
    assert rss_ideas.extract_symbol_and_side("Chart Art: EUR/NZD Testing Long-Term Triangle Top") is None
    assert rss_ideas.extract_symbol_and_side("EUR/USD bearish below 1.10") == ("EURUSD", "sell")
    assert rss_ideas.extract_symbol_and_side("Khuyến nghị MUA cổ phiếu HPG") == ("VN:HPG", "buy")


def test_default_feeds_env_semantics(monkeypatch):
    monkeypatch.delenv("EC_RSS_FEEDS", raising=False)
    assert [f["expert_id"] for f in ECConfig.from_env().rss_feeds] == ["rss:actionforex_weekly"]
    monkeypatch.setenv("EC_RSS_FEEDS", "[]")
    assert ECConfig.from_env().rss_feeds == []  # dat '[]' = tat han
    monkeypatch.setenv("EC_RSS_FEEDS", '[{"name":"x","url":"https://x.example/rss"}]')
    assert ECConfig.from_env().rss_feeds[0]["name"] == "x"
    assert "rss_ideas" in ECConfig.from_env().sources


def test_default_feed_publisher_reputation_passes_threshold():
    r = reputation_score(DEFAULT_RSS_FEEDS[0]["reputation"], Thresholds())
    assert r.qualified, r.reasons


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def test_default_config_end_to_end(bus):
    feed = rd("real_actionforex.xml")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, text=feed)

    client = PoliteClient("ua-test", min_interval=0, transport=httpx.MockTransport(handler))
    cfg = ECConfig(sources=["rss_ideas"], thresholds=Thresholds(), rss_feeds=[dict(f) for f in DEFAULT_RSS_FEEDS])
    c = Collector(build_sources(cfg, client), bus, cfg, now=lambda: T0)
    await c.poll_once()
    await c.poll_once()  # dedupe
    sigs = [s["payload"] for s in await stream(bus, "expert.signals")]
    assert {(s["symbol"], s["side"]) for s in sigs} == {("EURUSD", "sell"), ("USDJPY", "buy"), ("AUDUSD", "sell")}
    assert all(s["expert_id"] == "rss:actionforex_weekly" for s in sigs)
    await client.aclose()
