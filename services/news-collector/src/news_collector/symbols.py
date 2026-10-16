"""Gắn symbols[] cho tin bằng bảng từ khóa cấu hình. Hàm thuần, không I/O."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml


def fold(s: str) -> str:
    """lowercase + bỏ dấu tiếng Việt (đ->d) để 'vàng' khớp 'vang'."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


@dataclass(frozen=True)
class Rule:
    symbols: tuple[str, ...]
    patterns: tuple[re.Pattern, ...]
    case_sensitive: bool = False


def _compile(kw: str, case_sensitive: bool) -> re.Pattern:
    k = kw if case_sensitive else fold(kw)
    return re.compile(r"(?<![\w])" + re.escape(k) + r"(?![\w])", 0 if case_sensitive else re.I)


def build_rules(cfg: dict) -> list[Rule]:
    rules: list[Rule] = []
    for r in cfg.get("rules", []):
        cs = bool(r.get("case_sensitive", False))
        rules.append(Rule(tuple(r["symbols"]), tuple(_compile(k, cs) for k in r["keywords"]), cs))
    return rules


def load_rules(path: Path) -> list[Rule]:
    return build_rules(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def tag_symbols(text: str, rules: list[Rule], default: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Trả danh sách symbol (giữ thứ tự xuất hiện trong bảng luật, không trùng)."""
    folded = fold(text or "")
    out: list[str] = list(dict.fromkeys(default))
    for rule in rules:
        hay = text if rule.case_sensitive else folded
        if any(p.search(hay) for p in rule.patterns):
            for s in rule.symbols:
                if s not in out:
                    out.append(s)
    return out
