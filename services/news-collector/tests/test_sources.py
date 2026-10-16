import json

import httpx

from conftest import NOW, fx
from news_collector.alerts import upcoming_high
from news_collector.sources.calendar_sources import (FairEconomySource, OfficialCalendarSource, parse_bls_ics,
                                                     parse_faireconomy, parse_fomc)
from news_collector.sources.cot import CotSource
from news_collector.sources.gdelt import GdeltSource
from news_collector.sources.rss import RssSource, parse_feed
from news_collector.sources.sec13f import (Sec13FSource, find_infotable_name, latest_13f, parse_infotable)


# ---------- RSS ----------
def test_parse_rss_fed(make_ctx):
    ctx = make_ctx(lambda r: httpx.Response(200))
    out = parse_feed(fx("rss_fed.xml"), {"id": "fed", "lang": "en", "symbols": []}, ctx)
    assert len(out) == 2  # item thieu link bi bo
    p = out[0].payload
    assert p["url"].endswith("monetary20261028a.htm") and p["source"] == "fed" and p["lang"] == "en"
    assert p["published_at"] == "2026-10-28T18:00:00+00:00"
    assert "<p>" not in p["summary"] and p["sentiment"] is None
    assert "XAUUSD" in p["symbols"] and "EURUSD" in p["symbols"]  # Powell + gold
    assert out[0].dedupe_key == f"news:{p['url']}"


def test_parse_atom_vietnamese(make_ctx):
    ctx = make_ctx(lambda r: httpx.Response(200))
    out = parse_feed(fx("atom_vn.xml"), {"id": "vn", "lang": "vi"}, ctx)
    assert {"XAUUSD", "VN:VNINDEX", "VN:VNM"} <= set(out[0].payload["symbols"])


async def test_rss_source_skips_disabled_and_failing(make_ctx, tmp_path):
    seen = []
    (tmp_path / "feeds.yaml").write_text(
        "feeds:\n"
        "  - {id: ecb, url: 'https://www.ecb.europa.eu/rss/press.xml', lang: en, enabled: true}\n"
        "  - {id: fed, url: 'https://www.federalreserve.gov/feeds/press_all.xml', lang: en, enabled: true}\n"
        "  - {id: off, url: 'https://cafef.vn/off.rss', lang: vi, enabled: false}\n", encoding="utf-8")

    def handler(req):
        seen.append(str(req.url))
        if "ecb" in req.url.host:
            return httpx.Response(500)
        return httpx.Response(200, content=fx("rss_fed.xml"))
    ctx = make_ctx(handler)
    ctx.config_dir = tmp_path
    ctx.client.max_retries = 0
    out = await RssSource().fetch(ctx)
    assert out and not any("cafef" in u for u in seen)  # feed enabled:false bi bo qua
    assert any("ecb.europa.eu" in u for u in seen)


# ---------- GDELT ----------
async def test_gdelt(make_ctx):
    reqs = []

    def handler(req):
        reqs.append(req)
        return httpx.Response(200, content=fx("gdelt.json"))
    out = await GdeltSource().fetch(make_ctx(handler))
    assert len(reqs) == 4 and reqs[0].url.params["mode"] == "artlist"
    first = out[0].payload
    assert first["published_at"] == "2026-10-11T09:30:00+00:00" and first["lang"] == "en"
    assert first["source"] == "gdelt:news.example.com" and "XAUUSD" in first["symbols"]
    assert any(e.payload["lang"] == "vi" for e in out)


async def test_gdelt_non_json_is_tolerated(make_ctx):
    out = await GdeltSource().fetch(make_ctx(lambda r: httpx.Response(200, content=b"Please limit requests")))
    assert out == []


# ---------- Calendar ----------
def test_faireconomy():
    out = parse_faireconomy(fx("ff_week.json"))
    assert len(out) == 3  # ngay hong bi bo
    nfp = out[0].payload
    assert nfp["impact"] == "high" and nfp["ts"] == "2026-10-12T12:30:00+00:00" and nfp["country"] == "US"
    assert nfp["forecast"] == "150K" and nfp["actual"] is None and nfp["source"] == "faireconomy"
    assert out[1].payload["impact"] == "low" and out[1].payload["forecast"] is None
    assert out[2].payload["impact"] == "med" and out[2].payload["actual"] == "2.2%"
    assert out[0].payload["event_id"] == parse_faireconomy(fx("ff_week.json"))[0].payload["event_id"]  # on dinh


def test_faireconomy_actual_change_changes_dedupe_key():
    rows = json.loads(fx("ff_week.json"))
    a = parse_faireconomy(json.dumps(rows).encode())[0]
    rows[0]["actual"] = "160K"
    b = parse_faireconomy(json.dumps(rows).encode())[0]
    assert a.payload["event_id"] == b.payload["event_id"] and a.dedupe_key != b.dedupe_key


def test_bls_ics_and_impact():
    import yaml
    from conftest import CONFIG
    cfg = yaml.safe_load((CONFIG / "calendar_impact.yaml").read_text())
    out = {e.payload["title"]: e.payload for e in parse_bls_ics(fx("bls.ics"), cfg)}
    assert out["Employment Situation"]["ts"] == "2026-10-02T12:30:00+00:00"  # 08:30 EDT
    assert out["Employment Situation"]["impact"] == "high"
    assert out["Consumer Price Index"]["ts"] == "2026-10-14T12:30:00+00:00"
    assert out["Import and Export Prices"]["impact"] == "med"
    assert out["Import and Export Prices"]["ts"] == "2026-10-15T12:30:00+00:00"


def test_fomc():
    out = parse_fomc({"decision_dates": ["2026-10-28"]})
    assert out[0].payload["ts"] == "2026-10-28T18:00:00+00:00" and out[0].payload["impact"] == "high"


async def test_official_source_survives_bls_failure(make_ctx):
    ctx = make_ctx(lambda r: httpx.Response(404))
    out = await OfficialCalendarSource().fetch(ctx)
    assert out and all(e.payload["source"] == "fed" for e in out)


async def test_faireconomy_source_min_interval():
    assert FairEconomySource(60).interval >= 1800


def test_upcoming_high_alert_window_and_dedupe_key():
    evs = [e.payload for e in parse_faireconomy(fx("ff_week.json"))]
    nfp = evs[0]
    from datetime import datetime, timedelta
    ts = datetime.fromisoformat(nfp["ts"])
    assert upcoming_high(evs, ts - timedelta(minutes=45)) == []          # qua som
    assert upcoming_high(evs, ts + timedelta(minutes=1)) == []           # da qua
    al = upcoming_high(evs, ts - timedelta(minutes=29))
    assert len(al) == 1 and al[0].stream == "alerts"
    p = al[0].payload
    assert p["level"] == "warn" and p["dedupe_key"].startswith("cal:faireconomy:") and "calendar" in p["tags"]
    assert upcoming_high([evs[2]], ts - timedelta(minutes=29)) == []     # khong phai high


# ---------- COT ----------
async def test_cot(make_ctx):
    reqs = []

    def handler(req):
        reqs.append(req)
        return httpx.Response(200, content=fx("cot.json"))
    out = await CotSource().fetch(make_ctx(handler))
    assert "099741" in reqs[0].url.params["$where"]
    pos = {e.payload["symbol"]: e.payload for e in out if e.stream == "expert_positions"}
    assert set(pos) == {"EURUSD", "USDJPY"}  # ma la bi bo
    eur = pos["EURUSD"]
    assert eur["expert_id"] == "CFTC:099741" and eur["net_volume"] == 100000 and eur["source"] == "cftc"
    assert eur["as_of"] == "2026-10-06T00:00:00+00:00" and eur["raw"]["pair_direction"] == 1
    assert pos["USDJPY"]["net_volume"] == -50000 and pos["USDJPY"]["raw"]["pair_direction"] == -1
    news = [e for e in out if e.stream == "news"]
    assert len(news) == 1 and {"EURUSD", "USDJPY"} <= set(news[0].payload["symbols"])


# ---------- SEC 13F ----------
def test_13f_helpers():
    f = latest_13f(json.loads(fx("sec_submissions.json")))
    assert f["accession"] == "0001067983-26-000009" and f["report_date"] == "2026-06-30"  # bo /A va form khac
    assert find_infotable_name(json.loads(fx("sec_index.json"))) == "form13fInfoTable.xml"
    h = parse_infotable(fx("sec_infotable.xml"))
    assert h[0]["cusip"] == "037833100" and h[0]["value"] == 8000000 and h[0]["shares"] == 40000  # gop, bo option
    assert len(h) == 2


async def test_13f_source(make_ctx, tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        p = req.url.path
        if p.startswith("/submissions/"):
            return httpx.Response(200, content=fx("sec_submissions.json"))
        if p.endswith("index.json"):
            return httpx.Response(200, content=fx("sec_index.json"))
        if p.endswith("form13fInfoTable.xml"):
            return httpx.Response(200, content=fx("sec_infotable.xml"))
        return httpx.Response(404)
    ctx = make_ctx(handler)
    out = await Sec13FSource().fetch(ctx)
    assert any("CIK0001067983" in str(r.url) for r in seen)
    berk = [e.payload for e in out if e.payload["expert_id"] == "SEC13F:1067983"]
    aapl = next(p for p in berk if p["symbol"] == "US:AAPL")
    assert aapl["net_volume"] == 40000 and aapl["avg_price"] == 200.0 and aapl["as_of"] == "2026-06-30T00:00:00+00:00"
    assert any(p["symbol"] == "CUSIP:123456789" for p in berk)
    assert all(r.headers["user-agent"].count("@") == 1 for r in seen)


async def test_13f_requires_email_in_user_agent(make_ctx):
    ctx = make_ctx(lambda r: httpx.Response(500), user_agent="no-contact-bot/1.0")
    assert await Sec13FSource().fetch(ctx) == []


def test_parse_rss_vn_mdy_pubdate(make_ctx):
    """QA vong 4: tuoitre/baochinhphu dung pubDate 'M/D/Y h:mm:ss PM' gio VN -> truoc day published_at NULL."""
    ctx = make_ctx(lambda r: httpx.Response(200))
    xml = (b"<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
           b"<item><title>Bai 1</title><link>https://tuoitre.vn/a.htm</link><pubDate>10/14/2026 6:54:00 PM</pubDate></item>"
           b"<item><title>Bai 2</title><link>https://tuoitre.vn/b.htm</link><pubDate>10/2/2026 12:05:00 AM</pubDate></item>"
           b"<item><title>Bai 3</title><link>https://tuoitre.vn/c.htm</link><pubDate>khong ro</pubDate></item>"
           b"</channel></rss>")
    out = parse_feed(xml, {"id": "tuoitre_kinhdoanh", "lang": "vi", "symbols": []}, ctx)
    got = [o.payload["published_at"] for o in out]
    assert got == ["2026-10-14T11:54:00+00:00", "2026-10-01T17:05:00+00:00", None]
    # feed tieng Anh khong khai bao tz -> coi la UTC
    out = parse_feed(xml, {"id": "x", "lang": "en", "tz_offset_h": 0}, ctx)
    assert out[0].payload["published_at"] == "2026-10-14T18:54:00+00:00"


def test_parse_rss_drops_too_old_items(make_ctx):
    """QA vong 4: feed BLS tra ban tin luu tru 2025, Guardian tra bai 2014 -> bo bai cu hon max_age_days (mac dinh 180)."""
    ctx = make_ctx(lambda r: httpx.Response(200))
    xml = (b"<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
           b"<item><title>Old CPI</title><link>https://www.bls.gov/news.release/archives/cpi_09112025.htm</link>"
           b"<pubDate>Thu, 11 Sep 2025 12:30:00 GMT</pubDate></item>"
           b"<item><title>New CPI</title><link>https://www.bls.gov/news.release/cpi.htm</link>"
           b"<pubDate>Fri, 10 Oct 2026 12:30:00 GMT</pubDate></item>"
           b"<item><title>No date</title><link>https://www.bls.gov/x.htm</link></item>"
           b"</channel></rss>")
    out = parse_feed(xml, {"id": "bls_cpi", "lang": "en"}, ctx)
    assert [o.payload["title"] for o in out] == ["New CPI", "No date"]
    assert len(parse_feed(xml, {"id": "bls_cpi", "lang": "en", "max_age_days": 800}, ctx)) == 3
