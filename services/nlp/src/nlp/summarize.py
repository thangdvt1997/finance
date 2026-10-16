"""Tóm tắt TRÍCH XUẤT (không sinh văn bản): TextRank (Mihalcea & Tarau 2004) chọn câu có sẵn trong bài.

Dùng thuật toán TextRank chuẩn (độ tương đồng = số từ chung / (log|Si|+log|Sj|), PageRank 0.85) viết gọn bằng numpy (~25 dòng)
thay vì kéo thư viện `summa` (phụ thuộc scipy, +110MB image).
Đầu ra luôn là câu nguyên văn (an toàn trước prompt-injection: không có LLM, không có tool).
"""
from __future__ import annotations

import logging
import re

import math

import numpy as np

log = logging.getLogger("nlp.summarize")

_STOP = set("""a an the and or but if of to in on at for with by from as is are was were be been it its this that these those
not no than then so such there their they he she we you i our your his her has have had will would can could may might
và là của có được cho các những một trong với này đó khi để từ đã sẽ cũng không như về ra vào theo tại lên thì mà hay còn""".split())
_WORD = re.compile(r"\w+", re.U)


def textrank(sents: list[str], d: float = 0.85, iters: int = 30) -> list[float]:
    toks = [{w for w in _WORD.findall(x.lower()) if w not in _STOP and len(w) > 2} for x in sents]
    n = len(sents)
    m = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            if toks[i] and toks[j] and len(toks[i]) > 1 and len(toks[j]) > 1:
                m[i, j] = m[j, i] = len(toks[i] & toks[j]) / (math.log(len(toks[i])) + math.log(len(toks[j])))
    rs = m.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1
    t = (m / rs).T
    r = np.full(n, 1.0 / n)
    for _ in range(iters):
        r = (1 - d) / n + d * t @ r
    return r.tolist()

_SENT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ỵ0-9\"“])")
_TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", text or "")).strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(clean(text)) if len(s.strip()) >= 20]


def extract_summary(title: str, body: str, lang: str | None, n: int = 2, max_chars: int = 300,
                    min_chars: int = 400) -> str | None:
    """Trả None nếu không có gì đáng tóm tắt (body ngắn hơn min_chars hoặc trùng title)."""
    body = clean(body)
    if len(body) < min_chars:
        return None
    sents = [s for s in split_sentences(body) if s.lower() != (title or "").strip().lower()]
    if not sents:
        return None
    pick: list[str] = []
    if len(sents) > n:
        sc = textrank(sents)
        top = sorted(sorted(range(len(sents)), key=lambda i: (-sc[i], i))[:n])    # giữ thứ tự gốc trong bài
        pick = [sents[i] for i in top]
    if not pick:
        pick = sents[:n]
    out = " ".join(pick)
    return out if len(out) <= max_chars else out[:max_chars - 1].rstrip() + "…"
