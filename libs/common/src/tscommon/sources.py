"""Bo loc TEN NGUON du lieu cho moi noi dung hien thi cho nguoi dung (thong bao, bao cao, API cong khai).

Quy tac san pham: he thong chi hien thi NOI DUNG (tin, tin hieu, chi bao, gia, lich), KHONG hien thi ten nguon.
Danh sach ten o `sources.yaml` (ghi de bang env SOURCES_CONFIG). KHONG anh huong log/Prometheus/Gatus/Grafana (cong cu van hanh).
Ham thuan, khong phu thuoc mang/DB. Xem docs/UI_NO_SOURCES.md.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

_TLD = r"(?:com|net|org|vn|io|gov|co|uk|eu|jp|ch|ca|au|info|biz)"
_URL_TAIL = r"(?:/[^\s)\]>\"'<]*)?"
_DOMAIN_TAIL = rf"(?:\.{_TLD}(?:\.[a-z]{{2}})?{_URL_TAIL})?"
_ATTR_WORDS = (r"(?:ngu(?:ồ|o)n(?:\s+d(?:ữ|u)\s+li(?:ệ|e)u)?|source|via|provider|nh(?:à|a)\s+cung\s+c(?:ấ|a)p|"
               r"theo|according\s+to|t(?:ừ|u)|from|by|data\s+from)")
_LEAD = r"(?<![\w@/-])(?:https?://)?(?:[a-z0-9-]+\.)*"


def _name_re(n: str) -> str:
    parts = [re.escape(p) for p in re.split(r"[\s_]+", n.strip()) if p]
    return r"[\s_-]?".join(parts)


def _alt(names: list[str]) -> str:
    return "|".join(sorted({_name_re(n) for n in names}, key=len, reverse=True))


@dataclass
class _Compiled:
    replacement: str
    strict: re.Pattern
    ctx_attr: re.Pattern | None
    ctx_after: re.Pattern | None
    ctx_domain: re.Pattern | None
    id_pre: re.Pattern | None
    rewrites: list
    attr_strip: re.Pattern
    lead_trail: list
    domains: tuple
    strict_names: tuple
    keys: frozenset
    strong: frozenset
    id_keys: frozenset
    quick: re.Pattern
    value_re: re.Pattern


@lru_cache(maxsize=1)
def _load() -> _Compiled:
    path = os.getenv("SOURCES_CONFIG", "").strip()
    text = Path(path).read_text(encoding="utf-8") if path and Path(path).is_file() else \
        resources.files("tscommon").joinpath("sources.yaml").read_text(encoding="utf-8")
    raw: dict[str, Any] = yaml.safe_load(text) or {}
    strict = [str(x) for x in raw.get("strict") or []]
    ctxn = [str(x) for x in raw.get("contextual") or []]
    pref = [str(x) for x in raw.get("id_prefixes") or []]
    s_alt = _alt(strict)
    c_alt = _alt(ctxn) if ctxn else ""
    p_alt = _alt(pref) if pref else ""
    all_alt = "|".join(a for a in (s_alt, c_alt) if a)
    src_any = rf"{_LEAD}(?:{all_alt})(?:_[a-z0-9_]+)?{_DOMAIN_TAIL}(?![\w])"
    rewrites = []
    for r in raw.get("rewrites") or []:
        pat = str(r["pattern"]).replace("{SRC}", f"(?:{src_any})")
        rewrites.append((re.compile(pat, re.I), str(r["to"])))
    sep = r"(?:\s*[,/+&]\s*|\s+(?:v(?:à|a)|and)\s+)"
    one = f"(?:{src_any})"
    attr = re.compile(rf"(?i)(?:\(\s*)?\b{_ATTR_WORDS}\s*[:\-–—]?\s*{one}(?:{sep}{one})*[,;.]?(?:\s*\))?")
    lead = [(re.compile(rf"(?i)^\s*{one}\s*[:\-–—|]\s*"), ""),
            (re.compile(rf"(?i)\s*[\-–—|:]\s*{one}\s*$"), ""),
            (re.compile(rf"(?i)\(\s*{one}\s*\)"), " "),
            (re.compile(rf"(?i)\[\s*{one}\s*\]"), " ")]
    ctx_attr = ctx_after = ctx_domain = None
    if c_alt:
        ctx_attr = re.compile(rf"(?i)\b{_ATTR_WORDS}\s*[:\-–—]?\s*(?:{c_alt})(?:_[a-z0-9_]+)?{_DOMAIN_TAIL}(?![\w:])[,;.]?")
        ctx_after = re.compile(
            rf"(?i)(?<![\w@/.:-])(?:{c_alt})\s+(?:api|feed|rss|provider|data|d(?:ữ|u)\s+li(?:ệ|e)u|"
            rf"l(?:ỗ|o)i|error|down|timeout|tr(?:ả|a)\s+v(?:ề|e)|http\s*\d+)\b")
        ctx_domain = re.compile(rf"(?i){_LEAD}(?:{c_alt})(?:_[a-z0-9_]+)?\.{_TLD}(?:\.[a-z]{{2}})?{_URL_TAIL}(?![\w])")
    return _Compiled(
        replacement=str(raw.get("replacement") or "nguồn dữ liệu"),
        strict=re.compile(rf"(?i){_LEAD}(?:{s_alt})(?:_[a-z0-9_]+)?{_DOMAIN_TAIL}(?![\w])"),
        ctx_attr=ctx_attr, ctx_after=ctx_after, ctx_domain=ctx_domain,
        id_pre=re.compile(rf"(?i)(?<![\w@/.:-])(?:{p_alt})_[a-z0-9_]+(?![\w])") if p_alt else None,
        rewrites=rewrites, attr_strip=attr, lead_trail=lead,
        domains=tuple(d.lower() for d in raw.get("domains") or []),
        strict_names=tuple(n.lower().replace(" ", "") for n in strict),
        keys=frozenset(str(k).lower() for k in raw.get("source_keys") or []),
        strong=frozenset(str(k).lower() for k in raw.get("strong_keys") or []),
        id_keys=frozenset(str(k).lower() for k in raw.get("id_keys") or []),
        quick=re.compile("(?i)" + "|".join(a for a in (all_alt, p_alt, "|".join(re.escape(d) for d in (raw.get("domains") or []))) if a)),
        value_re=re.compile(rf"(?i)^\s*(?:{'|'.join(a for a in (all_alt, p_alt) if a)})(?:[\s_:.\-/].*)?$", re.S))


def reload() -> None:
    _load.cache_clear()
    _MEMO.clear()


_URL = re.compile(r"https?://[^\s)\]>\"'<]+", re.I)


def _url_is_source(u: str, c: _Compiled) -> bool:
    host = (urlparse(u).hostname or "").lower()
    if not host:
        return False
    if any(host == d or host.endswith("." + d) for d in c.domains):
        return True
    h = host.replace("-", "").replace(".", "")
    return any(n.replace(".", "").replace("_", "") in h for n in c.strict_names if len(n) >= 3)


def _tidy(t: str) -> str:
    t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,;:])\s*(?=[,;:])", "", t)
    t = re.sub(r"(?m)^[ \t]*[,;:\-–—|]+[ \t]*(?=\S)", "", t)
    t = re.sub(r"(?m)[ \t]*[,;:\-–—|]+[ \t]*$", "", t)
    return t.strip()


_MEMO: dict[str, str] = {}
_NO_ALPHA = re.compile(r"[0-9TZ:.+\- ]*")


def scrub_sources(text: Any, replacement: str | None = None) -> Any:
    """Go ten nguon khoi 1 chuoi hien thi. Khong phai chuoi -> tra nguyen. Idempotent."""
    if not isinstance(text, str) or not text:
        return text
    if _NO_ALPHA.fullmatch(text):
        return text
    if replacement is None and len(text) <= 64:
        r = _MEMO.get(text)          # chuỗi ngắn lặp lại (mã, tf, "mt5"...): bỏ qua regex lớn; ts/số dạng chuỗi qua _NO_ALPHA
        if r is None:
            r = _scrub_sources(text, None)
            if len(_MEMO) >= 20000:
                _MEMO.clear()
            _MEMO[text] = r
        return r
    return _scrub_sources(text, replacement)


def _scrub_sources(text: str, replacement: str | None) -> str:
    c = _load()
    if not c.quick.search(text):
        return text  # duong nhanh: khong co ten nguon -> giu nguyen
    rep = c.replacement if replacement is None else replacement
    t = text
    for pat, to in c.rewrites:
        t = pat.sub(to, t)
    t = _URL.sub(lambda m: "" if _url_is_source(m.group(0), c) else m.group(0), t)
    t = c.attr_strip.sub(" ", t)
    for p, sub in c.lead_trail:
        t = p.sub(sub, t)
    if c.ctx_attr:
        t = c.ctx_attr.sub(" ", t)
    if c.ctx_after:
        t = c.ctx_after.sub(rep, t)
    if c.ctx_domain:
        t = c.ctx_domain.sub(rep, t)
    if c.id_pre:
        t = c.id_pre.sub(rep, t)
    t = c.strict.sub(rep, t)
    if rep:
        esc = re.escape(rep)
        for _ in range(2):
            t = re.sub(rf"(?i){esc}(?:\s*[,/+&]\s*|\s+){esc}", rep, t)
    return _tidy(t)


def has_source_name(text: Any) -> bool:
    """True neu chuoi con ten nguon (de test/quet)."""
    return isinstance(text, str) and bool(text) and scrub_sources(text) != text


def scrub_tags(tags: Any) -> list[str]:
    """Bo tag la/chua ten nguon (tag dieu huong `ch:*`/`rule:*` va tag thong thuong giu nguyen)."""
    out: list[str] = []
    for t in tags or []:
        if not isinstance(t, str):
            continue
        if t.startswith(("ch:", "rule:")):
            out.append(t)
            continue
        if has_source_name(t) or has_source_name(t.replace(":", " ")):
            continue
        out.append(t)
    return out


def is_source_key(key: str) -> bool:
    """Khoa "giong nguon" (gia tri chi bi bo khi la ten nguon)."""
    k = str(key).lower()
    return k in _load().keys or k.endswith(("_source", "_provider", "_publisher"))


def is_source_value(v: Any) -> bool:
    """Gia tri la (hoac bat dau bang) mot ten nguon: 'dukascopy', 'yahoo_daily', 'bls_cpi', 'fred:DGS10'..."""
    return isinstance(v, str) and bool(v) and (bool(_load().value_re.match(v)) or has_source_name(v))


def scrub_obj(obj: Any, *, drop_keys: bool = True, neutral: Any = None) -> Any:
    """Duyet de quy dict/list: scrub moi chuoi (tru gia tri cua khoa dinh danh `id_keys`).
    Khoa strong (provider, publisher, feed...) luon bi bo; khoa giong-nguon (source, *_source...) bi bo khi gia tri
    la ten nguon (gia tri trung tinh nhu "mt5", "quote" duoc giu). drop_keys=False -> gan `neutral` thay vi bo."""
    c = _load()
    if isinstance(obj, str):
        return scrub_sources(obj)
    if isinstance(obj, list):
        return [scrub_obj(x, drop_keys=drop_keys, neutral=neutral) for x in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_obj(x, drop_keys=drop_keys, neutral=neutral) for x in obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower() if isinstance(k, str) else ""
            if lk in c.strong or (is_source_key(lk) and (is_source_value(v) or isinstance(v, (dict, list)))):
                if not drop_keys:
                    out[k] = neutral
                continue
            if lk in c.id_keys:
                out[k] = v
            elif lk == "tags" and isinstance(v, list):
                out[k] = scrub_tags(v)
            else:
                out[k] = scrub_obj(v, drop_keys=drop_keys, neutral=neutral)
        return out
    return obj
