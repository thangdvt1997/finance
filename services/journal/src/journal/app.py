"""journal: nhat ky giao dich + analytics tai khoan (MT4/MT5 tu account_deals, paper tu paper_fills). READ-ONLY ve giao dich.

Chi doc du lieu giao dich (role ts_ro). Ghi DUY NHAT bang journal_notes (tag/ghi chu/review tay) qua role ts_journal. Khong dat/sua/dong lenh.
API noi bo (chi api-gateway goi): GET /journal/accounts | /{id}/summary | /{id}/deals | /{id}/discipline | /{id}/excursions | /{id}/review | /{id}/notes |
PUT/DELETE /{id}/notes/{kind}/{ref}.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from prometheus_client import Counter
from tscommon import make_app
from tscommon import risk_windows as rw

from . import __version__, discipline, excursions, review, stats
from .models import KINDS, REF_RE, NoteIn, Trade
from .notes import LimitReached
from .source import Source

log = logging.getLogger("journal")
ID_RE = re.compile(r"^[\w.:\-]{1,64}$")
TZ_RE = re.compile(r"^[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}$")
DEFAULT_TZ = os.getenv("JOURNAL_TZ", "Asia/Ho_Chi_Minh")
MAX_ANALYZE = 5000  # so lenh toi da dua vao kiem tra ky luat (O(n^2))
NOTE_WRITES = Counter("journal_note_writes_total", "Ghi chu/tag da ghi", ["op"])
CACHE_TTL_S = 10.0


def tz_of(name: Optional[str]) -> ZoneInfo:
    name = name or DEFAULT_TZ
    if not TZ_RE.match(name):
        raise HTTPException(422, "tz không hợp lệ")
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "tz không hợp lệ") from None


def parse_when(v: Optional[str], tz: ZoneInfo, end: bool = False) -> Optional[datetime]:
    """YYYY-MM-DD (ngay theo tz; `end` -> het ngay do) hoac ISO datetime."""
    if not v:
        return None
    try:
        if len(v) == 10:
            d = date.fromisoformat(v)
            dt = datetime(d.year, d.month, d.day, tzinfo=tz) + (timedelta(days=1) if end else timedelta())
            return dt.astimezone(timezone.utc)
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(422, f"thời gian không hợp lệ: {v!r}") from None


def check_id(account_id: str) -> str:
    if not ID_RE.match(account_id):
        raise HTTPException(422, "account_id không hợp lệ")
    return account_id


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def row_out(t: Trade, note: Optional[dict] = None, flags: Optional[list[str]] = None) -> dict:
    r = t.r_multiple
    return {"ticket": t.ticket, "position_id": t.position_id, "symbol": t.symbol, "side": t.side, "volume": t.volume, "price_open": t.price_open,
            "price_close": t.price_close, "sl": t.sl, "tp": t.tp, "time_open": t.time_open.isoformat(), "time_close": t.time_close.isoformat(),
            "hold_s": round(t.hold_s), "profit": round(t.profit, 2), "swap": round(t.swap, 2), "commission": round(t.commission, 2), "net": round(t.net, 2),
            "r": None if r is None else round(r, 2), "magic": t.magic, "group": t.group, "reason": t.reason, "comment": t.comment, "source": t.source,
            "note": None if not note else {"tags": note["tags"], "note": note["note"], "rating": note["rating"], "updated_at": _iso(note["updated_at"])},
            "flags": flags or []}


class Ctx:
    """Nap du lieu 1 tai khoan (cache ngan) + cac phep loc dung chung."""

    def __init__(self, source: Source, notes, rw_cfg: Optional[dict]):
        self.source, self.notes, self.rw_cfg = source, notes, rw_cfg
        self._cache: dict[str, tuple[float, Any]] = {}

    async def account(self, account_id: str) -> dict:
        a = await self.source.account(check_id(account_id))
        if a is None:
            raise HTTPException(404, "không có tài khoản/nhật ký này")
        return a

    async def all_rows(self, acct: dict) -> tuple[list[Trade], Optional[float], str]:
        """(toan bo dong, base truoc deal dau tien, nguon base)."""
        k = acct["account_id"]
        hit = self._cache.get(k)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        rows = await self.source.trades(acct, None, None)
        if acct["kind"] == "paper":
            base, src = acct.get("initial_capital"), "paper_initial_capital"
        else:
            bal = await self.source.balance_now(acct)
            total = sum((t.net if t.kind == "trade" else t.profit) for t in rows)
            base, src = (bal - total, "balance_now_minus_history") if bal is not None else (None, "unknown")
        res = (rows, None if base is None else float(base), src)
        self._cache[k] = (time.monotonic(), res)
        return res

    async def window(self, acct: dict, start, end, symbol: Optional[str], group: Optional[str], side: Optional[str]) -> dict:
        rows, base, base_src = await self.all_rows(acct)
        pre = [t for t in rows if start is not None and t.time_close < start]
        base_w = None if base is None else base + sum((t.net if t.kind == "trade" else t.profit) for t in pre)
        win = [t for t in rows if (start is None or t.time_close >= start) and (end is None or t.time_close < end)]
        filtered = bool(symbol or group or side)
        if filtered:
            win = [t for t in win if t.kind == "trade" and (not symbol or t.symbol == symbol) and (not group or t.group == group) and (not side or t.side == side)]
        return {"rows": win, "trades": [t for t in win if t.kind == "trade"], "base": base_w, "base_source": base_src, "filtered": filtered}

    def disc_cfg(self, acct: dict, params: Optional[dict]) -> dict:
        p = dict(params or {})
        if acct["kind"] == "paper":
            p["require_sl"] = False
        return p

    async def run_discipline(self, acct: dict, trades: list[Trade], tz: ZoneInfo, base: Optional[float], params: Optional[dict]) -> dict:
        ts = sorted((t for t in trades if t.kind == "trade"), key=lambda t: t.time_open)[-MAX_ANALYZE:]
        events: list[dict] = []
        if ts:
            events = await self.source.calendar_events(min(t.time_open for t in ts) - timedelta(days=1), max(t.time_open for t in ts) + timedelta(days=1))
        # paper: khong ap dung 'news' neu khong co cua so (van tinh binh thuong); symbol khong ho tro -> khong co co
        return discipline.check(ts, tz, events=events, rw_cfg=self.rw_cfg, params=self.disc_cfg(acct, params), base_equity=base)


def create_app(source: Optional[Source] = None, notes=None, rw_cfg: Optional[dict] = None) -> FastAPI:
    app = make_app("journal", __version__, internal_auth=True)
    app.state.source, app.state.notes = source, notes
    app.state.ctx = None
    started = time.time()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        own = []
        if _app.state.source is None:
            from .source import PgSource
            _app.state.source = await PgSource.connect(os.environ["DATABASE_URL"])
            own.append(_app.state.source)
        if _app.state.notes is None:
            from .notes import PgNotes
            _app.state.notes = await PgNotes.connect(os.environ["JOURNAL_DB_RW_URL"])
            own.append(_app.state.notes)
        cfg = rw_cfg
        if cfg is None:
            with contextlib.suppress(Exception):
                cfg = rw.load_config()
        _app.state.ctx = Ctx(_app.state.source, _app.state.notes, cfg)
        try:
            yield
        finally:
            for o in own:
                with contextlib.suppress(Exception):
                    await o.close()

    app.router.lifespan_context = lifespan
    if source is not None and notes is not None:
        app.state.ctx = Ctx(source, notes, rw_cfg)

    def ctx(request: Request) -> Ctx:
        c = request.app.state.ctx
        if c is None:
            raise HTTPException(503, "journal chưa sẵn sàng")
        return c

    @app.get("/status", tags=["ops"])
    async def status(request: Request):
        accts = await ctx(request).source.accounts()
        return {"accounts": len(accts), "uptime_s": int(time.time() - started), "read_only": True}

    @app.get("/journal/accounts", tags=["journal"])
    async def accounts(request: Request):
        c = ctx(request)
        out = []
        for a in await c.source.accounts():
            out.append({"account_id": a["account_id"], "kind": a["kind"], "platform": a.get("platform"), "name": a.get("name"), "strategy": a.get("strategy"),
                        "currency": a.get("currency"), "n_trades": int(a.get("n_trades", a.get("n_fills", 0)) or 0),
                        "first": _iso(a.get("first_ts")), "last": _iso(a.get("last_ts")), "source": a.get("source")})
        return {"items": out, "read_only": True}

    @app.get("/journal/{account_id}/summary", tags=["journal"])
    async def summary(request: Request, account_id: str, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, tz: Optional[str] = None,
                      symbol: Optional[str] = Query(None, max_length=32), group: Optional[str] = Query(None, max_length=40), side: Optional[str] = Query(None, pattern="^(buy|sell)$")):
        c = ctx(request)
        z = tz_of(tz)
        acct = await c.account(account_id)
        w = await c.window(acct, parse_when(frm, z), parse_when(to, z, end=True), symbol, group, side)
        ts = w["trades"]
        curve = stats.equity_curve(w["rows"], w["base"])
        s = stats.summarize(ts)
        return {"account": {"account_id": acct["account_id"], "kind": acct["kind"], "platform": acct.get("platform"), "currency": acct.get("currency")},
                "filters": {"from": frm, "to": to, "symbol": symbol, "group": group, "side": side, "tz": z.key}, "filtered": w["filtered"],
                "base_source": w["base_source"], "summary": s, "equity": curve, "streaks": stats.streaks(ts), "hold": stats.hold_stats(ts), "costs": stats.costs(ts),
                "r": stats.r_distribution(ts), "groups": stats.groups(ts, z), "contribution": stats.contribution(ts), "calendar": stats.calendar_days(ts, z),
                "n_balance_ops": sum(1 for t in w["rows"] if t.kind == "balance"),
                "notes": ["Thống kê trên deal ĐÃ ĐÓNG (không gồm lệnh đang mở/floating).", "Giờ/ngày/thứ theo thời điểm VÀO lệnh; lịch lãi/lỗ theo ngày ĐÓNG lệnh; phiên theo giờ UTC lúc vào."]}

    @app.get("/journal/{account_id}/deals", tags=["journal"])
    async def deals(request: Request, account_id: str, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, tz: Optional[str] = None,
                    symbol: Optional[str] = Query(None, max_length=32), group: Optional[str] = Query(None, max_length=40), side: Optional[str] = Query(None, pattern="^(buy|sell)$"),
                    tag: Optional[str] = Query(None, max_length=32), outcome: Optional[str] = Query(None, pattern="^(win|loss|be)$"),
                    flagged: bool = False, sort: str = Query("time_close", pattern="^(time_close|time_open|net|profit|volume|symbol|hold_s|r)$"),
                    order: str = Query("desc", pattern="^(asc|desc)$"), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0, le=100000)):
        c = ctx(request)
        z = tz_of(tz)
        acct = await c.account(account_id)
        w = await c.window(acct, parse_when(frm, z), parse_when(to, z, end=True), symbol, group, side)
        ts = w["trades"]
        notes_all = {n["ref"]: n for n in await c.notes.list(acct["account_id"], "deal")}
        if tag:
            ts = [t for t in ts if tag in (notes_all.get(t.ticket) or {}).get("tags", [])]
        if outcome:
            ts = [t for t in ts if (t.net > 0 if outcome == "win" else t.net < 0 if outcome == "loss" else t.net == 0)]
        disc = await c.run_discipline(acct, ts, z, w["base"], None)
        flags = disc["tickets"]
        if flagged:
            ts = [t for t in ts if t.ticket in flags]
        keyf = {"time_close": lambda t: t.time_close, "time_open": lambda t: t.time_open, "net": lambda t: t.net, "profit": lambda t: t.profit,
                "volume": lambda t: t.volume, "symbol": lambda t: t.symbol, "hold_s": lambda t: t.hold_s, "r": lambda t: (t.r_multiple is None, t.r_multiple or 0.0)}[sort]
        ts = sorted(ts, key=keyf, reverse=(order == "desc"))
        page = ts[offset:offset + limit]
        return {"total": len(ts), "offset": offset, "limit": limit, "items": [row_out(t, notes_all.get(t.ticket), flags.get(t.ticket)) for t in page],
                "tags": await c.notes.tag_counts(acct["account_id"]), "totals": {"net": round(sum(t.net for t in ts), 2), "n": len(ts)}}

    @app.get("/journal/{account_id}/discipline", tags=["journal"])
    async def disc_ep(request: Request, account_id: str, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, tz: Optional[str] = None,
                      symbol: Optional[str] = Query(None, max_length=32), group: Optional[str] = Query(None, max_length=40),
                      revenge_gap_min: int = Query(30, ge=1, le=1440), size_up_ratio: float = Query(1.5, ge=1.0, le=10.0),
                      max_trades_day: int = Query(10, ge=1, le=200), max_trades_hour: int = Query(5, ge=1, le=100),
                      daily_loss_limit_pct: float = Query(3.0, ge=0.1, le=100.0)):
        c = ctx(request)
        z = tz_of(tz)
        acct = await c.account(account_id)
        w = await c.window(acct, parse_when(frm, z), parse_when(to, z, end=True), symbol, group, None)
        params = {"revenge_gap_min": revenge_gap_min, "size_up_ratio": size_up_ratio, "max_trades_day": max_trades_day, "max_trades_hour": max_trades_hour,
                  "daily_loss_limit_pct": daily_loss_limit_pct}
        d = await c.run_discipline(acct, w["trades"], z, w["base"], params)
        return {"account_id": acct["account_id"], **{k: v for k, v in d.items() if k != "tickets"}, "n_analyzed_cap": MAX_ANALYZE,
                "note": "Phát hiện SAU KHI xảy ra (tự soi lại), không phải cảnh báo thời gian thực. Cửa sổ tin dùng tscommon.risk_windows."}

    @app.get("/journal/{account_id}/excursions", tags=["journal"])
    async def exc(request: Request, account_id: str, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, tz: Optional[str] = None,
                  symbol: Optional[str] = Query(None, max_length=32), limit: int = Query(50, ge=1, le=100)):
        c = ctx(request)
        z = tz_of(tz)
        acct = await c.account(account_id)
        w = await c.window(acct, parse_when(frm, z), parse_when(to, z, end=True), symbol, None, None)
        ts = sorted(w["trades"], key=lambda t: t.time_close)[-limit:]

        async def one(t: Trade):
            tf = excursions.pick_tf(t.hold_s)
            bars = await c.source.bars(t.symbol, tf, t.time_open - timedelta(seconds=excursions.TF_SECONDS[tf]), t.time_close + timedelta(seconds=1))
            e = excursions.excursion(t, bars, tf)
            if e is not None:
                e["spread_bps"] = await c.source.entry_spread_bps(t.symbol, t.time_open)
            return e

        res = await asyncio.gather(*[one(t) for t in ts], return_exceptions=True)
        items = [r for r in res if isinstance(r, dict)]
        sp = [r["spread_bps"] for r in items if r.get("spread_bps") is not None]
        return {"account_id": acct["account_id"], "requested": len(ts), "covered": len(items), "summary": {**excursions.summary(items), "avg_spread_bps": round(sum(sp) / len(sp), 3) if sp else None},
                "items": items, "note": "MAE/MFE xấp xỉ từ nến (khung nhỏ nhất phù hợp thời gian giữ lệnh); lệnh không có nến phủ thì bị bỏ qua."}

    @app.get("/journal/{account_id}/review", tags=["journal"])
    async def review_ep(request: Request, account_id: str, week: Optional[str] = Query(None, pattern=r"^\d{4}-W\d{2}$"), tz: Optional[str] = None):
        c = ctx(request)
        z = tz_of(tz)
        acct = await c.account(account_id)
        label = week or stats.iso_week_label(datetime.now(timezone.utc), z)
        try:
            a, b = stats.week_range(label, z)
        except ValueError:
            raise HTTPException(422, "tuần không hợp lệ") from None
        rows, base, _ = await c.all_rows(acct)
        pa, pb = a - timedelta(days=7), a
        cur = [t for t in rows if t.kind == "trade" and a <= t.time_close < b]
        prev = [t for t in rows if t.kind == "trade" and pa <= t.time_close < pb]
        events = await c.source.calendar_events(a - timedelta(days=1), b + timedelta(days=1)) if cur else []
        notes_ = await c.notes.list(acct["account_id"])
        wk_refs = {t.ticket for t in cur}
        notes_ = [n for n in notes_ if (n["kind"] == "deal" and n["ref"] in wk_refs) or (n["kind"] == "week" and n["ref"] == label)]
        out = review.weekly(label, z, cur, prev, events=events, rw_cfg=c.rw_cfg, params=c.disc_cfg(acct, None), base_equity=base, notes=notes_)
        out["range"] = {"from": a.isoformat(), "to": b.isoformat()}
        return {"account_id": acct["account_id"], **out}

    @app.get("/journal/{account_id}/notes", tags=["journal"])
    async def list_notes(request: Request, account_id: str, kind: Optional[str] = Query(None, pattern="^(deal|week|day)$"), tag: Optional[str] = Query(None, max_length=32)):
        c = ctx(request)
        acct = await c.account(account_id)
        return {"items": [{**n, "updated_at": _iso(n["updated_at"])} for n in await c.notes.list(acct["account_id"], kind, tag)], "tags": await c.notes.tag_counts(acct["account_id"])}

    def _check_ref(kind: str, ref: str) -> None:
        if kind not in KINDS or not REF_RE[kind].match(ref):
            raise HTTPException(422, "kind/ref không hợp lệ")

    @app.put("/journal/{account_id}/notes/{kind}/{ref}", tags=["journal"])
    async def put_note(request: Request, account_id: str, kind: str, ref: str, body: NoteIn):
        c = ctx(request)
        _check_ref(kind, ref)
        acct = await c.account(account_id)
        if kind == "deal":
            rows, _, _ = await c.all_rows(acct)
            if not any(t.ticket == ref and t.kind == "trade" for t in rows):
                raise HTTPException(404, "không có deal này")
        try:
            n = await c.notes.put(acct["account_id"], kind, ref, body)
        except LimitReached as e:
            raise HTTPException(422, str(e)) from None
        NOTE_WRITES.labels("put").inc()
        return {**n, "updated_at": _iso(n["updated_at"])}

    @app.delete("/journal/{account_id}/notes/{kind}/{ref}", tags=["journal"])
    async def del_note(request: Request, account_id: str, kind: str, ref: str):
        c = ctx(request)
        _check_ref(kind, ref)
        acct = await c.account(account_id)
        if not await c.notes.delete(acct["account_id"], kind, ref):
            raise HTTPException(404, "không có ghi chú này")
        NOTE_WRITES.labels("delete").inc()
        return {"ok": True}

    return app
