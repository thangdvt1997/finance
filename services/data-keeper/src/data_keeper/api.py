"""API data-keeper (K5): GET /v1/data/health, POST /v1/data/recheck, GET /v1/data/report/daily, GET /v1/data/decisions.

Gateway (datakeeper_routes.py) chỉ cho master gọi; service này còn nằm sau mạng nội bộ + X-Internal-Token (make_app(internal_auth=True)).
`build_router(ctx, llm)`: ctx là đối tượng của main.py (A1), kiểu duck-typing, mọi thuộc tính đều tuỳ chọn:
  ctx.db              asyncpg pool (đọc dk.coverage / dk.actions)
  ctx.matrix          ma trận mới nhất trong bộ nhớ {symbol:{tf:{last_bar,last_tick,gaps,status}}} (ưu tiên hơn DB)
  ctx.recheck()       coroutine kiểm kê lại ngay (trả ma trận hoặc None)
  ctx.enabled         cờ DATA_KEEPER_ENABLED
  ctx.queue_len()     coroutine/hàm trả độ dài dk.backfill_queue (tuỳ chọn)
ctx=None hoặc DATA_KEEPER_MOCK=1 -> dữ liệu giả để dựng UI.
Đầu ra KHÔNG chứa tên nguồn dữ liệu / tài khoản: nhật ký chỉ xuất khoá trong danh sách trắng, văn bản qua scrub_sources."""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .llm import LocalLLM, explain_action, make_facts, template_daily, template_diagnosis

log = logging.getLogger("data_keeper.api")

TF_ORDER = ["M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1"]
RANK = {"BROKEN": 3, "SLOW": 2, "OK": 1, "CLOSED": 0}
STATUS_OK = set(RANK)
_CRYPTO = {"BTC", "ETH", "LTC", "XRP", "BCH", "ADA", "DOT", "SOL", "DOGE", "BNB", "LINK", "XLM", "EOS", "DASH", "XMR", "TRX", "AVAX", "MATIC"}
_METAL = ("XAU", "XAG", "XPT", "XPD")
_CCY = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "TRY", "ZAR", "MXN", "SGD", "HKD", "CNH", "CNY", "RUB", "ILS", "THB", "INR", "KRW", "ARS", "GEL", "BRL", "CLP", "COP", "RON", "TWD", "IDR", "PHP", "SAR", "AED", "KES", "NGN", "EGP", "HRK", "BGN", "ISK", "UAH"}
GROUP_ORDER = ["Forex", "Kim loại", "Chỉ số", "Tiền số", "Khác"]


def group_of(sym: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", sym.upper())
    if s[:3] in _METAL:
        return "Kim loại"
    if s[:3] in _CRYPTO or s[:4] in _CRYPTO or (s.endswith(("USDT", "BTC")) and len(s) > 6):
        return "Tiền số"
    if len(s) == 6 and s[:3] in _CCY and s[3:] in _CCY:
        return "Forex"
    if re.search(r"\d", s) or s in {"DAX", "FTSE", "CAC", "NAS", "SPX", "DJI", "DJ30", "NDX", "US30", "US500", "UK100", "JP225", "VIX"} or not re.fullmatch(r"[A-Z]{6}", s):
        return "Chỉ số"
    return "Forex"


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc).isoformat()
    return str(v)


# --------------------------------------------------------------------------- tổng hợp (hàm thuần, dễ test)
def summarize(matrix: dict, now: datetime | None = None, gaps_filled_24h: int = 0, heal_24h: int = 0, backfill_queue: int = 0) -> dict:
    """matrix -> {summary, tfs, symbols[]}. Trạng thái mã = tồi nhất theo khung (BROKEN>SLOW>OK>CLOSED); CLOSED chỉ khi mọi khung đều CLOSED."""
    syms, tfs_seen = [], set()
    for sym in sorted(matrix):
        cells = {}
        for tf, c in (matrix[sym] or {}).items():
            st = str(c.get("status") or "OK").upper()
            st = st if st in STATUS_OK else "OK"
            tfs_seen.add(tf)
            g = c.get("gaps")
            cells[tf] = {"s": st, "bar": _iso(c.get("last_bar")), "tick": _iso(c.get("last_tick")), "g": int(g) if isinstance(g, (int, float)) else 0}
        if not cells:
            continue
        sts = {c["s"] for c in cells.values()}
        if "BROKEN" in sts:
            st = "BROKEN"
        elif "SLOW" in sts:
            st = "SLOW"
        elif sts == {"CLOSED"}:
            st = "CLOSED"
        else:
            st = "OK"
        ticks = [c["tick"] for c in cells.values() if c["tick"]]
        syms.append({"symbol": sym, "group": group_of(sym), "status": st, "gaps": sum(c["g"] for c in cells.values()),
                     "last_tick": max(ticks) if ticks else None, "tf": cells})
    tfs = [t for t in TF_ORDER if t in tfs_seen] + sorted(t for t in tfs_seen if t not in TF_ORDER)
    cnt = {k: sum(1 for s in syms if s["status"] == k) for k in RANK}
    silent_open = [s["symbol"] for s in syms if s["status"] in ("BROKEN", "SLOW") and not s["last_tick"]]
    summary = {"total": len(syms), "complete": cnt["OK"] + cnt["CLOSED"], "ok": cnt["OK"], "closed": cnt["CLOSED"], "slow": cnt["SLOW"], "broken": cnt["BROKEN"],
               "gaps_open": sum(s["gaps"] for s in syms), "gaps_filled_24h": int(gaps_filled_24h), "heal_actions_24h": int(heal_24h),
               "backfill_queue": int(backfill_queue), "tfs": len(tfs)}
    facts_raw = {**summary, "silent_open": silent_open,
                 "broken_symbols": [s["symbol"] for s in syms if s["status"] == "BROKEN"], "slow_symbols": [s["symbol"] for s in syms if s["status"] == "SLOW"],
                 "silent_closed": [s["symbol"] for s in syms if s["status"] == "CLOSED"]}
    return {"summary": summary, "tfs": tfs, "symbols": syms, "facts": make_facts(facts_raw)}


# --------------------------------------------------------------------------- truy cập dữ liệu
def mock_matrix(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    syms = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDMXN", "USDARS", "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "DE40", "UK100", "US500", "JP225", "FR40"]
    tfs = ["M1", "M5", "M15", "H1", "H4", "D1"]
    m: dict = {}
    for i, s in enumerate(syms):
        st = "CLOSED" if s in ("DE40", "UK100", "FR40") else "BROKEN" if s == "USDARS" else "SLOW" if s == "NZDMXN" else "OK"
        m[s] = {tf: {"last_bar": now - timedelta(minutes=1 + i), "last_tick": None if st == "CLOSED" else now - timedelta(seconds=2 + i), "gaps": 3 if st == "BROKEN" else 0,
                     "status": "OK" if (tf == "D1" and st == "SLOW") else st} for tf in tfs}
    return m


class Access:
    def __init__(self, ctx: Any = None):
        self.ctx = ctx
        self.mock = ctx is None or os.getenv("DATA_KEEPER_MOCK") == "1"

    async def matrix(self) -> tuple[dict, str | None]:
        if self.mock:
            return mock_matrix(), _iso(datetime.now(timezone.utc))
        m = getattr(self.ctx, "matrix", None)
        if m:
            return m, _iso(getattr(self.ctx, "matrix_at", None))
        db = getattr(self.ctx, "db", None)
        out: dict = {}
        upd = None
        if db is not None:
            rows = await db.fetch("SELECT * FROM dk.coverage")
            for r in rows:
                r = dict(r)
                out.setdefault(r["symbol"], {})[r.get("tf") or r.get("timeframe")] = {k: r.get(k) for k in ("last_bar", "last_tick", "gaps", "status")}
                u = r.get("updated_at")
                if u and (upd is None or u > upd):
                    upd = u
        return out, _iso(upd)

    async def counters(self) -> dict:
        res = {"gaps_filled_24h": 0, "heal_24h": 0, "backfill_queue": 0}
        if self.mock:
            return {"gaps_filled_24h": 41, "heal_24h": 5, "backfill_queue": 2}
        db = getattr(self.ctx, "db", None)
        if db is not None:
            try:
                rows = await db.fetch("SELECT kind, (status IN ('done','sent','ok')) AS ok, detail FROM dk.actions WHERE ts > now() - interval '24 hours'")
                for r in rows:
                    k = str(r["kind"])
                    d = r["detail"] if isinstance(r["detail"], dict) else {}
                    if k.startswith("backfill") and r["ok"] is not False:
                        n = d.get("filled", d.get("count", 0))
                        res["gaps_filled_24h"] += int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else 0
                    elif not k.startswith(("backfill", "recheck")):
                        res["heal_24h"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("đọc dk.actions lỗi: %s", type(e).__name__)
        q = getattr(self.ctx, "queue_len", None)
        if q:
            try:
                v = q()
                res["backfill_queue"] = int(await v if inspect.isawaitable(v) else v)
            except Exception:  # noqa: BLE001
                pass
        return res

    async def actions(self, limit: int) -> list[dict]:
        if self.mock:
            now = datetime.now(timezone.utc)
            return [{"ts": now - timedelta(minutes=5 * i), "kind": k, "symbol": s, "tf": tf, "ok": ok, "detail": {"filled": 12}} for i, (k, s, tf, ok) in
                    enumerate([("backfill", "EURUSD", "M1", True), ("resubscribe", "NZDMXN", None, False), ("skip_closed", "DE40", None, True), ("recheck", None, None, True)])][:limit]
        db = getattr(self.ctx, "db", None)
        if db is None:
            return []
        rows = await db.fetch("SELECT ts, kind, target AS symbol, NULL::text AS tf, (status IN ('done','sent','ok')) AS ok, detail FROM dk.actions ORDER BY ts DESC LIMIT $1", limit)
        return [dict(r) for r in rows]


def public_action(a: dict) -> dict:
    """Danh sách trắng: kind/symbol/tf/ok/count/ts + lời giải thích tất định. Không xuất detail thô (có thể chứa tên nguồn/tài khoản)."""
    d = a.get("detail") if isinstance(a.get("detail"), dict) else {}
    n = d.get("filled", d.get("count"))
    sym = a.get("symbol") if isinstance(a.get("symbol"), str) and re.fullmatch(r"[A-Za-z0-9._#&-]{2,24}", a.get("symbol") or "") else None
    out = {"ts": _iso(a.get("ts")), "kind": re.sub(r"[^a-z0-9_:]", "", str(a.get("kind") or "").lower())[:40].split(":")[0], "symbol": sym,
           "tf": a.get("tf") if a.get("tf") in TF_ORDER else None, "ok": a.get("ok") if isinstance(a.get("ok"), bool) else None,
           "count": int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else None}
    out["explain"] = explain_action(out)
    return out


# --------------------------------------------------------------------------- router
def build_router(ctx: Any = None, llm: LocalLLM | None = None) -> APIRouter:
    acc = Access(ctx)
    llm = llm or LocalLLM()
    r = APIRouter(prefix="/v1/data", tags=["data"])
    state: dict[str, Any] = {"diag": None, "diag_at": 0.0, "diag_key": None, "task": None, "last_recheck": 0.0, "report": None, "report_at": 0.0}
    DIAG_TTL, RECHECK_MIN_S, REPORT_TTL = 300.0, 20.0, 900.0
    REPORT_LLM_WAIT_S = float(os.getenv("DATA_KEEPER_REPORT_LLM_WAIT_S", "8"))

    async def snapshot() -> dict:
        m, upd = await acc.matrix()
        c = await acc.counters()
        s = summarize(m, gaps_filled_24h=c["gaps_filled_24h"], heal_24h=c["heal_24h"], backfill_queue=c["backfill_queue"])
        s["updated_at"] = upd
        return s

    async def _refresh_diag(facts: dict, key: str) -> None:
        try:
            d = await llm.diagnose(facts)
            state.update(diag=d, diag_at=time.monotonic(), diag_key=key)
        finally:
            state["task"] = None

    def diag_for(facts: dict) -> dict:
        from .llm import template_diagnosis
        key = repr(sorted((k, v) for k, v in facts.items() if not isinstance(v, list)))
        fresh = state["diag"] and state["diag_key"] == key and time.monotonic() - state["diag_at"] < DIAG_TTL
        if not fresh and state["task"] is None:
            state["task"] = asyncio.create_task(_refresh_diag(facts, key))     # LLM chậm: không chặn phản hồi, lần sau có kết quả
        if state["diag"] and state["diag_key"] == key:
            return state["diag"]
        return {**template_diagnosis(facts), "mode": "template"}

    @r.get("/health", summary="Phủ dữ liệu mã x khung + chẩn đoán (master)")
    async def health():
        s = await snapshot()
        diag = diag_for(s.pop("facts"))
        enabled = bool(getattr(ctx, "enabled", True)) if ctx is not None else True
        return {"generated_at": _iso(datetime.now(timezone.utc)), "enabled": enabled, "mock": acc.mock, **s, "groups": GROUP_ORDER, "diagnosis": diag}

    @r.post("/recheck", summary="Kiểm tra lại ngay (nhẹ, giới hạn tần suất)")
    async def recheck():
        now = time.monotonic()
        wait = RECHECK_MIN_S - (now - state["last_recheck"])
        if wait > 0:
            raise HTTPException(429, f"Vừa kiểm tra xong, thử lại sau {int(wait) + 1} giây")
        state["last_recheck"] = now
        fn = getattr(ctx, "recheck", None)
        if fn:
            try:
                v = fn()
                if inspect.isawaitable(v):
                    await asyncio.wait_for(v, 60)
            except Exception as e:  # noqa: BLE001
                log.warning("recheck lỗi: %s", type(e).__name__)
                raise HTTPException(502, "Không kiểm tra lại được, thử lại sau") from None
        s = await snapshot()
        s.pop("facts")
        return {"ok": True, "generated_at": _iso(datetime.now(timezone.utc)), "summary": s["summary"], "updated_at": s["updated_at"]}

    @r.get("/report/daily", summary="Báo cáo hằng ngày")
    async def report_daily(fresh: bool = Query(False)):
        if state["report"] and not fresh and time.monotonic() - state["report_at"] < REPORT_TTL:
            return state["report"]
        s = await snapshot()
        slow = False
        try:   # gateway cắt ở 15 s: LLM CPU có thể chạy > 100 s -> chờ tối đa REPORT_LLM_WAIT_S rồi trả bản mẫu tất định (đúng số), thử lại LLM sau 60 s
            rep = await asyncio.wait_for(llm.daily_report(s["facts"]), REPORT_LLM_WAIT_S)
        except asyncio.TimeoutError:
            slow = True
            rep = {"headline": template_daily(s["facts"]), "diagnosis": {**template_diagnosis(s["facts"]), "mode": "template"}, "mode": "template"}
        out = {"date": datetime.now(timezone(timedelta(hours=7))).date().isoformat(), "generated_at": _iso(datetime.now(timezone.utc)),
               "headline": rep["headline"], "diagnosis": rep["diagnosis"], "mode": rep["mode"], "summary": s["summary"]}
        state["report"], state["report_at"] = out, time.monotonic() - (REPORT_TTL - 60 if slow else 0.0)
        return out

    @r.get("/decisions", summary="Nhật ký quyết định có giải thích")
    async def decisions(limit: int = Query(50, ge=1, le=200)):
        rows = await acc.actions(limit)
        return {"items": [public_action(a) for a in rows], "count": len(rows)}

    return r


def facts_headline(facts: dict) -> str:
    """Câu báo cáo tất định (dùng cho thông báo hằng ngày ở heal/main)."""
    return template_daily(facts)
