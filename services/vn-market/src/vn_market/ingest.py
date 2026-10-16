"""Nạp dữ liệu cuối ngày VN từ VNDirect finfo vào Postgres (idempotent: chạy lại bao nhiêu lần cũng được, upsert).

Quy trình `run_once`:
  1. đồng bộ danh mục mã (stocks) + gắn ngành/rổ từ seed;
  2. chỉ số chính (lịch sử 2018 nếu thiếu) -> biết các phiên giao dịch gần đây (không cần lịch nghỉ lễ: sở là nguồn sự thật);
  3. với mỗi phiên trong cửa sổ `window` còn thiếu giá/khối ngoại: nạp giá 3 sàn + chỉ số + khối ngoại;
  4. phiên mới nhất: ratios (vốn hoá, P/E, P/B ...) + lịch sự kiện;
  5. backfill lịch sử D1 dài hạn cho rổ theo dõi (VN100 + HNX30 + ETF) nếu thiếu.
Vòng `loop` chỉ chạy khi phiên đã đóng cửa mà chưa có dữ liệu của phiên đó (kiểm tra 30 phút/lần), nên số request/ngày rất nhỏ.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone

from prometheus_client import Counter, Gauge

from . import rules, universe
from .vndirect import (RATIO_CODES, SourceError, VNDirectClient, merge_ratios, parse_event, parse_foreign, parse_index, parse_price)

log = logging.getLogger("vn_market.ingest")

INGEST_RUNS = Counter("vn_ingest_runs_total", "Số lần nạp dữ liệu VN", ["result"])
LAST_OK = Gauge("vn_ingest_last_ok_timestamp", "Epoch lần nạp thành công gần nhất")
LAST_SESSION_AGE = Gauge("vn_last_session_age_days", "Tuổi (ngày) của phiên mới nhất trong DB")
SOURCE_REQUESTS = Gauge("vn_source_requests", "Tổng request đã gọi VNDirect từ khi chạy")

MAIN_INDEXES = ["VNINDEX", "VN30", "VN100", "HNX", "HNX30", "UPCOM", "VNALL", "VNMID", "VNSML"]
HISTORY_START = date(2018, 1, 2)
FLOORS = ("HOSE", "HNX", "UPCOM")


class Ingestor:
    def __init__(self, client: VNDirectClient, store, *, window: int = 30, history_start: date = HISTORY_START, min_rows: int = 800):
        self.c = client
        self.s = store
        self.window = window
        self.history_start = history_start
        self.min_rows = min_rows   # số dòng tối thiểu/ngày để coi là đã nạp đủ (thực tế ~1.500 mã cả 3 sàn)
        self.status: dict = {"running": False, "last_run": None, "last_ok": None, "last_error": None, "stage": None, "last_summary": None}

    # ---- các bước -----------------------------------------------------------------------------------------------------------
    async def sync_symbols(self) -> int:
        rows = await self.c.listed_symbols()
        out = []
        for r in rows:
            code = (r.get("code") or "").strip().upper()
            if not code:
                continue
            ld = r.get("listedDate")
            out.append(universe.enrich_symbol({"code": code, "floor": r.get("floor") or "", "kind": r.get("type") or "STOCK",
                                               "name": r.get("companyName"), "short_name": r.get("shortName"),
                                               "listed_date": date.fromisoformat(ld[:10]) if ld else None}))
        n = await self.s.upsert("vn_symbols", out)
        await self.s.meta_set("symbols_synced", {"at": datetime.now(timezone.utc).isoformat(), "n": n})
        return n

    async def _ensure_symbols(self, price_rows: list[dict], known: set[str]) -> None:
        missing = {}
        for r in price_rows:
            if r["code"] not in known:
                missing[r["code"]] = r
        if missing:
            await self.s.upsert("vn_symbols", [universe.enrich_symbol({"code": c, "floor": r["floor"], "kind": r.get("kind") or "STOCK"}) for c, r in missing.items()])
            known.update(missing)

    async def ingest_day(self, d: date, known: set[str], *, foreign: bool = True, prices: bool = True) -> dict:
        res = {"d": d.isoformat(), "prices": 0, "foreign": 0, "index": 0}
        if prices:
            allp: list[dict] = []
            for fl in FLOORS:
                allp += [p for p in (parse_price(r) for r in await self.c.prices_on(fl, d)) if p]
            await self._ensure_symbols(allp, known)
            res["prices"] = await self.s.upsert("vn_daily", allp)
            idx = [p for p in (parse_index(r) for r in await self.c.indices_on(d)) if p]
            res["index"] = await self.s.upsert("vn_index_daily", idx)
        if foreign:
            fr = [p for p in (parse_foreign(r) for r in await self.c.foreign_on(d)) if p]
            res["foreign"] = await self.s.upsert("vn_foreign", fr)
        return res

    async def ingest_ratios(self, d: date) -> int:
        by = {}
        for rc in RATIO_CODES:
            by[rc] = await self.c.ratio_on(rc, d)
        rows = merge_ratios(by, d)
        return await self.s.upsert("vn_ratios", rows)

    async def ingest_events(self, today: date) -> int:
        rows = [p for p in (parse_event(r) for r in await self.c.events_between(today - timedelta(days=14), today + timedelta(days=150))) if p]
        return await self.s.upsert("vn_events", rows)

    async def ensure_indexes(self) -> dict:
        have = await self.s.index_counts()
        out = {}
        for code in MAIN_INDEXES:
            n = have.get(code, 0)
            start = self.history_start if n < 1200 else date.today() - timedelta(days=45)
            rows = [p for p in (parse_index(r) for r in await self.c.index_history(code, start)) if p]
            out[code] = await self.s.upsert("vn_index_daily", rows)
        return out

    async def backfill_focus(self, limit: int | None = None) -> dict:
        """Lịch sử D1 dài hạn (giá thô + giá điều chỉnh) cho rổ theo dõi nếu mã chưa đủ lịch sử."""
        cov = await self.s.daily_coverage()
        todo = [c for c in sorted(universe.focus_codes()) if cov.get(c, (0, None))[0] < 400]
        done = 0
        for code in todo[:limit]:
            try:
                rows = [p for p in (parse_price(r) for r in await self.c.price_history(code, self.history_start)) if p]
            except SourceError as e:
                log.warning("backfill %s lỗi: %s", code, e)
                continue
            await self.s.upsert("vn_daily", rows)
            done += 1
        return {"todo": len(todo), "done": done}

    # ---- vòng chính ---------------------------------------------------------------------------------------------------------
    async def run_once(self, *, force_symbols: bool = False, backfill: bool = True) -> dict:
        self.status.update(running=True, last_run=datetime.now(timezone.utc).isoformat(), stage="symbols")
        t0 = time.monotonic()
        summary: dict = {}
        try:
            meta = await self.s.meta_get("symbols_synced")
            if force_symbols or not meta or (datetime.now(timezone.utc) - datetime.fromisoformat(meta["at"])).days >= 7:
                summary["symbols"] = await self.sync_symbols()
            known = {s["code"] for s in await self.s.symbols()}
            self.status["stage"] = "indexes"
            summary["indexes"] = await self.ensure_indexes()
            latest = await self.s.latest_date()
            if latest is None:
                raise SourceError("không lấy được phiên mới nhất")
            dates = await self.s.trading_dates(self.window)
            price_have = await self.s.dates_with_prices(min(dates) if dates else latest)
            foreign_have = await self.s.foreign_dates(min(dates) if dates else latest)
            self.status["stage"] = "days"
            days = []
            for d in sorted(dates):
                need_p = price_have.get(d, 0) < self.min_rows
                need_f = foreign_have.get(d, 0) < self.min_rows
                if need_p or need_f:
                    days.append(await self.ingest_day(d, known, prices=need_p, foreign=need_f))
            summary["days"] = days
            ratio_meta = await self.s.meta_get("ratios")
            if not ratio_meta or ratio_meta.get("d") != latest.isoformat():
                self.status["stage"] = "ratios"
                n = await self.ingest_ratios(latest)
                if n == 0 and len(dates) > 1:   # ratios của phiên mới nhất chưa có -> thử phiên trước
                    n = await self.ingest_ratios(sorted(dates)[-2])
                summary["ratios"] = n
                if n:
                    await self.s.meta_set("ratios", {"d": latest.isoformat(), "n": n})
            ev_meta = await self.s.meta_get("events")
            vn_today = datetime.now(rules.VN_TZ).date()
            if not ev_meta or ev_meta.get("d") != vn_today.isoformat():
                self.status["stage"] = "events"
                summary["events"] = await self.ingest_events(vn_today)
                await self.s.meta_set("events", {"d": vn_today.isoformat(), "n": summary["events"]})
            if backfill:
                self.status["stage"] = "history"
                summary["history"] = await self.backfill_focus()
            await self.s.meta_set("ingest", {"d": latest.isoformat(), "at": datetime.now(timezone.utc).isoformat(), "summary": summary})
            self.status.update(last_ok=datetime.now(timezone.utc).isoformat(), last_error=None, last_summary=summary)
            INGEST_RUNS.labels("ok").inc()
            LAST_OK.set(time.time())
            LAST_SESSION_AGE.set((vn_today - latest).days)
            return summary
        except Exception as e:  # noqa: BLE001
            INGEST_RUNS.labels("error").inc()
            self.status["last_error"] = f"{type(e).__name__}: {e}"
            log.exception("nạp dữ liệu VN lỗi")
            raise
        finally:
            SOURCE_REQUESTS.set(self.c.requests)
            self.status.update(running=False, stage=None, last_duration_s=round(time.monotonic() - t0, 1))

    async def due(self, now: datetime | None = None) -> bool:
        """Có phiên đã đóng cửa mà DB chưa có không? (so với phiên cuối của sở; ngày lễ -> kiểm tra thưa)."""
        now = now or datetime.now(timezone.utc)
        expected = rules.last_session_date(now)
        latest = await self.s.latest_date()
        if latest is not None and latest.isoformat() >= expected:
            ev = await self.s.meta_get("events")
            return not ev or ev.get("d") != now.astimezone(rules.VN_TZ).date().isoformat()
        last_ok = self.status.get("last_ok")
        if latest is not None and last_ok and (now - datetime.fromisoformat(last_ok)).total_seconds() < 3 * 3600:
            return False   # ngày lễ/sở chưa công bố: kiểm tra thưa (3 giờ/lần) thay vì mỗi chu kỳ
        return True

    async def loop(self, interval_s: float = 1800.0, first_delay_s: float = 5.0) -> None:
        await asyncio.sleep(first_delay_s)
        while True:
            try:
                if await self.due():
                    await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  (đã log + đếm trong run_once)
                await asyncio.sleep(300)
            await asyncio.sleep(interval_s)
