from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import D, FakeStore
from vn_market import vndirect as vd
from vn_market.app import create_app
from vn_market.ingest import Ingestor

PRICE = {"code": "VNM", "date": "2026-10-09", "floor": "HOSE", "type": "STOCK", "basicPrice": 57.9, "ceilingPrice": 61.9, "floorPrice": 53.9,
         "open": 57.8, "high": 58.3, "low": 57.6, "close": 57.7, "adClose": 57.7, "average": 57.913, "nmVolume": 1355700.0, "nmValue": 7.85e10,
         "ptVolume": 0.0, "ptValue": 0.0, "pctChange": -0.3454}


def test_parse_price_scales_to_vnd():
    p = vd.parse_price(PRICE)
    assert p["close"] == 57_700.0 and p["ceil"] == 61_900.0 and p["flr"] == 53_900.0 and p["basic"] == 57_900.0
    assert p["volume"] == 1_355_700.0 and p["value"] == 7.85e10 and p["pct"] == -0.3454 and p["d"] == date(2026, 10, 9)
    assert vd.parse_price({"code": "X"}) is None and vd.parse_price({"date": "2026-10-09"}) is None


def test_parse_index_foreign_event_ratios():
    i = vd.parse_index({"code": "VNINDEX", "date": "2026-10-09", "close": 1735.09, "advances": 121.0, "ceilingStocks": 9.0, "pctChange": -0.22})
    assert i["close"] == 1735.09 and i["advances"] == 121 and i["ceiling_n"] == 9    # chỉ số KHÔNG nhân 1000
    f = vd.parse_foreign({"code": "VNM", "type": "STOCK", "tradingDate": "2026-10-09", "netVal": -2.4e9, "totalRoom": 2.0e9, "currentRoom": 1.0e9})
    assert f["net_val"] == -2.4e9 and vd.parse_foreign({"code": "EW_HOSE", "type": "SECURITIES", "tradingDate": "2026-10-09"}) is None
    e = vd.parse_event({"id": "1.VN", "code": "vnm", "type": "DIVIDEND", "locale": "VN", "dividend": 1850.0, "effectiveDate": "2026-06-26", "note": "x"})
    assert e["code"] == "VNM" and e["dividend"] == 1850.0 and e["effective_date"] == date(2026, 6, 26)
    assert vd.parse_event({"id": "1.EN", "code": "VNM", "type": "DIVIDEND", "locale": "EN_GB"}) is None
    assert vd.parse_event({"id": "2", "code": "VNM", "type": "LISTED", "locale": "VN"}) is None
    r = vd.merge_ratios({"MARKETCAP": [{"code": "VNM", "value": 1.2e14}], "PRICE_TO_EARNINGS": [{"code": "VNM", "value": 11.0}, {"code": "ABC", "value": None}]}, D)
    assert r == [{"code": "VNM", "as_of": D, "marketcap": 1.2e14, "pe": 11.0, **{c: None for c in vd.RATIO_CODES.values() if c not in ("marketcap", "pe")}}]


# ---- client: tự giới hạn tốc độ, retry, phân trang -------------------------------------------------------------------------
async def test_client_pagination_and_retry():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        page = int(req.url.params.get("page", "1"))
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": [{"n": page * 10 + i} for i in range(2)], "totalElements": 4, "currentPage": page})
    c = vd.VNDirectClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), min_interval=0.0, retries=3)
    rows = await c.fetch_all("stock_prices", "floor:HOSE", size=2)
    assert len(rows) == 4 and len(calls) == 3 and c.requests == 3     # 1 lỗi 503 + 2 trang


async def test_client_gives_up_on_4xx():
    c = vd.VNDirectClient(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))), min_interval=0.0)
    with pytest.raises(vd.SourceError):
        await c.get("stock_prices", q="x")
    assert c.requests == 1


# ---- ingest với client giả + store trong bộ nhớ ------------------------------------------------------------------------------
class MemStore(FakeStore):
    def __init__(self):
        super().__init__()
        self.t: dict[str, dict] = {}
        self.dates = [D - timedelta(days=1), D]

    async def upsert(self, table, rows):
        pk = {"vn_daily": ("code", "d"), "vn_index_daily": ("code", "d"), "vn_foreign": ("code", "d"), "vn_ratios": ("code",),
              "vn_events": ("event_id",), "vn_symbols": ("code",)}[table]
        for r in rows:
            self.t.setdefault(table, {})[tuple(r[k] for k in pk)] = r
        return len(rows)
    async def symbols(self, focus_only=False): return list(self.t.get("vn_symbols", {}).values())
    async def latest_date(self): return max((k[1] for k in self.t.get("vn_index_daily", {}) if k[0] == "VNINDEX"), default=None)
    async def trading_dates(self, n): return sorted({k[1] for k in self.t.get("vn_index_daily", {}) if k[0] == "VNINDEX"}, reverse=True)[:n]
    async def dates_with_prices(self, since):
        out: dict = {}
        for k in self.t.get("vn_daily", {}):
            out[k[1]] = out.get(k[1], 0) + 1
        return out
    async def foreign_dates(self, since):
        out: dict = {}
        for k in self.t.get("vn_foreign", {}):
            out[k[1]] = out.get(k[1], 0) + 1
        return out
    async def index_counts(self):
        out: dict = {}
        for k in self.t.get("vn_index_daily", {}):
            out[k[0]] = out.get(k[0], 0) + 1
        return out
    async def daily_coverage(self):
        out: dict = {}
        for k in self.t.get("vn_daily", {}):
            n, f = out.get(k[0], (0, k[1]))
            out[k[0]] = (n + 1, min(f, k[1]))
        return out


class FakeClient:
    requests = 0

    async def listed_symbols(self): return [{"code": "VCB", "floor": "HOSE", "type": "STOCK", "companyName": "Vietcombank", "shortName": "VCB", "listedDate": "2009-06-30"}]
    async def index_history(self, code, start):
        return [{"code": code, "date": (D - timedelta(days=i)).isoformat(), "close": 1700.0 + i, "type": "COMPOSITE", "floor": "HOSE"} for i in (1, 0)]
    async def prices_on(self, floor, d):
        return [{**PRICE, "code": "VCB", "floor": floor, "date": d.isoformat()}] if floor == "HOSE" else []
    async def indices_on(self, d): return [{"code": "VNINDEX", "date": d.isoformat(), "close": 1700.0}]
    async def foreign_on(self, d): return [{"code": "VCB", "type": "STOCK", "tradingDate": d.isoformat(), "netVal": 1.0}]
    async def ratio_on(self, rc, d): return [{"code": "VCB", "value": 1.0}] if rc in ("MARKETCAP", "PRICE_TO_EARNINGS") else []
    async def events_between(self, a, b): return [{"id": "e1.VN", "code": "VCB", "type": "DIVIDEND", "locale": "VN", "effectiveDate": "2026-10-20"}]
    async def price_history(self, code, start): return [{**PRICE, "code": code, "date": (D - timedelta(days=i)).isoformat()} for i in range(3)]


async def test_run_once_idempotent():
    st = MemStore()
    ing = Ingestor(FakeClient(), st, window=5, min_rows=1)
    s1 = await ing.run_once(backfill=False)
    assert s1["symbols"] == 1 and len(s1["days"]) == 2 and s1["ratios"] == 1 and s1["events"] == 1
    assert len(st.t["vn_daily"]) == 2 and len(st.t["vn_foreign"]) == 2 and ("VCB",) in st.t["vn_ratios"]
    n_daily = len(st.t["vn_daily"])
    s2 = await ing.run_once(backfill=False)          # chạy lại: không nạp thêm ngày/ratios/events
    assert s2["days"] == [] and "ratios" not in s2 and "events" not in s2 and len(st.t["vn_daily"]) == n_daily
    assert ing.status["last_error"] is None and ing.status["last_ok"]


async def test_backfill_focus():
    st = MemStore()
    r = await Ingestor(FakeClient(), st, window=5, min_rows=1).backfill_focus(limit=2)
    assert r["done"] == 2 and r["todo"] > 100 and len(st.t["vn_daily"]) == 6


async def test_unknown_symbols_are_added():
    st = MemStore()
    ing = Ingestor(FakeClient(), st, window=5)
    await ing.run_once(backfill=False)
    class C2(FakeClient):
        async def prices_on(self, floor, d): return [{**PRICE, "code": "NEW", "floor": "HNX", "date": d.isoformat()}] if floor == "HNX" else []
    ing2 = Ingestor(C2(), st, window=5)
    known = {"VCB"}
    await ing2.ingest_day(D, known)
    assert "NEW" in known and ("NEW",) in st.t["vn_symbols"]


# ---- API --------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def client(fake_store):
    with TestClient(create_app(fake_store, None, run_ingest=False)) as c:
        yield c


def test_api_overview_and_status(client):
    j = client.get("/vn/overview").json()
    assert j["as_of"] == "2026-10-09" and j["indices"][0]["code"] == "VNINDEX" and len(j["indices"][0]["spark"]) == 30
    assert j["breadth"]["HOSE"]["advances"] == 2 and j["liquidity"]["label"] == "sôi động"
    assert set(j["session"]) == {"HOSE", "HNX", "UPCOM"} and j["limits"] == {"ceiling_n": 1, "floor_n": 1}
    s = client.get("/vn/status").json()
    assert s["capabilities"]["proprietary"] is False and s["capabilities"]["foreign_flow"] is True and "proprietary" in s["unavailable"]
    assert client.get("/healthz").status_code == 200


def test_api_views(client):
    assert [r["code"] for r in client.get("/vn/movers?by=gainers&min_value=5e9").json()["rows"]] == ["SHS", "VCB"]
    assert client.get("/vn/limits").json()["ceiling"][0]["code"] == "TLH"
    h = client.get("/vn/heatmap?universe=vn30&size=value").json()
    assert h["count"] == 4 and h["sectors"][0]["children"]
    f = client.get("/vn/foreign").json()
    assert f["top_buy"][0]["code"] == "VCB" and f["cum"]["top_sell"][0]["code"] == "HPG" and f["proprietary"]["available"] is False
    sc = client.get("/vn/screener?pe_max=13&universe=vn100").json()
    assert {r["code"] for r in sc["rows"]} == {"VCB", "BID", "VNM"} and sc["filters"] == {"pe": [None, 13.0]}
    assert client.get("/vn/screener?pe_min=abc").status_code == 400
    assert client.get("/vn/screener?rsi14_min=50&universe=vn100").json()["total"] >= 0
    sy = client.get("/vn/symbol/vn:vcb").json()
    assert sy["info"]["code"] == "VCB" and sy["snapshot"]["code"] == "VCB" and sy["events"][0]["etype"] == "DIVIDEND"
    assert client.get("/vn/symbol/ZZZ").status_code == 404 and client.get("/vn/symbol/a b").status_code in (400, 404)
    ev = client.get("/vn/events").json()
    assert [e["code"] for e in ev["rows"]] == ["VCB"]                      # focus: TLH ngoài VN100 bị lọc
    assert sorted(e["code"] for e in client.get("/vn/events?focus=false").json()["rows"]) == ["TLH", "VCB"]
    n = client.get("/vn/news").json()
    assert [t["url"] for t in n["rows"]] == ["u1"] and n["rows"][0]["codes"] == ["VCB", "HPG"]
    assert client.get("/vn/news?code=HPG").json()["total"] == 1
    assert client.get("/vn/rules").json()["sell_tax_pct"] == 0.1
    assert client.get("/vn/breadth").json()["computed"]["ALL"]["total"] == 8
    assert client.get("/vn/movers?universe=bogus").status_code == 400
    assert client.get("/vn/overview?date=2026-13-01").status_code == 400
    assert client.get("/vn/symbols?q=vc").json()["rows"][0]["code"] == "VCB"
    assert client.get("/vn/session").json()["sessions"]["HOSE"]["floor"] == "HOSE"


def test_api_readonly(client):
    for m in ("post", "put", "delete", "patch"):
        assert getattr(client, m)("/vn/overview").status_code == 405
