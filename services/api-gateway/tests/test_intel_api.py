"""Endpoint /v1/intel/* tren du lieu tong hop (InMemoryRepo): suc manh tien te, heatmap, movers, tuong quan, nhip, tin, lich su lich, vi the."""
import math
import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api_gateway import intel_calc as C, intel_data as D
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
D0 = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
H = {"X-API-Key": "tok1"}


def walk(sym, n, start, drift=0.0, vol=0.01, tf="D1", seed=1, step=timedelta(days=1), end=None, vmul=1000.0):
    rnd = random.Random(seed)
    end = end or (D0 - timedelta(days=1) if tf == "D1" else NOW.replace(minute=0, second=0, microsecond=0))
    rows, px = [], start
    for i in range(n):
        ts = end - step * (n - 1 - i)
        o = px
        px = px * math.exp(drift + rnd.gauss(0, vol))
        rows.append({"symbol": sym, "tf": tf, "ts_open": ts, "o": o, "h": max(o, px) * 1.003, "l": min(o, px) * 0.997, "c": px, "v": vmul * (1 + (i % 5)), "source": "t"})
    return rows


def repo():
    bars = []
    # EUR manh (+), JPY yeu (USDJPY +), GBP, AUD nhe: D1 300 nen
    bars += walk("EURUSD", 300, 1.1, 0.001, 0.003, seed=1)
    bars += walk("GBPUSD", 300, 1.3, 0.0003, 0.003, seed=2)
    bars += walk("AUDUSD", 300, 0.65, -0.0002, 0.003, seed=3)
    bars += walk("NZDUSD", 300, 0.6, -0.0003, 0.003, seed=4)
    bars += walk("USDJPY", 300, 140.0, 0.0007, 0.003, seed=5)
    bars += walk("USDCHF", 300, 0.9, 0.0001, 0.003, seed=6)
    bars += walk("USDCAD", 300, 1.35, 0.0, 0.003, seed=7)
    bars += walk("US:SPY", 300, 450.0, 0.0006, 0.008, seed=8)
    bars += walk("US:QQQ", 300, 380.0, 0.0008, 0.010, seed=9)
    bars += walk("US:XLK", 300, 200.0, 0.0008, 0.010, seed=10)
    bars += walk("CRYPTO:BTCUSDT", 300, 60000.0, 0.001, 0.03, seed=11)
    bars += walk("CRYPTO:ETHUSDT", 300, 3000.0, 0.001, 0.035, seed=12)
    bars += walk("VN:FPT", 300, 100000.0, 0.0005, 0.012, seed=13)
    bars += walk("FRED:DGS10", 30, 4.2, 0.0, 0.005, seed=14)
    bars += walk("EURUSD", 60, 1.4, 0.0005, 0.001, tf="H1", seed=15, step=timedelta(hours=1))
    bars += walk("USDJPY", 60, 150.0, 0.0001, 0.001, tf="H1", seed=16, step=timedelta(hours=1))
    news = [
        {"url": "https://x.test/a", "title": "Fed giữ nguyên lãi suất, Powell nói lạm phát vẫn cao", "summary": "FOMC họp tháng 10", "published_at": NOW - timedelta(minutes=30),
         "lang": "vi", "symbols": ["EURUSD", "US:SPY"], "sentiment": -0.8, "source": "s"},
        {"url": "https://x.test/b", "title": "Fed họp: lạm phát và lãi suất chi phối thị trường", "summary": "Tin tương tự", "published_at": NOW - timedelta(hours=2),
         "lang": "vi", "symbols": ["US:SPY"], "sentiment": 0.1, "source": "s"},
        {"url": "https://x.test/c", "title": "Bitcoin vượt đỉnh mới", "summary": None, "published_at": NOW - timedelta(hours=5), "lang": "vi",
         "symbols": ["CRYPTO:BTCUSDT"], "sentiment": 0.9, "source": "s"},
        {"url": "https://x.test/e", "title": "Số liệu mới công bố", "summary": None, "published_at": NOW - timedelta(minutes=50), "lang": "vi", "symbols": [],
         "sentiment": 0.0, "sentiment_label": "neutral", "topics": ["inflation", "jobs"], "importance": "high", "source": "s"},
        {"url": "https://x.test/d", "title": "Tin cũ về bất động sản", "summary": None, "published_at": NOW - timedelta(days=40), "lang": "vi", "symbols": [], "sentiment": 0.0, "source": "s"},
    ]
    cal = [{"event_id": f"e{i}", "source": "x", "country": "US", "title": "CPI m/m", "impact": "high", "ts": NOW - timedelta(days=30 * (6 - i)),
            "forecast": f"{0.2 + i / 100}%", "previous": f"{0.1 + i / 100}%", "actual": (f"{0.3 + i / 100}%" if i < 5 else None), "extra": None} for i in range(7)]
    pos = [{"expert_id": "CFTC:1", "source": "cftc", "symbol": "EURUSD", "as_of": NOW - timedelta(days=7 * (12 - i)), "net_volume": float(i * 1000 - 3000), "avg_price": None} for i in range(12)]
    quotes = [{"symbol": "CRYPTO:BTCUSDT", "ts": NOW - timedelta(minutes=1), "bid": 66000.0, "ask": 66010.0, "source": "q"}]
    return InMemoryRepo(bars=bars, news_items=news, calendar_events=cal, expert_positions=pos, quotes=quotes)


@pytest.fixture()
def client():
    D.clear_cache()
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=repo(), redis=object())
    with TestClient(app) as c:
        yield c


def get(c, path, **params):
    r = c.get(f"/v1/intel{path}", params=params, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_strength_d1_and_h1_partial(client):
    d1 = get(client, "/strength", tf="D1", window=20)
    assert d1["coverage"] == "8/8" and {c["ccy"] for c in d1["currencies"]} == set(C.CCYS)
    assert [c["rank"] for c in d1["currencies"]] == list(range(1, 9))
    assert abs(sum(c["score"] for c in d1["currencies"])) < 1e-3          # tong diem = 0 (tuong doi so voi ro)
    assert len(d1["history_ts"]) == 21 and all(len(c["history"]) == 21 for c in d1["currencies"])
    h1 = get(client, "/strength", tf="H1", window=24)
    assert h1["coverage"] == "3/8" and set(h1["pairs"]) == {"EURUSD", "USDJPY"} and "GBPUSD" in h1["missing"]
    assert h1["currencies"][0]["ccy"] == "EUR"                             # EURUSD H1 tang manh
    bad = client.get("/v1/intel/strength", params={"tf": "M1"}, headers=H)
    assert bad.status_code == 422


def test_fx_matrix(client):
    j = get(client, "/fx")
    assert len(j["rows"]) == 28 and j["periods"] == ["1h", "4h", "1d", "1w", "1m"]
    eur = next(r for r in j["rows"] if r["pair"] == "EURUSD")
    assert eur["1d"] is not None and eur["1h"] is not None and eur["4h"] is None
    gbp = next(r for r in j["rows"] if r["pair"] == "EURGBP")
    assert gbp["1h"] is None and gbp["1d"] is not None                       # cheo suy ra tu 2 chan
    m = j["cross"]["matrix"]
    assert j["cross"]["ccys"][0] == "USD" and m[0][0] is None
    i = j["cross"]["ccys"].index("EUR")
    assert m[i][0] > 0 and abs(m[i][0] * m[0][i] - 1) < 1e-4                # EUR/USD * USD/EUR = 1


def test_heatmap_and_groups(client):
    j = get(client, "/heatmap", group="crypto", period="1d")
    assert {i["label"] for i in j["items"]} == {"BTC", "ETH"} and j["size_basis"] == "turnover_20d"
    btc = next(i for i in j["items"] if i["label"] == "BTC")
    assert btc["last"] == pytest.approx(66005.0)                            # quote moi ghi de dong cua
    assert get(client, "/heatmap", group="vn", period="1m")["count"] == 1
    assert get(client, "/heatmap", group="bond")["count"] == 0               # FRED bi loai
    assert client.get("/v1/intel/heatmap", params={"group": "zzz"}, headers=H).status_code == 422


def test_movers(client):
    j = get(client, "/movers", group="all", period="1d", limit=5)
    assert j["count"] > 5 and len(j["gainers"]) <= 5 and all(g["change_pct"] > 0 for g in j["gainers"])
    assert j["gainers"] == sorted(j["gainers"], key=lambda r: -r["change_pct"])
    assert all(r["from_high"] <= 0.01 for r in j["near_high"]) and "new_high" in j
    h = get(client, "/movers", group="forex", period="1h")
    assert h["covered"] == 2 and {r["symbol"] for r in h["gainers"] + h["losers"]} <= {"EURUSD", "USDJPY"}


def test_stats_corr_dist(client):
    s = get(client, "/stats", group="all", benchmark="US:SPY", window=60)
    spy = next(i for i in s["items"] if i["symbol"] == "US:SPY")
    assert spy["beta"] is None and spy["atr_pct"] > 0 and 0 <= spy["vol_rank"] <= 100
    qqq = next(i for i in s["items"] if i["symbol"] == "US:QQQ")
    assert qqq["beta"] is not None and qqq["beta_n"] >= 20
    c = get(client, "/correlation", symbols="US:SPY,US:QQQ,US:XLK,CRYPTO:BTCUSDT,NOPE", window=120)
    assert c["symbols"] == ["US:SPY", "US:QQQ", "US:XLK", "CRYPTO:BTCUSDT"] and c["missing"] == ["NOPE"]
    n = len(c["symbols"])
    assert all(c["matrix"][i][i] == 1.0 for i in range(n)) and c["matrix"][0][1] == c["matrix"][1][0]
    sp = get(client, "/correlation", symbols="US:SPY,US:QQQ", method="spearman")
    assert sp["method"] == "spearman"
    r = get(client, "/correlation/rolling", a="US:SPY", b="US:QQQ", window=30, span=100)
    assert len(r["series"]) > 50 and -1 <= r["latest"] <= 1
    d = get(client, "/distribution", symbol="CRYPTO:BTCUSDT", window=250)
    assert d["n"] == 250 and sum(b["n"] for b in d["bins"]) == 250 and d["var95_pct"] > 0 and d["es95_pct"] >= d["var95_pct"]
    assert client.get("/v1/intel/distribution", params={"symbol": "NOPE"}, headers=H).status_code == 404
    assert client.get("/v1/intel/correlation", params={"symbols": "A B"}, headers=H).status_code == 422


def test_pulse(client):
    j = get(client, "/pulse")
    assert {c["class"] for c in j["classes"]} >= {"forex", "crypto", "stock_vn"}
    assert 0 <= j["volatility"]["index"] <= 100 and j["volatility"]["items"]
    assert j["news"]["n_24h"] == 4 and j["news"]["neg"] == 1 and j["news"]["pos"] == 1
    assert 0 <= j["appetite"]["score"] <= 100 and "tham khảo" in j["disclaimer"]


def test_news_terminal(client):
    j = get(client, "/news", hours=48)
    assert j["count"] == 4 and j["items"][0]["title"].startswith("Fed giữ") and j["items"][0]["id"] and j["items"][0]["importance"] >= 2
    assert "monetary_policy" in j["items"][0]["topics"]
    q = get(client, "/news", q="lãi suất", hours=48)
    assert {i["title"][:3] for i in q["items"]} == {"Fed"}
    assert get(client, "/news", symbol="CRYPTO:BTCUSDT", hours=48)["count"] == 1
    assert get(client, "/news", sentiment="neg", hours=48)["count"] == 1
    assert get(client, "/news", topic="crypto", hours=48)["count"] == 1
    nlp = next(i for i in get(client, "/news", hours=48)["items"] if i["url"].endswith("/e"))   # topics/importance do nlp gan san duoc ton trong
    assert nlp["topics"] == ["inflation", "jobs"] and nlp["importance"] == 3 and nlp["sentiment_label"] == "neutral"
    assert {i["url"] for i in get(client, "/news", topic="jobs", hours=48)["items"]} == {"https://x.test/e"}
    assert get(client, "/news", min_importance=3, hours=48)["count"] >= 1
    page = get(client, "/news", hours=48, limit=2)
    assert page["next_before"] and get(client, "/news", hours=48, limit=2, before=page["next_before"])["count"] == 2
    t = get(client, "/news/topics", hours=24)
    assert t["total"] == 4 and any(x["id"] == "monetary_policy" and x["n"] == 2 for x in t["topics"])
    rel = get(client, "/news/related", url="https://x.test/a")
    assert rel["related"][0]["url"] == "https://x.test/b" and {s["symbol"] for s in rel["symbols"]} == {"EURUSD", "US:SPY"}
    assert client.get("/v1/intel/news/related", params={"url": "https://nope.test/zz"}, headers=H).status_code == 404
    assert client.get("/v1/intel/news", params={"topic": "bogus"}, headers=H).status_code == 422


def test_calendar_history_and_cot(client):
    ind = get(client, "/calendar/indicators")
    assert ind["items"][0]["title"] == "CPI m/m" and ind["items"][0]["n"] == 7
    h = get(client, "/calendar/history", title="CPI m/m", country="US")
    assert h["count"] == 7 and h["stats"]["n_actual"] == 5 and h["items"][0]["ts"] < h["items"][-1]["ts"]
    assert h["items"][0]["surprise"] == pytest.approx(0.1) and h["stats"]["beat_pct"] == 100.0
    assert h["items"][5]["actual"] is None and h["items"][5]["actual_from_next"] == pytest.approx(0.16)
    assert client.get("/v1/intel/calendar/history", params={"title": "Khong co"}, headers=H).status_code == 404
    cot = get(client, "/cot")
    e = cot["items"][0]
    assert e["symbol"] == "EURUSD" and e["n"] == 12 and e["percentile"] == 100.0 and e["change"] == 1000.0 and "tham khảo" in cot["note"]


def test_auth_required_and_client_role_allowed(client):
    assert client.get("/v1/intel/pulse").status_code == 401


def test_calc_units():
    assert C.pearson([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 12]) == pytest.approx(1.0)
    assert C.pearson([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert C.percentile_rank([1, 2, 3, 4], 3) == 75.0
    assert C._rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ser = {"EURUSD": [(t0 + timedelta(days=i), 1, 1, 1, 1.0 * (1.01 ** i), 0) for i in range(5)]}
    r = C.strength(ser, 4)
    assert [c["ccy"] for c in r["currencies"]] == ["EUR", "USD"] and r["currencies"][0]["score"] == pytest.approx(-r["currencies"][1]["score"])
