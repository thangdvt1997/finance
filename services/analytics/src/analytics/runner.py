from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram
from tscommon import make_event

from . import alerts as al
from . import stats
from .engine import Analysis, analyze
from .indicators import TF_SECONDS, resample, to_frame
from .repo import BarSource, SnapshotStore

log = logging.getLogger("analytics")

CYCLES = Counter("analytics_cycles_total", "Số chu kỳ tính", ["status"])
CYCLE_SECONDS = Histogram("analytics_cycle_seconds", "Thời gian 1 chu kỳ", buckets=(1, 5, 15, 30, 60, 120, 300, 600))
SNAPSHOTS = Gauge("analytics_snapshots", "Số snapshot (symbol×khung) của chu kỳ gần nhất")
ALERTS_SENT = Counter("analytics_alerts_published_total", "Cảnh báo điều kiện đã phát", ["rule"])
SYM_ERRORS = Counter("analytics_symbol_errors_total", "Lỗi tính theo symbol")
LAST_OK = Gauge("analytics_last_success_timestamp", "Unix time của chu kỳ thành công gần nhất")

SIGNALS_STREAM = "analytics.signals"
ALERTS_STREAM = "alerts.out"
RESAMPLE_FROM = {"H4": ("H1", 4), "D1": ("H1", 24)}


class Runner:
    def __init__(self, cfg: dict, source: BarSource, store: SnapshotStore, bus=None):
        self.cfg, self.source, self.store, self.bus = cfg, source, store, bus
        self._sent: dict[str, float] = {}
        self.last: dict = {"status": "chưa chạy"}

    # ------------------------------------------------------------------ nạp dữ liệu
    async def _frame(self, sym: str, tf: str, have: set[str]):
        lb = int(self.cfg["lookback_bars"].get(tf, 500))
        if tf in have:
            df = to_frame(await self.source.bars(sym, tf, lb))
            if len(df) >= self.cfg["min_bars"]:
                return df, False
        if self.cfg.get("resample_missing") and tf in RESAMPLE_FROM and "H1" in have:
            src, ratio = RESAMPLE_FROM[tf]
            raw = to_frame(await self.source.bars(sym, src, min(lb * ratio, 12000)))
            df = resample(raw, tf)
            if len(df) >= self.cfg["min_bars"]:
                return df, True
        return None, False

    def _pick_symbols(self, avail: dict) -> list[str]:
        sc = self.cfg["symbols"]
        inc, exc = set(sc.get("include") or []), set(sc.get("exclude") or [])
        syms = [s for s, tfs in avail.items() if "H1" in tfs or any(t in tfs for t in self.cfg["timeframes"])]
        if inc:
            syms = [s for s in syms if s in inc]
        syms = sorted(s for s in syms if s not in exc)
        return syms[: int(sc.get("max", 60))]

    # ------------------------------------------------------------------ 1 chu kỳ
    async def run_cycle(self) -> dict:
        t0 = time.monotonic()
        cfg = self.cfg
        tfs = list(cfg["timeframes"])
        need = sorted(set(tfs) | {"H1"})
        avail = await self.source.available(need)
        symbols = self._pick_symbols(avail)
        analyses: list[Analysis] = []
        h1: dict[str, object] = {}
        resampled = 0
        for sym in symbols:
            have = set(avail[sym])
            for tf in tfs:
                try:
                    df, rs = await self._frame(sym, tf, have)
                    if df is None:
                        continue
                    a = await asyncio.to_thread(analyze, sym, tf, df, int(cfg["series_points"]))
                    if a:
                        analyses.append(a)
                        resampled += int(rs)
                        if tf == "H1":
                            h1[sym] = df
                except Exception:  # noqa: BLE001
                    SYM_ERRORS.inc()
                    log.exception("analytics lỗi %s %s", sym, tf)
            if "H1" not in tfs and "H1" in have:
                try:
                    h1[sym] = to_frame(await self.source.bars(sym, "H1", int(cfg["sessions_days"]) * 24 + 24))
                except Exception:  # noqa: BLE001
                    SYM_ERRORS.inc()

        rows: list[tuple[str, str, dict]] = []
        for a in analyses:
            rows.append(("summary", f"{a.symbol}:{a.tf}", a.summary))
            rows.append(("detail", f"{a.symbol}:{a.tf}", a.detail))

        # tương quan
        cc = cfg["correlation"]
        corr = None
        frames = {a.symbol: a.df for a in analyses if a.tf == cc["tf"]}
        if frames:
            corr = await asyncio.to_thread(stats.correlation, frames, int(cc["window"]), int(cc["max_symbols"]))
        if corr:
            rows.append(("correlation", cc["tf"], corr))

        # phiên / giờ
        n_sess = 0
        for sym, df in h1.items():
            s = await asyncio.to_thread(stats.sessions, sym, df, cfg["sessions_utc"], int(cfg["sessions_days"]))
            if s:
                rows.append(("sessions", sym, s))
                n_sess += 1

        await self.store.upsert_many(rows)

        # cảnh báo điều kiện
        acfg = cfg["alerts"]
        cands: list[dict] = []
        if acfg.get("enabled"):
            for a in analyses:
                cands.extend(al.bar_alerts(a, acfg))
            if corr:
                flips = stats.correlation_flips(corr, float(acfg.get("correlation_flip", {}).get("min_abs_delta", 0.8)))
                cands.extend(al.correlation_alerts(flips, acfg, cc["tf"], corr["as_of"]))
        published = await self._publish_alerts(cands, int(acfg.get("max_per_cycle", 20)))

        heat = sorted(({"symbol": a.symbol, "tf": a.tf, "heat": a.summary["heat"], "bias": a.summary["bias"],
                        "trend": a.summary["trend"]} for a in analyses), key=lambda x: -x["heat"])[:10]
        out = {"generated_at": datetime.now(timezone.utc).isoformat(), "symbols": len(symbols), "snapshots": len(analyses),
               "resampled": resampled, "sessions": n_sess, "correlation": bool(corr), "alerts_published": published,
               "top_heat": heat, "disclaimer": "Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư."}
        if self.bus is not None:
            await self.bus.publish(SIGNALS_STREAM, make_event("analytics.snapshot", "analytics", out))
        SNAPSHOTS.set(len(analyses))
        LAST_OK.set(time.time())
        CYCLE_SECONDS.observe(time.monotonic() - t0)
        CYCLES.labels("ok").inc()
        self.last = {**out, "status": "ok", "seconds": round(time.monotonic() - t0, 2)}
        return out

    async def _publish_alerts(self, cands: list[dict], cap: int) -> int:
        now = time.time()
        self._sent = {k: t for k, t in self._sent.items() if now - t < 3 * 86400}
        n = 0
        for c in cands:
            if c["dedupe_key"] in self._sent:
                continue
            if n >= cap:
                break
            self._sent[c["dedupe_key"]] = now
            if self.bus is not None:
                await self.bus.publish(ALERTS_STREAM, make_event("alert", "analytics", c))
            ALERTS_SENT.labels(c["tags"][1] if len(c["tags"]) > 1 else "x").inc()
            n += 1
        return n


async def loop(runner: Runner, interval: int, stop: asyncio.Event) -> None:
    await asyncio.sleep(min(10, interval))
    while not stop.is_set():
        try:
            await runner.run_cycle()
        except Exception:  # noqa: BLE001
            CYCLES.labels("error").inc()
            runner.last = {"status": "lỗi", "generated_at": datetime.now(timezone.utc).isoformat()}
            log.exception("analytics: chu kỳ lỗi")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


__all__ = ["Runner", "loop", "TF_SECONDS"]
