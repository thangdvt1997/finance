from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    service_name: str = field(default_factory=lambda: os.getenv("SERVICE_NAME", "unknown"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts:ts@localhost:5432/ts"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    user_agent: str = field(default_factory=lambda: os.getenv("USER_AGENT", "trading-system/0.1 (contact: set USER_AGENT)"))
    enabled: bool = field(default_factory=lambda: _bool(os.getenv("ENABLED"), True))


@lru_cache
def get_settings() -> Settings:
    return Settings()
