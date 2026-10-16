"""Phân loại chủ đề (từ điển) + mức quan trọng. Hàm thuần."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .entities import _is_cs, _rx, fold


@dataclass(frozen=True)
class TopicRule:
    name: str
    weight: float
    ci: tuple[re.Pattern, ...]
    cs: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class TopicModel:
    rules: tuple[TopicRule, ...]
    strong: tuple[re.Pattern, ...]
    routine: tuple[re.Pattern, ...]
    source_boost: dict[str, float]
    med: float
    high: float


def _compile(words: list[str]) -> tuple[tuple[re.Pattern, ...], tuple[re.Pattern, ...]]:
    ci, cs = [], []
    for k in words:
        (cs if _is_cs(k) else ci).append(_rx(k) if _is_cs(k) else _rx(fold(k), re.I))
    return tuple(ci), tuple(cs)


def build(cfg: dict) -> TopicModel:
    rules = []
    for name, r in cfg["topics"].items():
        ci, cs = _compile(r["keywords"])
        rules.append(TopicRule(name, float(r["weight"]), ci, cs))
    imp = cfg.get("importance", {})
    th = imp.get("thresholds", {"med": 0.4, "high": 0.65})
    return TopicModel(
        tuple(rules), _compile(imp.get("strong_words", []))[0], _compile(imp.get("routine_words", []))[0],
        dict(imp.get("source_boost", {})), float(th["med"]), float(th["high"]))


def load(path: Path) -> TopicModel:
    return build(yaml.safe_load(path.read_text(encoding="utf-8")))


def classify_topics(text: str, tm: TopicModel, max_topics: int = 3) -> list[str]:
    folded = fold(text or "")
    hits: list[tuple[float, int, str]] = []
    for r in tm.rules:
        n = sum(1 for p in r.ci if p.search(folded)) + sum(1 for p in r.cs if p.search(text or ""))
        if n:
            hits.append((r.weight * (1 + 0.15 * min(n, 4)), n, r.name))
    hits.sort(reverse=True)
    return [h[2] for h in hits[:max_topics]]


def importance(text: str, topics: list[str], n_symbols: int, source: str, sentiment: float, confidence: float,
               tm: TopicModel) -> tuple[str, float]:
    """Trả (mức low|med|high, điểm 0..1)."""
    folded = fold(text or "")
    wmap = {r.name: r.weight for r in tm.rules}
    top = max((wmap[t] for t in topics), default=0.0)
    multi = 0.15 * min(2, max(0, len(topics) - 1)) / 2
    strong = 0.2 if any(p.search(folded) for p in tm.strong) else 0.0
    sym = 0.1 if n_symbols else 0.0
    boost = max((v for k, v in tm.source_boost.items() if (source or "").startswith(k)), default=0.0)
    sent = 0.1 * abs(sentiment) * confidence
    score = 0.55 * top + multi + strong + sym + boost + sent
    if any(p.search(folded) for p in tm.routine):
        score *= 0.6
    score = round(max(0.0, min(1.0, score)), 3)
    level = "high" if score >= tm.high else "med" if score >= tm.med else "low"
    return level, score
