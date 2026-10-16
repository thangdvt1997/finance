from __future__ import annotations

import os
from dataclasses import dataclass, field


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def _int(name: str, d: int) -> int:
    try:
        return int(os.getenv(name, d))
    except ValueError:
        return d


@dataclass(frozen=True)
class GatewaySettings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts:ts@localhost:5432/ts"))
    api_tokens: tuple[str, ...] = field(default_factory=lambda: tuple(_list("API_TOKENS")))
    auth_disabled: bool = field(default_factory=lambda: os.getenv("AUTH_DISABLED", "").lower() in {"1", "true", "yes"})
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(_list("CORS_ORIGINS")))
    max_page_size: int = field(default_factory=lambda: _int("MAX_PAGE_SIZE", 1000))
    ws_max_connections: int = field(default_factory=lambda: _int("WS_MAX_CONNECTIONS", 100))
    prometheus_url: str = field(default_factory=lambda: os.getenv("PROMETHEUS_URL", ""))
    # HIDE_SOURCES (mac dinh true): phan hoi /v1/* khong chua TEN NGUON du lieu (docs/UI_NO_SOURCES.md). Dat false de debug.
    hide_sources: bool = field(default_factory=lambda: os.getenv("HIDE_SOURCES", "true").strip().lower() not in {"0", "false", "no", "off"})
    # AUTH_TRUST_SECRET: bi mat chia se nginx<->gateway; header X-User-Id/X-Role/X-Accounts chi duoc tin khi X-Auth-Secret khop (api_gateway/authz.py). Rong = tu choi moi header nguoi dung.
    auth_trust_secret: str = field(default_factory=lambda: os.getenv("AUTH_TRUST_SECRET", ""))
