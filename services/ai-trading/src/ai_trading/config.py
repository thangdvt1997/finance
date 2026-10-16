from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    registry_dir: str = field(default_factory=lambda: os.getenv("AI_REGISTRY_DIR", "/app/services/ai-trading/registry"))
    research_dir: str = field(default_factory=lambda: os.getenv("AI_RESEARCH_DIR", "/research/pattern_sell"))
    scan_url: str = field(default_factory=lambda: os.getenv("PATTERN_SCAN_URL", "http://pattern-scan:8000").rstrip("/"))
    paper_url: str = field(default_factory=lambda: os.getenv("PAPER_TRADER_URL", "http://paper-trader:8000").rstrip("/"))
    arena_ttl_s: int = field(default_factory=lambda: int(os.getenv("AI_ARENA_TTL_S", "30")))
    state_dir: str = field(default_factory=lambda: os.getenv("AI_STATE_DIR", "/state"))
    regime_dir: str = field(default_factory=lambda: os.getenv("AI_REGIME_DIR", "/research/regime"))
    track_url: str = field(default_factory=lambda: os.getenv("TRACK_RECORD_URL", "http://track-record:8000").rstrip("/"))
    class_dir: str = field(default_factory=lambda: os.getenv("AI_CLASS_DIR", "/classroom"))
    class_msg_rate: int = field(default_factory=lambda: int(os.getenv("AI_CLASS_MSG_RATE", "12")))      # tin nhắn/phút/người
    class_write_rate: int = field(default_factory=lambda: int(os.getenv("AI_CLASS_WRITE_RATE", "90")))  # thao tác ghi/phút/người
