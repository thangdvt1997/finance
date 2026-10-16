from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import numpy as np
import pytest

from conftest import T0, UTC, walk
from track_record import consensus
from track_record.app import create_app
from track_record.data import MemData
from track_record.engine import Engine
from track_record.store import MemStore

NOW = T0 + timedelta(days=330)


def make_data() -> MemData:
    rng = np.random.default_rng(5)
    prices = {"EURUSD": walk(420, 1), "XAUUSD": walk(420, 2, 2000.0, 0.01)}
    news = []
    for src in ("fxstreet_news", "cafef_chungkhoan", "boe_speeches"):
        for i in range(200):
            ing = T0 + timedelta(days=100 + i, hours=9)
            news.append({"source": src, "lang": "en", "published_at": ing, "ingested_at": ing, "enriched_at": ing + timedelta(minutes=1),
                         "symbols": ["EURUSD"], "sentiment": float(rng.choice([-0.8, 0.8]))})
    sig = [{"expert_id": "x1", "symbol": "XAUUSD", "side": "buy", "opened_at": NOW - timedelta(days=2), "sl": 1900.0}]
    return MemData(news=news, signals=sig, names={"x1": "Tran Van A"}, prices=prices)


@pytest.fixture
async def client():
    eng = Engine(make_data(), MemStore(), None, now_fn=lambda: NOW)
    await eng.run_once()
    app = create_app(eng, interval_s=0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, eng


async def test_leaderboard_honest_and_hides_sources(client):
    c, eng = client
    r = await c.get("/track/leaderboard", params={"horizon": "1W"})
    j = r.json()
    assert r.status_code == 200 and j["disclaimer"].startswith("Chỉ tham khảo") and j["baseline"]["hit_rate"] == 0.5
    assert j["summary"]["entities"] == 4 and j["summary"]["rated"] >= 1
    for row in j["rows"]:
        assert set(("entity_id", "label", "kind", "lang", "n", "n_total", "hit_rate", "p_value", "q_value", "beats_baseline", "score", "weight", "status", "rank", "n_needed")) <= set(row)
        if row["status"] != "rated":
            assert row["rank"] is None and row["weight"] == 1.0
        else:
            assert row["n"] >= 30 and row["rank"] is not None
    blob = (await c.get("/track/feed")).text + r.text + (await c.get("/track/methodology")).text
    for tok in ("fxstreet", "cafef", "boe_", "chungkhoan", "speeches", '"source"'):
        assert tok not in blob


async def test_random_news_streams_do_not_beat_baseline(client):
    c, _ = client
    j = (await c.get("/track/leaderboard", params={"horizon": "1W", "scope": "all"})).json()
    assert j["summary"]["beating_baseline"] == 0 or j["summary"]["beating_baseline"] <= 1


async def test_track_record_detail_and_404_and_validation(client):
    c, _ = client
    lb = (await c.get("/track/leaderboard")).json()["rows"]
    eid = next(r["entity_id"] for r in lb if r["kind"] == "media")
    r = await c.get(f"/track/experts/{eid}/track-record", params={"horizon": "1W"})
    j = r.json()
    assert r.status_code == 200 and set(j["horizons"]) == {"1D", "1W", "1M"} and j["chain"]["verified"] is True
    assert j["equity"]["points"] and j["rolling"] and j["recent"] and set(j["recent"][0]["outcome"]) == {"1D", "1W", "1M"}
    assert (await c.get("/track/experts/ent:deadbeef/track-record")).status_code == 404
    assert (await c.get("/track/experts/xx/track-record")).status_code == 422
    for bad in ({"horizon": "2W"}, {"scope": "sym:<script>"}, {"limit": 9999}, {"min_n": 3}):
        assert (await c.get("/track/leaderboard", params=bad)).status_code == 422
    assert (await c.post("/track/leaderboard")).status_code == 405
    assert (await c.get("/track/feed", params={"before": "nope"})).status_code == 422


async def test_feed_consensus_chain_methodology(client):
    c, eng = client
    f = (await c.get("/track/feed", params={"limit": 5})).json()
    assert len(f["items"]) == 5 and f["next_before"]
    f2 = (await c.get("/track/feed", params={"limit": 5, "before": f["next_before"]})).json()
    assert f2["items"][0]["view_id"] not in {x["view_id"] for x in f["items"]}
    cs = (await c.get("/track/consensus", params={"window_days": 90})).json()
    assert cs["rows"] and all(r["level"] in ("none", "weak", "consensus") for r in cs["rows"])
    v = (await c.get("/track/chain/verify")).json()
    assert v["ok"] and v["n"] > 100
    assert (await c.get("/track/methodology")).json()["min_n"] == 30
    assert (await c.get("/healthz")).status_code == 200


def test_consensus_levels_and_latest_per_expert():
    now = datetime(2026, 10, 12, tzinfo=UTC)
    ents = {f"e{i}": {"label": f"L{i}"} for i in range(4)}
    w = {f"e{i}": {"w": 1.0, "status": "insufficient"} for i in range(4)}
    views = [{"entity_id": f"e{i}", "symbol": "EURUSD", "direction": "bullish", "published_at": now - timedelta(days=1)} for i in range(3)]
    views.append({"entity_id": "e3", "symbol": "EURUSD", "direction": "bearish", "published_at": now - timedelta(days=2)})
    views.append({"entity_id": "e3", "symbol": "EURUSD", "direction": "bullish", "published_at": now - timedelta(days=1)})   # moi nhat thang
    views.append({"entity_id": "e0", "symbol": "EURUSD", "direction": "bearish", "published_at": now - timedelta(days=40)})    # ngoai cua so
    rows = consensus.build(views, ents, w, now, 14, "all", 1)
    assert len(rows) == 1 and rows[0]["n_experts"] == 4 and rows[0]["level"] == "consensus" and rows[0]["net_weighted"] == 1.0
    assert consensus.build(views, ents, w, now, 14, "all", 5) == []
    assert consensus.build(views, ents, w, now, 14, "crypto", 1) == []
    w["e0"]["w"] = 0.25
    w["e1"]["w"] = 0.25
    views[0]["direction"] = "bearish"
    r2 = consensus.build(views, ents, w, now, 14, "all", 1)[0]
    assert r2["net_weighted"] != r2["net_unweighted"]
