from __future__ import annotations

from datetime import datetime, timezone

from conftest import D, sample_rows
from vn_market import analytics as an, news as newsmod, rules, universe


def utc(y, mo, d, h, mi):  # giờ VN -> UTC
    return datetime(y, mo, d, h - 7, mi, tzinfo=timezone.utc)


# ---- rules ----------------------------------------------------------------------------------------------------------------------
def test_tick_and_limits_match_exchange_data():
    # số liệu thật VNDirect 2026-10-09: VNM tham chiếu 57.900 -> trần 61.900, sàn 53.900; PDV 9.050 -> 9.680/8.420; E1VFVN30 34.000 -> 36.380/31.620
    assert rules.limit_prices(57_900, "HOSE") == (61_900, 53_900)
    assert rules.limit_prices(9_050, "HOSE") == (9_680, 8_420)
    assert rules.limit_prices(34_000, "HOSE", "ETF") == (36_380, 31_620)
    assert rules.limit_prices(14_000, "HNX") == (15_400, 12_600)
    assert rules.limit_prices(10_000, "UPCOM") == (11_500, 8_500)
    assert rules.tick_size("HOSE", 9_999) == 10 and rules.tick_size("HOSE", 10_000) == 50 and rules.tick_size("HOSE", 50_000) == 100


def test_tax_consistent_with_paper_trader():
    pr = rules.sell_proceeds(25_000, 1_000)
    assert pr["tax"] == 25_000 and pr["gross"] == 25_000_000   # ví dụ PRO_WORKFLOW_GAPS: 1.000cp x 25.000đ -> thuế 25.000đ
    assert rules.SELL_TAX * 1e4 == 10.0 and rules.BROKER_FEE_REF * 1e4 == 15.0   # = sell_tax_bps / commission_bps của equity_vn trong paper-trader


def test_sessions():
    assert rules.session_status(utc(2026, 10, 12, 9, 5))["code"] == "ato"               # T2 09:05 HOSE
    assert rules.session_status(utc(2026, 10, 12, 9, 5), "HNX")["code"] == "continuous"
    assert rules.session_status(utc(2026, 10, 12, 10, 0))["code"] == "continuous"
    assert rules.session_status(utc(2026, 10, 12, 12, 0))["code"] == "lunch"
    assert rules.session_status(utc(2026, 10, 12, 14, 35))["code"] == "atc"
    assert rules.session_status(utc(2026, 10, 12, 14, 35), "UPCOM")["code"] == "continuous"
    s = rules.session_status(utc(2026, 10, 12, 16, 0))
    assert s["code"] == "closed" and s["next_at"].startswith("2026-10-13T08:30")
    w = rules.session_status(utc(2026, 10, 10, 10, 0))                                    # T7
    assert w["code"] == "closed" and w["next_at"].startswith("2026-10-12T08:30") and w["label"] == "Cuối tuần"


def test_last_session_date():
    assert rules.last_session_date(utc(2026, 10, 12, 10, 0)) == "2026-10-09"   # T2 giữa phiên -> thứ 6 trước
    assert rules.last_session_date(utc(2026, 10, 12, 15, 20)) == "2026-10-12"
    assert rules.last_session_date(utc(2026, 10, 11, 12, 0)) == "2026-10-09"


# ---- analytics ------------------------------------------------------------------------------------------------------------------
def test_breadth_and_limits():
    b = an.breadth(sample_rows())
    assert b["ALL"]["total"] == 8                       # không tính ETF
    assert b["HOSE"]["advances"] == 2 and b["HOSE"]["declines"] == 3 and b["HOSE"]["unchanged"] == 1
    assert b["UPCOM"]["no_trade"] == 1
    assert b["HOSE"]["ceiling"] == 1 and b["HOSE"]["floor"] == 1
    lim = an.limit_hits(sample_rows())
    assert [x["code"] for x in lim["ceiling"]] == ["TLH"] and [x["code"] for x in lim["floor"]] == ["PDV"]


def test_movers_filters_liquidity_and_universe():
    g = an.movers(sample_rows(), "gainers", "all", 5)
    assert [x["code"] for x in g[:2]] == ["SHS", "TLH"]
    g2 = an.movers(sample_rows(), "gainers", "all", 5, min_value=5e9)
    assert [x["code"] for x in g2] == ["SHS", "VCB"]
    assert an.movers(sample_rows(), "losers", "vn30", 5)[0]["code"] == "HPG"
    assert an.movers(sample_rows(), "value", "all", 1)[0]["code"] == "VCB"
    assert an.movers(sample_rows(), "foreign_sell", "all", 1)[0]["code"] == "HPG"
    assert [x["code"] for x in an.movers(sample_rows(), "gainers", "etf", 5)] == []


def test_heatmap_structure():
    h = an.heatmap(sample_rows(), "all", "marketcap")
    names = {s["name"] for s in h["sectors"]}
    assert "Ngân hàng" in names and "Thép" in names and "Khác" not in names     # ABC không có vốn hoá
    bank = next(s for s in h["sectors"] if s["name"] == "Ngân hàng")
    assert bank["children"][0]["name"] == "VCB" and abs(bank["pct"]) < 2
    assert all(c["value"] > 0 for s in h["sectors"] for c in s["children"])
    assert an.heatmap(sample_rows(), "vn30", "value")["count"] == 4


def test_liquidity_label():
    from conftest import FakeStore
    import asyncio
    series = asyncio.run(FakeStore().liquidity_series(25))
    liq = an.liquidity(series)
    assert liq["ratio"] == 1.5 and liq["label"] == "sôi động" and liq["window"] == 20


def test_foreign_summary():
    f = an.foreign_summary(sample_rows(), 3)
    assert f["top_buy"][0]["code"] == "VCB" and f["top_sell"][0]["code"] == "HPG"
    assert f["top_buy"][0]["own_pct"] == 40.0
    assert round(f["totals"]["ALL"]["net"]) == round(sum(r["f_net"] for r in sample_rows()))


def test_rsi_and_technicals():
    up = [float(i) for i in range(1, 40)]
    assert an.rsi(up) == 100.0
    assert an.rsi([1.0, 2.0]) is None
    flat = [10.0] * 3 + [10 + (-1) ** i for i in range(40)]
    assert 30 < an.rsi(flat) < 70


def test_screen_filters_and_estimates():
    rows = sample_rows()
    r = an.screen(rows, {}, {"pe": (None, 13.0)}, universe="vn100")
    assert {x["code"] for x in r["rows"]} == {"VCB", "BID", "VNM"}              # HPG pe=15 loại
    vcb = next(x for x in r["rows"] if x["code"] == "VCB")
    assert vcb["eps"] == round(61_000 / 12.0, 2) and vcb["roe"] == round(2.0 / 12.0 * 100, 2)
    assert an.screen(rows, {}, {"roe": (20, None)}, universe="all")["total"] == 0
    s = an.screen(rows, {}, {}, universe="vn100", sort="pe", desc=False)
    assert s["rows"][0]["pe"] <= s["rows"][-1]["pe"]
    # mã thiếu dữ liệu tiêu chí -> bị loại
    assert "ABC" not in {x["code"] for x in an.screen(rows, {}, {"pe": (0, 100)}, universe="all")["rows"]}


def test_news_tagging():
    items = [{"url": "1", "title": "VCB và HPG dẫn dắt", "summary": ""}, {"url": "2", "title": "GDP và USD tăng", "summary": "CPI"},
             {"url": "3", "title": "VCB TĂNG GIÁ MẠNH", "summary": ""}, {"url": "4", "title": "Cổ phiếu vcb thường", "summary": ""},
             {"url": "5", "title": "Giá nhà TP.HCM tăng, chủ đầu tư HPG.", "summary": ""}]
    out = newsmod.tag_news(items, ["VCB", "HPG", "GDP", "USD", "HCM"])
    assert [o["url"] for o in out] == ["1", "5"] and out[0]["codes"] == ["VCB", "HPG"] and out[1]["codes"] == ["HPG"]


def test_universe_seed_loaded():
    seed = universe.load_seed()
    assert len(seed["groups"]["VN30"]) == 30 and len(seed["groups"]["HNX30"]) == 30 and len(seed["groups"]["VN100"]) == 100
    assert universe.industry_of("VCB")[1] == "Ngân hàng"
    assert "E1VFVN30" in universe.etf_codes()
    assert universe.group_members("VN30") <= universe.group_members("VN100")
    e = universe.enrich_symbol({"code": "vcb", "floor": "HOSE", "kind": "STOCK"})
    assert e["in_vn30"] and e["focus"] and e["industry_name"] == "Ngân hàng"
