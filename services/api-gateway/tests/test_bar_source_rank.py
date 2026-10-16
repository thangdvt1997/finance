"""/v1/bars (hide_sources): nhieu nguon cung (symbol, tf, ts_open) -> giu 1 nen; chuoi canon (feed EA) uu tien nhat."""
from api_gateway.app import _dedupe_bars, _src_rank


def _r(src, c, ts="2026-10-14T13:00:00Z"):
    return {"symbol": "EURUSD", "tf": "M1", "ts_open": ts, "c": c, "source": src}


def test_canon_beats_dukascopy_and_raw_mt():
    rows = [_r("dukascopy", 1.0), _r("mt5:mt5:100000001", 2.0), _r("canon:mt5:100000001", 3.0), _r("dukascopy", 4.0, ts="2026-10-14T12:59:00Z")]
    out = _dedupe_bars(rows)
    assert [(x["ts_open"][11:16], x["c"]) for x in out] == [("13:00", 3.0), ("12:59", 4.0)]


def test_rank_prefix_matching():
    assert _src_rank("canon:x") < _src_rank("dukascopy") < _src_rank("mt5:demo-mt5-01") < _src_rank("yahoo_daily") < _src_rank("zzz")
    assert _src_rank("mt4:a") == _src_rank("mt")


async def test_v1_bars_returns_limit_unique_bars_when_multi_source():
    """3 nguon/ts (canon, mt tho, dukascopy): limit=5 phai tra 5 nen duy nhat (khong phai 5 hang), deu la canon."""
    from datetime import datetime, timedelta, timezone

    import httpx
    from api_gateway.app import create_app
    from api_gateway.config import GatewaySettings
    from api_gateway.repo import InMemoryRepo

    now = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)
    bars = [{"symbol": "EURUSD", "tf": "M1", "ts_open": now - timedelta(minutes=i), "o": 1.0, "h": 1.1, "l": 0.9, "c": c, "v": 1, "source": s}
            for i in range(20) for s, c in (("dukascopy", 1.01), ("mt5:mt5:100000001", 1.02), ("canon:mt5:100000001", 1.03))]
    app = create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, max_page_size=50), InMemoryRepo(bars=bars), None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers={"X-API-Key": "tok1"}) as c:
        r = await c.get("/v1/bars", params={"symbol": "EURUSD", "tf": "M1", "limit": 5})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 5 and len({x["ts_open"] for x in items}) == 5 and all(x["c"] == 1.03 for x in items)
