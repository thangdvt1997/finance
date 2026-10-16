"""Cấu hình từ biến môi trường (không có bí mật nào ngoài API key nội bộ tới gateway)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _hhmm(s: str) -> tuple[int, int]:
    h, m = s.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(s)
    return h, m


@dataclass(frozen=True)
class Settings:
    gateway_url: str = "http://api-gateway:8000"
    api_key: str = ""
    tz: str = "Asia/Ho_Chi_Minh"
    daily_at: tuple[int, int] = (6, 30)
    weekly_dow: int = 6                 # 0=Thứ hai ... 6=Chủ nhật
    weekly_at: tuple[int, int] = (19, 0)
    data_dir: Path = Path("/data")
    keep_daily: int = 60
    keep_weekly: int = 26
    base_url: str = ""
    redis_url: str = ""
    enabled: bool = True
    http_timeout: float = 20.0
    tick_seconds: float = 60.0
    auth_url: str = "http://auth:8000"      # auth nội bộ (phân giải phạm vi lịch + tuân thủ luật): /internal/fleet/*
    internal_token: str = field(default="", repr=False)                # FLEET_INTERNAL_TOKEN (Bearer); rỗng -> mục tuân thủ "chưa có dữ liệu", lịch theo phạm vi không chạy
    # Danh sách mã đưa vào bảng thị trường: (nhóm, mã, nhãn)
    instruments: tuple = field(default_factory=lambda: (
        ("FX", "EURUSD", "EUR/USD"), ("FX", "GBPUSD", "GBP/USD"), ("FX", "USDJPY", "USD/JPY"),
        ("FX", "AUDUSD", "AUD/USD"), ("FX", "USDCAD", "USD/CAD"), ("FX", "USDCHF", "USD/CHF"),
        ("Vàng", "XAUUSD", "Vàng (XAU/USD)"),
        ("Chỉ số / ETF Mỹ", "US:SPY", "SPY (S&P 500)"), ("Chỉ số / ETF Mỹ", "US:QQQ", "QQQ (Nasdaq 100)"),
        ("Chỉ số / ETF Mỹ", "US:IWM", "IWM (Russell 2000)"), ("Chỉ số / ETF Mỹ", "US:TLT", "TLT (TP dài hạn)"),
        ("Chỉ số / ETF Mỹ", "US:GLD", "GLD (vàng)"), ("Chỉ số / ETF Mỹ", "US:USO", "USO (dầu)"),
        ("Việt Nam", "VN:VNM", "VNM"), ("Việt Nam", "VN:FPT", "FPT"), ("Việt Nam", "VN:VCB", "VCB"),
    ))

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        e = os.environ if env is None else env
        return cls(
            gateway_url=e.get("GATEWAY_URL", "http://api-gateway:8000").rstrip("/"),
            api_key=e.get("API_KEY", ""),
            tz=e.get("REPORT_TZ", "Asia/Ho_Chi_Minh"),
            daily_at=_hhmm(e.get("REPORT_DAILY_AT", "06:30")),
            weekly_dow=int(e.get("REPORT_WEEKLY_DOW", "6")),
            weekly_at=_hhmm(e.get("REPORT_WEEKLY_AT", "19:00")),
            data_dir=Path(e.get("DATA_DIR", "/data")),
            keep_daily=int(e.get("REPORT_KEEP_DAILY", "60")),
            keep_weekly=int(e.get("REPORT_KEEP_WEEKLY", "26")),
            base_url=e.get("REPORT_BASE_URL", "").strip().rstrip("/"),
            redis_url=e.get("REDIS_URL", ""),
            enabled=e.get("ENABLED", "true").lower() in ("1", "true", "yes"),
            auth_url=e.get("FLEET_AUTH_URL", "http://auth:8000").rstrip("/"),
            internal_token=e.get("FLEET_INTERNAL_TOKEN", ""),
        )

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"
