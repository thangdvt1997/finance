"""Hoi quy: rac kiem thu (source='qa', tai khoan qa-*/mt5:99xxxxxx) khong duoc lot vao truy van nguoi dung/alert."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = {
    "services/api-gateway/src/api_gateway/intel_data.py": 3,   # news list, news item, calendar
    "services/api-gateway/src/api_gateway/pg_repo.py": 2,      # news, calendar
    "services/alert-rules/src/alert_rules/market.py": 1,       # calendar
    "services/briefing/src/briefing/source.py": 2,             # news, calendar
    "services/journal/src/journal/source.py": 1,               # calendar
}


def test_queries_exclude_qa_source():
    for rel, minimum in SRC.items():
        txt = (ROOT / rel).read_text(encoding="utf-8")
        n = len(re.findall(r"(?i)<>\s*'qa'", txt))
        assert n >= minimum, f"{rel}: chi {n} bo loc source<>'qa' (can >= {minimum})"


def test_risk_query_skips_qa_accounts():
    txt = (ROOT / "services/alert-rules/src/alert_rules/market.py").read_text(encoding="utf-8")
    m = re.search(r"account_id !~ '([^']+)' OR l\.account_id = '([^']+)'", txt)
    assert m, "thieu bo loc tai khoan qa trong truy van rui ro"
    rx, keep = m.group(1), m.group(2)
    assert re.match(rx, "qa-fleet-1") and re.match(rx, "mt5:99000007")
    assert not re.match(rx, "mt5:100000001") and not re.match(rx, "demo-mt4-01")
    assert keep == "mt5:99000001"


def test_cleanup_deletes_qa_rows():
    txt = (ROOT / "tests/e2e/cleanup.py").read_text(encoding="utf-8")
    for needle in ("DELETE FROM news_items", "DELETE FROM calendar_events WHERE source='qa'", "symbol >= 'QA'"):
        assert needle in txt
