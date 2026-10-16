"""Route /class/methods... (Phương pháp + liên kết kịch bản + hồ sơ + phòng phương pháp + kế hoạch áp dụng). Hợp đồng: docs/handoff/METHOD_API.md.
Cùng cơ chế danh tính/quyền như ux_api (header x-class-*; master|expert; 404 đồng nhất chống IDOR). CHỈ nghiên cứu/paper."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .api import NOSTORE, RID, ROLES, UID, Who, _disp, _Limiter, sse
from .methods import MBY, MROW_KEYS, MAXEDIT, ROLES as SCEN_ROLES, Methods, RelError, validate_relations
from .safety import clean_text, looks_injected

log = logging.getLogger("class.methods")
MAX_MSG = 4000
AI = {"role": "ai", "name": "AI Training Class", "user_id": "ai"}


def register(app: FastAPI, st: Any, store: Any, sstore: Any = None, llm: Any = None) -> Methods:
    from .llm import build_client
    M = Methods(store, sstore, llm if llm is not None else build_client())
    app.state.methods = M
    write_rl = _Limiter(getattr(st, "class_write_rate", 60), 60.0)
    msg_rl = _Limiter(getattr(st, "class_msg_rate", 20), 60.0)

    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def method_of(mid: str, w: Who) -> dict:
        m = M.get(mid) if RID.match(mid or "") else None
        if not m or not (w.master or m["owner"] == w.uid):
            raise HTTPException(404, "không tìm thấy phương pháp")
        return m

    def room_ok(rid: str, w: Who) -> dict:
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            raise HTTPException(404, "không tìm thấy phòng")
        return r

    def wr(w: Who) -> None:
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")

    def j(data: Any, code: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers=NOSTORE)

    def plan_brief(mid: str) -> dict:
        try:
            from .methods_plan import compute_plan
            p = compute_plan(M, mid)
            return {"passed": p["progress"]["passed"], "total": p["progress"]["total"], "verdict": p["verdict"]["code"]}
        except ImportError:
            return {"passed": 0, "total": 9, "verdict": "incomplete"}

    def summary(m: dict, brief: bool = True) -> dict:
        sc = M.scen_rows(m["id"])
        scores = [M.room_canvas(s["room_id"])[1]["score"] for s in sc]
        return {"id": m["id"], "name": m["name"], "description": m["description"], "owner": m["owner"], "owner_name": m["owner_name"], "version": m["version"],
                "scenario_count": len(sc), "clarity_avg": round(sum(scores) / len(scores)) if scores else 0, "plan": plan_brief(m["id"]) if brief else None,
                "created_at": m["created_at"], "updated_at": m["updated_at"]}

    def detail(m: dict) -> dict:
        mid = m["id"]
        d = summary(m, brief=False)
        d.pop("plan")
        d["scenarios"] = [M.scenario_view(s["room_id"], s["role"], s["added_at"]) for s in M.scen_rows(mid)]
        d["relations"] = M.relations(mid)
        d["profile"] = {"clarity": M.canvas(mid)["clarity"], "version": m["version"]}
        d["plan"] = plan_brief(mid)
        return d

    def clean_name(v: Any, lo: int, hi: int, what: str) -> str:
        if not isinstance(v, str):
            raise HTTPException(422, f"{what} bắt buộc")
        s = clean_text(v, hi).strip()
        if not lo <= len(s) <= hi or looks_injected(s):
            raise HTTPException(422, f"{what}: {lo}-{hi} ký tự, không chứa chỉ thị")
        return s

    # ------------------------------------------------------------------ L1: phương pháp
    @app.get("/class/methods", tags=["class-methods"])
    async def list_methods(request: Request):
        w = who(request)
        items = [summary(m) for m in M.listing(w.uid, w.master)]
        return j({"items": items, "total": len(items)})

    @app.post("/class/methods", tags=["class-methods"], status_code=201)
    async def create_method(request: Request, body: dict):
        w = who(request)
        wr(w)
        name = clean_name(body.get("name"), 3, 80, "name")
        desc = clean_text(body.get("description") or "", 1000)
        if looks_injected(desc):
            raise HTTPException(422, "description chứa chỉ thị")
        mid = M.create(name, desc, w.uid, w.name)
        store.audit(w.uid, w.role, None, "method.create", mid)
        return j(summary(M.get(mid)), 201)

    @app.get("/class/methods/{mid}", tags=["class-methods"])
    async def get_method(request: Request, mid: str):
        return j(detail(method_of(mid, who(request))))

    @app.patch("/class/methods/{mid}", tags=["class-methods"])
    async def patch_method(request: Request, mid: str, body: dict):
        w = who(request)
        m = method_of(mid, w)
        wr(w)
        name = clean_name(body["name"], 3, 80, "name") if "name" in body else None
        desc = None
        if "description" in body:
            desc = clean_text(body.get("description") or "", 1000)
            if looks_injected(desc):
                raise HTTPException(422, "description chứa chỉ thị")
        if name is None and desc is None:
            raise HTTPException(422, "cần name hoặc description")
        M.update(mid, name, desc, w.uid)
        store.audit(w.uid, w.role, None, "method.update", mid)
        return j(detail(M.get(m["id"])))

    @app.delete("/class/methods/{mid}", tags=["class-methods"])
    async def delete_method(request: Request, mid: str):
        w = who(request)
        method_of(mid, w)
        wr(w)
        n = M.delete(mid, w.uid)
        store.audit(w.uid, w.role, None, "method.delete", mid)
        return j({"ok": True, "detached": n})

    # ------------------------------------------------------------------ kịch bản trong phương pháp
    def role_of(body: dict) -> str:
        r = body.get("role", "core")
        if r not in SCEN_ROLES:
            raise HTTPException(422, "role: " + "|".join(SCEN_ROLES))
        return r

    @app.post("/class/methods/{mid}/scenarios", tags=["class-methods"], status_code=201)
    async def add_scenario(request: Request, mid: str, body: dict):
        w = who(request)
        method_of(mid, w)
        wr(w)
        role = role_of(body)
        new = body.get("new")
        with store.room_lock("method:" + mid):
            if isinstance(new, dict):
                title = clean_name(new.get("title"), 3, 120, "title")
                rid = store.create_room(title, w.uid, w.name, w.role)["id"]
                store.audit(w.uid, w.role, rid, "room.create", "via method " + mid)
            else:
                rid = body.get("room_id")
                room_ok(rid, w)
                cur = M.method_of_room(rid)
                if cur == mid:
                    raise HTTPException(409, "phòng đã thuộc phương pháp này")
                if cur:
                    other = M.get(cur)
                    if body.get("move") is not True or not (w.master or (other and other["owner"] == w.uid)):
                        raise HTTPException(409, "phòng đang thuộc phương pháp khác (đặt move=true nếu bạn có quyền để chuyển)")
                    M.put_relations(cur, [r for r in M.relations(cur) if rid not in (r["a"], r["b"])], w.uid)
                    M.log(cur, w.uid, "move_out", rid)
                    M.bump(cur)
            M.attach(mid, rid, role, w.uid)
            v = M.bump(mid)
        store.audit(w.uid, w.role, rid, "method.attach", mid)
        s = next(x for x in M.scen_rows(mid) if x["room_id"] == rid)
        return j({"scenario": M.scenario_view(rid, role, s["added_at"]), "method_version": v}, 201)

    @app.delete("/class/methods/{mid}/scenarios/{rid}", tags=["class-methods"])
    async def remove_scenario(request: Request, mid: str, rid: str):
        w = who(request)
        method_of(mid, w)
        wr(w)
        if rid not in M.scen_ids(mid):
            raise HTTPException(404, "kịch bản không thuộc phương pháp")
        n = M.detach(mid, rid, w.uid)
        v = M.bump(mid)
        store.audit(w.uid, w.role, rid, "method.detach", mid)
        return j({"ok": True, "removed_relations": n, "method_version": v})

    @app.patch("/class/methods/{mid}/scenarios/{rid}", tags=["class-methods"])
    async def patch_scenario(request: Request, mid: str, rid: str, body: dict):
        w = who(request)
        method_of(mid, w)
        wr(w)
        if rid not in M.scen_ids(mid):
            raise HTTPException(404, "kịch bản không thuộc phương pháp")
        M.set_role(mid, rid, role_of(body), w.uid)
        v = M.bump(mid)
        row = next(x for x in M.scen_rows(mid) if x["room_id"] == rid)
        return j({"scenario": M.scenario_view(rid, row["role"], row["added_at"]), "method_version": v})

    # ------------------------------------------------------------------ quan hệ
    @app.get("/class/methods/{mid}/relations", tags=["class-methods"])
    async def get_relations(request: Request, mid: str):
        method_of(mid, who(request))
        return j(M.graph(mid))

    @app.put("/class/methods/{mid}/relations", tags=["class-methods"])
    async def put_relations(request: Request, mid: str, body: dict):
        w = who(request)
        method_of(mid, w)
        wr(w)
        try:
            rels, _ = validate_relations(body.get("relations"), M.scen_ids(mid))
        except RelError as e:
            raise HTTPException(422, str(e)) from None
        M.put_relations(mid, rels, w.uid)
        M.bump(mid)
        store.audit(w.uid, w.role, None, "method.relations", mid)
        return j(M.graph(mid))

    # ------------------------------------------------------------------ L2: hồ sơ phương pháp
    @app.get("/class/methods/{mid}/canvas", tags=["class-methods"])
    async def method_canvas(request: Request, mid: str):
        method_of(mid, who(request))
        return j(M.canvas(mid))

    def check_key(key: str) -> None:
        if key not in MBY:
            raise HTTPException(422, "key không hợp lệ")

    @app.post("/class/methods/{mid}/canvas/{key}/edit", tags=["class-methods"])
    async def method_edit(request: Request, mid: str, key: str, body: dict):
        w = who(request)
        method_of(mid, w)
        wr(w)
        check_key(key)
        text = body.get("text")
        if not isinstance(text, str):
            raise HTTPException(422, "text bắt buộc")
        text = clean_text(text, MAXEDIT)
        if not text.strip() or looks_injected(text):
            raise HTTPException(422, "text rỗng hoặc chứa chỉ thị")
        with store.room_lock("method:" + mid):
            before, v = M.record(mid, key, text.strip(), w.name, w.uid)
        cv = M.canvas(mid)
        store.audit(w.uid, w.role, None, "method.canvas.edit", f"{mid}:{key}")
        return j({"key": key, "before": before, "after": text.strip(), "row": next(r for r in cv["rows"] if r["key"] == key), "clarity": cv["clarity"], "method_version": v})

    @app.post("/class/methods/{mid}/canvas/{key}/confirm", tags=["class-methods"])
    async def method_confirm(request: Request, mid: str, key: str, body: dict):
        w = who(request)
        method_of(mid, w)
        wr(w)
        check_key(key)
        on = body.get("confirmed", True)
        if not isinstance(on, bool):
            raise HTTPException(422, "confirmed phải là boolean")
        if on and key not in M.rows_raw(mid):
            raise HTTPException(404, "hàng còn trống, chưa có gì để xác nhận")
        M.set_confirm(mid, key, on, w.uid)
        store.audit(w.uid, w.role, None, "method.canvas.confirm" if on else "method.canvas.unconfirm", f"{mid}:{key}")
        return j({"key": key, "confirmed": on, "clarity": M.canvas(mid)["clarity"]})

    # ------------------------------------------------------------------ L2: phòng phương pháp (chat SSE)
    @app.get("/class/methods/{mid}/messages", tags=["class-methods"])
    async def get_messages(request: Request, mid: str, limit: int = 50, before: int | None = None):
        method_of(mid, who(request))
        items, more = M.messages(mid, max(1, min(limit, 200)), before)
        return j({"items": items, "has_more": more, "next_row": M.next_row(mid)})

    @app.post("/class/methods/{mid}/messages", tags=["class-methods"])
    async def post_message(request: Request, mid: str, body: dict):
        w = who(request)
        method_of(mid, w)
        text, row = body.get("text"), body.get("row")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MSG:
            raise HTTPException(422, f"text: 1-{MAX_MSG} ký tự")
        if row is not None and row not in MBY:
            raise HTTPException(422, "row không hợp lệ")
        if not msg_rl.ok(w.uid):
            raise HTTPException(429, "Bạn gửi quá nhanh, thử lại sau ít giây")
        lock = store.room_lock("method:" + mid)
        if not await asyncio.to_thread(lock.acquire, True, 20):
            raise HTTPException(429, "Phòng đang xử lý tin trước, thử lại")

        def turn_logic() -> tuple[dict, dict, dict]:
            author = {"role": "user", "name": w.name, "user_id": w.uid}
            um = M.add_msg(mid, "text", author, clean_text(text, MAX_MSG))
            store.audit(w.uid, w.role, None, "method.message", f"{mid} len={len(text)}")
            notes: list[str] = []
            key = row or M.next_row(mid) or MROW_KEYS[-1]
            hit = looks_injected(text)
            recorded = False
            if hit:
                notes.append("injection bị chặn")
                note = "Tin nhắn có mẫu giống chỉ thị cho AI nên tôi bỏ qua (không lưu). Hãy mô tả bằng lời của bạn."
            else:
                msg = clean_text(text, MAXEDIT).strip()
                if msg:
                    M.record(mid, key, msg, w.name, w.uid)
                    recorded = True
                note = ""
            reply, qs, used = M.reply(mid, key, recorded, note)
            nxt = M.next_row(mid)
            am = M.add_msg(mid, "text", AI, reply, data={"row": key, "recorded": recorded, "next_row": nxt, "used_llm": used}, chips=M.chips_for(nxt))
            t = {"row": key, "recorded": recorded, "next_row": nxt, "questions": qs, "chips": am["chips"], "used_llm": used, "notes": notes, "clarity": M.canvas(mid)["clarity"]}
            return um, am, t

        async def gen():
            try:
                um, am, t = await asyncio.to_thread(turn_logic)
                yield sse({"type": "user", "message": um})
                yield sse({"type": "meta", "message_id": am["id"], "row": t["row"]})
                for i in range(0, len(am["text"]), 48):
                    yield sse({"type": "delta", "text": am["text"][i:i + 48]})
                    await asyncio.sleep(0)
                yield sse({"type": "turn", "message": am, "turn": t})
                yield sse({"type": "done"})
            except asyncio.CancelledError:
                raise
            except HTTPException as e:
                yield sse({"type": "error", "detail": str(e.detail)})
            except Exception as e:  # noqa: BLE001
                log.exception("method message lỗi")
                yield sse({"type": "error", "detail": "Lỗi nội bộ: " + type(e).__name__})
            finally:
                lock.release()
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"})

    # ------------------------------------------------------------------ L3: kế hoạch áp dụng
    try:
        from . import methods_plan
        methods_plan.register(app, st, store, M, who, method_of, wr, j)
    except ImportError:
        pass
    return M
