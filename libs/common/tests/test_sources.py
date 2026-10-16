import pytest

from tscommon import sources
from tscommon.sources import has_source_name, scrub_obj, scrub_sources, scrub_tags

STRICT = ["dukascopy", "frankfurter", "yahoo", "vnstock", "vndirect", "tcbs", "okx", "kucoin", "bitfinex", "kraken", "ccxt",
          "alpaca", "tiingo", "edgar", "gdelt", "marketaux", "oanda", "truefx", "twelvedata", "faireconomy", "forexfactory",
          "myfxbook", "mql5", "actionforex", "reuters", "cafef", "vnexpress", "vietstock", "vneconomy", "tuoitre", "bbc",
          "guardian", "fxstreet", "investinglive", "oilprice", "baochinhphu"]


def test_issue_example_technical_alert():
    assert scrub_sources("dukascopy lỗi lấy dữ liệu GBPUSD M1") == "dữ liệu giá GBPUSD M1: lỗi cập nhật"
    assert scrub_sources("dukascopy loi lay du lieu GBPUSD M1") == "dữ liệu giá GBPUSD M1: lỗi cập nhật"
    assert scrub_sources("DUKASCOPY lỗi lấy dữ liệu XAUUSD H1") == "dữ liệu giá XAUUSD H1: lỗi cập nhật"


def test_other_collector_titles():
    assert scrub_sources("yahoo_daily tra du lieu rong lien tuc (EURUSD D1)") == "dữ liệu giá EURUSD D1: rỗng liên tục"
    assert scrub_sources("frankfurter: 3 ngay du lieu con thieu") == "dữ liệu giá: 3 ngày còn thiếu"
    out = scrub_sources("Lech gia EURUSD: yahoo_daily vs dukascopy")
    assert out == "Lech gia EURUSD: lệch giữa hai luồng giá" and "yahoo" not in out.lower()


@pytest.mark.parametrize("name", STRICT)
@pytest.mark.parametrize("fmt", ["Nguồn: {n}", "{n} lỗi", "Tin từ {N} hôm nay", "(theo {n})", "see https://www.{n}.com/path?x=1", "{N}.com thông báo"])
def test_no_name_survives(name, fmt):
    for n in (name, name.upper(), name.title()):
        text = fmt.format(n=n, N=n.upper())
        out = scrub_sources(text)
        assert name not in out.lower(), (text, out)


@pytest.mark.parametrize("text", ["ECB giữ nguyên lãi suất", "Fed tăng lãi suất", "Giá FRED:DGS10 tăng", "Biểu đồ SEC filing", "gate mở cửa",
                                  "CFTC COT report cho thấy", "Chỉ số tiếp cận BLS lao động"])
def test_ambiguous_names_in_content_kept(text):
    assert scrub_sources(text) == text.replace("  ", " ")


def test_contextual_names_removed_in_attribution():
    for t in ("Nguồn: ECB", "theo FRED", "BLS API lỗi", "ssi feed down", "via cftc"):
        out = scrub_sources(t)
        assert not has_source_name(out) and not any(w in out.lower().split() for w in ("ecb", "fred", "bls", "ssi", "cftc")), out


def test_ids_domains_urls():
    assert "fed_press_all" not in scrub_sources("feed fed_press_all lỗi")
    assert "vietstock" not in scrub_sources("vietstock_cophieu chậm").lower()
    assert scrub_sources("Xem https://www.federalreserve.gov/newsevents/x.htm") == "Xem"
    assert scrub_sources("Xem https://example.org/a") == "Xem https://example.org/a"
    assert "reuters" not in scrub_sources("Reuters - Vàng tăng").lower()
    assert scrub_sources("Vàng tăng - Reuters") == "Vàng tăng"
    assert scrub_sources("Fair Economy, ForexFactory và Myfxbook cập nhật").lower().count("forex") == 0
    assert "twelve" not in scrub_sources("Twelve Data timeout").lower()


def test_content_unchanged_and_idempotent():
    for t in ("Giá EURUSD tăng 0.5%", "Lịch: CPI Mỹ lúc 19:30", "VN:VNM 57.700 +1.2%", "", "RSI 62, ADX 28"):
        assert scrub_sources(t) == t
    s = scrub_sources("Nguồn: dukascopy. dukascopy lỗi lấy dữ liệu GBPUSD M1")
    assert scrub_sources(s) == s
    assert scrub_sources(None) is None and scrub_sources(5) == 5


def test_scrub_tags_keeps_routing():
    assert scrub_tags(["market-collector", "dukascopy", "GBPUSD", "ch:ntfy", "rule:5", "rss:actionforex"]) == \
        ["market-collector", "GBPUSD", "ch:ntfy", "rule:5"]


def test_scrub_obj_keys_and_values():
    o = {"symbol": "EURUSD", "source": "dukascopy", "provider": "x", "forecast_source": "faireconomy", "price_source": "quote",
         "source_kind": "mt5", "acct": {"source": "sim:abc"}, "title": "Reuters - Vàng tăng", "url": "https://www.reuters.com/a",
         "items": [{"source": "yahoo_daily", "c": 1.0}, {"source": "bls_cpi"}], "tags": ["dukascopy", "ok"], "expert_id": "rss:actionforex_weekly"}
    r = scrub_obj(o)
    assert "source" not in r and "provider" not in r and "forecast_source" not in r
    assert r["price_source"] == "quote" and r["acct"] == {"source": "sim:abc"}
    assert r["title"] == "Vàng tăng" and r["url"] == "https://www.reuters.com/a"
    assert r["items"] == [{"c": 1.0}, {}] and r["tags"] == ["ok"] and r["expert_id"] == "rss:actionforex_weekly"
    r2 = scrub_obj(o, drop_keys=False, neutral="-")
    assert r2["source"] == "-" and r2["provider"] == "-"


def test_config_override(tmp_path, monkeypatch):
    f = tmp_path / "s.yaml"
    f.write_text("strict: [acmefeed]\nreplacement: 'dữ liệu'\n", encoding="utf-8")
    monkeypatch.setenv("SOURCES_CONFIG", str(f))
    sources.reload()
    try:
        assert scrub_sources("AcmeFeed lỗi") == "dữ liệu lỗi"
        assert scrub_sources("dukascopy lỗi") == "dukascopy lỗi"
    finally:
        monkeypatch.delenv("SOURCES_CONFIG")
        sources.reload()


def test_real_world_values_from_db():
    # gia tri source thuc te trong DB (bars/news/calendar/experts) bi bo; dinh danh tai khoan MT khong phai nguon
    for v in ("dukascopy", "yahoo_daily", "frankfurter", "crypto_ccxt", "fred", "bls_cpi", "fed_press_all", "boe", "boj", "ecb", "cftc",
              "faireconomy", "baochinhphu_kinhte", "vietstock_ptkt", "tuoitre_kinhdoanh", "vneconomy_taichinh", "cafef_vimo", "investinglive"):
        assert scrub_obj({"source": v}) == {}, v
    assert scrub_obj({"source": "mt5:demo-mt5-01"}) == {"source": "mt5:demo-mt5-01"}
    assert "vietstock" not in scrub_sources("Theo dữ liệu của VietstockFinance, tuần giao dịch").lower()
