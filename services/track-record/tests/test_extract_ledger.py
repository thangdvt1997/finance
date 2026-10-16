from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

import pytest

from conftest import UTC
from track_record import extract, ledger
from track_record.store import MemStore

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
SRC = ["cafef_chungkhoan", "fxstreet_news", "boe_speeches", "vneconomy_taichinh", "investinglive", "bbc_business"]


_D = object()


def news(src="fxstreet_news", s=0.6, syms=("EURUSD",), pub=_D, ing=None, enr=None):
    ing = ing or datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    return {"source": src, "lang": "en", "published_at": ing - timedelta(minutes=5) if pub is _D else pub, "ingested_at": ing, "enriched_at": enr,
            "symbols": list(syms), "sentiment": s}


def hp(sym):
    return sym in {"EURUSD", "XAUUSD", "GBPUSD", "VN:FPT", "USDJPY"}


def test_news_threshold_symbols_and_price_filter():
    rows = [news(s=0.2), news(s=-0.5), news(syms=("EURUSD", "VN:ZZZ", "XAUUSD", "GBPUSD", "USDJPY"), s=0.9), news(syms=())]
    v = extract.news_views(rows, hp, NOW)
    assert len(v) == 1 + 3                               # |s|<0,35 bi bo; bai 2 chi giu toi da 3 ma co gia (VN:ZZZ bi loai)
    assert {x["direction"] for x in v} == {"bullish", "bearish"}
    assert "VN:ZZZ" not in {x["symbol"] for x in v}


def test_news_observed_is_max_of_publish_ingest_enrich_and_invalid_publish():
    ing = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    v = extract.news_views([news(pub=ing - timedelta(days=30), ing=ing, enr=ing + timedelta(hours=3))], hp, NOW)[0]
    assert v["observed_at"] == ing + timedelta(hours=3) and v["published_at"] == ing - timedelta(days=30)
    v = extract.news_views([news(pub=None, ing=ing)], hp, NOW)[0]
    assert v["published_at"] == ing                      # khong co published_at -> dung ingested_at
    v = extract.news_views([news(pub=ing + timedelta(days=9), ing=ing)], hp, NOW)[0]
    assert v["published_at"] == ing                      # tuong lai -> khong hop le


def test_cot_publish_time_and_stance():
    as_of = datetime(2026, 10, 6, tzinfo=UTC)            # thu Ba
    assert extract.cot_published_at(as_of) == datetime(2026, 10, 9, 20, 30, tzinfo=UTC)   # thu Sau 20:30 UTC
    rows = [
        {"expert_id": "CFTC:1", "source": "cftc", "symbol": "EURUSD", "as_of": as_of, "net_volume": -99, "raw": {"noncomm_long": 10.0, "noncomm_short": 110.0, "pair_direction": 1}},
        {"expert_id": "CFTC:2", "source": "cftc", "symbol": "USDJPY", "as_of": as_of, "net_volume": -5, "raw": {"noncomm_long": 10.0, "noncomm_short": 20.0, "pair_direction": -1}},
        {"expert_id": "CFTC:3", "source": "cftc", "symbol": "XAUUSD", "as_of": datetime(2026, 10, 10, tzinfo=UTC), "net_volume": 5, "raw": {"noncomm_long": 20.0, "noncomm_short": 10.0}},
    ]
    v = {x["symbol"]: x for x in extract.cot_views(rows, NOW)}
    assert v["EURUSD"]["direction"] == "bearish" and v["USDJPY"]["direction"] == "bullish"
    assert "XAUUSD" not in v                              # chua cong bo (as_of + 3 ngay > now) => khong dung
    assert v["EURUSD"]["observed_at"] > as_of and v["EURUSD"]["label"] == "Vị thế đầu cơ — EUR" and v["USDJPY"]["label"].endswith("JPY")


def test_signals_basic():
    rows = [{"expert_id": "e1", "symbol": "EURUSD", "side": "buy", "opened_at": NOW - timedelta(days=3), "sl": 1.05},
            {"expert_id": "e1", "symbol": "EURUSD", "side": "flat", "opened_at": NOW - timedelta(days=2), "sl": None}]
    v = extract.signal_views(rows, {"e1": "An Nguyen"}, NOW)
    assert len(v) == 1 and v[0]["label"] == "An Nguyen" and v[0]["invalidation"] == 1.05 and v[0]["direction"] == "bullish"


def test_merge_daily_conflict_drops_day_and_only_closed_days():
    t = datetime(2026, 10, 5, 8, tzinfo=UTC)
    base = dict(entity_id="ent:aaaa0000", symbol="EURUSD", kind="media", lang="en", group=None, label=None, invalidation=None, horizon_hint=None, basis="news")
    c = [dict(base, direction="bullish", observed_at=t, published_at=t), dict(base, direction="bearish", observed_at=t + timedelta(hours=2), published_at=t),
         dict(base, direction="bullish", observed_at=t + timedelta(days=1), published_at=t), dict(base, direction="bullish", observed_at=t + timedelta(days=1, hours=1), published_at=t),
         dict(base, direction="bullish", observed_at=NOW, published_at=NOW)]
    m = extract.merge_daily(c, NOW.date())
    assert len(m) == 1 and m[0]["observed_at"] == t + timedelta(days=1)       # ngay mau thuan bi bo; ngay hien tai chua dong
    assert extract.merge_daily(c, NOW.date())[0]["ref"] == m[0]["ref"]        # ref on dinh (idempotent)


async def test_labels_never_leak_source_names():
    rows = [news(src=s, s=0.7) for s in SRC]
    rows.append(news(src="cafef_chungkhoan", s=-0.7, ing=datetime(2026, 10, 6, 10, tzinfo=UTC)))
    st = MemStore()
    await st.append_views(extract.merge_daily(extract.news_views(rows, hp, NOW), NOW.date()))
    blob = json.dumps(list((await st.entities_all()).values()) + await st.views(), default=str).lower()
    for s in SRC:
        assert s not in blob
        for tok in s.split("_"):
            if len(tok) > 3 and tok != "news":
                assert tok not in blob, tok
    labels = sorted(e["label"] for e in (await st.entities_all()).values())
    assert all(lb.rsplit(" #", 1)[0] in ("Luồng tin", "Ngân hàng trung ương", "Báo kinh tế") for lb in labels)
    assert len(set(labels)) == len(labels)
    assert all(e["entity_id"].startswith("ent:") and len(e["entity_id"]) == 12 for e in (await st.entities_all()).values())


async def test_ledger_idempotent_and_detects_tamper():
    st = MemStore()
    rows = [news(src="fxstreet_news", s=0.7, ing=datetime(2026, 10, d, 10, tzinfo=UTC)) for d in range(1, 8)]
    views = extract.merge_daily(extract.news_views(rows, hp, NOW), NOW.date())
    assert await st.append_views(views) == 7
    assert await st.append_views(views) == 0             # idempotent theo ref
    res = await st.verify()
    assert res["ok"] and res["n"] == 7
    st.rows[3]["direction"] = "bearish" if st.rows[3]["direction"] == "bullish" else "bullish"   # sua lich su truc tiep
    res = await st.verify()
    assert not res["ok"] and res["first_bad_seq"] == st.rows[3]["seq"] and res["reason"] == "hash"
    st.rows[3]["direction"] = "bullish" if st.rows[3]["direction"] == "bearish" else "bearish"
    assert (await st.verify())["ok"]
    del st.rows[2]                                         # xoa dong giua chuoi
    assert not (await st.verify())["ok"]


@pytest.mark.skipif(not os.getenv("TRACKREC_TEST_DSN"), reason="can Postgres (chay tren VPS voi TRACKREC_TEST_DSN = superuser)")
async def test_pg_chain_detects_superuser_edit():
    import asyncpg
    from track_record.store import PgStore

    dsn = os.environ["TRACKREC_TEST_DSN"]
    c = await asyncpg.connect(dsn)
    await c.execute("DROP SCHEMA IF EXISTS trtest CASCADE; CREATE SCHEMA trtest")
    await c.execute("SET search_path=trtest")
    mig = open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "db", "migrations", "016_track_record.sql"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra")) else os.environ["TRACKREC_TEST_MIGRATION"]
    await c.execute(mig)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2, server_settings={"search_path": "trtest"})
    st = PgStore(pool)
    rows = [news(src="fxstreet_news", s=0.7, ing=datetime(2026, 10, d, 10, tzinfo=UTC)) for d in range(1, 6)]
    views = extract.merge_daily(extract.news_views(rows, hp, NOW), NOW.date())
    assert await st.append_views(views) == 5 and await st.append_views(views) == 0
    assert (await st.verify())["ok"]
    with pytest.raises(asyncpg.PostgresError):
        await c.execute("UPDATE tr_views SET direction='bearish' WHERE seq=2")        # trigger chan
    with pytest.raises(asyncpg.PostgresError):
        await c.execute("DELETE FROM tr_views WHERE seq=2")
    with pytest.raises(asyncpg.PostgresError):
        await c.execute("TRUNCATE tr_views")
    await c.execute("ALTER TABLE tr_views DISABLE TRIGGER tr_views_no_update")       # superuser vo hieu hoa trigger roi sua
    await c.execute("UPDATE tr_views SET symbol='XAUUSD' WHERE seq=3")
    res = await st.verify()
    assert not res["ok"] and res["first_bad_seq"] == 3
    await pool.close()
    await c.execute("DROP SCHEMA trtest CASCADE")
    await c.close()
