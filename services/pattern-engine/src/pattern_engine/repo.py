"""Truy cập dữ liệu: đọc nến (ts_ro) và lưu/đọc pattern_signals (role hẹp ts_pattern)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .detector import Signal

Row = dict[str, Any]


class BarSource(Protocol):
    async def available(self, tfs: list[str]) -> dict[str, dict[str, datetime]]: ...
    async def bars(self, symbol: str, tf: str, limit: int) -> list[Row]: ...


class SignalStore(Protocol):
    async def insert(self, sig: Signal) -> bool: ...
    async def recent(self, *, symbol: str | None, tf: str | None, pattern: str | None, states: list[str] | None,
                     since: datetime | None, limit: int) -> list[Row]: ...
    async def close(self) -> None: ...


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
               "AND ts_open > now() - interval '10 days' GROUP BY symbol, tf")
        async with self.pool.acquire() as c:
            rows = await c.fetch(sql, tfs)
        out: dict[str, dict[str, datetime]] = {}
        for r in rows:
            out.setdefault(r["symbol"], {})[r["tf"]] = r["last"]
        return out

    async def bars(self, symbol, tf, limit):
        # Cận dưới ts_open để loại chunk hypertable (tránh planning/scan mọi chunk -> statement timeout).
        since = datetime.now(timezone.utc) - timedelta(seconds=max(int(limit) * _TF_SEC.get(tf, 86400) * 3, 14 * 86400))
        sql = ("SELECT DISTINCT ON (ts_open) ts_open, o, h, l, c, v FROM bars WHERE symbol=$1 AND tf=$2 AND ts_open >= $4 "
               "ORDER BY ts_open DESC, source LIMIT $3")
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, symbol, tf, limit, since)]


class PgSignalStore:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgSignalStore":
        import asyncpg
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30))

    async def close(self) -> None:
        await self.pool.close()

    async def insert(self, sig: Signal) -> bool:
        p = sig.to_payload()
        sql = ("INSERT INTO pattern_signals (setup_id, pattern, symbol, tf, state, side, score, bar_ts, ts, levels, steps, reason) "
               "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12) "
               "ON CONFLICT (setup_id, symbol, tf, state) DO NOTHING RETURNING id")
        async with self.pool.acquire() as c:
            r = await c.fetchval(sql, sig.setup_id, sig.pattern, sig.symbol, sig.tf, sig.state, sig.side, float(sig.score), sig.bar_ts,
                                 sig.ts, json.dumps(p["levels"], allow_nan=False), json.dumps(p["steps"], ensure_ascii=False), sig.reason)
        return r is not None

    async def recent(self, *, symbol, tf, pattern, states, since, limit):
        sql = ("SELECT id, setup_id, pattern, symbol, tf, state, side, score, bar_ts, ts, levels, steps, reason, created_at FROM pattern_signals "
               "WHERE ($1::text IS NULL OR symbol=$1) AND ($2::text IS NULL OR tf=$2) AND ($3::text IS NULL OR pattern=$3) "
               "AND ($4::text[] IS NULL OR state = ANY($4)) AND ($5::timestamptz IS NULL OR bar_ts >= $5) "
               "ORDER BY bar_ts DESC, id DESC LIMIT $6")
        async with self.pool.acquire() as c:
            rows = await c.fetch(sql, symbol, tf, pattern, states, since, limit)
        out = []
        for r in rows:
            d = dict(r)
            for k in ("levels", "steps"):
                if isinstance(d[k], str):
                    d[k] = json.loads(d[k])
            out.append(d)
        return out


class MemoryBarSource:
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
    """Test/dev và chế độ không có PATTERN_DB_RW_URL (chỉ giữ vòng đệm gần nhất trong RAM)."""

    def __init__(self, cap: int = 2000):
        self.rows: list[Row] = []
        self.keys: set[tuple] = set()
        self.cap = cap
        self._id = 0

    async def insert(self, sig: Signal) -> bool:
        k = (sig.setup_id, sig.symbol, sig.tf, sig.state)
        if k in self.keys:
            return False
        self.keys.add(k)
        self._id += 1
        p = sig.to_payload()
        self.rows.append({"id": self._id, "setup_id": sig.setup_id, "pattern": sig.pattern, "symbol": sig.symbol, "tf": sig.tf,
                          "state": sig.state, "side": sig.side, "score": sig.score, "bar_ts": sig.bar_ts, "ts": sig.ts,
                          "levels": p["levels"], "steps": p["steps"], "reason": sig.reason, "created_at": sig.ts})
        if len(self.rows) > self.cap:
            self.rows = self.rows[-self.cap:]
        return True

    async def recent(self, *, symbol=None, tf=None, pattern=None, states=None, since=None, limit=100):
        rows = [r for r in self.rows if (not symbol or r["symbol"] == symbol) and (not tf or r["tf"] == tf)
                and (not pattern or r["pattern"] == pattern) and (not states or r["state"] in states)
                and (not since or r["bar_ts"] >= since)]
        return sorted(rows, key=lambda r: (r["bar_ts"], r["id"]), reverse=True)[:limit]

    async def close(self) -> None:
        return None
