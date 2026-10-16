"""Thùng rác phòng AI Training Class: xoá mềm / khôi phục / xoá vĩnh viễn (master) / xoá hàng loạt 2 bước / tự dọn sau N ngày.
Chỉ THÊM module + 1 dòng đăng ký trong app.py; hook vào store.room()/rooms_for() (lọc phòng đã vào thùng) là thay đổi tối thiểu duy nhất ở store.py.
Hợp đồng: docs/handoff/ROOMS_TRASH_API.md. Phòng trong thùng = 404 với mọi route cũ (IDOR đồng nhất)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import secrets
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .api import NOSTORE, RID, ROLES, UID, Who, _Limiter, _disp
from .store import now
from urllib.parse import unquote

MAX_BULK = 50
TOKEN_TTL = 300.0
REASON_MAX = 200
# Hook cho module khác (bộ nhớ AI, hồ sơ phương pháp): hàm(rid, forget_learned: bool). Lỗi hook không chặn thao tác.
ON_TRASH: list[Callable[[str, bool], None]] = []
ON_RESTORE: list[Callable[[str], None]] = []
ON_PURGE: list[Callable[[str, bool], None]] = []
# Bảng con theo room_id bị xoá khi purge (thứ tự không phụ thuộc: không dùng FK)
CHILD_TABLES = ("class_messages", "class_examples", "class_labels", "class_profile_versions", "class_profiles", "class_actions", "class_attachments", "class_members", "class_ux_confirm")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)


def register(app: FastAPI, st: Any, store: Any, sstore: Any = None) -> dict:
    days = int(getattr(st, "class_trash_days", 30) or 30)
    write_rl = _Limiter(getattr(st, "class_write_rate", 60), 60.0)
    prepared: dict[str, tuple[str, tuple[str, ...], float]] = {}

    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def j(data: Any, code: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers=NOSTORE)

    def wr(w: Who) -> None:
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")

    def trash_row(rid: str) -> dict | None:
        r = store.q("SELECT * FROM class_room_trash WHERE room_id=?", (rid,))
        return dict(r[0]) if r else None

    def counts(rid: str) -> dict:
        c = lambda sql: store.q(sql, (rid,))[0][0]  # noqa: E731
        return {"messages": c("SELECT COUNT(*) FROM class_messages WHERE room_id=?"), "examples": c("SELECT COUNT(*) FROM class_examples WHERE room_id=?"),
                "labels": c("SELECT COUNT(*) FROM class_labels WHERE room_id=?"), "versions": c("SELECT COUNT(*) FROM class_profile_versions WHERE room_id=?"),
                "attachments": c("SELECT COUNT(*) FROM class_attachments WHERE room_id=?")}

    def others_contributed(rid: str, owner: str) -> bool:
        for m in store.q("SELECT author FROM class_messages WHERE room_id=?", (rid,)):
            try:
                a = json.loads(m["author"])
            except Exception:
                continue
            if a.get("user_id") not in (owner, "ai", "system", None) and a.get("role") not in ("ai", "system"):
                return True
        return False

    def running_job(rid: str) -> bool:
        for a in store.q("SELECT job_id FROM class_actions WHERE room_id=? AND status IN ('queued','running')", (rid,)):
            if not a["job_id"]:
                return True
            jb = sstore.job(a["job_id"]) if sstore else None
            if jb and jb.get("status") in ("queued", "running"):
                return True
        return False

    def can_trash(rid: str, w: Who) -> tuple[dict | None, str | None]:
        """(phòng, lý do từ chối). 404 đồng nhất cho phòng không thấy được."""
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            return None, "không tìm thấy phòng"
        if not w.master:
            if r["created_by"] != w.uid:
                return r, "chỉ chủ phòng hoặc master được xoá phòng"
            if others_contributed(rid, w.uid):
                return r, "phòng có người khác đóng góp: chỉ master được xoá"
        if running_job(rid):
            return r, "phòng đang chạy tác vụ nền: chờ xong hoặc huỷ trước khi xoá"
        return r, None

    def do_trash(r: dict, w: Who, reason: str, forget: bool) -> dict:
        rid = r["id"]
        t = datetime.now(timezone.utc)
        store.x("INSERT OR IGNORE INTO class_room_trash(room_id,deleted_at,deleted_by,deleted_by_name,reason,forget_learned,purge_after) VALUES(?,?,?,?,?,?,?)",
                (rid, _iso(t), w.uid, w.name, reason or None, 1 if forget else 0, _iso(t + timedelta(days=days))))
        store.audit(w.uid, w.role, rid, "room.trash", (f"{r['title'][:80]} | " + reason)[:300])
        for h in ON_TRASH:
            try:
                h(rid, forget)
            except Exception:  # noqa: BLE001
                pass
        tr = trash_row(rid)
        return {"id": rid, "title": r["title"], "deleted_at": tr["deleted_at"], "purge_after": tr["purge_after"], "days": days}

    def trashed_visible(rid: str, w: Who) -> tuple[dict, dict]:
        r = store.room(rid, include_trashed=True) if RID.match(rid or "") else None
        tr = trash_row(rid) if r else None
        if not r or not tr:
            raise HTTPException(404, "không tìm thấy phòng trong thùng rác")
        if not w.master and not (store.is_member(rid, w.uid) and w.uid in (r["created_by"], tr["deleted_by"])):
            raise HTTPException(404, "không tìm thấy phòng trong thùng rác")
        return r, tr

    def item(r: dict, tr: dict) -> dict:
        left = max(0, (_parse(tr["purge_after"]) - datetime.now(timezone.utc)).days)
        return {"id": r["id"], "title": r["title"], "created_by": r["created_by"], "created_at": r["created_at"], "updated_at": r["updated_at"], "members": len(r["members"]),
                "deleted_at": tr["deleted_at"], "deleted_by": tr["deleted_by"], "deleted_by_name": tr["deleted_by_name"], "reason": tr["reason"],
                "forget_learned": bool(tr["forget_learned"]), "purge_after": tr["purge_after"], "days_left": left, "counts": counts(r["id"])}

    def purge_room(rid: str, w: Who | None, why: str) -> bool:
        tr = trash_row(rid)
        if not tr:
            return False
        r = store.room(rid, include_trashed=True)
        forget = bool(tr["forget_learned"])
        with store.room_lock(rid):
            with store._lock:                       # noqa: SLF001 (một giao dịch)
                store.db.execute("BEGIN")
                try:
                    for tb in CHILD_TABLES:
                        store.db.execute(f"DELETE FROM {tb} WHERE room_id=?", (rid,))  # noqa: S608 (tên bảng cố định)
                    store.db.execute("DELETE FROM class_rooms WHERE id=?", (rid,))
                    store.db.execute("DELETE FROM class_room_trash WHERE room_id=?", (rid,))
                    store.db.execute("COMMIT")
                except Exception:
                    store.db.execute("ROLLBACK")
                    raise
        shutil.rmtree(store.root / "media" / rid, ignore_errors=True)
        store.audit(w.uid if w else "system", w.role if w else "system", rid, "room.purge", f"{why} | {(r or {}).get('title', '')[:80]}")
        for h in ON_PURGE:
            try:
                h(rid, forget)
            except Exception:  # noqa: BLE001
                pass
        return True

    def purge_expired(at: datetime | None = None) -> int:
        t = _iso(at or datetime.now(timezone.utc))
        n = 0
        for r in store.q("SELECT room_id FROM class_room_trash WHERE purge_after<=?", (t,)):
            try:
                n += purge_room(r["room_id"], None, "auto")
            except Exception:  # noqa: BLE001
                pass
        return n

    # ------------------------------------------------------------------ routes
    @app.get("/class/rooms/trash", tags=["class-trash"])
    async def trash_list(request: Request):
        w = who(request)
        rows = store.q("SELECT room_id FROM class_room_trash ORDER BY deleted_at DESC")
        out = []
        for x in rows:
            try:
                r, tr = trashed_visible(x["room_id"], w)
            except HTTPException:
                continue
            out.append(item(r, tr))
        return j({"items": out, "count": len(out), "days": days})

    @app.delete("/class/rooms/{rid}", tags=["class-trash"])
    async def trash_room(request: Request, rid: str, reason: str = Query("", max_length=REASON_MAX), forget_learned: bool = Query(False)):
        w = who(request)
        wr(w)
        r, why = can_trash(rid, w)
        if not r:
            raise HTTPException(404, why)
        if why:
            raise HTTPException(409 if "tác vụ nền" in why else 403, why)
        return j(do_trash(r, w, _disp(reason, "")[:REASON_MAX] if reason else "", forget_learned))

    @app.post("/class/rooms/{rid}/restore", tags=["class-trash"])
    async def restore(request: Request, rid: str):
        w = who(request)
        wr(w)
        r, tr = trashed_visible(rid, w)
        store.x("DELETE FROM class_room_trash WHERE room_id=?", (rid,))
        store.touch(rid)
        store.audit(w.uid, w.role, rid, "room.restore", r["title"][:80])
        for h in ON_RESTORE:
            try:
                h(rid)
            except Exception:  # noqa: BLE001
                pass
        return j({"id": rid, "title": r["title"], "restored": True})

    @app.delete("/class/rooms/{rid}/purge", tags=["class-trash"])
    async def purge(request: Request, rid: str):
        w = who(request)
        if not w.master:
            if not RID.match(rid or "") or not (trash_row(rid) and store.is_member(rid, w.uid)):
                raise HTTPException(404, "không tìm thấy phòng trong thùng rác")
            raise HTTPException(403, "chỉ master được xoá vĩnh viễn")
        wr(w)
        trashed_visible(rid, w)
        await asyncio.to_thread(purge_room, rid, w, "manual")
        return j({"id": rid, "purged": True})

    @app.post("/class/rooms/bulk-delete", tags=["class-trash"])
    async def bulk(request: Request, body: dict):
        w = who(request)
        wr(w)
        step = body.get("step")
        if step not in ("prepare", "confirm"):
            raise HTTPException(422, "step phải là prepare hoặc confirm")
        ids = body.get("ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
            raise HTTPException(422, "ids: danh sách id phòng")
        ids = list(dict.fromkeys(ids))
        if len(ids) > MAX_BULK:
            raise HTTPException(422, f"tối đa {MAX_BULK} phòng mỗi lần")
        now_m = time.monotonic()
        for k in [k for k, v in prepared.items() if v[2] < now_m]:
            prepared.pop(k, None)
        reason = _disp(str(body.get("reason") or ""), "")[:REASON_MAX]
        if step == "prepare":
            ok, rej = [], []
            for rid in ids:
                r, why = can_trash(rid, w)
                if why:
                    rej.append({"id": rid, "reason": why if r else "không tìm thấy phòng", **({"title": r["title"]} if r else {})})
                else:
                    ok.append({"id": rid, "title": r["title"], "counts": counts(rid), "updated_at": r["updated_at"]})
            tok = secrets.token_urlsafe(18)
            prepared[tok] = (w.uid, tuple(sorted(x["id"] for x in ok)), now_m + TOKEN_TTL)
            return j({"token": tok, "expires_in": int(TOKEN_TTL), "eligible": ok, "rejected": rej})
        tok = body.get("token")
        p = prepared.get(tok) if isinstance(tok, str) else None
        if not p or p[0] != w.uid or p[1] != tuple(sorted(x for x in ids if x in p[1])) :
            raise HTTPException(409, "mã xác nhận không hợp lệ hoặc đã hết hạn: hãy chuẩn bị lại")
        prepared.pop(tok, None)
        done, rej = [], []
        for rid in p[1]:
            r, why = can_trash(rid, w)
            if why:
                rej.append({"id": rid, "reason": why})
                continue
            do_trash(r, w, reason, bool(body.get("forget_learned")))
            done.append(rid)
        store.audit(w.uid, w.role, None, "room.bulk_trash", f"{len(done)} phòng, {len(rej)} bỏ qua")
        return j({"trashed": done, "rejected": rej, "days": days})

    # Tuyến /class/rooms/trash phải đứng trước /class/rooms/{rid} (đã đăng ký ở api.py)
    mine = [r for r in app.router.routes if getattr(r, "path", "") in ("/class/rooms/trash", "/class/rooms/bulk-delete")]
    for r in mine:
        app.router.routes.remove(r)
    app.router.routes[0:0] = mine

    async def loop() -> None:
        while True:
            try:
                await asyncio.to_thread(purge_expired)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(3600)

    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a):
        task = asyncio.get_running_loop().create_task(loop())
        try:
            async with inner(a) as state:
                yield state
        finally:
            task.cancel()

    app.router.lifespan_context = lifespan
    api = {"purge_expired": purge_expired, "purge_room": purge_room, "days": days}
    app.state.rooms_trash = api
    return api
