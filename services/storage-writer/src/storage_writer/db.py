"""Lớp DB mỏng. Interface: `await db.execute_many(stmts)` chạy trong 1 transaction."""
from __future__ import annotations

from typing import Any, Protocol

Stmt = tuple[str, tuple[Any, ...]]


class DB(Protocol):
    async def execute_many(self, stmts: list[Stmt]) -> None: ...
    async def close(self) -> None: ...


class AsyncpgDB:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "AsyncpgDB":
        import asyncpg

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=5))

    async def execute_many(self, stmts: list[Stmt]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for sql, args in stmts:
                    await conn.execute(sql, *args)

    async def ping(self) -> None:
        async with self.pool.acquire(timeout=5) as conn:
            await conn.fetchval("SELECT 1", timeout=5)

    async def close(self) -> None:
        await self.pool.close()
