"""Fixture giả của api-gateway (httpx.MockTransport): không cần mạng/Redis thật."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from reporter.collect import Gateway
from reporter.config import Settings

NOW = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)  # = 07:00 giờ VN
XSS = '<script>alert("x")</script> & "q"'


def _bars(sym, base, n=40, src="yahoo_daily"):
    items = []
    for i in range(n):
        ts = (NOW - timedelta(days=i + 1)).replace(hour=0).strftime("%Y-%m-%dT00:00:00Z")
        c = base * (1 + 0.002 * (n - i) * (1 if i % 2 else -0.5))
        items.append({"symbol": sym, "tf": "D1", "ts_open": ts, "o": c, "h": c, "l": c, "c": c, "v": 1.0, "source": src})
    return {"items": items, "limit": n, "offset": 0, "count": n}


def routes(cfg: Settings, overrides: dict | None = None) -> dict:
    ts = lambda h: (NOW + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    r = {
        "/v1/quotes/latest": [],
        "/v1/news": {"items": [
            {"url": "u1", "title": XSS, "summary": "", "published_at": ts(-3), "source": "cafef", "symbols": ["VN:VNM"], "sentiment": -0.9},
            {"url": "u2", "title": "Giá vàng tăng mạnh", "summary": "", "published_at": ts(-5), "source": "x", "symbols": ["XAUUSD", "VN:VNM"], "sentiment": 0.8},
            {"url": "u3", "title": "Tin trung lập", "summary": "", "published_at": ts(-6), "source": "x", "symbols": ["XAUUSD"], "sentiment": 0.05},
        ]},
        "/v1/calendar": {"items": [
            {"event_id": "1", "country": "US", "title": "Core CPI y/y", "impact": "high", "ts": ts(12), "forecast": "2.5%", "previous": "2.6%"},
            {"event_id": "2", "country": "EU", "title": "ECB Speaks", "impact": "med", "ts": ts(3), "forecast": None, "previous": None}]},
        "/v1/expert-signals": {"items": [{"expert_id": "e1", "symbol": "EURUSD", "side": "buy", "status": "open"},
                                         {"expert_id": "e2", "symbol": "EURUSD", "side": "sell", "status": "open"},
                                         {"expert_id": "e3", "symbol": "EURUSD", "side": "buy", "status": "open"}]},
        "/v1/accounts": [{"account_id": "demo-mt4-01", "platform": "mt4", "equity": 0.0, "balance": 0.0, "margin": 0.0, "positions": []}],
        "/v1/analytics/overview": {"items": [{"symbol": "EURUSD", "tf": "D1", "heat": 55, "trend": "up", "rsi": 61.2, "adx": 28, "bias": 40}]},
        "/v1/system": {"services": [{"name": "api-gateway", "up": True}, {"name": "mt-bridge", "up": False}],
                       "streams": [{"stream": "alerts.out", "length": 5, "last_event_at": "2026-10-11T17:04:21Z"}],
                       "sources": [{"name": "bars", "age_seconds": 7200, "count_24h": 10}]},
        "/v1/data-sources": {"market": [{"provider": "dukascopy", "state": "active", "kind": "fx", "last_ok": ts(-1)},
                                        {"provider": "twelvedata", "state": "needs_key", "kind": "multi", "last_ok": None}],
                             "reconcile": {"summary": {"ok": 3}}},
        "/v1/alerts": {"items": [{"id": 1, "ts": ts(-2), "level": "crit", "title": "Sự cố <b>nặng</b>"},
                                 {"id": 2, "ts": ts(-30), "level": "warn", "title": "quá cũ"}]},
        "/v1/paper/overview": {"cycle": {"accounts": {"old": {"deprecated": True}}}, "strategies": []},
        "/v1/paper/accounts": {"items": [
            {"account_id": "acc1", "name": "Chiến lược 1", "strategy": "slow", "base_ccy": "USD", "equity": 10100.0, "total_return": 0.01,
             "drawdown": -0.002, "benchmark_id": "bm", "replay": False, "status": "active"},
            {"account_id": "old", "name": "cũ", "replay": False}]},
        "/v1/paper/accounts/acc1/stats": {"reliable": False, "max_drawdown": -0.004, "current_drawdown": -0.002, "sharpe": 1.2, "days": 5},
        "/v1/paper/accounts/acc1/equity": {"series": [{"ts": (NOW - timedelta(days=d)).isoformat(), "equity": 10000 + 20 * (8 - d), "index": 100 + 0.2 * (8 - d)} for d in range(8, -1, -1)],
                                           "benchmark": [{"ts": (NOW - timedelta(days=d)).isoformat(), "equity": 1, "index": 100 + 0.1 * (8 - d)} for d in range(8, -1, -1)]},
    }
    for _, sym, _l in cfg.instruments:
        r["/v1/bars?" + sym] = _bars(sym, 100.0 if ":" in sym or sym == "XAUUSD" else 1.1)
    r["/v1/briefing/latest"] = {"items": [{
        "id": "b1", "edition": "morning", "scope": "vn", "status": "llm", "model": "test-model", "generated_at": ts(-1), "headline": "VN-Index giảm về 1.730 điểm",
        "body": {"points": [{"text": "VN-Index giảm 12,5 điểm xuống 1.730 điểm.", "cites": [1]}, {"text": "Khối ngoại bán ròng <b>350</b> tỷ đồng.", "cites": [2, 1]}],
                 "mood": {"text": "Tâm lý tin tức 24 giờ qua trung tính."}, "watch": [{"text": "19:30 12/10 — US CPI y/y", "cites": [1]}]},
        "context": {"items": [{"n": 1, "title": "VN-Index giảm 12,5 điểm"}, {"n": 2, "title": "Khối ngoại bán ròng 350 tỷ"}]}}]}
    r.update(overrides or {})
    return r


def make_gateway(cfg: Settings, overrides: dict | None = None, fail: set | None = None) -> Gateway:
    table = routes(cfg, overrides)
    fail = fail or set()

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        key = path + "?" + req.url.params["symbol"] if path == "/v1/bars" else path
        if any(path.startswith(f) for f in fail) or key not in table:
            return httpx.Response(404 if key not in table else 500, json={"detail": "x"})
        return httpx.Response(200, json=table[key])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://gw")
    return Gateway(cfg, client)


@pytest.fixture
def cfg(tmp_path):
    return Settings(data_dir=tmp_path, api_key="k", tick_seconds=0.01)
