from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from prometheus_client import Counter, Gauge, Histogram
from tscommon import make_event

from .detector import Detector
from .repo import BarSource, SignalStore
from .series import TF_SECONDS, Bar
from .specs import load_specs

log = logging.getLogger("pattern-engine")

CYCLES = Counter("pattern_cycles_total", "Số chu kỳ quét", ["status"])
CYCLE_SECONDS = Histogram("pattern_cycle_seconds", "Thời gian 1 chu kỳ", buckets=(0.5, 1, 2, 5, 15, 30, 60, 120))
SIGNALS = Counter("pattern_signals_total", "Sự kiện pattern.signal đã phát", ["pattern", "state"])
ERRORS = Counter("pattern_symbol_errors_total", "Lỗi theo symbol×khung")
SCANNED = Gauge("pattern_series_scanned", "Số chuỗi symbol×khung quét ở chu kỳ gần nhất")
LAST_OK = Gauge("pattern_last_success_timestamp", "Unix time chu kỳ thành công gần nhất")

STREAM = "pattern.signals"   # = tscommon.STREAMS["patterns"]


def to_bars(rows: list[dict], tf: str, now: datetime) -> list[Bar]:
    """Hàng DB -> Bar tăng dần theo thời gian, CHỈ nến đã đóng (ts_open + tf <= now)."""
    dt = timedelta(seconds=TF_SECONDS[tf])
    out: list[Bar] = []
    for r in sorted(rows, key=lambda r: r["ts_open"]):
        b = Bar(r["ts_open"], float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r.get("v") or 0))
        if b.ts + dt <= now and b.valid():
            out.append(b)
    return out


class Runner:
    def __init__(self, cfg: dict, source: BarSource, store: SignalStore, bus=None, specs: dict | None = None):
        self.cfg, self.source, self.store, self.bus = cfg, source, store, bus
        self.specs = specs or load_specs(overrides=cfg.get("overrides"))
        for sp in self.specs.values():
            sp["params"]["emit_forming"] = bool(cfg.get("emit_forming", True))
        self._last: dict[tuple[str, str], datetime] = {}
        self.last: dict = {"status": "chưa chạy"}

    def _pick_symbols(self, avail: dict) -> list[str]:
        sc = self.cfg["symbols"]
        inc, exc = set(sc.get("include") or []), set(sc.get("exclude") or [])
        syms = [s for s in avail if (not inc or s in inc) and s not in exc]
        return sorted(syms)[: int(sc.get("max", 40))]

    def scan_series(self, symbol: str, tf: str, bars: list[Bar]):
        d = Detector(symbol, tf, self.specs, self.cfg["patterns"])
        sigs = d.feed_many(bars)
        if not bars:
            return []
        horizon = bars[-1].ts - timedelta(seconds=TF_SECONDS[tf] * int(self.cfg["max_age_bars"]))
        return [s for s in sigs if s.bar_ts >= horizon]

    async def run_cycle(self, now: datetime | None = None) -> dict:
        t0 = time.monotonic()
        now = now or datetime.now(timezone.utc)
        if not self.cfg.get("patterns"):   # danh sách kịch bản bật rỗng = tắt quét
            self.last = {"status": "tắt (patterns rỗng)", "series": 0, "new": 0}
            return self.last
        tfs = list(self.cfg["timeframes"])
        avail = await self.source.available(tfs)
        n_series = n_new = 0
        for sym in self._pick_symbols(avail):
            for tf in tfs:
                if tf not in avail[sym] or tf not in TF_SECONDS:
                    continue
                try:
                    rows = await self.source.bars(sym, tf, int(self.cfg["lookback_bars"].get(tf, 700)))
                    bars = to_bars(rows, tf, now)
                    if len(bars) < 80 or self._last.get((sym, tf)) == bars[-1].ts:
                        continue
                    self._last[(sym, tf)] = bars[-1].ts
                    sigs = await asyncio.to_thread(self.scan_series, sym, tf, bars)
                    n_series += 1
                    for sg in sigs:
                        if await self.store.insert(sg):
                            n_new += 1
                            SIGNALS.labels(sg.pattern, sg.state).inc()
                            if self.bus is not None:
                                await self.bus.publish(STREAM, make_event("pattern.signal", "pattern-engine", sg.to_payload()))
                except Exception:  # noqa: BLE001
                    ERRORS.inc()
                    log.exception("pattern-engine lỗi %s %s", sym, tf)
        SCANNED.set(n_series)
        LAST_OK.set(time.time())
        CYCLE_SECONDS.observe(time.monotonic() - t0)
        CYCLES.labels("ok").inc()
        self.last = {"status": "ok", "generated_at": now.isoformat(), "series_scanned": n_series, "signals_new": n_new,
                     "seconds": round(time.monotonic() - t0, 2)}
        return self.last


async def loop(runner: Runner, interval: int, stop: asyncio.Event) -> None:
    await asyncio.sleep(min(10, interval))
    while not stop.is_set():
        try:
            await runner.run_cycle()
        except Exception:  # noqa: BLE001
            CYCLES.labels("error").inc()
            runner.last = {"status": "lỗi", "generated_at": datetime.now(timezone.utc).isoformat()}
            log.exception("pattern-engine: chu kỳ lỗi")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
