"""Trong so thanh tich chuyen gia tu service `track-record` (Redis hash `tr:weights`, hop dong: services/track-record/CONTRACT.md).

`tr:weights` = hash entity_id -> json {"w","score","n","status","hit","beats"}; `tr:weights:ts` = thoi diem cap nhat (epoch giay hoac ISO).
FAIL-OPEN: Redis loi / khong co key / du lieu hong / qua cu -> trong so 1.0 (hanh vi nhu truoc khi co track-record), ghi metric. Chi DOC, khong bao gio ghi.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Callable

from prometheus_client import Counter, Gauge

log = logging.getLogger(__name__)

W_MIN, W_MAX = 0.0, 3.0
KEY, KEY_TS = "tr:weights", "tr:weights:ts"

TW_ERRORS = Counter("ec_trackweights_errors_total", "loi doc tr:weights (fail-open -> trong so 1.0)", ["reason"])
TW_ENTITIES = Gauge("ec_trackweights_entities", "so entity doc duoc tu tr:weights")
TW_AVAILABLE = Gauge("ec_trackweights_available", "1 neu dang dung trong so tu track-record, 0 neu fail-open")


def _s(v) -> str:
    return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)


def _clean(d: dict) -> dict | None:
    """Chuan hoa 1 ban ghi; None neu hong."""
    try:
        w = float(d["w"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(w):
        return None
    out = {"weight": min(max(w, W_MIN), W_MAX)}
    for k_in, k_out in (("score", "score"), ("n", "n"), ("hit", "hit")):
        v = d.get(k_in)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out[k_out] = v
    st = d.get("status")
    if st in ("rated", "insufficient"):
        out["status"] = st
    if isinstance(d.get("beats"), bool):
        out["beats"] = d["beats"]
    return out


def _parse_ts(raw) -> float | None:
    s = _s(raw).strip()
    try:
        return float(s)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        return None


class TrackWeights:
    def __init__(self, redis, cache_seconds: float = 30.0, max_age_hours: float = 72.0, enabled: bool = True,
                 clock: Callable[[], float] = time.time):
        self.r, self.cache_seconds, self.max_age, self.enabled, self.clock = redis, cache_seconds, max_age_hours * 3600, enabled, clock
        self._snap: dict[str, dict] = {}
        self._at: float | None = None

    async def snapshot(self, force: bool = False) -> dict[str, dict]:
        """entity_id -> {weight, score?, n?, status?, hit?, beats?}. Khong bao gio nem loi; thieu/hong -> {}."""
        if not self.enabled:
            return {}
        now = self.clock()
        if not force and self._at is not None and now - self._at < self.cache_seconds:
            return self._snap
        snap: dict[str, dict] = {}
        try:
            raw = await self.r.hgetall(KEY)
            if raw:
                ts = None
                try:
                    ts_raw = await self.r.get(KEY_TS)
                    ts = _parse_ts(ts_raw) if ts_raw is not None else None
                except Exception:  # noqa: BLE001
                    ts = None
                if ts is not None and now - ts > self.max_age:
                    TW_ERRORS.labels("stale").inc()
                else:
                    bad = 0
                    for k, v in raw.items():
                        try:
                            rec = _clean(json.loads(_s(v)))
                        except ValueError:
                            rec = None
                        if rec is None:
                            bad += 1
                        else:
                            snap[_s(k)] = rec
                    if bad:
                        TW_ERRORS.labels("bad_record").inc(bad)
        except Exception as e:  # noqa: BLE001 - Redis loi -> fail-open
            TW_ERRORS.labels("redis").inc()
            log.warning("tr:weights khong doc duoc (%s) -> fail-open, trong so 1.0", type(e).__name__)
            snap = {}
        self._snap, self._at = snap, now
        TW_ENTITIES.set(len(snap))
        TW_AVAILABLE.set(1 if snap else 0)
        return snap


def lookup(snap: dict[str, dict], expert_id: str, source: str | None = None) -> dict | None:
    """Tim ban ghi theo expert_id, roi `source:expert_id`."""
    rec = snap.get(expert_id)
    if rec is None and source:
        rec = snap.get(f"{source}:{expert_id}")
    return rec


def weight_of(snap: dict[str, dict], expert_id: str, source: str | None = None) -> float:
    rec = lookup(snap, expert_id, source)
    return rec["weight"] if rec else 1.0
