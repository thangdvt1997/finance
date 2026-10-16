import json
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from tscommon import Bus

from expert_collector.app import build_app
from expert_collector.collector import Collector
from expert_collector.config import ECConfig
from expert_collector.httpclient import PoliteClient, RobotsDenied
from expert_collector.registry import build_sources
from expert_collector.reputation import Thresholds
from expert_collector.sources.static_json import StaticJsonSource

GOOD = {"gain_pct": 80, "max_drawdown_pct": 15, "months_active": 24, "followers": 500}
T0 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def write_doc(path, experts):
    path.write_text(json.dumps({"experts": experts}), encoding="utf-8")


def expert(eid, positions, rep=GOOD, name=None):
    return {"expert_id": eid, "display_name": name or eid, "reputation": rep, "positions": positions}


def pos(sym, side, vol=0.1, opened="2026-10-01T00:00:00Z"):
    return {"symbol": sym, "side": side, "volume": vol, "entry": 1.1, "opened_at": opened}


async def stream(bus, name):
    return [json.loads(f["e"]) for _, f in await bus.r.xrange(name)]


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


def make(bus, path, th=None, **kw):
    cfg = ECConfig(thresholds=th or Thresholds(), consensus_min_experts=3, **kw)
    clock = {"t": T0}
    c = Collector([StaticJsonSource(str(path))], bus, cfg, now=lambda: clock["t"])
    return c, clock


async def test_baseline_then_changes(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("e1", [pos("EURUSD", "buy")])])
    c, clock = make(bus, f)
    await c.poll_once()
    sigs = await stream(bus, "expert.signals")
    assert len(sigs) == 1 and sigs[0]["payload"]["raw"]["baseline"] is True
    assert await stream(bus, "alerts.out") == []  # baseline khong bao dong

    await c.poll_once()  # khong doi -> khong phat them
    assert len(await stream(bus, "expert.signals")) == 1

    clock["t"] += timedelta(minutes=5)
    write_doc(f, [expert("e1", [pos("EURUSD", "sell", opened="2026-10-10T12:03:00Z"), pos("GBPUSD", "buy", 0.2)])])
    await c.poll_once()
    sigs = [s["payload"] for s in await stream(bus, "expert.signals")]
    statuses = [(s["symbol"], s["side"], s["status"]) for s in sigs[1:]]
    assert ("EURUSD", "buy", "closed") in statuses and ("EURUSD", "sell", "open") in statuses
    assert ("GBPUSD", "buy", "open") in statuses
    alerts = [a["payload"] for a in await stream(bus, "alerts.out")]
    assert len(alerts) == 2 and all("KHONG phai khuyen nghi" in a["body"] for a in alerts)
    assert any(a["level"] == "warn" and "DAO CHIEU" in a["title"] for a in alerts)
    assert all(a["dedupe_key"] for a in alerts)
    pos_ev = await stream(bus, "expert.positions")
    assert {p["payload"]["symbol"] for p in pos_ev} == {"EURUSD", "GBPUSD"}

    write_doc(f, [expert("e1", [])])
    await c.poll_once()
    assert any(a["payload"]["title"].endswith("DONG GBPUSD") for a in await stream(bus, "alerts.out"))


async def test_unqualified_expert_not_tracked(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("bad", [pos("EURUSD", "buy")], rep={**GOOD, "months_active": 2})])
    c, _ = make(bus, f)
    await c.poll_once()
    assert await stream(bus, "expert.signals") == []
    items = await c.list_experts_api()
    assert items[0]["tracked"] is False and any("months_active" in r for r in items[0]["reasons"])
    assert await c.list_experts_api(tracked_only=True) == []


async def test_history_wipe_disqualifies(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("e1", [], rep={**GOOD, "months_active": 14, "trades": 400})])
    c, clock = make(bus, f)
    await c.poll_once()
    assert (await c.list_experts_api())[0]["tracked"] is True
    clock["t"] += timedelta(days=1)
    write_doc(f, [expert("e1", [], rep={**GOOD, "months_active": 8, "trades": 40})])  # xoa lich su de 'lam dep'
    await c.poll_once()
    e = (await c.list_experts_api())[0]
    assert e["history_wiped"] and not e["tracked"]
    clock["t"] += timedelta(days=1)
    write_doc(f, [expert("e1", [], rep={**GOOD, "months_active": 24, "trades": 500})])
    await c.poll_once()
    assert (await c.list_experts_api())[0]["history_wiped"]  # co van con trong 90 ngay


async def test_martingale_excluded(bus, tmp_path):
    f = tmp_path / "e.json"
    doc = expert("m", [])
    doc["closed_trades"] = [{"volume": v, "profit": -1} for v in (0.1, 0.2, 0.4, 0.8, 1.6)]
    write_doc(f, [doc])
    c, _ = make(bus, f)
    await c.poll_once()
    e = (await c.list_experts_api())[0]
    assert e["martingale"] and not e["tracked"]


async def test_consensus_alert_once(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert(x, [pos("EURUSD", "buy")]) for x in ("a", "b", "c")])
    c, _ = make(bus, f)
    await c.poll_once()
    await c.poll_once()
    cons = [a["payload"] for a in await stream(bus, "alerts.out") if a["payload"]["dedupe_key"].startswith("consensus")]
    assert len(cons) == 1 and "BUY EURUSD" in cons[0]["title"] and "3/3" in cons[0]["body"]


async def test_source_failure_isolated(bus, tmp_path):
    class Boom(StaticJsonSource):
        async def list_experts(self):
            raise RuntimeError("down")

    f = tmp_path / "e.json"
    write_doc(f, [expert("e1", [pos("EURUSD", "buy")])])
    c = Collector([Boom(str(f)), StaticJsonSource(str(f))], bus, ECConfig(), now=lambda: T0)
    await c.poll_once()
    assert len(await stream(bus, "expert.signals")) == 1


async def test_rss_source_end_to_end(bus):
    feed = open(__file__.replace("test_integration.py", "fixtures/feed.xml"), encoding="utf-8").read()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=feed)

    client = PoliteClient("ua-test", min_interval=0, transport=httpx.MockTransport(handler))
    cfg = ECConfig(sources=["rss_ideas"], thresholds=Thresholds(),
                   rss_feeds=[{"name": "Pro", "url": "https://feed.example/rss", "reputation": GOOD}])
    c = Collector(build_sources(cfg, client), bus, cfg, now=lambda: T0)
    await c.poll_once()
    await c.poll_once()  # dedupe
    sigs = [s["payload"] for s in await stream(bus, "expert.signals")]
    assert {(s["symbol"], s["side"]) for s in sigs} == {("EURUSD", "buy"), ("VN:VNM", "buy"), ("VN:HPG", "sell"), ("XAUUSD", "sell")}
    assert len(sigs) == 4
    await client.aclose()


async def test_api(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("vn:abc", [])])
    c, _ = make(bus, f)
    await c.poll_once()
    app = build_app(c, run_loop=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        assert (await http.get("/healthz")).json()["status"] == "ok"
        assert "ec_signals_published_total" in (await http.get("/metrics")).text
        j = (await http.get("/experts")).json()
        assert j["items"][0]["expert_id"] == "vn:abc" and "KHONG" in j["disclaimer"]
        assert (await http.get("/experts/vn:abc")).status_code == 200
        assert (await http.get("/experts/none")).status_code == 404


def test_registry_gates_risky_sources():
    cfg = ECConfig(sources=["mql5", "myfxbook", "rss_ideas"], mql5_accept_tos=False)
    srcs = build_sources(cfg, PoliteClient("ua"))
    assert [s.name for s in srcs] == ["rss_ideas"]
    cfg = ECConfig(sources=["mql5", "myfxbook"], mql5_accept_tos=True, myfxbook_email="a", myfxbook_password="b")
    assert [s.name for s in build_sources(cfg, PoliteClient("ua"))] == ["mql5", "myfxbook"]


async def test_polite_client_cache_ratelimit_robots():
    calls = []
    sleeps = []
    clock = {"t": 0.0}

    def handler(req):
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="ok")

    async def fake_sleep(s):
        sleeps.append(s)
        clock["t"] += s

    c = PoliteClient("ua", min_interval=2, cache_ttl=60, transport=httpx.MockTransport(handler),
                     clock=lambda: clock["t"], sleep=fake_sleep)
    assert await c.get_text("https://h.example/a") == "ok"
    assert await c.get_text("https://h.example/a") == "ok"  # cache
    assert len([x for x in calls if x.endswith("/a")]) == 1
    await c.get_text("https://h.example/b")
    assert sleeps and max(sleeps) <= 2
    with pytest.raises(RobotsDenied):
        await c.get_text("https://h.example/private/x")
    assert len([x for x in calls if x.endswith("robots.txt")]) == 1
    await c.aclose()


async def test_robots_unreachable_denies():
    def handler(req):
        return httpx.Response(503)

    c = PoliteClient("ua", min_interval=0, transport=httpx.MockTransport(handler))
    with pytest.raises(RobotsDenied):
        await c.get_text("https://h.example/a")
    await c.aclose()


async def test_profiles_published_and_deduped(bus, tmp_path):
    f = tmp_path / "e.json"
    write_doc(f, [expert("e1", [pos("EURUSD", "buy")], name="Ten E1"),
                  expert("bad", [], rep={"gain_pct": 1, "max_drawdown_pct": 90, "months_active": 1, "followers": 0})])
    c, clock = make(bus, f)
    await c.poll_once()
    profs = {p["payload"]["expert_id"]: p for p in await stream(bus, "expert.profiles")}
    assert set(profs) == {"e1", "bad"}  # ca chuyen gia khong dat chuan (tracked=False) cung duoc ghi nhan
    e1 = profs["e1"]
    assert e1["type"] == "expert_profile" and e1["payload"]["tracked"] is True
    assert e1["payload"]["display_name"] == "Ten E1" and e1["payload"]["reputation"]["gain_pct"] == 80
    assert "score" in e1["payload"]["reputation"]
    assert profs["bad"]["payload"]["tracked"] is False
    await c.poll_once()  # khong doi -> khong phat lai
    assert len(await stream(bus, "expert.profiles")) == 2
    write_doc(f, [expert("e1", [pos("EURUSD", "buy")], rep={**GOOD, "followers": 900}, name="Ten E1")])
    await c.poll_once()  # reputation doi -> phat lai
    assert len(await stream(bus, "expert.profiles")) == 3
