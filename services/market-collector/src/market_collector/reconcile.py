"""Doi chieu nguon gia: Dukascopy (chuan) vs OANDA / TrueFX (M1 cung phut) vs Frankfurter (ty gia ECB 14:15 CET).

Dinh ky (`RECONCILE_INTERVAL`) lay gio da dong gan nhat (tru `RECONCILE_LAG_HOURS` de Dukascopy kip xuat file), so gia dong cua M1
tren cac phut CHUNG; lech (bps = 1/10000) trung vi > nguong, hoac lech toi da > 4x nguong -> alert `alerts.out` (dedupe 6h/cap/nguon)
+ metric Prometheus. Khong co du lieu (cuoi tuan/nguon tat) -> trang thai `no_data`, KHONG alert. Chi doc, khong phat nen.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Callable

from prometheus_client import Counter, Gauge

from .config import CollectorSettings
from .models import ensure_utc, floor_ts, utcnow
from .providers.base import Provider
from .publisher import Publisher

log = logging.getLogger("market_collector.reconcile")

RECON_DIFF = Gauge("mc_recon_diff_bps", "Lech gia so voi Dukascopy (bps) o lan doi chieu gan nhat", ["pair", "source", "stat"])
RECON_MISMATCH = Counter("mc_recon_mismatch_total", "So lan doi chieu vuot nguong", ["pair", "source"])
RECON_LAST_RUN = Gauge("mc_recon_last_run_timestamp", "Unix ts lan doi chieu gan nhat")
RECON_STATUS = Gauge("mc_recon_status", "1 neu cap/nguon o trang thai nay", ["pair", "source", "status"])
MIN_COMMON = 5          # so phut chung toi thieu de ket luan
MAX_FACTOR = 4.0        # lech toi da > MAX_FACTOR * nguong -> bat thuong


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31 if month in (3, 10) else 30)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def cet_offset_hours(d: date) -> int:
    """Gio CET (+1) / CEST (+2) theo quy tac EU (chuyen gio cuoi tuan CN cua thang 3 va thang 10)."""
    return 2 if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10) else 1


def bps(a: float, b: float) -> float:
    return (a - b) / b * 1e4


def summarize(diffs: list[float]) -> dict:
    ad = [abs(x) for x in diffs]
    return {"n": len(diffs), "median_bps": round(statistics.median(ad), 3), "max_bps": round(max(ad), 3),
            "bias_bps": round(statistics.fmean(diffs), 3)}


class Reconciler:
    def __init__(self, providers: dict[str, Provider], publisher: Publisher, settings: CollectorSettings,
                 now: Callable[[], datetime] = utcnow):
        self.providers, self.pub, self.cfg, self._now = providers, publisher, settings, now
        self.last_report: dict = {"generated_at": None, "enabled": settings.reconcile_enabled, "results": [], "summary": {}}
        self._frank_done: dict[tuple[str, str], dict] = {}   # (pair, ecb_date) -> ket qua (moi ngay ECB chi doi chieu 1 lan)

    # ---- nguon M1 ----
    async def _m1_closes(self, name: str, pair: str, start: datetime, end: datetime) -> dict[datetime, float] | None:
        p = self.providers.get(name)
        if p is None:
            return None
        if name == "truefx":
            return p.minute_closes(pair, start, end)  # type: ignore[attr-defined]
        bars = await p.fetch_bars(pair, "M1", start, end)
        return {b.ts_open: b.c for b in bars}

    async def _compare_m1(self, source: str, pair: str, hour: datetime, ref: dict[datetime, float]) -> dict:
        res = {"pair": pair, "source": source, "reference": "dukascopy", "hour": hour.isoformat(), "threshold_bps": self.cfg.reconcile_threshold_bps}
        if not ref:
            return {**res, "status": "no_data", "note": "Dukascopy khong co du lieu gio nay (thi truong dong / chua xuat file)"}
        try:
            other = await self._m1_closes(source, pair, hour, hour + timedelta(hours=1))
        except Exception as e:  # noqa: BLE001
            return {**res, "status": "error", "note": f"{type(e).__name__}: {str(e)[:120]}"}
        common = sorted(set(ref) & set(other or {}))
        if len(common) < MIN_COMMON:
            return {**res, "status": "no_data", "n": len(common), "note": f"chi {len(common)} phut chung (< {MIN_COMMON})"}
        stats = summarize([bps(other[t], ref[t]) for t in common])  # type: ignore[index]
        th = self.cfg.reconcile_threshold_bps
        bad = stats["median_bps"] > th or stats["max_bps"] > th * MAX_FACTOR
        return {**res, **stats, "status": "warn" if bad else "ok"}

    # ---- Frankfurter (ECB) ----
    async def _compare_frankfurter(self, pair: str, now: datetime) -> dict | None:
        fr, duka = self.providers.get("frankfurter"), self.providers.get("dukascopy")
        if fr is None or duka is None or not fr.supports(pair):
            return None
        res = {"pair": pair, "source": "frankfurter", "reference": "dukascopy", "threshold_bps": self.cfg.reconcile_frankfurter_bps}
        try:
            bars = await fr.fetch_bars(pair, "D1", floor_ts(now - timedelta(days=7), "D1"), now + timedelta(seconds=1))
        except Exception as e:  # noqa: BLE001
            return {**res, "status": "error", "note": f"{type(e).__name__}: {str(e)[:120]}"}
        if not bars:
            return {**res, "status": "no_data", "note": "Frankfurter chua co ty gia"}
        last = bars[-1]
        day = last.ts_open.date()
        key = (pair, day.isoformat())
        if key in self._frank_done and self._frank_done[key]["status"] in ("ok", "warn"):
            return self._frank_done[key]
        # ECB tham chieu ~14:15 CET -> UTC; so voi gia dong cua phut M1 14:14 (gio CET) cua Dukascopy
        t_utc = datetime(day.year, day.month, day.day, 14, 14) - timedelta(hours=cet_offset_hours(day))
        t_utc = ensure_utc(t_utc)
        res.update(ecb_date=day.isoformat(), at=t_utc.isoformat())
        try:
            m1 = await duka.fetch_bars(pair, "M1", floor_ts(t_utc, "H1"), floor_ts(t_utc, "H1") + timedelta(hours=1))
        except Exception as e:  # noqa: BLE001
            return {**res, "status": "error", "note": f"{type(e).__name__}: {str(e)[:120]}"}
        near = [b for b in m1 if abs((b.ts_open - t_utc).total_seconds()) <= 180]
        if not near:
            return {**res, "status": "no_data", "note": "Dukascopy khong co M1 gan 14:15 CET"}
        ref = min(near, key=lambda b: abs((b.ts_open - t_utc).total_seconds())).c
        d = bps(last.c, ref)
        out = {**res, "n": 1, "median_bps": round(abs(d), 3), "max_bps": round(abs(d), 3), "bias_bps": round(d, 3),
               "status": "warn" if abs(d) > self.cfg.reconcile_frankfurter_bps else "ok"}
        self._frank_done[key] = out
        for k in [k for k in self._frank_done if k[0] == pair and k != key]:
            self._frank_done.pop(k, None)
        return out

    # ---- chay ----
    async def run_once(self) -> dict:
        now = self._now()
        results: list[dict] = []
        if "dukascopy" not in self.providers:
            self.last_report = {"generated_at": now.isoformat(), "enabled": True, "results": [], "summary": {},
                                "note": "thieu dukascopy (nguon chuan) -> khong doi chieu"}
            return self.last_report
        hour = floor_ts(now, "H1") - timedelta(hours=1 + self.cfg.reconcile_lag_hours)
        others = [n for n in ("oanda", "truefx") if n in self.providers]
        for pair in self.cfg.reconcile_pairs:
            ref: dict[datetime, float] = {}
            if self.providers["dukascopy"].supports(pair) and (others or "frankfurter" in self.providers):
                try:
                    ref = await self._m1_closes("dukascopy", pair, hour, hour + timedelta(hours=1)) or {}
                except Exception as e:  # noqa: BLE001
                    log.warning("doi chieu: Dukascopy %s loi %s", pair, type(e).__name__)
            for src in others:
                if self.providers[src].supports(pair):
                    results.append(await self._compare_m1(src, pair, hour, ref))
            fr = await self._compare_frankfurter(pair, now)
            if fr:
                results.append(fr)
        await self._publish(results, now)
        summary: dict[str, int] = {}
        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        self.last_report = {"generated_at": now.isoformat(), "enabled": True, "reference": "dukascopy",
                            "interval_s": self.cfg.reconcile_interval, "threshold_bps": self.cfg.reconcile_threshold_bps,
                            "frankfurter_threshold_bps": self.cfg.reconcile_frankfurter_bps,
                            "sources": sorted({r["source"] for r in results}), "results": results, "summary": summary}
        return self.last_report

    async def _publish(self, results: list[dict], now: datetime) -> None:
        RECON_LAST_RUN.set(now.timestamp())
        block = f"{now:%Y%m%d}{now.hour // 6}"
        for r in results:
            pair, src = r["pair"], r["source"]
            for st in ("ok", "warn", "no_data", "error"):
                RECON_STATUS.labels(pair, src, st).set(1 if r["status"] == st else 0)
            if "median_bps" in r:
                RECON_DIFF.labels(pair, src, "median").set(r["median_bps"])
                RECON_DIFF.labels(pair, src, "max").set(r["max_bps"])
            if r["status"] == "warn":
                RECON_MISMATCH.labels(pair, src).inc()
                await self.pub.alert(
                    "warn", f"Lech gia {pair}: {src} vs dukascopy",
                    f"Lech trung vi {r['median_bps']} bps, toi da {r['max_bps']} bps, thien lech {r.get('bias_bps')} bps "
                    f"(nguong {r['threshold_bps']} bps, {r.get('n')} mau, gio {r.get('hour') or r.get('at')}). "
                    f"Kiem tra nguon nao sai truoc khi dung du lieu de backtest/giao dich.",
                    ["market-collector", "reconcile", src, pair], f"mc:recon:{pair}:{src}:{block}")
