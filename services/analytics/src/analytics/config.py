from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "interval_seconds": 300,
    "timeframes": ["H1", "H4", "D1"],
    "lookback_bars": {"H1": 800, "H4": 600, "D1": 500},
    "min_bars": 60,
    "resample_missing": True,
    "series_points": 160,
    "symbols": {"include": [], "exclude": [], "max": 300},   # ~240 mã có D1 (forex MT5 + ETF + VN + crypto); trước đây 120 cắt theo thứ tự chữ cái -> thiếu nhiều mã; ~0,3 s/mã/chu kỳ
    "correlation": {"tf": "D1", "window": 30, "max_symbols": 80},
    "sessions_utc": {"tokyo": [0, 9], "london": [7, 16], "newyork": [12, 21]},
    "sessions_days": 30,
    "alerts": {
        "enabled": True,
        "rsi_cross": {"enabled": True, "upper": 70, "lower": 30, "tfs": ["H4", "D1"]},
        "ema200_touch": {"enabled": True, "tfs": ["H4", "D1"]},
        "range_breakout": {"enabled": True, "days": 20, "tfs": ["D1"]},
        "volatility_spike": {"enabled": True, "atr_percentile": 95, "tfs": ["H1", "H4", "D1"]},
        "correlation_flip": {"enabled": True, "min_abs_delta": 0.8},
        "max_per_cycle": 20,
    },
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
class AnalyticsSettings:
    """Biến môi trường. DATABASE_URL = role chỉ-đọc ts_ro; ANALYTICS_DB_RW_URL = role ts_analytics (chỉ ghi analytics_snapshots)."""
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    read_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts_ro:ts_ro@localhost:5432/ts"))
    write_url: str = field(default_factory=lambda: os.getenv("ANALYTICS_DB_RW_URL", ""))
    config_path: str = field(default_factory=lambda: os.getenv("ANALYTICS_CONFIG", ""))
    enabled: bool = field(default_factory=lambda: os.getenv("ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
