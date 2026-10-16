from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, d: int) -> int:
    try:
        return int(os.getenv(name, d))
    except ValueError:
        return d


def _bool(name: str, d: bool) -> bool:
    v = os.getenv(name)
    return d if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    db_url: str = field(default_factory=lambda: os.getenv("AUTH_DB_URL", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("AUTH_SECRET_KEY", ""))   # Fernet (HMAC secret EA + TOTP)
    cookie_name: str = field(default_factory=lambda: os.getenv("AUTH_COOKIE_NAME", "ts_session"))
    cookie_secure: bool = field(default_factory=lambda: _bool("AUTH_COOKIE_SECURE", True))
    # thời hạn phiên (giờ): tuyệt đối / không hoạt động
    master_ttl_h: int = field(default_factory=lambda: _int("AUTH_MASTER_TTL_H", 12))
    master_idle_h: int = field(default_factory=lambda: _int("AUTH_MASTER_IDLE_H", 2))
    client_ttl_h: int = field(default_factory=lambda: _int("AUTH_CLIENT_TTL_H", 168))
    client_idle_h: int = field(default_factory=lambda: _int("AUTH_CLIENT_IDLE_H", 48))
    # khoá tạm: sau N lần sai liên tiếp -> khoá lock_minutes
    max_fails: int = field(default_factory=lambda: _int("AUTH_MAX_FAILS", 5))
    lock_minutes: int = field(default_factory=lambda: _int("AUTH_LOCK_MINUTES", 15))
    ip_fail_limit: int = field(default_factory=lambda: _int("AUTH_IP_FAIL_LIMIT", 30))      # số lần sai tối đa / cửa sổ / IP
    ip_window_s: int = field(default_factory=lambda: _int("AUTH_IP_WINDOW_S", 600))
    pairing_days: int = field(default_factory=lambda: _int("AUTH_PAIRING_DAYS", 7))
    min_password_len: int = field(default_factory=lambda: _int("AUTH_MIN_PASSWORD_LEN", 10))
    # tiền tố đường dẫn công khai (không cần phiên) — vỏ tĩnh của client-ui. KHÔNG bao giờ áp cho /api/
    public_prefixes: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip() for x in os.getenv("AUTH_PUBLIC_PREFIXES", "/c/").split(",") if x.strip()))
    totp_issuer: str = field(default_factory=lambda: os.getenv("AUTH_TOTP_ISSUER", "Tram thi truong"))
    # token dịch vụ 2 chiều auth<->mt-bridge (/internal/*); rỗng = tắt toàn bộ /internal (503)
    internal_token: str = field(default_factory=lambda: os.getenv("AUTH_INTERNAL_TOKEN") or os.getenv("BRIDGE_AUTH_TOKEN", ""))
    bridge_url: str = field(default_factory=lambda: os.getenv("AUTH_BRIDGE_URL", "http://mt-bridge:8000").rstrip("/"))
    self_register: bool = field(default_factory=lambda: _bool("AUTH_SELF_REGISTER", True))   # EA tự đăng ký (pending + mã ghép cặp) khi chưa có tài khoản
    self_register_per_ip_h: int = field(default_factory=lambda: _int("AUTH_SELF_REGISTER_PER_IP_H", 5))
    max_unclaimed: int = field(default_factory=lambda: _int("AUTH_MAX_UNCLAIMED", 500))
    # token dịch vụ 2 chiều auth<->mt-bridge (/internal/*); rỗng = tắt toàn bộ /internal (503)
    internal_token: str = field(default_factory=lambda: os.getenv("AUTH_INTERNAL_TOKEN") or os.getenv("BRIDGE_AUTH_TOKEN", ""))
    bridge_url: str = field(default_factory=lambda: os.getenv("AUTH_BRIDGE_URL", "http://mt-bridge:8000").rstrip("/"))
    self_register: bool = field(default_factory=lambda: _bool("AUTH_SELF_REGISTER", True))   # EA tự đăng ký (pending + mã ghép cặp) khi chưa có tài khoản
    self_register_per_ip_h: int = field(default_factory=lambda: _int("AUTH_SELF_REGISTER_PER_IP_H", 5))
    max_unclaimed: int = field(default_factory=lambda: _int("AUTH_MAX_UNCLAIMED", 500))
    # quản trị đội tài khoản (docs/FLEET_MGMT.md)
    master_totp_required: bool = field(default_factory=lambda: _bool("AUTH_MASTER_TOTP_REQUIRED", True))   # thao tác nhạy cảm cần master đã bật TOTP
    master_totp_enforce: bool = field(default_factory=lambda: _bool("AUTH_MASTER_TOTP_ENFORCE", False))    # 2FA BẮT BUỘC cho mọi /api của master (service.totp_gate); mặc định TẮT — cần người dùng quyết
    view_as_minutes: int = field(default_factory=lambda: _int("AUTH_VIEW_AS_MINUTES", 30))
    fleet_token: str = field(default_factory=lambda: os.getenv("FLEET_INTERNAL_TOKEN", ""))                 # risk-monitor/reporter -> /internal/fleet/*
