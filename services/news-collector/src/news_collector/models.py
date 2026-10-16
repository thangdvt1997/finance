from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass
class Emit:
    """Một bản tin cần phát lên bus. stream = khóa trong tscommon.bus.STREAMS."""
    stream: str          # news | calendar | expert_positions | alerts
    type: str            # news | calendar | expert_position | alert
    payload: dict[str, Any]
    dedupe_key: str      # khóa tự nhiên để bỏ trùng (Redis SET NX)


class SentimentScorer(Protocol):
    """Hook tùy chọn. Mặc định NullScorer -> sentiment=None (không gọi LLM)."""
    def score(self, title: str, summary: str | None, lang: str | None) -> float | None: ...


class NullScorer:
    def score(self, title: str, summary: str | None, lang: str | None) -> float | None:
        return None


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
