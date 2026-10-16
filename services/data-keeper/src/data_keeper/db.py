"""Hai pool: ro (ts_ro, đọc bars/quotes) và rw (ts_dk, ghi CHỈ schema dk). Thiếu URL -> None (module phải chịu được)."""
from __future__ import annotations

import logging

import asyncpg

log = logging.getLogger("data_keeper.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dk.coverage (
  symbol text NOT NULL, tf text NOT NULL,
  last_bar timestamptz, last_tick timestamptz,
  gaps integer NOT NULL DEFAULT 0, expected integer NOT NULL DEFAULT 0, present integer NOT NULL DEFAULT 0,
  status text NOT NULL, market_open boolean NOT NULL, grp text, note text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, tf)
);
"""


class DB:
    def __init__(self, ro: asyncpg.Pool | None, rw: asyncpg.Pool | None):
        self.ro, self.rw = ro, rw
        self.schemas: list[str] = [SCHEMA_SQL]   # module khác có thể append SQL (CREATE ... IF NOT EXISTS, schema dk)

    @classmethod
    async def connect(cls, s) -> "DB":
        async def mk(url, n):
            if not url:
                return None
            return await asyncpg.create_pool(url, min_size=1, max_size=n, command_timeout=60,
                                             server_settings={"application_name": "data-keeper"})
        return cls(await mk(s.ro_url, 3), await mk(s.rw_url, 3))

    async def ensure_schema(self) -> None:
        if not self.rw:
            return
        async with self.rw.acquire() as c:
            for sql in self.schemas:
                await c.execute(sql)

    async def close(self) -> None:
        for p in (self.ro, self.rw):
            if p:
                await p.close()

    # --- tiện ích kiểu asyncpg cho module khác (heal/backfill/histload): đi qua pool rw (ts_dk có SELECT bars/quotes + ghi dk.*) ---
    def _p(self):
        p = self.rw or self.ro
        if p is None:
            raise RuntimeError("DB chua cau hinh")
        return p

    async def execute(self, q, *a):
        return await self._p().execute(q, *a)

    async def executemany(self, q, args):
        return await self._p().executemany(q, args)

    async def fetch(self, q, *a):
        return await self._p().fetch(q, *a)

    async def fetchrow(self, q, *a):
        return await self._p().fetchrow(q, *a)

    async def fetchval(self, q, *a):
        return await self._p().fetchval(q, *a)
