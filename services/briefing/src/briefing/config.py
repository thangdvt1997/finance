"""Cấu hình từ biến môi trường (compose đặt tường minh)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _b(v: str | None, d: bool) -> bool:
    return d if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _load_secrets_file() -> None:
    """Nạp KEY=VALUE từ file mount :ro (BRIEFING_SECRETS_FILE) vào os.environ nếu biến chưa có.
    Giữ mật khẩu/DSN khỏi Config.Env (docker inspect). Không ghi log giá trị."""
    path = os.getenv("BRIEFING_SECRETS_FILE", "").strip()
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v
    except OSError:
        pass


_load_secrets_file()


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))        # ts_ro (chỉ đọc dữ liệu thị trường)
    db_rw_url: str = field(default_factory=lambda: os.getenv("BRIEFING_DB_RW_URL", ""))     # ts_briefing (CHỈ bảng briefings)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    llm_url: str = field(default_factory=lambda: os.getenv("BRIEFING_LLM_URL", "http://briefing-llm:8080").rstrip("/"))
    llm_fallback_url: str = field(default_factory=lambda: os.getenv("BRIEFING_LLM_FALLBACK_URL", "").rstrip("/"))  # rỗng = không fallback
    llm_pool_timeout_s: float = field(default_factory=lambda: float(os.getenv("BRIEFING_LLM_POOL_TIMEOUT_S", "120")))  # timeout đường chính (pool) trước khi fallback
    llm_model: str = field(default_factory=lambda: os.getenv("BRIEFING_LLM_MODEL", "unknown"))  # nhãn phiên bản mô hình ghi vào bản tin
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("BRIEFING_LLM_TIMEOUT_S", "900")))
    llm_max_tokens: int = field(default_factory=lambda: int(os.getenv("BRIEFING_LLM_MAX_TOKENS", "1100")))
    llm_enabled: bool = field(default_factory=lambda: _b(os.getenv("BRIEFING_LLM_ENABLED"), True))  # false = luôn dùng bản mẫu (template)
    tz: str = field(default_factory=lambda: os.getenv("BRIEFING_TZ", "Asia/Ho_Chi_Minh"))
    schedule: str = field(default_factory=lambda: os.getenv("BRIEFING_SCHEDULE", "06:15=morning,16:30=close"))
    scopes: str = field(default_factory=lambda: os.getenv("BRIEFING_SCOPES", "vn,intl"))
    scheduler_enabled: bool = field(default_factory=lambda: _b(os.getenv("BRIEFING_SCHEDULER"), True))
    notify: bool = field(default_factory=lambda: _b(os.getenv("BRIEFING_NOTIFY"), True))
    admin_token: str = field(default_factory=lambda: os.getenv("BRIEFING_ADMIN_TOKEN", ""))
    max_news: int = field(default_factory=lambda: int(os.getenv("BRIEFING_MAX_NEWS", "22")))
    min_points: int = field(default_factory=lambda: int(os.getenv("BRIEFING_MIN_POINTS", "3")))
    max_points: int = field(default_factory=lambda: int(os.getenv("BRIEFING_MAX_POINTS", "8")))
    ai_url: str = field(default_factory=lambda: os.getenv("AI_TRADING_URL", "http://ai-trading:8000").rstrip("/"))
    analyst_ttl_s: int = field(default_factory=lambda: int(os.getenv("ANALYST_TTL_S", "600")))
    analyst_timeout_s: float = field(default_factory=lambda: float(os.getenv("ANALYST_LLM_TIMEOUT_S", "270")))
    public_base: str = field(default_factory=lambda: os.getenv("REPORT_BASE_URL", ""))


def settings() -> Settings:
    return Settings()
