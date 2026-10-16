"""Nguon du lieu CHI DOC (Postgres role ts_ro) + ban in-memory cho test. Ghi chu/tag di qua notes.py (role ts_journal)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from .models import Trade, group_label
from .paper import fills_to_trades

Row = dict[str, Any]


class Source(Protocol):
    async def accounts(self) -> list[Row]: ...
    async def account(self, account_id: str) -> Optional[Row]: ...
    async def trades(self, account: Row, start: Optional[datetime], end: Optional[datetime]) -> list[Trade]: ...
    async def balance_now(self, account: Row) -> Optional[float]: ...
    async def calendar_events(self, start: datetime, end: datetime) -> list[dict]: ...
    async def bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[dict]: ...
    async def entry_spread_bps(self, symbol: str, at: datetime) -> Optional[float]: ...
    async def close(self) -> None: ...


def deal_to_trade(r: Row) -> Trade:
    kind = "balance" if r["side"] == "balance" else "trade"
    return Trade(
        ticket=str(r["ticket"]), kind=kind, symbol=r.get("symbol") or "", side=r["side"], volume=float(r.get("volume") or 0.0),
        price_open=float(r.get("price_open") or 0.0), price_close=float(r.get("price_close") or 0.0),
        time_open=r.get("time_open") or r["time_close"], time_close=r["time_close"], profit=float(r.get("profit") or 0.0),
        swap=float(r.get("swap") or 0.0), commission=float(r.get("commission") or 0.0), sl=float(r.get("sl") or 0.0), tp=float(r.get("tp") or 0.0),
        magic=int(r.get("magic") or 0), group=group_label(int(r.get("magic") or 0)), comment=r.get("comment") or "", reason=r.get("reason") or "",
        source=r.get("source") or "", position_id=str(r.get("position_id") or ""))


class PgSource:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgSource":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=30, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def _q(self, sql: str, *a) -> list[Row]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, *a)]

    async def accounts(self) -> list[Row]:
        mt = await self._q(
            "SELECT account_id, 'mt' AS kind, max(platform) AS platform, count(*) FILTER (WHERE side<>'balance') AS n_trades, "
            "min(time_close) AS first_ts, max(time_close) AS last_ts, max(source) AS source FROM account_deals GROUP BY account_id ORDER BY account_id")
        paper = await self._q(
            "SELECT a.account_id, 'paper' AS kind, 'paper' AS platform, a.name, a.strategy, a.base_ccy AS currency, a.initial_capital, "
            "(SELECT count(*) FROM paper_fills f WHERE f.account_id=a.account_id) AS n_fills, "
            "(SELECT min(ts) FROM paper_fills f WHERE f.account_id=a.account_id) AS first_ts, "
            "(SELECT max(ts) FROM paper_fills f WHERE f.account_id=a.account_id) AS last_ts FROM paper_accounts a ORDER BY a.account_id")
        seen = {r["account_id"] for r in mt}
        return mt + [r for r in paper if r["account_id"] not in seen]

    async def account(self, account_id: str) -> Optional[Row]:
        for r in await self.accounts():
            if r["account_id"] == account_id:
                return r
        return None

    async def trades(self, account: Row, start, end) -> list[Trade]:
        if account["kind"] == "mt":
            rows = await self._q(
                "SELECT * FROM account_deals WHERE account_id=$1 AND ($2::timestamptz IS NULL OR time_close >= $2) "
                "AND ($3::timestamptz IS NULL OR time_close < $3) ORDER BY time_close, ticket LIMIT 50000", account["account_id"], start, end)
            return [deal_to_trade(r) for r in rows]
        # paper: phai doc TOAN BO fills de dung gia von/vi the dung, roi loc theo thoi gian dong
        fills = await self._q("SELECT fill_id, symbol, side, qty, ts, price, spread_cost, slippage_cost, commission, tax, realized_pnl "
                              "FROM paper_fills WHERE account_id=$1 ORDER BY ts, fill_id", account["account_id"])
        ts = fills_to_trades(fills, account_id=account["account_id"], strategy=account.get("strategy") or "")
        return [t for t in ts if (start is None or t.time_close >= start) and (end is None or t.time_close < end)]

    async def balance_now(self, account: Row) -> Optional[float]:
        if account["kind"] == "mt":
            r = await self._q("SELECT balance FROM account_snapshots WHERE account_id=$1 ORDER BY ts DESC LIMIT 1", account["account_id"])
            return float(r[0]["balance"]) if r and r[0]["balance"] is not None else None
        return None

    async def calendar_events(self, start, end) -> list[dict]:
        return await self._q(
            "SELECT event_id, source, country, title, impact, ts, extra FROM calendar_events WHERE impact='high' AND COALESCE(source,'') <> 'qa' AND ts >= $1 AND ts < $2 ORDER BY ts", start, end)

    async def bars(self, symbol, tf, start, end) -> list[dict]:
        rows = await self._q(
            "SELECT DISTINCT ON (ts_open) ts_open AS ts, h, l FROM bars WHERE symbol=$1 AND tf=$2 AND ts_open >= $3 AND ts_open < $4 "
            "ORDER BY ts_open, source LIMIT 20000", symbol, tf, start, end)
        return rows

    async def entry_spread_bps(self, symbol, at) -> Optional[float]:
        r = await self._q("SELECT bid, ask FROM quotes WHERE symbol=$1 AND ts <= $2 AND ts > $2 - interval '10 minutes' AND bid>0 AND ask>=bid ORDER BY ts DESC LIMIT 1", symbol, at)
        if not r:
            return None
        bid, ask = float(r[0]["bid"]), float(r[0]["ask"])
        mid = (bid + ask) / 2
        return round((ask - bid) / mid * 1e4, 3) if mid > 0 else None


class MemSource:
    """Nguon trong bo nho cho test."""

    def __init__(self, accounts: list[Row], trades: dict[str, list[Trade]], balance: Optional[dict[str, float]] = None,
                 events: Optional[list[dict]] = None, bars: Optional[dict[tuple[str, str], list[dict]]] = None):
        self._accounts, self._trades, self._balance = accounts, trades, balance or {}
        self._events, self._bars = events or [], bars or {}

    async def accounts(self):
        return list(self._accounts)

    async def account(self, account_id):
        return next((a for a in self._accounts if a["account_id"] == account_id), None)

    async def trades(self, account, start, end):
        return [t for t in self._trades.get(account["account_id"], []) if (start is None or t.time_close >= start) and (end is None or t.time_close < end)]

    async def balance_now(self, account):
        return self._balance.get(account["account_id"])

    async def calendar_events(self, start, end):
        return [e for e in self._events if start <= e["ts"] < end]

    async def bars(self, symbol, tf, start, end):
        return [b for b in self._bars.get((symbol, tf), []) if start <= b["ts"] < end]

    async def entry_spread_bps(self, symbol, at):
        return None

    async def close(self):
        pass


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

