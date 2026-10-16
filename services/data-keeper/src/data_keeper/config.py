from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
# cửa sổ kiểm kê khoảng thiếu theo khung (giây): nhỏ để truy vấn rẻ (chunk exclusion)
TF_WINDOW = {"M1": 6 * 3600, "M5": 24 * 3600, "M15": 3 * 86400, "H1": 7 * 86400, "H4": 14 * 86400, "D1": 60 * 86400}


@dataclass(frozen=True)
class Settings:
    service_name: str = field(default_factory=lambda: os.getenv("SERVICE_NAME", "data-keeper"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    enabled: bool = field(default_factory=lambda: _b("DATA_KEEPER_ENABLED", True))
    ro_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))          # role chỉ đọc ts_ro
    rw_url: str = field(default_factory=lambda: os.getenv("DK_DB_RW_URL", ""))          # role ghi hẹp ts_dk (schema dk.*)
    interval_s: float = field(default_factory=lambda: _f("DK_INVENTORY_INTERVAL_S", 300))
    first_delay_s: float = field(default_factory=lambda: _f("DK_FIRST_DELAY_S", 20))
    cycle_timeout_s: float = field(default_factory=lambda: _f("DK_CYCLE_TIMEOUT_S", 240))
    nice: int = field(default_factory=lambda: int(_f("DK_NICE", 10)))
    tfs: tuple = field(default_factory=lambda: tuple(x for x in os.getenv("DK_TFS", "M1,M5,M15,H1,H4,D1").split(",") if x in TF_SECONDS))
    universe_days: int = field(default_factory=lambda: int(_f("DK_UNIVERSE_DAYS", 3)))
    tick_fresh_s: float = field(default_factory=lambda: _f("DK_TICK_FRESH_S", 180))
    open_grace_s: float = field(default_factory=lambda: _f("DK_OPEN_GRACE_S", 1800))   # sau khi mở cửa, chưa quy BROKEN
    bridge_metrics_url: str = field(default_factory=lambda: os.getenv("DK_BRIDGE_METRICS_URL", "http://mt-bridge:8000/metrics"))
    p95_max_s: float = field(default_factory=lambda: _f("DK_P95_MAX_S", 0.5))           # ngưỡng cho guard (heal/backfill dừng khi vượt)
    modules: tuple = field(default_factory=lambda: tuple(x.strip() for x in os.getenv("DK_MODULES", "inventory,rollup,heal,backfill,histload,llm,api").split(",") if x.strip()))


@lru_cache
def get_settings() -> Settings:
    return Settings()
