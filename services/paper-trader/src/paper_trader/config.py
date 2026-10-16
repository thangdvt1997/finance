"""Cấu hình: biến môi trường (kết nối) + YAML (tài khoản mô phỏng, chi phí, rủi ro)."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import Instrument

DEFAULTS: dict = {
    "interval_seconds": 300,
    "tf": "D1",
    "history_bars": 520,              # số bar nạp mỗi chu kỳ cho mỗi symbol (>= required_history của chiến lược)
    "periods_per_year": 252,
    "max_pending_steps": 5,           # lệnh chờ quá số bước này mà không có bar -> hết hạn
    "events_stream": "paper.events",
    "alerts_enabled": True,
    "risk_windows_url": "",           # vd http://api-gateway:8000/v1/risk-windows (CHƯA có -> dùng news_windows tĩnh)
    "risk_windows_token_env": "",     # tên biến môi trường chứa X-API-Key nếu endpoint yêu cầu
    "news_windows": [],               # [{start: ISO, end: ISO, currencies: [USD], symbols: [], title: ""}]
    "instrument_defaults": {
        "fx": {"kind": "fx", "quote": "USD", "lot": 1000, "spread_bps": 1.5, "slippage_bps": 0.5, "slip_range_frac": 0.02,
               "commission_bps": 0.3, "swap_long_bps": 200, "swap_short_bps": 200, "shortable": True},
        "metal": {"kind": "metal", "quote": "USD", "lot": 0.01, "spread_bps": 3.0, "slippage_bps": 1.0, "slip_range_frac": 0.02,
                  "commission_bps": 0.5, "swap_long_bps": 300, "swap_short_bps": 300, "shortable": True},
        # ETF/cổ phiếu Mỹ (US:SPY...), tài khoản USD, mô phỏng vị thế đòn bẩy kiểu CFD/futures: swap = funding + markup (bảo thủ)
        "equity_us": {"kind": "equity", "quote": "USD", "lot": 1, "spread_bps": 4.0, "slippage_bps": 1.0, "slip_range_frac": 0.02,
                      "commission_bps": 1.0, "swap_long_bps": 350, "swap_short_bps": 350, "shortable": True},
        "equity_vn": {"kind": "equity", "quote": "VND", "lot": 100, "spread_bps": 10.0, "slippage_bps": 5.0, "slip_range_frac": 0.02,
                      "commission_bps": 15.0, "sell_tax_bps": 10.0, "swap_long_bps": 0, "swap_short_bps": 0, "shortable": False},
        # Crypto spot (CRYPTO:<BASE>USDT): USDT coi ~ USD; KHONG nam trong universe chien luoc hien tai (chi de khong bi nhan nham la cap FX)
        "crypto": {"kind": "crypto", "quote": "USD", "lot": 0.0001, "spread_bps": 8.0, "slippage_bps": 3.0, "slip_range_frac": 0.02,
                   "commission_bps": 10.0, "swap_long_bps": 0, "swap_short_bps": 0, "shortable": False},
    },
    "instruments": {},                # ghi đè theo symbol: {EURUSD: {spread_bps: 2.0, ...}}
    "accounts": [],
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


def infer_class(symbol: str) -> str:
    if symbol.startswith("VN:"):
        return "equity_vn"
    if symbol.startswith("US:"):
        return "equity_us"
    if symbol.startswith("CRYPTO:"):
        return "crypto"
    if symbol[:3] in {"XAU", "XAG", "XPT", "XPD"}:
        return "metal"
    return "fx"


def instrument_for(cfg: dict, symbol: str) -> Instrument:
    base = dict(cfg["instrument_defaults"][infer_class(symbol)])
    base.update((cfg.get("instruments") or {}).get(symbol, {}))
    if infer_class(symbol) == "fx" and "quote" not in (cfg.get("instruments") or {}).get(symbol, {}):
        base["quote"] = symbol[3:6]          # EURUSD -> USD, USDJPY -> JPY
    return Instrument(symbol=symbol, **base)


def _truthy(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """DATABASE_URL = role chỉ-đọc ts_ro (nến/analytics); PAPER_DB_RW_URL = role ts_paper (CHỈ bảng paper_*)."""
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    read_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts_ro:ts_ro@localhost:5432/ts"))
    write_url: str = field(default_factory=lambda: os.getenv("PAPER_DB_RW_URL", ""))
    config_path: str = field(default_factory=lambda: os.getenv("PAPER_CONFIG", ""))
    strategy_dir: str = field(default_factory=lambda: os.getenv("PAPER_STRATEGY_DIR", ""))
    admin_token: str = field(default_factory=lambda: os.getenv("PAPER_ADMIN_TOKEN", ""))
    card_dir: str = field(default_factory=lambda: os.getenv("PAPER_CARD_DIR", "/app/services/paper-trader/cards"))
    monitor_interval: float = field(default_factory=lambda: float(os.getenv("PAPER_MONITOR_INTERVAL", "3600")))
    enabled: bool = field(default_factory=lambda: _truthy(os.getenv("ENABLED", "true")))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
