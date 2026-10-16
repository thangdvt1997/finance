"""Endpoint /v1/analytics/* trên snapshot giả (hợp đồng kind/key xem services/analytics/README.md)."""
import asyncio
from datetime import datetime, timezone

import fakeredis.aioredis as fr
import httpx
import pytest

from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
H = {"X-API-Key": "tok1"}


def st(code, label="x", tone="neutral"):
    return {"code": code, "label": label, "tone": tone, "rule": "r", "group": "g"}


def summ(symbol, tf, heat, bias, trend, momentum, vol, rsi, adx, states=(), atr_p=50.0):
    return {"symbol": symbol, "tf": tf, "bar_ts": NOW.isoformat(), "bars": 300, "close": 1.1, "heat": heat, "bias": bias,
            "trend": trend, "momentum": momentum, "volatility": vol, "squeeze": vol == "squeeze", "atr_percentile": atr_p,
            "rsi": rsi, "adx": adx, "atr_pct": 0.2, "macd_hist": 0.1, "stoch_k": 50, "bb_pctb": 0.5, "ema200_dist_pct": 1.0,
            "states": [st(c) for c in states], "disclaimer": "Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư."}


def row(kind, key, payload):
    return {"kind": kind, "key": key, "ts": NOW, "payload": payload, "updated_at": NOW}


def make_repo():
    S = [summ("EURUSD", "H1", 70, 60, "up", "bullish", "high", 62, 30, ["above_ema200", "trend_strong"], 85),
         summ("EURUSD", "D1", 40, 20, "side", "neutral", "normal", 51, 15, ["range_bound"]),
         summ("XAUUSD", "H1", 90, -80, "down", "oversold", "squeeze", 25, 40, ["below_ema200", "squeeze"], 10),
         summ("VN:VNM", "H1", 20, 0, "side", "neutral", "low", 49, 12, ["range_bound"], 5)]
    rows = [row("summary", f"{s['symbol']}:{s['tf']}", s) for s in S]
    rows += [row("detail", f"{s['symbol']}:{s['tf']}", {**s, "indicators": {"rsi": s["rsi"]}, "pivot": {"p": 1.0},
                                                        "series": {"t": [1, 2], "rsi": [50, 51]}}) for s in S]
    rows.append(row("correlation", "D1", {"symbols": ["EURUSD", "GBPUSD", "XAUUSD"], "window": 30, "as_of": "2026-01-01",
                                          "matrix": [[1, 0.9, -0.2], [0.9, 1, -0.5], [-0.2, -0.5, 1]],
                                          "matrix_prev": [[1, -0.1, 0.1], [-0.1, 1, 0.1], [0.1, 0.1, 1]]}))
    rows.append(row("sessions", "EURUSD", {"symbol": "EURUSD", "sessions": {"tokyo": {"avg_range_pct": 0.2}}, "hourly": []}))
    rows.append(row("sessions", "XAUUSD", {"symbol": "XAUUSD", "sessions": {}, "hourly": []}))
    return InMemoryRepo(analytics_snapshots=rows)


@pytest.fixture
async def c():
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, cors_origins=(), max_page_size=50),
                     make_repo(), fr.FakeRedis(decode_responses=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as cl:
        yield cl


async def test_auth_required():
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), make_repo(), None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as cl:
        assert (await cl.get("/v1/analytics/overview")).status_code == 401


async def test_overview(c):
    d = (await c.get("/v1/analytics/overview")).json()
    assert d["symbols"] == ["EURUSD", "VN:VNM", "XAUUSD"] and d["tfs"] == ["H1", "D1"]
    assert len(d["items"]) == 4 and "khuyến nghị" in d["disclaimer"]
    h1 = d["summary"]["by_tf"]["H1"]
    assert h1 == {"n": 3, "up": 1, "down": 1, "side": 1, "overbought": 0, "oversold": 1, "squeeze": 1, "high_vol": 1}
    assert d["summary"]["top_heat"][0]["symbol"] == "XAUUSD"
    assert d["age_seconds"] is not None and d["age_seconds"] < 60


async def test_empty_states():
    app = create_app(GatewaySettings(api_tokens=("tok1",)), InMemoryRepo(), None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H) as cl:
        d = (await cl.get("/v1/analytics/overview")).json()
        assert d["items"] == [] and d["updated_at"] is None
        assert (await cl.get("/v1/analytics/symbol/EURUSD")).json()["available"] is False
        assert (await cl.get("/v1/analytics/correlation")).json()["symbols"] == []
        assert (await cl.get("/v1/analytics/sessions")).json()["items"] == []


async def test_symbol_detail(c):
    d = (await c.get("/v1/analytics/symbol/EURUSD")).json()
    assert list(d["tfs"]) == ["H1", "D1"] and d["tfs"]["H1"]["series"]["t"] == [1, 2]
    assert d["sessions"]["symbol"] == "EURUSD"
    d = (await c.get("/v1/analytics/symbol/EURUSD", params={"tf": "D1"})).json()
    assert list(d["tfs"]) == ["D1"]
    assert (await c.get("/v1/analytics/symbol/VN:VNM")).json()["symbol"] == "VN:VNM"
    r = await c.get("/v1/analytics/symbol/NOPE")
    assert r.status_code == 200 and r.json()["available"] is False and r.json()["tfs"] == {}
    assert (await c.get("/v1/analytics/symbol/EURUSD", params={"tf": "M2"})).status_code == 422


async def test_screener_filters_and_sort(c):
    r = (await c.get("/v1/analytics/screener", params={"tf": "H1"})).json()
    assert [i["symbol"] for i in r["items"]] == ["XAUUSD", "EURUSD", "VN:VNM"] and r["total"] == 3   # heat giảm dần
    r = (await c.get("/v1/analytics/screener", params={"tf": "H1", "sort": "heat", "order": "asc"})).json()
    assert r["items"][0]["symbol"] == "VN:VNM"
    r = (await c.get("/v1/analytics/screener", params={"trend": "up,down"})).json()
    assert {i["symbol"] for i in r["items"]} == {"EURUSD", "XAUUSD"}
    r = (await c.get("/v1/analytics/screener", params={"state": "below_ema200,squeeze"})).json()
    assert [i["symbol"] for i in r["items"]] == ["XAUUSD"]
    r = (await c.get("/v1/analytics/screener", params={"state": "above_ema200,squeeze"})).json()
    assert r["items"] == []
    r = (await c.get("/v1/analytics/screener", params={"rsi_max": 30})).json()
    assert [i["symbol"] for i in r["items"]] == ["XAUUSD"]
    r = (await c.get("/v1/analytics/screener", params={"adx_min": 35, "heat_min": 80})).json()
    assert [i["symbol"] for i in r["items"]] == ["XAUUSD"]
    r = (await c.get("/v1/analytics/screener", params={"atr_pctile_min": 80})).json()
    assert [i["symbol"] for i in r["items"]] == ["EURUSD"]
    r = (await c.get("/v1/analytics/screener", params={"bias_max": -50})).json()
    assert [i["symbol"] for i in r["items"]] == ["XAUUSD"]
    r = (await c.get("/v1/analytics/screener", params={"q": "vn:", "limit": 1})).json()
    assert r["count"] == 1 and r["items"][0]["symbol"] == "VN:VNM"
    r = (await c.get("/v1/analytics/screener", params={"tf": "D1"})).json()
    assert r["total"] == 1


async def test_screener_validation(c):
    for bad in ({"trend": "sideways"}, {"momentum": "x"}, {"volatility": "extreme"}, {"sort": "price;drop"}, {"order": "up"},
                {"tf": "M2"}, {"state": "Bad Code"}, {"limit": 0}, {"limit": 9999}):
        assert (await c.get("/v1/analytics/screener", params=bad)).status_code == 422, bad


async def test_correlation_and_flips(c):
    d = (await c.get("/v1/analytics/correlation")).json()
    assert d["symbols"] == ["EURUSD", "GBPUSD", "XAUUSD"] and d["window"] == 30
    assert d["top_pairs"][0]["a"] == "EURUSD" and d["top_pairs"][0]["b"] == "GBPUSD"
    assert [(f["a"], f["b"]) for f in d["flips"]] == [("EURUSD", "GBPUSD")] and d["flips"][0]["delta"] == 1.0
    d = (await c.get("/v1/analytics/correlation", params={"min_delta": 1.5})).json()
    assert d["flips"] == []
    assert (await c.get("/v1/analytics/correlation", params={"tf": "H4"})).json()["symbols"] == []


async def test_sessions(c):
    assert len((await c.get("/v1/analytics/sessions")).json()["items"]) == 2
    d = (await c.get("/v1/analytics/sessions", params={"symbol": "EURUSD"})).json()
    assert [i["symbol"] for i in d["items"]] == ["EURUSD"]


def test_ws_allows_analytics_stream():
    from fastapi.testclient import TestClient
    class _IdleRedis:  # fakeredis + BLOCK có thể treo khi hủy task; xread rỗng, có thể hủy ngay
        async def xread(self, streams, count=None, block=None):
            await asyncio.sleep(0.05)
            return []

    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), make_repo(), _IdleRedis())
    with TestClient(app) as t, t.websocket_connect("/v1/stream?streams=analytics.signals", headers=H) as ws:
        assert ws.receive_json() == {"type": "ready", "streams": ["analytics.signals"]}
