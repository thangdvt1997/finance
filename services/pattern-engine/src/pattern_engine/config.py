from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "interval_seconds": 60,
    "timeframes": ["M15"],
    "lookback_bars": {"M5": 900, "M15": 700, "H1": 600, "H4": 500, "D1": 400},
    "symbols": {"include": [], "exclude": [], "max": 40},
    "patterns": ["KB-1", "KB-2", "KB-3", "KB-4"],
    "max_age_bars": 3,           # chỉ phát sự kiện có nến đổi trạng thái trong N nến gần nhất (replay không làm ngập bus)
    "emit_forming": True,
    "overrides": {},             # {"common"|"KB-n": {tham số: giá trị}} ghi đè spec/*.yaml
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_yaml(path: str | None) -> dict:
    cfg = deepcopy(DEFAULTS)
    if path and Path(path).is_file():
        _merge(cfg, yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


@dataclass(frozen=True)
class Settings:
    """DATABASE_URL = role chỉ-đọc ts_ro (đọc nến); PATTERN_DB_RW_URL = role ts_pattern (CHỈ bảng pattern_signals)."""
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    read_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts_ro:ts_ro@localhost:5432/ts"))
    write_url: str = field(default_factory=lambda: os.getenv("PATTERN_DB_RW_URL", ""))
    config_path: str = field(default_factory=lambda: os.getenv("PATTERN_CONFIG", ""))
    enabled: bool = field(default_factory=lambda: os.getenv("ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
