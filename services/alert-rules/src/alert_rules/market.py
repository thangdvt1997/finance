"""Provider dữ liệu cho evaluator: ĐỌC DB bằng role chỉ-đọc ts_ro (DATABASE_URL). Lỗi truy vấn -> None/rỗng (điều kiện thành 'không rõ')."""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger("alert_rules.market")


class PgMarket:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgMarket":
        import asyncpg

        async def init(c):
            import json
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=15, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def latest_price(self, symbol):
        async with self.pool.acquire() as c:
            q = await c.fetchrow("SELECT bid, ask, ts, source FROM quotes WHERE symbol=$1 AND ts > now() - interval '3 days' "
                                 "ORDER BY ts DESC LIMIT 1", symbol)
            b = await c.fetchrow("SELECT c, ts_open, source FROM bars WHERE symbol=$1 AND tf IN ('M1','M5','M15','H1','D1') "
                                 "AND ts_open > now() - interval '10 days' ORDER BY ts_open DESC LIMIT 1", symbol)
        out = None
        if q and (q["bid"] or q["ask"]):
            px = [x for x in (q["bid"], q["ask"]) if x]
            out = {"mid": sum(px) / len(px), "ts": q["ts"].timestamp(), "source": q["source"]}
        if b and (not out or b["ts_open"].timestamp() > out["ts"]):
            out = {"mid": float(b["c"]), "ts": b["ts_open"].timestamp(), "source": b["source"]}
        return out

    async def bar_closes(self, symbol, minutes):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT DISTINCT ON (ts_open) ts_open, c FROM bars WHERE symbol=$1 AND tf='M1' "
                                 "AND ts_open > now() - make_interval(mins => $2) ORDER BY ts_open, source", symbol, minutes)
        return [(r["ts_open"].timestamp() + 60, float(r["c"])) for r in rows]

    async def analytics(self, symbol, tf):
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT payload, updated_at FROM analytics_snapshots WHERE kind='summary' AND key=$1", f"{symbol}:{tf}")
        return (r["payload"], r["updated_at"].timestamp()) if r else None

    async def calendar(self, impacts, start: datetime, end: datetime, country):
        sql = ("SELECT event_id, title, country, impact, ts FROM calendar_events WHERE COALESCE(source,'') <> 'qa' AND impact = ANY($1::text[]) AND ts BETWEEN $2 AND $3")
        args: list = [impacts, start, end]
        if country:
            sql += " AND upper(country) = upper($4)"
            args.append(country)
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql + " ORDER BY ts LIMIT 50", *args)]

    async def sentiment(self, symbol, start, end):
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT avg(sentiment) AS a, count(sentiment) AS n FROM news_items WHERE $1 = ANY(symbols) "
                                 "AND published_at >= $2 AND published_at < $3 AND sentiment IS NOT NULL", symbol, start, end)
        return (float(r["a"]) if r["a"] is not None else None), int(r["n"])

    async def accounts(self):
        sql = ("WITH last AS (SELECT DISTINCT ON (account_id) account_id, ts, balance, equity, margin FROM account_snapshots "
               "WHERE ts > now() - interval '2 hours' ORDER BY account_id, ts DESC), "
               "peak AS (SELECT account_id, max(equity) AS peak24 FROM account_snapshots WHERE ts > now() - interval '24 hours' GROUP BY account_id) "
               "SELECT l.account_id, l.ts, l.balance, l.equity, l.margin, p.peak24 FROM last l LEFT JOIN peak p USING (account_id) "
               # tài khoản thử QA (qa-*, mt5:99xxxxxx; trừ demo cũ mt5:99000001) không sinh cảnh báo/ntfy
               "WHERE l.account_id !~ '^(qa-|mt5:99)' OR l.account_id = 'mt5:99000001'")
        async with self.pool.acquire() as c:
            rows = await c.fetch(sql)
        return [{**dict(r), "ts": r["ts"].timestamp()} for r in rows]

    async def limit_metrics(self, account_id: str, now: datetime) -> dict | None:
        """Số liệu tiến độ giới hạn của 1 tài khoản (đọc account_snapshots/account_deals; ngày/tháng theo giờ VN). Thiếu dữ liệu -> None."""
        from datetime import timedelta
        from .limits import day_start, month_start

        ds, ms = day_start(now), month_start(now)
        async with self.pool.acquire() as c:
            last = await c.fetchrow("SELECT ts, equity, margin, positions FROM account_snapshots WHERE account_id=$1 AND ts > $2 ORDER BY ts DESC LIMIT 1",
                                    account_id, now - timedelta(days=3))
            if not last:
                return None

            async def base(start, back):
                r = await c.fetchrow("SELECT equity FROM account_snapshots WHERE account_id=$1 AND ts <= $2 AND ts > $3 ORDER BY ts DESC LIMIT 1", account_id, start, start - back)
                if r is None:
                    r = await c.fetchrow("SELECT equity FROM account_snapshots WHERE account_id=$1 AND ts > $2 ORDER BY ts LIMIT 1", account_id, start)
                return r["equity"] if r else None

            eq_day, eq_month = await base(ds, timedelta(hours=48)), await base(ms, timedelta(days=7))
            peak = await c.fetchval("SELECT max(equity) FROM account_snapshots WHERE account_id=$1 AND ts > $2", account_id, now - timedelta(days=30))
            flows = await c.fetchrow("SELECT COALESCE(sum(profit) FILTER (WHERE time_close >= $2), 0) AS d, COALESCE(sum(profit), 0) AS m FROM account_deals "
                                     "WHERE account_id=$1 AND side='balance' AND time_close >= $3", account_id, ds, ms)
            closed = await c.fetch("SELECT DISTINCT position_id FROM account_deals WHERE account_id=$1 AND side <> 'balance' AND time_open >= $2", account_id, ds)
        seen = {r["position_id"] for r in closed}
        poss = last["positions"] if isinstance(last["positions"], list) else []
        for p in poss:
            if not isinstance(p, dict):
                continue
            t = p.get("time_open")
            try:
                ts = datetime.fromisoformat(t.replace("Z", "+00:00")) if isinstance(t, str) else datetime.fromtimestamp(float(t), tz=ds.tzinfo)
            except (TypeError, ValueError):
                continue
            if ts >= ds:
                seen.add(str(p.get("position_id") or p.get("ticket") or id(p)))
        return {"as_of": last["ts"].timestamp(), "equity": last["equity"], "margin": last["margin"], "equity_day_start": eq_day, "equity_month_start": eq_month,
                "peak_equity": peak, "flows_day": float(flows["d"]), "flows_month": float(flows["m"]), "orders_today": len(seen)}
