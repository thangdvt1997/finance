"""R3-8 (2026-10-14): mo rong nguon 'actual' mien phi khong key — BoJ (Nhat), Eurostat HICP moi (prc_hicp_minr), ONS/StatCan/ABS/BLS
them chi so. Fixture = phan hoi THAT lay tu VPS 2026-10-14."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from conftest import fx
from news_collector.calendar_book import CalendarBook, indicator_value, load_enrich_config
from news_collector.models import Emit
from news_collector.runner import Runner
from news_collector.sources.actuals import ActualsSource, build_providers, parse_boj, parse_eurostat
from news_collector.sources.base import Source
from news_collector.sources.calendar_sources import cal_emit

from conftest import CONFIG

UTC = timezone.utc
CFG = load_enrich_config(CONFIG)
IND = {i["id"]: i for i in CFG["indicators"]}


def test_parse_boj_real():
    ppi = parse_boj(fx("real_act_boj_ppi.json"))["PRCG20_2200000000"]
    assert ppi["2026-09"] == 135.7 and ppi["2025-09"] > 0
    yoy, prev = indicator_value(ppi, "2026-09", IND["jp_ppi_yoy"])
    assert yoy == pytest.approx((135.7 / ppi["2025-09"] - 1) * 100) and prev == pytest.approx((136.1 / ppi["2025-08"] - 1) * 100)
    assert round(prev, 1) == 7.6  # khop 'previous' cua lich (PPI y/y thang 8 = 7.6%)
    m2 = parse_boj(fx("real_act_boj_m2.json"))["MAM1YAM2M2MO"]
    assert m2["2026-08"] == 2.0 and indicator_value(m2, "2026-09", IND["jp_m2_yoy"])[0] == 2.0


def test_parse_boj_error_and_blank_values():
    with pytest.raises(ValueError, match="BoJ"):
        parse_boj(b'{"STATUS":400,"MESSAGEID":"M181005E","MESSAGE":"Invalid parameter","RESULTSET":[]}')
    d = parse_boj(b'{"STATUS":200,"RESULTSET":[{"SERIES_CODE":"X","VALUES":{"SURVEY_DATES":[202608,202609,2026],'
                  b'"VALUES":[1.5,"",3]}}]}')
    assert d == {"X": {"2026-08": 1.5}}  # o trong / tan suat nam bi bo


def test_eurostat_new_hicp_dataset_is_current():
    eu = parse_eurostat(fx("real_act_eurostat_hicp_minr.json"))
    assert max(eu) >= "2026-09" and eu["2026-09"] == 3.8
    assert IND["eu_cpi_yoy"]["series"].startswith("prc_hicp_minr|") and "coicop18=" in IND["eu_cpi_flash_yoy"]["series"]


@pytest.mark.parametrize("country,title,ind_id", [
    ("JPY", "PPI y/y", "jp_ppi_yoy"), ("JPY", "M2 Money Stock y/y", "jp_m2_yoy"), ("EUR", "Final CPI y/y", "eu_cpi_yoy"),
    ("EUR", "Final Core CPI y/y", "eu_core_cpi_yoy"), ("EUR", "Industrial Production m/m", "eu_indpro_mom"),
    ("GBP", "GDP m/m", "gb_gdp_mom"), ("GBP", "Manufacturing Production m/m", "gb_manuf_mom"),
    ("AUD", "Employment Change", "au_employment"), ("USD", "Import Prices m/m", "us_import_mom"), ("CAD", "Retail Sales m/m", "ca_retail_mom"),
])
def test_calendar_titles_map_to_indicators(country, title, ind_id):
    assert CalendarBook(CFG).indicator_for({"country": country, "title": title})["id"] == ind_id


def test_every_indicator_has_known_provider():
    prov = build_providers(CFG, fred_key="k")
    assert {i["provider"] for i in CFG["indicators"]} <= set(prov)


class StubSource(Source):
    name = "stub"

    def __init__(self, emits):
        self.emits = emits

    async def fetch(self, ctx):
        return self.emits


async def test_boj_actual_filled_end_to_end(bus, make_ctx):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        u = req.url
        if u.host == "www.stat-search.boj.or.jp":
            calls.append(u.params["code"])
            assert u.params["db"] in ("PR01", "MD02") and u.params["format"] == "json"
            return httpx.Response(200, content=fx("real_act_boj_ppi.json" if u.params["db"] == "PR01" else "real_act_boj_m2.json"))
        return httpx.Response(404)

    rel = datetime(2026, 10, 12, 23, 50, tzinfo=UTC)  # 08:50 JST 13/10: PPI thang 9
    ctx = make_ctx(handler)
    ctx.now = lambda: rel + timedelta(minutes=2)
    ev = [cal_emit(eid="ppi", country="JP", title="PPI y/y", impact="low", ts=rel, forecast="7.6%", previous="7.6%", source="faireconomy"),
          cal_emit(eid="m2", country="JP", title="M2 Money Stock y/y", impact="low", ts=rel, forecast="2.1%", previous="2.0%", source="faireconomy")]
    stub = StubSource([Emit(e.stream, e.type, e.payload, f"k{i}") for i, e in enumerate(ev)])
    act = ActualsSource(build_providers(CFG))
    r = Runner(bus, ctx, [stub, act], risk_enabled=False)
    await r.run_once(stub)
    await r.run_once(act)
    assert act.last["filled"] == 2 and sorted(calls) == ["MAM1YAM2M2MO", "PRCG20_2200000000"]
    m = {p["title"]: p for p in (r.book.merged(k) for k in r.book.raw)}
    assert m["PPI y/y"]["actual"] == "6.8%" and m["PPI y/y"]["extra"]["actual_source"] == "boj"
    assert m["PPI y/y"]["extra"]["actual_period"] == "2026-09" and m["PPI y/y"]["extra"]["surprise"]["direction"] == "below"
    assert m["M2 Money Stock y/y"]["actual"] == "2.0%"
