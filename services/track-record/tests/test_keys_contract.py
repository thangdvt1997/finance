from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime

import pytest

from conftest import UTC
from track_record import extract
from track_record.engine import Engine

TW = os.path.join(os.path.dirname(__file__), "..", "..", "expert-collector", "src", "expert_collector", "trackweights.py")


_TW = []


def load_tw():
    if _TW:
        return _TW[0]
    spec = importlib.util.spec_from_file_location("tw_ec", TW)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _TW.append(m)
    return m


@pytest.mark.skipif(not os.path.exists(TW), reason="khong co expert-collector trong cay ma")
def test_weight_keys_match_expert_collector_lookup():
    tw = load_tw()
    pos = [{"expert_id": "CFTC:099741", "source": "cftc"}]
    sigs = [{"expert_id": "abc", "source": "myfx"}]
    emap = extract.expert_keys(sigs, pos)
    ent_cot, ent_sig = extract.entity_id("cot", "CFTC:099741"), extract.entity_id("expert", "abc")
    weights = {ent_cot: {"w": 0.53, "score": 42.0, "n": 150, "status": "rated", "hit": 0.4, "beats": False},
               ent_sig: {"w": 1.0, "score": 50.0, "n": 1, "status": "insufficient", "hit": None, "beats": False}}
    entries = [(k, r) for e, r in weights.items() for k in extract.weight_keys(e, emap)]
    redis_hash = {k: json.dumps(v) for k, v in extract.merge_weight_records(entries).items()}
    snap = {k: tw._clean(json.loads(v)) for k, v in redis_hash.items()}
    assert tw.weight_of(snap, "CFTC:099741", "cftc") == 0.53 and tw.weight_of(snap, "CFTC:099741") == 0.53
    assert tw.weight_of(snap, "abc", "myfx") == 1.0 and "myfx:abc" in snap


def test_shared_key_takes_conservative_min():
    out = extract.merge_weight_records([("k", {"w": 1.5}), ("k", {"w": 0.4}), ("j", {"w": 1.1})])
    assert out["k"]["w"] == 0.4 and out["j"]["w"] == 1.1


@pytest.mark.skipif(not os.path.exists(TW), reason="khong co expert-collector trong cay ma")
async def test_opinion_expert_news_entities_get_real_label_and_op_keys():
    from datetime import timedelta
    from track_record.store import MemStore
    tw = load_tw()
    meta = {"op:delong": {"name": "Brad DeLong", "org_type": "individual", "source": "opinion_feeds"}}
    ing = datetime(2026, 10, 5, 10, tzinfo=UTC)
    rows = [{"source": "expert:op:delong", "lang": "en", "published_at": ing, "ingested_at": ing, "enriched_at": None, "symbols": ["EURUSD"], "sentiment": 0.7}]
    now = datetime(2026, 10, 12, tzinfo=UTC)
    v = extract.news_views(rows, lambda s: True, now, meta)
    assert v[0]["label"] == "Brad DeLong" and v[0]["kind"] == "analyst"
    st = MemStore()
    await st.append_views(extract.merge_daily(v, now.date()))
    assert (await st.entities_all())[v[0]["entity_id"]]["label"] == "Brad DeLong"
    emap = extract.expert_keys([], [], rows, meta)
    eid = v[0]["entity_id"]
    keys = extract.weight_keys(eid, emap)
    assert "op:delong" in keys and "opinion_feeds:op:delong" in keys
    snap = {k: tw._clean({"w": 1.0, "status": "insufficient", "n": 3}) for k in keys}
    assert tw.lookup(snap, "op:delong", "opinion_feeds")["status"] == "insufficient"
