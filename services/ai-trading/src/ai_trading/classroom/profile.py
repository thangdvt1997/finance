"""Hồ sơ kịch bản (sổ tay phương pháp): dataclass thuần, serialize JSON/YAML, phiên bản + diff. Lưu DB là việc của backend (P2b)."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field

import yaml

from .checklist import BY_KEY, KEYS, REQUIRED
from .extract import confidence, extract

SCHEMA_VERSION = 1
_MARKET_KEYS = ("context", "symbol_tf", "formation", "trigger")   # mã/khung chỉ lấy từ các bước này (ví dụ/khung khác không được xuất ngầm)


@dataclass
class Answer:
    key: str
    text: str
    author: str = "expert"
    role: str = "expert"
    fields: dict = field(default_factory=dict)
    confidence: str = "thấp"
    source: str = "chat"           # chat | brief | file | image
    skipped: bool = False


@dataclass
class Profile:
    room: str = "room"
    name: str = "Kịch bản chưa đặt tên"
    version: int = 1
    answers: dict = field(default_factory=dict)       # key -> list[Answer]
    open_questions: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)   # {id, text, question, status}
    evidence: list = field(default_factory=list)      # dữ liệu đã làm sạch (ảnh/file/tin)
    conflicts: list = field(default_factory=list)
    contributors: list = field(default_factory=list)
    labels: list = field(default_factory=list)        # nhãn ví dụ ĐÚNG/SAI/GẦN ĐÚNG do backend gắn (P2b)

    # ---- ghi ----
    def add_answer(self, key: str, text: str, author: str = "expert", role: str = "expert", source: str = "chat", skipped: bool = False) -> Answer:
        if key not in BY_KEY:
            raise KeyError(key)
        fields = extract(text)
        a = Answer(key, text, author, role, fields, "thấp" if skipped else confidence(text, BY_KEY[key].quantitative, fields), source, skipped)
        self.answers.setdefault(key, []).append(a)
        if author not in self.contributors:
            self.contributors.append(author)
        if skipped and text not in self.open_questions:
            self.open_questions.append(BY_KEY[key].title)
        elif not skipped and BY_KEY[key].title in self.open_questions:
            self.open_questions.remove(BY_KEY[key].title)
        return a

    # ---- đọc ----
    def current(self, key: str) -> Answer | None:
        xs = [a for a in self.answers.get(key, []) if not a.skipped]
        return xs[-1] if xs else None

    def answered(self) -> list[str]:
        return [k for k in KEYS if self.current(k)]

    def missing_required(self) -> list[str]:
        return [k for k in REQUIRED if not self.current(k)]

    def merged(self) -> dict:
        """Gộp trường có cấu trúc từ bản trả lời hiện hành của mọi bước."""
        out: dict = {"symbols": [], "tfs": [], "rules": [], "levels": {}, "side": None}
        for k in KEYS:
            a = self.current(k)
            if not a:
                continue
            for s in a.fields.get("symbols", []) if k in _MARKET_KEYS else []:
                if s not in out["symbols"]:
                    out["symbols"].append(s)
            for t in a.fields.get("tfs", []) if k in _MARKET_KEYS else []:
                if t not in out["tfs"]:
                    out["tfs"].append(t)
            for r in a.fields.get("rules", []):
                if r not in out["rules"]:
                    out["rules"].append(r)
            for lk, lv in a.fields.get("levels", {}).items():
                out["levels"].setdefault(lk, lv)
            if k in ("context", "symbol_tf", "formation", "trigger", "sl_tp") and a.fields.get("side") and not out["side"]:
                out["side"] = a.fields["side"]
        return out

    def all_text(self) -> str:
        return "\n".join(a.text for k in KEYS if (a := self.current(k)))

    def lines(self) -> list[str]:
        return [f"{BY_KEY[k].title}: {self.current(k).text.strip()}" for k in KEYS if self.current(k)]

    # ---- serialize ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["schema"] = SCHEMA_VERSION
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        p = cls(room=d.get("room", "room"), name=d.get("name", ""), version=int(d.get("version", 1)))
        for k, xs in (d.get("answers") or {}).items():
            if k in BY_KEY:
                p.answers[k] = [Answer(**{**{"key": k, "text": ""}, **x}) for x in xs]
        for f_ in ("open_questions", "assumptions", "evidence", "conflicts", "contributors", "labels"):
            setattr(p, f_, list(d.get(f_) or []))
        return p

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=1)

    @classmethod
    def from_json(cls, s: str) -> "Profile":
        return cls.from_dict(json.loads(s))

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=True)

    @classmethod
    def from_yaml(cls, s: str) -> "Profile":
        return cls.from_dict(yaml.safe_load(s))


def diff_profiles(a: dict, b: dict) -> list[dict]:
    """So sánh 2 bản (dạng to_dict): theo từng bước, đổi câu trả lời hiện hành / thêm / bớt; cộng thêm câu hỏi mở + giả định."""
    out: list[dict] = []

    def cur(d: dict, k: str) -> str | None:
        xs = [x for x in (d.get("answers") or {}).get(k, []) if not x.get("skipped")]
        return xs[-1]["text"] if xs else None

    for k in KEYS:
        x, y = cur(a, k), cur(b, k)
        if x == y:
            continue
        out.append({"section": k, "title": BY_KEY[k].title, "change": "thêm" if x is None else "bỏ" if y is None else "sửa", "before": x, "after": y})
    for fld in ("open_questions",):
        sa, sb = set(a.get(fld) or []), set(b.get(fld) or [])
        for z in sorted(sb - sa):
            out.append({"section": fld, "change": "thêm", "before": None, "after": z})
        for z in sorted(sa - sb):
            out.append({"section": fld, "change": "bỏ", "before": z, "after": None})
    return out


class ProfileHistory:
    """Lịch sử phiên bản trong bộ nhớ: commit() chụp ảnh bất biến, version tăng đơn điệu."""

    def __init__(self) -> None:
        self.versions: list[dict] = []

    def commit(self, p: Profile, note: str = "") -> int:
        snap = copy.deepcopy(p.to_dict())
        snap["version"] = len(self.versions) + 1
        snap["note"] = note[:200]
        self.versions.append(snap)
        p.version = snap["version"] + 1     # bản đang sửa là bản kế tiếp
        return snap["version"]

    def get(self, v: int) -> dict:
        return self.versions[v - 1]

    def diff(self, v1: int, v2: int) -> list[dict]:
        return diff_profiles(self.get(v1), self.get(v2))
