"""REST bo loc rui ro tin: GET /v1/risk-windows?symbol= va /v1/risk-windows/status.

Logic tinh o `tscommon.risk_windows` (ham thuan, dung chung voi news-collector de alert va API luon nhat quan);
module nay chi doc lich tu repo (calendar_events — gateway duoc phep doc DB) va dinh dang ket qua. Cau hinh: risk_windows.yaml
(mac dinh trong tscommon; ghi de bang env RISK_WINDOWS_CONFIG).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from tscommon.risk_windows import load_config, risk_state

from .calendar_view import hide_superseded

SYMBOL_RE = r"^[A-Za-z0-9:._\-]{1,32}$"
_cfg: dict | None = None


def config() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


class RiskEvent(BaseModel):
    event_id: str
    source: str
    title: str
    country: str | None = None
    impact: str | None = None
    ts: datetime
    window_start: datetime
    window_end: datetime
    phase: str                       # scheduled | imminent | active | past
    minutes_to_event: int
    minutes_to_start: int
    minutes_to_end: int
    group: str | None = None


class NextWindow(BaseModel):
    start: datetime
    minutes_to_start: int
    title: str


class RiskState(BaseModel):
    symbol: str
    now: datetime
    state: str                       # active | imminent | clear
    in_window: bool
    currencies: list[str]
    window_start: datetime | None = None
    window_end: datetime | None = None
    minutes_to_end: int | None = None      # khi active: con bao nhieu phut het cua so
    minutes_to_start: int | None = None    # khi imminent: con bao nhieu phut thi vao cua so
    current: list[RiskEvent]
    upcoming: list[RiskEvent]
    next_window: NextWindow | None = None


class RiskSymbols(BaseModel):
    generated_at: datetime
    horizon_hours: float
    symbols: list[RiskState]


class RiskStatus(BaseModel):
    generated_at: datetime
    any_active: bool
    active_symbols: list[str]
    imminent_symbols: list[str]
    clear_symbols: int
    active_events: list[RiskEvent]
    next_window: dict[str, Any] | None = None
    config: dict[str, Any]


async def load_events(repo, now: datetime, horizon_h: float) -> list[dict]:
    """Su kien HIGH tu 3 gio truoc (cua so con keo dai) toi horizon+gio sau; an hang chinh thuc trung voi hang FF."""
    rows = await repo.calendar(now - timedelta(hours=3), now + timedelta(hours=horizon_h + 1), ["high"], 1000, 0,
                               order="asc", now=now)
    return hide_superseded(list(rows))


async def universe(repo) -> list[str]:
    syms = list(config().get("universe", []))
    try:
        syms += [r["symbol"] for r in await repo.symbols()]
    except Exception:  # noqa: BLE001 - DB loi khong lam hong API rui ro; dung danh sach cau hinh
        pass
    return sorted(dict.fromkeys(syms))


def register_risk_routes(api: APIRouter, get_repo: Callable) -> None:
    """Gan 2 route vao router /v1 da co auth (goi trong create_app truoc include_router)."""

    @api.get("/risk-windows", response_model=RiskState | RiskSymbols,
             summary="Cua so rui ro tin (T-15..T+30 quanh su kien HIGH) theo symbol: hien tai + sap toi 24h")
    async def risk_windows(request: Request,
                           symbol: Annotated[str | None, Query(pattern=SYMBOL_RE, description="Bo trong = moi symbol")] = None,
                           horizon_hours: Annotated[float, Query(ge=1, le=168, description="Cua so 'sap toi'")] = 24,
                           symbols: Annotated[str | None, Query(max_length=1024, description="Loc: danh sach symbol cach nhau dau phay (chi khi bo trong `symbol`)")] = None,
                           state: Annotated[str | None, Query(max_length=64, description="Loc: active,imminent,clear (cach nhau dau phay). Vi du state=active,imminent -> payload nho")] = None):
        repo = get_repo(request)
        now = datetime.now(timezone.utc)
        cfg = config()
        events = await load_events(repo, now, horizon_hours)
        if symbol:
            return risk_state(events, symbol, now, cfg, horizon_hours)
        syms = await universe(repo)
        if symbols:   # RS-4: loc phia may chu de client chi tai ma can (khong doi hop dong: bo trong = nhu cu)
            want = {x.strip() for x in symbols.split(",") if x.strip()}
            syms = [x for x in syms if x in want]
        out = [risk_state(events, s, now, cfg, horizon_hours) for s in syms]
        if state:
            ok = {x.strip() for x in state.split(",") if x.strip()}
            out = [o for o in out if o["state"] in ok]
        return {"generated_at": now, "horizon_hours": horizon_hours, "symbols": out}

    @api.get("/risk-windows/status", response_model=RiskStatus,
             summary="Tong quan: symbol nao dang/sap trong cua so rui ro, cua so ke tiep, cau hinh dang dung")
    async def risk_status(request: Request):
        repo = get_repo(request)
        now = datetime.now(timezone.utc)
        cfg = config()
        events = await load_events(repo, now, 24)
        syms = await universe(repo)
        states = [risk_state(events, s, now, cfg, 24) for s in syms]
        active = [s for s in states if s["state"] == "active"]
        imminent = [s for s in states if s["state"] == "imminent"]
        seen, act_events = set(), []
        for s in active:
            for e in s["current"]:
                k = (e["source"], e["event_id"])
                if e["phase"] == "active" and k not in seen:
                    seen.add(k)
                    act_events.append(e)
        nxt = None
        for s in states:
            n = s["next_window"]
            if n and (nxt is None or n["start"] < nxt["start"]):
                nxt = {**n, "symbols": []}
        if nxt:
            nxt["symbols"] = [s["symbol"] for s in states if s["next_window"] and s["next_window"]["start"] == nxt["start"]]
        return {"generated_at": now, "any_active": bool(active), "active_symbols": [s["symbol"] for s in active],
                "imminent_symbols": [s["symbol"] for s in imminent],
                "clear_symbols": len(states) - len(active) - len(imminent), "active_events": act_events, "next_window": nxt,
                "config": {"impacts": cfg["impacts"], "default": cfg["default"], "overrides": cfg.get("overrides", []),
                           "ignore_title_any": cfg.get("ignore_title_any", []), "universe": cfg.get("universe", [])}}
