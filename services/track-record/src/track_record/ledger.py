"""So cai BAT BIEN dang hash-chain: hash_i = sha256(prev_hash_i || '|' || canonical_json(row_i)). Ham thuan; luu tru o store.py."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Optional

from .config import UTC

GENESIS = "0" * 64
FIELDS = ("seq", "view_id", "ref", "entity_id", "symbol", "direction", "published_at", "observed_at", "invalidation", "horizon_hint", "basis", "recorded_at")
TS_FIELDS = ("published_at", "observed_at", "recorded_at")


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical(row: dict[str, Any]) -> str:
    d = {}
    for f in FIELDS:
        v = row.get(f)
        d[f] = iso(v) if f in TS_FIELDS else v
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(prev_hash: str, row: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + "|" + canonical(row)).encode()).hexdigest()


def build_row(prev_hash: str, seq: int, view: dict[str, Any], recorded_at: datetime) -> dict[str, Any]:
    r = {f: view.get(f) for f in FIELDS}
    r.update(seq=seq, recorded_at=recorded_at, prev_hash=prev_hash)
    r["hash"] = compute_hash(prev_hash, r)
    return r


def verify_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Duyet toan chuoi theo seq; tra {ok, n, head_hash, first_bad_seq, reason}."""
    prev, n, last = GENESIS, 0, None
    exp_seq: Optional[int] = None
    for r in rows:
        n += 1
        if exp_seq is not None and r["seq"] != exp_seq:
            return {"ok": False, "n": n, "head_hash": last, "first_bad_seq": r["seq"], "reason": "seq_gap"}
        if r["prev_hash"] != prev:
            return {"ok": False, "n": n, "head_hash": last, "first_bad_seq": r["seq"], "reason": "prev_hash"}
        if compute_hash(prev, r) != r["hash"]:
            return {"ok": False, "n": n, "head_hash": last, "first_bad_seq": r["seq"], "reason": "hash"}
        prev, last, exp_seq = r["hash"], r["hash"], r["seq"] + 1
    return {"ok": True, "n": n, "head_hash": last or GENESIS, "first_bad_seq": None, "reason": None}
