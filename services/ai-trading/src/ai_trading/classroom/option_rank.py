"""Xếp hạng option/ gợi ý học được cho AI Training Class (M3). Chỉ THÊM, không sửa module khác.

Điểm = w_info*giá trị thông tin + w_ctx*độ phù hợp ngữ cảnh + w_bandit*xác suất được chấp nhận (Thompson/ UCB theo LOẠI option,
trộn lịch sử chuyên gia + lớp) - w_cost*chi phí (việc nặng xếp sau). Có giải thích "vì sao gợi ý này".
Đây là bộ xếp hạng thống kê nhẹ, KHÔNG phải huấn luyện lại model. Không chạy lệnh nào; chỉ chọn thứ tự hiển thị.

Giao diện cho agent intent:  rank(options, context, stats, *, top=4, mode="thompson", seed=None) -> list[dict]
  option  : {id, kind, label, row_key?, heavy?: bool|0..1, tags?: [str]}
  context : {rows: {row_key: "trống"|"thấp"|"vừa"|"cao"}, confirmed?: [row_key], text?: str, intent?: str, kinds_boost?: [kind]}
  stats   : load_stats(store, uid)  ->  {"expert": {kind: {shown, clicked, ignored, not_this}}, "class": {...}}
  ra      : option + {score, parts:{info,ctx,bandit,cost}, why:[str], why_en:[str]}   (đã sắp giảm dần, cắt top)
"""
from __future__ import annotations

import math
import random
import re
import unicodedata
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .store import now

DDL = (
    "CREATE TABLE IF NOT EXISTS class_option_feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT NOT NULL, uid TEXT NOT NULL, "
    "option_id TEXT NOT NULL, kind TEXT NOT NULL, outcome TEXT NOT NULL, rank_pos INTEGER, at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS ix_opt_fb_uid ON class_option_feedback(uid, kind)",
    "CREATE INDEX IF NOT EXISTS ix_opt_fb_room ON class_option_feedback(room_id)",
)
OUTCOMES = ("shown", "clicked", "ignored", "not_this")
W = {"info": 0.40, "ctx": 0.20, "bandit": 0.30, "cost": 0.10}
CONF_GAP = {"trống": 1.0, "thấp": 0.7, "vừa": 0.35, "cao": 0.05}
PRIOR_A, PRIOR_B = 2.0, 3.0            # prior Beta(2,3): kỳ vọng ban đầu 0.4, khiêm tốn
CLASS_WEIGHT = 0.35                    # lịch sử lớp tính nhẹ hơn lịch sử chuyên gia này
IMPLICIT_MISS = 0.25                   # trọng số 'hiển thị nhưng không bấm'
NOT_THIS_PENALTY = 1.5                 # "không phải ý này" nặng hơn bỏ qua
KIND_VI = {"question": "câu hỏi tiếp theo", "clarify": "làm rõ hàng mơ hồ", "variant": "biến thể", "symmetry": "bản đối xứng",
           "compare": "so sánh", "action": "hành động", "test": "kiểm thử", "scan": "quét lịch sử", "counter": "phản ví dụ"}
_TOK = re.compile(r"[a-z0-9]{2,}")


def ensure(store) -> None:
    for d in DDL:
        store.x(d)


def _norm(t: str) -> set[str]:
    s = unicodedata.normalize("NFD", str(t or "").lower().replace("đ", "d"))
    return set(_TOK.findall("".join(c for c in s if unicodedata.category(c) != "Mn")))


def record_feedback(store, room_id: str, uid: str, option_id: str, kind: str, outcome: str, rank_pos: int | None = None) -> int:
    """Lưu kết quả bấm/ bỏ qua/ 'không phải ý này' (agent intent gọi từ POST rooms/{rid}/options/feedback)."""
    if outcome not in OUTCOMES:
        raise ValueError("outcome không hợp lệ")
    ensure(store)
    return store.x("INSERT INTO class_option_feedback(room_id,uid,option_id,kind,outcome,rank_pos,at) VALUES(?,?,?,?,?,?,?)",
                   (room_id, uid, str(option_id)[:80], str(kind)[:40], outcome, rank_pos, now()))


def _fold(rows) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        d = out.setdefault(r["kind"], {"shown": 0, "clicked": 0, "ignored": 0, "not_this": 0})
        d[r["outcome"]] = d.get(r["outcome"], 0) + r["n"]
    return out


def load_stats(store, uid: str | None = None) -> dict[str, dict]:
    ensure(store)
    cls = _fold(store.q("SELECT kind,outcome,COUNT(*) n FROM class_option_feedback GROUP BY kind,outcome"))
    exp = _fold(store.q("SELECT kind,outcome,COUNT(*) n FROM class_option_feedback WHERE uid=? GROUP BY kind,outcome", (uid,))) if uid else {}
    return {"expert": exp, "class": cls}


def posterior(kind: str, stats: dict | None) -> tuple[float, float, dict]:
    """Beta(a,b) cho loại option. Chấp nhận = bấm; thất bại = bỏ qua + 'không phải ý này' (nặng hơn). 'shown' không tự là thất bại."""
    a, b = PRIOR_A, PRIOR_B
    used = {}
    for src, wgt in (("class", CLASS_WEIGHT), ("expert", 1.0)):
        s = ((stats or {}).get(src) or {}).get(kind) or {}
        c, i, n = s.get("clicked", 0), s.get("ignored", 0), s.get("not_this", 0)
        unresolved = max(0, s.get("shown", 0) - c - i - n)     # hiển thị mà không bấm gì: tín hiệu âm yếu (người dùng có thể đã trả lời bằng chữ)
        a += wgt * c
        b += wgt * (i + NOT_THIS_PENALTY * n + IMPLICIT_MISS * unresolved)
        used[src] = {"clicked": c, "ignored": i, "not_this": n, "shown": s.get("shown", 0)}
    return a, b, used


def _bandit(kind: str, stats, mode: str, rng: random.Random) -> tuple[float, float, dict]:
    a, b, used = posterior(kind, stats)
    mean = a / (a + b)
    n = a + b - PRIOR_A - PRIOR_B
    if mode == "thompson":
        v = rng.betavariate(a, b)
    elif mode == "ucb":
        v = min(1.0, mean + math.sqrt(2 * math.log(2 + n) / (1 + n)) * 0.25)
    else:                                  # "mean": xác định, dùng cho giải thích/ test
        v = mean
    return v, mean, used


def _info(opt: dict, ctx: dict) -> tuple[float, str, str]:
    rows = ctx.get("rows") or {}
    rk = opt.get("row_key")
    if rk and rk in rows:
        conf = rows[rk]
        gap = CONF_GAP.get(conf, 0.5)
        if rk in (ctx.get("confirmed") or []):
            gap *= 0.3
        if conf == "trống":
            return gap, "hàng hồ sơ này còn trống", "this profile row is still empty"
        if conf == "thấp":
            return gap, "hàng hồ sơ này còn mơ hồ", "this profile row is still vague"
        if gap > 0.3:
            return gap, "hàng hồ sơ này chưa chắc chắn", "this row is not settled yet"
        return gap, "hàng hồ sơ này đã khá rõ", "this row is already fairly clear"
    if rk:
        return 0.3, "chưa rõ hàng hồ sơ liên quan", "related profile row unknown"
    return 0.25, "không gắn hàng hồ sơ cụ thể", "not tied to a specific profile row"


def _ctx(opt: dict, ctx: dict) -> tuple[float, str, str]:
    base = _norm(ctx.get("text", ""))
    ot = _norm(opt.get("label", "")) | _norm(" ".join(opt.get("tags") or []))
    ov = len(base & ot) / max(1, min(len(ot), 6)) if base and ot else 0.0
    s = min(1.0, ov * 1.5)
    boost = opt.get("kind") in (ctx.get("kinds_boost") or []) or (ctx.get("intent") and ctx["intent"] == opt.get("intent"))
    if boost:
        s = min(1.0, s + 0.5)
    why = "khớp điều bạn vừa nói/ ý định" if s >= 0.4 else "liên quan nhẹ tới câu vừa rồi"
    return s, why, ("matches what you just said / the intent" if s >= 0.4 else "loosely related to the last message")


def _cost(opt: dict) -> float:
    h = opt.get("heavy", 0)
    return 1.0 if h is True else float(h or 0)


def rank(options: list[dict], context: dict | None, stats: dict | None, *, top: int | None = 4, mode: str = "thompson", seed: int | None = None) -> list[dict]:
    """Sắp xếp option giảm dần theo điểm. mode: thompson | ucb | mean (xác định). Option hỏng (thiếu id) bị bỏ, id trùng giữ bản đầu."""
    ctx = context or {}
    rng = random.Random(seed)
    seen, res = set(), []
    for o in options or []:
        if not isinstance(o, dict) or not o.get("id") or o["id"] in seen:
            continue
        seen.add(o["id"])
        kind = o.get("kind") or "action"
        info, iw, ie = _info(o, ctx)
        cx, cw, ce = _ctx(o, ctx)
        bv, mean, used = _bandit(kind, stats, mode, rng)
        cost = _cost(o)
        parts = {"info": round(info, 3), "ctx": round(cx, 3), "bandit": round(bv, 3), "cost": round(cost, 3)}
        score = W["info"] * info + W["ctx"] * cx + W["bandit"] * bv - W["cost"] * cost
        e_c, c_c = used["expert"], used["class"]
        hist_vi = hist_en = None
        if e_c.get('clicked', 0) + e_c.get('ignored', 0) + e_c.get('not_this', 0) + c_c.get('clicked', 0) + c_c.get('ignored', 0) + c_c.get('not_this', 0) + e_c.get('shown', 0) + c_c.get('shown', 0):
            hist_vi = f"loại '{KIND_VI.get(kind, kind)}': bạn bấm {e_c['clicked']}, bỏ qua {e_c['ignored']}; lớp bấm {c_c['clicked']}, bỏ qua {c_c['ignored']}"
            hist_en = f"kind '{kind}': you clicked {e_c['clicked']}, ignored {e_c['ignored']}; class clicked {c_c['clicked']}, ignored {c_c['ignored']}"
        else:
            hist_vi, hist_en = "chưa có lịch sử cho loại này, đang thử", "no history for this kind yet, exploring"
        why = [iw, cw, hist_vi] + (["việc nặng nên xếp sau"] if cost >= 0.5 else [])
        why_en = [ie, ce, hist_en] + (["heavy task, ranked later"] if cost >= 0.5 else [])
        res.append({**o, "kind": kind, "score": round(score, 4), "parts": parts, "p_accept": round(mean, 3), "why": why, "why_en": why_en})
    res.sort(key=lambda x: (-x["score"], x["id"]))
    for i, r in enumerate(res):
        r["rank"] = i + 1
    return res[:top] if top else res


def explain(opt: dict) -> dict:
    """Văn bản 'vì sao gợi ý này' từ kết quả rank()."""
    return {"id": opt.get("id"), "score": opt.get("score"), "parts": opt.get("parts"), "why": opt.get("why", []), "why_en": opt.get("why_en", []),
            "weights": W, "note": "Xếp hạng thống kê nhẹ từ lịch sử bấm của bạn và của lớp; không phải huấn luyện lại model."}


def summary(store, uid: str | None = None) -> dict:
    """Số liệu cho UI: tỉ lệ chấp nhận theo loại option (chuyên gia + lớp)."""
    st = load_stats(store, uid)
    out = []
    for kind in sorted(set(st["class"]) | set(st["expert"])):
        a, b, _ = posterior(kind, st)
        c = st["class"].get(kind, {})
        shown = c.get("clicked", 0) + c.get("ignored", 0) + c.get("not_this", 0)
        out.append({"kind": kind, "label": KIND_VI.get(kind, kind), "p_accept": round(a / (a + b), 3), "events": shown, "clicked": c.get("clicked", 0)})
    return {"kinds": out, "total": sum(k["events"] for k in out)}


def register(app, store) -> None:
    """GET /class/options/stats (cho UI giải thích). POST feedback do agent intent làm, gọi record_feedback()."""
    from .api import NOSTORE, ROLES, UID

    @app.get("/class/options/stats", tags=["class-options"])
    async def options_stats(request: Request):
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return JSONResponse({"mine": summary(store, uid), "class": summary(store, None), "weights": W}, headers=NOSTORE)
