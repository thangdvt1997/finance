import asyncio
from datetime import datetime, timezone

import fakeredis
import pytest
from tscommon.events import make_event

from storage_writer.mapping import MAPPERS, MappingError, map_event
from storage_writer.writer import DLQ_STREAM, GROUP, StorageWriter


class FakeDB:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    async def execute_many(self, stmts):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("db down")
        self.calls.append(stmts)

    async def close(self):
        pass


SAMPLES = {
    "md.bars": ("bar", dict(symbol="EURUSD", tf="M1", ts_open="2026-01-01T00:00:00Z", o=1, h=2, l=0.5, c=1.5, v=10, source="x")),
    "md.quotes": ("quote", dict(symbol="EURUSD", bid=1.1, ask=1.2, ts="2026-01-01T00:00:00Z", source="x")),
    "news.items": ("news", dict(url="http://a", title="t", summary="s", published_at="2026-01-01T00:00:00Z", source="rss", lang="en", symbols=["EURUSD"], sentiment=0.2)),
    "news.enriched": ("news_enriched", dict(url="http://a", title="t", source="rss", lang="en", sentiment=-0.4, label="negative", confidence=0.9, symbols=["XAUUSD"], topics=["inflation"], importance="high", model_version="finbert-int8@1")),
    "calendar.events": ("calendar", dict(event_id="e1", country="US", title="NFP", impact="high", ts="2026-01-01T13:30:00Z", forecast="1", previous="2", actual=None, source="ff")),
    "expert.profiles": ("expert_profile", dict(expert_id="x1", source="s", display_name="X One", url="http://x", reputation={"score": 80, "gain_pct": 50}, tracked=True)),
    "expert.signals": ("expert_signal", dict(expert_id="x1", source="s", symbol="XAUUSD", side="buy", entry=1, sl=0.9, tp=1.2, opened_at="2026-01-01T00:00:00Z", status="open", url="u", raw={"a": 1})),
    "expert.positions": ("expert_position", dict(expert_id="x1", source="s", symbol="XAUUSD", net_volume=1.5, avg_price=2000, as_of="2026-01-01T00:00:00Z", raw={})),
    "account.snapshots": ("account_snapshot", dict(account_id="a1", platform="mt5", balance=1, equity=2, margin=3, positions=[{"s": 1}], ts="2026-01-01T00:00:00Z")),
    "account.deals": ("account_deals", dict(account_id="a1", platform="mt5", deals=[dict(
        ticket="9001", position_id="9000", symbol="EURUSD", broker_symbol="EURUSD.m", side="buy", volume=0.1, price_open=1.08, price_close=1.085,
        sl=1.07, tp=0.0, time_open="2026-01-01T08:00:00Z", time_close="2026-01-01T09:00:00Z", profit=50.0, swap=-0.5, commission=-0.7,
        magic=7, comment="FIXTURE-JRN", reason="tp", source="mt5:a1")])),
    "alerts.out": ("alert", dict(level="warn", title="t", body="b", tags=["a"], dedupe_key="k")),
    "alerts.delivery": ("alert_delivered", dict(alert_event_id="ev-1", delivered=True, outcome="sent", ts="2026-01-01T00:00:00Z", level="warn", title="t", body="b", tags=["a"], dedupe_key="k")),
}


def ev_for(stream, **override):
    t, p = SAMPLES[stream]
    return make_event(t, "test", {**p, **override})


@pytest.mark.parametrize("stream", list(SAMPLES))
def test_mapping_all_streams(stream):
    stmts = map_event(stream, ev_for(stream))
    assert stmts and all("ON CONFLICT" in sql for sql, _ in stmts)
    for sql, args in stmts:
        # số placeholder = số tham số
        import re
        n = max(int(x) for x in re.findall(r"\$(\d+)", sql))
        assert n == len(args)
    assert set(SAMPLES) == set(MAPPERS)


def test_account_deals_mapping_idempotent_and_validated():
    ev = ev_for("account.deals")
    stmts = map_event("account.deals", ev)
    assert len(stmts) == 1 and "ON CONFLICT (account_id, ticket) DO UPDATE" in stmts[0][0]
    a = stmts[0][1]
    assert a[0] == "a1" and a[1] == "9001" and a[6] == "buy" and a[13] == datetime(2026, 1, 1, 9, tzinfo=timezone.utc) and a[17] == 7
    assert map_event("account.deals", ev)[0][1] == a  # cung su kien -> cung tham so (idempotent)
    d = ev.payload["deals"][0]
    two = ev_for("account.deals", deals=[d, {**d, "ticket": "9002", "side": "balance", "symbol": "", "profit": 100.0}])
    assert [s[1][1] for s in map_event("account.deals", two)] == ["9001", "9002"]
    for bad in ({**d, "side": "hold"}, {**d, "profit": "abc"}, {**d, "time_close": "x"}, {**d, "volume": None}, {k: v for k, v in d.items() if k != "ticket"}):
        with pytest.raises(MappingError):
            map_event("account.deals", ev_for("account.deals", deals=[bad]))
    with pytest.raises(MappingError):
        map_event("account.deals", ev_for("account.deals", deals="x"))


def test_bar_types():
    sql, args = map_event("md.bars", ev_for("md.bars"))[0]
    assert args[2] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert args[7] == 10.0


def test_mapping_errors():
    with pytest.raises(MappingError):
        map_event("md.bars", ev_for("md.bars", o=None))
    with pytest.raises(MappingError):
        map_event("md.bars", ev_for("md.bars", ts_open="not-a-date"))
    with pytest.raises(MappingError):
        map_event("expert.signals", ev_for("expert.signals", side="hold"))
    with pytest.raises(MappingError):
        map_event("nope", ev_for("md.bars"))


@pytest.fixture
async def redis():
    r = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield r
    await r.aclose()


async def publish(r, stream, ev):
    await r.xadd(stream, {"e": ev.model_dump_json()})


async def test_consume_all_and_ack(redis):
    db = FakeDB()
    w = StorageWriter(redis, db, block_ms=10, retry_base_s=0)
    await w.setup()
    for s in SAMPLES:
        await publish(redis, s, ev_for(s))
    n = await w.poll_once()
    assert n == len(SAMPLES)
    assert len(db.calls) == len(SAMPLES)
    for s in SAMPLES:
        assert (await redis.xpending(s, GROUP))["pending"] == 0
    assert await redis.xlen(DLQ_STREAM) == 0


async def test_bad_payload_to_dlq(redis):
    db = FakeDB()
    w = StorageWriter(redis, db, block_ms=10)
    await w.setup()
    await publish(redis, "md.bars", ev_for("md.bars", o=None))
    await redis.xadd("md.quotes", {"e": "{not json"})
    await redis.xadd("md.quotes", {"zzz": "1"})
    await w.poll_once()
    assert db.calls == []
    assert await redis.xlen(DLQ_STREAM) == 3
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0
    assert (await redis.xpending("md.quotes", GROUP))["pending"] == 0


async def test_db_retry_then_success(redis):
    db = FakeDB(fail_times=2)
    w = StorageWriter(redis, db, block_ms=10, retry_base_s=0, max_retries=3)
    await w.setup()
    await publish(redis, "md.bars", ev_for("md.bars"))
    await w.poll_once()
    assert len(db.calls) == 1
    assert await redis.xlen(DLQ_STREAM) == 0


async def test_db_outage_does_not_dlq_valid_event(redis):
    """Lỗi DB tạm thời (không biết ping được) KHÔNG đẩy sự kiện hợp lệ vào DLQ: giữ trong PEL, hồi phục thì ghi."""
    from storage_writer.writer import DBUnavailable
    db = FakeDB(fail_times=99)
    w = StorageWriter(redis, db, block_ms=10, retry_base_s=0, max_retries=2)
    await w.setup()
    await publish(redis, "alerts.out", ev_for("alerts.out"))
    with pytest.raises(DBUnavailable):
        await w.poll_once()
    assert await redis.xlen(DLQ_STREAM) == 0
    assert (await redis.xpending("alerts.out", GROUP))["pending"] == 1
    db.fail_times = 0  # DB hồi phục
    w.db_wait_cap_s = 0.01
    await w._drain_pending()
    assert len(db.calls) == 1
    assert await redis.xlen(DLQ_STREAM) == 0
    assert (await redis.xpending("alerts.out", GROUP))["pending"] == 0


class DataErr(Exception):
    sqlstate = "23502"


async def test_db_data_error_goes_to_dlq(redis):
    class BadDB(FakeDB):
        async def execute_many(self, stmts):
            raise DataErr("null value")
    w = StorageWriter(redis, BadDB(), block_ms=10, retry_base_s=0, max_retries=1)
    await w.setup()
    await publish(redis, "alerts.out", ev_for("alerts.out"))
    await w.poll_once()
    entries = await redis.xrange(DLQ_STREAM)
    assert len(entries) == 1 and entries[0][1]["reason"].startswith("db-data:")
    assert (await redis.xpending("alerts.out", GROUP))["pending"] == 0


async def test_db_alive_but_failing_is_poison(redis):
    class AliveBad(FakeDB):
        async def execute_many(self, stmts):
            raise RuntimeError("syntax error")

        async def ping(self):
            return None
    w = StorageWriter(redis, AliveBad(), block_ms=10, retry_base_s=0, max_retries=1)
    await w.setup()
    await publish(redis, "alerts.out", ev_for("alerts.out"))
    await w.poll_once()
    entries = await redis.xrange(DLQ_STREAM)
    assert len(entries) == 1 and entries[0][1]["reason"].startswith("db-poison:")


async def test_batch_single_transaction(redis):
    """Lô nhiều tin hợp lệ -> MỘT lần execute_many (một transaction) và ack hết."""
    from datetime import timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(50):
        await publish(redis, "md.bars", ev_for("md.bars", ts_open=(base + timedelta(minutes=i)).isoformat()))
    db = FakeDB()
    w = StorageWriter(redis, db, block_ms=10)
    await w.setup()
    assert await w.poll_once() == 50
    assert len(db.calls) == 1 and len(db.calls[0]) == 50
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0


async def test_batch_failure_falls_back_per_message(redis):
    """Một tin trong lô gây lỗi dữ liệu -> chỉ tin đó vào DLQ, các tin còn lại vẫn được ghi."""
    from datetime import timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class OneBad(FakeDB):
        async def execute_many(self, stmts):
            if len(stmts) > 1 or any(a[2].minute == 3 for _, a in stmts):
                raise DataErr("bad")
            self.calls.append(stmts)
    for i in range(6):
        await publish(redis, "md.bars", ev_for("md.bars", ts_open=(base + timedelta(minutes=i)).isoformat()))
    db = OneBad()
    w = StorageWriter(redis, db, block_ms=10, retry_base_s=0, max_retries=1)
    await w.setup()
    await w.poll_once()
    assert len(db.calls) == 5 and await redis.xlen(DLQ_STREAM) == 1
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0


async def test_pending_recovery(redis):
    """Message đã giao nhưng chưa ack (crash) được xử lý lại khi khởi động."""
    db = FakeDB()
    w = StorageWriter(redis, db, consumer="c1", block_ms=10)
    await w.setup()
    await publish(redis, "md.bars", ev_for("md.bars"))
    await redis.xreadgroup(GROUP, "c1", {"md.bars": ">"}, count=10)  # giao, không ack
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 1
    assert await w.poll_once(pending=True) == 1
    assert len(db.calls) == 1
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0


def test_expert_profile_upsert_args():
    sql, args = map_event("expert.profiles", ev_for("expert.profiles"))[0]
    assert "INSERT INTO experts" in sql and "DO UPDATE" in sql
    assert args[:4] == ("x1", "s", "X One", "http://x")
    import json
    assert json.loads(args[4]) == {"score": 80, "gain_pct": 50} and args[5] is True
    _, args2 = map_event("expert.profiles", ev_for("expert.profiles", tracked=False, reputation=None))[0]
    assert args2[5] is False and args2[4] == "{}"
    with pytest.raises(MappingError):
        map_event("expert.profiles", ev_for("expert.profiles", expert_id=None))


def test_alert_delivered_upsert_args():
    (sql, args), = map_event("alerts.delivery", ev_for("alerts.delivery"))
    assert "DO UPDATE SET delivered" in sql
    assert args[6] == "ev-1" and args[7] is True


def test_alert_delivered_requires_event_id():
    with pytest.raises(MappingError):
        map_event("alerts.delivery", ev_for("alerts.delivery", alert_event_id=None))


async def test_orphan_pel_reclaimed_by_other_consumer_no_duplicates(redis):
    """Consumer A nhận 100 tin rồi chết không ack; B (tên khác) reclaim xử lý đủ 100, không trùng DB."""
    from datetime import timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(100):
        await publish(redis, "md.bars", ev_for("md.bars", ts_open=(base + timedelta(minutes=i)).isoformat()))
    wa = StorageWriter(redis, FakeDB(), consumer="A", block_ms=10)
    await wa.setup()
    got = await redis.xreadgroup(GROUP, "A", {"md.bars": ">"}, count=100)  # A nhận rồi chết
    assert len(got[0][1]) == 100
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 100

    db = FakeDB()
    wb = StorageWriter(redis, db, consumer="B", block_ms=10, reclaim_min_idle_ms=0)
    assert await wb.poll_once(pending=True) == 0  # PEL của A không phải của B
    assert await wb.reclaim_once() == 100
    keys = [args[2] for stmts in db.calls for _, args in stmts]
    assert len(keys) == 100 and len(set(keys)) == 100  # đủ 100, không trùng
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0
    assert await wb.reclaim_once() == 0
    assert await redis.xlen(DLQ_STREAM) == 0


async def test_reclaim_respects_idle_and_poison_to_dlq(redis):
    await publish(redis, "md.bars", ev_for("md.bars"))
    wa = StorageWriter(redis, FakeDB(), consumer="A", block_ms=10)
    await wa.setup()
    await redis.xreadgroup(GROUP, "A", {"md.bars": ">"}, count=10)
    wb = StorageWriter(redis, FakeDB(), consumer="B", block_ms=10, reclaim_min_idle_ms=60_000)
    assert await wb.reclaim_once() == 0  # chưa đủ idle -> không cướp tin của consumer còn sống
    # message đã giao vượt max_deliveries (crash-loop) -> dlq
    wc = StorageWriter(redis, FakeDB(fail_times=0), consumer="C", block_ms=10, reclaim_min_idle_ms=0, max_deliveries=1)
    assert await wc.reclaim_once() == 0
    entries = await redis.xrange(DLQ_STREAM)
    assert len(entries) == 1 and entries[0][1]["reason"].startswith("max_deliveries")
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0


BAD_BARS = {
    "low_above_body": dict(o=1, h=2, l=1.2, c=1.5),
    "high_below_body": dict(o=1, h=1.4, l=0.5, c=1.5),
    "non_positive_price": dict(o=0, h=2, l=0, c=1),
    "bad_volume": dict(v=-5),
    "not_finite": dict(h=float("inf")),
}


@pytest.mark.parametrize("code", list(BAD_BARS))
def test_bar_validation_rejects(code):
    from storage_writer.mapping import InvalidBar
    with pytest.raises(InvalidBar) as ei:
        map_event("md.bars", ev_for("md.bars", **BAD_BARS[code]))
    assert ei.value.code == code


def test_bar_validation_accepts_edges():
    # doji / o=l / c=h / v=0 / v thiếu đều hợp lệ
    for kw in (dict(o=1, h=1, l=1, c=1), dict(o=1, h=2, l=1, c=2, v=0), dict(v=None)):
        assert map_event("md.bars", ev_for("md.bars", **kw))


async def test_invalid_bar_to_dlq_with_reason_and_metric(redis):
    from storage_writer.writer import INVALID
    db = FakeDB()
    w = StorageWriter(redis, db, block_ms=10)
    await w.setup()
    before = INVALID.labels("md.bars", "low_above_body")._value.get()
    await publish(redis, "md.bars", ev_for("md.bars", o=5, h=1, l=9, c=100, v=-5))  # ví dụ từ QA (M1)
    await publish(redis, "md.bars", ev_for("md.bars", **BAD_BARS["low_above_body"]))
    await publish(redis, "md.bars", ev_for("md.bars"))  # hợp lệ vẫn ghi
    await w.poll_once()
    assert len(db.calls) == 1
    entries = await redis.xrange(DLQ_STREAM)
    assert len(entries) == 2 and all("bar không hợp lệ" in e[1]["reason"] for e in entries)
    assert INVALID.labels("md.bars", "low_above_body")._value.get() == before + 1
    assert (await redis.xpending("md.bars", GROUP))["pending"] == 0


def test_news_enriched_core_columns_and_range(monkeypatch):
    monkeypatch.delenv("STORAGE_ENRICH_EXTENDED", raising=False)
    sql, args = map_event("news.enriched", ev_for("news.enriched"))[0]
    assert "sentiment_label" not in sql and args[:2] == ("http://a", "t") and args[3] == -0.4 and args[4] == ["XAUUSD"]
    with pytest.raises(MappingError):
        map_event("news.enriched", ev_for("news.enriched", sentiment=1.5))
    with pytest.raises(MappingError):
        map_event("news.enriched", ev_for("news.enriched", model_version=None))


def test_news_enriched_extended_columns(monkeypatch):
    monkeypatch.setenv("STORAGE_ENRICH_EXTENDED", "true")
    sql, args = map_event("news.enriched", ev_for("news.enriched"))[0]
    for col in ("sentiment_label", "topics", "importance", "nlp_model", "enriched_at"):
        assert col in sql
    assert args[8] == ["inflation"] and args[10] == "finbert-int8@1"


def test_news_items_upsert_keeps_enrichment():
    sql, _ = map_event("news.items", ev_for("news.items"))[0]
    assert "COALESCE(EXCLUDED.sentiment, news_items.sentiment)" in sql and "unnest(news_items.symbols" in sql


def test_calendar_extra_gated_by_env(monkeypatch):
    payload = dict(event_id="e1", country="US", title="CPI m/m", impact="high", ts="2026-10-14T12:30:00Z", forecast="0.3%",
                   previous="0.2%", actual="0.4%", source="faireconomy",
                   extra={"group": "us_cpi", "surprise": {"verdict": "good", "value": 0.1}})
    ev = make_event("calendar", "t", payload)
    monkeypatch.delenv("STORAGE_CALENDAR_EXTRA", raising=False)
    sql, args = map_event("calendar.events", ev)[0]
    assert "extra" not in sql and len(args) == 9  # chua ap migration -> khong dung cot moi
    monkeypatch.setenv("STORAGE_CALENDAR_EXTRA", "true")
    sql, args = map_event("calendar.events", ev)[0]
    assert "extra=EXCLUDED.extra" in sql and len(args) == 10 and '"us_cpi"' in args[9]
    ev2 = make_event("calendar", "t", {**payload, "extra": None})
    assert map_event("calendar.events", ev2)[0][1][9] is None


async def test_dlq_replay_cli_dry_run_then_apply(redis):
    from types import SimpleNamespace

    import storage_writer.dlq_replay as rp
    ev = ev_for("md.bars")
    await redis.xadd(DLQ_STREAM, {"stream": "md.bars", "msg_id": "1-0", "reason": "db-data: boom", "e": ev.model_dump_json(), "ts": "1"})
    await redis.xadd(DLQ_STREAM, {"stream": "md.bars", "msg_id": "2-0", "reason": "decode: bad", "e": "{x", "ts": "1"})

    rp.aioredis.from_url = lambda *a, **k: redis
    orig_aclose = getattr(redis, "aclose", None)
    redis.aclose = lambda: asyncio.sleep(0)
    args = SimpleNamespace(redis_url="x", since=None, stream=None, reason_prefix=None, include_bad=False, limit=0, apply=False)
    await rp.run(args)
    assert await redis.xlen(DLQ_STREAM) == 2 and await redis.xlen("md.bars") == 0  # dry-run
    args.apply = True
    await rp.run(args)
    assert await redis.xlen(DLQ_STREAM) == 1 and await redis.xlen("md.bars") == 1  # chỉ bản db-*, bản decode giữ lại
    if orig_aclose:
        redis.aclose = orig_aclose


# ---- account.snapshots: currency + lệnh chờ (account_orders) ----
def _snap(**kw):
    base = dict(account_id="mt5:1", platform="mt5", balance=1000, equity=990, margin=10, positions=[], ts="2026-01-01T10:00:00Z", currency="usd")
    return make_event("account_snapshot", "test", {**base, **kw})


ORD = dict(order_id="7001", symbol="EURUSD", broker_symbol="EURUSD.m", kind="buy_limit", volume=0.3, price=1.079, sl=1.075, tp=1.088,
           magic=5, comment="c", time_setup="2026-01-01T09:00:00Z")


def test_snapshot_currency_normalized_and_no_orders_key():
    stmts = map_event("account.snapshots", _snap())
    assert len(stmts) == 1 and stmts[0][1][-1] == "USD"                      # currency chuẩn hoá HOA
    assert map_event("account.snapshots", _snap(currency=""))[0][1][-1] is None
    assert map_event("account.snapshots", _snap(currency="x;drop table"))[0][1][-1] is None   # không phải mã tiền tệ -> bỏ
    assert len(map_event("account.snapshots", _snap(orders=None))) == 1       # không có danh sách lệnh chờ -> không đụng account_orders


def test_snapshot_orders_upsert_and_mark_removed():
    stmts = map_event("account.snapshots", _snap(orders=[ORD, {**ORD, "order_id": "7002", "kind": "weird"}]))
    assert len(stmts) == 4                                                   # snapshot + 2 upsert + 1 removed
    up = stmts[1]
    assert "ON CONFLICT (account_id, ticket)" in up[0] and "last_seen_at <= EXCLUDED.last_seen_at" in up[0]
    assert up[1][:3] == ("mt5:1", "7001", "mt5") and up[1][5] == "buy_limit" and stmts[2][1][5] == "other"
    rm = stmts[-1]
    assert "status='removed'" in rm[0] and rm[1][0] == "mt5:1" and rm[1][1] == ["7001", "7002"]
    import re
    for sql, args in stmts:
        assert max(int(x) for x in re.findall(r"\$(\d+)", sql)) == len(args)


def test_snapshot_empty_orders_removes_all_and_bad_orders_rejected():
    stmts = map_event("account.snapshots", _snap(orders=[]))
    assert len(stmts) == 2 and stmts[1][1][1] == []                          # danh sách rỗng = mọi lệnh chờ đã biến mất
    for bad in ("x", [1], [{"symbol": "EURUSD"}], [ORD] * 501, [{**ORD, "price": float("inf")}]):
        with pytest.raises(MappingError):
            map_event("account.snapshots", _snap(orders=bad))


def test_news_expert_opinion_gated_by_env(monkeypatch):
    payload = dict(url="http://op/1", title="Waller, X", source="expert:op:fed_waller", published_at="2026-10-12T10:00:00Z", lang="en",
                   symbols=["EURUSD"], expert={"expert_id": "op:fed_waller", "name": "Waller", "group": "cb_speech", "stance": "dovish",
                                               "stance_score": -0.4, "topics": ["lai_suat"], "credibility": 93})
    ev = make_event("news", "t", payload)
    monkeypatch.delenv("STORAGE_EXPERT_OPINIONS", raising=False)
    assert len(map_event("news.items", ev)) == 1
    monkeypatch.setenv("STORAGE_EXPERT_OPINIONS", "true")
    stmts = map_event("news.items", ev)
    assert len(stmts) == 2 and "expert_opinions" in stmts[1][0] and stmts[1][1][1] == "op:fed_waller" and stmts[1][1][5] == "dovish"
    assert len(map_event("news.items", ev_for("news.items"))) == 1  # tin thuong khong co 'expert'


def test_quote_store_throttle_non_full_symbols():
    from storage_writer import mapping as m
    m._QLAST.clear()

    def q(sym, sec, src="mt"):
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + sec
        return make_event("t", "quote", dict(symbol=sym, bid=1.0, ask=1.1, ts=datetime.fromtimestamp(ts, timezone.utc).isoformat(), source=src))
    n = lambda ev: len(m.map_quote(ev))  # noqa: E731
    assert [n(q("AUDDKK", s)) for s in (0, 0.3, 0.9, 1.0, 1.4)] == [1, 0, 0, 1, 0]   # toi da 1/s
    assert n(q("AUDDKK", 1.2, "other")) == 1                                      # khoa theo (symbol, nguon)
    assert [n(q("EURUSD", s)) for s in (0, 0.1, 0.2)] == [1, 1, 1]                 # 7 ma canon goc luu day du


async def test_quote_throttled_symbol_single_message_is_stored(redis):
    """Hoi quy: lo 1 tin (hoac fallback) khong duoc map lai -> map_quote co throttle se nuot mat quote dau tien cua ma khong thuoc _QFULL."""
    from storage_writer import mapping
    mapping._QLAST.pop(("QAHZ", "qa"), None)
    await publish(redis, "md.quotes", ev_for("md.quotes", symbol="QAHZ", source="qa", ts=datetime.now(timezone.utc).isoformat()))
    db = FakeDB()
    w = StorageWriter(redis, db, block_ms=10)
    await w.setup()
    assert await w.poll_once() == 1
    assert len(db.calls) == 1 and len(db.calls[0]) == 1
    assert (await redis.xpending("md.quotes", GROUP))["pending"] == 0
