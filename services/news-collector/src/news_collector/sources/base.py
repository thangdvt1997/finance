from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from ..httpclient import PoliteClient
from ..models import Emit, NullScorer, SentimentScorer
from ..symbols import Rule


@dataclass
class Context:
    client: PoliteClient
    rules: list[Rule]
    config_dir: Path
    user_agent: str
    now: Callable[[], datetime]
    scorer: SentimentScorer = NullScorer()
    book: Any = None  # CalendarBook (do Runner gan) - cho nguon 'actual'

    def load_yaml(self, name: str) -> dict:
        return yaml.safe_load((self.config_dir / name).read_text(encoding="utf-8")) or {}


class Source:
    """Plugin nguồn. fetch() trả danh sách Emit (đã chuẩn hóa theo CONTRACTS); runner lo dedupe + publish."""
    name: str = "source"
    interval: float = 900.0

    async def fetch(self, ctx: Context) -> list[Emit]:  # pragma: no cover - interface
        raise NotImplementedError


def news_emit(ctx: Context, *, url: str, title: str, summary: str | None, published_at: datetime | None,
              source: str, lang: str | None, default_symbols=(), extra_text: str = "") -> Emit:
    from ..models import iso
    from ..symbols import tag_symbols
    title = " ".join((title or "").split())
    summary = " ".join(summary.split())[:1000] if summary else None
    symbols = tag_symbols(f"{title} {summary or ''} {extra_text}", ctx.rules, default_symbols)
    payload = {"url": url, "title": title, "summary": summary, "published_at": iso(published_at),
               "source": source, "lang": lang, "symbols": symbols,
               "sentiment": ctx.scorer.score(title, summary, lang)}
    return Emit("news", "news", payload, f"news:{url}")
