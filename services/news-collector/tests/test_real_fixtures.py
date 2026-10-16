"""Test voi fixture lay tu PHAN HOI THAT (rut gon) ngay 2026-10-11: dam bao parser/config khop dinh dang that."""
import json

import yaml

from conftest import CONFIG, fx
from news_collector.sources.calendar_sources import classify_impact, parse_bls_ics, parse_fomc
from news_collector.sources.cot import parse_cot
from news_collector.sources.rss import parse_feed
from news_collector.sources.sec13f import build_positions, find_infotable_name, parse_infotable


def _ctx(make_ctx):
    import httpx
    return make_ctx(lambda r: httpx.Response(200))


def test_real_bls_atom_has_numbers(make_ctx):
    out = parse_feed(fx("real_bls_cpi_atom.xml"), {"id": "bls_cpi", "lang": "en", "symbols": ["EURUSD"]}, _ctx(make_ctx))
    p = out[0].payload
    assert p["title"].startswith("CPI for all items") and p["url"].startswith("https://www.bls.gov/news.release/")
    assert p["published_at"].startswith("2026-09-11T11:50") and "percent" in p["summary"]  # Atom <content> -> summary


def test_real_rdf_dates_from_dc_date(make_ctx):  # RBA/BIS dung RSS 1.0 (RDF), ngay o dc:date
    rba = parse_feed(fx("real_rba_rdf.xml"), {"id": "rba", "lang": "en", "symbols": ["AUDUSD"]}, _ctx(make_ctx))
    assert rba[0].payload["published_at"] == "2026-10-01T01:30:00+00:00"
    bis = parse_feed(fx("real_bis_rdf.xml"), {"id": "bis", "lang": "en"}, _ctx(make_ctx))
    assert len(bis) == 2 and bis[0].payload["published_at"] and bis[0].payload["url"].startswith("https://www.bis.org/")


def test_real_vn_feeds_and_summary_cap(make_ctx):
    ctx = _ctx(make_ctx)
    cafef = parse_feed(fx("real_cafef.xml"), {"id": "cafef", "lang": "vi", "summary_max": 80}, ctx)
    vnx = parse_feed(fx("real_vnexpress.xml"), {"id": "vnx", "lang": "vi"}, ctx)
    assert len(cafef) == 2 and len(vnx) == 2
    assert all(len(e.payload["summary"] or "") <= 81 for e in cafef)  # 80 + dau '…'
    assert all(e.payload["published_at"] and e.payload["title"] for e in cafef + vnx)


def test_real_bls_ics_impact_and_timezone():
    cfg = yaml.safe_load((CONFIG / "calendar_impact.yaml").read_text())
    ev = {e.payload["title"]: e.payload for e in parse_bls_ics(fx("real_bls.ics"), cfg)}
    assert ev["Consumer Price Index"]["ts"] == "2026-10-14T12:30:00+00:00"  # 08:30 EDT (TZID=US-Eastern)
    assert ev["Consumer Price Index"]["impact"] == "high" and ev["Employment Situation"]["impact"] == "high"
    assert ev["Employment Situation of Veterans"]["impact"] == "low"
    assert ev["State Job Openings and Labor Turnover"]["impact"] == "low"
    assert ev["U.S. Import and Export Price Indexes"]["impact"] == "med"
    assert ev["Job Openings and Labor Turnover Survey"]["impact"] == "high"
    assert ev["Productivity and Costs by Industry: Manufacturing and Mining Industries"]["impact"] == "low"
    assert classify_impact("Productivity and Costs", cfg) == "high"


def test_fomc_2026_config_matches_federal_reserve_calendar():
    cfg = yaml.safe_load((CONFIG / "fomc_dates.yaml").read_text())
    got = [str(d) for d in cfg["decision_dates"]]
    assert got == ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28",
                   "2026-12-09"]
    assert len(parse_fomc(cfg)) == 8


def test_real_cot_all_configured_contracts_present(make_ctx):
    cfg = yaml.safe_load((CONFIG / "cot_contracts.yaml").read_text())
    contracts = {str(k): v for k, v in cfg["contracts"].items()}
    rows = json.loads(fx("real_cot.json"))
    out = parse_cot(rows, contracts, _ctx(make_ctx))
    pos = [e.payload for e in out if e.stream == "expert_positions"] if hasattr(out[0], "stream") else [
        e.payload for e in out if "expert_id" in e.payload]
    codes = {p["expert_id"].split(":")[1] for p in pos}
    assert codes == set(contracts)  # 12/12 ma hop dong co du lieu that
    spx = next(p for p in pos if p["expert_id"] == "CFTC:13874A" and p["as_of"].startswith("2026-10-06"))
    assert spx["net_volume"] == 212009 - 366079 and spx["symbol"] == "US:SPX"
    jpy = next(p for p in pos if p["expert_id"] == "CFTC:097741")
    assert jpy["raw"]["pair_direction"] == -1


def test_real_13f_berkshire_infotable(make_ctx):
    h = parse_infotable(fx("real_13f_berkshire_infotable.xml"))
    assert {x["cusip"]: x["name"] for x in h}["037833100"] == "APPLE INC"
    ally = next(x for x in h if x["cusip"] == "02005N100")
    assert ally["shares"] == 12561737 + 2803875  # gop nhieu dong cung CUSIP (otherManager khac nhau)
    cusips = yaml.safe_load((CONFIG / "cusip_map.yaml").read_text())["cusips"]
    filing = {"accession": "0001193125-26-352200", "report_date": "2026-06-30", "filing_date": "2026-08-14"}
    pos = [e.payload for e in build_positions("1067983", {"name": "Berkshire"}, filing, h, cusips, 50)]
    assert {p["symbol"] for p in pos} == {"US:AAPL", "US:AXP", "US:KO", "US:ALLY"}  # khong con CUSIP:... cho ma da map
    assert find_infotable_name({"directory": {"item": [{"name": "56757.xml"}, {"name": "primary_doc.xml"}]}}) == "56757.xml"
