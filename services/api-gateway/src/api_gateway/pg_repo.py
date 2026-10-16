from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

Row = dict[str, Any]


def _rec(r: asyncpg.Record) -> Row:
    d = dict(r)
    for k in ("positions", "reputation", "raw", "payload", "extra", "orders"):  # jsonb có thể trả về str
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


class PgRepo:
    """Truy vấn tham số hoá (không nối chuỗi từ input). Chỉ SELECT; nên dùng role DB chỉ-đọc."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.cal_extra = False  # cot calendar_events.extra (migration 003) ton tai?

    @classmethod
    async def connect(cls, dsn: str) -> "PgRepo":
        self = cls(await asyncpg.create_pool(dsn, min_size=2, max_size=int(os.getenv("PG_POOL_MAX", "20")), command_timeout=15, max_inactive_connection_lifetime=300))
        self.cal_extra = bool(await self.pool.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_name='calendar_events' AND column_name='extra'"))
        self._warm_task = asyncio.ensure_future(self._warm_loop())
        return self

    async def _warm_loop(self) -> None:
        """Lam nong bo nho symbols/D1 dinh ky de request khong bao gio gap cache nguoi (RS-3)."""
        while True:
            for key, fn in (("symbols", self._symbols_q), ("d1", self._d1_q)):
                try:
                    self._memo[key] = (await fn(), time.monotonic() + self._MEMO_TTL)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - DB loi tam thoi: giu ban cu, thu lai vong sau
                    pass
            await asyncio.sleep(self._MEMO_TTL * 0.8)

    async def close(self) -> None:
        t = getattr(self, "_warm_task", None)
        if t:
            t.cancel()
        await self.pool.close()

    async def _q(self, sql: str, *args) -> list[Row]:
        async with self.pool.acquire() as c:
            return [_rec(r) for r in await c.fetch(sql, *args)]

    async def ping(self) -> bool:
        async with self.pool.acquire() as c:
            return (await c.fetchval("SELECT 1")) == 1

    # Bộ nhớ "khoảng lịch sử đã biết" theo (symbol, tf): bars là hypertable chunk 7 ngày (~1900 chunk, dữ liệu từ 1989) — truy vấn `ORDER BY ts_open DESC LIMIT n`
    # KHÔNG có cận dưới mà chuỗi có < n nến sẽ duyệt MỌI chunk (EURUSD H1: 174 nến, ~2-4s/truy vấn, 770k buffer). Khi kết quả desc/offset=0 trả ít hơn `limit` nghĩa là đã thấy
    # toàn bộ lịch sử => nến cũ nhất là cận dưới an toàn; các truy vấn sau thêm cận này (ts_open >= cận) để loại chunk. TTL 10 phút (nến backfill cũ hơn cận có thể trễ ≤10 phút).
    _SPAN_TTL = 600.0
    _span: dict[tuple[str, str], tuple[datetime, float]] = {}

    async def bars(self, symbol, tf, start, end, order, limit, offset):
        direction = "DESC" if order == "desc" else "ASC"  # whitelist, không lấy từ input thô
        k = (symbol, tf)
        bound = None
        if start is None and order == "desc":
            hit = self._span.get(k)
            if hit and hit[1] > time.monotonic():
                bound = hit[0]
        rows = await self._q(
            "SELECT symbol, tf, ts_open, o, h, l, c, v, source FROM bars "
            "WHERE symbol=$1 AND tf=$2 AND ($3::timestamptz IS NULL OR ts_open >= $3) "
            "AND ($4::timestamptz IS NULL OR ts_open <= $4) "
            f"ORDER BY ts_open {direction} LIMIT $5 OFFSET $6",
            symbol, tf, start if start is not None else bound, end, limit, offset)
        if start is None and order == "desc" and offset == 0 and rows and len(rows) < limit:
            if len(self._span) > 5000:
                self._span.clear()
            self._span[k] = (min(r["ts_open"] for r in rows), time.monotonic() + self._SPAN_TTL)
        return rows

    async def quotes_latest(self, symbols, limit):
        since = datetime.now(timezone.utc) - timedelta(days=7)  # cắt chunk hypertable
        # Mỗi symbol lấy 1 tick mới nhất bằng LATERAL + LIMIT 1 trên PK (symbol, ts, source): ~0,3 s thay vì DISTINCT ON quét ~4,6M dòng 7 ngày (18 s -> statement timeout).
        # Tập symbol: danh sách yêu cầu, hoặc các symbol có trong cagg quotes_1m 7 ngày.
        return await self._q(
            "SELECT q.symbol, q.ts, q.bid, q.ask, q.source FROM "
            "(SELECT unnest($2::text[]) AS symbol UNION "
            " SELECT DISTINCT symbol FROM quotes_1m WHERE $2::text[] IS NULL AND bucket > $1) s "
            "CROSS JOIN LATERAL (SELECT symbol, ts, bid, ask, source FROM quotes "
            " WHERE symbol = s.symbol AND ts > $1 ORDER BY ts DESC LIMIT 1) q ORDER BY q.symbol LIMIT $3",
            since, symbols or None, limit)

    async def news(self, symbol, since, limit, offset):
        # Bo trung hien thi (QA vong 4): cung tieu de chuan hoa + cung ngay UTC tu nhieu nguon (bao dang lai, repost)
        # -> giu 1 dong: uu tien nguon tin (khong phai y kien chuyen gia), roi ban dang som nhat.
        # Chi xet cua so ung vien moi nhat (3x trang + 50) de van dung index theo thoi gian.
        return await self._q(
            "WITH c AS (SELECT url, title, summary, published_at, source, lang, symbols, sentiment, "
            " COALESCE(published_at, ingested_at) AS ts_, regexp_replace(lower(title), '\\W+', ' ', 'g') AS k_ FROM news_items "
            " WHERE COALESCE(source,'') <> 'qa' AND ($1::text IS NULL OR $1 = ANY(symbols)) "
            " AND ($2::timestamptz IS NULL OR COALESCE(published_at, ingested_at) >= $2) "
            " ORDER BY COALESCE(published_at, ingested_at) DESC NULLS LAST, url LIMIT ($3::int + $4::int) * 3 + 50), "
            "d AS (SELECT DISTINCT ON (k_, (ts_ AT TIME ZONE 'UTC')::date) * FROM c "
            " ORDER BY k_, (ts_ AT TIME ZONE 'UTC')::date, (source LIKE 'expert:%'), ts_, url) "
            "SELECT url, title, summary, published_at, source, lang, symbols, sentiment FROM d "
            "ORDER BY ts_ DESC NULLS LAST, url LIMIT $3 OFFSET $4", symbol, since, limit, offset)

    _CAL_ORDER = {
        # sắp tới (ts >= now) tăng dần trước, rồi quá khứ mới -> cũ
        "upcoming": "(ts < $6::timestamptz), CASE WHEN ts >= $6::timestamptz THEN ts END ASC, ts DESC, event_id",
        "asc": "ts ASC, event_id",
        "desc": "ts DESC, event_id",
    }

    async def calendar(self, start, end, impact, limit, offset, order="upcoming", now=None):
        now = now or datetime.now(timezone.utc)
        return await self._q(
            "SELECT event_id, source, country, title, impact, ts, forecast, previous, actual, "
            + ("extra" if self.cal_extra else "NULL::jsonb AS extra") + " FROM calendar_events "
            "WHERE COALESCE(source,'') <> 'qa' AND ($1::timestamptz IS NULL OR ts >= $1) AND ($2::timestamptz IS NULL OR ts <= $2) "
            "AND ($3::text[] IS NULL OR impact = ANY($3)) ORDER BY " + self._CAL_ORDER[order] +
            " LIMIT $4 OFFSET $5", start, end, impact or None, limit, offset, *([now] if order == "upcoming" else []))

    async def experts(self, limit, offset):
        return await self._q(
            "SELECT expert_id, source, display_name, url, reputation, tracked FROM experts "
            "ORDER BY expert_id LIMIT $1 OFFSET $2", limit, offset)

    async def expert_signals(self, symbol, status, expert_id, limit, offset):
        return await self._q(
            "SELECT expert_id, source, symbol, side, opened_at, entry, sl, tp, status, url FROM expert_signals "
            "WHERE ($1::text IS NULL OR symbol=$1) AND ($2::text IS NULL OR status=$2) "
            "AND ($3::text IS NULL OR expert_id=$3) ORDER BY opened_at DESC LIMIT $4 OFFSET $5",
            symbol, status, expert_id, limit, offset)

    async def expert_positions(self, symbol, expert_id, limit, offset):
        return await self._q(
            "SELECT expert_id, source, symbol, as_of, net_volume, avg_price FROM expert_positions "
            "WHERE ($1::text IS NULL OR symbol=$1) AND ($2::text IS NULL OR expert_id=$2) "
            "ORDER BY as_of DESC LIMIT $3 OFFSET $4", symbol, expert_id, limit, offset)

    async def expert_opinions(self, group, stance, symbol, expert_id, limit, offset):
        try:
            return await self._q(
                "SELECT url, expert_id, name, grp, title, stance, stance_score, topics, symbols, credibility, published_at, lang "
                "FROM expert_opinions WHERE ($1::text IS NULL OR grp=$1) AND ($2::text IS NULL OR stance=$2) "
                "AND ($3::text IS NULL OR $3 = ANY(symbols)) AND ($4::text IS NULL OR expert_id=$4) "
                "ORDER BY published_at DESC NULLS LAST LIMIT $5 OFFSET $6", group, stance, symbol, expert_id, limit, offset)
        except Exception:  # noqa: BLE001 - chua ap migration 017
            return []

    async def accounts_latest(self):
        """Snapshot mới nhất mỗi tài khoản + currency + lệnh chờ ĐANG MỞ (account_orders). Chưa áp migration 013 -> truy vấn cũ."""
        try:
            return await self._q(
                "WITH l AS (SELECT DISTINCT ON (account_id) account_id, platform, ts, balance, equity, margin, positions, currency "
                "FROM account_snapshots WHERE ts > now() - interval '30 days' ORDER BY account_id, ts DESC) "
                "SELECT l.*, COALESCE((SELECT jsonb_agg(jsonb_build_object('order_id', o.ticket, 'symbol', o.symbol, 'kind', o.kind, "
                "'volume', o.volume, 'price', o.price, 'sl', o.sl, 'tp', o.tp, 'time_setup', o.time_setup) ORDER BY o.time_setup, o.ticket) "
                "FROM account_orders o WHERE o.account_id = l.account_id AND o.status = 'open'), '[]'::jsonb) AS orders "
                "FROM l ORDER BY l.account_id")
        except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
            return await self._q(
                "SELECT DISTINCT ON (account_id) account_id, platform, ts, balance, equity, margin, positions "
                "FROM account_snapshots WHERE ts > now() - interval '30 days' ORDER BY account_id, ts DESC")

    async def account_orders(self, account_id, status, limit):
        """Lệnh chờ của 1 tài khoản. status: open | removed | all (removed: chỉ 7 ngày gần nhất). Bảng chưa có -> []."""
        try:
            return await self._q(
                "SELECT ticket AS order_id, symbol, kind, volume, price, sl, tp, magic, comment, time_setup, status, first_seen_at, last_seen_at, removed_at "
                "FROM account_orders WHERE account_id=$1 AND ($2::text = 'all' OR status = $2) "
                "AND (status = 'open' OR removed_at > now() - interval '7 days') "
                "ORDER BY (status = 'open') DESC, COALESCE(time_setup, first_seen_at) DESC, ticket LIMIT $3", account_id, status, limit)
        except asyncpg.UndefinedTableError:
            return []

    async def alerts(self, level, limit, offset):
        return await self._q(
            "SELECT id, ts, level, title, body, tags, dedupe_key, delivered FROM alerts "
            "WHERE ($1::text IS NULL OR level=$1) ORDER BY ts DESC LIMIT $2 OFFSET $3", level, limit, offset)

    # Bo nho SWR cho truy van tong hop nang (symbols ~1 s, price_snapshot ~1 s khi nguoi dung nguoi/ tai cao): tra ban cu ngay, lam moi nen (single-flight).
    _MEMO_TTL = 45.0
    _memo: dict[str, tuple[Any, float]] = {}
    _memo_fly: dict[str, "asyncio.Task"] = {}

    async def _memoized(self, key: str, fn):
        hit = self._memo.get(key)
        now = time.monotonic()
        if hit and hit[1] > now:
            return hit[0]
        task = self._memo_fly.get(key)
        if task is None or task.done():
            async def run():
                try:
                    val = await fn()
                    self._memo[key] = (val, time.monotonic() + self._MEMO_TTL)
                    return val
                finally:
                    self._memo_fly.pop(key, None)
            task = self._memo_fly[key] = asyncio.ensure_future(run())
        if hit:   # stale-while-revalidate: co ban cu (toi da 10 phut) -> tra ngay
            if now - (hit[1] - self._MEMO_TTL) < 600:
                return hit[0]
        return await asyncio.shield(task)

    async def symbols(self):
        return [dict(r) for r in await self._memoized("symbols", self._symbols_q)]

    async def _symbols_q(self):
        since = datetime.now(timezone.utc) - timedelta(days=30)  # cắt chunk hypertable
        return await self._q(
            "WITH b0 AS (SELECT symbol, tf, max(ts_open) AS lb FROM bars WHERE ts_open > $1 GROUP BY symbol, tf), "
            # W1/MN1 mở nến thưa (tuần/tháng): cửa sổ 30 ngày bỏ sót MN1 -> thêm cửa sổ 120 ngày riêng cho 2 khung này
            "bl AS (SELECT symbol, tf, max(ts_open) AS lb FROM bars WHERE tf IN ('W1','MN1') AND ts_open > $1 - interval '90 days' "
            "GROUP BY symbol, tf), "
            "bu AS (SELECT * FROM b0 UNION ALL SELECT * FROM bl), "
            "b AS (SELECT symbol, array_agg(DISTINCT tf) AS tfs, max(lb) AS last_bar FROM bu GROUP BY symbol), "
            "q AS (SELECT symbol, max(ts) AS last_quote FROM quotes WHERE ts > $2 GROUP BY symbol) "
            "SELECT COALESCE(b.symbol, q.symbol) AS symbol, COALESCE(b.tfs, '{}') AS tfs, b.last_bar, q.last_quote "
            "FROM b FULL JOIN q ON b.symbol = q.symbol ORDER BY 1", since, datetime.now(timezone.utc) - timedelta(days=7))

    async def price_snapshot(self):
        quotes = {r["symbol"]: r for r in await self.quotes_latest(None, 10_000)}   # quote luon moi; chi D1 (cham) duoc nho dem
        return {"quotes": quotes, "d1": await self._memoized("d1", self._d1_q)}

    async def _d1_q(self):
        now = datetime.now(timezone.utc)
        rows = await self._q(
            "SELECT symbol, ts_open, c FROM (SELECT symbol, ts_open, c, row_number() OVER (PARTITION BY symbol ORDER BY ts_open DESC) AS rn "
            "FROM (SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, c FROM bars WHERE tf = 'D1' AND ts_open > $1 "
            "ORDER BY symbol, ts_open DESC, source) d) x WHERE rn <= 3 ORDER BY symbol, ts_open DESC", now - timedelta(days=45))
        d1: dict[str, list[Row]] = {}
        for r in rows:
            d1.setdefault(r["symbol"], []).append({"ts_open": r["ts_open"], "c": r["c"]})
        return d1

    async def equity_history(self, account_id, start, end, limit):
        rows = await self._q(
            "SELECT ts, balance, equity, margin FROM account_snapshots WHERE account_id=$1 "
            "AND ($2::timestamptz IS NULL OR ts >= $2) AND ($3::timestamptz IS NULL OR ts <= $3) "
            "ORDER BY ts DESC LIMIT $4", account_id, start or datetime.now(timezone.utc) - timedelta(days=30), end, limit)
        return rows[::-1]

    async def freshness(self):
        # mỗi bảng 1 truy vấn nhỏ có cắt thời gian; tên bảng/cột cố định (không từ input)
        spec = [("bars", "bars", "ts_open"), ("quotes", "quotes", "ts"), ("news_items", "news", "COALESCE(published_at, ingested_at)"),
                ("calendar_events", "calendar", "ts"), ("expert_signals", "expert_signals", "opened_at"),
                ("expert_positions", "expert_positions", "as_of"), ("account_snapshots", "accounts", "ts"),
                ("alerts", "alerts", "ts")]
        out = []
        for tab, name, col in spec:
            rows = await self._q(
                f"SELECT max({col}) AS last_ts, count(*) FILTER (WHERE {col} > now() - interval '24 hours') AS count_24h "
                f"FROM {tab} WHERE {col} > now() - interval '30 days' AND {col} <= now()")
            r = rows[0] if rows else {}
            out.append({"name": name, "last_ts": r.get("last_ts"), "count_24h": int(r.get("count_24h") or 0)})
        return out

    async def analytics(self, kind, symbol=None, key=None):
        """Snapshot do service analytics ghi. Bảng chưa có (chưa chạy migration 002) => [] (UI hiện trạng thái trống)."""
        try:
            return await self._q(
                "SELECT kind, key, ts, payload, updated_at FROM analytics_snapshots WHERE kind=$1 "
                "AND ($2::text IS NULL OR payload->>'symbol' = $2) AND ($3::text IS NULL OR key = $3) ORDER BY key",
                kind, symbol, key)
        except asyncpg.UndefinedTableError:
            return []
