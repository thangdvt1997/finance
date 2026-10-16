"""Dieu phoi 1 vong cham: trich quan diem -> ghi so cai -> lay gia -> ket qua -> the diem -> trong so (Redis) -> snapshot trong bo nho."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from . import config as C
from . import extract, scoring
from .data import Data
from .pricing import PROXY, PriceBook
from .store import MemStore, PgStore

log = logging.getLogger("track-record")


@dataclass
class Snapshot:
    as_of: datetime
    entities: dict[str, dict] = field(default_factory=dict)
    views: list[dict] = field(default_factory=list)                    # moi -> cu theo published_at
    items: dict[tuple, list[dict]] = field(default_factory=dict)       # (entity_id, horizon) -> item da cham
    outcome_idx: dict[tuple, dict] = field(default_factory=dict)       # (view_id, horizon) -> item
    cards: dict[tuple, dict] = field(default_factory=dict)             # (entity_id, scope, horizon) -> thong ke
    summary: dict = field(default_factory=dict)
    weights: dict[str, dict] = field(default_factory=dict)
    chain: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)
    emap: dict = field(default_factory=dict)


def outcome_rows(views: list[dict], pb: PriceBook) -> tuple[list[dict], dict]:
    """Moi (view, horizon) -> hang ket qua da chot. Thieu gia/chua du nen => khong co hang (pending/unpriced)."""
    out, stats = [], {"pending": 0, "unpriced": 0}
    for v in views:
        regime = None
        got_regime = False
        for hz in C.HORIZONS:
            f = pb.fill(v["symbol"], v["observed_at"], hz)
            if f is None:
                stats["unpriced"] += 1
                continue
            if f == "pending":
                stats["pending"] += 1
                continue
            if not got_regime:
                regime, got_regime = pb.regime(v["symbol"], v["observed_at"]), True
            d = 1.0 if v["direction"] == "bullish" else -1.0
            out.append({"view_id": v["view_id"], "horizon": hz, "entry_ts": f.entry_ts, "entry_px": f.entry_px, "exit_ts": f.exit_ts, "exit_px": f.exit_px,
                        "ret_log": f.ret_log, "hit": d * f.ret_log > 0, "regime": regime})
    return out, stats


def build_snapshot(now: datetime, views: list[dict], entities: dict[str, dict], outcomes: list[dict], chain: dict) -> Snapshot:
    vmap = {v["view_id"]: v for v in views}
    items: dict[tuple, list[dict]] = {}
    idx: dict[tuple, dict] = {}
    for o in outcomes:
        v = vmap.get(o["view_id"])
        if v is None:
            continue
        it = {"view_id": v["view_id"], "entity_id": v["entity_id"], "symbol": v["symbol"], "asset_class": C.asset_class(v["symbol"]), "direction": v["direction"],
              "observed_at": v["observed_at"], "entry_ts": o["entry_ts"], "exit_ts": o["exit_ts"], "raw": o["ret_log"], "hit": o["hit"], "regime": o.get("regime")}
        items.setdefault((v["entity_id"], o["horizon"]), []).append(it)
        idx[(v["view_id"], o["horizon"])] = it
    by_ent: dict[str, dict[str, list[dict]]] = {}
    for (eid, hz), lst in items.items():
        by_ent.setdefault(eid, {})[hz] = lst
    counts: dict[tuple, int] = {}
    last: dict[str, str] = {}
    syms: dict[str, set] = {}
    for v in views:
        e = v["entity_id"]
        for sc in ("all", C.asset_class(v["symbol"]), "sym:" + v["symbol"]):
            counts[(e, sc)] = counts.get((e, sc), 0) + 1
        last[e] = max(last.get(e, ""), v["published_at"].isoformat())
        syms.setdefault(e, set()).add(v["symbol"])
    cards, summary = scoring.compute_cards(by_ent, entities, counts, last, {e: len(s) for e, s in syms.items()})
    weights = {}
    for eid in entities:
        c = cards.get((eid, "all", "1W"))
        if c:
            weights[eid] = {"w": c["weight"], "score": c["score"], "n": c["n"], "status": c["status"], "hit": c["hit_rate"], "beats": c["beats_baseline"]}
    snap = Snapshot(as_of=now, entities=entities, views=sorted(views, key=lambda v: (v["published_at"], v["seq"]), reverse=True), items=items, outcome_idx=idx,
                    cards=cards, summary=summary, weights=weights, chain=chain)
    return snap


class Engine:
    def __init__(self, data: Data, store, redis=None, now_fn: Callable[[], datetime] = C.utcnow):
        self.data, self.store, self.redis, self.now_fn = data, store, redis, now_fn
        self.snap: Optional[Snapshot] = None
        self.last_run: dict = {}
        self._lock = asyncio.Lock()

    async def run_once(self) -> dict:
        async with self._lock:
            t0 = time.monotonic()
            started = self.now_fn()
            avail = await self.data.price_symbols()

            def has_price(s: str) -> bool:
                return s in avail or PROXY.get(s) in avail

            news, sigs, pos, meta = await asyncio.gather(self.data.news_rows(), self.data.signal_rows(), self.data.position_rows(), self.data.expert_meta())
            names = {k: v["name"] for k, v in meta.items() if v.get("name")}
            now = started
            cands = extract.news_views(news, has_price, now, meta) + extract.signal_views(sigs, names, now) + extract.cot_views(pos, now)
            merged = extract.merge_daily(cands, closed_before=now.date())
            n_new = await self.store.append_views(merged)
            await self.store.sync_entities(cands)
            views = await self.store.views()
            entities = await self.store.entities_all()
            keys = set()
            for v in views:
                s = v["symbol"]
                if s in avail:
                    keys.add(s)
                elif PROXY.get(s) in avail:
                    keys.add(PROXY[s])
            since = (min((v["observed_at"] for v in views), default=now) - timedelta(days=420))
            pb = PriceBook.build(await self.data.prices(sorted(keys), since)) if keys else PriceBook()
            outcomes, ostats = await asyncio.to_thread(outcome_rows, views, pb)
            old = await self.store.load_outcomes()
            new_keys = {(o["view_id"], o["horizon"]) for o in outcomes}
            changed = [o for o in outcomes if (o["view_id"], o["horizon"]) not in old or abs(old[(o["view_id"], o["horizon"])]["ret_log"] - o["ret_log"]) > 1e-12
                       or old[(o["view_id"], o["horizon"])]["entry_ts"] != o["entry_ts"] or old[(o["view_id"], o["horizon"])].get("regime") != o.get("regime")]
            gone = [k for k in old if k not in new_keys]
            if changed or gone:
                await self.store.save_outcomes(changed, gone)
            chain = await self.store.verify()
            snap = await asyncio.to_thread(build_snapshot, now, views, entities, outcomes, chain)
            snap.counts = {"views": len(views), "new_views": n_new, "outcomes": len(outcomes), **ostats}
            await self.store.save_scorecards([{"entity_id": k[0], "scope": k[1], "horizon": k[2], "n": c["n"], "n_total": c["n_total"], "status": c["status"],
                                               "stats": {x: y for x, y in c.items() if x not in ("entity_id", "scope", "horizon")}} for k, c in snap.cards.items()])
            rated = sum(1 for c in snap.cards.values() if c["status"] == "rated")
            secs = time.monotonic() - t0
            run = {"started_at": started, "finished_at": self.now_fn(), "n_views": len(views), "n_new_views": n_new, "n_outcomes": len(outcomes), "n_tests": snap.summary["tests"],
                   "n_rated": rated, "n_beating": snap.summary["beating_baseline"], "seconds": secs, "note": {"chain_ok": chain["ok"], **ostats}}
            await self.store.log_run(run)
            snap.emap = extract.expert_keys(sigs, pos, news, meta)
            await self._push_weights(snap)
            self.snap, self.last_run = snap, run
            log.info("track-record run: %s", {k: v for k, v in run.items() if k not in ("started_at", "finished_at")})
            return run

    @staticmethod
    def _mapping(snap: Snapshot) -> dict[str, str]:
        entries = [(k, rec) for eid, rec in snap.weights.items() for k in extract.weight_keys(eid, snap.emap)]
        return {k: json.dumps(v, separators=(",", ":")) for k, v in extract.merge_weight_records(entries).items()}

    async def _push_weights(self, snap: Snapshot) -> None:
        if self.redis is None:
            return
        try:
            mapping = self._mapping(snap)
            old = set(await self.redis.hkeys("tr:weights")) if hasattr(self.redis, "hkeys") else set()
        except Exception:  # noqa: BLE001
            old, mapping = set(), self._mapping(snap)
        try:
            if mapping:
                await self.redis.hset("tr:weights", mapping=mapping)
            stale = [k.decode() if isinstance(k, bytes) else k for k in old]
            stale = [k for k in stale if k not in mapping]
            if stale:
                await self.redis.hdel("tr:weights", *stale)
            await self.redis.set("tr:weights:ts", snap.as_of.isoformat())
        except Exception as e:  # noqa: BLE001
            log.warning("khong ghi duoc tr:weights: %s", e)
