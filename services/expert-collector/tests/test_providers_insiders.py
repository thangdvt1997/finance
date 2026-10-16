"""Fixture THAT (rut gon) tu Form 4 / daily-index / Atom cua SEC EDGAR lay 2026-10-12 tu VPS."""
import asyncio
from datetime import date
from pathlib import Path

import httpx

from expert_collector.httpclient import PoliteClient
from expert_collector.providers_insiders import (
    InsiderForm4Source, build_signals, extract_ownership_xml, is_opportunity, parse_atom_filings, parse_daily_index,
    parse_form4, strength)

FX = Path(__file__).parent / "fixtures"


def rd(n):
    return (FX / n).read_text(encoding="utf-8")


def test_parse_daily_index_only_form4():
    rows = parse_daily_index(rd("real_form4_daily_index.idx"))
    assert [r["path"].rsplit("/", 1)[-1] for r in rows] == [
        "0000066740-26-000293.txt", "0000066740-26-000294.txt", "0001460471-26-000008.txt"]  # bo 1-A va 4/A
    assert rows[2]["cik"] == "1043509" and rows[2]["date"] == "20261009"


def test_parse_atom_dedupes_reporting_and_issuer():
    rows = parse_atom_filings(rd("real_form4_atom.xml"))
    assert len(rows) == 1 and rows[0]["path"] == "edgar/data/1275002/0001214659-26-012761.txt"


def test_real_buy_by_ten_percent_owner_is_opportunity():
    txs = parse_form4(rd("real_form4_sah_buy.xml"), "0001460471-26-000008")
    assert len(txs) == 1
    x = txs[0]
    assert (x.ticker, x.code, x.acq_disp, x.roles, x.plan_10b5) == ("SAH", "P", "A", ["10pct_owner"], False)
    assert round(x.value_usd) == 819_046 and x.tx_date == date(2026, 10, 7)
    sigs = build_signals(txs)
    assert len(sigs) == 1
    s = sigs[0]
    assert (s.symbol, s.side, s.entry) == ("US:SAH", "buy", 59.78) and s.raw["kind"] == "insider_buy"
    assert s.raw["value_usd"] == 819045.78 and 0.3 < s.raw["strength"] < 0.9 and s.raw["cluster"] == 0


def test_real_drip_purchase_excluded():
    txs = parse_form4(rd("real_form4_ahrt_drip.xml"))
    assert txs[0].code == "P" and txs[0].auto_buy is True and round(txs[0].value_usd) == 11200
    assert build_signals(txs) == []
    assert build_signals(txs, min_buy_usd=1) == []  # DRIP bi loai du nguong thap


def test_real_10b5_sell_excluded_and_rows_aggregated():
    txs = parse_form4(rd("real_form4_ptct_10b5_sell.xml"))
    assert len(txs) == 2 and all(t.code == "S" and t.plan_10b5 for t in txs)  # nonDerivativeHolding khong tinh
    assert build_signals(txs, min_sell_usd=1) == []


def test_real_grant_award_excluded():
    txs = parse_form4(rd("real_form4_stld_grant.xml"))
    assert txs[0].code == "A" and txs[0].price == 0.0
    assert is_opportunity(txs[0], min_buy_usd=1) is None


def test_sell_threshold_and_role_weight_and_cluster():
    base = parse_form4(rd("real_form4_sah_buy.xml"))[0]
    sell = type(base)(**{**base.__dict__, "code": "S", "acq_disp": "D", "value_usd": 2_000_000.0})
    assert is_opportunity(sell) == "insider_sell"
    assert is_opportunity(type(sell)(**{**sell.__dict__, "value_usd": 500_000.0})) is None
    ceo = type(base)(**{**base.__dict__, "roles": ["officer"], "title": "Chief Executive Officer"})
    assert strength(ceo) > strength(base)
    b1, b2, b3 = (type(base)(**{**base.__dict__, "owner_cik": str(i), "owner": f"O{i}"}) for i in range(3))
    sigs = build_signals([b1, b2, b3])
    assert len(sigs) == 3 and all(s.raw["cluster"] == 3 for s in sigs)
    assert sigs[0].raw["strength"] > build_signals([b1])[0].raw["strength"]


def _transport(requests_seen):
    sah = "<SEC-DOCUMENT>\n<XML>\n" + rd("real_form4_sah_buy.xml") + "\n</XML>\n"

    def handler(req: httpx.Request) -> httpx.Response:
        requests_seen.append(str(req.url))
        p = req.url.path
        if p == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /cgi-bin\n")
        if "daily-index" in p:
            return httpx.Response(200, text=rd("real_form4_daily_index.idx")) if p.endswith("20261009.idx") else httpx.Response(404)
        if p.endswith("0001460471-26-000008.txt"):
            return httpx.Response(200, text=sah)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_source_falls_back_to_daily_index_when_atom_blocked_by_robots():
    seen: list[str] = []
    client = PoliteClient("trading-system/0.1 (contact: <OWNER_EMAIL>)", min_interval=0, transport=_transport(seen))
    src = InsiderForm4Source(client, lookback_days=2, today=date(2026, 10, 12), use_atom=True)  # T2 12/10 -> duyet 12,9,8/10; chi 09 co chi muc

    async def run():
        try:
            e = (await src.list_experts())[0]
            return await src.fetch_signals(e)
        finally:
            await client.aclose()
    sigs = asyncio.run(run())
    assert not any("browse-edgar" in u for u in seen)  # khong cham /cgi-bin bi robots cam
    assert [(s.symbol, s.raw["kind"]) for s in sigs] == [("US:SAH", "insider_buy")]  # 2 filing 3M 404 -> bo qua


def test_extract_xml_from_submission_text():
    doc = "<SEC-DOCUMENT>\n<XML>\n" + rd("real_form4_sah_buy.xml") + "\n</XML>"
    assert extract_ownership_xml(doc).startswith("<ownershipDocument>") and extract_ownership_xml("no xml") is None
