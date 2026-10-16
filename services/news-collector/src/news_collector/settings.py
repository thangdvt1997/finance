from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from tscommon.config import Settings


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _num(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class NewsSettings:
    base: Settings = field(default_factory=Settings)
    config_dir: Path = field(default_factory=lambda: Path(os.getenv("NC_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config")))
    src_rss: bool = field(default_factory=lambda: _bool("NC_SRC_RSS", True))
    src_gdelt: bool = field(default_factory=lambda: _bool("NC_SRC_GDELT", True))
    src_cal_official: bool = field(default_factory=lambda: _bool("NC_SRC_CAL_OFFICIAL", True))
    src_cal_central_banks: bool = field(default_factory=lambda: _bool("NC_SRC_CAL_CENTRAL_BANKS", True))
    src_cal_fmp: bool = field(default_factory=lambda: _bool("NC_SRC_CAL_FMP", False))
    fmp_api_key: str = field(default_factory=lambda: os.getenv("FMP_API_KEY", "").strip(), repr=False)
    # Fair Economy (nguon ForexFactory): nguoi dung dong y dung cho he thong ca nhan noi bo -> BAT mac dinh; dat false de tat (xem README: canh bao ToS)
    src_cal_faireconomy: bool = field(default_factory=lambda: _bool("NC_SRC_CAL_FAIRECONOMY", True))
    # 'actual' tu API co quan thong ke (BLS/StatCan/ONS/ABS/Eurostat; FRED neu co key) - cong khai, BAT mac dinh
    src_cal_actuals: bool = field(default_factory=lambda: _bool("NC_SRC_CAL_ACTUALS", True))
    bls_api_key: str = field(default_factory=lambda: os.getenv("BLS_API_KEY", "").strip(), repr=False)
    fred_api_key: str = field(default_factory=lambda: os.getenv("FRED_API_KEY", "").strip(), repr=False)
    # Marketaux Free (tin + entity + sentiment): TU BAT khi co MARKETAUX_TOKEN; NC_SRC_NEWS_MARKETAUX=false de tat
    src_marketaux: bool = field(default_factory=lambda: _bool("NC_SRC_NEWS_MARKETAUX", True))
    marketaux_token: str = field(default_factory=lambda: os.getenv("MARKETAUX_TOKEN", "").strip(), repr=False)
    marketaux_interval: float = field(default_factory=lambda: _num("NC_MARKETAUX_INTERVAL", 1200))
    marketaux_daily_budget: int = field(default_factory=lambda: int(_num("MARKETAUX_DAILY_BUDGET", 70)))
    risk_enabled: bool = field(default_factory=lambda: _bool("NC_RISK_ALERTS", True))
    src_cot: bool = field(default_factory=lambda: _bool("NC_SRC_COT", True))
    src_sec13f: bool = field(default_factory=lambda: _bool("NC_SRC_SEC13F", False))
    rss_interval: float = field(default_factory=lambda: _num("NC_RSS_INTERVAL", 900))
    gdelt_interval: float = field(default_factory=lambda: _num("NC_GDELT_INTERVAL", 900))
    cal_interval: float = field(default_factory=lambda: _num("NC_CAL_INTERVAL", 3600))
    cb_interval: float = field(default_factory=lambda: _num("NC_CB_INTERVAL", 21600))
    cot_interval: float = field(default_factory=lambda: _num("NC_COT_INTERVAL", 21600))
    sec13f_interval: float = field(default_factory=lambda: _num("NC_SEC13F_INTERVAL", 43200))
    alert_window_min: float = field(default_factory=lambda: _num("NC_ALERT_WINDOW_MIN", 30))
    alert_check_interval: float = field(default_factory=lambda: _num("NC_ALERT_CHECK_INTERVAL", 60))
    dedupe_ttl: int = field(default_factory=lambda: int(_num("NC_DEDUPE_TTL", 30 * 86400)))

    @property
    def user_agent(self) -> str:
        return self.base.user_agent
