"""Lớp truy cập Postgres (asyncpg) cho vn-market. Ghi bằng role hạn chế ts_vn (chỉ bảng vn_* + SELECT news_items).
Toàn bộ truy vấn là tham số hoá ($n). Logic nghiệp vụ nằm ở analytics.py (hàm thuần, không I/O)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import asyncpg

COLS = {
    "vn_symbols": ["code", "floor", "kind", "name", "short_name", "listed_date", "industry_code", "industry_name", "in_vn30", "in_vn100",
                   "in_hnx30", "focus"],
    "vn_daily": ["code", "d", "floor", "basic", "ceil", "flr", "open", "high", "low", "close", "ad_close", "avg_price", "volume", "value",
                 "pt_volume", "pt_value", "pct"],
    "vn_index_daily": ["code", "d", "floor", "kind", "open", "high", "low", "close", "chg", "pct", "volume", "value", "pt_value", "advances",
                       "declines", "no_change", "no_trade", "ceiling_n", "floor_n"],
    "vn_foreign": ["code", "d", "floor", "buy_val", "sell_val", "net_val", "buy_vol", "sell_vol", "net_vol", "total_room", "current_room"],
    "vn_ratios": ["code", "as_of", "marketcap", "pe", "pb", "ps", "div_yield", "beta", "bvps", "chg_1m", "chg_3m", "chg_6m", "chg_1y", "hi_52w", "lo_52w"],
    "vn_events": ["event_id", "code", "etype", "type_desc", "note", "dividend", "ratio", "disclosure_date", "effective_date", "expired_date", "actual_date"],
}
PK = {"vn_symbols": ["code"], "vn_daily": ["code", "d"], "vn_index_daily": ["code", "d"], "vn_foreign": ["code", "d"],
      "vn_ratios": ["code"], "vn_events": ["event_id"]}

SNAPSHOT_SQL = """
SELECT d.code, d.floor, s.kind, s.name, s.short_name, s.industry_code, s.industry_name, s.in_vn30, s.in_vn100, s.in_hnx30, s.focus,
       d.d, d.basic, d.ceil, d.flr, d.open, d.high, d.low, d.close, d.ad_close, d.volume, d.value, d.pt_volume, d.pt_value, d.pct,
       r.marketcap, r.pe, r.pb, r.ps, r.div_yield, r.beta, r.bvps, r.chg_1m, r.chg_3m, r.chg_6m, r.chg_1y, r.hi_52w, r.lo_52w, r.as_of AS ratio_as_of,
       f.buy_val AS f_buy, f.sell_val AS f_sell, f.net_val AS f_net, f.net_vol AS f_net_vol, f.total_room, f.current_room
  FROM vn_daily d
  JOIN vn_symbols s ON s.code = d.code
  LEFT JOIN vn_ratios r ON r.code = d.code
  LEFT JOIN vn_foreign f ON f.code = d.code AND f.d = d.d
 WHERE d.d = $1
"""


def _rows(rs: Iterable[asyncpg.Record]) -> list[dict]:
    return [dict(r) for r in rs]


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Store":
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=30))

    async def close(self) -> None:
        await self.pool.close()

    # ---- ghi ----------------------------------------------------------------------------------------------------------------
    async def upsert(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        cols, pk = COLS[table], PK[table]
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in pk)
        extra = ", updated_at = now()" if table in ("vn_symbols", "vn_ratios", "vn_events") else ""
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(cols)))}) "
               f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {sets}{extra}")
        data = [tuple(r.get(c) for c in cols) for r in rows]
        async with self.pool.acquire() as con:
            for i in range(0, len(data), 2000):
                await con.executemany(sql, data[i:i + 2000])
        return len(rows)

    async def meta_get(self, key: str) -> dict | None:
        async with self.pool.acquire() as con:
            v = await con.fetchval("SELECT value FROM vn_meta WHERE key = $1", key)
        return json.loads(v) if isinstance(v, str) else v

    async def meta_set(self, key: str, value: dict) -> None:
        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO vn_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                              key, json.dumps(value, default=str))

    # ---- đọc ----------------------------------------------------------------------------------------------------------------
    async def counts(self) -> dict[str, Any]:
        async with self.pool.acquire() as con:
            r = await con.fetchrow("SELECT (SELECT count(*) FROM vn_symbols) AS symbols, (SELECT count(*) FROM vn_daily) AS daily_rows, "
                                   "(SELECT max(d) FROM vn_daily) AS last_daily, (SELECT count(DISTINCT d) FROM vn_daily) AS daily_dates, "
                                   "(SELECT max(d) FROM vn_foreign) AS last_foreign, (SELECT max(as_of) FROM vn_ratios) AS last_ratio, "
                                   "(SELECT count(*) FROM vn_events WHERE effective_date >= current_date) AS upcoming_events")
        return dict(r)

    async def latest_date(self) -> date | None:
        async with self.pool.acquire() as con:
            return await con.fetchval("SELECT max(d) FROM vn_index_daily WHERE code = 'VNINDEX'") or await con.fetchval("SELECT max(d) FROM vn_daily")

    async def trading_dates(self, n: int) -> list[date]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT DISTINCT d FROM vn_index_daily WHERE code = 'VNINDEX' ORDER BY d DESC LIMIT $1", n)
        return [r["d"] for r in rs]

    async def dates_with_prices(self, since: date) -> dict[date, int]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT d, count(*) AS n FROM vn_daily WHERE d >= $1 GROUP BY d", since)
        return {r["d"]: r["n"] for r in rs}

    async def foreign_dates(self, since: date) -> dict[date, int]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT d, count(*) AS n FROM vn_foreign WHERE d >= $1 GROUP BY d", since)
        return {r["d"]: r["n"] for r in rs}

    async def index_counts(self) -> dict[str, int]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT code, count(*) AS n FROM vn_index_daily GROUP BY code")
        return {r["code"]: r["n"] for r in rs}

    async def daily_coverage(self) -> dict[str, tuple[int, date]]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT code, count(*) AS n, min(d) AS first FROM vn_daily GROUP BY code")
        return {r["code"]: (r["n"], r["first"]) for r in rs}

    async def snapshot(self, d: date) -> list[dict]:
        async with self.pool.acquire() as con:
            return _rows(await con.fetch(SNAPSHOT_SQL, d))

    async def symbols(self, focus_only: bool = False) -> list[dict]:
        async with self.pool.acquire() as con:
            return _rows(await con.fetch("SELECT * FROM vn_symbols" + (" WHERE focus" if focus_only else "") + " ORDER BY code"))

    async def symbol_info(self, code: str) -> dict | None:
        async with self.pool.acquire() as con:
            r = await con.fetchrow("SELECT s.*, r.marketcap, r.pe, r.pb, r.ps, r.div_yield, r.beta, r.bvps, r.chg_1m, r.chg_3m, r.chg_6m, r.chg_1y, "
                                   "r.hi_52w, r.lo_52w, r.as_of AS ratio_as_of FROM vn_symbols s LEFT JOIN vn_ratios r USING (code) WHERE s.code = $1", code)
        return dict(r) if r else None

    async def index_on(self, d: date) -> list[dict]:
        async with self.pool.acquire() as con:
            return _rows(await con.fetch("SELECT * FROM vn_index_daily WHERE d = $1 ORDER BY code", d))

    async def index_series(self, code: str, n: int) -> list[dict]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT * FROM (SELECT * FROM vn_index_daily WHERE code = $1 ORDER BY d DESC LIMIT $2) t ORDER BY d", code, n)
        return _rows(rs)

    async def history(self, code: str, n: int) -> list[dict]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT * FROM (SELECT code, d, basic, ceil, flr, open, high, low, close, ad_close, volume, value, pt_value, pct "
                                 "FROM vn_daily WHERE code = $1 ORDER BY d DESC LIMIT $2) t ORDER BY d", code, n)
        return _rows(rs)

    async def closes(self, codes: list[str], since: date) -> list[dict]:
        async with self.pool.acquire() as con:
            return _rows(await con.fetch("SELECT code, d, ad_close, close, value FROM vn_daily WHERE code = ANY($1::text[]) AND d >= $2 ORDER BY code, d", codes, since))

    async def foreign_market_series(self, n: int) -> list[dict]:
        """Tổng khối ngoại theo ngày & sàn (cổ phiếu + ETF)."""
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT d, floor, sum(buy_val) AS buy_val, sum(sell_val) AS sell_val, sum(net_val) AS net_val FROM vn_foreign "
                                 "WHERE d IN (SELECT DISTINCT d FROM vn_foreign ORDER BY d DESC LIMIT $1) GROUP BY d, floor ORDER BY d, floor", n)
        return _rows(rs)

    async def foreign_series(self, code: str, n: int) -> list[dict]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT * FROM (SELECT * FROM vn_foreign WHERE code = $1 ORDER BY d DESC LIMIT $2) t ORDER BY d", code, n)
        return _rows(rs)

    async def foreign_cum(self, since: date) -> list[dict]:
        async with self.pool.acquire() as con:
            return _rows(await con.fetch("SELECT code, sum(net_val) AS net_val, sum(buy_val) AS buy_val, sum(sell_val) AS sell_val, count(*) AS days "
                                         "FROM vn_foreign WHERE d >= $1 GROUP BY code", since))

    async def liquidity_series(self, n: int) -> list[dict]:
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT d, floor, sum(value) AS value, sum(pt_value) AS pt_value, sum(volume) AS volume, count(*) FILTER (WHERE volume > 0) AS traded "
                                 "FROM vn_daily WHERE d IN (SELECT DISTINCT d FROM vn_index_daily WHERE code = 'VNINDEX' ORDER BY d DESC LIMIT $1) "
                                 "GROUP BY d, floor ORDER BY d, floor", n)
        return _rows(rs)

    async def events(self, start: date, end: date, codes: list[str] | None = None) -> list[dict]:
        async with self.pool.acquire() as con:
            if codes:
                rs = await con.fetch("SELECT e.*, s.name, s.floor, s.in_vn30, s.in_vn100, s.industry_name FROM vn_events e LEFT JOIN vn_symbols s USING (code) "
                                     "WHERE e.effective_date BETWEEN $1 AND $2 AND e.code = ANY($3::text[]) ORDER BY e.effective_date, e.code", start, end, codes)
            else:
                rs = await con.fetch("SELECT e.*, s.name, s.floor, s.in_vn30, s.in_vn100, s.industry_name FROM vn_events e LEFT JOIN vn_symbols s USING (code) "
                                     "WHERE e.effective_date BETWEEN $1 AND $2 ORDER BY e.effective_date, e.code", start, end)
        return _rows(rs)

    async def news_recent(self, days: int, limit: int = 600) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        async with self.pool.acquire() as con:
            rs = await con.fetch("SELECT url, title, summary, source, lang, published_at, ingested_at FROM news_items "
                                 "WHERE coalesce(published_at, ingested_at) >= $1 AND (lang = 'vi' OR lang IS NULL) "
                                 "ORDER BY coalesce(published_at, ingested_at) DESC LIMIT $2", since, limit)
        return _rows(rs)
