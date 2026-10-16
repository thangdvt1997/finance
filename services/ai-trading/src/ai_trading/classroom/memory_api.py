"""Route Bộ nhớ của AI (hợp đồng: docs/handoff/MEMORY_API.md). Module riêng, đăng ký bằng register(app, st, store, llm). CHỈ nghiên cứu/paper."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import memory as M
from .api import NOSTORE, RID, ROLES, UID, Who, _Limiter, _disp
from .memory import Memory, MemoryError_


def register(app: FastAPI, st: Any, store: Any, llm: Any = None) -> Memory:
    mem = Memory(store, llm)
    M.SVC = mem
    write_rl = _Limiter(getattr(st, "class_write_rate", 60), 60.0)

    from . import rooms_trash as _rt      # hook thùng rác: "xoá cả những gì AI đã học từ phòng này"

    def _on_room_gone(rid: str, forget: bool) -> None:
        mem.on_room_trashed(rid, bool(forget))
    _on_room_gone._mem = True   # type: ignore[attr-defined]
    for lst in (_rt.ON_TRASH, _rt.ON_PURGE):
        lst[:] = [h for h in lst if not getattr(h, "_mem", False)]
        lst.append(_on_room_gone)

    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def wwho(request: Request) -> Who:
        w = who(request)
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        return w

    def j(data: Any, code: int = 200, headers: dict | None = None) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers={**NOSTORE, **(headers or {})})

    def err(e: MemoryError_) -> JSONResponse:
        body: dict = {"detail": e.detail}
        if e.reason:
            body["reason"] = e.reason
        return j(body, e.code)

    def room_of(rid: str, w: Who) -> dict:
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            raise HTTPException(404, "không tìm thấy phòng")
        return r

    def item(r: dict, w: Who) -> dict:
        return mem.view(r, w)

    # ---- danh sách / thêm
    @app.get("/class/memory", tags=["class-memory"])
    async def mem_list(request: Request, type: str | None = None, room: str | None = None, author: str | None = None, status: str | None = None, scope: str | None = None,
                       topic: str | None = None, q: str | None = None, pinned: int = 0, history: int = 0, limit: int = 50, offset: int = 0, sort: str = "updated"):
        w = who(request)
        if (type and type not in M.TYPES) or (status and status not in M.STATUSES) or (scope and scope not in ("scenario", "expert")) or (room and not RID.match(room)) or (author and not UID.match(author)):
            raise HTTPException(422, "tham số lọc không hợp lệ")
        return j(mem.list(w, type=type, room=room, author=author, status=status, scope=scope, topic=topic, q=(q or "")[:200] or None, pinned=bool(pinned),
                          history=bool(history), limit=limit, offset=max(0, offset), sort=sort))

    @app.post("/class/memory", tags=["class-memory"], status_code=201)
    async def mem_add(request: Request, body: dict):
        w = wwho(request)
        rid = body.get("room_id") or None
        if rid:
            room_of(rid, w)
        data = body.get("data")
        try:
            r, info = mem.add(w, type=str(body.get("type", "")), text=body.get("text"), topic=str(body.get("topic", "general")), data=data if isinstance(data, dict) else {},
                              room_id=rid, scope=str(body.get("scope", "scenario")), importance=body.get("importance") if body.get("importance") in ("critical", "minor") else None,
                              confidence=0.9, status="confirmed", event="create")
        except MemoryError_ as e:
            return err(e)
        store.audit(w.uid, w.role, rid, "memory.create", r["id"])
        warns = [f"trùng với {r['id']}: đã hợp nhất"] if info["merged"] else []
        cf = mem.conflict_view(info["conflict"], w) if info["conflict"] else None
        return j({"item": item(r, w), "warnings": warns, "conflict": cf}, 201)

    # ---- mâu thuẫn / thống kê / xuất nhập (đặt TRƯỚC memory/{id})
    @app.get("/class/memory/conflicts", tags=["class-memory"])
    async def mem_conflicts(request: Request, status: str = "open", room: str | None = None):
        w = who(request)
        if status not in ("open", "resolved") or (room and not RID.match(room)):
            raise HTTPException(422, "tham số không hợp lệ")
        out = []
        for c in store.q("SELECT * FROM class_memory_conflict WHERE status=? ORDER BY created_at DESC LIMIT 200", (status,)):
            c = dict(c)
            if room and c["room_id"] != room:
                continue
            v = mem.conflict_view(c, w)
            if v["a"] and v["b"] and (w.master or (mem.can_see(mem._row(c["a_id"]), w) and mem.can_see(mem._row(c["b_id"]), w))):
                out.append(v)
        return j({"items": out, "total": len(out)})

    @app.post("/class/memory/conflicts/{cid}/resolve", tags=["class-memory"])
    async def mem_resolve(request: Request, cid: str, body: dict):
        w = wwho(request)
        if not cid.startswith("c_") or len(cid) > 40:
            raise HTTPException(404, "không có mâu thuẫn mở này")
        try:
            c = mem.resolve(cid, w, str(body.get("choice", "")), body.get("text"), body.get("note"))
        except MemoryError_ as e:
            return err(e)
        store.audit(w.uid, w.role, c["room_id"], "memory.resolve", cid)
        ids = [c["a_id"], c["b_id"]]
        return j({"conflict": mem.conflict_view(c, w), "items": [item(r, w) for i in ids if (r := mem._row(i))]})

    @app.get("/class/memory/stats", tags=["class-memory"])
    async def mem_stats(request: Request):
        return j(mem.stats(who(request)))

    @app.get("/class/memory/export", tags=["class-memory"])
    async def mem_export(request: Request):
        w = who(request)
        d = mem.export(w)
        store.audit(w.uid, w.role, None, "memory.export", f"n={len(d['items'])}")
        return j(d, headers={"Content-Disposition": 'attachment; filename="ai-memory.json"'})

    @app.post("/class/memory/import", tags=["class-memory"])
    async def mem_import(request: Request, body: dict):
        w = wwho(request)
        try:
            r = mem.import_items(w, body.get("items"), bool(body.get("dry_run", True)))
        except MemoryError_ as e:
            return err(e)
        store.audit(w.uid, w.role, None, "memory.import" + (".dry" if body.get("dry_run", True) else ""), f"n={r['imported']}")
        return j(r)

    # ---- một bản ghi
    @app.get("/class/memory/{mid}", tags=["class-memory"])
    async def mem_get(request: Request, mid: str):
        w = who(request)
        try:
            r = mem.get(mid, w)
        except MemoryError_ as e:
            return err(e)
        src = None
        if r["src_room"] and r["src_msg"]:
            try:
                m = store.message(r["src_room"], r["src_msg"]) if (w.master or store.is_member(r["src_room"], w.uid)) else None
            except Exception:  # noqa: BLE001
                m = None
            if m:
                src = {"id": m["id"], "author": (m.get("author") or {}).get("name") if isinstance(m.get("author"), dict) else m.get("author"), "text": (m.get("text") or "")[:600], "created_at": m.get("created_at")}
        rooms: dict = {}
        return j({"item": mem.view(r, w, rooms), "history": mem.history(mid), "versions": [mem.view(v, w, rooms) for v in mem.versions(r)], "source_message": src})

    @app.patch("/class/memory/{mid}", tags=["class-memory"])
    async def mem_patch(request: Request, mid: str, body: dict):
        w = wwho(request)
        data = body.get("data")
        try:
            new, old = mem.edit(mid, w, body.get("text"), data if isinstance(data, dict) else None, body.get("topic"), body.get("scope"), str(body.get("reason") or ""))
        except MemoryError_ as e:
            return err(e)
        store.audit(w.uid, w.role, new["room_id"], "memory.edit", new["id"])
        return j({"item": item(new, w), "previous": item(old, w)})

    @app.delete("/class/memory/{mid}", tags=["class-memory"])
    async def mem_delete(request: Request, mid: str, hard: int = 0):
        w = wwho(request)
        try:
            r = mem.get(mid, w)
            mem.delete(mid, w, bool(hard))
        except MemoryError_ as e:
            return err(e)
        store.audit(w.uid, w.role, r["room_id"], "memory.delete" + (".hard" if hard else ""), mid)
        return j({"ok": True, "id": mid})

    def act(name: str, fn):
        async def h(request: Request, mid: str, body: dict | None = None):
            w = wwho(request)
            try:
                r = fn(mid, w, body or {})
            except MemoryError_ as e:
                return err(e)
            store.audit(w.uid, w.role, r["room_id"], "memory." + name, mid)
            return j({"item": item(r, w)})
        h.__name__ = "mem_" + name
        app.post(f"/class/memory/{{mid}}/{name}", tags=["class-memory"])(h)

    act("confirm", lambda mid, w, b: mem.confirm(mid, w))
    act("reject", lambda mid, w, b: mem.reject(mid, w, str(b.get("reason") or "")))
    act("pin", lambda mid, w, b: mem.pin(mid, w, bool(b.get("pinned", True))))
    act("lock", lambda mid, w, b: mem.lock(mid, w, bool(b.get("locked", True))))
    act("revoke", lambda mid, w, b: mem.revoke(mid, w, str(b.get("reason") or "")))

    # ---- theo phòng
    @app.post("/class/rooms/{rid}/memory/extract", tags=["class-memory"])
    async def mem_extract(request: Request, rid: str, body: dict):
        w = wwho(request)
        room_of(rid, w)
        msgs = body.get("messages")
        if isinstance(msgs, list):
            pairs = [(str(m.get("text", "")), str(m.get("id") or "") or None) for m in msgs[:8] if isinstance(m, dict)]
        else:
            pairs = [(body.get("text"), body.get("message_id"))]
        if not pairs or any(not isinstance(t, str) or not t.strip() or len(t) > 3000 for t, _ in pairs):
            raise HTTPException(422, "text: 1-3000 ký tự")
        agg: dict = {"created": [], "merged": [], "conflicts": [], "cards": [], "notice": "", "skipped": [], "used_llm": False}
        try:
            for t, mid in pairs:
                r = mem.extract(w, rid, t, mid, body.get("ai_reply"))
                for k in ("created", "merged", "conflicts", "cards", "skipped"):
                    agg[k] += r[k]
                agg["used_llm"] = agg["used_llm"] or r["used_llm"]
        except MemoryError_ as e:
            return err(e)
        agg["created"] = [item(r, w) for r in agg["created"]]
        agg["conflicts"] = [mem.conflict_view(c, w) for c in agg["conflicts"]]
        agg["notice"] = f"Đã ghi nhớ {len(agg['created'])} điều" if agg["created"] else ""
        store.audit(w.uid, w.role, rid, "memory.extract", f"n={len(agg['created'])}")
        return j(agg)

    @app.get("/class/rooms/{rid}/memory/retrieve", tags=["class-memory"])
    async def mem_retrieve(request: Request, rid: str, q: str = "", k: int = 5, budget: int = M.BUDGET_TOKENS):
        w = who(request)
        room_of(rid, w)
        r = mem.retrieve(rid, w.uid, q[:300], k=max(1, min(k, 12)), budget=max(50, min(budget, 2000)), mark=False)
        rooms: dict = {}
        r["items"] = [{"item": mem.view(o["row"], w, rooms), "score": o["score"], "why": o["why"]} for o in r["items"]]
        return j(r)

    return mem
