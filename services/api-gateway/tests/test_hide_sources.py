"""UI_NO_SOURCES: HIDE_SOURCES (mac dinh true) -> phan hoi /v1/* khong chua ten nguon."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_gateway import datasources_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
H = {"X-API-Key": "tok1"}
BANNED = ("dukascopy", "yahoo", "frankfurter", "faireconomy", "vietstock", "reuters", "actionforex", "cafef")


def repo():
    ts = NOW - timedelta(minutes=1)
    return InMemoryRepo(
        bars=[{"symbol": "EURUSD", "tf": "D1", "ts_open": ts, "o": 1, "h": 1, "l": 1, "c": 1.1, "v": 1, "source": "yahoo_daily"},
              {"symbol": "EURUSD", "tf": "D1", "ts_open": ts, "o": 1, "h": 1, "l": 1, "c": 1.2, "v": 1, "source": "dukascopy"}],
        quotes=[{"symbol": "EURUSD", "ts": NOW, "bid": 1.1, "ask": 1.2, "source": "dukascopy"}],
        news_items=[{"url": "https://www.reuters.com/a", "title": "Reuters - Vàng tăng mạnh", "summary": "Nguồn: vietstock_cophieu. Giá vàng tăng.",
                     "published_at": NOW, "source": "vietstock_cophieu", "symbols": ["XAUUSD"]}],
        calendar_events=[{"event_id": "1", "source": "faireconomy", "title": "NFP", "impact": "high", "ts": NOW + timedelta(hours=3),
                          "extra": {"forecast_source": "faireconomy", "group": "nfp"}}],
        experts=[{"expert_id": "e1", "source": "actionforex", "display_name": "ActionForex Weekly Outlook"}],
        alerts=[{"id": 1, "ts": NOW, "level": "warn", "title": "dukascopy lỗi lấy dữ liệu GBPUSD M1", "body": "Nguồn: dukascopy",
                 "tags": ["dukascopy", "x"]}])


def client(hide=True):
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, hide_sources=hide), repo=repo(), redis=object()))


def test_hidden_by_default_no_source_names_anywhere():
    assert GatewaySettings().hide_sources is True
    with client() as c:
        for url in ("/v1/bars?symbol=EURUSD&tf=D1", "/v1/quotes/latest", "/v1/news", "/v1/calendar?from=2000-01-01T00:00:00Z",
                    "/v1/experts", "/v1/alerts"):
            r = c.get(url, headers=H)
            assert r.status_code == 200, (url, r.text)
            low = r.text.lower()
            for w in BANNED:
                if w == "reuters" and url == "/v1/news":
                    continue  # url bai viet la khoa dinh danh (giu nguyen, UI khong hien thi)
                assert w not in low, (url, w, r.text)
            assert '"source"' not in low, url


def test_content_preserved_and_bars_deduped_with_priority():
    with client() as c:
        bars = c.get("/v1/bars?symbol=EURUSD&tf=D1", headers=H).json()["items"]
        assert len(bars) == 1 and bars[0]["c"] == 1.2 and "source" not in bars[0]  # ưu tiên dukascopy nhưng không lộ tên
        n = c.get("/v1/news", headers=H).json()["items"][0]
        assert n["title"] == "Vàng tăng mạnh" and n["summary"] == "Giá vàng tăng." and n["symbols"] == ["XAUUSD"]
        ev = c.get("/v1/calendar?from=2000-01-01T00:00:00Z", headers=H).json()["items"][0]
        assert ev["title"] == "NFP" and ev["extra"] == {"group": "nfp"}
        a = c.get("/v1/alerts", headers=H).json()["items"][0]
        assert a["title"] == "dữ liệu giá GBPUSD M1: lỗi cập nhật" and "dukascopy" not in json.dumps(a).lower()


def test_hide_sources_false_returns_raw():
    with client(hide=False) as c:
        assert c.get("/v1/quotes/latest", headers=H).json()[0]["source"] == "dukascopy"
        assert len(c.get("/v1/bars?symbol=EURUSD&tf=D1", headers=H).json()["items"]) == 2


def test_env_flag(monkeypatch):
    monkeypatch.setenv("HIDE_SOURCES", "false")
    assert GatewaySettings().hide_sources is False
    monkeypatch.setenv("HIDE_SOURCES", "true")
    assert GatewaySettings().hide_sources is True


def test_data_sources_anonymous_when_hidden(monkeypatch):
    def fake(url):
        if url.endswith("/providers") and "market" in url:
            return {"providers": [{"provider": "oanda", "state": "needs_key", "kind": "fx", "needs_env": ["OANDA_PRACTICE_TOKEN"], "last_ok": None},
                                  {"provider": "dukascopy", "state": "active", "kind": "fx", "last_ok": "2026-10-12T00:00:00"}]}
        if url.endswith("/reconcile"):
            return {"results": [{"pair": "EURUSD", "source": "oanda", "status": "ok"}], "summary": {"ok": 1}}
        return {"providers": [{"provider": "vietstock_cophieu", "state": "active"}]}
    monkeypatch.setattr(datasources_routes, "_get", fake)
    with client() as c:
        raw = c.get("/v1/data-sources", headers=H).text
        d = c.get("/v1/data-sources", headers=H).json()
    low = raw.lower()
    assert not any(w in low for w in ("oanda", "dukascopy", "vietstock", "needs_env"))
    assert [m["state"] for m in d["market"]] == ["needs_key", "active"] and d["market"][0]["provider"].startswith("Luồng giá")
    assert d["reconcile"]["summary"] == {"ok": 1} and d["reconcile"]["results"][0]["source"] == "luồng giá"
