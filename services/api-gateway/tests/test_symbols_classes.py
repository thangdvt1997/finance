from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo
from api_gateway.symbols_view import price_fields

NOW = datetime.now(timezone.utc)
D = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
H = {"X-API-Key": "tok1"}
BTC = "CRYPTO:BTCUSDT"


def bar(sym, days_ago, c, tf="D1"):
    return {"symbol": sym, "tf": tf, "ts_open": D - timedelta(days=days_ago), "o": c, "h": c, "l": c, "c": c, "v": 1, "source": "t"}


def client():
    bars = [bar(s, d, c) for s, rows in {"US:SPY": [(1, 500.0), (2, 495.0)], "VN:VNM": [(1, 60000.0), (2, 59000.0)],
                                         "US:GLD": [(1, 250.0), (2, 251.0)], "US:USO": [(3, 70.0), (4, 71.0)],
                                         BTC: [(1, 80000.0), (2, 79000.0)], "EURUSD": [(1, 1.1), (2, 1.09)],
                                         "NEW:THING": [(1, 1.0)]}.items() for d, c in rows]
    bars.append(bar(BTC, 0, 80500.0, tf="H1"))
    quotes = [{"symbol": BTC, "ts": NOW - timedelta(seconds=20), "bid": 83999.0, "ask": 84001.0, "source": "crypto_ccxt"},
              {"symbol": "EURUSD", "ts": NOW - timedelta(days=3), "bid": 1.2, "ask": 1.2, "source": "old"}]
    repo = InMemoryRepo(bars=bars, quotes=quotes)
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False), repo=repo, redis=object()))


def test_symbols_have_class_and_metadata():
    with client() as c:
        r = c.get("/v1/symbols", headers=H)
        assert r.status_code == 200
        by = {x["symbol"]: x for x in r.json()}
        assert by[BTC]["class"] == "crypto" and by[BTC]["session"] == "crypto_24x7" and by[BTC]["session_open"] is True
        assert by[BTC]["name"] == "Bitcoin" and by[BTC]["quote_currency"] == "USDT" and by[BTC]["precision"] == 2
        assert by["EURUSD"]["class"] == "forex" and by["EURUSD"]["precision"] == 5 and by["EURUSD"]["session"] == "fx_24x5"
        assert by["US:GLD"]["class"] == "metal" and by["US:USO"]["class"] == "commodity" and by["US:SPY"]["class"] == "index"
        assert by["VN:VNM"]["class"] == "stock_vn" and by["VN:VNM"]["quote_currency"] == "VND" and by["VN:VNM"]["precision"] == 0
        assert by["NEW:THING"]["class"] == "other" and by["NEW:THING"]["registered"] is False
        for k in ("symbol", "tfs", "last_bar", "last_quote"):                      # truong cu van con
            assert k in by["EURUSD"]
        assert by[BTC]["tfs"] == ["H1", "D1"] or set(by[BTC]["tfs"]) == {"H1", "D1"}


def test_price_and_change_rules():
    with client() as c:
        by = {x["symbol"]: x for x in c.get("/v1/symbols", headers=H).json()}
        b = by[BTC]                                    # quote moi -> last = mid, tham chieu = dong cua D1 ngay UTC truoc
        assert b["price_source"] == "quote" and b["last"] == 84000.0 and b["prev_close"] == 80000.0
        assert abs(b["change_pct"] - 5.0) < 1e-6
        s = by["US:SPY"]                               # khong co quote -> 2 nen D1 gan nhat
        assert s["price_source"] == "d1" and s["last"] == 500.0 and s["prev_close"] == 495.0 and 1.0 < s["change_pct"] < 1.02
        assert by["EURUSD"]["price_source"] == "d1" and by["EURUSD"]["last"] == 1.1      # quote 3 ngay tuoi bi bo qua
        assert by["NEW:THING"]["change_pct"] is None and by["NEW:THING"]["last"] == 1.0   # chi 1 nen


def test_class_filter_and_prices_off():
    with client() as c:
        r = c.get("/v1/symbols", params={"class": "crypto"}, headers=H).json()
        assert [x["symbol"] for x in r] == [BTC]
        r = c.get("/v1/symbols", params={"prices": "false"}, headers=H).json()
        assert all(x["last"] is None and x["change_pct"] is None for x in r) and len(r) == 7
        assert c.get("/v1/symbols", params={"class": "BAD CLASS!"}, headers=H).status_code == 422
        assert c.get("/v1/symbols").status_code == 401


def test_classes_endpoint_counts_and_order():
    with client() as c:
        r = c.get("/v1/symbols/classes", headers=H).json()
        order = [x["class"] for x in r]
        assert order == ["forex", "crypto", "metal", "commodity", "index", "etf", "stock_us", "stock_vn", "bond", "other"]
        n = {x["class"]: x["count"] for x in r}
        assert n["forex"] == 1 and n["crypto"] == 1 and n["metal"] == 1 and n["commodity"] == 1 and n["index"] == 1
        assert n["stock_vn"] == 1 and n["bond"] == 0 and n["other"] == 1
        crypto = next(x for x in r if x["class"] == "crypto")
        assert crypto["name"] and crypto["name_en"] == "Crypto" and crypto["session"] == "crypto_24x7"
        assert crypto["groups"] == [{"group": "Vốn hoá lớn", "count": 1}]


def test_price_fields_unit():
    q = {"ts": NOW, "bid": 10.0, "ask": 12.0}
    f = price_fields(q, [{"ts_open": D, "c": 5.0}, {"ts_open": D - timedelta(days=1), "c": 8.0}], NOW)
    assert f["last"] == 11.0 and f["prev_close"] == 8.0           # nen D1 cua chinh ngay quote khong lam moc tham chieu
    assert price_fields(None, [], NOW)["last"] is None
