from __future__ import annotations

from datetime import timedelta

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tscommon import STREAMS, Bus

from pattern_engine.app import create_app
from pattern_engine.config import DEFAULTS, Settings
from pattern_engine.repo import MemoryBarSource, MemoryStore
from pattern_engine.runner import STREAM, Runner, to_bars
from pattern_engine.series import TF_SECONDS


def rows_of(bars):
    return [{"ts_open": b.ts, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v} for b in bars]


def make_runner(bars, upto, bus=None, store=None):
    cfg = {**DEFAULTS, "max_age_bars": 3, "symbols": {"include": [], "exclude": [], "max": 10}}
    src = MemoryBarSource({("XAUUSD", "M15"): rows_of(bars[:upto])})
    return Runner(cfg, src, store or MemoryStore(), bus), src


def test_stream_registered_in_tscommon():
    assert STREAMS["patterns"] == STREAM == "pattern.signals"


def test_to_bars_drops_unclosed_candle(xau_bars):
    last = xau_bars[500]
    now = last.ts + timedelta(seconds=TF_SECONDS["M15"] - 1)        # nến cuối CHƯA đóng
    bars = to_bars(rows_of(xau_bars[:501]), "M15", now)
    assert bars[-1].ts == xau_bars[499].ts
    assert to_bars(rows_of(xau_bars[:501]), "M15", last.ts + timedelta(seconds=TF_SECONDS["M15"]))[-1].ts == last.ts


@pytest.mark.asyncio
async def test_cycle_publishes_and_dedupes(xau_bars):
    bus = Bus(fakeredis.aioredis.FakeRedis(decode_responses=True))
    store = MemoryStore()
    # cắt ngay sau nến kích hoạt KB-1 (2026-10-05 11:30) để có sự kiện trong 3 nến cuối
    n = next(i for i, b in enumerate(xau_bars) if b.ts.isoformat().startswith("2026-10-05T11:30")) + 1
    runner, src = make_runner(xau_bars, n, bus, store)
    now = xau_bars[n - 1].ts + timedelta(minutes=15)
    out = await runner.run_cycle(now)
    assert out["status"] == "ok" and out["series_scanned"] == 1
    entries = await bus.r.xrange(STREAM)
    assert entries, "phải phát pattern.signal lên bus"
    import json
    ev = [json.loads(e[1]["e"]) for e in entries]
    assert all(x["type"] == "pattern.signal" and x["source"] == "pattern-engine" for x in ev)
    trig = [x["payload"] for x in ev if x["payload"]["state"] == "triggered"]
    assert trig and trig[0]["pattern"] == "KB-1" and trig[0]["symbol"] == "XAUUSD" and trig[0]["tf"] == "M15"
    assert {"levels", "steps", "score", "ts", "setup_id"} <= set(trig[0])
    # chạy lại cùng dữ liệu: không phát trùng (nến cuối không đổi)
    n_before = len(entries)
    await runner.run_cycle(now)
    assert len(await bus.r.xrange(STREAM)) == n_before
    # xoá bộ nhớ nến-cuối (mô phỏng restart) -> DB/store chặn trùng
    runner._last.clear()
    out2 = await runner.run_cycle(now)
    assert out2["signals_new"] == 0 and len(await bus.r.xrange(STREAM)) == n_before


def test_api_patterns_and_spec(xau_bars):
    import asyncio
    store = MemoryStore()
    runner, _ = make_runner(xau_bars, len(xau_bars), None, store)
    asyncio.run(runner.run_cycle(xau_bars[-1].ts + timedelta(minutes=15)))
    app = create_app(Settings(enabled=False), runner=runner, store=store)
    with TestClient(app) as c:
        assert c.get("/healthz").json()["status"] == "ok"
        r = c.get("/patterns", params={"symbol": "XAUUSD", "tf": "M15", "state": "armed,triggered", "limit": 50})
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["state"] in ("armed", "triggered") for i in items)
        assert c.get("/patterns", params={"symbol": "bad symbol!"}).status_code == 422
        assert c.get("/patterns", params={"limit": 9999}).status_code == 422
        sp = c.get("/patterns/spec").json()["items"]
        assert {s["id"] for s in sp} == {"KB-1", "KB-2", "KB-3", "KB-4"}
        assert "/metrics" and c.get("/metrics").status_code == 200
