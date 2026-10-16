"""Route nhận ý định tự nhiên + option gợi ý (AI Training Class): POST /class/rooms/{rid}/understand, POST /class/rooms/{rid}/options/feedback.
Chỉ THÊM (module riêng). Không có đường đặt lệnh: ý định chỉ là gợi ý đã lọc (allow-list + parse_command); việc nặng luôn cần xác nhận.
Hợp đồng: docs/handoff/INTENT_API.md."""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import re
import uuid
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import intent as I
from . import persist
from .api import NOSTORE, RID, ROLES, UID, Who, _disp, _Limiter
from .safety import clean_text
from .ux_api import build_rows, clarity

log = logging.getLogger("ai-trading.class")
OUTCOMES = ("clicked", "ignored", "not_this")
OPT_ID = re.compile(r"^u_[0-9a-f]{12}(?::[0-9]{1,2}|:intent:[a-z_]{3,24})?$")
LOG_DDL = "CREATE TABLE IF NOT EXISTS class_intent_log(id TEXT PRIMARY KEY, room_id TEXT NOT NULL, uid TEXT NOT NULL, intent TEXT, level TEXT, at TEXT NOT NULL)"
LLM_TIMEOUT_S = 3.0
_POOL = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="intent-llm")


def _llm_on() -> bool:
    return os.environ.get("CLASSROOM_INTENT_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


def register(app: FastAPI, st: Any, store: Any, llm: Any = None) -> None:
    from .store import now
    store.x(LOG_DDL)
    try:
        from . import option_rank as OR
        OR.ensure(store)
    except Exception:  # noqa: BLE001 - module Bộ nhớ chưa có: bỏ qua học, vẫn chạy
        OR = None
    rl = _Limiter(max(int(getattr(st, "class_write_rate", 60)) * 3, 120), 60.0)

    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def room_of(rid: str, w: Who) -> dict:
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            raise HTTPException(404, "không tìm thấy phòng")
        return r

    def j(data: Any, code: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers=NOSTORE)

    def room_ctx(rid: str) -> dict:
        """Ngữ cảnh phòng cho option/ thẻ xác nhận: pha, hàng hồ sơ, độ rõ, mã/khung mặc định. Lỗi -> ngữ cảnh rỗng (không chặn)."""
        try:
            c = persist.load(store.get_state(rid), rid, llm)
            cf_ = {r["row_key"]: r["text_hash"] for r in store.q("SELECT row_key,text_hash FROM class_ux_confirm WHERE room_id=?", (rid,))}
            rows = build_rows(c.profile, cf_)
            cl = clarity(rows)
            m = c.profile.merged()
            return {"phase": c.phase, "rows": {r["key"]: r["confidence"] for r in rows}, "confirmed": [r["key"] for r in rows if r["confirmed"]], "clarity": cl["score"],
                    "weakest_row": cl["weakest_row"], "next_question": cl["next_question"], "missing_required": c.profile.missing_required(),
                    "conflicts": len(c.profile.conflicts or []), "n_labels": len(c.profile.labels or []),
                    "symbol": (m.get("symbols") or [None])[0], "tf": ((m.get("tfs") or [None])[0] or "").upper() or None}
        except Exception:  # noqa: BLE001
            log.warning("understand: không đọc được ngữ cảnh phòng", exc_info=False)
            return {"phase": "intake", "rows": {}}

    def with_llm(text: str, res: dict, ctx: dict) -> bool:
        """Chỉ khi bật cờ + luật không chắc: hạn 3 s, JSON ràng buộc đã kiểm. Trả True nếu LLM thay đổi kết quả."""
        it = res["intent"]
        if not llm or not _llm_on() or res["injected"] or (it and it["level"] == "strong") or res["ntokens"] < 2:
            return False
        fut = _POOL.submit(I.llm_classify, llm, text)
        try:
            d = fut.result(timeout=LLM_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - quá hạn/ lỗi: bỏ LLM
            return False
        if not d or d["confidence"] < I.WEAK or (it and it["confidence"] >= d["confidence"]):
            return False
        params = {**(res.get("params") or {})}
        for k in ("symbol", "tf"):
            if d.get(k):
                params[k] = d[k]
        key = d["intent"]
        ct, notes = I.build_command(key, params)
        spec = I.INTENTS[key]
        vi, en = I.label_for(key, params, ctx)
        res["intent"] = {"key": key, "command": spec["command"], "action": spec["command"] or "ui:" + spec.get("ui", ""), "label_vi": vi, "label_en": en, "confidence": d["confidence"], "level": "strong" if d["confidence"] >= I.STRONG else "weak",
                         "heavy": spec["heavy"], "params": {k: v for k, v in params.items() if k in ("symbol", "tf", "period", "vs", "vs_name", "row", "kind")}, "command_text": ct, "ui": spec.get("ui"), "notes": notes,
                         "auto_run": False}   # kết quả LLM không bao giờ tự chạy
        res["highlights"] = []
        return True

    @app.post("/class/rooms/{rid}/understand", tags=["class-intent"])
    async def understand(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        if not rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        text = body.get("text", "")
        if text is None:
            text = ""
        if not isinstance(text, str) or len(text) > 6000:
            raise HTTPException(422, "text không hợp lệ")
        uid = "u_" + uuid.uuid4().hex[:12]
        ctx = room_ctx(rid)
        try:
            res = I.detect(text, ctx)
            llm_used = with_llm(res["text"], res, ctx) if body.get("use_llm", True) else False
        except Exception:  # noqa: BLE001 - lỗi bộ nhận ý định không được chặn chat
            log.warning("understand: lỗi nhận ý định", exc_info=True)
            res, llm_used = {"text": clean_text(text, 200), "injected": False, "intent": None, "alternatives": [], "highlights": [], "ntokens": 0}, False
        it = res["intent"]
        u_vi, u_en = I.understood_text(it, res.get("params") or {})
        card = I.build_card(it, ctx, uid) if it else None
        if it and it["level"] == "weak":
            card = None   # ý định yếu: chỉ hỏi lại bằng option, không dựng thẻ chạy việc nặng
        stats = {}
        if OR:
            try:
                stats = OR.load_stats(store, w.uid)
            except Exception:  # noqa: BLE001
                stats = {}
        cands = I.build_options(ctx, it if (it and it["level"] == "strong") else None, uid, res["alternatives"] if not (it and it["level"] == "strong") else [])
        rctx = {"rows": ctx.get("rows") or {}, "confirmed": ctx.get("confirmed") or [], "text": res["text"], "intent": it["key"] if it else None}
        opts = I.rank_options(cands, rctx, stats, top=4)
        for n, o in enumerate(opts):
            o["id"] = f"{uid}:{n + 1}"
        try:
            store.x("INSERT INTO class_intent_log(id,room_id,uid,intent,level,at) VALUES(?,?,?,?,?,?)", (uid, rid, w.uid, it["key"] if it else None, it["level"] if it else None, now()))
            if OR:
                for n, o in enumerate(opts):
                    OR.record_feedback(store, rid, w.uid, o["id"], o["kind"], "shown", n + 1)
        except Exception:  # noqa: BLE001 - không ghi được nhật ký thì thôi
            pass
        pub_it = None
        if it:
            pub_it = {k: v for k, v in it.items()}
        for o in opts:
            for k in ("base", "parts", "tags", "label"):
                o.pop(k, None)
        return j({"id": uid, "text": res["text"], "injected": res["injected"], "llm_used": llm_used, "intent": pub_it, "alternatives": res["alternatives"], "highlights": res["highlights"],
                  "understood_vi": u_vi, "understood_en": u_en, "confirm_card": card, "options": opts,
                  "paper_only": True})

    @app.post("/class/rooms/{rid}/options/feedback", tags=["class-intent"])
    async def feedback(request: Request, rid: str, body: dict):
        w = who(request)
        room_of(rid, w)
        if not rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        oid, outcome = body.get("option_id"), body.get("outcome")
        if not isinstance(oid, str) or not OPT_ID.match(oid):
            raise HTTPException(422, "option_id không hợp lệ")
        if outcome not in OUTCOMES:
            raise HTTPException(422, "outcome phải là clicked|ignored|not_this")
        uid = oid.split(":")[0]
        row = store.q("SELECT room_id,uid FROM class_intent_log WHERE id=?", (uid,))
        if not row or row[0]["room_id"] != rid or row[0]["uid"] != w.uid:
            raise HTTPException(404, "không tìm thấy lượt gợi ý")      # chỉ phản hồi được lượt của chính mình trong phòng đó
        kind = oid.split(":")[2] if ":intent:" in oid else None
        if not kind:
            k = body.get("kind")
            kind = k if isinstance(k, str) and re.fullmatch(r"[a-z_]{3,16}", k) else "action"
        else:
            kind = (I.INTENTS.get(kind) or {}).get("kind", "action")
        if OR:
            OR.record_feedback(store, rid, w.uid, oid, kind[:40], outcome)
        store.audit(w.uid, w.role, rid, "intent." + outcome, oid[:40])
        return j({"ok": True})
