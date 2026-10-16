"""Lam giau lich: actual tu API thong ke (fixture = phan hoi THAT lay tu VPS 2026-10-11), forecast tu Fair Economy, surprise, nhom, rui ro."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from conftest import CONFIG, NOW, fx
from news_collector.calendar_book import (CalendarBook, expected_period, indicator_value, load_enrich_config, norm_title)
from news_collector.models import Emit
from news_collector.runner import Runner
from news_collector.sources.actuals import (ActualsSource, build_providers, parse_abs, parse_bls, parse_eurostat, parse_ons,
                                            parse_statcan)
from news_collector.sources.base import Source
from news_collector.sources.calendar_sources import cal_emit, parse_faireconomy
from news_collector.values import format_like, parse_value, surprise

UTC = timezone.utc
CFG = load_enrich_config(CONFIG)


# ---- values -------------------------------------------------------------------------------------------
def test_parse_and_format():
    assert parse_value("0.3%") == (0.3, "%") and parse_value("-0.1%") == (-0.1, "%") and parse_value("150K") == (150.0, "K")
    assert parse_value("<0.1%") == (0.1, "%") and parse_value("4.5|1.8") == (4.5, "") and parse_value("") is None
    assert parse_value("n/a") is None and parse_value(None) is None
    assert format_like(4.2, "%", "4.3%", 1) == "4.2%" and format_like(0.0, "%", "0.3%", 1) == "0.0%"
    assert format_like(7.079, "M", "7.20M", 2) == "7.08M"
    assert format_like(151.0, "K", None, 0) == "151K"
    assert format_like(1.5, "M", "850K", 0) == "1500K"  # doi don vi theo mau forecast


def test_surprise_polarity_and_scale():
    s = surprise("4.2%", "4.3%", "Unemployment Rate", CFG["surprise"])
    assert s["value"] == -0.1 and s["direction"] == "below" and s["verdict"] == "good" and s["polarity"] == -1  # that nghiep thap = tot
    s = surprise("0.5%", "0.3%", "CPI m/m", CFG["surprise"])
    assert s["value"] == 0.2 and s["z"] == 2.0 and s["verdict"] == "good" and s["direction"] == "above"
    s = surprise("100K", "150K", "Non-Farm Employment Change", CFG["surprise"])
    assert s["value"] == -50 and s["verdict"] == "bad" and s["z"] == pytest.approx(-0.67, abs=0.01)
    assert surprise("0.3%", "0.3%", "CPI m/m", CFG["surprise"])["verdict"] == "neutral"
    assert surprise("260K", "250K", "Unemployment Claims", CFG["surprise"])["verdict"] == "bad"  # nhieu xin tro cap = xau
    assert surprise("1.2M", "1.0M", "Something", None)["value"] == pytest.approx(0.2)
    assert surprise(None, "1.0%", "x") is None and surprise("1%", "n/a", "x") is None


def test_norm_title_and_expected_period():
    assert norm_title("CPI y/y") == norm_title("CPI YoY") == "cpiyoy"
    assert expected_period(datetime(2026, 10, 14, 12, 30, tzinfo=UTC), 1) == "2026-09"
    assert expected_period(datetime(2027, 1, 5, tzinfo=UTC), 2) == "2026-11"


# ---- parser tren phan hoi THAT ------------------------------------------------------------------------------
def test_parse_bls_real_and_transforms():
    d = parse_bls(fx("real_act_bls.json"))
    assert len(d) == 10 and d["LNS14000000"]["2026-09"] == 4.2 and "2026-13" not in d["CUSR0000SA0"]
    ind = {i["id"]: i for i in CFG["indicators"]}
    cpi = d["CUSR0000SA0"]
    v, prev = indicator_value(cpi, "2026-08", ind["us_cpi_mom"])
    assert v == pytest.approx((cpi["2026-08"] / cpi["2026-07"] - 1) * 100) and prev == pytest.approx((cpi["2026-07"] / cpi["2026-06"] - 1) * 100)
    yoy, _ = indicator_value(d["CUUR0000SA0"], "2026-08", ind["us_cpi_yoy"])
    assert yoy == pytest.approx((d["CUUR0000SA0"]["2026-08"] / d["CUUR0000SA0"]["2025-08"] - 1) * 100)
    nfp, _ = indicator_value(d["CES0000000001"], "2026-09", ind["us_nfp"])
    assert nfp == d["CES0000000001"]["2026-09"] - d["CES0000000001"]["2026-08"]
    assert indicator_value(cpi, "2026-09", ind["us_cpi_mom"]) == (None, pytest.approx(v, abs=5))  # chua co CPI thang 9 -> None
    jolts, _ = indicator_value(d["JTS000000000000000JOL"], "2026-08", ind["us_jolts"])
    assert jolts == pytest.approx(7.079)  # nghin -> trieu


def test_parse_bls_error_status():
    with pytest.raises(ValueError, match="REQUEST_NOT_PROCESSED"):
        parse_bls(b'{"status":"REQUEST_NOT_PROCESSED","message":["daily threshold reached"],"Results":{}}')


def test_parse_other_providers_real():
    sc = parse_statcan(fx("real_act_statcan.json"))
    assert sc["2062815"]["2026-09"] == 6.5 and sc["41690973"]["2026-08"] == 169.8
    cpi_m, _ = indicator_value(sc["41690973"], "2026-08", {"transform": "mom_pct"})
    assert cpi_m == pytest.approx((169.8 / 169.9 - 1) * 100)
    ons = parse_ons(fx("real_act_ons_cpi.json"))
    assert ons["2026-08"] == 3.1 and ons["2026-07"] == 2.9
    a = parse_abs(fx("real_act_abs_lf.json"))
    assert a["2026-08"] == pytest.approx(4.64629609) and a["2026-06"] == pytest.approx(4.44997236)
    eu = parse_eurostat(fx("real_act_eurostat_hicp.json"))
    assert max(eu) == "2025-12"  # dataset dong bang -> khong duoc dung lam actual cho ky 2026-xx
    assert indicator_value(eu, expected_period(datetime(2026, 10, 30, tzinfo=UTC), 0), {"transform": "level"})[0] is None


# ---- So lich: gop nguon, group, surprise -----------------------------------------------------------------------
def ff_book():
    book = CalendarBook(CFG)
    for e in parse_faireconomy(fx("real_faireconomy_thisweek.json")):
        book.ingest(e.payload)
    return book


def test_groups_and_peer_fill():
    book = ff_book()
    # hang chinh thuc BLS cung nhom voi FF; forecast duoc dien khi cung ten+quoc gia+gio
    bls = cal_emit(eid="u1", country="US", title="Consumer Price Index", impact="high", ts=datetime(2026, 10, 14, 12, 30, tzinfo=UTC), source="bls").payload
    m = book.ingest(bls)
    assert m["extra"]["group"] == "us_cpi" and not m["forecast"]
    ff = [v for k, v in book.raw.items() if v["title"] == "CPI m/m"][0]
    assert book.merged((ff["source"], ff["event_id"]))["extra"]["group"] == "us_cpi" and ff["forecast"] == "0.6%"
    # cung ten tu nguon khac -> dien forecast + ghi nguon
    peer = cal_emit(eid="p1", country="US", title="CPI m/m", impact="high", ts=datetime(2026, 10, 14, 12, 30, tzinfo=UTC), source="other").payload
    mp = book.ingest(peer)
    assert mp["forecast"] == "0.6%" and mp["previous"] == "0.4%" and mp["extra"]["forecast_source"] == "faireconomy"
    assert book.group_of({"country": "GBP", "title": "Official Bank Rate"}) == "gb_boe"
    assert book.group_of({"country": "AU", "title": "Unemployment Rate"}) is None  # chi US o nhom us_employment


def event(country, title, ts, forecast=None, previous=None, impact="high", eid=None, source="faireconomy"):
    return cal_emit(eid=eid or f"{country}-{title}", country=country, title=title, impact=impact, ts=ts, forecast=forecast,
                    previous=previous, source=source).payload


class StubSource(Source):
    name = "stub"

    def __init__(self, emits):
        self.emits = emits

    async def fetch(self, ctx):
        return self.emits


def api_handler(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    if "api.bls.gov" in u:
        assert req.method == "POST" and json.loads(req.content)["seriesid"]
        return httpx.Response(200, content=fx("real_act_bls.json"))
    if "statcan" in u:
        return httpx.Response(200, content=fx("real_act_statcan.json"))
    if "ons.gov.uk" in u:
        return httpx.Response(200, content=fx("real_act_ons_cpi.json"))
    return httpx.Response(404)


async def test_actual_filled_published_with_surprise(bus, make_ctx):
    """Phat lai hang lich khi API tra actual: forecast tu FF, actual tu BLS (that nhiep thap hon du bao = tot cho USD)."""
    rel = datetime(2026, 10, 2, 12, 30, tzinfo=UTC)
    now = [rel - timedelta(minutes=5)]
    ctx = make_ctx(api_handler)
    ctx.now = lambda: now[0]
    stub = StubSource([Emit("calendar", "calendar", event("USD", "Unemployment Rate", rel, "4.3%", "4.3%"), "x1"),
                       Emit("calendar", "calendar", event("USD", "Non-Farm Employment Change", rel, "50K", "22K"), "x2"),
                       Emit("calendar", "calendar", event("USD", "FOMC Member X Speaks", rel, None, None), "x3")])
    act = ActualsSource(build_providers(CFG), interval=30)
    r = Runner(bus, ctx, [stub, act], risk_enabled=False)
    await r.run_once(stub)
    assert await r.bus.r.xlen("calendar.events") == 3
    await r.run_once(act)  # truoc gio cong bo -> khong goi API
    assert act.last["filled"] == 0 and act.providers["bls"].calls == 0
    now[0] = rel + timedelta(minutes=1)
    await r.run_once(act)
    assert act.last["filled"] == 2 and act.providers["bls"].calls == 1  # 1 request cho ca 2 chi so (batch)
    evs = {json.loads(m["e"])["payload"]["title"]: json.loads(m["e"])["payload"] for _, m in await r.bus.r.xrange("calendar.events")}
    # lan phat cuoi cung cua moi su kien (xrange tang dan -> ghi de) co actual
    ur = evs["Unemployment Rate"]
    assert ur["actual"] == "4.2%" and ur["extra"]["actual_source"] == "bls" and ur["extra"]["actual_period"] == "2026-09"
    assert ur["extra"]["surprise"]["verdict"] == "good" and ur["extra"]["surprise"]["direction"] == "below"
    nfp = evs["Non-Farm Employment Change"]
    d = parse_bls(fx("real_act_bls.json"))["CES0000000001"]
    assert nfp["actual"] == f"{round(d['2026-09'] - d['2026-08'])}K" and nfp["extra"]["group"] == "us_employment"
    assert evs["FOMC Member X Speaks"]["actual"] is None
    n = await r.bus.r.xlen("calendar.events")
    await r.run_once(act)  # da co actual -> khong goi API nua, khong phat lai
    assert act.providers["bls"].calls == 1 and await r.bus.r.xlen("calendar.events") == n


async def test_not_yet_published_period_keeps_pending_and_schedule(bus, make_ctx):
    rel = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)  # CPI thang 9: BLS chua co (fixture chi toi thang 8)
    now = [rel + timedelta(seconds=20)]
    ctx = make_ctx(api_handler)
    ctx.now = lambda: now[0]
    stub = StubSource([Emit("calendar", "calendar", event("USD", "CPI m/m", rel, "0.6%", "0.4%"), "x1")])
    act = ActualsSource(build_providers(CFG))
    r = Runner(bus, ctx, [stub, act], risk_enabled=False)
    await r.run_once(stub)
    await r.run_once(act)
    assert act.last["filled"] == 0 and act.providers["bls"].calls == 1
    await r.run_once(act)  # chua den moc tham do ke tiep (T+1p) -> khong goi them
    assert act.providers["bls"].calls == 1
    now[0] = rel + timedelta(minutes=1, seconds=5)
    await r.run_once(act)
    assert act.providers["bls"].calls == 2
    now[0] = rel + timedelta(hours=40)  # qua give_up -> thoi
    await r.run_once(act)
    assert act.providers["bls"].calls == 2


async def test_budget_and_missing_key(bus, make_ctx):
    rel = datetime(2026, 10, 2, 12, 30, tzinfo=UTC)
    ctx = make_ctx(api_handler)
    ctx.now = lambda: rel + timedelta(minutes=1)
    stub = StubSource([Emit("calendar", "calendar", event("US", "Retail Sales m/m", rel, "0.3%", "0.1%"), "x1"),
                       Emit("calendar", "calendar", event("USD", "Unemployment Rate", rel, "4.3%", None), "x2")])
    prov = build_providers(CFG)  # khong co FRED key -> khong co provider fred
    assert "fred" not in prov and "fred" in build_providers(CFG, fred_key="k")
    prov["bls"].daily_cap = 0  # het ngan sach
    act = ActualsSource(prov)
    r = Runner(bus, ctx, [stub, act], risk_enabled=False)
    await r.run_once(stub)
    await r.run_once(act)
    assert act.last["filled"] == 0 and prov["bls"].calls == 0


def test_actual_from_api_does_not_overwrite_source_actual():
    book = CalendarBook(CFG)
    p = event("USD", "Unemployment Rate", datetime(2026, 10, 2, 12, 30, tzinfo=UTC), "4.3%")
    p["actual"] = "4.1%"
    m = book.ingest(p)
    assert m["actual"] == "4.1%" and m["extra"]["actual_source"] == "faireconomy"
    assert book.pending(datetime(2026, 10, 2, 13, tzinfo=UTC)) == []


# ---- Rui ro qua Runner ---------------------------------------------------------------------------------------------
async def test_runner_risk_alerts_once_per_phase(bus, make_ctx):
    cpi = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)
    now = [cpi - timedelta(minutes=25)]
    ctx = make_ctx(api_handler)
    ctx.now = lambda: now[0]
    stub = StubSource(parse_faireconomy(fx("real_faireconomy_thisweek.json")))
    r = Runner(bus, ctx, [stub])
    await r.run_once(stub)
    assert await r.check_risk() == 1  # T-30 'pre' cho nhom CPI (4 su kien gom 1)
    assert await r.check_risk() == 0
    now[0] = cpi - timedelta(minutes=10)
    assert await r.check_risk() == 1  # enter
    now[0] = cpi + timedelta(minutes=31)
    assert await r.check_risk() == 1  # exit
    msgs = [json.loads(m["e"])["payload"] for _, m in await r.bus.r.xrange("alerts.out")]
    assert [m["tags"][-1] for m in msgs] == ["pre", "enter", "exit"]
    assert all(m["dedupe_key"].startswith("risk:") and "risk-window" in m["tags"] for m in msgs)
