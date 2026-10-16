from pathlib import Path

from nlp import entities, topics
from nlp.summarize import extract_summary

CONFIG = Path(__file__).resolve().parents[1] / "config"
RULES, PFX = entities.load(CONFIG / "entities.yaml")
TM = topics.load(CONFIG / "topics.yaml")


def tag(text, existing=()):
    return entities.tag_symbols(text, RULES, PFX, existing)


def test_symbols_currency_gold_oil_index_cb():
    assert "EURUSD" in tag("Euro falls to 17-month low against dollar")
    assert "XAUUSD" in tag("Giá vàng miếng SJC tăng 2 tuần liên tiếp")
    assert "USOIL" in tag("Oil prices jump 5% on Middle East tensions")
    assert "US:SPX" in tag("S&P 500 jumps as yields ease")
    assert "USDJPY" in tag("Bank of Japan holds rates, Ueda says")
    assert "VN:VNINDEX" in tag("VN-Index lùi về dưới mốc 1,740 điểm")
    assert "BTCUSD" in tag("Bitcoin sellers had their shot")


def test_vn_tickers_case_sensitive_and_cashtag():
    assert "VN:PNJ" in tag("Cổ phiếu PNJ và Novaland đồng loạt tăng trần")
    assert "VN:PNJ" not in tag("pnj gold")
    assert "US:AAPL" in tag("Buy $AAPL and $TSLA now")
    assert "US:TSLA" in tag("Buy $AAPL and $TSLA now")


def test_case_sensitive_short_words_no_false_positive():
    assert "EURUSD" not in tag("The cattle were fed hay in the lane")      # 'fed', 'lane'
    assert "XAUUSD" in tag("The Fed holds rates")
    assert "GBPUSD" not in tag("cable car opens")


def test_existing_symbols_preserved_first():
    out = tag("Euro falls", existing=["XAGUSD"])
    assert out[0] == "XAGUSD" and "EURUSD" in out and len(out) == len(set(out))


def test_topics():
    assert topics.classify_topics("Fed signals rate cut as CPI cools", TM)[0] in {"monetary_policy", "inflation"}
    assert "inflation" in topics.classify_topics("CPI for all items rises 0.6% in April", TM)
    assert "jobs" in topics.classify_topics("Nonfarm payrolls beat, unemployment falls", TM)
    assert "geopolitics" in topics.classify_topics("Oil jumps on Middle East tensions and missile attack", TM)
    assert "sovereign_rating" in topics.classify_topics("Việt Nam lần đầu được nâng hạng tín nhiệm đầu tư", TM)
    assert topics.classify_topics("zzz qqq", TM) == []


def test_importance_levels():
    hi = topics.importance("CPI for all items surges 0.9% in April, record jump", ["inflation"], 4, "bls_cpi", 0.5, 0.9, TM)
    lo = topics.importance("Bài phát biểu: speech by a new director at lecture", [], 0, "snb_press", 0.0, 0.5, TM)
    assert hi[0] == "high" and lo[0] == "low" and 0 <= lo[1] < hi[1] <= 1


def test_summary_extractive_only():
    body = ("The central bank raised rates by 25 basis points on Wednesday. Officials said inflation remains too high and "
            "signalled further tightening. Markets had expected a pause. The dollar rallied against major peers. "
            "Analysts at several banks revised their forecasts for the year. Bond yields rose across the curve.")
    s = extract_summary("Central bank raises rates", body, "en", min_chars=200)
    assert s and len(s) <= 300
    for sent in [x for x in s.replace("…", "").split(". ") if len(x) > 25]:
        assert sent.strip(". ") in body                      # chỉ trích câu có sẵn, không bịa
    assert extract_summary("t", "ngắn", "en") is None
    assert extract_summary("t", body, "en", min_chars=10_000) is None
    vi = extract_summary("t", "Câu thứ nhất khá dài để vượt ngưỡng. " * 12, "vi", min_chars=100)
    assert vi and vi.startswith("Câu thứ nhất")
