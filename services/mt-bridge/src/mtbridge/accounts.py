"""Cau hinh theo tung tai khoan (YAML): mapping symbol/hau to, mui gio server, nguong canh bao."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Platform


class AlertRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heartbeat_timeout_s: float = 90.0
    drawdown_pct: float = 10.0  # equity giam so voi dinh (high-water mark) >= nguong -> crit
    margin_level_warn: float = 200.0  # %
    margin_level_crit: float = 100.0
    new_position: bool = True  # canh bao vi the moi ngoai du kien
    expected_magics: list[int] = Field(default_factory=list)  # vi the co magic nay la "du kien"
    expected_tickets: list[str] = Field(default_factory=list)


class AccountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str
    platform: Platform
    transport: str = "agent"  # "agent" (EA outbound) | "mt5_direct" (package Python, chi Windows)
    token_env: str = ""  # ten bien moi truong chua token ingest (KHONG dat token vao YAML)
    hmac_secret_env: str = ""  # tuy chon: neu co thi bat buoc chu ky HMAC (xem ingest.py)
    require_hmac: Optional[bool] = None  # theo tai khoan: True = bat buoc (thieu secret -> tu choi); False = chi kiem khi co chu ky; None = theo MT_REQUIRE_HMAC / co secret
    # --- chi cho mt5_direct ---
    login: int = 0
    server: str = ""
    password_env: str = ""  # ten bien moi truong chua mat khau INVESTOR (chi doc)
    terminal_path: str = ""
    require_investor: bool = True  # tu choi chay neu tai khoan cho phep giao dich (khong phai investor)
    # --- chuan hoa ---
    symbol_prefix: str = ""
    symbol_suffix: str = ""
    symbol_aliases: dict[str, str] = Field(default_factory=dict)  # ten broker -> ten chuan
    watch_symbols: list[str] = Field(default_factory=list)  # ten CHUAN
    timeframes: list[str] = Field(default_factory=lambda: ["M1", "M5", "M15", "H1", "H4", "D1"])
    server_tz: str = ""  # vd "Europe/Athens"; rong -> suy ra tu server_time EA gui / hoac server_utc_offset_hours
    server_utc_offset_hours: Optional[float] = None
    rules: AlertRules = Field(default_factory=AlertRules)

    @model_validator(mode="after")
    def _check(self):
        if self.transport not in ("agent", "mt5_direct"):
            raise ValueError("transport phai la agent|mt5_direct")
        if self.transport == "mt5_direct" and self.platform != "mt5":
            raise ValueError("mt5_direct chi danh cho platform mt5")
        return self

    # ---- symbol ----
    def to_canonical(self, broker_symbol: str) -> str:
        if broker_symbol in self.symbol_aliases:
            return self.symbol_aliases[broker_symbol].upper()
        s = broker_symbol
        if self.symbol_prefix and s.startswith(self.symbol_prefix):
            s = s[len(self.symbol_prefix):]
        if self.symbol_suffix and s.endswith(self.symbol_suffix):
            s = s[: -len(self.symbol_suffix)]
        return s.upper()

    def to_broker(self, canonical: str) -> str:
        for b, c in self.symbol_aliases.items():
            if c.upper() == canonical.upper():
                return b
        return f"{self.symbol_prefix}{canonical}{self.symbol_suffix}"

    # ---- thoi gian ----
    def server_epoch_to_utc(self, epoch: float, derived_offset_s: Optional[float] = None) -> datetime:
        """Thoi gian MT (MqlRates.time, ORDER_TIME...) la 'gio dia phuong server dong goi nhu epoch'.

        Uu tien: server_tz (xu ly DST) > server_utc_offset_hours > offset suy ra tu EA > 0.
        """
        naive = datetime.fromtimestamp(0, timezone.utc).replace(tzinfo=None) + timedelta(seconds=float(epoch))
        if self.server_tz:
            local = naive.replace(tzinfo=ZoneInfo(self.server_tz))
            return local.astimezone(timezone.utc)
        if self.server_utc_offset_hours is not None:
            off = self.server_utc_offset_hours * 3600
        elif derived_offset_s is not None:
            off = derived_offset_s
        else:
            off = 0.0
        return (naive - timedelta(seconds=off)).replace(tzinfo=timezone.utc)

    def utc_to_server_epoch(self, dt: datetime) -> float:
        """Nghich dao cua server_epoch_to_utc (dung khi hoi MT5 theo khoang thoi gian)."""
        dt = dt.astimezone(timezone.utc)
        if self.server_tz:
            local = dt.astimezone(ZoneInfo(self.server_tz))
            return local.replace(tzinfo=timezone.utc).timestamp()
        off = (self.server_utc_offset_hours or 0.0) * 3600
        return dt.timestamp() + off

    # ---- secret tu env ----
    def token(self) -> str:
        return os.getenv(self.token_env, "") if self.token_env else ""

    def hmac_secret(self) -> str:
        return os.getenv(self.hmac_secret_env, "") if self.hmac_secret_env else ""

    def password(self) -> str:
        return os.getenv(self.password_env, "") if self.password_env else ""


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounts: list[AccountConfig]

    def by_id(self) -> dict[str, AccountConfig]:
        d = {a.account_id: a for a in self.accounts}
        if len(d) != len(self.accounts):
            raise ValueError("account_id trung lap")
        return d


def load_config(path: str) -> BridgeConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cfg = BridgeConfig.model_validate(data)
    cfg.by_id()
    return cfg
