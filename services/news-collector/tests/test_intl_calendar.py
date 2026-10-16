"""Lich quoc te: ECB/BoE/BoJ (fixture = HTML THAT trich ngay 2026-10-11), Fair Economy that, FMP (mau theo tai lieu)."""
import json
from datetime import datetime, timezone

import httpx
import pytest

from conftest import fx
from news_collector.app import build_sources
from news_collector.settings import NewsSettings
from news_collector.sources.calendar_sources import parse_faireconomy
from news_collector.sources.central_banks import CentralBankCalendarSource, parse_boe, parse_boj, parse_ecb
from news_collector.sources.fmp_calendar import FmpCalendarSource, parse_fmp

UTC = timezone.utc


def by(emits, **kw):
    return [e.payload for e in emits if all(e.payload[k] == v for k, v in kw.items())]


def test_ecb_real_calendar():
    out = parse_ecb(fx("real_ecb_gc.html"))
    dec = by(out, title="ECB Interest Rate Decision")
    ts = {p["ts"] for p in dec}
    # 29/10/2026 14:15 CET (UTC+1 sau khi DST chau Au ket thuc 25/10) = 13:15Z; 17/12 14:15 CET = 13:15Z
    assert "2026-10-29T13:15:00+00:00" in ts and "2026-12-17T13:15:00+00:00" in ts
    # 04/02/2027 va 22/07/2027 (mua he: 14:15 CEST = 12:15Z)
    assert "2027-02-04T13:15:00+00:00" in ts and "2027-07-22T12:15:00+00:00" in ts
    assert all(p["impact"] == "high" and p["country"] == "EU" and p["source"] == "ecb" for p in dec)
    assert not any("non-monetary" in p["title"].lower() for p in out_payloads(out))  # hop non-monetary/General Council bi loai
    assert by(out, title="ECB Press Conference")[0]["impact"] == "med"
    assert len(dec) == len({p["event_id"] for p in dec}) >= 8  # id on dinh, khong trung


def out_payloads(out):
    return [e.payload for e in out]


def test_boe_real_calendar_with_current_rate():
    out = parse_boe(fx("real_boe_mpc.html"))
    p = by(out, ts="2026-11-05T12:00:00+00:00")[0]  # 5/11/2026 12:00 GMT (London = UTC)
    assert p["title"] == "BoE Interest Rate Decision" and p["impact"] == "high" and p["country"] == "GB"
    assert p["previous"] == "3.75%"  # Bank Rate hien hanh gan vao ky hop ke tiep
    sept = by(out, ts="2026-09-17T11:00:00+00:00")  # BST: 12:00 = 11:00Z
    assert sept and sept[0]["previous"] is None
    assert len(out) == 16  # 8 ky 2026 + 8 ky 2027
    assert by(out, ts="2027-12-16T12:00:00+00:00") and by(out, ts="2026-12-17T12:00:00+00:00")
    assert by(out, ts="2026-12-18T12:00:00+00:00") == []  # khong bia ngay ngoai trang


def test_boj_real_calendar_takes_last_day_of_two_day_meeting():
    out = parse_boj(fx("real_boj_mpm.html"))
    ts = {e.payload["ts"] for e in out}
    assert "2026-10-30T03:00:00+00:00" in ts  # Oct. 29 (Thurs.), 30 (Fri.) -> ngay 30, 12:00 JST
    assert "2026-01-23T03:00:00+00:00" in ts and "2027-03-18T03:00:00+00:00" in ts  # hang co `\n` giua ngay
    assert len(out) == 16 and all(e.payload["country"] == "JP" and e.payload["impact"] == "high" for e in out)


async def test_central_bank_source_isolated_failures(make_ctx):
    def handler(req):
        h = req.url.host
        if h == "www.ecb.europa.eu":
            return httpx.Response(200, content=fx("real_ecb_gc.html"))
        if h == "www.boj.or.jp":
            return httpx.Response(200, content=b"<html>doi cau truc</html>")  # khong khop -> []
        return httpx.Response(404)  # BoE hong

    out = await CentralBankCalendarSource().fetch(make_ctx(handler))
    assert out and all(e.payload["source"] == "ecb" for e in out)


def test_central_bank_interval_floor():
    assert CentralBankCalendarSource(60).interval >= 3600


def test_faireconomy_real_week_forecast_previous_and_country_codes():
    out = [e.payload for e in parse_faireconomy(fx("real_faireconomy_thisweek.json"))]
    assert len(out) == 109
    assert sum(1 for p in out if p["forecast"]) >= 40 and sum(1 for p in out if p["previous"]) >= 40
    assert {p["country"] for p in out} >= {"US", "EU", "GB", "JP"} and "USD" not in {p["country"] for p in out}
    assert all(p["actual"] is None for p in out)  # feed 'thisweek' khong co truong actual


FMP_SAMPLE = json.dumps([  # MAU THEO TAI LIEU FMP (khong phai phan hoi that)
    {"date": "2026-10-14 12:30:00", "country": "US", "event": "CPI YoY", "currency": "USD", "previous": 2.9,
     "estimate": 3.0, "actual": None, "impact": "High"},
    {"date": "2026-10-15 08:00:00", "country": "GB", "event": "GDP MoM", "currency": "GBP", "previous": 0.1,
     "estimate": 0.2, "actual": 0.3, "impact": "Medium"},
    {"date": "bad", "country": "DE", "event": "x", "impact": "Low"},
]).encode()


def test_fmp_parse_sample():
    out = [e.payload for e in parse_fmp(FMP_SAMPLE)]
    assert len(out) == 2
    cpi = out[0]
    assert cpi["ts"] == "2026-10-14T12:30:00+00:00" and cpi["impact"] == "high" and cpi["country"] == "US"
    assert cpi["forecast"] == "3" and cpi["previous"] == "2.9" and cpi["actual"] is None and cpi["source"] == "fmp"
    assert out[1]["impact"] == "med" and out[1]["actual"] == "0.3"
    with pytest.raises(ValueError):
        parse_fmp(b'{"Error Message": "Invalid API KEY"}')


async def test_fmp_source_hides_key_in_errors(make_ctx):
    src = FmpCalendarSource("SECRETKEY123")
    seen = {}

    def ok(req):
        seen["q"] = dict(req.url.params)
        return httpx.Response(200, content=FMP_SAMPLE)

    assert len(await src.fetch(make_ctx(ok))) == 2 and seen["q"]["apikey"] == "SECRETKEY123"
    with pytest.raises(RuntimeError) as ei:
        await src.fetch(make_ctx(lambda r: httpx.Response(403)))
    assert "SECRETKEY123" not in str(ei.value)
    with pytest.raises(ValueError):
        FmpCalendarSource("")


def test_source_toggles_central_banks_and_fmp(monkeypatch):
    for k in ("NC_SRC_RSS", "NC_SRC_GDELT", "NC_SRC_COT", "NC_SRC_CAL_OFFICIAL", "NC_SRC_CAL_FAIRECONOMY", "NC_SRC_CAL_ACTUALS"):
        monkeypatch.setenv(k, "false")
    assert [s.name for s in build_sources(NewsSettings())] == ["cal_central_banks"]
    monkeypatch.setenv("NC_SRC_CAL_FMP", "true")  # bat nhung thieu key -> bo qua
    assert "cal_fmp" not in {s.name for s in build_sources(NewsSettings())}
    monkeypatch.setenv("FMP_API_KEY", "SECRETKEY999")
    assert "cal_fmp" in {s.name for s in build_sources(NewsSettings())}
    assert "SECRETKEY999" not in repr(NewsSettings())  # key khong lot vao repr


def test_faireconomy_event_id_stable_when_time_changes():
    """QA vong 4 (R3-14): nguon doi gio du kien (08:03 -> 09:03 -> 09:00) khong duoc tao dong moi; 2 lan phat bieu cung ngay van tach."""
    import json

    def rows(t):
        return json.dumps([
            {"title": "M2 Money Supply y/y", "country": "CNY", "date": f"2026-10-14T{t}:00-04:00", "impact": "Low", "forecast": "7.4%", "previous": "7.5%"},
            {"title": "ECB President Lagarde Speaks", "country": "EUR", "date": "2026-10-13T22:10:00-04:00", "impact": "High"},
            {"title": "ECB President Lagarde Speaks", "country": "EUR", "date": "2026-10-14T04:30:00-04:00", "impact": "High"},
        ]).encode()
    a = {e.payload["title"] + e.payload["ts"]: e.payload["event_id"] for e in parse_faireconomy(rows("04:03"))}
    b = [e.payload for e in parse_faireconomy(rows("05:00"))]
    m2a = [v for k, v in a.items() if k.startswith("M2")][0]
    m2b = [p for p in b if p["title"].startswith("M2")][0]
    assert m2a == m2b["event_id"] and m2b["ts"] == "2026-10-14T09:00:00+00:00"
    lag = [p["event_id"] for p in b if "Lagarde" in p["title"]]
    assert len(set(lag)) == 2
