"""Truy cập dữ liệu CHỈ ĐỌC: Postgres (role ts_ro) + snapshot MT mới nhất từ Redis stream account.snapshots."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import pandas as pd

Row = dict[str, Any]


class RiskSource(Protocol):
    async def mt_accounts(self) -> list[Row]: ...
    async def mt_equity(self, account_id: str, days: int) -> list[tuple[datetime, float]]: ...
    async def paper_accounts(self) -> list[Row]: ...
    async def paper_positions(self, account_id: str) -> list[Row]: ...
    async def paper_equity(self, account_id: str, days: int) -> list[tuple[datetime, float]]: ...
    async def closes(self, symbols: list[str], start: datetime, end: datetime | None = None) -> pd.DataFrame: ...
    async def mt_meta(self, account_id: str) -> Row: ...
    async def close(self) -> None: ...


class PgRedisSource:
    def __init__(self, pool, redis):
        self.pool = pool
        self.redis = redis
        self._meta: dict[str, tuple[float, Row]] = {}

    @classmethod
    async def connect(cls, dsn: str, redis_url: str) -> "PgRedisSource":
        import asyncpg
        import redis.asyncio as aioredis
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30)
        return cls(pool, aioredis.from_url(redis_url, decode_responses=True))

    async def close(self) -> None:
        await self.pool.close()
        await self.redis.aclose()

    async def _q(self, sql: str, *a) -> list[Row]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, *a)]

    async def mt_accounts(self) -> list[Row]:
        return await self._q(
            "SELECT DISTINCT ON (account_id) account_id, platform, ts, balance, equity, margin, positions "
            "FROM account_snapshots WHERE ts > now() - interval '30 days' ORDER BY account_id, ts DESC")

    async def mt_equity(self, account_id: str, days: int):
        rows = await self._q(
            "SELECT time_bucket('5 minutes', ts) AS b, last(equity, ts) AS e FROM account_snapshots "
            "WHERE account_id=$1 AND ts > now() - make_interval(days => $2) GROUP BY 1 ORDER BY 1", account_id, days)
        return [(r["b"], float(r["e"])) for r in rows if r["e"] is not None]

    async def deal_times(self, days: int = 2) -> dict[str, list[datetime]]:
        """Thời điểm đóng deal (loại side='balance': nạp/rút) của mọi tài khoản trong `days` ngày gần nhất — cho luật max_trades_day."""
        rows = await self._q("SELECT account_id, time_close FROM account_deals WHERE side <> 'balance' "
                             "AND time_close > now() - make_interval(days => $1)", int(days))
        out: dict[str, list[datetime]] = {}
        for r in rows:
            out.setdefault(r["account_id"], []).append(r["time_close"])
        return out

    async def paper_accounts(self) -> list[Row]:
        return await self._q(
            "SELECT a.account_id, a.name, a.strategy, a.base_ccy, a.initial_capital, a.meaningful, a.status, a.cash, "
            "(SELECT equity FROM paper_equity e WHERE e.account_id=a.account_id ORDER BY ts DESC LIMIT 1) AS equity, "
            "(SELECT ts FROM paper_equity e WHERE e.account_id=a.account_id ORDER BY ts DESC LIMIT 1) AS ts "
            "FROM paper_accounts a ORDER BY a.account_id")

    async def paper_positions(self, account_id: str) -> list[Row]:
        return await self._q("SELECT symbol, qty, avg_price, mark_price, unrealized_pnl, notional FROM paper_positions "
                             "WHERE account_id=$1", account_id)

    async def paper_equity(self, account_id: str, days: int):
        rows = await self._q("SELECT ts, equity FROM paper_equity WHERE account_id=$1 AND ts > now() - make_interval(days => $2) "
                             "ORDER BY ts", account_id, days)
        return [(r["ts"], float(r["equity"])) for r in rows]

    async def closes(self, symbols, start, end=None) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()
        rows = await self._q(
            "SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, c FROM bars WHERE tf='D1' AND symbol = ANY($1::text[]) "
            "AND ts_open >= $2 AND ($3::timestamptz IS NULL OR ts_open <= $3) ORDER BY symbol, ts_open, source",
            list(symbols), start, end)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["d"] = pd.to_datetime(df["ts_open"], utc=True).dt.tz_localize(None).dt.normalize()
        return df.pivot_table(index="d", columns="symbol", values="c", aggfunc="last").sort_index()

    async def mt_meta(self, account_id: str) -> Row:
        """currency/leverage/margin_mode/free_margin/margin_level: DB không lưu, lấy từ snapshot Redis mới nhất (giữ cache 10 phút)."""
        import time
        hit = self._meta.get(account_id)
        try:
            msgs = await self.redis.xrevrange("account.snapshots", count=300)
            for _id, f in msgs:
                p = json.loads(f["e"]).get("payload", {})
                if p.get("account_id") == account_id:
                    meta = {k: p.get(k) for k in ("currency", "leverage", "margin_mode", "free_margin", "margin_level", "login", "server")}
                    self._meta[account_id] = (time.time(), meta)
                    return meta
        except Exception:  # noqa: BLE001
            pass
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        return {}


def since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
