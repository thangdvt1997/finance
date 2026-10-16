from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    source: str
    ts: datetime = Field(default_factory=utcnow)
    schema_version: int = 1
    trace_id: str | None = None
    payload: dict[str, Any]


def make_event(type: str, source: str, payload: dict[str, Any], trace_id: str | None = None) -> Event:
    return Event(type=type, source=source, payload=payload, trace_id=trace_id)
