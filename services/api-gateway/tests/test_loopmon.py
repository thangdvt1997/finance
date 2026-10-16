import asyncio
import logging
import time

from api_gateway.loopmon import M_STALLS, LoopMonitor


def test_loopmon_detects_blocking_call_and_logs_stack(caplog):
    async def run():
        mon = LoopMonitor(interval=0.02, stall_s=0.1)
        mon.start()
        await asyncio.sleep(0.05)
        before = M_STALLS._value.get()
        time.sleep(0.4)                       # chặn loop có chủ ý
        await asyncio.sleep(0.05)
        await mon.stop()
        return M_STALLS._value.get() - before

    with caplog.at_level(logging.WARNING, logger="gateway.loopmon"):
        n = asyncio.run(run())
    assert n >= 1
    assert any("time.sleep(0.4)" in r.getMessage() for r in caplog.records)


def test_fast_pstdev_matches_statistics_and_vol_series_last():
    import random
    import statistics

    from api_gateway import intel_calc as C

    rnd = random.Random(1)
    rets = [rnd.gauss(0, 0.01) for _ in range(600)]
    assert abs(C.pstdev(rets) - statistics.pstdev(rets)) < 1e-12
    full = C.vol_series(rets, 20)
    tail = C.vol_series(rets, 20, last=252)
    assert len(full) == 581 and len(tail) == 252
    assert all(abs(a - b) < 1e-12 for a, b in zip(full[-252:], tail))
    assert C.vol_series(rets[:10], 20) == []
    t0 = time.perf_counter()
    for _ in range(50):
        C.vol_series(rets, 20, last=252)
    assert time.perf_counter() - t0 < 1.0     # statistics.pstdev cũ: ~vài giây cho 50 symbol
