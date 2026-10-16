"""Nguon du lieu CHI DOC (role ts_ro): tin, tin hieu, vi the COT, gia D1. + MemData cho test."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

Row = dict[str, Any]
UTC = timezone.utc


class Data(Protocol):
    async def news_rows(self) -> list[Row]: ...
    async def signal_rows(self) -> list[Row]: ...
    async def position_rows(self) -> list[Row]: ...
    async def expert_names(self) -> dict[str, str]: ...
    async def expert_meta(self) -> dict[str, dict]: ...
    async def price_symbols(self) -> set[str]: ...
    async def prices(self, keys: list[str], since: datetime) -> dict[str, list[tuple[datetime, float, float]]]: ...
    async def close(self) -> None: ...


class MemData:
    def __init__(self, news=None, signals=None, positions=None, names=None, prices=None):
        self.news, self.signals, self.positions, self.names = news or [], signals or [], positions or [], names or {}
        self._prices: dict[str, list[tuple[datetime, float, float]]] = prices or {}

    async def news_rows(self): return list(self.news)
    async def signal_rows(self): return list(self.signals)
    async def position_rows(self): return list(self.positions)
    async def expert_names(self): return dict(self.names)
    async def expert_meta(self): return {k: {"name": v, "org_type": None, "source": None} for k, v in self.names.items()}
    async def price_symbols(self): return set(self._prices)

    async def prices(self, keys, since):
        return {k: [x for x in self._prices.get(k, []) if x[0] >= since] for k in keys}

    async def close(self): return None


class PgData:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgData":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=120, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def news_rows(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT source, lang, published_at, ingested_at, enriched_at, symbols, sentiment FROM news_items "
                                 "WHERE sentiment IS NOT NULL AND cardinality(symbols) > 0 AND abs(sentiment) >= 0.35")
        return [dict(r) for r in rows]

    async def signal_rows(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT expert_id, source, symbol, side, opened_at, sl FROM expert_signals")
        return [dict(r) for r in rows]

    async def position_rows(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT expert_id, source, symbol, as_of, net_volume, raw FROM expert_positions WHERE source = 'cftc'")
        return [dict(r) for r in rows]

    async def expert_names(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT expert_id, display_name FROM experts WHERE display_name IS NOT NULL AND display_name <> ''")
        return {r["expert_id"]: r["display_name"] for r in rows}

    async def expert_meta(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT expert_id, display_name, source, reputation->>'org_type' AS org_type FROM experts")
        return {r["expert_id"]: {"name": (r["display_name"] or "").strip(), "org_type": r["org_type"], "source": r["source"]} for r in rows}

    async def price_symbols(self) -> set[str]:
        async with self.pool.acquire() as c:
            s = {r["symbol"] for r in await c.fetch("SELECT DISTINCT symbol FROM bars WHERE tf = 'D1' AND ts_open >= now() - interval '800 days'")}
            s |= {"VN:" + r["code"] for r in await c.fetch("SELECT DISTINCT code FROM vn_daily")}
            s |= {"VN:" + r["code"] for r in await c.fetch("SELECT DISTINCT code FROM vn_index_daily")}
        return s

    async def prices(self, keys, since):
        out: dict[str, list] = {}
        bars_keys = list(keys)
        vn_keys = [k for k in keys if k.startswith("VN:")]
        async with self.pool.acquire() as c:
            if bars_keys:
                # moi symbol chi dung MOT nguon (nguon co nhieu nen D1 nhat) de khong tron bang gia
                rows = await c.fetch(
                    "WITH src AS (SELECT DISTINCT ON (symbol) symbol, source FROM (SELECT symbol, source, count(*) n FROM bars WHERE tf='D1' AND ts_open >= $2 AND symbol = ANY($1::text[]) GROUP BY 1,2) x "
                    "ORDER BY symbol, n DESC, source) SELECT b.symbol, b.ts_open, b.o, b.c FROM bars b JOIN src s ON s.symbol=b.symbol AND s.source=b.source "
                    "WHERE b.tf='D1' AND b.ts_open >= $2 ORDER BY b.symbol, b.ts_open", bars_keys, since)
                for r in rows:
                    out.setdefault(r["symbol"], []).append((r["ts_open"], r["o"], r["c"]))
            in_bars = {k for k in vn_keys if k in out}
            rest = [k[3:] for k in vn_keys if k not in in_bars]
            if rest:
                filled: set[str] = set()
                for q in ("SELECT code, d, open, close FROM vn_index_daily WHERE code = ANY($1::text[]) AND d >= $2 ORDER BY code, d",
                          "SELECT code, d, open, close FROM vn_daily WHERE code = ANY($1::text[]) AND d >= $2 ORDER BY code, d"):
                    got: set[str] = set()
                    for r in await c.fetch(q, rest, since.date()):
                        k = "VN:" + r["code"]
                        if k in filled:
                            continue
                        got.add(k)
                        out.setdefault(k, []).append((datetime(r["d"].year, r["d"].month, r["d"].day, tzinfo=UTC), r["open"], r["close"]))
                    filled |= got
        return out
