import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from tscommon.bus import Bus
from tscommon.events import make_event

from nlp.settings import NlpSettings
from nlp.worker import ALERT_STREAM, IN_STREAM, OUT_STREAM, NlpWorker


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


def news(url, title, source="rss", lang="en", published_at=None, symbols=()):
    return make_event("news", "news-collector", {"url": url, "title": title, "summary": None,
                                                  "published_at": published_at, "source": source, "lang": lang,
                                                  "symbols": list(symbols), "sentiment": None})


async def read_all(bus, stream, group="t"):
    return [e async for _, e in bus.consume(stream, group, "c", block_ms=0)]


async def run_until(worker, pred, timeout=8.0):
    await worker.start()
    t = 0.0
    while not pred() and t < timeout:
        await asyncio.sleep(0.05)
        t += 0.05
    await worker.stop()


def make_worker(bus, enricher, **cfg):
    cfg.setdefault("read_block_ms", 0)      # fakeredis không hỗ trợ huỷ khi block
    return NlpWorker(NlpSettings(**cfg), bus, lambda: enricher)


async def test_enrich_publish_ack_and_idempotent(bus, enricher):
    for i in range(3):
        await bus.publish(IN_STREAM, news(f"http://x/{i}", "Gold prices surge as Fed cuts rates"))
    await bus.publish(IN_STREAM, news("http://x/0", "Gold prices surge as Fed cuts rates"))     # trùng url+model
    w = make_worker(bus, enricher)
    await run_until(w, lambda: w.processed >= 3)
    await asyncio.sleep(0.2)
    out = await read_all(bus, OUT_STREAM)
    assert sorted(e.payload["url"] for e in out) == ["http://x/0", "http://x/1", "http://x/2"]
    p = out[0].payload
    assert p["label"] == "positive" and p["model_version"] == "fake-en@1" and "XAUUSD" in p["symbols"]
    assert p["lang"] == "en" and p["importance"] in {"low", "med", "high"} and "monetary_policy" in p["topics"]
    assert p["title"] and p["source"] == "rss"
    assert out[0].type == "news_enriched" and out[0].source == "nlp"
    assert (await bus.r.xpending(IN_STREAM, "nlp"))["pending"] == 0


async def test_new_model_version_reprocesses(bus, enricher, fake_en):
    await bus.publish(IN_STREAM, news("http://y/1", "Stocks plunge"))
    w = make_worker(bus, enricher)
    await run_until(w, lambda: w.processed >= 1)
    fake_en.version = "fake-en@2"
    await bus.publish(IN_STREAM, news("http://y/1", "Stocks plunge"))
    w2 = make_worker(bus, enricher, consumer="c2")
    await run_until(w2, lambda: w2.processed >= 1)
    versions = sorted(e.payload["model_version"] for e in await read_all(bus, OUT_STREAM))
    assert versions == ["fake-en@1", "fake-en@2"]


async def test_vi_routing_invalid_and_skip_sources(bus, enricher):
    await bus.publish(IN_STREAM, news("http://v/1", "Cổ phiếu PNJ tăng trần", lang="vi"))
    await bus.publish(IN_STREAM, news("http://v/2", "COT report", source="cot"))
    await bus.r.xadd(IN_STREAM, {"e": "không phải json"})
    await bus.publish(IN_STREAM, make_event("news", "x", {"title": "thiếu url", "source": "rss"}))
    w = make_worker(bus, enricher)
    await run_until(w, lambda: w.processed >= 1)
    await asyncio.sleep(0.3)
    out = await read_all(bus, OUT_STREAM)
    assert len(out) == 1 and out[0].payload["model_version"] == "fake-vi@1" and "VN:PNJ" in out[0].payload["symbols"]
    assert await bus.r.xlen("dlq") == 2                                # json hỏng + thiếu url
    assert (await bus.r.xpending(IN_STREAM, "nlp"))["pending"] == 0    # cot được ack, không enriched


async def test_backpressure_large_backfill(bus, enricher, fake_en):
    n = 300
    for i in range(n):
        await bus.publish(IN_STREAM, news(f"http://b/{i}", f"Stocks gain {i}"))
    w = make_worker(bus, enricher, batch=32, queue_max=40)
    await run_until(w, lambda: w.processed >= n, timeout=30)
    assert w.processed == n and w.queue.qsize() == 0
    assert max(len(c) for c in fake_en.calls) <= 32 and len(fake_en.calls) < n    # có gộp lô


async def test_pending_own_recovered_after_restart(bus, enricher):
    await bus.publish(IN_STREAM, news("http://p/1", "Stocks surge"))
    await bus.ensure_group(IN_STREAM, "nlp")
    await bus.r.xreadgroup("nlp", "nlp-1", {IN_STREAM: ">"}, count=10)    # đã giao nhưng chưa ack (crash)
    w = make_worker(bus, enricher, consumer="nlp-1")
    await run_until(w, lambda: w.processed >= 1)
    assert len(await read_all(bus, OUT_STREAM)) == 1


async def test_reversal_alert_emitted_once(bus, enricher):
    now = datetime.now(timezone.utc)
    pos = [news(f"http://r/p{i}", "Gold prices surge on Fed", published_at=(now - timedelta(hours=3 + i)).isoformat())
           for i in range(8)]
    neg = [news(f"http://r/n{i}", "Gold prices plunge on Fed", published_at=(now - timedelta(minutes=5 * (i + 1))).isoformat())
           for i in range(4)]
    for e in pos + neg:
        await bus.publish(IN_STREAM, e)
    w = make_worker(bus, enricher, batch=4)
    await run_until(w, lambda: w.processed >= 12)
    alerts = [e for e in await read_all(bus, ALERT_STREAM) if "XAUUSD" in e.payload["title"]]
    assert len(alerts) == 1 and alerts[0].type == "alert"
    a = alerts[0].payload
    assert a["level"] in {"warn", "crit"} and a["dedupe_key"].startswith("nlp:flip:XAUUSD:down:") and "nlp" in a["tags"]
    assert "giao dịch" in a["body"]


async def test_backfill_old_news_no_alert(bus, enricher):
    old = datetime.now(timezone.utc) - timedelta(days=3)
    for i in range(10):
        await bus.publish(IN_STREAM, news(f"http://o/{i}", "Gold prices surge" if i < 6 else "Gold prices plunge",
                                          published_at=(old + timedelta(minutes=i)).isoformat()))
    w = make_worker(bus, enricher)
    await run_until(w, lambda: w.processed >= 10)
    assert await read_all(bus, ALERT_STREAM) == []


async def test_http_endpoints(bus, enricher):
    from httpx import ASGITransport, AsyncClient

    from nlp.app import create_app

    app = create_app(NlpSettings(), bus, start_worker=False, enricher_factory=lambda: enricher)
    app.state.worker.enricher = enricher
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/healthz")).json()["service"] == "nlp"
        assert (await c.get("/metrics")).status_code == 200
        r = await c.post("/v1/analyze", json={"title": "Gold prices surge as Fed cuts rates"})
        j = r.json()
        assert r.status_code == 200 and j["label"] == "positive" and "XAUUSD" in j["symbols"]
        assert (await c.get("/v1/sentiment")).status_code == 200
        assert (await c.get("/v1/sentiment", params={"symbol": "ZZZ"})).status_code == 404
        assert (await c.post("/v1/analyze", json={"title": ""})).status_code == 422
