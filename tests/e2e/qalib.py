"""Thu vien dung chung cho bo e2e/QA (chay trong container python:3.12-slim tren networks tradingsys_backend/ops/frontend/internal).

Quy uoc: du lieu test luon co source='qa' (hoac symbol QA*, account_id qa-*, tag 'qa').
Moi message da publish duoc ghi vao OUT/published_ids.jsonl de cleanup.py XDEL.
KHONG co ham nao dat lenh; KHONG in token ra log.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone

import asyncpg
import httpx
import redis.asyncio as aioredis

OUT = os.getenv("QA_OUT", "/qa/out")
os.makedirs(OUT, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


_RAP = _env("REDIS_ADMIN_PASSWORD")   # Redis ACL: e2e dùng user ts_admin (lấy từ infra/.env qua --env-file)
REDIS_URL = _env("QA_REDIS_URL", f"redis://ts_admin:{_RAP}@redis:6379/0" if _RAP else "redis://redis:6379/0")
GATEWAY = _env("QA_GATEWAY", "http://api-gateway:8000")
BRIDGE = _env("QA_BRIDGE", "http://mt-bridge:8000")
API_KEY = _env("API_TOKEN")
DSN = f"postgresql://{_env('POSTGRES_USER','ts')}:{_env('POSTGRES_PASSWORD')}@timescaledb:5432/{_env('POSTGRES_DB','ts')}"
SERVICES = ["storage-writer", "market-collector", "news-collector", "expert-collector", "mt-bridge", "alert-service", "api-gateway"]

SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def now() -> datetime:
    return datetime.now(timezone.utc)


class Results:
    def __init__(self, name: str):
        self.name = name
        self.rows: list[dict] = []
        self.metrics: dict = {}
        self.t0 = time.time()

    def check(self, cid: str, ok: bool, detail: str = "", severity: str = "medium") -> bool:
        self.rows.append({"id": cid, "ok": bool(ok), "detail": detail, "severity": severity})
        print(f"{'PASS' if ok else 'FAIL'} [{severity if not ok else '-'}] {cid} :: {detail}", flush=True)
        return bool(ok)

    def info(self, cid: str, detail: str) -> None:
        self.rows.append({"id": cid, "ok": None, "detail": detail, "severity": "info"})
        print(f"INFO {cid} :: {detail}", flush=True)

    def metric(self, k: str, v) -> None:
        self.metrics[k] = v
        print(f"METRIC {k} = {v}", flush=True)

    def finish(self) -> int:
        p = sum(1 for r in self.rows if r["ok"] is True)
        f = sum(1 for r in self.rows if r["ok"] is False)
        print(f"== {self.name}: PASS={p} FAIL={f} ({time.time()-self.t0:.1f}s)", flush=True)
        with open(os.path.join(OUT, f"{self.name}.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": self.name, "pass": p, "fail": f, "rows": self.rows, "metrics": self.metrics,
                       "ts": now().isoformat()}, fh, ensure_ascii=False, indent=1, default=str)
        return 1 if f else 0


def mk_event(type_: str, payload: dict, *, source: str = "qa", eid: str | None = None, ts: datetime | None = None) -> dict:
    return {"id": eid or str(uuid.uuid4()), "type": type_, "source": source,
            "ts": (ts or now()).isoformat(), "schema_version": 1, "trace_id": "qa", "payload": payload}


_ids_fh = None


def _track(stream: str, mid: str) -> None:
    global _ids_fh
    if _ids_fh is None:
        _ids_fh = open(os.path.join(OUT, "published_ids.jsonl"), "a", encoding="utf-8")
    _ids_fh.write(json.dumps([stream, mid]) + "\n")
    _ids_fh.flush()


async def publish(r, stream: str, ev: dict | str) -> str:
    raw = ev if isinstance(ev, str) else json.dumps(ev)
    mid = await r.xadd(stream, {"e": raw})
    _track(stream, mid)
    return mid


async def publish_many(r, stream: str, evs: list[dict], *, pipe: int = 500) -> list[tuple[str, float]]:
    """Publish theo pipeline; tra ve [(msg_id, t_publish)]"""
    out = []
    for i in range(0, len(evs), pipe):
        chunk = evs[i:i + pipe]
        p = r.pipeline(transaction=False)
        for e in chunk:
            p.xadd(stream, {"e": json.dumps(e)})
        t = time.time()
        ids = await p.execute()
        for mid in ids:
            _track(stream, mid)
            out.append((mid, t))
    return out


async def wait_for(fn, timeout: float = 20.0, interval: float = 0.25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = await fn()
        if v:
            return v
        await asyncio.sleep(interval)
    return None


class Ctx:
    def __init__(self):
        self.r = None
        self.db = None
        self.http = None

    async def __aenter__(self):
        self.r = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.db = await asyncpg.connect(DSN)
        self.http = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, *a):
        await self.http.aclose()
        await self.db.close()
        await self.r.aclose()

    async def api(self, path: str, key: str | None = API_KEY, **params):
        h = {"X-API-Key": key} if key is not None else {}
        return await self.http.get(GATEWAY + path, headers=h, params=params)


def pct(vals: list[float], q: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def lat_summary(vals: list[float]) -> dict:
    if not vals:
        return {}
    return {"n": len(vals), "p50": round(pct(vals, .5), 3), "p95": round(pct(vals, .95), 3),
            "p99": round(pct(vals, .99), 3), "max": round(max(vals), 3), "mean": round(statistics.mean(vals), 3)}
