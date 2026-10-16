from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

LEVELS = {"info": 0, "warn": 1, "crit": 2}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class AlertSettings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    port: int = field(default_factory=lambda: _int("PORT", 8000))
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    telegram_api_base: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org"))
    # Danh sách URL Apprise (phân tách bằng dấu phẩy/khoảng trắng/xuống dòng): tgram://, ntfy://, slack://, discord://, mailto://...
    apprise_urls: str = field(default_factory=lambda: os.getenv("APPRISE_URLS", ""))
    dedupe_window_s: int = field(default_factory=lambda: _int("DEDUPE_WINDOW_S", 300))
    rate_limit_per_min: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MIN", 20))
    digest_interval_s: int = field(default_factory=lambda: _int("DIGEST_INTERVAL_S", 60))
    rules_file: str = field(default_factory=lambda: os.getenv("RULES_FILE", ""))
    routes_file: str = field(default_factory=lambda: os.getenv("ROUTES_FILE", ""))
    webhook_token: str = field(default_factory=lambda: os.getenv("ALERT_WEBHOOK_TOKEN", ""))
    group: str = "alert-service"
    # Tên consumer ỔN ĐỊNH (không dùng HOSTNAME: đổi mỗi lần container recreate -> PEL mồ côi).
    consumer: str = field(default_factory=lambda: os.getenv("CONSUMER_NAME", "alert-1"))
    # Gửi đồng thời có giới hạn + circuit breaker
    send_concurrency: int = field(default_factory=lambda: _int("SEND_CONCURRENCY", 4))
    send_timeout_s: float = field(default_factory=lambda: float(os.getenv("SEND_TIMEOUT_S", "8")))
    breaker_threshold: int = field(default_factory=lambda: _int("BREAKER_THRESHOLD", 5))
    breaker_cooldown_s: float = field(default_factory=lambda: float(os.getenv("BREAKER_COOLDOWN_S", "60")))
    # Backlog (đang chờ + đang gửi) >= ngưỡng này thì tin non-crit mới được gom vào digest thay vì xếp hàng
    backlog_digest_threshold: int = field(default_factory=lambda: _int("BACKLOG_DIGEST_THRESHOLD", 20))
    max_inflight: int = field(default_factory=lambda: _int("MAX_INFLIGHT", 64))
    # Phục hồi message mồ côi (XAUTOCLAIM)
    reclaim_min_idle_ms: int = field(default_factory=lambda: _int("RECLAIM_MIN_IDLE_MS", 60000))
    reclaim_interval_s: float = field(default_factory=lambda: float(os.getenv("RECLAIM_INTERVAL_S", "30")))
    max_deliveries: int = field(default_factory=lambda: _int("MAX_DELIVERIES", 5))

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def apprise_url_list(self) -> list[str]:
        return [u for u in re.split(r"[\s,]+", self.apprise_urls.strip()) if u]


DEFAULT_ROUTES = {
    "routes": [
        {"name": "crit-all", "min_level": "crit", "channels": ["telegram", "apprise", "log"]},
        # bo loc rui ro tin (news-collector): sap vao / dang trong / het cua so -> ntfy (apprise) + log, khong lam on Telegram
        {"name": "risk-window", "min_level": "info", "tags_any": ["risk-window"], "channels": ["apprise", "log"]},
        # chất lượng dữ liệu (gap/outlier theo mã) chỉ ghi log + bảng alerts, không đẩy ntfy/Telegram (nhiễu ~9 tin/mã)
        {"name": "quality", "min_level": "info", "tags_any": ["quality"], "channels": ["log"]},
        {"name": "default", "min_level": "info", "channels": ["telegram", "apprise"]},
    ]
}

DEFAULT_RULES = {
    "rules": [
        {"name": "heartbeat-daily", "type": "heartbeat", "at": "01:00", "level": "info"},
    ]
}


def load_yaml(path: str, default: dict) -> dict:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    return yaml.safe_load(p.read_text(encoding="utf-8")) or default
