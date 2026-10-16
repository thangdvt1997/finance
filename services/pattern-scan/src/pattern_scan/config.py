from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "fresh_bars": 3,
    "stale_bars": {"forming": 48, "armed": 160},
    "render": {"enabled": True, "bars_before": 60, "max_bars": 260, "bars_after": 0, "size": [1600, 800], "max_kb": 180, "tz_offset_h": 7},
    "notify": {"enabled": True, "states": ["armed", "triggered"], "on_close": True, "max_per_min": 20, "min_score": 0},
    "paper": {"enabled": True, "max_hold_bars": 192, "cost_bps": {"default": 2.0}},
    "guardrail": {},   # xem guardrail.DEFAULTS (enabled mặc định True)
    # Kịch bản được xử lý: None = mọi kịch bản; [] = tắt (bỏ qua mọi tín hiệu); ["KB-1", ...] = chỉ các kịch bản đó.
    "patterns_enabled": None,
    "monitor_interval_s": 60,
    "backfill": {"days": 3, "interval_s": 600},
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_cfg(path: str | None) -> dict:
    cfg = deepcopy(DEFAULTS)
    if path and Path(path).is_file():
        _merge(cfg, yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


@dataclass(frozen=True)
class Settings:
    """DATABASE_URL = ts_ro (đọc nến + pattern_signals); PSCAN_DB_RW_URL = ts_pscan (CHỈ bảng pattern_scan_*/pattern_paper_*)."""
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    read_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    write_url: str = field(default_factory=lambda: os.getenv("PSCAN_DB_RW_URL", ""))
    config_path: str = field(default_factory=lambda: os.getenv("PATTERN_SCAN_CONFIG", ""))
    examples_dir: str = field(default_factory=lambda: os.getenv("PATTERN_EXAMPLES_DIR", "/examples"))
    backtest_dir: str = field(default_factory=lambda: os.getenv("PATTERN_BACKTEST_DIR", "/backtest"))
    ntfy_url: str = field(default_factory=lambda: os.getenv("NTFY_URL", "http://ntfy:80"))
    ntfy_topic: str = field(default_factory=lambda: os.getenv("PATTERN_NTFY_TOPIC", "tradingsys-patterns"))
    ntfy_token: str = field(default_factory=lambda: os.getenv("NTFY_TOKEN", ""))
    click_url: str = field(default_factory=lambda: os.getenv("PATTERN_CLICK_URL", ""))
    enabled: bool = field(default_factory=lambda: os.getenv("ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
    consumer: str = field(default_factory=lambda: os.getenv("HOSTNAME", "pattern-scan-1"))
