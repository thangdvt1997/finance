"""Cấu hình risk-monitor: mặc định trong mã + YAML ghi đè (RISK_CONFIG). Mọi ngưỡng/kịch bản chỉnh được không cần sửa mã."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Kịch bản LỊCH SỬ (replay): lấy biến động giá thật từ bảng bars D1 trong cửa sổ [start, end], áp lên vị thế HIỆN TẠI.
# Kịch bản GIẢ ĐỊNH: ccy (% giá trị đồng tiền so với mốc trung tính; cặp BASE/QUOTE đổi (1+b)/(1+q)-1), classes (% theo nhóm tài sản),
# symbols (% theo mã), adverse_pct (mọi vị thế cùng bất lợi x%).
SCENARIOS: list[dict] = [
    {"id": "gfc_2008", "type": "replay", "name": "Khủng hoảng tài chính 2008 (Lehman)", "start": "2008-09-12", "end": "2008-11-20"},
    {"id": "chf_2015", "type": "replay", "name": "CHF 2015 (SNB bỏ trần EURCHF)", "start": "2015-01-14", "end": "2015-01-15"},
    {"id": "brexit_2016", "type": "replay", "name": "Brexit 2016", "start": "2016-06-23", "end": "2016-06-27"},
    {"id": "covid_2020", "type": "replay", "name": "Sụp đổ COVID 2020", "start": "2020-02-19", "end": "2020-03-23"},
    {"id": "tightening_2022", "type": "replay", "name": "USD mạnh + lãi suất 2022", "start": "2022-01-03", "end": "2022-09-30"},
    {"id": "yen_carry_2024", "type": "replay", "name": "Yên carry-unwind 08/2024", "start": "2024-07-31", "end": "2024-08-05"},
    {"id": "usd_up_5", "type": "shock", "name": "USD +5% so với mọi đồng khác", "ccy": {"USD": 5}},
    {"id": "usd_down_5", "type": "shock", "name": "USD -5% so với mọi đồng khác", "ccy": {"USD": -5}},
    {"id": "gold_down_10", "type": "shock", "name": "Vàng -10%", "classes": {"gold": -10}},
    {"id": "risk_off", "type": "shock", "name": "Risk-off: cổ phiếu -10%, trú ẩn tăng",
     "classes": {"equity": -10, "bond": 2, "gold": 3, "commodity": -8}, "ccy": {"JPY": 4, "CHF": 3, "AUD": -4, "NZD": -4}},
    {"id": "gap_3", "type": "shock", "name": "Gap cuối tuần: mọi vị thế bất lợi 3%", "adverse_pct": 3},
    {"id": "adverse_10", "type": "shock", "name": "Mọi vị thế bất lợi 10% (thử stop-out)", "adverse_pct": 10},
]

DEFAULTS: dict = {
    "interval_seconds": 60,
    "cache_seconds": 20,
    "default_currency": "USD",
    "returns_lookback_days": 750,       # độ dài lịch sử D1 cho VaR/tương quan
    "min_history_days": 60,             # ít hơn thì bỏ VaR lịch sử
    "ewma_lambda": 0.94,
    "corr_window_days": 120,
    "equity_history_days": 30,
    "var": {"alphas": [0.95, 0.99], "es_alpha": 0.975, "horizons": [1, 10]},
    "mt": {"stop_out_pct": 50.0, "margin_call_pct": 100.0, "margin_level_warn_pct": 200.0},
    "contracts": {"fx": 100000, "XAUUSD": 100, "XAGUSD": 5000, "crypto": 1, "index": 1},
    "instruments": {},                  # ghi đè từng mã: {"US30": {"kind": "index", "quote": "USD", "contract": 1}}
    # ngân sách rủi ro (R6): limit_max = giá trị tối đa; limit_min = tối thiểu (mức margin). warn=80%, crit=100% mức hạn.
    "budget": {
        "warn_ratio": 0.8,
        "mt": {"day_loss_pct": 3.0, "week_loss_pct": 6.0, "dd_pct": 15.0, "leverage_gross": 10.0, "margin_level_min": 200.0,
               "es_1d_pct": 4.0, "ccy_conc_pct": 400.0, "positions": 20},
        "paper": {"day_loss_pct": 2.0, "week_loss_pct": 4.0, "dd_pct": 10.0, "leverage_gross": 2.0, "es_1d_pct": 3.0,
                  "ccy_conc_pct": 150.0, "positions": 40},
        "accounts": {},                 # {"demo-mt4-01": {"dd_pct": 8}}
    },
    "alerts": {"enabled": True, "kinds": ["mt", "paper"], "paper_meaningful_only": True, "min_level": "warn", "cooldown_seconds": 3600},
    "scenarios": SCENARIOS,
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if k == "scenarios" and isinstance(v, list):
            base[k] = v
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | None = None) -> dict:
    cfg = deepcopy(DEFAULTS)
    if path and Path(path).is_file():
        _merge(cfg, yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


@dataclass(frozen=True)
class Settings:
    """DATABASE_URL = role chỉ-đọc ts_ro. REDIS_URL = ts_app (đọc snapshot MT mới nhất + phát alerts.out)."""
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://ts_ro:ts_ro@localhost:5432/ts"))
    config_path: str = field(default_factory=lambda: os.getenv("RISK_CONFIG", ""))
    enabled: bool = field(default_factory=lambda: os.getenv("ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
