from __future__ import annotations

import pytest
from conftest import dt, five_trades, mk
from fastapi.testclient import TestClient
from tscommon import risk_windows as rw

from journal.app import create_app
from journal.notes import MemNotes
from journal.source import MemSource

ACC = [{"account_id": "demo-mt5-01", "kind": "mt", "platform": "mt5", "n_trades": 5, "first_ts": dt(1, 9), "last_ts": dt(3, 9), "source": "mt5:demo-mt5-01"}]


def client(trades=None, balance=1120.0, accounts=None, events=None):
    src = MemSource(accounts or ACC, {"demo-mt5-01": trades if trades is not None else five_trades()}, {"demo-mt5-01": balance}, events=events)
    return TestClient(create_app(src, MemNotes(), rw.load_config()))


def test_accounts_and_404():
    with client() as c:
        a = c.get("/journal/accounts").json()
        assert a["read_only"] is True and a["items"][0]["account_id"] == "demo-mt5-01" and a["items"][0]["n_trades"] == 5
        assert c.get("/journal/nope/summary").status_code == 404
        assert c.get("/journal/bad id!/summary").status_code in (404, 422)
        assert c.get("/journal/demo-mt5-01/summary?tz=../../etc/passwd").status_code == 422
        assert c.get("/journal/demo-mt5-01/summary?from=not-a-date").status_code == 422


def test_summary_base_derived_from_balance_and_matches_hand_numbers():
    with client() as c:
        j = c.get("/journal/demo-mt5-01/summary?tz=UTC").json()
        s = j["summary"]
        assert s["n"] == 5 and s["net"] == 120.0 and s["win_rate"] == 0.6 and s["profit_factor"] == pytest.approx(2.7143, abs=1e-4)
        # so du hien tai 1120 - tong net 120 = base 1000 -> duong von khop tinh tay
        assert j["base_source"] == "balance_now_minus_history" and j["equity"]["start"] == 1000.0
        assert j["equity"]["max_dd"] == 50.0 and j["equity"]["max_dd_pct"] == pytest.approx(4.5455, abs=1e-3)
        assert [r["ea"] for r in j["contribution"]] == ["magic:7", "manual"] or {r["ea"] for r in j["contribution"]} == {"magic:7", "manual"}
        shares = {r["ea"]: r["share_pct"] for r in j["contribution"]}
        assert shares["magic:7"] == pytest.approx(110 / 120 * 100, abs=0.01) and shares["manual"] == pytest.approx(10 / 120 * 100, abs=0.01)
        assert [d["date"] for d in j["calendar"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
        # loc theo ngay
        j2 = c.get("/journal/demo-mt5-01/summary?tz=UTC&from=2026-10-02&to=2026-10-02").json()
        assert j2["summary"]["n"] == 2 and j2["summary"]["net"] == 10.0 and j2["equity"]["start"] == 1050.0  # base cua cua so = 1000 + net truoc do (50)
        j3 = c.get("/journal/demo-mt5-01/summary?group=magic:7&tz=UTC").json()
        assert j3["summary"]["n"] == 3 and j3["filtered"] is True


def test_deals_sort_filter_page_and_flags():
    with client() as c:
        d = c.get("/journal/demo-mt5-01/deals?tz=UTC&sort=net&order=desc&limit=2").json()
        assert d["total"] == 5 and [x["net"] for x in d["items"]] == [100.0, 60.0]
        assert c.get("/journal/demo-mt5-01/deals?outcome=loss").json()["total"] == 2
        assert c.get("/journal/demo-mt5-01/deals?sort=DROP").status_code == 422
        assert c.get("/journal/demo-mt5-01/deals?limit=501").status_code == 422
        first = c.get("/journal/demo-mt5-01/deals?sort=time_close&order=asc&limit=1&offset=1").json()["items"][0]
        assert first["ticket"] == "2" and first["note"] is None
        assert "no_sl" in first["flags"]  # five_trades khong dat SL


def test_notes_put_tag_filter_review_and_delete():
    with client() as c:
        body = {"tags": ["Setup:Breakout", "emo:fomo", "setup:breakout"], "note": "Vào sớm trước nến xác nhận", "rating": 2}
        r = c.put("/journal/demo-mt5-01/notes/deal/2", json=body)
        assert r.status_code == 200 and r.json()["tags"] == ["setup:breakout", "emo:fomo"] and r.json()["rating"] == 2
        assert c.put("/journal/demo-mt5-01/notes/deal/9999", json={"tags": []}).status_code == 404  # deal khong ton tai
        for bad in ({"tags": ["BAD TAG!"]}, {"tags": ["x"] * 13}, {"note": "x" * 4001}, {"rating": 9}, {"extra": 1}):
            assert c.put("/journal/demo-mt5-01/notes/deal/2", json=bad).status_code == 422, bad
        assert c.put("/journal/demo-mt5-01/notes/week/2026-W99x", json={}).status_code == 422
        assert c.put("/journal/demo-mt5-01/notes/foo/1", json={}).status_code == 422
        assert c.put("/journal/demo-mt5-01/notes/week/2026-W40", json={"note": "Tuần tốt", "tags": ["review"]}).status_code == 200
        d = c.get("/journal/demo-mt5-01/deals?tag=emo:fomo").json()
        assert d["total"] == 1 and d["items"][0]["ticket"] == "2" and d["items"][0]["note"]["note"].startswith("Vào sớm")
        assert {t["tag"] for t in d["tags"]} == {"setup:breakout", "emo:fomo", "review"}
        rv = c.get("/journal/demo-mt5-01/review?week=2026-W40&tz=UTC").json()
        assert rv["week"] == "2026-W40" and rv["summary"]["n"] == 5 and rv["review"]["note"] == "Tuần tốt" and rv["tags"][0]["n"] == 1
        assert rv["discipline"]["score"] is not None and isinstance(rv["insights"], list)
        assert c.delete("/journal/demo-mt5-01/notes/deal/2").status_code == 200
        assert c.delete("/journal/demo-mt5-01/notes/deal/2").status_code == 404


def test_review_empty_week_and_prev_delta():
    with client() as c:
        rv = c.get("/journal/demo-mt5-01/review?week=2026-W10&tz=UTC").json()
        assert rv["summary"]["n"] == 0 and rv["insights"] == ["Không có lệnh nào đóng trong tuần này."]
        assert c.get("/journal/demo-mt5-01/review?week=2026W40").status_code == 422


def test_discipline_endpoint_with_news_and_excursions():
    ev = [{"event_id": "e", "source": "ff", "country": "US", "title": "CPI m/m", "impact": "high", "ts": dt(1, 10, 10), "extra": None}]
    tr = five_trades()
    bars = {("EURUSD", "M1"): [{"ts": dt(1, 8, m), "h": 1.102, "l": 1.098} for m in range(0, 60)]}
    src = MemSource(ACC, {"demo-mt5-01": tr}, {"demo-mt5-01": 1120.0}, events=ev, bars=bars)
    with TestClient(create_app(src, MemNotes(), rw.load_config())) as c:
        d = c.get("/journal/demo-mt5-01/discipline?tz=UTC").json()
        by_rule = {r["rule"]: r for r in d["rules"]}
        assert by_rule["news_window"]["count"] == 1  # lenh 2 vao 10:00, tin 10:10: trong cua so (truoc 15 phut)
        e = c.get("/journal/demo-mt5-01/excursions?tz=UTC&limit=5").json()
        assert e["requested"] == 5 and e["covered"] == 1 and e["items"][0]["ticket"] == "1"
        assert e["items"][0]["mfe"] == pytest.approx(0.002, abs=1e-6)


def test_paper_account_without_sl_rule_and_no_balance():
    acc = [{"account_id": "p1", "kind": "paper", "platform": "paper", "strategy": "trend", "initial_capital": 100000.0, "n_fills": 2, "first_ts": dt(1), "last_ts": dt(2)}]
    src = MemSource(acc, {"p1": [mk(1, profit=500, to=dt(1, 8), tc=dt(2, 8)), mk(2, profit=-200, to=dt(2, 9), tc=dt(3, 9))]})
    with TestClient(create_app(src, MemNotes(), rw.load_config())) as c:
        j = c.get("/journal/p1/summary?tz=UTC").json()
        assert j["base_source"] == "paper_initial_capital" and j["equity"]["start"] == 100000.0 and j["equity"]["end"] == 100300.0
        d = c.get("/journal/p1/discipline").json()
        assert "no_sl" not in {x["rule"] for x in d["rules"] if x["count"]}


def test_no_write_routes_beyond_notes():
    with client() as c:
        for method, path in [("POST", "/journal/demo-mt5-01/summary"), ("PUT", "/journal/demo-mt5-01/deals"), ("DELETE", "/journal/demo-mt5-01/summary"),
                             ("POST", "/journal/demo-mt5-01/notes/deal/1"), ("PUT", "/journal/accounts")]:
            assert c.request(method, path, json={}).status_code in (404, 405), (method, path)
