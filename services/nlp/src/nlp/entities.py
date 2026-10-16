"""Nhận diện thực thể -> symbols[] bằng từ điển (YAML). Hàm thuần, không I/O ngoài load_*.

Không dùng NER nặng (spaCy/GLiNER): từ điển tài chính đã phủ tiền tệ, vàng/dầu, chỉ số, NHTW, mã VN; thêm cashtag $XYZ.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

_CASHTAG = re.compile(r"(?<![\w$])\$([A-Z]{1,5})(?![\w])")


def fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _is_cs(kw: str) -> bool:
    """Từ khoá viết hoa ngắn (Fed, ECB, BoE, CPI, Brent) -> phân biệt hoa/thường để tránh 'fed', 'lane', 'cable'."""
    return len(kw) <= 5 and " " not in kw and any(c.isupper() for c in kw)


@dataclass(frozen=True)
class Rule:
    entity: str
    symbols: tuple[str, ...]
    ci: tuple[re.Pattern, ...]       # so khớp trên chuỗi đã bỏ dấu + lower
    cs: tuple[re.Pattern, ...]       # so khớp trên chuỗi gốc
    strength: float = 1.0


def _rx(k: str, flags: int = 0) -> re.Pattern:
    return re.compile(r"(?<![\w])" + re.escape(k) + r"(?![\w])", flags)


def build(cfg: dict) -> tuple[list[Rule], str]:
    rules: list[Rule] = []
    for r in cfg.get("rules", []):
        rule_cs = bool(r.get("case_sensitive", False))
        prefix = r.get("ticker_prefix", "")
        syms = [f"{prefix}{k}" for k in r["keywords"]] if prefix else list(r["symbols"])
        if prefix:   # mỗi mã = 1 rule riêng (mỗi mã -> symbol riêng)
            for k, sym in zip(r["keywords"], syms):
                rules.append(Rule(r.get("entity", k), (sym,), (), (_rx(k),), float(r.get("strength", 1.0))))
            continue
        ci, cs = [], []
        for k in r["keywords"]:
            if rule_cs or _is_cs(k):
                cs.append(_rx(k))
            else:
                ci.append(_rx(fold(k), re.I))
        rules.append(Rule(r.get("entity", ""), tuple(syms), tuple(ci), tuple(cs), float(r.get("strength", 1.0))))
    return rules, cfg.get("cashtag_prefix", "US:")


def load(path: Path) -> tuple[list[Rule], str]:
    return build(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def tag_symbols(text: str, rules: list[Rule], cashtag_prefix: str = "US:",
                existing: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Hợp của `existing` (từ collector) và thực thể phát hiện; giữ thứ tự: existing trước, rồi theo bảng luật."""
    folded = fold(text or "")
    out: list[str] = list(dict.fromkeys(existing))
    for rule in rules:
        if any(p.search(folded) for p in rule.ci) or any(p.search(text or "") for p in rule.cs):
            for s in rule.symbols:
                if s not in out:
                    out.append(s)
    for m in _CASHTAG.finditer(text or ""):
        s = f"{cashtag_prefix}{m.group(1)}"
        if s not in out:
            out.append(s)
    return out
