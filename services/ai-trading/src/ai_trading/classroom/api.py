"""API AI Training Class (P2b): /class/* trong service ai-trading (nội bộ; gateway gắn danh tính X-Class-User/-Role/-Name sau khi kiểm vai master|expert).
CHỈ nghiên cứu/paper. Không có đường đặt lệnh: action chạy qua allow-list của lõi (parse_command) + job nền sẵn có; test khoá chỉ master + confirm = id.
Hợp đồng: docs/handoff/AI_CLASSROOM_API.md."""
from __future__ import annotations

import asyncio
import base64
import binascii
import csv
import hashlib
import io
import json
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any

import yaml
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .. import scenario_schema as sch
from . import memory as _mem
from . import persist
from .commands import ALLOWED_ACTIONS, COMMANDS, CommandError, parse_command
from .export import export_scenario
from .llm import GuardedLLM, build_client
from .machine import MAX_MSG, Classroom
from .profile import diff_profiles
from .safety import clean_text, looks_injected
from .store import ClassStore, nid, now

log = logging.getLogger("ai-trading.class")
UID = re.compile(r"^[A-Za-z0-9_.:@\-]{1,64}$")
RID = re.compile(r"^[0-9a-f]{32}$")
EID = re.compile(r"^[0-9a-f]{16}$")
FNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. \-()]{0,79}$")
AI = {"user_id": "ai", "name": "AI học trò", "role": "ai"}
SYS = {"user_id": "system", "name": "Hệ thống", "role": "system"}
ROLES = ("master", "expert")
VERDICTS = {"dung": 1.0, "gan_dung": 0.5, "sai": 0.0}
LIMITS = {"image": 700 * 1024, "yaml": 64 * 1024, "csv": 256 * 1024, "pdf": 1536 * 1024, "note": 4000}
EXT = {"image": ("png", "jpg", "webp"), "yaml": ("yaml", "yml"), "csv": ("csv",), "pdf": ("pdf",), "note": ("txt", "md")}
CTYPE = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "yaml": "text/plain; charset=utf-8", "yml": "text/plain; charset=utf-8",
         "csv": "text/plain; charset=utf-8", "pdf": "application/pdf", "txt": "text/plain; charset=utf-8", "md": "text/plain; charset=utf-8"}
DISCLAIMER = "Chỉ nghiên cứu và mô phỏng (paper); hệ thống không đặt lệnh thật. Kết quả quá khứ không đảm bảo tương lai."
NOSTORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
_SRC = re.compile(r"(?i)\b(?:binance|yahoo|twelve\s*data|twelvedata|metaquotes|dukascopy|stooq|alpha\s*vantage|tradingview|polygon|finnhub|tiingo|coinbase|mt5|mt4)\b")


class Who:
    def __init__(self, uid: str, role: str, name: str):
        self.uid, self.role, self.name = uid, role, name

    @property
    def master(self) -> bool:
        return self.role == "master"

    @property
    def author(self) -> dict:
        return {"user_id": self.uid, "name": self.name, "role": self.role}


class _Limiter:
    def __init__(self, n: int, per: float):
        self.n, self.per, self.h = n, per, defaultdict(deque)

    def ok(self, key: str) -> bool:
        t, q = time.monotonic(), self.h[key]
        while q and t - q[0] > self.per:
            q.popleft()
        if len(q) >= self.n:
            return False
        q.append(t)
        return True


def _disp(name: str, fallback: str) -> str:
    n = clean_text(name or "", 60)
    n = re.sub(r"[<>`{}\\]", "", n).strip()
    return n or fallback


def sse(obj: dict) -> bytes:
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode() + b"\n\n"


def register(app: FastAPI, st, sstore, reg, enqueue, llm: GuardedLLM | None = None) -> ClassStore:
    store = ClassStore(st.class_dir)
    llm = llm if llm is not None else build_client()
    app.state.class_store = store
    msg_rl, write_rl = _Limiter(st.class_msg_rate, 60.0), _Limiter(st.class_write_rate, 60.0)

    # ------------------------------------------------------------------ danh tính / quyền
    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def room_of(rid: str, w: Who) -> dict:
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            raise HTTPException(404, "không tìm thấy phòng")      # 404 đồng nhất: không lộ phòng có tồn tại hay không (IDOR)
        mem = next((m for m in r["members"] if m["user_id"] == w.uid), None)
        if mem:
            w.name = mem["name"]          # tên hiển thị = tên đã đăng ký trong phòng (không tin header/nội dung gửi lên)
        return r

    class locked:
        """Khoá phòng dạng async (không chặn event loop); quá 20 s -> 429."""
        def __init__(self, rid: str):
            self.lk = store.room_lock(rid)

        async def __aenter__(self):
            if not await asyncio.to_thread(self.lk.acquire, True, 20):
                raise HTTPException(429, "Phòng đang xử lý, thử lại")

        async def __aexit__(self, *a):
            self.lk.release()

    def wr(w: Who) -> None:
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")

    def j(data: Any, code: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers=NOSTORE)

    def machine(rid: str) -> Classroom:
        return persist.load(store.get_state(rid), rid, llm)

    def save(rid: str, c: Classroom, by: str) -> None:
        store.put_state(rid, persist.dump(c))
        for s in c.history.versions:
            store.put_version(rid, s["version"], s, s.get("note", ""), by)

    def summary(r: dict) -> dict:
        st = store.get_state(rid := r["id"]) or {}
        prof = st.get("profile") or {}
        step = None
        if st.get("phase") == "interview":
            from .checklist import STEPS
            i = int(st.get("idx", 0))
            step = STEPS[i].key if i < len(STEPS) else None
        lm = store.last_message(rid)
        return {"id": rid, "title": r["title"], "created_at": r["created_at"], "updated_at": r["updated_at"], "members": r["members"],
                "phase": st.get("phase", "intake"), "step": step, "profile_name": prof.get("name"), "profile_version": prof.get("version", 1),
                "msg_count": store.count_messages(rid),
                "last_message": {"author": lm["author"], "text": lm["text"][:160], "created_at": lm["created_at"]} if lm else None}

    def llm_info() -> dict:
        nm = getattr(llm.inner, "name", "local") if llm else "none"
        prov = "claude" if nm == "claude" else "local"
        return {"provider": prov, "enabled": prov == "claude" or nm not in ("none", "null"),
                "note": "Mô hình cục bộ (giới hạn: có thể lạc đề; khi lỗi hệ thống dùng câu hỏi mẫu)." if prov == "local" else "Mô hình đám mây (đã bật có chủ đích)."}

    # ------------------------------------------------------------------ phòng
    @app.get("/class/status", tags=["class"])
    async def status(request: Request):
        who(request)
        return j({"llm": llm_info(), "limits": {"message_chars": MAX_MSG, "messages_per_min": st.class_msg_rate, "attachments_bytes": LIMITS}, "version": 1, "disclaimer": DISCLAIMER})

    @app.get("/class/rooms", tags=["class"])
    async def rooms(request: Request):
        w = who(request)
        return j({"items": [summary(r) for r in store.rooms_for(w.uid, w.master)], "llm": llm_info()})

    @app.post("/class/rooms", tags=["class"], status_code=201)
    async def create_room(request: Request, body: dict):
        w = who(request)
        wr(w)
        title = clean_text(body.get("title", ""), 80)
        if not 3 <= len(title) <= 80 or looks_injected(title):
            raise HTTPException(422, "title: 3-80 ký tự, không chứa chỉ thị")
        name = _disp(str(body.get("display_name") or ""), w.name)
        r = store.create_room(title, w.uid, name, w.role)
        store.audit(w.uid, w.role, r["id"], "room.create", title)
        store.add_message(r["id"], "system", SYS, "Phòng học đã tạo. Hãy giao kịch bản đầu tiên bằng khoảng 3 câu (mã, khung, điều kiện hình thành).")
        return j(summary(store.room(r["id"])), 201)

    @app.get("/class/rooms/{rid}", tags=["class"])
    async def get_room(request: Request, rid: str, q: str | None = Query(None, max_length=80), limit: int = Query(50, ge=1, le=200), before: int | None = Query(None, ge=1)):
        w = who(request)
        r = room_of(rid, w)
        await finalize(rid, w)
        msgs, more = store.messages(rid, limit, before, q or None)
        c = machine(rid)
        from .checklist import STEPS
        from .commands import chips_for
        step = STEPS[c.idx].key if c.phase == "interview" and c.idx < len(STEPS) else None
        return j({"room": summary(r), "messages": msgs, "pinned": store.pinned(rid), "has_more": more,
                  "chips": chips_for(c.phase, step, c.profile.missing_required(), len(c.profile.answered())),
                  "state": {"phase": c.phase, "step": step, "idx": c.idx, "total": len(STEPS), "missing_required": c.profile.missing_required()},
                  "labels_summary": label_summary(rid), "pending_actions": store.actions(rid, ("needs_confirm", "queued", "running"))})

    @app.post("/class/rooms/{rid}/members", tags=["class"], status_code=201)
    async def add_member(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        uid = str(body.get("user_id", ""))
        role = body.get("role", "expert")
        if not UID.match(uid) or role not in ROLES:
            raise HTTPException(422, "user_id/role không hợp lệ")
        if role == "master" and not w.master:
            raise HTTPException(403, "Không có quyền truy cập")
        m = store.add_member(rid, uid, _disp(str(body.get("name") or ""), "Chuyên gia " + uid[:8]), role)
        store.audit(w.uid, w.role, rid, "member.add", uid)
        store.add_message(rid, "system", SYS, f"{m['name']} đã vào lớp ({role}).")
        return j(m, 201)

    @app.post("/class/rooms/{rid}/pins", tags=["class"])
    async def pins(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        mid = str(body.get("message_id", ""))
        if not RID.match(mid) or not store.set_pin(rid, mid, bool(body.get("pinned", True))):
            raise HTTPException(404, "không tìm thấy tin nhắn")
        store.audit(w.uid, w.role, rid, "message.pin", mid)
        return j({"ok": True})

    # ------------------------------------------------------------------ tin nhắn (SSE)
    def intent_public(it) -> dict | None:
        return {"command": it.command, "action": it.action, "local": it.local, "requires_confirm": it.requires_confirm, "paper_only": True} if it else None

    @app.post("/class/rooms/{rid}/messages", tags=["class"])
    async def post_message(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MSG:
            raise HTTPException(422, f"text: 1-{MAX_MSG} ký tự")
        if not msg_rl.ok(w.uid):
            raise HTTPException(429, f"Bạn gửi quá nhanh (tối đa {st.class_msg_rate} tin/phút)")
        lock = store.room_lock(rid)
        if not await asyncio.to_thread(lock.acquire, True, 20):
            raise HTTPException(429, "Phòng đang xử lý tin trước, thử lại")

        async def gen():
            try:
                um = store.add_message(rid, "text", w.author, clean_text(text, MAX_MSG) if not text.lstrip().startswith("/") else text.strip()[:MAX_MSG])
                store.audit(w.uid, w.role, rid, "message", f"len={len(text)}")
                yield sse({"type": "user", "message": um})
                c = machine(rid)
                _mem.attach(c, rid, w.uid)     # Bộ nhớ của AI (no-op nếu chưa đăng ký)
                turn = await asyncio.to_thread(c.respond, text, w.name, "expert")
                save(rid, c, w.uid)
                am = store.add_message(rid, "text", AI, turn.reply, understanding=turn.understanding, chips=turn.chips, data={"step": turn.step, "phase": turn.phase, "notes": turn.notes, "used_llm": turn.used_llm})
                yield sse({"type": "meta", "message_id": am["id"], "phase": turn.phase, "step": turn.step})
                for i in range(0, len(turn.reply), 48):
                    yield sse({"type": "delta", "text": turn.reply[i:i + 48]})
                    await asyncio.sleep(0)
                t = asdict(turn)
                t["intent"] = intent_public(turn.intent)
                yield sse({"type": "turn", "message": am, "turn": t})
                if turn.intent and not turn.intent.local:
                    a = await asyncio.to_thread(run_intent, rid, w, c, turn.intent)
                    save(rid, c, w.uid)
                    yield sse({"type": "action", "action": a})
                    if a.get("result_message_id"):
                        yield sse({"type": "result", "message": store.message(rid, a["result_message_id"])})
                mp = await asyncio.to_thread(_mem.after_turn, rid, w, text, um.get("id"))
                if mp:
                    yield sse(mp)
                yield sse({"type": "done"})
            except asyncio.CancelledError:
                raise
            except HTTPException as e:
                yield sse({"type": "error", "detail": str(e.detail)})
            except Exception as e:  # noqa: BLE001
                log.exception("message lỗi")
                yield sse({"type": "error", "detail": "Lỗi nội bộ: " + type(e).__name__})
            finally:
                lock.release()
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"})

    @app.post("/class/rooms/{rid}/messages/{mid}/review", tags=["class"])
    async def review(request: Request, rid: str, mid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        v = body.get("verdict")
        if v not in ("accept", "edit", "reject") or not RID.match(mid):
            raise HTTPException(422, "verdict: accept|edit|reject")
        m = store.message(rid, mid)
        if not m or m["author"].get("role") != "ai":
            raise HTTPException(404, "không tìm thấy nhận định của AI")
        note, edit = clean_text(body.get("note") or "", 500), clean_text(body.get("edit_text") or "", 500)
        if looks_injected(note, edit) or (v == "edit" and not edit):
            raise HTTPException(422, "cần edit_text hợp lệ (không chứa chỉ thị)")
        async with locked(rid):
            c = machine(rid)
            if v == "edit":
                c.profile.evidence.append({"kind": "review_edit", "text": edit, "dropped": False, "author": w.name})
                c.profile.open_questions.append("Chuyên gia sửa nhận định: " + edit[:120])
            elif v == "reject":
                c.profile.open_questions.append("Chuyên gia phản bác: " + (note or "nhận định của AI")[:120])
            if w.name not in c.profile.contributors:
                c.profile.contributors.append(w.name)
            save(rid, c, w.uid)
            store.set_review(rid, mid, {"verdict": v, "note": note, "edit_text": edit, "by": w.name, "at": now()})
        store.audit(w.uid, w.role, rid, "review." + v, mid)
        return j({"ok": True, "message": store.message(rid, mid)})

    # ------------------------------------------------------------------ đính kèm
    @app.post("/class/rooms/{rid}/attachments", tags=["class"], status_code=201)
    async def attach(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        kind, name = body.get("kind"), str(body.get("name") or "ghi-chu.txt")
        if kind not in LIMITS or not FNAME.match(name) or ".." in name:
            raise HTTPException(422, "kind/name không hợp lệ")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ext = {"jpeg": "jpg"}.get(ext, ext)
        if ext not in EXT[kind]:
            raise HTTPException(422, f"đuôi tệp không khớp loại {kind}")
        caption = clean_text(body.get("caption") or "", 500)
        warns: list[str] = []
        if kind == "note":
            raw = str(body.get("text") or "").encode()
        else:
            b64 = body.get("data_b64")
            if not isinstance(b64, str) or len(b64) > LIMITS[kind] * 4 // 3 + 64:
                raise HTTPException(413, "tệp quá lớn hoặc thiếu data_b64")
            try:
                raw = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                raise HTTPException(422, "base64 không hợp lệ") from None
        if len(raw) > LIMITS[kind] or not raw:
            raise HTTPException(413, "tệp rỗng hoặc quá lớn")
        evid = ""
        if kind == "image":
            k = sch.image_kind(raw)
            if k is None or k != ext:
                raise HTTPException(422, "nội dung ảnh không khớp đuôi tệp")
            evid = caption
            if not caption:
                warns.append("Chưa có chú thích: AI chưa đọc được ảnh, hãy mô tả điều cần chú ý (hoặc dùng nút vẽ trên biểu đồ).")
        elif kind == "pdf":
            if not raw.startswith(b"%PDF-"):
                raise HTTPException(422, "không phải PDF")
            evid = ("[PDF] " + caption) if caption else ""
            warns.append("Chưa trích nội dung PDF: hãy chú thích điểm chính để AI dùng.")
        else:
            txt = raw.decode("utf-8", "replace")
            if kind == "yaml":
                try:
                    for ev in yaml.parse(txt):
                        if isinstance(ev, (yaml.AliasEvent,)) or getattr(ev, "anchor", None):
                            raise ValueError("alias")
                    obj = yaml.safe_load(txt)
                except (yaml.YAMLError, ValueError):
                    raise HTTPException(422, "YAML không hợp lệ hoặc có anchor/alias") from None
                evid = yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)[:1400]
            elif kind == "csv":
                rows = []
                try:
                    for i, row in enumerate(csv.reader(io.StringIO(txt))):
                        if i >= 20:
                            break
                        rows.append(", ".join(c[:40] for c in row[:10]))
                except csv.Error:
                    raise HTTPException(422, "CSV không hợp lệ") from None
                evid = "\n".join(rows)
            else:
                evid = txt[:1400]
        if _SRC.search(evid):
            evid = _SRC.sub("[nguồn]", evid)
        async with locked(rid):
            c = machine(rid)
            t = c.attach(kind, evid or "(không có nội dung đọc được)", w.name) if evid else None
            if t is not None and any("bị loại" in n for n in t.notes):
                raise HTTPException(422, "Đính kèm bị loại vì có mẫu giống chỉ thị cho AI hoặc nội dung không an toàn")
            att = store.add_attachment(rid, kind, name, raw, CTYPE[ext], ext)
            att["url"] = f"/api/v1/ai-trading/class/rooms/{rid}/media/{att['id']}"
            if caption:
                att["note"] = caption
            save(rid, c, w.uid)
        m = store.add_message(rid, "attachment", w.author, caption or f"Đính kèm {kind}: {name}", attachments=[att])
        store.audit(w.uid, w.role, rid, "attachment", f"{kind}:{len(raw)}")
        if t is not None:
            store.add_message(rid, "text", AI, t.reply)
        return j({"message": m, "attachment": att, "warnings": warns}, 201)

    @app.get("/class/rooms/{rid}/media/{aid}", tags=["class"])
    async def media(request: Request, rid: str, aid: str):
        w = who(request)
        room_of(rid, w)
        a = store.attachment(rid, aid) if RID.match(aid) else None
        if not a:
            ex = None
            for e in store.examples(rid):
                if e["id"] == aid:
                    ex = e
            if not ex:
                raise HTTPException(404, "không có tệp")
            p = sstore.path(ex["scenario_id"])
            f = (p / "scan" / ex["job"] / ex["image"]) if p and re.fullmatch(r"[0-9a-f]{32}", ex.get("job", "")) and re.fullmatch(r"ex\d{1,2}\.png", ex.get("image", "")) else None
            if not f or not f.is_file():
                raise HTTPException(404, "không có tệp")
            return Response(f.read_bytes(), media_type="image/png", headers={**NOSTORE, "Content-Security-Policy": "default-src 'none'; sandbox"})
        meta, p = a
        inline = meta["kind"] == "image"
        return Response(p.read_bytes(), media_type=meta["ctype"], headers={**NOSTORE, "Content-Security-Policy": "default-src 'none'; sandbox",
                        "Content-Disposition": ("inline" if inline else "attachment") + '; filename="' + re.sub(r"[^A-Za-z0-9_.\-]", "_", meta["name"]) + '"'})

    # ------------------------------------------------------------------ action
    def register_scenario(yaml_text: str, w: Who) -> tuple[str, str]:
        doc = yaml.safe_load(yaml_text)
        sid = doc["id"]
        sha = hashlib.sha256(yaml_text.encode()).hexdigest()[:16]
        if sstore.path(sid):
            return sid, sha
        taken = set(sstore.ids()) | set(reg.load()["strategies"])
        try:
            sc = sch.validate(yaml_text, taken_ids=taken)
        except sch.SchemaError as e:
            raise HTTPException(422, str(e)) from None
        sstore.create(sc, {}, w.uid)
        reg._sig = None
        return sid, sha

    def start_test(rid: str, w: Who, a: dict) -> dict:
        p = a["params"]
        sid, sha = register_scenario(p["scenario_yaml"], w)
        store.add_message(rid, "system", SYS, f"Đã ĐĂNG KÝ giả thuyết trước khi chạy: kịch bản {sid} (băm {sha}). Luật/SL/TP đã khoá cho lần chạy này; chạy walk-forward + baseline ngẫu nhiên, KHÔNG mở test khoá.",
                          data={"scenario_id": sid, "sha": sha})
        try:
            job = enqueue(sid, "backtest", None)
        except HTTPException as e:
            store.upd_action(a["id"], status="failed", scenario_id=sid, message=str(e.detail))
            return store.action(rid, a["id"])
        store.upd_action(a["id"], status="queued", job_id=job["id"], scenario_id=sid, message="Đang xếp hàng backtest walk-forward")
        return store.action(rid, a["id"])

    def run_intent(rid: str, w: Who, c: Classroom, it) -> dict:
        cmd = it.command
        if it.action not in ALLOWED_ACTIONS:
            raise HTTPException(422, "action không nằm trong danh sách cho phép")
        prm = {k: v for k, v in it.params.items() if k != "profile"}
        if cmd == "test":
            a = store.add_action(rid, cmd, "needs_confirm", prm, w.uid, message="Cần xác nhận trước khi chạy test")
            store.audit(w.uid, w.role, rid, "action.test.pending", a["id"])
            return {**a, "summary": f"Sẽ đăng ký giả thuyết (hồ sơ phiên bản {prm.get('profile_version')}), chạy walk-forward trên dữ liệu dev + baseline ngẫu nhiên. Không mở test khoá."}
        if cmd == "quet":
            sid, sha = register_scenario(prm["scenario_yaml"], w)
            rnd = store.rounds(rid) + 1
            a = store.add_action(rid, cmd, "queued", {**{k: v for k, v in prm.items() if k != "scenario_yaml"}, "round": rnd}, w.uid, scenario_id=sid)
            try:
                job = enqueue(sid, "scan_examples", None, {"limit": prm.get("limit", 8), "symbol": prm.get("symbol"), "tf": prm.get("tf")})
            except HTTPException as e:
                store.upd_action(a["id"], status="failed", message=str(e.detail))
                return store.action(rid, a["id"])
            store.upd_action(a["id"], job_id=job["id"], message="Đang quét lịch sử tìm lần xuất hiện")
            store.audit(w.uid, w.role, rid, "action.quet", a["id"])
            return store.action(rid, a["id"])
        if cmd == "luu":
            v = it.params.get("version")
            msg = store.add_message(rid, "system", SYS, f"Đã lưu phiên bản {v} của hồ sơ kịch bản.", data={"version": v})
            a = store.add_action(rid, cmd, "done", {"version": v}, w.uid, message=f"Đã lưu phiên bản {v}")
            store.upd_action(a["id"], result_message_id=msg["id"])
            store.audit(w.uid, w.role, rid, "action.luu", str(v))
            return store.action(rid, a["id"])
        if cmd == "ve":
            ann = {"kind": prm.get("kind"), "note": prm.get("note", ""), "symbol": prm.get("symbol"), "tf": prm.get("tf"), "from_ts": prm.get("from_ts"), "to_ts": prm.get("to_ts"), "points": prm.get("points") or []}
            msg = store.add_message(rid, "annotation", w.author, f"Chú thích {ann['kind']}: {ann['note']}".strip(": "), data=ann)
            c.profile.evidence.append({"kind": "annotation", "text": f"{ann['kind']} {ann['note']}"[:300], "dropped": False, "author": w.name})
            a = store.add_action(rid, cmd, "done", ann, w.uid, message="Đã ghi chú thích")
            store.upd_action(a["id"], result_message_id=msg["id"])
            return store.action(rid, a["id"])
        if cmd == "so-sanh":
            sid = latest_scenario(rid)
            res = sstore.result(sid) if sid else {}
            if not (res.get("dev") or {}).get("status") == "done":
                msg = store.add_message(rid, "system", SYS, "Chưa có kết quả test để so sánh. Hãy chạy test trước (nút “Chạy thử”).")
            else:
                msg = store.add_message(rid, "result_card", AI, "So sánh với baseline ngẫu nhiên (từ kết quả walk-forward gần nhất).", data={**card(sid, res), "compare": prm.get("vs", "random")})
            a = store.add_action(rid, cmd, "done", prm, w.uid)
            store.upd_action(a["id"], result_message_id=msg["id"])
            return store.action(rid, a["id"])
        a = store.add_action(rid, cmd, "failed", prm, w.uid, message="Lệnh chưa được hỗ trợ")
        return a

    def latest_scenario(rid: str) -> str | None:
        for a in reversed(store.actions(rid)):
            if a["command"] == "test" and a.get("scenario_id"):
                return a["scenario_id"]
        return None

    def card(sid: str, res: dict) -> dict:
        dev = res.get("dev") or {}
        pooled = (dev.get("oos") or {}).get("pooled") or {}
        verdict = res.get("verdict") or "unproven"
        honesty = ["Đây là kết quả walk-forward trên dữ liệu dev (ngoài mẫu theo năm); test khoá CHƯA mở -> chưa phải bằng chứng cuối.",
                   f"Số lần thử trong họ kịch bản: {dev.get('n_trials')} (DSR đã trừ).", dev.get("costs", ""),
                   "Chưa chứng minh có edge." if verdict != "edge" else "Cần xác nhận bằng test khoá trước khi tin."]
        if verdict == "no_edge":
            honesty.insert(0, "Không có edge sau chi phí theo tiêu chí đã khai báo.")
        if (pooled.get("n") or 0) < 30:
            honesty.insert(0, "Số lệnh ngoài mẫu quá ít (<30): kết luận không đáng tin.")
        return {"scenario_id": sid, "verdict": verdict, "metrics": {"trades": pooled.get("n"), "expectancy_r": pooled.get("exp_r"), "ci95": pooled.get("ci95"),
                "gross_expectancy_r": dev.get("oos_gross_exp_r"), "p_vs_random": (dev.get("oos") or {}).get("p_vs_random"), "random_exp_r": (dev.get("oos") or {}).get("random_exp_r"),
                "dsr": (dev.get("dsr") or {}).get("dsr") if isinstance(dev.get("dsr"), dict) else dev.get("dsr"), "pbo": (dev.get("pbo") or {}).get("pbo"),
                "first": pooled.get("first"), "last": pooled.get("last")},
                "honesty": [h for h in honesty if h], "disclaimer": DISCLAIMER}

    async def finalize(rid: str, w: Who) -> None:
        """Hoàn tất các action nền đã xong: thêm thẻ kết quả/ảnh quét vào phòng (idempotent, một lần mỗi action)."""
        for a in store.actions(rid, ("queued", "running")):
            job = sstore.job(a["job_id"]) if a.get("job_id") else None
            if not job:
                continue
            st = job.get("status")
            if st in ("queued", "running"):
                store.upd_action(a["id"], status=st, message=job.get("message"))
                continue
            async with locked(rid):
                if store.action(rid, a["id"])["status"] not in ("queued", "running"):
                    continue
                if st == "failed":
                    msg = store.add_message(rid, "system", SYS, "Job nền thất bại: " + str(job.get("message") or job.get("error") or "lỗi")[:200])
                    store.upd_action(a["id"], status="failed", result_message_id=msg["id"], message=str(job.get("message"))[:200])
                    continue
                if a["command"] == "test":
                    res = sstore.result(a["scenario_id"])
                    msg = store.add_message(rid, "result_card", AI, "Kết quả backtest (số thật từ job nền).", data=card(a["scenario_id"], res))
                else:
                    msg = scan_message(rid, a, job)
                store.upd_action(a["id"], status="done", result_message_id=msg["id"], message="Hoàn tất")

    def scan_message(rid: str, a: dict, job: dict) -> dict:
        sid = a["scenario_id"]
        p = sstore.path(sid)
        sc = json.loads((p / "scan" / job["id"] / "scan.json").read_text()) if p and (p / "scan" / job["id"] / "scan.json").is_file() else {"examples": [], "total_hits": 0}
        rnd = (a.get("params") or {}).get("round", 1)
        exs = []
        for e in sc["examples"]:
            eid = store.add_example(rid, rnd, a["id"], {**e, "scenario_id": sid, "job": job["id"]})
            exs.append({"id": eid, "symbol": e["symbol"], "tf": e["tf"], "ts": e["ts"], "entry": e["entry"], "sl": e["sl"], "note": "Nến vàng = nến tín hiệu; vạch vàng = vào lệnh; vạch đỏ = SL.",
                        "image_url": f"/api/v1/ai-trading/class/rooms/{rid}/media/{eid}"})
        text = (f"Vòng {rnd}: tìm thấy {sc['total_hits']} lần xuất hiện trên dữ liệu dev; đây là {len(exs)} ví dụ rải đều. Hãy gắn nhãn ĐÚNG / SAI / GẦN ĐÚNG + lý do."
                if exs else "Không tìm thấy lần xuất hiện nào theo hiểu biết hiện tại: có thể luật quá chặt hoặc thiếu dữ liệu cho mã/khung này.")
        return store.add_message(rid, "scan", AI, text, data={"round": rnd, "examples": exs, "total_hits": sc["total_hits"], "scenario_id": sid, "disclaimer": "Chỉ là ví dụ lịch sử, không phải bằng chứng có lãi."})

    @app.post("/class/rooms/{rid}/actions", tags=["class"])
    async def post_action(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        cmd = str(body.get("command", "")).lstrip("/")
        prm = body.get("params") or {}
        if not isinstance(prm, dict) or len(json.dumps(prm)) > 4000:
            raise HTTPException(422, "params không hợp lệ")
        okk = {"test": {"version", "mode"}, "quet": {"limit", "symbol", "tf"}, "so-sanh": {"vs"}, "ve": {"kind"}, "dat-lai": {"xacnhan"}}.get(re.sub(r"[^a-z\-]", "", cmd), set())
        kv = " ".join(f"{k}={v}" for k, v in prm.items() if k in okk and isinstance(v, (str, int, float)) and not isinstance(v, bool))
        free = clean_text(str(prm.get("note") or prm.get("topic") or ""), 200)
        try:
            it = parse_command(f"/{cmd} {kv} {free}".strip())
        except CommandError as e:
            raise HTTPException(422, str(e)) from None
        if it is None or it.command not in COMMANDS:
            raise HTTPException(422, "lệnh không có trong danh sách cho phép")
        lock = store.room_lock(rid)
        if not await asyncio.to_thread(lock.acquire, True, 20):
            raise HTTPException(429, "Phòng đang xử lý, thử lại")
        try:
            c = machine(rid)
            turn = await asyncio.to_thread(c.respond, f"/{cmd} {kv} {free}".strip(), w.name, "expert")
            if turn.intent and turn.intent.command == "ve":
                ip = turn.intent.params
                for k in ("symbol", "tf", "from_ts", "to_ts"):
                    if isinstance(prm.get(k), str) and re.fullmatch(r"[A-Za-z0-9_.:\- ]{1,32}", prm[k]):
                        ip[k] = prm[k]
                ip["points"] = [{"ts": str(p.get("ts"))[:32], "price": float(p["price"])} for p in (prm.get("points") if isinstance(prm.get("points"), list) else [])[:50]
                                if isinstance(p, dict) and isinstance(p.get("price"), (int, float)) and not isinstance(p["price"], bool)]
            am = store.add_message(rid, "text", AI, turn.reply, understanding=turn.understanding, chips=turn.chips, data={"phase": turn.phase, "notes": turn.notes})
            a = None
            if turn.intent and not turn.intent.local:
                a = await asyncio.to_thread(run_intent, rid, w, c, turn.intent)
            save(rid, c, w.uid)
            if a and a["status"] == "needs_confirm" and body.get("confirm") is True:
                store.upd_action(a["id"], status="running", message="Đang đăng ký giả thuyết")
                a = await asyncio.to_thread(start_test, rid, w, store.action(rid, a["id"]))
        finally:
            lock.release()
        store.audit(w.uid, w.role, rid, "action." + cmd, (a or {}).get("id", ""))
        code = 202 if a and a["status"] in ("needs_confirm", "queued") else 200
        return j({"action": a, "message": am, "turn": {**asdict(turn), "intent": intent_public(turn.intent)}}, code)

    @app.post("/class/rooms/{rid}/actions/{aid}/confirm", tags=["class"], status_code=202)
    async def confirm(request: Request, rid: str, aid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        a = store.action(rid, aid) if RID.match(aid) else None
        if not a or a["status"] != "needs_confirm" or a["command"] != "test":
            raise HTTPException(404, "không có action chờ xác nhận")
        async with locked(rid):
            if (store.action(rid, aid) or {}).get("status") != "needs_confirm":
                raise HTTPException(409, "action đã được xử lý")
            store.upd_action(aid, status="running", message="Đang đăng ký giả thuyết")
            out = await asyncio.to_thread(start_test, rid, w, store.action(rid, aid))
        store.audit(w.uid, w.role, rid, "action.test.confirm", aid)
        return j({"action": out}, 202)

    @app.get("/class/rooms/{rid}/actions", tags=["class"])
    async def list_actions(request: Request, rid: str):
        w = who(request)
        room_of(rid, w)
        await finalize(rid, w)
        return j({"items": store.actions(rid)})

    @app.get("/class/rooms/{rid}/actions/{aid}", tags=["class"])
    async def get_action(request: Request, rid: str, aid: str):
        w = who(request)
        room_of(rid, w)
        await finalize(rid, w)
        a = store.action(rid, aid) if RID.match(aid) else None
        if not a:
            raise HTTPException(404, "không tìm thấy action")
        job = sstore.job(a["job_id"]) if a.get("job_id") else None
        return j({**a, "progress": (job or {}).get("progress")})

    @app.post("/class/rooms/{rid}/final-test", tags=["class"], status_code=202)
    async def final_test(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        if not w.master:
            raise HTTPException(403, "Chỉ master mở được test khoá")
        wr(w)
        sid = str(body.get("scenario_id", ""))
        if not any(a.get("scenario_id") == sid for a in store.actions(rid)):
            raise HTTPException(404, "kịch bản không thuộc phòng này")
        job = enqueue(sid, "final_test", body.get("confirm"))
        a = store.add_action(rid, "final-test", "queued", {"scenario_id": sid}, w.uid, job_id=job["id"], scenario_id=sid, message="Test khoá đã được xác nhận và xếp hàng (mở 1 lần duy nhất)")
        store.audit(w.uid, w.role, rid, "final-test", sid)
        return j({"action": a, "job": job}, 202)

    # ------------------------------------------------------------------ nhãn
    def label_summary(rid: str) -> dict:
        exs, labs = store.examples(rid), store.labels(rid)
        # mỗi ví dụ lấy nhãn mới nhất (nhiều chuyên gia: nhãn cuối cùng thắng)
        last: dict[str, dict] = {}
        for lb in labs:
            last[lb["example_id"]] = lb
        n = len(last)
        score = sum(VERDICTS[lb["verdict"]] for lb in last.values())
        by_round = []
        for r in sorted({e["round"] for e in exs}):
            ids = {e["id"] for e in exs if e["round"] == r}
            ls = [lb for k, lb in last.items() if k in ids]
            by_round.append({"round": r, "n_examples": len(ids), "n": len(ls), "precision": round(sum(VERDICTS[x["verdict"]] for x in ls) / len(ls), 3) if ls else None})
        prec = round(score / n, 3) if n else None
        if not exs:
            adv = "Chưa có ví dụ: bấm “Tìm ví dụ” để AI tìm lần xuất hiện trong lịch sử."
        elif n < min(6, len(exs)):
            adv = "Gắn nhãn thêm (cần ít nhất 6 ví dụ) trước khi kết luận độ chính xác."
        elif prec is not None and prec < 0.5:
            adv = "AI hiểu chưa đúng (độ chính xác < 50%): sửa luật theo lý do các ví dụ SAI rồi bấm “Quét vòng mới”."
        else:
            adv = "Độ chính xác chấp nhận được trên mẫu nhỏ; có thể chạy test để kiểm chứng trung thực (mẫu ví dụ nhỏ, không phải bằng chứng)."
        return {"n_examples": len(exs), "n_labeled": n, "coverage": round(n / len(exs), 3) if exs else None, "precision": prec,
                "precision_strict": round(sum(1 for x in last.values() if x["verdict"] == "dung") / n, 3) if n else None,
                "by_round": by_round, "rounds": len(by_round), "advice": adv}

    @app.post("/class/rooms/{rid}/labels", tags=["class"], status_code=201)
    async def add_label(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        eid, v = str(body.get("example_id", "")), body.get("verdict")
        reason = clean_text(body.get("reason") or "", 300)
        ex = store.example(rid, eid) if EID.match(eid) else None
        if not ex or v not in VERDICTS or looks_injected(reason):
            raise HTTPException(422 if ex else 404, "example_id/verdict không hợp lệ" if ex else "không tìm thấy ví dụ")
        before = label_summary(rid)
        lab = store.add_label(rid, eid, v, reason, w.uid, ex["round"])
        _mem.label_hook(rid, w, eid, v, reason, ex.get("symbol"))
        async with locked(rid):
            c = machine(rid)
            c.profile.labels.append({"example_id": eid, "verdict": v, "reason": reason, "by": w.name, "round": ex["round"], "symbol": ex.get("symbol"), "ts": ex.get("ts")})
            if v == "sai" and reason:
                c.profile.open_questions.append("Phản ví dụ: " + reason[:120])
            if w.name not in c.profile.contributors:
                c.profile.contributors.append(w.name)
            save(rid, c, w.uid)
        sm = label_summary(rid)
        thr = min(6, sm["n_examples"])
        if before["n_labeled"] < thr <= sm["n_labeled"]:
            store.add_message(rid, "system", SYS, f"Đã gắn nhãn {sm['n_labeled']}/{sm['n_examples']} ví dụ. Độ chính xác (ĐÚNG=1, GẦN ĐÚNG=0,5): {round(100 * sm['precision'])}%; độ phủ {round(100 * sm['coverage'])}%. {sm['advice']}",
                              data={"labels_summary": sm}, chips=[{"label": "Quét vòng mới", "command": "/quet"}, {"label": "Hỏi thêm", "command": "/hoi-them"}, {"label": "Chạy test", "command": "/test"}])
        store.audit(w.uid, w.role, rid, "label." + v, eid)
        return j({"label": lab, "summary": sm}, 201)

    @app.get("/class/rooms/{rid}/labels", tags=["class"])
    async def get_labels(request: Request, rid: str):
        w = who(request)
        room_of(rid, w)
        return j({"items": store.labels(rid), "examples": store.examples(rid), "summary": label_summary(rid)})

    # ------------------------------------------------------------------ hồ sơ
    @app.get("/class/rooms/{rid}/profile", tags=["class"])
    async def get_profile(request: Request, rid: str):
        w = who(request)
        room_of(rid, w)
        c = machine(rid)
        p = c.profile.to_dict()
        return j({"profile": {k: p[k] for k in ("name", "version", "answers", "open_questions", "assumptions", "contributors", "labels", "conflicts")},
                  "understanding": c.understanding(), "versions": store.versions(rid)})

    @app.get("/class/rooms/{rid}/profile/versions/{v}", tags=["class"])
    async def get_version(request: Request, rid: str, v: int):
        w = who(request)
        room_of(rid, w)
        s = store.version(rid, v)
        if not s:
            raise HTTPException(404, "không có phiên bản")
        return j(s)

    @app.get("/class/rooms/{rid}/profile/diff", tags=["class"])
    async def get_diff(request: Request, rid: str, a: int = Query(..., ge=1), b: int = Query(..., ge=1)):
        w = who(request)
        room_of(rid, w)
        x, y = store.version(rid, a), store.version(rid, b)
        if not x or not y:
            raise HTTPException(404, "không có phiên bản")
        return j({"a": a, "b": b, "items": diff_profiles(x, y)})

    @app.post("/class/rooms/{rid}/profile/export", tags=["class"])
    async def export(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        wr(w)
        c = machine(rid)
        v = body.get("version")
        prof = c.profile
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise HTTPException(422, "version phải là số nguyên")
            s = store.version(rid, v)
            if not s:
                raise HTTPException(404, "không có phiên bản")
            from .profile import Profile
            prof = Profile.from_dict(s)
            prof.version = v
        rep = export_scenario(prof)
        out = {"ok": rep.ok, "yaml": rep.yaml, "errors": rep.errors, "warnings": rep.warnings, "registered": False}
        if rep.ok and body.get("register"):
            sid, sha = register_scenario(rep.yaml, w)
            out.update(registered=True, scenario_id=sid, sha=sha)
            store.audit(w.uid, w.role, rid, "profile.export.register", sid)
        return j(out)

    @app.get("/class/rooms/{rid}/minutes.md", tags=["class"])
    async def minutes(request: Request, rid: str):
        w = who(request)
        r = room_of(rid, w)
        await finalize(rid, w)
        c = machine(rid)
        L = [f"# Biên bản buổi học: {r['title']}", "", f"Xuất lúc {now()}. {DISCLAIMER}", "", "## Thành viên"]
        L += [f"- {m['name']} ({m['role']})" for m in r["members"]]
        L += ["", f"## Hồ sơ kịch bản: {c.profile.name} (bản đang sửa {c.profile.version})"]
        for k in c.profile.answered():
            a = c.profile.current(k)
            L.append(f"- **{k}** ({a.confidence}, {a.author}): {a.text[:300]}")
        if c.profile.open_questions:
            L += ["", "## Câu hỏi còn mở"] + [f"- {q}" for q in c.profile.open_questions[:30]]
        sm = label_summary(rid)
        L += ["", "## Nhãn ví dụ", f"- Đã gắn {sm['n_labeled']}/{sm['n_examples']}; độ chính xác {sm['precision']}; độ phủ {sm['coverage']}. {sm['advice']}", "", "## Hội thoại"]
        msgs, _ = store.messages(rid, 200)
        for m in msgs:
            L.append(f"- [{m['created_at'][:16]}] **{m['author'].get('name')}**: {m['text'][:400]}".replace("\n", " "))
            if m["kind"] == "result_card" and m.get("data"):
                mt = m["data"].get("metrics", {})
                L.append(f"  - Kết quả: {mt.get('trades')} lệnh, kỳ vọng {mt.get('expectancy_r')} R, verdict {m['data'].get('verdict')}")
        body = _SRC.sub("[nguồn]", "\n".join(L))
        return Response(body, media_type="text/markdown; charset=utf-8", headers={**NOSTORE, "Content-Disposition": 'attachment; filename="bien-ban-lop-hoc.md"'})

    return store
