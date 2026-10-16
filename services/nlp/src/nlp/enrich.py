"""Làm giàu một lô tin (đồng bộ, chạy trong thread): sentiment + symbols + chủ đề + quan trọng + tóm tắt trích xuất."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from . import entities, topics
from .models import _VI_CHARS, SentimentEngine
from .summarize import clean, extract_summary

MAX_INPUT_CHARS = 600


def detect_lang(payload: dict) -> str:
    lang = (payload.get("lang") or "").strip().lower()[:2]
    if lang:
        return lang
    return "vi" if _VI_CHARS.search((payload.get("title") or "").lower()) else "en"


def model_text(p: dict) -> str:
    """Văn bản đưa vào model: tiêu đề + đầu phần tóm tắt (đã bỏ HTML). Tokenizer cắt theo max_len."""
    title = clean(p.get("title") or "")
    body = clean(p.get("summary") or "")
    if body and body.lower().startswith(title.lower()[:40]):
        body = ""                                        # summary lặp lại title
    return (title + ". " + body)[:MAX_INPUT_CHARS] if body else title


@dataclass
class Enricher:
    engine: SentimentEngine
    rules: list
    cashtag_prefix: str
    topic_model: topics.TopicModel
    summary: bool = True
    summary_min_chars: int = 400

    def version_for(self, p: dict) -> str:
        return self.engine.version_for(detect_lang(p))

    def enrich_batch(self, payloads: list[dict]) -> list[dict]:
        by_lang: dict[str, list[int]] = defaultdict(list)
        langs = [detect_lang(p) for p in payloads]
        for i, lg in enumerate(langs):
            by_lang[lg].append(i)
        sents = [None] * len(payloads)
        for lg, idx in by_lang.items():
            # sắp theo độ dài để giảm padding
            idx = sorted(idx, key=lambda i: len(model_text(payloads[i])))
            res = self.engine.predict([model_text(payloads[i]) for i in idx], lg)
            for i, s in zip(idx, res):
                sents[i] = s
        return [self._one(p, langs[i], sents[i]) for i, p in enumerate(payloads)]

    def _one(self, p: dict, lang: str, s) -> dict:
        text = f"{p.get('title') or ''}. {clean(p.get('summary') or '')}"
        syms = entities.tag_symbols(text, self.rules, self.cashtag_prefix, p.get("symbols") or [])
        tps = topics.classify_topics(text, self.topic_model)
        imp, score = topics.importance(text, tps, len(syms), p.get("source") or "", s.score, s.confidence, self.topic_model)
        out = {
            "url": p["url"], "title": p["title"], "source": p.get("source"), "published_at": p.get("published_at"),
            "lang": lang, "sentiment": round(s.score, 4), "label": s.label, "confidence": round(s.confidence, 4),
            "symbols": syms, "topics": tps, "importance": imp, "importance_score": score,
            "model_version": s.model_version,
        }
        if self.summary:
            ex = extract_summary(p.get("title") or "", p.get("summary") or "", lang, min_chars=self.summary_min_chars)
            if ex:
                out["extract"] = ex
        return out


def valid_payload(p: dict) -> bool:
    return bool(p.get("url")) and bool(p.get("title")) and bool(p.get("source"))
