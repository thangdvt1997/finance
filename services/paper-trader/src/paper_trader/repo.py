"""Truy cập dữ liệu. Nến/analytics: role chỉ-đọc ts_ro. Journal mô phỏng: role ts_paper (CHỈ các bảng paper_*).
Có bản Memory cho test/dev. Journal (orders/fills/events/equity) là append-only; mọi ghi idempotent theo khoá tự nhiên."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from . import chain
from .models import AccountState, Order, StepResult, iso, parse_ts, utc

Row = dict[str, Any]


def _json(o: Any) -> str:
    return json.dumps(o, default=str, allow_nan=False)


class BarSource(Protocol):
    async def bars(self, symbol: str, tf: str, limit: int) -> list[Row]: ...
    async def analytics_summary(self, tf: str) -> dict | None: ...
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

    async def analytics_summary(self, tf):
        try:
            async with self.pool.acquire() as c:
                rows = await c.fetch("SELECT payload FROM analytics_snapshots WHERE kind='summary' AND key LIKE $1", f"%:{tf}")
        except Exception:  # noqa: BLE001 - bảng có thể chưa tồn tại
            return None
        out = {}
        for r in rows:
            p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
            out[p["symbol"]] = p
        return out or None


class MemoryBarSource:
    def __init__(self, data: dict[tuple[str, str], list[Row]], analytics: dict | None = None):
        self.data, self._an = data, analytics

    async def bars(self, symbol, tf, limit):
        rows = sorted(self.data.get((symbol, tf), []), key=lambda r: r["ts_open"], reverse=True)
        return rows[:limit]

    async def analytics_summary(self, tf):
        return self._an

    async def close(self):
        return None


class PaperStore(Protocol):
    async def get_account(self, account_id: str) -> Row | None: ...
    async def ensure_account(self, row: Row) -> None: ...
    async def save_step(self, account_id: str, res: StepResult, state: AccountState) -> list[str]: ...
    async def save_manual(self, account_id: str, state: AccountState, events: list[dict]) -> list[str]: ...
    async def list_accounts(self) -> list[Row]: ...
    async def equity(self, account_id: str, limit: int) -> list[Row]: ...
    async def positions(self, account_id: str) -> list[Row]: ...
    async def orders(self, account_id: str, limit: int) -> list[Row]: ...
    async def fills(self, account_id: str, limit: int) -> list[Row]: ...
    async def events(self, account_id: str | None, limit: int) -> list[Row]: ...
    async def close(self) -> None: ...
    # --- quản trị: hash-chain + phiên bản cấu hình (xem chain.py)
    async def chain_bootstrap(self, account_id: str) -> int: ...
    async def chain_entries(self, account_id: str) -> list[Row]: ...
    async def chain_live(self, account_id: str) -> tuple[dict, dict]: ...
    async def register_config(self, account_id: str, config_hash: str, params_hash: str, config: dict) -> dict: ...
    async def config_versions(self, account_id: str) -> list[Row]: ...
    async def all_fills(self, account_id: str) -> list[Row]: ...


# ======================================================================================= PostgreSQL (ts_paper)
class PgPaperStore:
    def __init__(self, pool, has_chain: bool = False, has_versions: bool = False):
        self.pool = pool
        self.has_chain, self.has_versions = has_chain, has_versions     # bảng 004_paper_governance.sql (chưa áp migration -> tắt, không làm hỏng runner)

    @classmethod
    async def connect(cls, dsn: str) -> "PgPaperStore":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=_json, decoder=json.loads, schema="pg_catalog")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=30, init=init)
        async with pool.acquire() as c:
            ch = await c.fetchval("SELECT to_regclass('paper_chain') IS NOT NULL")
            cv = await c.fetchval("SELECT to_regclass('paper_config_versions') IS NOT NULL")
        return cls(pool, bool(ch), bool(cv))

    async def close(self) -> None:
        await self.pool.close()

    async def get_account(self, account_id):
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT * FROM paper_accounts WHERE account_id=$1", account_id)
        return dict(r) if r else None

    async def ensure_account(self, row):
        sql = ("INSERT INTO paper_accounts (account_id, name, strategy, base_ccy, initial_capital, benchmark_id, meaningful, config, state, status, cash) "
               "VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,'active',$5) "
               "ON CONFLICT (account_id) DO UPDATE SET name=EXCLUDED.name, strategy=EXCLUDED.strategy, benchmark_id=EXCLUDED.benchmark_id, "
               "meaningful=EXCLUDED.meaningful, config=EXCLUDED.config, updated_at=now()")
        async with self.pool.acquire() as c:
            await c.execute(sql, row["account_id"], row["name"], row["strategy"], row["base_ccy"], float(row["initial_capital"]),
                            row.get("benchmark_id"), bool(row.get("meaningful", True)), row["config"], row["state"])

    async def _write(self, c, account_id: str, state: AccountState, events: list[dict]) -> list[str]:
        new_keys: list[str] = []
        for e in events:
            k = await c.fetchval(
                "INSERT INTO paper_events (account_id, ts, type, severity, message, data, event_key) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7) "
                "ON CONFLICT (account_id, event_key) DO NOTHING RETURNING event_key",
                account_id, e["ts"], e["type"], e["severity"], e["message"], e["data"], e["key"])
            if k:
                new_keys.append(k)
        await c.execute("UPDATE paper_accounts SET cash=$2, status=$3, halt_reason=$4, halt_until=$5, last_close=$6, state=$7::jsonb, updated_at=now() "
                        "WHERE account_id=$1", account_id, state.cash, state.status, state.halt_reason, state.halt_until, state.last_close, state.to_dict())
        if self.has_chain and new_keys:
            await self._chain_append(c, account_id, chain.items_from_events(account_id, [e for e in events if e["key"] in new_keys]))
        return new_keys

    # ------------------------------------------------------------------ hash-chain
    async def _chain_append(self, c, account_id: str, items: list[dict]) -> int:
        """Nối `items` vào chuỗi của tài khoản (trong CÙNG transaction với bản ghi nguồn). Bỏ qua mục đã có (idempotent)."""
        if not items:
            return 0
        await c.fetchval("SELECT 1 FROM paper_accounts WHERE account_id=$1 FOR UPDATE", account_id)      # tuần tự hoá người ghi
        have = {(r["kind"], r["ref"]) for r in await c.fetch("SELECT kind, ref FROM paper_chain WHERE account_id=$1 AND ref = ANY($2::text[])",
                                                               account_id, list({i["ref"] for i in items}))}
        fresh, seen = [], set()
        for i in items:
            k = (i["kind"], i["ref"])
            if k not in have and k not in seen:
                seen.add(k)
                fresh.append(i)
        if not fresh:
            return 0
        tail = await c.fetchrow("SELECT seq, row_hash FROM paper_chain WHERE account_id=$1 ORDER BY seq DESC LIMIT 1", account_id)
        rows = chain.link(account_id, tail["seq"] if tail else 0, tail["row_hash"] if tail else None, fresh)
        await c.executemany("INSERT INTO paper_chain (account_id, seq, kind, ref, ts, content_hash, prev_hash, row_hash) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                            [(r["account_id"], r["seq"], r["kind"], r["ref"], r["ts"], r["content_hash"], r["prev_hash"], r["row_hash"]) for r in rows])
        return len(rows)

    async def chain_entries(self, account_id):
        if not self.has_chain:
            return []
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM paper_chain WHERE account_id=$1 ORDER BY seq", account_id)]

    async def chain_live(self, account_id):
        """Băm LẠI nội dung hiện tại của các bảng nguồn (để so với chuỗi). Trả ({kind:{ref:content_hash}}, {client_order_id: status})."""
        async with self.pool.acquire() as c:
            orders = await c.fetch("SELECT * FROM paper_orders WHERE account_id=$1", account_id)
            fills = await c.fetch("SELECT * FROM paper_fills WHERE account_id=$1", account_id)
            evs = await c.fetch("SELECT * FROM paper_events WHERE account_id=$1", account_id)
            eqs = await c.fetch("SELECT * FROM paper_equity WHERE account_id=$1", account_id)
        live = {"order": {r["client_order_id"]: chain.hash_obj(chain.c_order(account_id, dict(r))) for r in orders},
                "fill": {r["client_order_id"]: chain.hash_obj(chain.c_fill(account_id, dict(r))) for r in fills},
                "event": {r["event_key"]: chain.hash_obj(chain.c_event(account_id, dict(r))) for r in evs},
                "equity": {iso(r["ts"]): chain.hash_obj(chain.c_equity(account_id, dict(r))) for r in eqs}}
        return live, {r["client_order_id"]: r["status"] for r in orders}

    async def chain_bootstrap(self, account_id):
        """Chuỗi còn trống mà đã có bản ghi cũ (trước khi có hash-chain) -> neo (genesis) toàn bộ hiện trạng làm điểm xuất phát.
        Chỉ chạy khi chuỗi RỖNG. Từ đây trở đi mới bảo vệ được; bản ghi trước mốc này không chứng minh được nguyên vẹn."""
        if not self.has_chain:
            return 0
        async with self.pool.acquire() as c, c.transaction():
            await c.fetchval("SELECT 1 FROM paper_accounts WHERE account_id=$1 FOR UPDATE", account_id)
            if await c.fetchval("SELECT count(*) FROM paper_chain WHERE account_id=$1", account_id):
                return 0
            items: list[dict] = []
            for r in await c.fetch("SELECT * FROM paper_orders WHERE account_id=$1", account_id):
                d = dict(r)
                items.append(chain.item("order", d["client_order_id"], chain.c_order(account_id, d), d["decision_ts"]))
                items.append(chain.item("order_status", f"{d['client_order_id']}#{d['status']}", chain.c_order_status(d), d["decision_ts"]))
            for r in await c.fetch("SELECT * FROM paper_fills WHERE account_id=$1", account_id):
                d = dict(r)
                items.append(chain.item("fill", d["client_order_id"], chain.c_fill(account_id, d), d["ts"]))
            for r in await c.fetch("SELECT * FROM paper_events WHERE account_id=$1", account_id):
                d = dict(r)
                items.append(chain.item("event", d["event_key"], chain.c_event(account_id, d), d["ts"]))
            for r in await c.fetch("SELECT * FROM paper_equity WHERE account_id=$1", account_id):
                d = dict(r)
                items.append(chain.item("equity", iso(d["ts"]), chain.c_equity(account_id, d), d["ts"]))
            return await self._chain_append(c, account_id, chain.sort_items(items))

    # ------------------------------------------------------------------ phiên bản cấu hình bất biến
    async def register_config(self, account_id, config_hash, params_hash, config):
        if not self.has_versions:
            return {"version": None, "new": False, "config_hash": config_hash, "disabled": True}
        async with self.pool.acquire() as c, c.transaction():
            last = await c.fetchrow("SELECT version, config_hash FROM paper_config_versions WHERE account_id=$1 ORDER BY version DESC LIMIT 1", account_id)
            if last and last["config_hash"] == config_hash:
                return {"version": last["version"], "new": False, "config_hash": config_hash}
            v = (last["version"] if last else 0) + 1
            await c.execute("INSERT INTO paper_config_versions (account_id, version, config_hash, params_hash, config) VALUES ($1,$2,$3,$4,$5::jsonb)",
                            account_id, v, config_hash, params_hash, config)
            return {"version": v, "new": True, "config_hash": config_hash, "previous": last["config_hash"] if last else None}

    async def config_versions(self, account_id):
        if not self.has_versions:
            return []
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT version, config_hash, params_hash, config, created_at FROM paper_config_versions "
                                                    "WHERE account_id=$1 ORDER BY version", account_id)]

    async def all_fills(self, account_id):
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM paper_fills WHERE account_id=$1 ORDER BY ts, fill_id", account_id)]

    async def save_step(self, account_id, res, state):
        async with self.pool.acquire() as c, c.transaction():
            for o in res.new_orders:
                await c.execute(
                    "INSERT INTO paper_orders (client_order_id, account_id, symbol, side, qty, kind, status, reason, target_weight, ref_price, decision_ts, eligible_from) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT (client_order_id) DO NOTHING",
                    o.client_order_id, account_id, o.symbol, o.side, o.qty, o.kind, o.status, o.reason, o.target_weight, o.ref_price,
                    o.decision_ts, o.eligible_from)
            for o in res.order_updates:
                await c.execute("UPDATE paper_orders SET status=$2, reason=$3, updated_at=now() WHERE client_order_id=$1",
                                o.client_order_id, o.status, o.reason)
            for f in res.fills:
                await c.execute(
                    "INSERT INTO paper_fills (client_order_id, account_id, symbol, side, qty, ts, ref_price, price, spread_cost, slippage_cost, commission, tax, realized_pnl, q2b) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) ON CONFLICT (client_order_id) DO NOTHING",
                    f.client_order_id, account_id, f.symbol, f.side, f.qty, f.ts, f.ref_price, f.price, f.spread_cost, f.slippage_cost,
                    f.commission, f.tax, f.realized_pnl, f.q2b)
            await c.execute(
                "INSERT INTO paper_equity (account_id, ts, equity, cash, gross_exposure, net_exposure, drawdown, swap_cost) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
                "ON CONFLICT (account_id, ts) DO NOTHING", account_id, res.close_ts, res.equity, res.cash, res.gross, res.net, res.drawdown, res.swap_step)
            for sym, d in res.positions.items():
                await c.execute(
                    "INSERT INTO paper_positions (account_id, symbol, qty, avg_price, mark_price, unrealized_pnl, notional, updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
                    "ON CONFLICT (account_id, symbol) DO UPDATE SET qty=EXCLUDED.qty, avg_price=EXCLUDED.avg_price, mark_price=EXCLUDED.mark_price, "
                    "unrealized_pnl=EXCLUDED.unrealized_pnl, notional=EXCLUDED.notional, updated_at=EXCLUDED.updated_at",
                    account_id, sym, d["qty"], d["avg_price"], d["mark"], d["unrealized"], d["notional"], res.close_ts)
            if self.has_chain:
                await self._chain_append(c, account_id, chain.items_from_step(account_id, res))
            return await self._write(c, account_id, state, res.events)

    async def save_manual(self, account_id, state, events):
        async with self.pool.acquire() as c, c.transaction():
            return await self._write(c, account_id, state, events)

    async def list_accounts(self):
        sql = ("SELECT a.*, e.ts AS equity_ts, e.equity, e.drawdown, e.gross_exposure, e.net_exposure FROM paper_accounts a "
               "LEFT JOIN LATERAL (SELECT * FROM paper_equity WHERE account_id=a.account_id ORDER BY ts DESC LIMIT 1) e ON true ORDER BY a.account_id")
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch(sql)]

    async def equity(self, account_id, limit):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT ts, equity, cash, gross_exposure, net_exposure, drawdown, swap_cost FROM paper_equity "
                                 "WHERE account_id=$1 ORDER BY ts DESC LIMIT $2", account_id, limit)
        return [dict(r) for r in reversed(rows)]

    async def positions(self, account_id):
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM paper_positions WHERE account_id=$1 AND qty<>0 ORDER BY symbol", account_id)]

    async def orders(self, account_id, limit):
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM paper_orders WHERE account_id=$1 ORDER BY decision_ts DESC, symbol LIMIT $2", account_id, limit)]

    async def fills(self, account_id, limit):
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM paper_fills WHERE account_id=$1 ORDER BY ts DESC, fill_id DESC LIMIT $2", account_id, limit)]

    async def events(self, account_id, limit):
        async with self.pool.acquire() as c:
            if account_id:
                rows = await c.fetch("SELECT * FROM paper_events WHERE account_id=$1 ORDER BY ts DESC, id DESC LIMIT $2", account_id, limit)
            else:
                rows = await c.fetch("SELECT * FROM paper_events ORDER BY ts DESC, id DESC LIMIT $1", limit)
        return [dict(r) for r in rows]


# ======================================================================================= Memory (test/dev)
class MemoryPaperStore:
    def __init__(self):
        self.accounts: dict[str, Row] = {}
        self.orders_: dict[str, Row] = {}
        self.fills_: dict[str, Row] = {}
        self.equity_: dict[tuple[str, datetime], Row] = {}
        self.positions_: dict[tuple[str, str], Row] = {}
        self.events_: dict[tuple[str, str], Row] = {}
        self.chain_: dict[str, list[Row]] = {}
        self.versions_: dict[str, list[Row]] = {}

    async def close(self):
        return None

    async def get_account(self, account_id):
        return self.accounts.get(account_id)

    async def ensure_account(self, row):
        cur = self.accounts.get(row["account_id"])
        if cur:
            cur.update({k: row[k] for k in ("name", "strategy", "benchmark_id", "meaningful", "config") if k in row})
        else:
            self.accounts[row["account_id"]] = {**row, "status": "active", "cash": float(row["initial_capital"]), "halt_reason": "", "halt_until": None, "last_close": None}

    def _write(self, account_id, state: AccountState, events) -> list[str]:
        new = []
        for e in events:
            k = (account_id, e["key"])
            if k not in self.events_:
                self.events_[k] = {"id": len(self.events_) + 1, "account_id": account_id, "ts": e["ts"], "type": e["type"], "severity": e["severity"],
                                   "message": e["message"], "data": json.loads(_json(e["data"])), "event_key": e["key"]}
                new.append(e["key"])
        a = self.accounts[account_id]
        a.update(cash=state.cash, status=state.status, halt_reason=state.halt_reason, halt_until=state.halt_until,
                 last_close=state.last_close, state=json.loads(_json(state.to_dict())))
        if new:
            self._chain_append(account_id, chain.items_from_events(account_id, [e for e in events if e["key"] in new]))
        return new

    def _chain_append(self, account_id: str, items: list[dict]) -> int:
        ents = self.chain_.setdefault(account_id, [])
        have = {(e["kind"], e["ref"]) for e in ents}
        fresh, seen = [], set()
        for i in items:
            k = (i["kind"], i["ref"])
            if k not in have and k not in seen:
                seen.add(k)
                fresh.append(i)
        rows = chain.link(account_id, ents[-1]["seq"] if ents else 0, ents[-1]["row_hash"] if ents else None, fresh)
        ents.extend(rows)
        return len(rows)

    async def chain_entries(self, account_id):
        return [dict(e) for e in self.chain_.get(account_id, [])]

    async def chain_live(self, account_id):
        orders = [v for v in self.orders_.values() if v["account_id"] == account_id]
        live = {"order": {o["client_order_id"]: chain.hash_obj(chain.c_order(account_id, o)) for o in orders},
                "fill": {f["client_order_id"]: chain.hash_obj(chain.c_fill(account_id, f)) for f in self.fills_.values() if f["account_id"] == account_id},
                "event": {e["event_key"]: chain.hash_obj(chain.c_event(account_id, e)) for (a, _), e in self.events_.items() if a == account_id},
                "equity": {iso(r["ts"]): chain.hash_obj(chain.c_equity(account_id, r)) for (a, _), r in self.equity_.items() if a == account_id}}
        return live, {o["client_order_id"]: o["status"] for o in orders}

    async def chain_bootstrap(self, account_id):
        if self.chain_.get(account_id):
            return 0
        items: list[dict] = []
        for o in (v for v in self.orders_.values() if v["account_id"] == account_id):
            items.append(chain.item("order", o["client_order_id"], chain.c_order(account_id, o), o["decision_ts"]))
            items.append(chain.item("order_status", f"{o['client_order_id']}#{o['status']}", chain.c_order_status(o), o["decision_ts"]))
        for f in (v for v in self.fills_.values() if v["account_id"] == account_id):
            items.append(chain.item("fill", f["client_order_id"], chain.c_fill(account_id, f), f["ts"]))
        for (a, _), e in self.events_.items():
            if a == account_id:
                items.append(chain.item("event", e["event_key"], chain.c_event(account_id, e), e["ts"]))
        for (a, _), r in self.equity_.items():
            if a == account_id:
                items.append(chain.item("equity", iso(r["ts"]), chain.c_equity(account_id, r), r["ts"]))
        return self._chain_append(account_id, chain.sort_items(items))

    async def register_config(self, account_id, config_hash, params_hash, config):
        vs = self.versions_.setdefault(account_id, [])
        if vs and vs[-1]["config_hash"] == config_hash:
            return {"version": vs[-1]["version"], "new": False, "config_hash": config_hash}
        vs.append({"version": len(vs) + 1, "config_hash": config_hash, "params_hash": params_hash, "config": config,
                   "created_at": datetime.now().astimezone()})
        return {"version": len(vs), "new": True, "config_hash": config_hash, "previous": vs[-2]["config_hash"] if len(vs) > 1 else None}

    async def config_versions(self, account_id):
        return [dict(v) for v in self.versions_.get(account_id, [])]

    async def all_fills(self, account_id):
        return sorted((v for v in self.fills_.values() if v["account_id"] == account_id), key=lambda r: r["ts"])

    async def save_step(self, account_id, res, state):
        for o in res.new_orders:
            self.orders_.setdefault(o.client_order_id, {**o.to_dict(), "decision_ts": o.decision_ts, "eligible_from": o.eligible_from})
        for o in res.order_updates:
            if o.client_order_id in self.orders_:
                self.orders_[o.client_order_id].update(status=o.status, reason=o.reason)
        for f in res.fills:
            self.fills_.setdefault(f.client_order_id, f.to_dict() | {"ts": f.ts})
        self.equity_.setdefault((account_id, res.close_ts), {"ts": res.close_ts, "equity": res.equity, "cash": res.cash, "gross_exposure": res.gross,
                                                            "net_exposure": res.net, "drawdown": res.drawdown, "swap_cost": res.swap_step})
        for sym, d in res.positions.items():
            self.positions_[(account_id, sym)] = {"account_id": account_id, "symbol": sym, "qty": d["qty"], "avg_price": d["avg_price"],
                                                  "mark_price": d["mark"], "unrealized_pnl": d["unrealized"], "notional": d["notional"], "updated_at": res.close_ts}
        self._chain_append(account_id, chain.items_from_step(account_id, res))
        return self._write(account_id, state, res.events)

    async def save_manual(self, account_id, state, events):
        return self._write(account_id, state, events)

    async def list_accounts(self):
        out = []
        for aid, a in sorted(self.accounts.items()):
            eq = sorted((v for (x, _), v in self.equity_.items() if x == aid), key=lambda r: r["ts"])
            last = eq[-1] if eq else {}
            out.append({**a, "equity_ts": last.get("ts"), "equity": last.get("equity"), "drawdown": last.get("drawdown"),
                        "gross_exposure": last.get("gross_exposure"), "net_exposure": last.get("net_exposure")})
        return out

    async def equity(self, account_id, limit):
        eq = sorted((v for (x, _), v in self.equity_.items() if x == account_id), key=lambda r: r["ts"])
        return eq[-limit:]

    async def positions(self, account_id):
        return [v for (a, _), v in sorted(self.positions_.items()) if a == account_id and v["qty"] != 0]

    async def orders(self, account_id, limit):
        rows = [v for v in self.orders_.values() if v["account_id"] == account_id]
        return sorted(rows, key=lambda r: (r["decision_ts"], r["symbol"]), reverse=True)[:limit]

    async def fills(self, account_id, limit):
        rows = [v for v in self.fills_.values() if v["account_id"] == account_id]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)[:limit]

    async def events(self, account_id, limit):
        rows = [v for (a, _), v in self.events_.items() if account_id is None or a == account_id]
        return sorted(rows, key=lambda r: (r["ts"], r["id"]), reverse=True)[:limit]


__all__ = ["BarSource", "PaperStore", "PgBarSource", "PgPaperStore", "MemoryBarSource", "MemoryPaperStore", "iso", "parse_ts", "utc", "timedelta"]
