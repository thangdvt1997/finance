"""API của ứng dụng client: giới hạn/mục tiêu, trung tâm thông báo, cài đặt đồng bộ thiết bị, thiết bị push, ticket báo quản trị.

Danh tính chỉ từ header X-Owner-* do api-gateway dựng (xem scope.py). Mọi truy vấn lọc theo chủ sở hữu; tài khoản không thuộc phiên -> 404 đồng nhất.
`/internal/notifications` chỉ dành cho service nội bộ (KHÔNG whitelist ở gateway/nginx)."""
from __future__ import annotations

import hmac
import json
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator

from .client_store import Conflict2, RateLimited
from .limits import SPEC, LimitError, progress_for, validate
from .models import SYMBOL_RE
from .notifications import KINDS, SEVERITIES, clean_link
from .scope import ACC_RE, FORBIDDEN, Scope, require_user, scope_dep

NOT_FOUND = "không tìm thấy"
MAX_PREFS_BYTES = 8 * 1024
PREF_KEYS = ("lang", "theme", "density", "tz", "num", "notif", "watchlist", "layout")
TICKET_CATEGORIES = ("ea_disconnected", "stale_data", "wrong_data", "other")
TICKET_MAX_PER_HOUR = 5
CTX_KEYS = {"ea_state": str, "age_s": (int, float), "latency_ms": (int, float)}

AccQ = Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:\-]{1,64}$")]


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LimitPut(_S):
    account_id: str = Field(pattern=r"^[A-Za-z0-9_.:\-]{1,64}$")
    key: str = Field(max_length=32)
    value: StrictInt | StrictFloat | None = None


class ReadBody(_S):
    ids: list[Annotated[int, Field(ge=1, le=2**62)]] | None = Field(default=None, max_length=200)
    all: StrictBool = False


class InternalNotif(_S):
    owner_user_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{2,64}$")
    owner_user_ids: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{2,64}$")]] | None = Field(default=None, max_length=200)
    kind: str
    severity: str = "info"
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    account_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:\-]{1,64}$")
    link: str | None = Field(default=None, max_length=140)
    dedupe_key: str | None = Field(default=None, max_length=120)
    push: StrictBool = True

    @field_validator("kind")
    @classmethod
    def _k(cls, v):
        if v not in KINDS:
            raise ValueError("kind không hợp lệ")
        return v

    @field_validator("severity")
    @classmethod
    def _s(cls, v):
        if v not in SEVERITIES:
            raise ValueError("severity không hợp lệ")
        return v


class PrefsPut(_S):
    rev: int = Field(ge=0, le=2**31 - 1)
    data: dict[str, Any]


class TicketIn(_S):
    account_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:\-]{1,64}$")
    category: str
    message: str = Field(default="", max_length=1000)
    context: dict[str, Any] | None = None

    @field_validator("category")
    @classmethod
    def _c(cls, v):
        if v not in TICKET_CATEGORIES:
            raise ValueError("category không hợp lệ")
        return v


class TicketUpdate(_S):
    status: str
    reply: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v not in ("open", "ack", "resolved"):
            raise ValueError("status không hợp lệ")
        return v


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _depth_ok(v, d=0) -> bool:
    if d > 6:
        return False
    if isinstance(v, dict):
        return len(v) <= 50 and all(isinstance(k, str) and len(k) <= 64 and _depth_ok(x, d + 1) for k, x in v.items())
    if isinstance(v, list):
        return len(v) <= 200 and all(_depth_ok(x, d + 1) for x in v)
    return v is None or isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 500)


def validate_prefs(data: dict) -> dict:
    """Khoá cấp 1 theo whitelist; kiểu cơ bản; kích thước <= 8KB. Ném HTTPException(422) khi sai."""
    bad = [k for k in data if k not in PREF_KEYS]
    if bad:
        raise HTTPException(422, "khoá cài đặt không được hỗ trợ")
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_PREFS_BYTES:
        raise HTTPException(413, "cài đặt quá lớn (tối đa 8KB)")
    if not _depth_ok(data):
        raise HTTPException(422, "cài đặt không hợp lệ")
    for k in ("lang", "theme", "density", "tz", "num"):
        if k in data and not (isinstance(data[k], str) and len(data[k]) <= 40):
            raise HTTPException(422, f"{k} không hợp lệ")
    if "notif" in data:
        n = data["notif"]
        if not isinstance(n, dict) or any(k not in KINDS or not isinstance(v, dict) or set(v) - {"app", "push"} or any(not isinstance(x, bool) for x in v.values())
                                          for k, v in n.items()):
            raise HTTPException(422, "notif không hợp lệ")
    if "watchlist" in data:
        w = data["watchlist"]
        def _syms_ok(a) -> bool:
            return isinstance(a, list) and len(a) <= 100 and all(isinstance(s, str) and re.fullmatch(SYMBOL_RE, s) for s in a)

        if isinstance(w, dict):  # định dạng nhiều nhóm của client-ui: {active, groups:[{id,name,symbols}]}
            gs = w.get("groups")
            ok = (isinstance(gs, list) and 1 <= len(gs) <= 8 and isinstance(w.get("active", ""), str)
                  and all(isinstance(g, dict) and isinstance(g.get("id", ""), str) and len(g.get("id", "")) <= 16
                          and isinstance(g.get("name", ""), str) and len(g.get("name", "")) <= 40 and _syms_ok(g.get("symbols", [])) for g in gs))
        else:
            ok = _syms_ok(w)  # định dạng cũ: danh sách phẳng
        if not ok:
            raise HTTPException(422, "watchlist không hợp lệ")
    return data


def _check_acc(sc: Scope, account_id: str) -> None:
    if not ACC_RE.match(account_id) or account_id not in sc.accounts:
        raise HTTPException(404, NOT_FOUND)


def _client(sc: Scope) -> str:
    if not sc.is_client:
        raise HTTPException(403, FORBIDDEN)
    return sc.user_id


def notif_out(n: dict) -> dict:
    return {"id": n["id"], "kind": n["kind"], "severity": n["severity"], "title": n["title"], "body": n["body"], "account_id": n["account_id"],
            "link": n["link"], "ts": _iso(n["ts"]), "read": n["read_at"] is not None}


def ticket_out(t: dict, master: bool) -> dict:
    o = {"id": t["id"], "account_id": t["account_id"], "category": t["category"], "message": t["message"],
         "context": t["context"] if isinstance(t["context"], dict) else json.loads(t["context"] or "{}"), "status": t["status"], "reply": t["reply"],
         "created_at": _iso(t["created_at"]), "updated_at": _iso(t["updated_at"])}
    if master:
        o["owner_user_id"] = t["owner_user_id"]
        o["handled_by"] = t["handled_by"]
    return o


def install(app) -> None:
    r = APIRouter()

    def now_of(request: Request) -> datetime:
        return datetime.fromtimestamp(request.app.state.clock(), timezone.utc)

    # ------------------------------------------------------------------ (1) giới hạn & mục tiêu
    @r.get("/limits")
    async def limits_get(request: Request, account_id: AccQ):
        sc = scope_dep(request)
        store, now = request.app.state.store, now_of(request)
        if sc.is_client:
            _check_acc(sc, account_id)
            await store.limits_sweep(sc.user_id, sc.accounts)
        owner = sc.owner
        await store.limits_apply_due(now, owner, account_id)
        items = await store.limits_get(owner, account_id)
        metrics = await request.app.state.watcher.metrics(account_id, now) if items else None
        progress = {i["key"]: progress_for(i["key"], i["value"], metrics, now) for i in items}
        return {"account_id": account_id, "now": now.isoformat(),
                "items": [{**i, "pending_effective_at": _iso(i["pending_effective_at"]), "updated_at": _iso(i["updated_at"])} for i in items], "progress": progress}

    @r.put("/limits")
    async def limits_put(body: LimitPut, request: Request):
        sc = scope_dep(request)
        owner = _client(sc)                       # master/service chỉ đọc: không đặt hộ giới hạn của client
        _check_acc(sc, body.account_id)
        try:
            value = validate(body.key, body.value)
        except LimitError as e:
            raise HTTPException(422, str(e)) from None
        d = await request.app.state.store.limits_set(owner, body.account_id, body.key, value, now_of(request), "client")
        return {"key": body.key, "applied": d.applied, "value": d.value, "pending_value": d.pending_value, "pending_remove": d.pending_remove,
                "effective_at": _iso(d.effective_at)}

    @r.get("/limits/history")
    async def limits_history(request: Request, account_id: AccQ, limit: Annotated[int, Query(ge=1, le=200)] = 50):
        sc = scope_dep(request)
        if sc.is_client:
            _check_acc(sc, account_id)
        rows = await request.app.state.store.limits_history(sc.owner, account_id, limit)
        return {"account_id": account_id, "items": [{"key": h["key"], "ts": _iso(h["ts"]), "by": h["actor_role"], "old_value": h["old_value"],
                                                     "new_value": h["new_value"], "applied": h["applied"], "effective_at": _iso(h["effective_at"])} for h in rows]}

    # ------------------------------------------------------------------ (2) thông báo
    @r.get("/notifications")
    async def notif_get(request: Request, kind: Annotated[str | None, Query(pattern=r"^(rule|limit|report|briefing|support|system)$")] = None,
                        unread: Annotated[int, Query(ge=0, le=1)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 30,
                        before: Annotated[int | None, Query(ge=1, le=2**62)] = None):
        uid = require_user(scope_dep(request))
        items, n = await request.app.state.store.notif_list(uid, kind, bool(unread), limit, before)
        return {"items": [notif_out(x) for x in items], "unread": n}

    @r.post("/notifications/read")
    async def notif_read(body: ReadBody, request: Request):
        uid = require_user(scope_dep(request))
        if not body.all and not body.ids:
            raise HTTPException(422, "cần ids hoặc all")
        n = await request.app.state.store.notif_mark_read(uid, None if body.all else body.ids, now_of(request))
        _, unread = await request.app.state.store.notif_list(uid, None, False, 1, None)
        return {"marked": n, "unread": unread}

    @r.post("/internal/notifications", status_code=201)
    async def internal_notify(body: InternalNotif, request: Request):
        """Cho service khác (reporter/briefing...) phát thông báo cho 1 hoặc nhiều chủ sở hữu. CHỈ mạng nội bộ; từ chối nếu đi qua gateway (có header X-Owner-*)."""
        if any(h.lower().startswith("x-owner-") for h in request.headers):
            raise HTTPException(403, FORBIDDEN)
        tok = os.getenv("NOTIFY_INTERNAL_TOKEN", "")
        if tok and not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {tok}"):
            raise HTTPException(403, FORBIDDEN)
        owners = [*([body.owner_user_id] if body.owner_user_id else []), *(body.owner_user_ids or [])]
        if not owners:
            raise HTTPException(422, "cần owner_user_id hoặc owner_user_ids")
        n = 0
        for o in dict.fromkeys(owners):
            if await request.app.state.notifier.send(o, body.kind, body.severity, body.title, body.body, body.account_id, clean_link(body.link),
                                                      body.dedupe_key, body.push) is not None:
                n += 1
        return {"created": n}

    # ------------------------------------------------------------------ (3) cài đặt đồng bộ + thiết bị push
    @r.get("/client-prefs")
    async def prefs_get(request: Request):
        uid = require_user(scope_dep(request))
        return await request.app.state.store.cprefs_get(uid)

    @r.put("/client-prefs")
    async def prefs_put(body: PrefsPut, request: Request):
        uid = require_user(scope_dep(request))
        data = validate_prefs(body.data)
        store = request.app.state.store
        try:
            return await store.cprefs_put(uid, body.rev, data)
        except Conflict2:
            cur = await store.cprefs_get(uid)
            return JSONResponse({"detail": "rev", **cur}, status_code=409)

    @r.get("/push/devices")
    async def devices(request: Request):
        uid = require_user(scope_dep(request))
        return [{**d, "created_at": _iso(d["created_at"]), "last_ok_at": _iso(d["last_ok_at"])} for d in await request.app.state.store.devices_list(uid)]

    @r.delete("/push/devices/{did}")
    async def device_del(did: str, request: Request):
        uid = require_user(scope_dep(request))
        if not re.fullmatch(r"[0-9a-f]{16}", did) or not await request.app.state.store.device_delete(uid, did):
            raise HTTPException(404, NOT_FOUND)
        return {"ok": True}

    # ------------------------------------------------------------------ (4) ticket
    @r.post("/tickets", status_code=201)
    async def ticket_create(body: TicketIn, request: Request):
        sc = scope_dep(request)
        uid = _client(sc)
        if body.account_id:
            _check_acc(sc, body.account_id)
        if body.category == "other" and len(body.message) < 3:
            raise HTTPException(422, "cần mô tả vấn đề")
        ctx = {k: v for k, v in (body.context or {}).items() if k in CTX_KEYS and isinstance(v, CTX_KEYS[k]) and not isinstance(v, bool)}
        if "ea_state" in ctx:
            ctx["ea_state"] = ctx["ea_state"][:32]
        try:
            t, merged = await request.app.state.store.ticket_create(uid, body.account_id, body.category, body.message, ctx, now_of(request), TICKET_MAX_PER_HOUR)
        except RateLimited:
            raise HTTPException(429, "báo quá nhiều lần, thử lại sau") from None
        out = {"id": t["id"], "status": t["status"]}
        if merged:
            return JSONResponse({**out, "merged": True}, status_code=200)
        return out

    @r.get("/tickets")
    async def ticket_list(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50):
        sc = scope_dep(request)
        rows = await request.app.state.store.ticket_list(sc.owner, limit)      # client: chỉ của mình; master/service: tất cả
        return {"items": [ticket_out(t, master=not sc.is_client) for t in rows]}

    @r.put("/tickets/{tid}")
    async def ticket_put(tid: str, body: TicketUpdate, request: Request):
        sc = scope_dep(request)
        if sc.is_client:
            raise HTTPException(403, FORBIDDEN)
        if not re.fullmatch(r"[0-9]{1,12}", tid):
            raise HTTPException(404, NOT_FOUND)
        now = now_of(request)
        t = await request.app.state.store.ticket_update(int(tid), body.status, body.reply, sc.user_id, now)
        if not t:
            raise HTTPException(404, NOT_FOUND)
        label = {"open": "đã mở lại", "ack": "đã được tiếp nhận", "resolved": "đã được xử lý"}[t["status"]]
        await request.app.state.notifier.send(t["owner_user_id"], "support", "info", f"Báo cáo của bạn {label}", t["reply"] or "", t["account_id"],
                                              dedupe_key=f"ticket:{t['id']}:{t['status']}:{int(now.timestamp())}")
        return ticket_out(t, master=True)

    app.include_router(r)


__all__ = ["install", "validate_prefs", "SPEC"]
