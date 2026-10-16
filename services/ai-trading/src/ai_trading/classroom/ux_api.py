"""API UX bổ sung cho AI Training Class: canvas 16 hàng + độ rõ ý tưởng, xác nhận/sửa hàng, mẫu khởi tạo, kịch bản demo ghi sẵn.
Chỉ THÊM (không sửa api.py/store.py). CHỈ nghiên cứu/paper. Hợp đồng: docs/handoff/UX_API.md."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import persist
from .api import NOSTORE, RID, Who, _Limiter, _disp, DISCLAIMER, ROLES, UID
from .checklist import BY_KEY
from .safety import clean_text, looks_injected
from .store import now
from urllib.parse import unquote

MAXEDIT = 1000
# (key, tiêu đề vi, tiêu đề en, khoá checklist nguồn, hàng định lượng?)
ROWS: tuple[tuple[str, str, str, str | None, bool], ...] = (
    ("context", "Bối cảnh & xu hướng lớn", "Context & higher trend", "context", False),
    ("symbol_tf", "Mã & khung", "Symbol & timeframe", "symbol_tf", False),
    ("formation", "Các bước hình thành", "Formation steps", "formation", True),
    ("trigger", "Điểm kích hoạt", "Entry trigger", "trigger", True),
    ("invalidation", "Điều kiện HUỶ", "Invalidation", "invalidation", True),
    ("sl", "SL", "Stop loss", "sl_tp", True),
    ("tp", "TP / quản lý lệnh", "TP / trade management", "sl_tp", True),
    ("sizing", "Khối lượng & rủi ro", "Size & risk", "sizing", True),
    ("filters", "Bộ lọc", "Filters", "filters", True),
    ("ex_ok", "Ví dụ ĐÚNG", "Correct examples", "examples", False),
    ("ex_bad", "Ví dụ SAI / gần giống", "Wrong / look-alike examples", "examples", False),
    ("failure", "Điều gì làm thất bại", "What makes it fail", "failure", False),
    ("symmetry", "Phiên bản đối xứng", "Symmetric version", "symmetry", False),
    ("rationale", "Lý do kinh tế / tâm lý", "Economic / psychological rationale", "rationale", False),
    ("assumptions", "Giả định ngầm", "Implicit assumptions", None, False),
    ("open_questions", "Câu hỏi còn mở", "Open questions", None, False),
)
ROW_KEYS = tuple(r[0] for r in ROWS)
CORE = tuple(r[0] for r in ROWS[:14])
EDITABLE = {r[0]: r[3] for r in ROWS if r[3]}
CONF_VAL = {"cao": 0.85, "vừa": 0.6, "thấp": 0.3, "trống": 0.0}
_BAD = re.compile(r"(?i)(gần giống|gan giong|không vào|khong vao|\bsai\b|loại)")
FLAG_DDL = "CREATE TABLE IF NOT EXISTS class_ux_confirm(room_id TEXT NOT NULL, row_key TEXT NOT NULL, text_hash TEXT NOT NULL, by_user TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY(room_id,row_key))"


def _h(t: str) -> str:
    return hashlib.sha1((t or "").encode()).hexdigest()[:16]


def _sl_tp_text(a, key: str) -> str:
    """Hàng sl/tp dùng chung một câu trả lời; nêu thêm phần AI hiểu từ levels."""
    lv = (a.fields or {}).get("levels", {}) if a else {}
    if key == "sl" and lv.get("sl"):
        s = lv["sl"]
        return "SL: " + ", ".join(f"{k}={v}" for k, v in s.items())
    if key == "tp":
        parts = []
        if lv.get("tp_r"):
            parts.append("TP " + "/".join(str(x) for x in lv["tp_r"]) + "R")
        if lv.get("max_hold"):
            parts.append(f"giữ tối đa {lv['max_hold']} nến")
        return "; ".join(parts)
    return ""


def build_rows(profile, confirms: dict[str, str]) -> list[dict]:
    labels = profile.labels or []
    rows = []
    for key, tvi, ten, src, quant in ROWS:
        text, conf, author, turn, fields, ai = "", "trống", None, None, {}, ""
        has_ex = False
        if src:
            a = profile.current(src)
            if a:
                text, conf, author, fields = a.text.strip(), a.confidence, a.author, a.fields or {}
                turn = len([x for x in profile.answers.get(src, []) if not x.skipped])
                ai = _sl_tp_text(a, key) or text[:200]
        elif key == "assumptions":
            xs = [f"{x.get('text') or x.get('question', '')}".strip() for x in profile.assumptions if x.get("status") != "rejected"]
            text = "\n".join(f"- {x}" for x in xs if x)
            conf = "thấp" if text else "trống"
            ai = f"AI đang giả định {len(xs)} điều chưa được xác nhận." if xs else ""
        else:
            xs = [q for q in profile.open_questions if q]
            text = "\n".join(f"- {q}" for q in xs)
            conf = "thấp" if text else "trống"
            ai = f"Còn {len(xs)} câu hỏi mở." if xs else ""
        if key == "ex_ok":
            ok = [lb for lb in labels if lb.get("verdict") == "dung"]
            has_ex = bool(text) or bool(ok)
            if ok:
                text = (text + "\n" if text else "") + f"Nhãn ĐÚNG đã gắn: {len(ok)}"
                conf = conf if conf != "trống" else "vừa"
        elif key == "ex_bad":
            bad = [lb for lb in labels if lb.get("verdict") in ("sai", "gan_dung")]
            a = profile.current("examples")
            has_ex = bool(bad) or bool(a and _BAD.search(a.text or ""))
            if not has_ex:
                text, conf, author, turn, ai = "", "trống", None, None, ""
            elif bad:
                lines = [f"- {lb.get('reason') or '(không lý do)'}" for lb in bad[:5]]
                text = (text + "\n" if text else "") + "Nhãn SAI/gần đúng:\n" + "\n".join(lines)
                conf = conf if conf != "trống" else "vừa"
        quantified = bool(fields.get("numbers") or fields.get("levels") or fields.get("rules")) if key not in ("assumptions", "open_questions") else False
        confirmed = bool(text) and confirms.get(key) == _h(text)
        rows.append({"key": key, "title_vi": tvi, "title_en": ten, "text": text, "confidence": conf,
                     "source": {"author": author, **({"turn": turn} if turn else {})}, "confirmed": confirmed, "quantified": quantified,
                     "has_examples": has_ex, "ai_understanding": ai or ("AI chưa hiểu mục này." if not text else text[:200]), "editable": key in EDITABLE})
    return rows


def clarity(rows: list[dict]) -> dict:
    core = [r for r in rows if r["key"] in CORE]
    n = len(core)
    qkeys = [r[0] for r in ROWS if r[4]]
    filled = sum(1 for r in core if r["confidence"] != "trống") / n
    confirmed = sum(1 for r in core if r["confirmed"]) / n
    quantified = sum(1 for r in core if r["key"] in qkeys and r["quantified"]) / len(qkeys)
    ex = {r["key"]: r for r in core}
    examples = (0.5 * (ex["ex_ok"]["confidence"] != "trống" and ex["ex_ok"]["has_examples"]) + 0.5 * ex["ex_bad"]["has_examples"])
    score = round(100 * (0.2 * filled + 0.3 * confirmed + 0.3 * quantified + 0.2 * examples))

    def rs(r: dict) -> float:
        return CONF_VAL[r["confidence"]] + (0.15 if r["confirmed"] else 0) + (0.1 if r["quantified"] else 0)
    weakest = min(core, key=lambda r: (rs(r), CORE.index(r["key"])))
    src = EDITABLE.get(weakest["key"])
    if src and not weakest["text"]:
        nq = BY_KEY[src].questions[0]
    elif src:
        nq = BY_KEY[src].followup
    else:
        nq = "Hãy mô tả thêm về mục này."
    return {"score": score, "breakdown": {"filled": round(filled, 3), "confirmed": round(confirmed, 3), "quantified": round(quantified, 3), "examples": round(examples, 3)},
            "weakest_row": weakest["key"], "next_question": nq}


# ---------------------------------------------------------------------- mẫu
def _tpl(i, nvi, nen, bvi, ben, ans):
    return {"id": i, "name_vi": nvi, "name_en": nen, "brief_vi": bvi, "brief_en": ben, "answers": ans}


TEMPLATES = [
    _tpl("breakout", "Phá vỡ (breakout)", "Breakout",
         "Kịch bản phá vỡ vùng tích luỹ. Giá đi ngang ít nhất 20 nến với biên độ dưới 1,5 ATR. Vào lệnh khi nến đóng cửa vượt biên vùng, mô phỏng, không đặt lệnh thật.",
         "Range breakout scenario. Price consolidates for at least 20 candles within 1.5 ATR. Enter (simulated only) when a candle closes beyond the range edge.",
         {"context": "Thị trường đi ngang sau một xu hướng, biến động thu hẹp.", "symbol_tf": "EURUSD khung H1, lọc bằng H4.",
          "formation": "Vùng đi ngang tối thiểu 20 nến, biên độ dưới 1,5 ATR, chạm biên ít nhất 2 lần mỗi phía.",
          "trigger": "Nến đóng cửa vượt biên vùng ít nhất 0,2 ATR, vào ở mở nến kế tiếp.",
          "invalidation": "Giá đóng cửa quay lại trong vùng trong vòng 3 nến thì huỷ.",
          "sl": "SL ở biên đối diện của vùng, TP 2R, giữ tối đa 30 nến.", "sizing": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh.",
          "failure": "Phá vỡ giả khi thanh khoản thấp (phiên Á)."}),
    _tpl("three_lower_highs", "3 đỉnh giảm dần rồi nến nén (Sell)", "Three lower highs then compression candle (Sell)",
         "Trong vùng đi ngang xuất hiện 3 đỉnh giảm dần liên tiếp. Sau đó có nến nén thân nhỏ dưới 30% biên độ. Vào Sell mô phỏng khi nến đóng cửa phá đáy nến nén.",
         "Inside a range, three consecutive lower highs form. A small-body compression candle (under 30% of range) follows. Simulated Sell on a close below the compression low.",
         {"context": "Vùng đi ngang sau nhịp giảm, xu hướng lớn H4 giảm hoặc trung tính.", "symbol_tf": "EURUSD H1.",
          "formation": "3 đỉnh giảm dần cách nhau 4-10 nến, mỗi đỉnh thấp hơn đỉnh trước ít nhất 0,1 ATR, rồi 1 nến thân dưới 30% biên độ.",
          "trigger": "Nến đóng cửa dưới đáy nến nén, vào ở mở nến kế tiếp.",
          "invalidation": "Giá đóng cửa trên đỉnh thứ nhất của chuỗi thì huỷ.",
          "sl": "SL trên đỉnh 6 nến + 0,25 ATR, TP 2R, giữ tối đa 24 nến.", "sizing": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh.",
          "symmetry": "Bản Buy: 3 đáy tăng dần rồi nến nén, vào khi phá đỉnh nến nén.", "rationale": "Bên mua yếu dần, bên bán bán ra sớm hơn ở mỗi nhịp hồi."}),
    _tpl("supply_demand", "Vùng cung - cầu", "Supply / demand zone",
         "Giá quay lại vùng cung (hoặc cầu) vừa tạo ra một nhịp đẩy mạnh. Vùng là thân nến cuối trước nhịp đẩy trên 2 ATR. Vào mô phỏng khi giá chạm lại vùng và có nến đảo chiều.",
         "Price returns to a supply (or demand) zone that launched a strong impulse. The zone is the last base candle before a 2+ ATR move. Simulated entry on retest with a reversal candle.",
         {"context": "Có nhịp đẩy mạnh rời khỏi vùng, chưa bị chạm lại.", "symbol_tf": "GBPUSD H1, vùng xác định từ H4.",
          "formation": "Nến cơ sở cuối cùng trước nhịp đẩy trên 2 ATR trong tối đa 5 nến; vùng chưa bị chạm lại.",
          "trigger": "Giá chạm lại vùng và đóng cửa nến đảo chiều thân trên 50% biên độ.",
          "invalidation": "Giá đóng cửa xuyên hẳn qua vùng thì huỷ.", "sl": "SL qua mép xa của vùng + 0,25 ATR, TP 2R.",
          "rationale": "Lệnh chờ lớn chưa khớp còn lại ở vùng, cung cầu mất cân bằng."}),
    _tpl("trend_pullback", "Pullback theo xu hướng", "Trend pullback",
         "Xu hướng rõ (giá trên EMA 50 và EMA dốc lên). Giá hồi không quá 50% nhịp đẩy gần nhất. Vào mô phỏng khi nến xác nhận tiếp tục xu hướng.",
         "Clear trend (price above a rising 50 EMA). Price pulls back no more than 50% of the last impulse. Simulated entry on a continuation confirmation candle.",
         {"context": "Xu hướng tăng H4: giá trên EMA 50, EMA dốc lên.", "symbol_tf": "EURUSD H1.",
          "formation": "Nhịp đẩy 2 ATR trong 6 nến, hồi không quá 50% nhịp đẩy trong 3-8 nến.",
          "trigger": "Nến đóng cửa trên đỉnh nến trước sau khi hồi, vào ở mở nến kế tiếp.",
          "invalidation": "Giá đóng cửa dưới 61,8% nhịp đẩy thì huỷ.", "sl": "SL dưới đáy hồi - 0,25 ATR, TP 2R.",
          "filters": "Chỉ phiên London và New York (07:00-20:00 UTC), spread dưới 1,5 pip."}),
    _tpl("blank", "Trống", "Blank", "Bắt đầu từ đầu: hãy mô tả kịch bản bằng 3 câu (mã, khung, điều kiện hình thành).",
         "Start from scratch: describe the scenario in 3 sentences (symbol, timeframe, formation rule).", {}),
]


# ---------------------------------------------------------------------- demo ghi sẵn
def _c(seq):
    return [list(map(float, x)) for x in seq]


DEMO = {
    "illustrative": True, "label_vi": "Minh hoạ", "label_en": "Illustrative",
    "title_vi": "Buổi học mẫu: 3 đỉnh giảm dần trong vùng đi ngang rồi nến nén -> Sell", "title_en": "Sample session: three lower highs in a range, then a compression candle -> Sell",
    "disclaimer_vi": "Toàn bộ nội dung và con số trong buổi này là MINH HOẠ, không phải dữ liệu hay kết quả thật. Chỉ nghiên cứu và mô phỏng, không đặt lệnh thật.",
    "disclaimer_en": "Everything here is ILLUSTRATIVE, not real data or results. Research and simulation only; no real orders.",
    "steps": [
        {"id": 1, "kind": "chat", "title_vi": "Mô tả kịch bản bằng 3 câu", "title_en": "Describe the idea in 3 sentences", "clarity": 10,
         "messages": [{"role": "user", "text_vi": "Trên EURUSD H1, trong vùng đi ngang xuất hiện 3 đỉnh giảm dần, sau đó một nến nén nhỏ. Tôi muốn Sell khi nến phá đáy nến nén.", "text_en": "On EURUSD H1, inside a range three lower highs form, then a small compression candle. I want to Sell when price breaks the compression low."},
                      {"role": "ai", "text_vi": "Em hiểu sơ bộ: Sell đảo chiều trong vùng đi ngang. 'Đi ngang' kéo dài bao nhiêu nến và biên độ tối đa bao nhiêu ATR?", "text_en": "Rough understanding: reversal Sell inside a range. How many candles must the range last, and what is the maximum amplitude in ATR?"}],
         "canvas_patch": {"symbol_tf": {"text": "EURUSD H1", "confidence": "vừa", "confirmed": False}, "trigger": {"text": "Sell khi nến phá đáy nến nén", "confidence": "thấp", "confirmed": False}}},
        {"id": 2, "kind": "chat", "title_vi": "Làm rõ bằng số", "title_en": "Clarify with numbers", "clarity": 30,
         "messages": [{"role": "user", "text_vi": "Vùng đi ngang tối thiểu 20 nến, biên độ dưới 1,5 ATR. 3 đỉnh giảm dần cách nhau 4-10 nến. Nến nén có thân dưới 30% biên độ.", "text_en": "Range of at least 20 candles, amplitude under 1.5 ATR. The three lower highs are 4-10 candles apart. The compression candle body is under 30% of its range."},
                      {"role": "ai", "text_vi": "Đã ghi. Còn điều kiện HUỶ: khi nào bỏ kịch bản?", "text_en": "Noted. What about invalidation: when is the idea dropped?"}],
         "canvas_patch": {"formation": {"text": "Vùng đi ngang >= 20 nến, biên độ < 1,5 ATR; 3 đỉnh giảm dần cách 4-10 nến; nến nén thân < 30% biên độ", "confidence": "cao", "confirmed": False}}},
        {"id": 3, "kind": "chat", "title_vi": "Điều kiện huỷ, SL, TP", "title_en": "Invalidation, SL, TP", "clarity": 50,
         "messages": [{"role": "user", "text_vi": "Huỷ nếu giá đóng cửa trên đỉnh thứ nhất. SL trên đỉnh 6 nến + 0,25 ATR, TP 2R, giữ tối đa 24 nến. Rủi ro 0,5% mỗi lệnh.", "text_en": "Cancel if price closes above the first high. SL above the 6-candle high + 0.25 ATR, TP 2R, max hold 24 candles. Risk 0.5% per trade."}],
         "canvas_patch": {"invalidation": {"text": "Đóng cửa trên đỉnh thứ nhất thì huỷ", "confidence": "cao", "confirmed": True},
                          "sl": {"text": "Trên đỉnh 6 nến + 0,25 ATR", "confidence": "cao", "confirmed": True}, "tp": {"text": "2R, giữ tối đa 24 nến", "confidence": "cao", "confirmed": True},
                          "sizing": {"text": "0,5% vốn mô phỏng mỗi lệnh", "confidence": "cao", "confirmed": True}}},
        {"id": 4, "kind": "example", "title_vi": "Ví dụ ĐÚNG và ví dụ SAI", "title_en": "Correct and wrong examples", "clarity": 62,
         "messages": [{"role": "user", "text_vi": "Ví dụ đúng: 3 đỉnh giảm đều rồi nến nén nhỏ. Ví dụ sai: đỉnh thứ 3 cao hơn đỉnh thứ 2, trông giống nhưng không vào lệnh.", "text_en": "Correct: three steadily lower highs then a small candle. Wrong: the third high is above the second; looks similar but no entry."}],
         "examples": [{"verdict": "dung", "description_vi": "Đỉnh 1.0850 > 1.0842 > 1.0834, nến nén thân nhỏ, phá đáy (dữ liệu nến tổng hợp)", "candles": _c([(1.0830, 1.0850, 1.0826, 1.0846), (1.0846, 1.0848, 1.0832, 1.0836), (1.0836, 1.0842, 1.0828, 1.0838), (1.0838, 1.0840, 1.0830, 1.0832), (1.0832, 1.0834, 1.0826, 1.0830), (1.0830, 1.0832, 1.0828, 1.0829), (1.0829, 1.0830, 1.0818, 1.0820)])},
                      {"verdict": "sai", "description_vi": "Đỉnh thứ 3 cao hơn đỉnh thứ 2 nên không phải chuỗi giảm dần (dữ liệu nến tổng hợp)", "candles": _c([(1.0830, 1.0850, 1.0826, 1.0846), (1.0846, 1.0848, 1.0832, 1.0836), (1.0836, 1.0842, 1.0828, 1.0838), (1.0838, 1.0846, 1.0834, 1.0840), (1.0840, 1.0841, 1.0832, 1.0834), (1.0834, 1.0836, 1.0832, 1.0835)])}],
         "canvas_patch": {"ex_ok": {"text": "3 đỉnh giảm đều rồi nến nén nhỏ", "confidence": "cao", "confirmed": True}, "ex_bad": {"text": "Đỉnh 3 cao hơn đỉnh 2: không vào lệnh", "confidence": "cao", "confirmed": True}}},
        {"id": 5, "kind": "canvas", "title_vi": "Lý do, thất bại, đối xứng, bộ lọc", "title_en": "Rationale, failure, symmetry, filters", "clarity": 78,
         "messages": [{"role": "user", "text_vi": "Bên mua yếu dần nên đỉnh thấp dần. Thất bại khi có tin mạnh. Bản Buy: 3 đáy tăng dần. Chỉ phiên London/NY, spread dưới 1,5 pip.", "text_en": "Buyers weaken so highs fall. Fails around strong news. Buy version: three higher lows. London/NY sessions only, spread under 1.5 pip."}],
         "canvas_patch": {"rationale": {"text": "Bên mua yếu dần", "confidence": "vừa", "confirmed": True}, "failure": {"text": "Tin mạnh làm phá cấu trúc", "confidence": "vừa", "confirmed": True},
                          "symmetry": {"text": "Bản Buy: 3 đáy tăng dần", "confidence": "vừa", "confirmed": True}, "filters": {"text": "London/NY, spread < 1,5 pip", "confidence": "cao", "confirmed": True}}},
        {"id": 6, "kind": "command", "title_vi": "Tìm ví dụ: AI quét lịch sử", "title_en": "Find examples: AI scans history", "clarity": 84, "command": "/quet",
         "messages": [{"role": "ai", "text_vi": "(Minh hoạ) Tìm thấy 42 lần xuất hiện; đây là 8 ví dụ rải đều, mời bạn gắn nhãn.", "text_en": "(Illustrative) Found 42 occurrences; here are 8 evenly spread examples to label."}]},
        {"id": 7, "kind": "label", "title_vi": "Gắn nhãn ví dụ", "title_en": "Label examples", "clarity": 88,
         "messages": [{"role": "user", "text_vi": "6 đúng, 1 gần đúng, 1 sai (đỉnh thứ 3 cao hơn).", "text_en": "6 correct, 1 near-miss, 1 wrong (third high is higher)."}],
         "labels_summary": {"n_examples": 8, "n_labeled": 8, "precision": 0.81, "coverage": 1.0, "illustrative": True}},
        {"id": 8, "kind": "result", "title_vi": "Chạy thử: thẻ kết quả minh hoạ", "title_en": "Run test: illustrative result card", "clarity": 90, "command": "/test",
         "messages": [{"role": "ai", "text_vi": "(Minh hoạ) Kết quả walk-forward trên dữ liệu dev; test khoá chưa mở.", "text_en": "(Illustrative) Walk-forward result on dev data; locked test not opened."}],
         "result_card": {"illustrative": True, "notice_vi": "Số minh hoạ, không phải kết quả thật", "notice_en": "Illustrative numbers, not real results",
                         "verdict": "unproven", "metrics": {"trades": 118, "expectancy_r": 0.04, "ci95": [-0.12, 0.2], "p_vs_random": 0.31, "dsr": 0.2, "pbo": 0.45},
                         "honesty_vi": ["Khoảng tin cậy chứa 0: chưa chứng minh có edge.", "Test khoá chưa mở; đây không phải bằng chứng cuối.", "Không hứa lợi nhuận."]}},
    ]}


# ---------------------------------------------------------------------- đăng ký
def register(app: FastAPI, st: Any, store: Any, llm: Any = None) -> None:
    store.x(FLAG_DDL)
    write_rl = _Limiter(getattr(st, "class_write_rate", 60), 60.0)

    def who(request: Request) -> Who:
        uid, role = request.headers.get("x-class-user", ""), request.headers.get("x-class-role", "")
        if role not in ROLES or not UID.match(uid):
            raise HTTPException(403, "Không có quyền truy cập")
        return Who(uid, role, _disp(unquote(request.headers.get("x-class-name", "")[:200]), "Quản trị" if role == "master" else "Chuyên gia " + uid[:8]))

    def room_of(rid: str, w: Who) -> dict:
        r = store.room(rid) if RID.match(rid or "") else None
        if not r or not (w.master or store.is_member(rid, w.uid)):
            raise HTTPException(404, "không tìm thấy phòng")
        mem = next((m for m in r["members"] if m["user_id"] == w.uid), None)
        if mem:
            w.name = mem["name"]
        return r

    def j(data: Any, code: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=code, headers=NOSTORE)

    def machine(rid: str):
        return persist.load(store.get_state(rid), rid, llm)

    def confirms(rid: str) -> dict[str, str]:
        return {r["row_key"]: r["text_hash"] for r in store.q("SELECT row_key,text_hash FROM class_ux_confirm WHERE room_id=?", (rid,))}

    def view(rid: str, c) -> dict:
        rows = build_rows(c.profile, confirms(rid))
        return {"rows": rows, "clarity": clarity(rows), "profile_version": c.profile.version}

    def check_key(key: str) -> None:
        if key not in ROW_KEYS:
            raise HTTPException(422, "key không hợp lệ")

    @app.get("/class/rooms/{rid}/canvas", tags=["class-ux"])
    async def canvas(request: Request, rid: str):
        w = who(request)
        room_of(rid, w)
        return j(view(rid, machine(rid)))

    @app.post("/class/rooms/{rid}/canvas/{key}/confirm", tags=["class-ux"])
    async def canvas_confirm(request: Request, rid: str, key: str, body: dict):
        w = who(request)
        room_of(rid, w)
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        check_key(key)
        on = body.get("confirmed", True)
        if not isinstance(on, bool):
            raise HTTPException(422, "confirmed phải là boolean")
        with store.room_lock(rid):
            c = machine(rid)
            row = next(r for r in build_rows(c.profile, {}) if r["key"] == key)
            if not row["text"]:
                raise HTTPException(404, "hàng còn trống, chưa có gì để xác nhận")
            if on:
                store.x("INSERT OR REPLACE INTO class_ux_confirm(room_id,row_key,text_hash,by_user,at) VALUES(?,?,?,?,?)", (rid, key, _h(row["text"]), w.uid, now()))
            else:
                store.x("DELETE FROM class_ux_confirm WHERE room_id=? AND row_key=?", (rid, key))
        store.audit(w.uid, w.role, rid, "canvas.confirm" if on else "canvas.unconfirm", key)
        v = view(rid, c)
        return j({"key": key, "confirmed": on, "clarity": v["clarity"]})

    @app.post("/class/rooms/{rid}/canvas/{key}/edit", tags=["class-ux"])
    async def canvas_edit(request: Request, rid: str, key: str, body: dict):
        w = who(request)
        room_of(rid, w)
        if not write_rl.ok(w.uid):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        check_key(key)
        src = EDITABLE.get(key)
        if not src:
            raise HTTPException(422, "hàng này do AI tổng hợp, không sửa trực tiếp")
        text = body.get("text")
        if not isinstance(text, str):
            raise HTTPException(422, "text bắt buộc")
        text = clean_text(text, MAXEDIT)
        if not text.strip() or looks_injected(text):
            raise HTTPException(422, "text rỗng hoặc chứa chỉ thị")
        with store.room_lock(rid):
            c = machine(rid)
            before = next(r for r in build_rows(c.profile, {}) if r["key"] == key)["text"] or None
            c.profile.add_answer(src, text, author=w.name, role="expert", source="chat")
            store.put_state(rid, persist.dump(c))
            row = next(r for r in build_rows(c.profile, confirms(rid)) if r["key"] == key)
        store.audit(w.uid, w.role, rid, "canvas.edit", key)
        return j({"key": key, "before": before, "after": row["text"], "row": row, "clarity": view(rid, c)["clarity"], "profile_version": c.profile.version})

    @app.get("/class/templates", tags=["class-ux"])
    async def templates(request: Request):
        who(request)
        return j({"items": TEMPLATES, "disclaimer": DISCLAIMER})

    @app.get("/class/demo/script", tags=["class-ux"])
    async def demo_script(request: Request):
        who(request)
        return j(DEMO)
