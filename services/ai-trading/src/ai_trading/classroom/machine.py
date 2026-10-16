"""State machine 'AI Training Class' do CODE điều khiển: thứ tự checklist, hỏi từng cụm ≤3 câu, lưu câu trả lời có cấu trúc, xác nhận, xung đột giữa chuyên gia.
LLM (nếu có) chỉ diễn đạt câu hỏi/tóm tắt; mọi đầu ra qua hậu kiểm, sai/lỗi -> câu mẫu cố định. KHÔNG thực thi gì: action = Intent cho backend."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterator

from . import one_to_ten
from .checklist import BY_KEY, STEPS
from .commands import CommandError, Intent, chips_for, parse_command
from .export import export_scenario
from .extract import extract, fold, is_skip
from .llm import GuardedLLM
from .profile import Profile, ProfileHistory
from .prompts import phrase_messages, summary_messages
from .safety import clean_text, data_block, ingest_untrusted, looks_injected, numbers_in

N = len(STEPS)
_CONFIRM = {"dung", "dung roi", "ok", "okay", "chinh xac", "yes", "dong y", "chuan", "dung vay", "chuan roi"}
MAX_MSG = 1500
_FIX = re.compile(r"^(?:s(?:ửa|ua)\s+)?(\d{1,2})\s*[:.\-]\s*(.+)$", re.S | re.I)


@dataclass
class Turn:
    reply: str
    phase: str
    step: str | None = None
    questions: list = field(default_factory=list)
    intent: Intent | None = None
    chips: list = field(default_factory=list)
    understanding: dict | None = None
    notes: list = field(default_factory=list)
    used_llm: bool = False
    profile_version: int = 1
    memory_used: list = field(default_factory=list)   # bản ghi bộ nhớ AI đã dùng ở lượt này (MEMORY_API.md)


class Classroom:
    def __init__(self, room: str = "room", llm: GuardedLLM | None = None, profile: Profile | None = None):
        self.llm = llm
        self.profile = profile or Profile(room=room)
        self.history = ProfileHistory()
        self.phase, self.idx = "intake", 0
        self._clarified: set[str] = set()
        self._reconcile: str | None = None
        self._more = 0
        self.flags: list[dict] = []     # nhật ký chặn injection (cho audit)
        self.memory = None              # hook Bộ nhớ của AI (memory.RoomMemory), không lưu bền

    # ---------- tiện ích ----------
    def _turn(self, reply: str, **kw) -> Turn:
        step = STEPS[self.idx].key if self.phase == "interview" and self.idx < N else None
        t = Turn(reply=reply, phase=self.phase, step=step, profile_version=self.profile.version, **kw)
        t.memory_used = list(self.memory.used) if self.memory else []
        t.chips = chips_for(self.phase, step, self.profile.missing_required(), len(self.profile.answered()))
        return t

    def _allowed_numbers(self, extra: str = "") -> set[str]:
        return numbers_in(self.profile.all_text() + " " + extra) | {"1", "2", "3"}

    def _ctx(self) -> str:
        m = self.profile.merged()
        bits = []
        if m["symbols"]:
            bits.append("mã " + "/".join(m["symbols"]))
        if m["tfs"]:
            bits.append("khung " + "/".join(m["tfs"]))
        if self.profile.name and not self.profile.name.startswith("Kịch bản chưa"):
            bits.append(self.profile.name)
        return ", ".join(bits)

    def _ask_text(self, qs: list[str], title: str, head: str) -> tuple[str, bool]:
        fixed = head + "\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1))
        if not self.llm:
            return fixed, False
        mb = self.memory.context(" ".join(qs) + " " + self._ctx(), STEPS[self.idx].key if self.idx < N else None) if self.memory else ""
        allowed = self._allowed_numbers(" ".join(qs) + " " + mb)

        def valid(t: str) -> str | None:
            if not 1 <= t.count("?") <= 3 or numbers_in(t) - allowed:
                return "sai dạng"
            return None
        ev = data_block([e for e in self.profile.evidence[-3:] if e.get("text")])
        if mb:
            ev = (ev + "\n\n" + mb).strip()
        text, used = self.llm.generate(phrase_messages(title, qs, self._ctx(), ev), "", valid, 120)
        if used and mb and self.memory and self.memory.used:
            text += f"\n(Mình dựa vào {len(self.memory.used)} điều đã được dạy trước đó, xem ở mục Bộ nhớ.)"
        return (head + "\n" + text, True) if used else (fixed, False)

    def _ask_current(self, prefix: str = "") -> Turn:
        if self.idx >= N:
            return self._finish(prefix)
        s = STEPS[self.idx]
        cur = self.profile.current(s.key)
        head = f"Bước {self.idx + 1}/{N} - {s.title}"
        known = None if cur or not self.memory else self.memory.known(s.key)
        if known:
            qs = [f"Mình nhớ bạn từng dạy: \"{known['text'][:160]}\" (đã xác nhận). Áp dụng cho kịch bản này không? Nếu khác, hãy sửa bằng số cụ thể."]
            return self._turn((prefix + "\n\n" if prefix else "") + head + "\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1)), questions=qs, notes=["dùng bộ nhớ"])
        if cur and cur.source == "brief":
            qs = [f"Từ mô tả ban đầu tôi ghi nhận: \"{cur.text[:160]}\". Đúng chưa? Nếu cần, hãy sửa hoặc bổ sung bằng số cụ thể."]
        else:
            qs = list(s.questions)
        text, used = self._ask_text(qs, s.title, head)
        return self._turn((prefix + "\n\n" if prefix else "") + text, questions=qs, used_llm=used)

    # ---------- vào ----------
    def respond(self, text: str, author: str = "expert", role: str = "expert") -> Turn:
        raw = text if isinstance(text, str) else ""
        raw = raw[:MAX_MSG]
        if self.memory:
            self.memory.used = []
        try:
            it = parse_command(raw)
        except CommandError as e:
            return self._turn(f"{e} Lệnh cho phép: " + ", ".join(e.suggestions[:11]), notes=["lệnh bị từ chối"])
        if it:
            return self._command(it)
        hit = looks_injected(raw)
        if hit:
            self.flags.append({"author": author, "pattern": hit})
            t = self._ask_current("Tin nhắn có mẫu giống chỉ thị cho AI nên tôi bỏ qua (không lưu). Hãy mô tả kịch bản bằng lời của bạn.") if self.phase == "interview" else \
                self._turn("Tin nhắn có mẫu giống chỉ thị cho AI nên tôi bỏ qua (không lưu). Hãy mô tả kịch bản bằng lời của bạn (3 câu là đủ).")
            t.notes.append("injection bị chặn")
            return t
        msg = clean_text(raw, MAX_MSG)
        if not msg:
            return self._turn("Tin nhắn trống.")
        if self.phase == "intake":
            return self._intake(msg, author, role)
        if self.phase == "review":
            return self._review(msg, author, role)
        mm = _FIX.match(msg)
        if mm and 1 <= int(mm.group(1)) <= N:        # sửa/bổ sung một bước bất kỳ khi đang phỏng vấn (nhiều chuyên gia)
            s = STEPS[int(mm.group(1)) - 1]
            a, conflict = self._record(s, mm.group(2).strip(), author, role)
            return conflict or self._ask_current(f"Đã cập nhật '{s.title}' (độ chắc chắn: {a.confidence}).")
        return self._answer(msg, author, role)

    def respond_stream(self, text: str, author: str = "expert", role: str = "expert", chunk: int = 48) -> Iterator[dict]:
        """Phát theo luồng văn bản ĐÃ hậu kiểm (không phát nháp thô của LLM), rồi sự kiện cuối chứa Turn."""
        t = self.respond(text, author, role)
        yield {"type": "meta", "phase": t.phase, "step": t.step}
        for i in range(0, len(t.reply), chunk):
            yield {"type": "delta", "text": t.reply[i:i + chunk]}
        yield {"type": "turn", "turn": asdict(t)}

    def attach(self, kind: str, text: str, author: str = "expert") -> Turn:
        """Nội dung từ ảnh/file/tin: làm sạch, loại nếu có chỉ thị; chỉ làm DỮ LIỆU tham khảo, không bao giờ thành chỉ thị."""
        r = ingest_untrusted(kind, text)
        if r["dropped"]:
            self.flags.append({"author": author, "pattern": "attachment", "kind": kind})
            return self._turn("Đính kèm bị loại: " + r["reason"] + ".", notes=["attachment bị loại"])
        if not r["text"]:
            return self._turn("Đính kèm không có nội dung đọc được; hãy chú thích bằng lời.")
        self.profile.evidence.append({**r, "author": author})
        return self._turn("Đã ghi nhận đính kèm làm dữ liệu tham khảo (không phải chỉ thị). Hãy chú thích điểm cần AI chú ý.")

    # ---------- các pha ----------
    def _intake(self, msg: str, author: str, role: str) -> Turn:
        ex = extract(msg)
        first = re.split(r"[.!?\n]", msg, 1)[0].strip()
        if self.profile.name.startswith("Kịch bản chưa") and first:
            self.profile.name = first[:60] if len(first) >= 3 else self.profile.name
        self.profile.evidence.append({"kind": "brief", "text": msg[:600], "dropped": False, "author": author})
        if ex.get("symbols") or ex.get("tfs"):
            self.profile.add_answer("symbol_tf", msg, author, role, source="brief")
        if ex.get("rules"):
            self.profile.add_answer("formation", msg, author, role, source="brief")
        if ex.get("levels"):
            self.profile.add_answer("sl_tp", msg, author, role, source="brief")
        self.phase, self.idx = "interview", 0
        n = len(self.profile.answered())
        pre = f"Cảm ơn, tôi đã nắm ý chính ({n} mục được điền tạm từ mô tả, sẽ xác nhận lại)." if n else "Cảm ơn, tôi sẽ hỏi lần lượt từng cụm nhỏ để hiểu thật sâu."
        return self._ask_current(pre)

    def _answer(self, msg: str, author: str, role: str) -> Turn:
        s = STEPS[self.idx]
        prev = self.profile.current(s.key)
        if is_skip(msg):
            self.profile.add_answer(s.key, "bỏ qua", author, role, skipped=True)
            return self._advance("Đã ghi vào danh sách câu hỏi còn mở.")
        if not prev and self.memory and fold(msg).strip(" .!") in _CONFIRM and (k := self.memory.known(s.key)):
            self.profile.add_answer(s.key, k["text"], author, role, source="memory+xác nhận")
            return self._advance("Đã xác nhận điều mình nhớ.")
        if prev and prev.source == "brief" and fold(msg).strip(" .!") in _CONFIRM:
            prev.source = "brief+xác nhận"
            return self._advance("Đã xác nhận.")
        a, conflict = self._record(s, msg, author, role)
        if conflict:
            return conflict
        if a.confidence == "thấp" and s.key not in self._clarified:
            self._clarified.add(s.key)
            return self._turn(f"Tôi chưa đủ rõ ở phần này (độ chắc chắn: thấp). {s.followup}", questions=[s.followup])
        return self._advance(f"Ghi nhận (độ chắc chắn: {a.confidence}).")

    def _record(self, s, msg: str, author: str, role: str):
        """Ghi câu trả lời cho bước s; phát hiện xung đột (khác người, cùng bước, số khác nhau) và giải quyết khi có câu thống nhất."""
        prev = self.profile.current(s.key)
        a = self.profile.add_answer(s.key, msg, author, role)
        if prev and prev.author != author and prev.source == "chat" and self._reconcile != s.key:
            pa, pb = set(prev.fields.get("numbers", [])), set(a.fields.get("numbers", []))
            if pa and pb and pa != pb:
                self._reconcile = s.key
                self.profile.conflicts.append({"step": s.key, "a": {"author": prev.author, "text": prev.text[:200]}, "b": {"author": author, "text": msg[:200]}, "status": "open"})
                return a, self._turn(f"{prev.author} và {author} nêu số khác nhau ở bước '{s.title}' ({sorted(pa)} và {sorted(pb)}). "
                                     "Hai bạn thống nhất một giá trị chung (hoặc nêu điều kiện nào dùng giá trị nào) nhé? (Trả lời dạng 'số bước: nội dung')", notes=["xung đột chuyên gia"])
        elif self._reconcile == s.key:
            self._reconcile = None
            for c in self.profile.conflicts:
                if c["step"] == s.key and c["status"] == "open":
                    c["status"] = "resolved"
        return a, None

    def _advance(self, prefix: str) -> Turn:
        self.idx += 1
        while self.idx < N and (c := self.profile.current(STEPS[self.idx].key)) and c.source == "brief+xác nhận":
            self.idx += 1
        return self._ask_current(prefix)

    def _finish(self, prefix: str) -> Turn:
        self.phase = "review"
        one_to_ten.add_assumptions(self.profile)
        u = self.understanding()
        return self._turn((prefix + "\n\n" if prefix else "") + self._summary_text(u) + "\n\nSửa bước nào, gõ 'số bước: nội dung mới'. Hoặc bấm một gợi ý bên dưới ô nhập: Biến thể, Đối xứng, AI hỏi thêm, Quét ví dụ, Test trung thực.",
                          understanding=u)

    def _review(self, msg: str, author: str, role: str) -> Turn:
        m = re.match(r"^(?:s(?:ửa|ua)\s+)?(\d{1,2})\s*[:.\-]\s*(.+)$", msg, re.S | re.I)
        if m and 1 <= int(m.group(1)) <= N:
            s = STEPS[int(m.group(1)) - 1]
            a, conflict = self._record(s, m.group(2).strip(), author, role)
            if conflict:
                return conflict
            return self._turn(f"Đã cập nhật '{s.title}' (độ chắc chắn: {a.confidence}). Bấm gợi ý “Lưu phiên bản” để chốt.", understanding=self.understanding())
        return self._turn("Để sửa: 'số bước: nội dung mới' (ví dụ '6: SL 1,5 ATR, TP 1R'). Hoặc bấm một gợi ý bên dưới ô nhập.")

    # ---------- tóm tắt "AI hiểu như sau" ----------
    def understanding(self) -> dict:
        items = []
        for st in STEPS:
            a = self.profile.current(st.key)
            if a:
                items.append({"section": st.key, "title": st.title, "text": a.text.strip()[:200], "confidence": a.confidence, "by": a.author})
        unknown = [st.title for st in STEPS if not self.profile.current(st.key)]
        lows = [i["title"] for i in items if i["confidence"] == "thấp"]
        return {"items": items, "unknown": unknown, "low": lows, "open_questions": list(self.profile.open_questions), "conflicts": [c for c in self.profile.conflicts if c["status"] == "open"],
                "assumptions_pending": [a["question"] for a in self.profile.assumptions if a["status"] == "pending"]}

    def _summary_text(self, u: dict) -> str:
        lead = ""
        if self.llm and u["items"]:
            allowed = numbers_in(self.profile.all_text())
            lead, used = self.llm.generate(summary_messages(self.profile.lines()[:12]), "", lambda t: "số lạ" if numbers_in(t) - allowed else None, 300)
            lead = lead if used else ""
        L = ["**AI hiểu như sau** (độ chắc chắn do hệ thống chấm theo mức định lượng của câu trả lời):"]
        L += [f"- {i['title']} [{i['confidence']}]: {i['text']}" for i in u["items"]]
        if u["unknown"]:
            L.append("Chưa biết: " + ", ".join(u["unknown"]))
        if u["low"]:
            L.append("Cần làm rõ (độ chắc chắn thấp): " + ", ".join(u["low"]))
        L.append("Lưu ý trung thực: chưa kiểm chứng gì cả; phương pháp nến cổ điển đã thử ở đây không có lợi thế sau chi phí, nên chạy test trung thực (gợi ý “Test trung thực”) là bước bắt buộc trước khi tin.")
        return (lead + "\n\n" if lead else "") + "\n".join(L)

    # ---------- lệnh ----------
    def _command(self, it: Intent) -> Turn:
        c, p = it.command, self.profile
        if c == "tom-tat":
            u = self.understanding()
            return self._turn(self._summary_text(u), intent=it, understanding=u)
        if c == "bien-the":
            e = one_to_ten.expand(p)
            one_to_ten.add_assumptions(p)
            extra = one_to_ten.llm_suggestions(self.llm, p) if self.llm else []
            body = one_to_ten.render(e) + ("\n\nGợi ý thêm từ AI (chưa kiểm chứng):\n" + "\n".join(f"- {x}" for x in extra) if extra else "")
            return self._turn(body, intent=it, used_llm=bool(extra))
        if c == "doi-xung":
            mm = one_to_ten.mirror(p)
            body = ("**Phiên bản đối xứng (buy):**\n" + "\n".join(f"- {x}" for x in mm["rules"]) if mm["rules"] else "Chưa có luật định lượng để đối xứng.") + \
                   ("\nCần xác nhận: " + " / ".join(mm["needs_confirm"]) if mm["needs_confirm"] else "") + "\n" + mm["note"]
            return self._turn(body, intent=it)
        if c == "giai-thich":
            t = fold(it.params.get("topic", ""))
            st = next((s for s in STEPS if t and (s.key in t or fold(s.title) in t or any(w in fold(s.title) for w in t.split() if len(w) > 3))), None)
            a = p.current(st.key) if st else None
            if not st:
                return self._turn("Nêu phần cần giải thích, ví dụ “giải thích SL” hoặc “giải thích bộ lọc” (hoặc bấm gợi ý “Giải thích”). Các phần: " + ", ".join(s.title for s in STEPS), intent=it)
            return self._turn(f"{st.title}: " + (f"tôi hiểu là \"{a.text[:200]}\" (độ chắc chắn {a.confidence})." if a else "chưa có thông tin.") + f" Tôi hỏi phần này vì: {st.questions[0]}", intent=it)
        if c == "hoi-them":
            return self._ask_more(it)
        if c == "dat-lai":
            if not it.params.get("confirmed"):
                _t = self._turn("Đặt lại sẽ xoá phiên dạy hiện tại (phiên bản đã lưu vẫn giữ). Bấm “Xác nhận đặt lại” để tiếp tục.", intent=it)
                _t.chips = [{"label": "Xác nhận đặt lại", "text": "/dat-lai xacnhan=co", "send": True}] + _t.chips
                return _t
            self.profile = Profile(room=p.room)
            self.phase, self.idx, self._clarified, self._reconcile, self._more = "intake", 0, set(), None, 0
            return self._turn("Đã đặt lại. Hãy giao kịch bản mới bằng khoảng 3 câu.", intent=it)
        if c == "luu":
            v = self.history.commit(p, it.params.get("note", ""))
            it.params.update({"version": v, "profile": self.history.get(v)})
            return self._turn(f"Đã lưu phiên bản {v} của hồ sơ (bản đang sửa là {p.version}).", intent=it)
        # các lệnh cần hồ sơ đủ để chạy: /test /quet /so-sanh /ve
        if c in ("test", "quet", "so-sanh"):
            miss = p.missing_required()
            if miss:
                return self._turn("Chưa đủ để chạy: còn thiếu " + ", ".join(BY_KEY[k].title for k in miss) + ". Bấm gợi ý “AI hỏi thêm” để tiếp tục.", notes=["thiếu bước bắt buộc"])
            rep = export_scenario(p)
            if not rep.ok:
                return self._turn("Chưa xuất được kịch bản chạy test: " + " ".join(rep.errors), notes=["export lỗi"])
            it.params.update({"scenario_yaml": rep.yaml, "profile_version": p.version})
            note = "Ý định đã gửi cho backend (chỉ nghiên cứu/paper)."
            if c == "test":
                note = "Sẽ đăng ký giả thuyết trước rồi chạy walk-forward + so baseline ngẫu nhiên; test khoá không dùng ở đây. " + note
            return self._turn(note + (" Cảnh báo: " + "; ".join(rep.warnings) if rep.warnings else ""), intent=it)
        return self._turn("Đã ghi nhận ý định " + c + " (backend thực thi).", intent=it)   # /ve

    def _ask_more(self, it: Intent) -> Turn:
        p = self.profile
        if self.phase == "interview" and self.idx < N:
            return self._ask_current("Tiếp tục theo checklist.")
        qs = [a["question"] for a in p.assumptions if a["status"] == "pending"]
        extra = one_to_ten.counterexamples(p) + one_to_ten.boundaries(p)
        pool = qs + extra
        if not pool:
            return self._turn("Hiện không còn câu hỏi mở.", intent=it)
        i = self._more % len(pool)
        grp = pool[i:i + 3]
        self._more += 3
        return self._turn("Tôi muốn xác nhận thêm:\n" + "\n".join(f"{k}. {q}" for k, q in enumerate(grp, 1)), intent=it, questions=grp)
