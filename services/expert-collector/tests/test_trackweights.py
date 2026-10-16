"""Trong so thanh tich (tr:weights) vao dong thuan + reputation.track; fail-open."""
import json
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from tscommon import Bus

from expert_collector.collector import Collector
from expert_collector.config import ECConfig
from expert_collector.consensus import compute_consensus, compute_weighted_consensus
from expert_collector.reputation import Thresholds
from expert_collector.sources.static_json import StaticJsonSource
from expert_collector.trackweights import TrackWeights, weight_of

from .test_integration import GOOD, T0, expert, pos, stream, write_doc

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
WIN = timedelta(hours=72)


def st(side="buy", sym="EURUSD"):
    return {sym: {"side": side, "ts": (NOW - timedelta(hours=1)).isoformat()}}


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


def rec(w, score=60, n=40, status="rated", hit=0.55, beats=False):
    return json.dumps({"w": w, "score": score, "n": n, "status": status, "hit": hit, "beats": beats})


def make(bus, path, **kw):
    cfg = ECConfig(thresholds=Thresholds(), consensus_min_experts=3, **kw)
    clock = {"t": T0}
    return Collector([StaticJsonSource(str(path))], bus, cfg, now=lambda: clock["t"]), clock


# ---------- thuan (compute_weighted_consensus) ----------
def test_weighted_equals_old_when_weights_default():
    s = {x: st("buy") for x in "abc"} | {"d": st("sell")}
    old = compute_consensus(s, NOW, WIN, 3, 0.7)
    new = compute_weighted_consensus(s, NOW, WIN, min_experts=3, min_ratio=0.7)
    assert [(c.symbol, c.side, c.experts, c.total) for c in new] == [(c.symbol, c.side, c.experts, c.total) for c in old]
    assert new[0].weight == 3.0 and new[0].weight_total == 4.0


def test_poor_track_cannot_create_consensus():
    s = {x: st("buy") for x in "abc"}
    assert compute_weighted_consensus(s, NOW, WIN, weights={"a": 0.25, "b": 0.25, "c": 0.25}) == []     # tong 0.75 < 3
    assert len(compute_weighted_consensus(s, NOW, WIN, weights={"a": 1.0, "b": 1.0, "c": 1.0})) == 1


def test_good_track_tips_ratio_and_weak_overruled():
    s = {"a": st("buy"), "b": st("buy"), "c": st("buy"), "d": st("sell"), "e": st("sell")}   # 3/5 = 60% < 70% (cu: khong dong thuan)
    assert compute_consensus(s, NOW, WIN, 3, 0.7) == []
    w = {"a": 1.6, "b": 1.6, "c": 1.6, "d": 0.4, "e": 0.4}                                    # buy 4.8 / 5.6 = 85.7%
    r = compute_weighted_consensus(s, NOW, WIN, weights=w, min_experts=3, min_ratio=0.7, min_weight=3.0)
    assert len(r) == 1 and r[0].side == "buy" and r[0].weight == 4.8 and r[0].weight_total == 5.6 and r[0].weight_ratio > 0.85
    # nguoc lai: 3 buy yeu, 1 sell manh -> ty le trong so thap -> khong dong thuan du 3/4 so luong (0.75 >= 0.7)
    s2 = {"a": st("buy"), "b": st("buy"), "c": st("buy"), "d": st("sell")}
    assert len(compute_consensus(s2, NOW, WIN, 3, 0.7)) == 1
    assert compute_weighted_consensus(s2, NOW, WIN, weights={"a": 1, "b": 1, "c": 1, "d": 2.5}, min_weight=0.5) == []


def test_high_weight_does_not_lower_expert_count():
    s = {"a": st("buy"), "b": st("buy")}
    assert compute_weighted_consensus(s, NOW, WIN, weights={"a": 2.0, "b": 2.0}) == []


def test_prior_and_bad_weights_sanitized():
    s = {x: st("buy") for x in "abc"}
    r = compute_weighted_consensus(s, NOW, WIN, weights={"a": float("nan"), "b": "x", "c": 99}, prior={"a": 1.0})
    assert len(r) == 1 and r[0].weights == {"a": 1.0, "b": 1.0, "c": 3.0}


# ---------- TrackWeights: fail-open ----------
async def test_trackweights_reads_and_lookup(bus):
    await bus.r.hset("tr:weights", mapping={"a": rec(1.4), "src:b": rec(0.5), "bad": "{not json", "nan": json.dumps({"w": "x"})})
    tw = TrackWeights(bus.r)
    snap = await tw.snapshot()
    assert set(snap) == {"a", "src:b"} and weight_of(snap, "a") == 1.4
    assert weight_of(snap, "b", "src") == 0.5 and weight_of(snap, "zzz") == 1.0


async def test_trackweights_fail_open_no_key_and_redis_down(bus):
    assert await TrackWeights(bus.r).snapshot() == {}

    class Boom:
        async def hgetall(self, *a):
            raise ConnectionError("down")
    assert await TrackWeights(Boom()).snapshot() == {}
    assert weight_of({}, "a") == 1.0


async def test_trackweights_stale_ignored_and_cache(bus):
    await bus.r.hset("tr:weights", mapping={"a": rec(0.3)})
    await bus.r.set("tr:weights:ts", str(NOW.timestamp() - 10 * 86400))
    assert await TrackWeights(bus.r, clock=lambda: NOW.timestamp()).snapshot() == {}      # qua cu -> fail-open
    await bus.r.set("tr:weights:ts", NOW.isoformat())
    t = {"v": NOW.timestamp()}
    tw = TrackWeights(bus.r, cache_seconds=30, clock=lambda: t["v"])
    assert weight_of(await tw.snapshot(), "a") == 0.3
    await bus.r.hset("tr:weights", mapping={"a": rec(1.9)})
    assert weight_of(await tw.snapshot(), "a") == 0.3          # cache
    t["v"] += 31
    assert weight_of(await tw.snapshot(), "a") == 1.9


# ---------- Collector ----------
async def cons_alerts(bus):
    return [a["payload"] for a in await stream(bus, "alerts.out") if a["payload"]["dedupe_key"].startswith("consensus")]


async def test_collector_consensus_weights_change_outcome(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert(x, [pos("EURUSD", "buy")]) for x in ("a", "b", "c")])
    await bus.r.hset("tr:weights", mapping={x: rec(0.3, score=40) for x in ("a", "b", "c")})
    c, _ = make(bus, f)
    await c.poll_once()
    assert await cons_alerts(bus) == []                       # 3 chuyen gia thanh tich kem -> khong du dong thuan


async def test_collector_consensus_alert_has_weight_and_disclaimer(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert(x, [pos("EURUSD", "buy")]) for x in ("a", "b", "c")])
    await bus.r.hset("tr:weights", mapping={x: rec(1.5, score=75, beats=True) for x in ("a", "b", "c")})
    c, _ = make(bus, f)
    await c.poll_once()
    al = await cons_alerts(bus)
    assert len(al) == 1 and "3/3" in al[0]["body"] and "4.50/4.50" in al[0]["body"] and "tham khao" in al[0]["body"].lower()


async def test_collector_fail_open_when_redis_weights_broken(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert(x, [pos("EURUSD", "buy")]) for x in ("a", "b", "c")])
    await bus.r.hset("tr:weights", mapping={"a": "garbage"})
    c, _ = make(bus, f)
    await c.poll_once()
    assert len(await cons_alerts(bus)) == 1                   # trong so 1.0 -> nhu cu


async def test_profile_track_field_and_dedupe(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("a", [pos("EURUSD", "buy")])])
    c, clock = make(bus, f)
    await c.poll_once()
    profs = [e["payload"] for e in await stream(bus, "expert.profiles")]
    assert len(profs) == 1 and "track" not in profs[0]["reputation"]                  # chua co track -> cau truc cu
    await c.poll_once()
    assert len(await stream(bus, "expert.profiles")) == 1

    await bus.r.hset("tr:weights", mapping={"a": rec(1.2, score=62, n=35, hit=0.56)})
    c.tw._at = None
    await c.poll_once()                                                                 # lan dau co track -> phat
    profs = [e["payload"] for e in await stream(bus, "expert.profiles")]
    assert len(profs) == 2
    t = profs[-1]["reputation"]["track"]
    assert t == {"score": 62, "n": 35, "status": "rated", "hit": 0.56, "beats": False, "weight": 1.2}
    assert profs[-1]["reputation"]["score"] is not None and "qualified" in profs[-1]["reputation"]   # cau truc reputation cu con nguyen

    await bus.r.hset("tr:weights", mapping={"a": rec(1.2, score=63)})                  # lech 1 diem -> KHONG phat lai
    c.tw._at = None
    await c.poll_once()
    assert len(await stream(bus, "expert.profiles")) == 2
    await bus.r.hset("tr:weights", mapping={"a": rec(1.3, score=65)})                  # lech >= 2 -> phat
    c.tw._at = None
    await c.poll_once()
    assert len(await stream(bus, "expert.profiles")) == 3
    await bus.r.hset("tr:weights", mapping={"a": rec(1.3, score=65, beats=True)})      # doi beats -> phat
    c.tw._at = None
    await c.poll_once()
    assert len(await stream(bus, "expert.profiles")) == 4
