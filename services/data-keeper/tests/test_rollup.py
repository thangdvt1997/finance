import asyncio

from data_keeper import rollup
from data_keeper.inventory import classify
from data_keeper.config import get_settings
from datetime import datetime, timezone, timedelta

UTC = timezone.utc


def test_window_closed_bucket_only():
    now = datetime(2026, 10, 16, 8, 21, tzinfo=UTC).timestamp()
    lo, hi = rollup.window("M15", now)
    assert hi == datetime(2026, 10, 16, 8, 15, tzinfo=UTC).timestamp()   # 08:00 dong luc 08:15, qua grace 3 phut o 08:18
    assert (hi - lo) >= rollup.WINDOW_S - 900 and lo % 900 == 0
    lo, hi = rollup.window("M5", datetime(2026, 10, 16, 8, 17, tzinfo=UTC).timestamp())
    assert hi == datetime(2026, 10, 16, 8, 10, tzinfo=UTC).timestamp()   # 08:10 chua qua grace -> chua va


class FakeDB:
    rw = object()

    def __init__(self):
        self.calls = []

    async def execute(self, q, *a):
        self.calls.append(a)
        return "INSERT 0 3"


class Ctx:
    def __init__(self):
        self.db = FakeDB()


def test_cycle_inserts_each_tf():
    ctx = Ctx()
    out = asyncio.run(rollup.rollup_cycle(ctx))
    assert out == {"M5": 3, "M15": 3, "H1": 3}
    assert [c[0] for c in ctx.db.calls] == ["M5", "M15", "H1"]


def test_classify_tolerates_one_missing_high_tf_bar_after_restart():
    now = datetime(2026, 10, 16, 8, 21, tzinfo=UTC)
    cfg = get_settings()
    st, _ = classify(tf="M15", now=now, last_bar=datetime(2026, 10, 16, 7, 45, tzinfo=UTC), last_tick=now, market_open=True, open_since_s=99999, cfg=cfg)
    assert st == "OK"
    st, _ = classify(tf="M15", now=now, last_bar=datetime(2026, 10, 16, 6, 45, tzinfo=UTC), last_tick=now, market_open=True, open_since_s=99999, cfg=cfg)
    assert st == "SLOW"
