"""Y kien chuyen gia: fixture rut gon tu phan hoi THAT 2026-10-12 (feed Fed, BIS, ING, Project Syndicate, Vietstock, Bluesky, Form 4)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import fakeredis.aioredis
import httpx
import pytest
from tscommon import Bus

from expert_collector import sources_loader as L
from expert_collector.collector import Collector
from expert_collector.config import ECConfig
from expert_collector.httpclient import PoliteClient
from expert_collector.opinion_catalog import CATALOG
from expert_collector.sources import opinion_feeds as O
from expert_collector.stance import classify_stance, detect_topics, is_finance_relevant, tag_symbols

FX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
BY = {e["id"]: e for e in CATALOG}


def rd(n):
    return (FX / n).read_text(encoding="utf-8")


def test_catalog_valid_unique_and_enough():
    ids = [e["id"] for e in CATALOG]
    urls = [e["url"] for e in CATALOG]
    assert len(ids) == len(set(ids)) and len(urls) == len(set(urls))
    assert len(CATALOG) >= 60 and not any(e['kind'] == 'form4' for e in CATALOG)
    for e in CATALOG:
        assert 0 <= e["cred"] <= 100 and e["kind"] in {"rss", "bsky", "form4"} and e["name"] and e["bias"]
        if e["kind"] != "bsky":
            assert e["url"].startswith("https://")
    # khong ten website/nha cung cap trong ten hien thi
    for e in CATALOG:
        for bad in ("vietstock", "cafef", "vneconomy", "tradingview", "myfxbook", "fxstreet", "substack", "bluesky", "youtube", "coindesk", "bankless", "syndicate"):
            assert bad not in e["name"].lower(), e["name"]


def test_fed_speeches_real():
    ops = O.parse_rss_opinions(rd("real_op_waller.xml"), BY["fed_waller"], NOW)
    assert len(ops) >= 1 and ops[0].url.startswith("https://www.federalreserve.gov/")
    assert ops[0].title.startswith("Waller,") and "EURUSD" in ops[0].symbols
    assert ops[0].stance in {"hawkish", "dovish", "neutral"}


def test_bis_ing_syndicate_real():
    assert O.parse_rss_opinions(rd("real_op_bis_speeches.xml"), BY["bis_cbspeeches"], NOW)
    ing = O.parse_rss_opinions(rd("real_op_ing.xml"), BY["ing_think"], NOW)
    assert ing and all(o.url and o.title for o in ing)
    ps = O.parse_rss_opinions(rd("real_op_projectsyndicate.xml"), BY["projectsyndicate"], NOW)
    assert ps and any(o.author for o in ps)  # co tac gia rieng tung bai


def test_vietnamese_opinions_real():
    ops = O.parse_rss_opinions(rd("real_op_vs_ykien.xml"), BY["vs_ykien"], NOW)
    assert ops and ops[0].lang == "vi" and "VN:VNINDEX" in ops[0].symbols


def test_bluesky_only_own_relevant_recent_posts():
    js = json.loads(rd("real_op_bsky.json"))
    cfg = BY["bsky_justinwolfers"]
    ops = O.parse_bsky_opinions(js, cfg, NOW)
    assert ops and all(o.url.startswith("https://bsky.app/profile/justinwolfers.bsky.social/post/") for o in ops)
    assert all(is_finance_relevant(o.title + o.summary) for o in ops)  # 'Come work with me!' (khong lien quan) bi loc
    # qua cu -> bo
    assert O.parse_bsky_opinions(js, cfg, datetime(2027, 1, 1, tzinfo=timezone.utc)) == []
    # repost/reply bi bo
    js2 = json.loads(json.dumps(js))
    for it in js2["feed"]:
        it["reason"] = {"$type": "repost"}
    assert O.parse_bsky_opinions(js2, cfg, NOW) == []


def test_form4_real_to_opinion():
    from expert_collector.providers_insiders import build_signals, parse_form4
    txs = parse_form4(rd("real_form4_P.xml"), "0001628280-26-065573") + parse_form4(rd("real_form4_S.xml"), "0001493152-26-046648")
    sigs = build_signals(txs, min_buy_usd=1000, min_sell_usd=1)
    assert any(s.side == "buy" for s in sigs)
    ops = [O.signal_to_opinion(s) for s in sigs]
    buy = next(o for o in ops if o.stance == "bullish")
    assert buy.symbols == ["US:REF"] and buy.title.startswith("Giao dich noi bo:") and "MUA" in buy.title and buy.url.endswith("-buy")
    assert buy.lang == "vi" and buy.raw["group"] == "insider"
    assert all(o.stance in {"bullish", "bearish"} for o in ops)


def test_html_list_profiles_real():
    from expert_collector import providers_htmllist as H
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    for key, cid in (("vcsc", "vn_vcsc_research"), ("vdsc", "vn_vdsc_daily"), ("phs", "vn_phs_daily"), ("shs", "vn_shs_daily")):
        cfg = {"id": cid, "kind": "html_list", "group": "bank_research", "lang": "vi", "mode": "mkt", "symbols": ["VN:VNINDEX"], "topics": []}
        ops = H.parse_html_list(rd(f"real_html_{key}.html"), cfg, now)
        assert ops, key
        assert all(o.url.startswith("https://") and o.title and o.published_at for o in ops), key
        assert not any(o.title.endswith(("Doanh Nghiệp", "Thị Trường")) for o in ops)
    assert H.parse_html_list("<html></html>", {"id": "vn_phs_daily", "kind": "html_list", "group": "x"}, now) == []


def test_stance_and_topics_rules():
    assert classify_stance("Fed signals further rate hikes as inflation remains elevated", mode="cb")[0] == "hawkish"
    assert classify_stance("Rate cuts likely as labor market softening", "disinflation continues", mode="cb")[0] == "dovish"
    assert classify_stance("Stocks rally to record high on resilient growth")[0] == "bullish"
    assert classify_stance("Recession fears trigger sell-off")[0] == "bearish"
    assert classify_stance("Lai suat giam, thi truong hoi phuc but pha")[0] == "bullish"
    assert classify_stance("Weekly review of the economy")[0] == "neutral"
    assert "lai_suat" in detect_topics("FOMC raises interest rates", "")
    assert tag_symbols("Gold and oil jump after Fed") >= ["XAUUSD", "USOIL"]
    assert not is_finance_relevant("Come work with me, we need a producer")


def test_loader_validates_dedupes_and_survives_bad_entries(tmp_path):
    (tmp_path / "a.yaml").write_text("""
- {id: good_one, name_display: Tac gia A, type: rss, url: https://example.org/a.xml, prior_score: 0.7, group: indep_macro, poll_minutes: 3}
- {id: BAD ID, name_display: x, type: rss, url: https://example.org/b.xml}
- {id: no_url, name_display: x, type: rss}
- {id: http_only, name_display: x, type: rss, url: http://example.org/c.xml}
- {id: weird_type, name_display: x, type: carrier_pigeon, url: https://example.org/d.xml}
- {id: bad_score, name_display: x, type: rss, url: https://example.org/e.xml, prior_score: 1.7}
- {id: dup_url, name_display: x, type: rss, url: https://example.org/a.xml}
- {id: waller_off, name_display: x, type: rss, url: https://example.org/f.xml, override: true}
- {id: fed_waller, name_display: Waller, type: rss, url: https://example.org/g.xml, override: true, enabled: false, prior_score: 0.5}
""", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("{ not: [valid", encoding="utf-8")
    entries, errs = L.load_yaml_entries(sorted(tmp_path.glob("*.yaml")))
    assert len(errs) >= 5 and any("b.yaml" in e for e in errs)
    merged, stats = L.merge(CATALOG, entries, {"fed_powell"})
    ids = {e["id"]: e for e in merged}
    assert ids["good_one"]["every"] == 300 and ids["good_one"]["cred"] == 70  # poll toi thieu 5 phut
    assert "dup_url" not in ids and stats["dup_url"] == 1
    assert ids["fed_waller"]["enabled"] is False and ids["fed_waller"]["cred"] == 50 and ids["fed_waller"]["url"].startswith("https://www.federalreserve.gov")
    assert ids["fed_powell"]["enabled"] is False  # EC_OPINION_DISABLE
    merged2, stats2, errs2 = L.load_all(tmp_path)
    assert stats2["invalid"] == len(errs2) and stats2["yaml"] >= 1


def _transport(routes):
    def h(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=routes[req.url.host]) if req.url.host in routes else httpx.Response(404)
    return httpx.MockTransport(h)


@pytest.fixture
async def bus():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield Bus(r)
    await r.aclose()


async def stream(bus, name):
    return [json.loads(f["e"]) for _, f in await bus.r.xrange(name)]


async def test_opinions_flow_to_news_and_profiles(bus):
    entries = [dict(BY["fed_waller"], url="https://www.federalreserve.gov/feeds/s_t_waller.xml"),
               dict(BY["ing_think"], cred=30)]  # diem thap -> khong theo doi
    client = PoliteClient("t/1 (c@x.io)", min_interval=0, cache_ttl=0, respect_robots=False,
                          transport=_transport({"www.federalreserve.gov": rd("real_op_waller.xml"), "think.ing.com": rd("real_op_ing.xml")}),
                          sleep=lambda s: __import__("asyncio").sleep(0))
    src = O.OpinionFeedsSource(client, entries)
    c = Collector([src], bus, ECConfig(), now=lambda: NOW)
    await c.poll_once()
    news = await stream(bus, "news.items")
    assert news, "phai co tin y kien"
    p = news[0]["payload"]
    assert p["source"] == "expert:op:fed_waller" and p["expert"]["label"] == "ý kiến tham khảo" and p["expert"]["group"] == "cb_speech"
    assert p["expert"]["stance"] in {"hawkish", "dovish", "neutral"} and p["expert"]["disclaimer"]
    assert not any(n["payload"]["source"].endswith("ing_think") for n in news)  # uy tin < 40 -> khong lay
    profs = {e["payload"]["expert_id"]: e["payload"] for e in await stream(bus, "expert.profiles")}
    assert profs["op:fed_waller"]["tracked"] is True and profs["op:ing_think"]["tracked"] is False
    assert profs["op:fed_waller"]["display_name"] == "Christopher Waller (Fed)"
    assert await stream(bus, "expert.signals") == [] and await stream(bus, "alerts.out") == []  # khong sinh khuyen nghi/alert
    n = len(news)
    await c.poll_once()  # dedupe + chu ky: khong phat lai
    assert len(await stream(bus, "news.items")) == n
    assert (await c.list_opinions_api("cb_speech"))[0]["expert_id"] == "op:fed_waller"


def test_real_sources_dir_valid_and_names_have_no_website():
    merged, stats, errs = L.load_all(Path(__file__).parents[1] / "config" / "sources.d")
    assert errs == [] and stats["enabled"] >= 150
    ids = [e["id"] for e in merged]
    assert len(ids) == len(set(ids))
    for e in merged:
        low = e["name"].lower()
        for bad in ("vietstock", "cafef", "vnexpress", "vneconomy", "investing.com", "fxstreet", "tradingview", "substack", "coindesk", "myfxbook"):
            assert bad not in low, (e["id"], e["name"])


def test_build_chuan_hoa_url_ngay_tuong_lai_va_entity():
    """QA vong 3: link http cung host feed https -> https; link tuong doi -> tuyet doi; ngay su kien tuong lai -> None; &amp;amp; -> &."""
    cfg = {"kind": "rss", "group": "g", "url": "https://www.vietstock.vn/rss/x.rss", "mode": "mkt"}
    far = datetime(2036, 1, 1, tzinfo=timezone.utc)
    op = O._build(cfg, "http://www.vietstock.vn/a.htm", "T&amp;amp;T Group", "", far)
    assert op.url == "https://www.vietstock.vn/a.htm" and op.title == "T&T Group" and op.published_at is None
    assert O._build(cfg, "/pressroom/releases/p1.php", "t", "", None).url == "https://www.vietstock.vn/pressroom/releases/p1.php"
    assert O._build(cfg, "http://other.example/a", "t", "", None).url == "http://other.example/a"


def test_rss_vn_mdy_pubdate_parsed():
    """QA vong 4: pubDate 'M/D/Y h:mm:ss PM' (gio VN) cua tuoitre/baochinhphu truoc day -> published_at NULL."""
    xml = ("<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
           "<item><title>Lãi suất ngân hàng tăng, giá vàng giảm mạnh</title><link>https://tuoitre.vn/a.htm</link>"
           "<pubDate>10/12/2026 6:54:00 PM</pubDate><description>lãi suất lạm phát tỷ giá</description></item>"
           "</channel></rss>")
    cfg = {"id": "vn_tt_business", "kind": "rss", "url": "https://tuoitre.vn/rss/kinh-doanh.rss", "lang": "vi", "group": "vn_analysis"}
    ops = O.parse_rss_opinions(xml, cfg, NOW)
    assert ops and ops[0].published_at == datetime(2026, 10, 12, 11, 54, tzinfo=timezone.utc)
    assert O._parse_mdy("13/40/2026 1:00:00 PM", 7) is None


def test_rss_near_future_date_clamped_to_now():
    """QA vong 4: ban tin ngay 15-10 dang toi 14-10 voi pubDate 15-10 00:00 (+07) -> published_at tuong lai vai gio -> kep ve now."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(hours=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml = ("<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
           "<item><title>Bản tin ngày mai: lãi suất, tỷ giá, chứng khoán</title><link>https://example.vn/a</link>"
           f"<pubDate>{soon}</pubDate><description>lãi suất tỷ giá chứng khoán</description></item></channel></rss>")
    cfg = {"id": "x", "kind": "rss", "url": "https://example.vn/rss", "lang": "vi", "group": "vn_analysis"}
    ops = O.parse_rss_opinions(xml, cfg, now)
    assert ops and ops[0].published_at <= datetime.now(timezone.utc)
