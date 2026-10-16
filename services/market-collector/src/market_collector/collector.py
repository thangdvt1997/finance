from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Callable

from .config import CollectorSettings
from .errors import PartialData, RetryableError
from .models import TF_SECONDS, ensure_utc, floor_ts, utcnow
from .providers.base import Provider
from .publisher import (BACKFILL_RUNNING, BARS_REJECTED, FETCH_EMPTY, FETCH_ERRORS, GAP_DAYS, GAP_FILLED,
                        LOOP_ALIVE, LOOP_ERRORS, QUALITY_ISSUES, Publisher)
from .quality import check_bars
from .resample import resample
from .state import StateStore

log = logging.getLogger("market_collector")

REJECT_KINDS = ("invalid_ohlc", "invalid_volume", "nonpositive")
UTC_DAY = timedelta(days=1)


class Collector:
    def __init__(self, providers: list[Provider], publisher: Publisher, settings: CollectorSettings,
                 state: StateStore | None = None, now: Callable[[], datetime] = utcnow,
                 sleep: Callable = asyncio.sleep):
        self.providers = {p.name: p for p in providers}
        self.pub, self.cfg = publisher, settings
        self.state = state or StateStore(None)
        self._now, self._sleep = now, sleep
        self._empty: Counter = Counter()
        self._errors: Counter = Counter()  # so lan loi lien tiep theo key
        self.backfill_pending: dict[str, dict] = {}  # provider:symbol -> {fails, next_try}
        self._stop = asyncio.Event()
        self.tasks: set[asyncio.Task] = set()
        self.last_ok: dict[str, datetime] = {}
        # gap registry: (provider, symbol, tf) -> {ngay_UTC: {fails, next_try, first_seen}}
        self.gaps: dict[tuple[str, str, str], dict[datetime, dict]] = {}
        self.loop_restarts: Counter = Counter()
        self.last_cycle: dict[str, datetime] = {}

    # ---- xu ly 1 lo nen ----
    def _align_start(self, start: datetime) -> datetime:
        """Cat cua so ve 00:00 UTC de bucket resample (toi D1) luon tron, khong de len ban dung bang nen thieu."""
        return floor_ts(start, "D1")

    async def process(self, provider: Provider, symbol: str, tf: str, bars: list, missing: list | None = None) -> int:
        clean, issues = check_bars(bars, ignore_weekend=provider.name != "frankfurter" and not provider.trades_weekends)
        by_kind: dict[str, list] = {}
        for i in issues:
            QUALITY_ISSUES.labels(provider.name, i.kind).inc()
            if i.kind in REJECT_KINDS:
                BARS_REJECTED.labels(provider.name, i.kind).inc()
            by_kind.setdefault(i.kind, []).append(i)
        for kind, items in by_kind.items():
            level = "warn" if kind in REJECT_KINDS or kind == "outlier" else "info"
            sample = "; ".join(f"{i.detail}" for i in items[:3])
            await self.pub.alert(level, f"Chat luong du lieu {symbol} {tf}: {kind}",
                                 f"{provider.name}: {len(items)} van de. {sample}",
                                 ["market-collector", "quality", provider.name, symbol],
                                 f"mc:quality:{provider.name}:{symbol}:{tf}:{kind}")
        if not clean:
            return 0
        if tf == "M1" and provider.resample_m1:
            n = 0
            for out_tf in self.cfg.output_tfs:
                out = clean if out_tf == "M1" else resample(clean, out_tf)
                if missing and out_tf != "M1":
                    # QA vong 4: poll thieu gio (503 tam thoi) -> KHONG phat nen gop (H1/H4/D1) chua gio thieu,
                    # neu khong se ghi de nen da day du bang ban thieu (vd USDJPY H4 08:00 mat gio 11)
                    w = timedelta(seconds=TF_SECONDS[out_tf])
                    out = [b for b in out if not any(b.ts_open <= m < b.ts_open + w for m in missing)]
                n += await self.pub.bars(out)
            return n
        return await self.pub.bars(clean)

    async def _fetch(self, provider: Provider, symbol: str, tf: str, start: datetime, end: datetime,
                     *, partial_ok=None, missing_out: list | None = None):
        """Tra ve list nen, hoac None khi loi. `partial_ok(missing) -> bool`: cho phep dung ket qua thieu mot phan
        (khi do `missing_out`, neu co, nhan danh sach gio thieu)."""
        key = f"{provider.name}:{symbol}:{tf}"
        try:
            bars = await provider.fetch_bars(symbol, tf, start, end)
            self._errors[key] = 0
            return bars
        except PartialData as e:
            await self._note_error(provider, key, symbol, tf, e, transient=True)
            if partial_ok is not None and partial_ok(e.missing):
                if missing_out is not None:
                    missing_out.extend(e.missing)
                return list(e.bars or [])
            return None
        except Exception as e:  # noqa: BLE001
            await self._note_error(provider, key, symbol, tf, e, transient=isinstance(e, RetryableError))
            return None

    async def _note_error(self, provider: Provider, key: str, symbol: str, tf: str, e: Exception, *, transient: bool) -> None:
        FETCH_ERRORS.labels(provider.name).inc()
        self._errors[key] += 1
        n = self._errors[key]
        # loi tam thoi (503/429/mang): chi canh bao o log, khong alert tru khi keo dai lien tuc
        log.warning("fetch loi %s %s %s (lan %d lien tiep): %s", provider.name, symbol, tf, n, e)
        threshold = self.cfg.error_alert_after if transient else 1
        if n == threshold or (transient and n > threshold and n % (threshold * 10) == 0):
            await self.pub.alert("warn", f"{provider.name} loi lay du lieu {symbol} {tf}",
                                 f"{n} lan loi lien tiep. {str(e)[:300]}",
                                 ["market-collector", "fetch-error", provider.name], f"mc:error:{key}")

    # ---- backfill ----
    async def backfill(self, provider_name: str, symbol: str, start: datetime, end: datetime | None = None,
                       tfs: list[str] | None = None, *, resume: bool = False, plan: bool = False) -> int:
        """Tra ve so nen da phat. Loi tam thoi -> dung o chunk loi (giu moc resume), danh dau `backfill_pending`
        de vong lap provider thu lai sau (cooldown tang dan). Hoan tat -> xoa khoi pending."""
        provider = self.providers[provider_name]
        end = ensure_utc(end or self._now())
        total = 0
        pkey = f"{provider.name}:{symbol}"
        incomplete = False
        BACKFILL_RUNNING.inc()
        try:
            for tf in tfs or provider.fetch_tfs:
                key = f"{provider.name}:{symbol}:{tf}"
                cursor = self._align_start(ensure_utc(provider.backfill_start(tf, ensure_utc(start), end) if plan else start))
                if resume and (done := self.state.get(key)):
                    cursor = max(cursor, self._align_start(done))
                chunk = provider.chunk_for(tf)
                while cursor < end:
                    chunk_end = min(cursor + chunk, end)
                    missing: list[datetime] = []
                    # chunk thieu mot so gio (503/429): van phat phan da co, ghi gio thieu vao gap registry
                    # va DI TIEP sang chunk sau (khong de 1 gio loi chan ca cac ngay phia sau).
                    bars = await self._fetch(provider, symbol, tf, cursor, chunk_end,
                                             partial_ok=lambda m: True, missing_out=missing)
                    if bars is None:
                        incomplete = True
                        break  # loi han (khong phai thieu gio): giu moc cu, lan sau (resume) lam tiep tu chunk nay
                    total += await self.process(provider, symbol, tf, bars, missing) if bars else 0
                    if missing:
                        self._add_gap_days(provider, symbol, tf, {floor_ts(m, "D1") for m in missing})
                    if resume:
                        self.state.set(key, chunk_end)
                    cursor = chunk_end
        finally:
            BACKFILL_RUNNING.dec()
        if incomplete:
            prev = self.backfill_pending.get(pkey, {"fails": 0})
            fails = prev["fails"] + 1
            delay = min(self.cfg.backfill_retry_max, self.cfg.backfill_retry_base * 2 ** (fails - 1))
            self.backfill_pending[pkey] = {"fails": fails, "next_try": self._now() + timedelta(seconds=delay)}
        else:
            self.backfill_pending.pop(pkey, None)
        return total

    # ---- cap nhat dinh ky ----
    async def poll_once(self, provider: Provider, symbol: str) -> int:
        now = self._now()
        total = 0
        for tf in provider.poll_tfs(symbol, now):
            start = provider.poll_start(symbol, tf, now) or self._align_start(now - provider.lookback)
            tail = floor_ts(now, "H1") - timedelta(hours=1)
            # thieu gio gan nhat (dang phat hanh/503) la binh thuong -> van phat phan da co
            missing: list[datetime] = []
            bars = await self._fetch(provider, symbol, tf, start, now + timedelta(seconds=1),
                                     partial_ok=lambda missing: all(m >= tail for m in missing), missing_out=missing)
            if bars is None:
                continue
            ekey = f"{provider.name}:{symbol}:{tf}"
            if not bars:
                if provider.expects_data(now, symbol):
                    FETCH_EMPTY.labels(provider.name).inc()
                    self._empty[ekey] += 1
                    if self._empty[ekey] == self.cfg.empty_alert_after:
                        await self.pub.alert("warn", f"{provider.name} tra du lieu rong lien tuc ({symbol} {tf})",
                                             f"{self._empty[ekey]} lan lien tiep khong co nen trong khi thi truong dang mo.",
                                             ["market-collector", "empty", provider.name], f"mc:empty:{ekey}")
                continue
            self._empty[ekey] = 0
            self.last_ok[ekey] = now
            try:
                total += await self.process(provider, symbol, tf, bars, missing)
            except Exception:
                # phat that bai (vd Redis dang nap/timeout): provider da ghi nho 'nen cuoi da thay' khi fetch -> lui lai de lan poll sau lay lai, khong de lai khe M1
                provider.rewind(symbol, tf, start)
                raise
        if provider.has_quotes and symbol in self.cfg.symbols_for(provider.name):
            try:
                q = await provider.latest_quote(symbol)
                if q:
                    await self.pub.quote(q)
            except Exception as e:  # noqa: BLE001
                FETCH_ERRORS.labels(provider.name).inc()
                log.warning("quote loi %s %s: %s", provider.name, symbol, e)
        return total

    async def retry_pending_backfills(self, provider_name: str) -> int:
        """Thu lai backfill con do (loi tam thoi) khi den han cooldown; resume tu moc da luu."""
        total = 0
        now = self._now()
        start = now - timedelta(days=self.cfg.backfill_days)
        for pkey, info in list(self.backfill_pending.items()):
            prov, _, symbol = pkey.partition(":")
            if prov != provider_name or info["next_try"] > now or self._stop.is_set():
                continue
            total += await self.backfill(prov, symbol, start, resume=True, plan=True)
        return total

    async def _quote_loop(self, provider: Provider) -> None:
        """Vong lap quote gan real-time (1 lan goi cho moi symbol), chi phat khi gia doi; loi -> backoff, khong bao gio chet."""
        last: dict[str, tuple[float, float]] = {}
        fails = 0
        while not self._stop.is_set():
            delay = provider.quote_stream_interval
            try:
                for q in await provider.latest_quotes():
                    if last.get(q.symbol) != (q.bid, q.ask):
                        last[q.symbol] = (q.bid, q.ask)
                        await self.pub.quote(q)
                fails = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                fails += 1
                FETCH_ERRORS.labels(provider.name).inc()
                delay = min(300.0, provider.quote_stream_interval * 2 ** min(fails, 5))
                if fails in (1, 10) or fails % 100 == 0:
                    log.warning("quote-stream %s loi (lan %d): %s", provider.name, fails, e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    # ---- gap detector + lap day ----
    def _add_gap_days(self, provider: Provider, symbol: str, tf: str, days: set[datetime]) -> None:
        reg = self.gaps.setdefault((provider.name, symbol, tf), {})
        now = self._now()
        for d in days:
            reg.setdefault(d, {"fails": 0, "next_try": now, "first_seen": now})
        self._update_gap_gauge(provider.name)

    def _update_gap_gauge(self, provider_name: str) -> None:
        GAP_DAYS.labels(provider_name).set(sum(len(r) for (p, _, _), r in self.gaps.items() if p == provider_name))

    def detect_gaps(self, provider: Provider) -> int:
        """Quet khoang trong trong cua so `gap_scan_days` (provider tu bao qua `find_missing_days`).
        Tra ve so ngay thieu moi phat hien."""
        now = self._now()
        start = floor_ts(now - timedelta(days=self.cfg.gap_scan_days), "D1")
        new = 0
        for symbol in (s for s in self.cfg.symbols_for(provider.name) if provider.supports(s)):
            for tf in provider.fetch_tfs:
                found = set(provider.find_missing_days(symbol, tf, start, now))
                reg = self.gaps.get((provider.name, symbol, tf), {})
                new += len(found - set(reg))
                if found:
                    self._add_gap_days(provider, symbol, tf, found)
                for d in [d for d in reg if d not in found]:  # da duoc lap (vd boi backfill thu cong) -> bo
                    reg.pop(d, None)
        for k in [k for k, r in self.gaps.items() if not r]:
            self.gaps.pop(k, None)
        self._update_gap_gauge(provider.name)
        return new

    async def fill_gaps(self, provider: Provider, max_days: int | None = None) -> int:
        """Tai lai (nguyen ngay UTC, ngay moi nhat truoc) cac ngay con thieu theo cooldown tang dan.
        Tra ve so ngay da lap day hoan toan."""
        limit = max_days if max_days is not None else self.cfg.gap_fill_per_cycle
        now = self._now()
        todo = [(d, k) for k, reg in self.gaps.items() if k[0] == provider.name
                for d, info in reg.items() if info["next_try"] <= now]
        todo.sort(key=lambda x: x[0], reverse=True)
        filled = 0
        for day, k in todo[:limit]:
            if self._stop.is_set():
                break
            _, symbol, tf = k
            info = self.gaps[k][day]
            missing: list[datetime] = []
            bars = await self._fetch(provider, symbol, tf, day, min(day + UTC_DAY, now),
                                     partial_ok=lambda m: True, missing_out=missing)
            if bars:
                await self.process(provider, symbol, tf, bars)
            if bars is not None and not missing:
                self.gaps[k].pop(day, None)
                GAP_FILLED.labels(provider.name).inc()
                filled += 1
            else:
                info["fails"] += 1
                delay = min(self.cfg.backfill_retry_max, self.cfg.backfill_retry_base * 2 ** (info["fails"] - 1))
                info["next_try"] = now + timedelta(seconds=delay)
        for k in [k for k, r in self.gaps.items() if not r]:
            self.gaps.pop(k, None)
        self._update_gap_gauge(provider.name)
        await self._alert_stuck_gaps(provider)
        return filled

    async def _alert_stuck_gaps(self, provider: Provider) -> None:
        """1 alert tong hop / provider khi co ngay thieu ton qua `gap_alert_after` giay."""
        now = self._now()
        stuck = [(k, d) for k, reg in self.gaps.items() if k[0] == provider.name
                 for d, info in reg.items() if (now - info["first_seen"]).total_seconds() >= self.cfg.gap_alert_after]
        if not stuck:
            return
        sample = ", ".join(f"{k[1]} {d:%m-%d}" for k, d in sorted(stuck, key=lambda x: x[1])[:6])
        await self.pub.alert("warn", f"{provider.name}: {len(stuck)} ngay du lieu con thieu",
                             f"Chua lap duoc sau {self.cfg.gap_alert_after / 3600:.0f}h (van tiep tuc thu lai). Vi du: {sample}",
                             ["market-collector", "gap", provider.name], f"mc:gap:{provider.name}")

    async def _guarded(self, provider: Provider, what: str, fn, *a, **kw):
        """Chay 1 buoc cua vong lap; ngoai le bat ky (vd Redis rot) KHONG duoc giet task provider."""
        try:
            return await fn(*a, **kw)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            LOOP_ERRORS.labels(provider.name).inc()
            log.exception("loi %s %s: %s", provider.name, what, e)
            return None

    async def _provider_loop(self, provider: Provider) -> None:
        symbols = [s for s in self.cfg.symbols_for(provider.name) if provider.supports(s)]
        if not symbols:
            log.info("%s: khong co symbol -> khong chay", provider.name)
            return
        backfill_on = self.cfg.backfill_on_start and self.cfg.backfill_days > 0
        if backfill_on:
            start = self._now() - timedelta(days=self.cfg.backfill_days)
            for s in symbols:
                r = await self._guarded(provider, f"backfill {s}", self.backfill, provider.name, s, start, resume=True, plan=True)
                if r is None:  # loi bat ngo (vd Redis rot giua chung) -> dat lich thu lai thay vi bo quen
                    self.backfill_pending.setdefault(f"{provider.name}:{s}", {"fails": 1, "next_try": self._now()})
        last_scan: datetime | None = None
        while not self._stop.is_set():
            for s in symbols:
                await self._guarded(provider, f"poll {s}", self.poll_once, provider, s)
            if backfill_on:
                await self._guarded(provider, "retry backfill", self.retry_pending_backfills, provider.name)
            now = self._now()
            if backfill_on and self.cfg.gap_scan_interval > 0 and (
                    last_scan is None or (now - last_scan).total_seconds() >= self.cfg.gap_scan_interval):
                last_scan = now
                try:
                    self.detect_gaps(provider)
                except Exception as e:  # noqa: BLE001
                    LOOP_ERRORS.labels(provider.name).inc()
                    log.exception("loi detect_gaps %s: %s", provider.name, e)
            if any(k[0] == provider.name for k in self.gaps):
                await self._guarded(provider, "fill gaps", self.fill_gaps, provider)
            self.last_cycle[provider.name] = self._now()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=provider.next_poll_delay(self._now()))
            except asyncio.TimeoutError:
                pass

    async def _supervise(self, provider: Provider) -> None:
        """Task provider thoat bat thuong -> ghi log + khoi dong lai (khong bao gio chet am tham)."""
        LOOP_ALIVE.labels(provider.name).set(1)
        try:
            while not self._stop.is_set():
                try:
                    await self._provider_loop(provider)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    LOOP_ERRORS.labels(provider.name).inc()
                    self.loop_restarts[provider.name] += 1
                    log.exception("task provider %s chet bat thuong, khoi dong lai: %s", provider.name, e)
                    await self._sleep(5)
        finally:
            LOOP_ALIVE.labels(provider.name).set(0)

    def start(self) -> None:
        for p in self.providers.values():
            t = asyncio.create_task(self._supervise(p), name=f"provider-{p.name}")
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)
            if p.quote_stream_interval > 0:
                q = asyncio.create_task(self._quote_loop(p), name=f"quotes-{p.name}")
                self.tasks.add(q)
                q.add_done_callback(self.tasks.discard)

    async def stop(self) -> None:
        self._stop.set()
        for t in list(self.tasks):
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for p in self.providers.values():
            await p.aclose()
