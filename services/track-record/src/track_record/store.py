"""Luu tru: PgStore (role ts_trackrec) + MemStore (test). Ghi tuan tu bang advisory lock; idempotent theo ref."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from . import ledger
from .config import utcnow

LOCK_KEY = 74700016
Row = dict[str, Any]


def next_label(group: str, existing_labels: list[str]) -> str:
    n = sum(1 for lb in existing_labels if lb.startswith(group + " #")) + 1
    return f"{group} #{n}"


class MemStore:
    def __init__(self):
        self.rows: list[Row] = []
        self.entities: dict[str, Row] = {}
        self.outcomes: dict[tuple, Row] = {}
        self.scorecards: dict[tuple, Row] = {}
        self.runs: list[Row] = []

    async def ensure_entities(self, views: list[Row]) -> None:
        for v in views:
            if v["entity_id"] in self.entities:
                continue
            label = v.get("label") or next_label(v.get("group") or "Chuyên gia", [e["label"] for e in self.entities.values()])
            self.entities[v["entity_id"]] = {"entity_id": v["entity_id"], "label": label, "kind": v["kind"], "lang": v["lang"]}

    async def sync_entities(self, cands: list[Row]) -> int:
        n = 0
        for v in cands:
            e = self.entities.get(v["entity_id"])
            if e and v.get("label") and (e["label"], e["kind"]) != (v["label"], v["kind"]):
                e["label"], e["kind"] = v["label"], v["kind"]
                n += 1
        return n

    async def append_views(self, views: list[Row], recorded_at: Optional[datetime] = None) -> int:
        have = {r["ref"] for r in self.rows}
        new = [v for v in views if v["ref"] not in have]
        await self.ensure_entities(new)
        ts = recorded_at or utcnow()
        prev = self.rows[-1]["hash"] if self.rows else ledger.GENESIS
        seq = self.rows[-1]["seq"] if self.rows else 0
        for v in sorted(new, key=lambda x: (x["observed_at"], x["ref"])):
            seq += 1
            r = ledger.build_row(prev, seq, v, ts)
            self.rows.append(r)
            prev = r["hash"]
        return len(new)

    async def views(self) -> list[Row]:
        return list(self.rows)

    async def entities_all(self) -> dict[str, Row]:
        return dict(self.entities)

    async def verify(self) -> dict:
        return ledger.verify_rows(self.rows)

    async def load_outcomes(self) -> dict[tuple, Row]:
        return dict(self.outcomes)

    async def save_outcomes(self, rows: list[Row], delete_keys: list[tuple]) -> None:
        for r in rows:
            self.outcomes[(r["view_id"], r["horizon"])] = r
        for k in delete_keys:
            self.outcomes.pop(k, None)

    async def save_scorecards(self, rows: list[Row]) -> None:
        self.scorecards = {(r["entity_id"], r["scope"], r["horizon"]): r for r in rows}

    async def log_run(self, row: Row) -> None:
        self.runs.append(row)

    async def close(self) -> None:
        return None


class PgStore:
    def __init__(self, pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "PgStore":
        import asyncpg

        async def init(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=120, init=init))

    async def close(self) -> None:
        await self.pool.close()

    async def _ensure(self, c, views: list[Row]) -> None:
        have = {r["entity_id"] for r in await c.fetch("SELECT entity_id FROM tr_entities")}
        labels = [r["label"] for r in await c.fetch("SELECT label FROM tr_entities")]
        for v in views:
            if v["entity_id"] in have:
                continue
            label = v.get("label") or next_label(v.get("group") or "Chuyên gia", labels)
            await c.execute("INSERT INTO tr_entities(entity_id,label,kind,lang) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING", v["entity_id"], label, v["kind"], v["lang"])
            have.add(v["entity_id"])
            labels.append(label)

    async def sync_entities(self, cands: list[Row]) -> int:
        """Dong bo nhan/loai THAT (ten chuyen gia) cho entity da ton tai (nhan chung 'Luong tin #n' tao truoc do). tr_entities cho phep UPDATE."""
        want = {v["entity_id"]: (v["label"], v["kind"], v["lang"]) for v in cands if v.get("label")}
        if not want:
            return 0
        async with self.pool.acquire() as c:
            have = {r["entity_id"]: (r["label"], r["kind"]) for r in await c.fetch("SELECT entity_id,label,kind FROM tr_entities")}
            todo = [(e, *w) for e, w in want.items() if e in have and have[e] != (w[0], w[1])]
            if todo:
                await c.executemany("UPDATE tr_entities SET label=$2, kind=$3, lang=$4 WHERE entity_id=$1", todo)
        return len(todo)

    async def append_views(self, views: list[Row], recorded_at: Optional[datetime] = None) -> int:
        if not views:
            return 0
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEY)
            refs = [v["ref"] for v in views]
            have = {r["ref"] for r in await c.fetch("SELECT ref FROM tr_views WHERE ref = ANY($1::text[])", refs)}
            new = sorted((v for v in views if v["ref"] not in have), key=lambda x: (x["observed_at"], x["ref"]))
            if not new:
                return 0
            await self._ensure(c, new)
            head = await c.fetchrow("SELECT seq, hash FROM tr_views ORDER BY seq DESC LIMIT 1")
            prev, seq = (head["hash"], head["seq"]) if head else (ledger.GENESIS, 0)
            ts = recorded_at or utcnow()
            out = []
            for v in new:
                seq += 1
                r = ledger.build_row(prev, seq, v, ts)
                prev = r["hash"]
                out.append((r["seq"], r["view_id"], r["ref"], r["entity_id"], r["symbol"], r["direction"], r["published_at"], r["observed_at"], r["invalidation"],
                            r["horizon_hint"], r["basis"], r["recorded_at"], r["prev_hash"], r["hash"]))
            await c.executemany("INSERT INTO tr_views(seq,view_id,ref,entity_id,symbol,direction,published_at,observed_at,invalidation,horizon_hint,basis,recorded_at,prev_hash,hash) "
                                "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)", out)
            return len(out)

    async def views(self) -> list[Row]:
        async with self.pool.acquire() as c:
            return [dict(r) for r in await c.fetch("SELECT * FROM tr_views ORDER BY seq")]

    async def entities_all(self) -> dict[str, Row]:
        async with self.pool.acquire() as c:
            return {r["entity_id"]: dict(r) for r in await c.fetch("SELECT entity_id,label,kind,lang FROM tr_entities")}

    async def verify(self) -> dict:
        # cache theo (so dong, seq cuoi, hash cuoi) + TTL 60 s: tranh tinh lai ca chuoi moi lan goi (p95 1,3 s)
        import time
        async with self.pool.acquire() as c:
            head = await c.fetchrow("SELECT count(*) n, max(seq) s FROM tr_views")
            hh = await c.fetchval("SELECT hash FROM tr_views WHERE seq=$1", head["s"]) if head["s"] is not None else None
            key = (head["n"], head["s"], hh)
            ck = getattr(self, "_vcache", None)
            now = time.monotonic()
            if ck and ck[0] == key and now - ck[1] < 60:
                return dict(ck[2])
            res = ledger.verify_rows(dict(r) for r in await c.fetch("SELECT * FROM tr_views ORDER BY seq"))
        self._vcache = (key, now, res)
        return dict(res)

    async def load_outcomes(self) -> dict[tuple, Row]:
        async with self.pool.acquire() as c:
            return {(r["view_id"], r["horizon"]): dict(r) for r in await c.fetch("SELECT * FROM tr_outcomes")}

    async def save_outcomes(self, rows: list[Row], delete_keys: list[tuple]) -> None:
        async with self.pool.acquire() as c, c.transaction():
            if delete_keys:
                await c.executemany("DELETE FROM tr_outcomes WHERE view_id=$1 AND horizon=$2", delete_keys)
            if rows:
                await c.executemany(
                    "INSERT INTO tr_outcomes(view_id,horizon,entry_ts,entry_px,exit_ts,exit_px,ret_log,hit,regime,computed_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,now()) "
                    "ON CONFLICT (view_id,horizon) DO UPDATE SET entry_ts=$3,entry_px=$4,exit_ts=$5,exit_px=$6,ret_log=$7,hit=$8,regime=$9,computed_at=now()",
                    [(r["view_id"], r["horizon"], r["entry_ts"], r["entry_px"], r["exit_ts"], r["exit_px"], r["ret_log"], r["hit"], r.get("regime")) for r in rows])

    async def save_scorecards(self, rows: list[Row]) -> None:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("DELETE FROM tr_scorecards")
            if rows:
                await c.executemany("INSERT INTO tr_scorecards(entity_id,scope,horizon,n,n_total,status,stats) VALUES($1,$2,$3,$4,$5,$6,$7)",
                                    [(r["entity_id"], r["scope"], r["horizon"], r["n"], r["n_total"], r["status"], r["stats"]) for r in rows])

    async def log_run(self, row: Row) -> None:
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO tr_runs(started_at,finished_at,n_views,n_new_views,n_outcomes,n_tests,n_rated,n_beating,seconds,note) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                            row["started_at"], row["finished_at"], row["n_views"], row["n_new_views"], row["n_outcomes"], row["n_tests"], row["n_rated"], row["n_beating"], row["seconds"], row.get("note"))
