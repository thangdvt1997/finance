import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis as fr
import httpx
import pytest
from fastapi.testclient import TestClient
from tscommon import make_event

from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
H = {"X-API-Key": "tok1"}


def settings(**kw):
    base = dict(api_tokens=("tok1", "tok2"), auth_disabled=False, cors_origins=("http://ui.local",),
                max_page_size=50, ws_max_connections=2)
    base.update(kw)
    return GatewaySettings(**base)


def make_repo():
    bars = [{"symbol": "EURUSD", "tf": "M1", "ts_open": NOW - timedelta(minutes=i), "o": 1.0, "h": 1.1, "l": 0.9,
             "c": 1.05, "v": 10, "source": "t"} for i in range(120)]
    return InMemoryRepo(
        bars=bars,
        quotes=[{"symbol": "EURUSD", "ts": NOW - timedelta(seconds=5), "bid": 1.1, "ask": 1.2, "source": "t"},
                {"symbol": "EURUSD", "ts": NOW - timedelta(seconds=50), "bid": 1.0, "ask": 1.1, "source": "t"},
                {"symbol": "XAUUSD", "ts": NOW, "bid": 2400.0, "ask": 2400.5, "source": "t"}],
        news_items=[{"url": f"u{i}", "title": f"n{i}", "published_at": NOW - timedelta(hours=i), "source": "rss",
                     "symbols": ["EURUSD"] if i % 2 == 0 else ["XAUUSD"]} for i in range(6)],
        calendar_events=[{"event_id": "1", "source": "ff", "title": "NFP", "impact": "high", "ts": NOW + timedelta(hours=3)},
                         {"event_id": "2", "source": "ff", "title": "Minor", "impact": "low", "ts": NOW + timedelta(hours=4)},
                         {"event_id": "3", "source": "ff", "title": "Far", "impact": "high", "ts": NOW + timedelta(days=9)}],
        experts=[{"expert_id": "e1", "source": "s", "display_name": "E1"}],
        expert_signals=[{"expert_id": "e1", "source": "s", "symbol": "EURUSD", "side": "buy", "opened_at": NOW,
                         "status": "open", "entry": 1.1},
                        {"expert_id": "e1", "source": "s", "symbol": "XAUUSD", "side": "sell",
                         "opened_at": NOW - timedelta(days=1), "status": "closed"}],
        expert_positions=[{"expert_id": "e1", "source": "s", "symbol": "EURUSD", "as_of": NOW, "net_volume": 1.5}],
        account_snapshots=[{"account_id": "a1", "platform": "mt5", "ts": NOW - timedelta(minutes=1), "balance": 1, "equity": 1},
                           {"account_id": "a1", "platform": "mt5", "ts": NOW, "balance": 2, "equity": 2, "positions": []}],
        alerts=[{"id": 1, "ts": NOW, "level": "warn", "title": "w"}, {"id": 2, "ts": NOW, "level": "crit", "title": "c"}],
    )


@pytest.fixture
async def client():
    app = create_app(settings(), make_repo(), fr.FakeRedis(decode_responses=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as c:
        yield c


@pytest.fixture
async def anon():
    app = create_app(settings(), make_repo(), fr.FakeRedis(decode_responses=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_open_endpoints_no_auth(anon):
    client = anon
    assert (await client.get("/healthz", headers={})).status_code == 200
    assert "gateway_http_requests_total" in (await client.get("/metrics", headers={})).text
    r = await client.get("/ui", headers={})
    assert r.status_code == 200 and "Trading System" in r.text
    assert (await client.get("/readyz", headers={})).status_code == 200


async def test_auth(anon):
    client = anon
    assert (await client.get("/v1/experts", headers={})).status_code == 401
    assert (await client.get("/v1/experts", headers={"X-API-Key": "bad"})).status_code == 401
    assert (await client.get("/v1/experts", headers={"X-API-Key": "tok2"})).status_code == 200


async def test_fail_closed_without_tokens():
    app = create_app(settings(api_tokens=()), make_repo(), None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/v1/experts", headers=H)).status_code == 401


async def test_bars_filters_and_paging(client):
    r = await client.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M1", "limit": 10})
    d = r.json()
    assert r.status_code == 200 and d["count"] == 10 and d["limit"] == 10
    assert d["items"][0]["ts_open"] > d["items"][-1]["ts_open"]  # desc mặc định
    frm = (NOW - timedelta(minutes=5)).isoformat()
    r = await client.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M1", "from": frm, "order": "asc"})
    items = r.json()["items"]
    assert 5 <= len(items) <= 6 and items[0]["ts_open"] < items[-1]["ts_open"]
    p2 = (await client.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M1", "limit": 10, "offset": 10})).json()
    assert p2["items"][0] != d["items"][0]


async def test_validation(client):
    assert (await client.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M2"})).status_code == 422
    assert (await client.get("/v1/bars", params={"symbol": "EUR USD;--", "tf": "M1"})).status_code == 422
    assert (await client.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M1", "limit": 999999})).status_code == 422
    assert (await client.get("/v1/calendar", params={"impact": "huge"})).status_code == 422
    r = await client.get("/v1/news", params={"limit": 500})  # kẹp theo max_page_size
    assert r.json()["limit"] == 50


async def test_quotes_news_calendar(client):
    q = (await client.get("/v1/quotes/latest")).json()
    assert {x["symbol"]: x["bid"] for x in q} == {"EURUSD": 1.1, "XAUUSD": 2400.0}
    assert len((await client.get("/v1/quotes/latest", params={"symbols": "XAUUSD"})).json()) == 1
    assert (await client.get("/v1/news", params={"symbol": "EURUSD"})).json()["count"] == 3
    since = (NOW - timedelta(hours=1, minutes=30)).isoformat()
    assert (await client.get("/v1/news", params={"since": since})).json()["count"] == 2
    c = (await client.get("/v1/calendar", params={"impact": "high", "to": (NOW + timedelta(days=1)).isoformat()})).json()
    assert [e["title"] for e in c["items"]] == ["NFP"]


async def test_experts_accounts_alerts(client):
    assert (await client.get("/v1/experts")).json()["count"] == 1
    s = (await client.get("/v1/expert-signals", params={"status": "open"})).json()
    assert [x["symbol"] for x in s["items"]] == ["EURUSD"]
    assert (await client.get("/v1/expert-positions", params={"symbol": "EURUSD"})).json()["count"] == 1
    a = (await client.get("/v1/accounts")).json()
    assert len(a) == 1 and a[0]["balance"] == 2
    al = (await client.get("/v1/alerts", params={"level": "crit"})).json()
    assert [x["title"] for x in al["items"]] == ["c"]


async def test_overview(client):
    o = (await client.get("/v1/overview")).json()
    assert len(o["quotes"]) == 2 and o["news"] and len(o["upcoming_events"]) == 1
    assert o["upcoming_events"][0]["title"] == "NFP"
    assert len(o["expert_signals"]) == 1 and len(o["accounts"]) == 1


async def test_openapi_and_cors(client):
    spec = (await client.get("/openapi.json")).json()
    for p in ("/v1/bars", "/v1/overview", "/v1/quotes/latest", "/v1/expert-signals", "/v1/accounts"):
        assert p in spec["paths"]
    r = await client.options("/v1/experts", headers={"Origin": "http://ui.local", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://ui.local"
    r = await client.options("/v1/experts", headers={"Origin": "http://evil", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


class _ScriptedRedis:
    """Redis giả cho WS: xread trả sự kiện đã xếp sẵn (fakeredis treo loop với BLOCK)."""

    def __init__(self, events):
        self.events = list(events)

    async def xread(self, streams, count=None, block=None):
        if self.events:
            st, ev = self.events.pop(0)
            return [(st, [("1-0", {"e": ev.model_dump_json()})])]
        await asyncio.sleep(0.05)
        return []


def test_websocket_auth_and_stream():
    evs = [("md.quotes", make_event("quote", "t", {"symbol": s, "bid": 1, "ask": 2, "source": "t"}))
           for s in ("XAUUSD", "EURUSD")]
    app = create_app(settings(), make_repo(), _ScriptedRedis(evs))
    tc = TestClient(app)
    with tc.websocket_connect("/v1/stream") as ws:  # sai key
        ws.send_json({"type": "auth", "api_key": "nope"})
        with pytest.raises(Exception):
            ws.receive_json()
    with pytest.raises(Exception):  # stream không hợp lệ
        with tc.websocket_connect("/v1/stream?streams=evil"):
            pass
    with tc.websocket_connect("/v1/stream?streams=md.quotes&symbols=EURUSD") as ws:  # auth bằng tin nhắn đầu
        ws.send_json({"type": "auth", "api_key": "tok1"})
        assert ws.receive_json()["type"] == "ready"
        msg = ws.receive_json()  # XAUUSD bị lọc
        assert msg["type"] == "event" and msg["event"]["payload"]["symbol"] == "EURUSD"
    # dọn dẹp phía server chạy bất đồng bộ sau khi client đóng: chờ điều kiện có timeout thay vì assert ngay
    deadline = time.monotonic() + 5
    while app.state.ws_count != 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert app.state.ws_count == 0


def _cal_repo():
    ev = lambda i, **kw: {"event_id": str(i), "source": "ff", "title": f"E{i}", "impact": "high", **kw}  # noqa: E731
    return InMemoryRepo(
        calendar_events=[ev(1, ts=NOW - timedelta(days=3)), ev(2, ts=NOW - timedelta(hours=5)),
                         ev(3, ts=NOW + timedelta(hours=6)), ev(4, ts=NOW + timedelta(hours=1)),
                         ev(5, ts=NOW + timedelta(days=2))],
        news_items=[{"url": "a", "title": "old", "published_at": NOW - timedelta(days=2), "source": "r"},
                    {"url": "b", "title": "new", "published_at": NOW - timedelta(minutes=1), "source": "r"},
                    {"url": "c", "title": "nopub", "published_at": None, "ingested_at": NOW - timedelta(hours=1),
                     "source": "r"},
                    {"url": "d", "title": "mid", "published_at": NOW - timedelta(hours=2), "source": "r"}])


@pytest.fixture
async def cal_client():
    app = create_app(settings(), _cal_repo(), fr.FakeRedis(decode_responses=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as c:
        yield c


async def test_calendar_default_upcoming_first_and_from_default(cal_client):
    items = (await cal_client.get("/v1/calendar")).json()["items"]
    # mặc định from = now-1d: bỏ E1 (3 ngày trước); sắp tới tăng dần (E4,E3,E5) rồi quá khứ (E2)
    assert [e["title"] for e in items] == ["E4", "E3", "E5", "E2"]


async def test_calendar_explicit_from_to_and_order(cal_client):
    r = (await cal_client.get("/v1/calendar", params={"from": (NOW - timedelta(days=5)).isoformat(),
                                                      "to": (NOW + timedelta(days=1)).isoformat(), "order": "asc"})).json()
    assert [e["title"] for e in r["items"]] == ["E1", "E2", "E4", "E3"]
    r = (await cal_client.get("/v1/calendar", params={"order": "desc"})).json()
    assert [e["title"] for e in r["items"]] == ["E5", "E3", "E4", "E2"]
    assert (await cal_client.get("/v1/calendar", params={"order": "x"})).status_code == 422
    r = (await cal_client.get("/v1/calendar", params={"limit": 2})).json()
    assert [e["title"] for e in r["items"]] == ["E4", "E3"]


async def test_news_newest_first(cal_client):
    items = (await cal_client.get("/v1/news")).json()["items"]
    assert [n["title"] for n in items] == ["new", "nopub", "mid", "old"]


async def test_symbols_equity_history(client):
    syms = (await client.get("/v1/symbols")).json()
    by = {x["symbol"]: x for x in syms}
    assert by["EURUSD"]["tfs"] == ["M1"] and by["EURUSD"]["last_bar"] and by["EURUSD"]["last_quote"]
    assert by["XAUUSD"]["tfs"] == [] and by["XAUUSD"]["last_quote"]
    h = (await client.get("/v1/equity-history", params={"account_id": "a1"})).json()
    assert [p["equity"] for p in h] == [1, 2]  # tăng dần theo ts
    assert (await client.get("/v1/equity-history", params={"account_id": "a1", "limit": 1})).json()[0]["equity"] == 2
    frm = (NOW - timedelta(seconds=30)).isoformat()
    assert len((await client.get("/v1/equity-history", params={"account_id": "a1", "from": frm})).json()) == 1
    assert (await client.get("/v1/equity-history", params={"account_id": "x"})).json() == []
    assert (await client.get("/v1/equity-history")).status_code == 422
    assert (await client.get("/v1/equity-history", params={"account_id": "a;b"})).status_code == 422


async def test_system_fallback_from_redis_and_freshness():
    r = fr.FakeRedis(decode_responses=True)
    ev = make_event("quote", "market-collector", {"symbol": "EURUSD", "bid": 1, "ask": 2, "source": "t"})
    await r.xadd("md.quotes", {"e": ev.model_dump_json()})
    app = create_app(settings(), make_repo(), r)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as c:
        d = (await c.get("/v1/system")).json()
        assert d["services_source"] == "redis"
        assert d["services"][0]["name"] == "market-collector" and d["services"][0]["up"] is True
        q = next(s for s in d["streams"] if s["stream"] == "md.quotes")
        assert q["length"] == 1 and q["lag_seconds"] is not None and q["lag_seconds"] < 60
        assert next(s for s in d["streams"] if s["stream"] == "news.items")["length"] == 0
        src = {s["name"]: s for s in d["sources"]}
        assert src["bars"]["count_24h"] == 120 and src["bars"]["age_seconds"] < 120 + (datetime.now(timezone.utc) - NOW).total_seconds()   # NOW cố định lúc import: dung sai theo thời gian chạy cả bộ test (VPS tải cao)
        assert src["news"]["last_ts"] and d["version"]
        assert (await c.get("/v1/system", headers={"X-API-Key": "bad"})).status_code == 401


async def test_system_prometheus(monkeypatch):
    app = create_app(settings(prometheus_url="http://prom:9090"), make_repo(), fr.FakeRedis(decode_responses=True))
    import api_gateway.app as appmod

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"status": "success", "data": {"result": [
                {"metric": {"service": "storage-writer"}, "value": [1.7e9, "1"]},
                {"metric": {"service": "mt-bridge"}, "value": [1.7e9, "0"]}]}}).encode()

    seen = {}
    monkeypatch.setattr(appmod.urllib.request, "urlopen", lambda url, timeout: seen.setdefault("u", url) and _Resp())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as c:
        d = (await c.get("/v1/system")).json()
    assert d["services_source"] == "prometheus"
    assert {s["name"]: s["up"] for s in d["services"]} == {"mt-bridge": False, "storage-writer": True}
    assert seen["u"].startswith("http://prom:9090/api/v1/query?")
