"""Lưu trữ: đọc nến + pattern_signals bằng ts_ro; ghi pattern_scan_events/media + pattern_paper_trades/ledger bằng role hẹp ts_pscan."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .paper import GENESIS, chain_hash

Row = dict[str, Any]
_TF = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
EV_COLS = "id, setup_id, pattern, symbol, tf, state, score, bar_ts, ts, levels, steps, reason, points, live, received_at"
TR_COLS = ("id, setup_id, pattern, symbol, tf, side, opened_at, entry, sl, r, tp, status, closed_at, legs, cost_r, result_r, mfe_r, mae_r, "
           "bars_held, last_bar_ts, replay, open_hash")


def _dt(v) -> datetime:
    if isinstance(v, datetime):
        return v
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _js(d: dict, *keys) -> dict:
    for k in keys:
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


class PgStore:
    def __init__(self, ro, rw):
        self.ro, self.rw = ro, rw

    @classmethod
    async def connect(cls, read_url: str, write_url: str) -> "PgStore":
        import asyncpg
        ro = await asyncpg.create_pool(read_url, min_size=1, max_size=3, command_timeout=30)
        rw = await asyncpg.create_pool(write_url, min_size=1, max_size=3, command_timeout=30)
        return cls(ro, rw)

    async def close(self) -> None:
        await self.ro.close()
        await self.rw.close()

    # ---- nến (chỉ đọc) ----
    async def bars_until(self, symbol: str, tf: str, until_open: datetime, limit: int) -> list[Row]:
        # cận dưới thời gian để TimescaleDB loại chunk (không có -> quét mọi chunk, quá statement_timeout)
        lo = until_open - timedelta(seconds=_TF.get(tf, 900) * limit * 3 + 10 * 86400)
        sql = ("SELECT DISTINCT ON (ts_open) ts_open, o, h, l, c FROM bars WHERE symbol=$1 AND tf=$2 AND ts_open <= $3 AND ts_open > $5 "
               "ORDER BY ts_open DESC, source LIMIT $4")
        async with self.ro.acquire() as c:
            rows = [dict(r) for r in await c.fetch(sql, symbol, tf, until_open, limit, lo)]
        return sorted(rows, key=lambda r: r["ts_open"])

    async def bars_after(self, symbol: str, tf: str, after_open: datetime, limit: int = 500) -> list[Row]:
        hi = after_open + timedelta(seconds=_TF.get(tf, 900) * limit * 3 + 10 * 86400)
        sql = ("SELECT DISTINCT ON (ts_open) ts_open, o, h, l, c FROM bars WHERE symbol=$1 AND tf=$2 AND ts_open > $3 AND ts_open <= $5 "
               "ORDER BY ts_open ASC, source LIMIT $4")
        async with self.ro.acquire() as c:
            return [dict(r) for r in await c.fetch(sql, symbol, tf, after_open, limit, hi)]

    async def signals_since(self, since: datetime) -> list[Row]:
        sql = ("SELECT setup_id, pattern, symbol, tf, state, side, score, bar_ts, ts, levels, steps, reason FROM pattern_signals "
               "WHERE created_at >= $1 ORDER BY id ASC LIMIT 5000")
        async with self.ro.acquire() as c:
            try:
                rows = await c.fetch(sql, since)
            except Exception:  # noqa: BLE001 - bảng chưa có (migration 018 chưa áp)
                return []
        return [_js(dict(r), "levels", "steps") for r in rows]

    # ---- sự kiện + ảnh ----
    async def insert_event(self, p: dict, live: bool) -> int | None:
        sql = ("INSERT INTO pattern_scan_events (setup_id, pattern, symbol, tf, state, score, bar_ts, ts, levels, steps, reason, points, live) "
               "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12::jsonb,$13) "
               "ON CONFLICT (setup_id, symbol, tf, state) DO NOTHING RETURNING id")
        async with self.rw.acquire() as c:
            return await c.fetchval(sql, p["setup_id"], p["pattern"], p["symbol"], p["tf"], p["state"], float(p.get("score") or 0),
                                    _dt(p["bar_ts"]), _dt(p["ts"]), json.dumps(p.get("levels") or {}),
                                    json.dumps(p.get("steps") or [], ensure_ascii=False), p.get("reason"),
                                    json.dumps(p.get("points") or []), live)

    async def events(self, since: datetime, limit: int = 5000) -> list[Row]:
        sql = f"SELECT {EV_COLS}, EXISTS (SELECT 1 FROM pattern_scan_media m WHERE m.event_id=e.id) AS has_image " \
              f"FROM pattern_scan_events e WHERE bar_ts >= $1 ORDER BY bar_ts DESC, id DESC LIMIT $2"
        async with self.rw.acquire() as c:
            return [_js(dict(r), "levels", "steps", "points") for r in await c.fetch(sql, since, limit)]

    async def event(self, eid: int) -> Row | None:
        async with self.rw.acquire() as c:
            r = await c.fetchrow(f"SELECT {EV_COLS} FROM pattern_scan_events WHERE id=$1", eid)
        return _js(dict(r), "levels", "steps", "points") if r else None

    async def put_media(self, eid: int, png: bytes) -> None:
        async with self.rw.acquire() as c:
            await c.execute("INSERT INTO pattern_scan_media (event_id, png) VALUES ($1,$2) ON CONFLICT DO NOTHING", eid, png)

    async def media(self, eid: int) -> tuple[bytes, str] | None:
        async with self.rw.acquire() as c:
            r = await c.fetchrow("SELECT m.png, e.state FROM pattern_scan_media m JOIN pattern_scan_events e ON e.id=m.event_id "
                                 "WHERE m.event_id=$1", eid)
        return (bytes(r["png"]), r["state"]) if r else None

    # ---- lệnh paper + sổ cái ----
    async def insert_trade(self, t: dict) -> int | None:
        async with self.rw.acquire() as c, c.transaction():
            tid = await c.fetchval(
                "INSERT INTO pattern_paper_trades (setup_id, pattern, symbol, tf, side, opened_at, entry, sl, r, tp, status, legs, cost_r, "
                "mfe_r, mae_r, bars_held, last_bar_ts, replay) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12::jsonb,$13,$14,$15,$16,$17,$18) "
                "ON CONFLICT (setup_id, symbol, tf) DO NOTHING RETURNING id",
                t["setup_id"], t["pattern"], t["symbol"], t["tf"], t["side"], _dt(t["opened_at"]), t["entry"], t["sl"], t["r"],
                json.dumps(t["tp"]), t["status"], json.dumps(t["legs"]), t["cost_r"], t["mfe_r"], t["mae_r"], t["bars_held"],
                _dt(t["last_bar_ts"]), t["replay"])
            if tid is None:
                return None
            h = await self._ledger(c, "open", str(tid), _open_content(tid, t))
            await c.execute("UPDATE pattern_paper_trades SET open_hash=$2 WHERE id=$1", tid, h)
            return tid

    async def update_trade(self, t: dict, closed: bool) -> None:
        async with self.rw.acquire() as c, c.transaction():
            await c.execute(
                "UPDATE pattern_paper_trades SET status=$2, closed_at=$3, legs=$4::jsonb, result_r=$5, mfe_r=$6, mae_r=$7, bars_held=$8, "
                "last_bar_ts=$9, updated_at=now() WHERE id=$1 AND status='open'",
                t["id"], t["status"], _dt(t["closed_at"]) if t.get("closed_at") else None, json.dumps(t["legs"]), t.get("result_r"),
                t["mfe_r"], t["mae_r"], t["bars_held"], _dt(t["last_bar_ts"]))
            if closed:
                await self._ledger(c, "close", str(t["id"]), _close_content(t))

    async def _ledger(self, c, kind: str, ref: str, content: dict) -> str:
        await c.execute("SELECT pg_advisory_xact_lock(hashtext('pattern_paper_ledger'))")
        prev = await c.fetchval("SELECT hash FROM pattern_paper_ledger ORDER BY seq DESC LIMIT 1") or GENESIS
        h = chain_hash(prev, kind, ref, content)
        await c.execute("INSERT INTO pattern_paper_ledger (kind, ref, content, prev_hash, hash) VALUES ($1,$2,$3::jsonb,$4,$5)",
                        kind, ref, json.dumps(content, ensure_ascii=False), prev, h)
        return h

    async def trades(self, status: str | None = None, limit: int = 1000) -> list[Row]:
        sql = f"SELECT {TR_COLS} FROM pattern_paper_trades WHERE ($1::text IS NULL OR status=$1) ORDER BY opened_at DESC LIMIT $2"
        async with self.rw.acquire() as c:
            return [_js(dict(r), "tp", "legs") for r in await c.fetch(sql, status, limit)]

    async def calendar_events(self, start: datetime, end: datetime) -> list[Row]:
        async with self.ro.acquire() as c:
            return [dict(r) for r in await c.fetch(
                "SELECT event_id, title, country, impact, ts FROM calendar_events WHERE impact='high' AND ts BETWEEN $1 AND $2", start, end)]

    async def ledger_rows(self) -> list[Row]:
        async with self.rw.acquire() as c:
            return [_js(dict(r), "content") for r in await c.fetch(
                "SELECT seq, kind, ref, content, prev_hash, hash FROM pattern_paper_ledger ORDER BY seq ASC")]


def _iso(v) -> str:
    return _dt(v).isoformat()


def _open_content(tid: int, t: dict) -> dict:
    c = _open_core(tid, t)
    if t.get("guard"):
        c["guard"] = t["guard"]      # quyết định guardrail (cỡ vị thế danh nghĩa) nằm trong bản ghi bất biến
    return c


def _open_core(tid: int, t: dict) -> dict:
    return {"id": tid, "setup_id": t["setup_id"], "symbol": t["symbol"], "tf": t["tf"], "side": t["side"], "opened_at": _iso(t["opened_at"]),
            "entry": t["entry"], "sl": t["sl"], "tp": t["tp"], "cost_r": t["cost_r"], "replay": t["replay"]}


def _close_content(t: dict) -> dict:
    return {"id": t["id"], "closed_at": _iso(t["closed_at"]), "result_r": t["result_r"],
            "legs": [{"status": lg["status"], "exit": lg["exit"], "r": lg["r"]} for lg in t["legs"]]}


class MemoryStore:
    """Cho test/dev: cùng giao diện với PgStore."""

    def __init__(self, bars: dict[tuple[str, str], list[Row]] | None = None, signals: list[Row] | None = None):
        self.bars = bars or {}
        self.sigs = signals or []
        self.ev: list[Row] = []
        self.img: dict[int, bytes] = {}
        self.tr: list[Row] = []
        self.led: list[Row] = []

    async def close(self) -> None:
        return None

    async def bars_until(self, symbol, tf, until_open, limit):
        rows = [r for r in self.bars.get((symbol, tf), []) if r["ts_open"] <= until_open]
        return sorted(rows, key=lambda r: r["ts_open"])[-limit:]

    async def bars_after(self, symbol, tf, after_open, limit=500):
        rows = [r for r in self.bars.get((symbol, tf), []) if r["ts_open"] > after_open]
        return sorted(rows, key=lambda r: r["ts_open"])[:limit]

    async def signals_since(self, since):
        return [dict(s) for s in self.sigs]

    async def insert_event(self, p, live):
        if any((e["setup_id"], e["symbol"], e["tf"], e["state"]) == (p["setup_id"], p["symbol"], p["tf"], p["state"]) for e in self.ev):
            return None
        eid = len(self.ev) + 1
        self.ev.append({"id": eid, "setup_id": p["setup_id"], "pattern": p["pattern"], "symbol": p["symbol"], "tf": p["tf"],
                        "state": p["state"], "score": float(p.get("score") or 0), "bar_ts": _dt(p["bar_ts"]), "ts": _dt(p["ts"]),
                        "levels": p.get("levels") or {}, "steps": p.get("steps") or [], "reason": p.get("reason"),
                        "points": p.get("points") or [], "live": live, "received_at": datetime.now(timezone.utc)})
        return eid

    async def events(self, since, limit=5000):
        rows = [dict(e, has_image=e["id"] in self.img) for e in self.ev if e["bar_ts"] >= since]
        return sorted(rows, key=lambda e: (e["bar_ts"], e["id"]), reverse=True)[:limit]

    async def event(self, eid):
        return next((dict(e) for e in self.ev if e["id"] == eid), None)

    async def put_media(self, eid, png):
        self.img.setdefault(eid, png)

    async def media(self, eid):
        e = await self.event(eid)
        return (self.img[eid], e["state"]) if e and eid in self.img else None

    async def insert_trade(self, t):
        if any((x["setup_id"], x["symbol"], x["tf"]) == (t["setup_id"], t["symbol"], t["tf"]) for x in self.tr):
            return None
        tid = len(self.tr) + 1
        row = dict(t, id=tid)
        row["open_hash"] = self._ledger("open", str(tid), _open_content(tid, t))
        self.tr.append(row)
        return tid

    async def update_trade(self, t, closed):
        for k, x in enumerate(self.tr):
            if x["id"] == t["id"] and x["status"] == "open":
                self.tr[k] = dict(x, **{a: t[a] for a in ("status", "closed_at", "legs", "result_r", "mfe_r", "mae_r", "bars_held", "last_bar_ts")})
        if closed:
            self._ledger("close", str(t["id"]), _close_content(t))

    def _ledger(self, kind, ref, content):
        prev = self.led[-1]["hash"] if self.led else GENESIS
        content = json.loads(json.dumps(content, ensure_ascii=False))
        h = chain_hash(prev, kind, ref, content)
        self.led.append({"seq": len(self.led) + 1, "kind": kind, "ref": ref, "content": content, "prev_hash": prev, "hash": h})
        return h

    async def trades(self, status=None, limit=1000):
        rows = [dict(x) for x in self.tr if not status or x["status"] == status]
        return sorted(rows, key=lambda x: str(x["opened_at"]), reverse=True)[:limit]

    async def calendar_events(self, start, end):
        return list(getattr(self, "cal", []))

    async def ledger_rows(self):
        return [dict(r) for r in self.led]


def since_days(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
