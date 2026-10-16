"""Nguồn dữ liệu CHỈ ĐỌC cho bản tin (Postgres role ts_ro) + bản in-memory cho test. Không đọc/ghi gì khác.

Loại bỏ dữ liệu kiểm thử (source 'qa', sự kiện 'QA event') ngay ở truy vấn. KHÔNG trả tên nguồn tin (cột source không được SELECT)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

Row = dict[str, Any]


class Source(Protocol):
    async def news(self, start: datetime, end: datetime) -> list[Row]: ...
    async def calendar(self, start: datetime, end: datetime) -> list[Row]: ...
    async def d1_closes(self, symbols: list[str]) -> dict[str, list[Row]]: ...        # {symbol: [{ts, c}] mới -> cũ, tối đa 3}
    async def analytics(self, symbols: list[str]) -> dict[str, Row]: ...               # {symbol: payload tóm tắt D1}
    async def vn_indices(self) -> list[Row]: ...                                       # mỗi mã chỉ số: phiên mới nhất + phiên liền trước
    async def close(self) -> None: ...


class PgSource:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgSource":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def _q(self, sql: str, *a) -> list[Row]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, *a)]

    async def news(self, start, end):
        return await self._q(
            "SELECT url, title, summary, coalesce(published_at, ingested_at) AS ts, lang, symbols, sentiment, sentiment_label, importance "
            "FROM news_items WHERE coalesce(published_at, ingested_at) >= $1 AND coalesce(published_at, ingested_at) < $2 "
            "AND lower(coalesce(source,'')) <> 'qa' AND title <> '' ORDER BY coalesce(published_at, ingested_at) DESC LIMIT 3000", start, end)

    async def calendar(self, start, end):
        return await self._q(
            "SELECT event_id, country, title, impact, ts, forecast, previous, actual FROM calendar_events "
            "WHERE impact='high' AND ts >= $1 AND ts < $2 AND lower(coalesce(source,'')) <> 'qa' AND title NOT ILIKE 'QA event%%' ORDER BY ts LIMIT 200", start, end)

    async def d1_closes(self, symbols):
        out: dict[str, list[Row]] = {}
        for s in symbols:
            rows = await self._q(
                "SELECT ts, c FROM (SELECT DISTINCT ON (ts_open) ts_open AS ts, c FROM bars WHERE symbol=$1 AND tf='D1' "
                "AND ts_open > now() - interval '12 days' ORDER BY ts_open DESC, source) x ORDER BY ts DESC LIMIT 3", s)
            if rows:
                out[s] = rows
        return out

    async def analytics(self, symbols):
        rows = await self._q("SELECT key, payload FROM analytics_snapshots WHERE kind='summary' AND key = ANY($1::text[])", [f"{s}:D1" for s in symbols])
        res: dict[str, Row] = {}
        for r in rows:
            p = r["payload"]
            if isinstance(p, str):
                p = json.loads(p)
            res[r["key"][:-3]] = {k: p.get(k) for k in ("trend", "rsi", "adx", "bar_ts")}
        return res

    async def vn_indices(self):
        return await self._q(
            "SELECT code, d, close, chg, pct, advances, declines, ceiling_n, floor_n FROM ("
            " SELECT *, row_number() OVER (PARTITION BY code ORDER BY d DESC) rn FROM vn_index_daily WHERE d > current_date - 10) x "
            "WHERE rn = 1 ORDER BY value DESC NULLS LAST LIMIT 8")


class MemSource:
    def __init__(self, news=None, calendar=None, closes=None, analytics=None, vn=None):
        self._news, self._cal = news or [], calendar or []
        self._closes, self._an, self._vn = closes or {}, analytics or {}, vn or []

    async def news(self, start, end):
        return [r for r in self._news if start <= r["ts"] < end]

    async def calendar(self, start, end):
        return [r for r in self._cal if start <= r["ts"] < end]

    async def d1_closes(self, symbols):
        return {s: self._closes[s] for s in symbols if s in self._closes}

    async def analytics(self, symbols):
        return {s: self._an[s] for s in symbols if s in self._an}

    async def vn_indices(self):
        return list(self._vn)

    async def close(self):
        pass
