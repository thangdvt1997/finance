"""Ghi chu/tag thu cong: bang DUY NHAT service nay duoc GHI (journal_notes) qua role ts_journal. Co ban in-memory cho test."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from .models import NoteIn

Row = dict[str, Any]
MAX_NOTES_PER_ACCOUNT = 20000


class LimitReached(Exception):
    pass


class NotesStore(Protocol):
    async def list(self, account_id: str, kind: Optional[str] = None, tag: Optional[str] = None, refs: Optional[list[str]] = None) -> list[Row]: ...
    async def put(self, account_id: str, kind: str, ref: str, note: NoteIn) -> Row: ...
    async def delete(self, account_id: str, kind: str, ref: str) -> bool: ...
    async def tag_counts(self, account_id: str) -> list[Row]: ...
    async def close(self) -> None: ...


class PgNotes:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgNotes":
        import asyncpg
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=15))

    async def close(self) -> None:
        await self.pool.close()

    async def list(self, account_id, kind=None, tag=None, refs=None):
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT account_id, kind, ref, tags, note, rating, updated_at FROM journal_notes WHERE account_id=$1 "
                "AND ($2::text IS NULL OR kind=$2) AND ($3::text IS NULL OR $3 = ANY(tags)) AND ($4::text[] IS NULL OR ref = ANY($4)) "
                "ORDER BY updated_at DESC LIMIT 5000", account_id, kind, tag, refs)
        return [dict(r) for r in rows]

    async def put(self, account_id, kind, ref, note: NoteIn):
        async with self.pool.acquire() as c, c.transaction():
            n = await c.fetchval("SELECT count(*) FROM journal_notes WHERE account_id=$1", account_id)
            exists = await c.fetchval("SELECT 1 FROM journal_notes WHERE account_id=$1 AND kind=$2 AND ref=$3", account_id, kind, ref)
            if not exists and n >= MAX_NOTES_PER_ACCOUNT:
                raise LimitReached(f"tối đa {MAX_NOTES_PER_ACCOUNT} ghi chú/tài khoản")
            r = await c.fetchrow(
                "INSERT INTO journal_notes (account_id, kind, ref, tags, note, rating, updated_at) VALUES ($1,$2,$3,$4,$5,$6,now()) "
                "ON CONFLICT (account_id, kind, ref) DO UPDATE SET tags=EXCLUDED.tags, note=EXCLUDED.note, rating=EXCLUDED.rating, updated_at=now() "
                "RETURNING account_id, kind, ref, tags, note, rating, updated_at", account_id, kind, ref, note.tags, note.note, note.rating)
        return dict(r)

    async def delete(self, account_id, kind, ref) -> bool:
        async with self.pool.acquire() as c:
            return (await c.execute("DELETE FROM journal_notes WHERE account_id=$1 AND kind=$2 AND ref=$3", account_id, kind, ref)).endswith("1")

    async def tag_counts(self, account_id):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT t AS tag, count(*) AS n FROM journal_notes, unnest(tags) AS t WHERE account_id=$1 GROUP BY t ORDER BY n DESC, t LIMIT 200", account_id)
        return [dict(r) for r in rows]


class MemNotes:
    def __init__(self):
        self.d: dict[tuple[str, str, str], Row] = {}

    async def list(self, account_id, kind=None, tag=None, refs=None):
        rows = [r for (a, k, ref), r in self.d.items() if a == account_id and (kind is None or k == kind) and (tag is None or tag in r["tags"]) and (refs is None or ref in refs)]
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    async def put(self, account_id, kind, ref, note):
        key = (account_id, kind, ref)
        if key not in self.d and sum(1 for k in self.d if k[0] == account_id) >= MAX_NOTES_PER_ACCOUNT:
            raise LimitReached("limit")
        r = {"account_id": account_id, "kind": kind, "ref": ref, "tags": list(note.tags), "note": note.note, "rating": note.rating,
             "updated_at": datetime.now(timezone.utc)}
        self.d[key] = r
        return dict(r)

    async def delete(self, account_id, kind, ref):
        return self.d.pop((account_id, kind, ref), None) is not None

    async def tag_counts(self, account_id):
        cnt: dict[str, int] = {}
        for (a, _, _), r in self.d.items():
            if a == account_id:
                for t in r["tags"]:
                    cnt[t] = cnt.get(t, 0) + 1
        return [{"tag": t, "n": n} for t, n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))]

    async def close(self):
        pass
