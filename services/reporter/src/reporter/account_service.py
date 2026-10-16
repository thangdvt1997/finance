"""Sinh báo cáo theo tài khoản + bộ lập lịch nền. Đồng thời tối đa 2 báo cáo, không chạy trùng cùng (tài khoản, kind, kỳ), bỏ qua tài khoản không có dữ liệu."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone

from prometheus_client import Counter

from .account_report import AuthClient, build_account, collect_account, due_period, has_data, last_period
from .account_store import AccountStore, ScheduleStore, valid_account
from .collect import Gateway
from .config import Settings
from .render import render_account_html, render_pdf

log = logging.getLogger("reporter.account")
GEN = Counter("reporter_account_reports_total", "Báo cáo theo tài khoản đã sinh", ["kind", "result"])
RETRY_AFTER = timedelta(minutes=30)


class AccountReporter:
    def __init__(self, cfg: Settings, store: AccountStore | None = None, schedules: ScheduleStore | None = None, gateway: Gateway | None = None,
                 auth: AuthClient | None = None, pdf=render_pdf, clock=lambda: datetime.now(timezone.utc), concurrency: int = 2):
        self.cfg = cfg
        self.store = store or AccountStore(cfg.reports_dir)
        self.schedules = schedules or ScheduleStore(cfg.reports_dir)
        self.gw, self.auth, self.pdf, self.clock = gateway, auth, pdf, clock
        self._sem = asyncio.Semaphore(concurrency)
        self._inflight: set[tuple[str, str, str]] = set()
        self._tried: dict[tuple[str, str], datetime] = {}
        self._done: set[tuple[str, str]] = set()

    # ---- kết nối ----
    def _auth(self) -> AuthClient | None:
        if self.auth is not None:
            return self.auth
        return AuthClient(self.cfg.auth_url, self.cfg.internal_token) if self.cfg.internal_token else None

    def default_period(self, kind: str) -> str:
        return last_period(kind, self.clock(), self.cfg.tz).isoformat()

    # ---- sinh một báo cáo ----
    async def generate(self, account_id: str, kind: str, period: str | None = None, release: bool = False, force: bool = True,
                       label: str | None = None) -> dict:
        if not valid_account(account_id):
            raise ValueError("account_id không hợp lệ")
        period = period or self.default_period(kind)
        key = (account_id, kind, period)
        if key in self._inflight:
            return {"skipped": "running", "account_id": account_id, "kind": kind, "period": period}
        if not force and self.store.exists(account_id, kind, period):
            return {**(self.store.find(account_id, kind, period) or {}), "skipped": "exists"}
        self._inflight.add(key)
        try:
            async with self._sem:
                t0 = time.time()
                now = self.clock()
                own_gw, own_auth = self.gw is None, self.auth is None
                gw = self.gw or Gateway(self.cfg)
                auth = self._auth()
                try:
                    raw = await collect_account(self.cfg, gw, auth, account_id, kind, period)
                finally:
                    if own_gw:
                        await gw.aclose()
                    if own_auth and auth is not None:
                        await auth.aclose()
                if not has_data(raw):
                    GEN.labels(kind, "no_data").inc()
                    return {"skipped": "no_data", "account_id": account_id, "kind": kind, "period": period}
                ctx = build_account(kind, period, account_id, label, raw, self.cfg, now)
                html = render_account_html(ctx)
                try:
                    pdf = await asyncio.to_thread(self.pdf, html)
                except Exception:  # noqa: BLE001  (vẫn lưu HTML, đánh dấu degraded)
                    log.exception("tạo PDF lỗi")
                    pdf = None
                entry = self.store.save(account_id, kind, period, html, pdf, ctx["ok"], ctx["fail"] + ([] if pdf else ["pdf"]), release, now)
                GEN.labels(kind, entry["status"]).inc()
                log.info("báo cáo tài khoản %s %s %s xong (%s) %.1fs", account_id, kind, period, entry["status"], time.time() - t0)
                return entry
        finally:
            self._inflight.discard(key)

    # ---- lịch ----
    async def resolve_scope(self, scope: dict) -> list[dict]:
        t, ref = scope.get("type"), scope.get("ref")
        if t == "account":
            return [{"account_id": ref, "label": None}] if valid_account(ref or "") else []
        auth = self._auth()
        if auth is None:
            raise RuntimeError("chưa cấu hình FLEET_INTERNAL_TOKEN: không phân giải được phạm vi")
        try:
            return [a for a in await auth.scope_accounts(t, ref) if valid_account(a.get("account_id", ""))]
        finally:
            if self.auth is None:
                await auth.aclose()

    async def run_schedule(self, sc: dict, now: datetime) -> bool:
        """Một lượt cho một lịch; True nếu mọi tài khoản xử lý xong (kể cả bỏ qua), False nếu có lỗi cần thử lại."""
        period = due_period(sc["kind"], sc["hour"], now, self.cfg.tz)
        accounts = await self.resolve_scope(sc["scope"])

        async def one(a: dict) -> bool:
            try:
                await self.generate(a["account_id"], sc["kind"], period, release=bool(sc.get("auto_release")), force=False, label=a.get("label"))
                return True
            except Exception:  # noqa: BLE001
                log.exception("lịch %s: tài khoản %s lỗi", sc.get("schedule_id"), a.get("account_id"))
                GEN.labels(sc["kind"], "error").inc()
                return False

        return all(await asyncio.gather(*[one(a) for a in accounts]))

    async def tick(self, now: datetime | None = None) -> int:
        now = now or self.clock()
        n = 0
        for sc in self.schedules.list():
            if not sc.get("enabled", True):
                continue
            try:
                period = due_period(sc["kind"], sc["hour"], now, self.cfg.tz)
            except Exception:  # noqa: BLE001
                continue
            key = (sc["schedule_id"], period)
            last = self._tried.get(key)
            if key in self._done or (last and now - last < RETRY_AFTER):
                continue
            self._tried[key] = now
            try:
                if await self.run_schedule(sc, now):
                    self._done.add(key)
                n += 1
            except Exception:  # noqa: BLE001
                log.exception("lịch %s lỗi", sc.get("schedule_id"))
        if len(self._tried) > 2000:
            self._tried.clear()
            self._done.clear()
        return n

    async def loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("vòng lập lịch báo cáo tài khoản lỗi")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.cfg.tick_seconds)
            except asyncio.TimeoutError:
                pass


def parse_period(s: str | None) -> str | None:
    if s is None:
        return None
    date.fromisoformat(s)   # ValueError nếu sai
    return s
