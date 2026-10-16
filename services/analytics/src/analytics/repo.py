"""Truy cập dữ liệu: đọc nến (role chỉ-đọc ts_ro) và ghi snapshot (role ts_analytics, CHỈ bảng analytics_snapshots)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

Row = dict[str, Any]


class BarSource(Protocol):
    async def available(self, tfs: list[str]) -> dict[str, dict[str, datetime]]:
        """{symbol: {tf: ts_open nến mới nhất}} (chỉ nến gần đây)."""
        ...

    async def bars(self, symbol: str, tf: str, limit: int) -> list[Row]:
        """`limit` nến MỚI nhất (ts_open,o,h,l,c,v), thứ tự bất kỳ; bản trùng ts_open đã loại."""
        ...


class SnapshotStore(Protocol):
    async def upsert_many(self, rows: list[tuple[str, str, dict]]) -> None: ...
    async def get(self, kind: str, key: str) -> dict | None: ...
    async def close(self) -> None: ...


_TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800, "MN1": 2592000}
_log = logging.getLogger(__name__)

class PgBarSource:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgBarSource":
        import asyncpg
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30))

    async def close(self) -> None:
        await self.pool.close()

    async def available(self, tfs):
        sql = ("SELECT symbol, tf, max(ts_open) AS last FROM bars WHERE tf = ANY($1::text[]) "
               "AND ts_open > now() - interval '45 days' GROUP BY symbol, tf")
        async with self.pool.acquire() as c:
            rows = await c.fetch(sql, tfs)
        out: dict[str, dict[str, datetime]] = {}
        for r in rows:
            out.setdefault(r["symbol"], {})[r["tf"]] = r["last"]
        return out

    async def bars(self, symbol, tf, limit):
        # Cận dưới ts_open để loại chunk hypertable (planning/scan nhanh, tránh statement timeout); QueryCanceled -> [] (không traceback).
        sec = _TF_SEC.get(tf, 86400)
        since = datetime.now(timezone.utc) - timedelta(seconds=max(int(limit) * sec * 3, 14 * 86400))
        sql = ("SELECT DISTINCT ON (ts_open) ts_open, o, h, l, c, v FROM bars WHERE symbol=$1 AND tf=$2 AND ts_open >= $4 "
               "ORDER BY ts_open DESC, source LIMIT $3")
        try:
            async with self.pool.acquire() as c:
                return [dict(r) for r in await c.fetch(sql, symbol, tf, limit, since)]
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ != "QueryCanceledError":
                raise
            _log.warning("bars %s/%s bị statement timeout, bỏ qua vòng này", symbol, tf)
            return []


class PgSnapshotStore:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgSnapshotStore":
        import asyncpg
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=2, command_timeout=30))

    async def close(self) -> None:
        await self.pool.close()

    async def upsert_many(self, rows):
        if not rows:
            return
        sql = ("INSERT INTO analytics_snapshots (kind, key, ts, payload, updated_at) VALUES ($1,$2,$3,$4::jsonb, now()) "
               "ON CONFLICT (kind, key) DO UPDATE SET ts=EXCLUDED.ts, payload=EXCLUDED.payload, updated_at=now()")
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as c:
            await c.executemany(sql, [(k, key, now, json.dumps(p, default=str, allow_nan=False)) for k, key, p in rows])

    async def get(self, kind, key):
        async with self.pool.acquire() as c:
            r = await c.fetchval("SELECT payload FROM analytics_snapshots WHERE kind=$1 AND key=$2", kind, key)
        return json.loads(r) if isinstance(r, str) else r


class MemoryBarSource:
    """Cho test/dev: dữ liệu dạng {(symbol, tf): [rows]}."""

    def __init__(self, data: dict[tuple[str, str], list[Row]]):
        self.data = data

    async def available(self, tfs):
        out: dict[str, dict[str, datetime]] = {}
        for (s, tf), rows in self.data.items():
            if tf in tfs and rows:
                out.setdefault(s, {})[tf] = max(r["ts_open"] for r in rows)
        return out

    async def bars(self, symbol, tf, limit):
        rows = sorted(self.data.get((symbol, tf), []), key=lambda r: r["ts_open"], reverse=True)
        return rows[:limit]


class MemoryStore:
    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}
        self.updated: dict[tuple[str, str], datetime] = {}

    async def upsert_many(self, rows):
        for k, key, p in rows:
            self.rows[(k, key)] = json.loads(json.dumps(p, default=str, allow_nan=False))  # kiểm tra JSON hợp lệ
            self.updated[(k, key)] = datetime.now(timezone.utc)

    async def get(self, kind, key):
        return self.rows.get((kind, key))

    async def close(self) -> None:
        return None

    def as_gateway_rows(self) -> list[Row]:
        """Định dạng bảng analytics_snapshots (cho InMemoryRepo của api-gateway / mock server)."""
        return [{"kind": k, "key": key, "ts": self.updated[(k, key)], "payload": p, "updated_at": self.updated[(k, key)]}
                for (k, key), p in self.rows.items()]


class NullStore(MemoryStore):
    """Không có ANALYTICS_DB_RW_URL: vẫn tính + phát sự kiện/cảnh báo, không lưu."""

