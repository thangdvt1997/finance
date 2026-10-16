import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from data_keeper import backfill as bf

UTC = timezone.utc
SRC = "canon:mt5:1-feed"


class FakeDB:
    def __init__(self):
        self.bars = {}
        self.queue = {}
        self.log = []
        self._id = 0

    async def execute(self, sql, *a):
        if sql.startswith(("CREATE", "DO")):
            return "OK"
        if "INSERT INTO dk.backfill_queue" in sql:
            key = (a[0], a[1], a[2], a[3], a[4])
            if key in self.queue:
                return "INSERT 0 0"
            self._id += 1
            self.queue[key] = {"id": self._id, "symbol": a[0], "tf": a[1], "t0": a[2], "t1": a[3], "source": a[4], "priority": a[5], "status": "pending"}
            return "INSERT 0 1"
        if "UPDATE dk.backfill_queue SET status=$2" in sql:
            for q in self.queue.values():
                if q["id"] == a[0]:
                    q["status"] = a[1]
        elif "SET status='failed'" in sql:
            for q in self.queue.values():
                if q["id"] == a[0]:
                    q["status"] = "failed"
        elif "INSERT INTO dk.backfill_log" in sql:
            self.log.append(a)
        return "OK"

    async def executemany(self, sql, rows):
        for r in rows:
            self.bars.setdefault((r[0], r[1], r[2], r[8]), r)

    async def fetchval(self, sql, sym, tf, src, a, b):
        return sum(1 for k in self.bars if k[0] == sym and k[1] == tf and k[3] == src and a <= k[2] <= b)

    async def fetch(self, sql, *a):
        if sql.lstrip().startswith("UPDATE dk.backfill_queue"):
            out = sorted((q for q in self.queue.values() if q["status"] == "pending"), key=lambda q: (q["priority"], -q["t0"].timestamp()))[: a[0]]
            for q in out:
                q["status"] = "running"
            return [dict(q) for q in out]
        raise AssertionError(sql)


class FakeFetcher:
    name = "fake"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def fetch(self, symbol, tf, t0, t1):
        self.calls.append((symbol, tf, t0, t1))
        if self.fail:
            raise TimeoutError("x")
        step, t, out = timedelta(seconds=bf.TF_SEC[tf]), t0, []
        while t <= t1:
            out.append((t, 1.0, 1.2, 0.9, 1.1, 5))
            t += step
        out.append((t1 + step, 1, 1, 1, 1, 1))  # ngoai khoang -> phai bi loc
        out.append((t0 + timedelta(seconds=1), 1, 1, 1, 1, 1))  # lech luoi -> loc
        return out


class Ctx:
    def __init__(self, db, fetcher, **kw):
        self.db, self.fetcher, self.account = db, fetcher, "mt5:1-feed"
        self.__dict__.update(kw)


def T(h, m=0, d=14):  # thu Ba 2026-10-13 +d
    return datetime(2026, 10, d, h, m, tzinfo=UTC)


def test_priority_majors_first():
    assert bf.priority_of("EURUSD", "M5", T(1), T(2)) < bf.priority_of("NZDMXN", "M1", T(1), T(2))
    assert bf.priority_of("EURUSD", "M1", T(1), T(2)) < bf.priority_of("EURUSD", "H1", T(1), T(2))


def test_subtract_closed_weekend():
    # gap T6 20:00 -> CN 23:00 M15; dong T6 22:00 -> CN 22:00
    g = bf.Gap("EURUSD", "M15", datetime(2026, 10, 16, 20, tzinfo=UTC), datetime(2026, 10, 18, 23, tzinfo=UTC))
    parts = bf.subtract_closed(g, [(datetime(2026, 10, 16, 22, tzinfo=UTC), datetime(2026, 10, 18, 22, tzinfo=UTC))])
    assert [(p.t0.hour, p.t1.hour) for p in parts] == [(20, 21), (22, 23)]
    assert parts[0].t1 == datetime(2026, 10, 16, 21, 45, tzinfo=UTC)


def test_gaps_from_matrix_skips_closed_and_bad():
    m = {"EURUSD": {"M1": {"status": "SLOW", "gaps": [(T(1), T(2)), {"t0": T(5), "t1": T(6)}, "bad"]},
                    "M5": {"status": "CLOSED", "gaps": [(T(1), T(2))]}}}
    assert len(bf.gaps_from_matrix(m, SRC)) == 2


def test_valid_bars_filters():
    ok = bf.valid_bars([(T(1), 1, 1.2, 0.9, 1.1, 1), (T(1), 1, 1.2, 0.9, 1.1, 1), (T(1, 1), 1, 1, 1, 1, 1),
                        (T(2), 1, 0.5, 0.9, 1.1, 1), (T(9), 1, 1, 1, 1, 1)], "M5", T(0), T(3))
    assert len(ok) == 1


async def test_cycle_fills_idempotent_and_logs():
    db, f = FakeDB(), FakeFetcher()
    m = {"EURUSD": {"M5": {"status": "SLOW", "gaps": [(T(1), T(1, 20))]}}}
    r = await bf.backfill_cycle(Ctx(db, f), m)
    assert r[0]["status"] == "done" and r[0]["inserted"] == 5 and len(db.bars) == 5
    assert all(k[3] == SRC for k in db.bars) and len(db.log) == 1
    r2 = await bf.backfill_cycle(Ctx(db, f), m)  # chay lai: khong xep trung, khong goi lai
    assert r2 == [] and len(db.bars) == 5 and len(f.calls) == 1


async def test_write_twice_inserts_zero():
    db = FakeDB()
    bars = [(T(1), 1, 1.2, 0.9, 1.1, 1)]
    assert await bf.write_bars(db, "EURUSD", "M5", SRC, bars) == 1
    assert await bf.write_bars(db, "EURUSD", "M5", SRC, bars) == 0


async def test_refuses_non_canon_source():
    with pytest.raises(ValueError):
        await bf.write_bars(FakeDB(), "EURUSD", "M5", "mt5hist:1", [(T(1), 1, 1, 1, 1, 1)])


async def test_latency_pause():
    db, f = FakeDB(), FakeFetcher()
    m = {"EURUSD": {"M5": {"status": "SLOW", "gaps": [(T(1), T(1, 20))]}}}
    r = await bf.backfill_cycle(Ctx(db, f, latency_p95=lambda: 0.9), m)
    assert r == [{"status": "paused_latency"}] and not f.calls and not db.bars


async def test_failure_logged_and_marked():
    db = FakeDB()
    m = {"EURUSD": {"M5": {"status": "SLOW", "gaps": [(T(1), T(1, 20))]}}}
    r = await bf.backfill_cycle(Ctx(db, FakeFetcher(fail=True)), m)
    assert r[0]["status"] == "failed" and db.log[0][8] == "failed"


async def test_enqueue_chunks_and_priority_order():
    db = FakeDB()
    n = await bf.enqueue(db, [bf.Gap("NZDMXN", "M1", T(0), T(0) + timedelta(minutes=4499)), bf.Gap("EURUSD", "H1", T(0), T(5))], SRC, now=T(6))
    assert n == 4  # 3 manh M1 (2000+2000+500) + 1
    first = (await bf.claim(db, 1))[0]
    assert first["symbol"] == "EURUSD"


async def test_parallel_capped_at_2():
    db, f = FakeDB(), FakeFetcher()
    gaps = [(T(h), T(h, 10)) for h in range(1, 6)]
    r = await bf.backfill_cycle(Ctx(db, f, backfill_parallel=9, backfill_batch=10), {"EURUSD": {"M5": {"status": "SLOW", "gaps": gaps}}})
    assert len(r) == 5


def test_guard_job_cfg_states(tmp_path):
    import os, time
    from data_keeper.backfill import guard_job_cfg
    assert guard_job_cfg(tmp_path, ttl_s=60)["state"] == "none"
    f = tmp_path / "job-mt5.cfg"
    f.write_text("MTAgentRange\nMTAgentRange.set\n")
    assert guard_job_cfg(tmp_path, ttl_s=60)["state"] == "active" and f.exists()
    old = time.time() - 3600
    os.utime(f, (old, old))
    r = guard_job_cfg(tmp_path, ttl_s=60)
    assert r["state"] == "removed" and not f.exists()
