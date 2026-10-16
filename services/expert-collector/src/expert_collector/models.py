from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_FX = {"EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "XAU", "XAG", "BTC", "ETH"}


def normalize_symbol(s: str) -> str:
    """'EUR/USD', 'eurusd.m', 'XAUUSD#' -> 'EURUSD'. Giu tien to 'VN:'/'US:'."""
    s = (s or "").strip().upper()
    if s.startswith(("VN:", "US:")):
        return s
    s = re.sub(r"[^A-Z0-9]", "", s)
    if len(s) > 6 and s[:3] in _FX and s[3:6] in _FX:
        s = s[:6]  # bo hau to broker
    return s


@dataclass
class ExpertInfo:
    expert_id: str
    source: str
    display_name: str = ""
    url: str = ""
    reputation: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionInfo:
    symbol: str
    side: str  # buy|sell
    volume: float = 0.0
    entry: float | None = None
    sl: float | None = None
    tp: float | None = None
    opened_at: datetime | None = None
    ticket: str | None = None


@dataclass
class SignalInfo:
    symbol: str
    side: str  # buy|sell|flat
    entry: float | None = None
    sl: float | None = None
    tp: float | None = None
    opened_at: datetime | None = None
    status: str = "open"
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpinionInfo:
    """Y KIEN/BAI VIET tham khao cua chuyen gia hoac to chuc (KHONG phai khuyen nghi mua/ban).
    stance: bullish|bearish|neutral (thi truong) hoac hawkish|dovish|neutral (ngan hang trung uong)."""
    url: str
    title: str
    summary: str = ""
    published_at: datetime | None = None
    lang: str = "en"
    symbols: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    stance: str = "neutral"
    stance_score: float = 0.0  # [-1, 1]; > 0 = bullish/hawkish
    author: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
