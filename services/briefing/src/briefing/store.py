"""Lưu bản tin: bảng `briefings` (role ts_briefing, CHỈ bảng này) + bản in-memory cho test."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Protocol

Row = dict[str, Any]
COLS = ("id, edition, scope, for_date, generated_at, window_start, window_end, status, model, runtime, latency_ms, prompt_tokens, completion_tokens, "
        "title, headline, body, context, quality, disclaimer")
SUMMARY_COLS = "id, edition, scope, for_date, generated_at, status, model, latency_ms, title, headline"


def jsonable(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


class Store(Protocol):
    async def insert(self, b: Row) -> None: ...
    async def latest(self, edition: str | None, scope: str | None, n: int = 1) -> list[Row]: ...
    async def list(self, limit: int, edition: str | None, scope: str | None) -> list[Row]: ...
    async def get(self, bid: str) -> Row | None: ...
    async def exists(self, for_date: date, edition: str, scope: str) -> bool: ...
    async def close(self) -> None: ...


class PgStore:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgStore":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def insert(self, b):
        async with self.pool.acquire() as c:
            await c.execute(
                f"INSERT INTO briefings ({COLS}) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,$17::jsonb,$18::jsonb,$19)",
                b["id"], b["edition"], b["scope"], b["for_date"], b["generated_at"], b["window_start"], b["window_end"], b["status"], b["model"], b["runtime"],
                b.get("latency_ms"), b.get("prompt_tokens"), b.get("completion_tokens"), b["title"], b["headline"],
                jsonable(b["body"]), jsonable(b["context"]), jsonable(b["quality"]), b["disclaimer"])   # codec jsonb của pool tự json.dumps

    async def _q(self, sql: str, *a) -> list[Row]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, *a)]

    async def latest(self, edition, scope, n=1):
        return await self._q(f"SELECT {COLS} FROM briefings WHERE ($1::text IS NULL OR edition=$1) AND ($2::text IS NULL OR scope=$2) "
                             "ORDER BY generated_at DESC LIMIT $3", edition, scope, n)

    async def list(self, limit, edition, scope):
        return await self._q(f"SELECT {SUMMARY_COLS} FROM briefings WHERE ($1::text IS NULL OR edition=$1) AND ($2::text IS NULL OR scope=$2) "
                             "ORDER BY generated_at DESC LIMIT $3", edition, scope, limit)

    async def get(self, bid):
        r = await self._q(f"SELECT {COLS} FROM briefings WHERE id=$1::uuid", bid)
        return r[0] if r else None

    async def exists(self, for_date, edition, scope):
        r = await self._q("SELECT 1 FROM briefings WHERE for_date=$1 AND edition=$2 AND scope=$3 LIMIT 1", for_date, edition, scope)
        return bool(r)


class MemStore:
    def __init__(self):
        self.rows: list[Row] = []

    async def insert(self, b):
        self.rows.append(dict(b))

    def _f(self, edition, scope):
        return sorted([r for r in self.rows if (edition is None or r["edition"] == edition) and (scope is None or r["scope"] == scope)],
                      key=lambda r: r["generated_at"], reverse=True)

    async def latest(self, edition, scope, n=1):
        return self._f(edition, scope)[:n]

    async def list(self, limit, edition, scope):
        return [{k: r[k] for k in SUMMARY_COLS.replace(" ", "").split(",")} for r in self._f(edition, scope)[:limit]]

    async def get(self, bid):
        return next((r for r in self.rows if r["id"] == bid), None)

    async def exists(self, for_date, edition, scope):
        return any(r["for_date"] == for_date and r["edition"] == edition and r["scope"] == scope for r in self.rows)

    async def close(self):
        pass
