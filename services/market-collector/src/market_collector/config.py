from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .models import TF_SECONDS
from .symbols import parse_symbol_list

ALL_PROVIDERS = ("dukascopy", "frankfurter", "vnstock", "twelvedata", "stooq", "yahoo",
                 "oanda", "truefx", "alpaca", "tiingo", "fred", "yahoo_daily", "crypto_ccxt")
# nguon mien phi (goi 0 dong): tu bat khi co key/tai khoan trong env, thieu -> tat gon + hien trang thai "can key"
DEFAULT_PROVIDERS = "dukascopy,frankfurter,vnstock,twelvedata,oanda,truefx,alpaca,tiingo,fred,crypto_ccxt"
RISKY_PROVIDERS = {"stooq", "yahoo", "yahoo_daily"}

_DEFAULT_SYMBOLS = {
    "dukascopy": "EURUSD,GBPUSD,USDJPY,XAUUSD,AUDUSD,USDCAD,USDCHF,NZDUSD,XAGUSD",   # 7 cap quy USD -> suc manh 8 tien te dung ca H1/H4
    "frankfurter": "EURUSD,GBPUSD,USDJPY",
    "vnstock": "VN:VNM,VN:FPT,VN:VCB",
    "twelvedata": "",
    "stooq": "",
    "yahoo": "",
    "oanda": "EURUSD,GBPUSD,USDJPY,XAUUSD",
    "truefx": "EURUSD,GBPUSD,USDJPY",
    "alpaca": "US:SPY,US:QQQ,US:AAPL,US:MSFT,US:NVDA",
    "tiingo": "US:SPY,US:QQQ,US:AAPL",
    "fred": "FRED:DGS10,FRED:DGS2,FRED:DFF,FRED:T10YIE,FRED:DTWEXBGS",
    "crypto_ccxt": ",".join(f"CRYPTO:{b}USDT" for b in (
        "BTC ETH BNB SOL XRP ADA DOGE TON AVAX LINK DOT LTC TRX BCH ATOM NEAR UNI XLM ETC APT ARB OP SUI INJ AAVE FIL HBAR SHIB ICP").split()),   # CRYPTO:<BASE>USDT, ~29 cap von hoa lon (san khong co cap nao thi bo qua gon)
    # universe trend cham da tai san (cong cu giao dich paper: ETF My + vang). Xem docs/DATA_SOURCE_PRIORITY.md
    "yahoo_daily": ("XAUUSD,VN:VNM,VN:FPT,VN:VCB,US:SPY,US:QQQ,US:IWM,US:EWG,US:FEZ,US:EWQ,US:EWU,US:EWJ,US:EWH,US:EWA,US:EWY,US:INDA,US:EWZ,US:VNM,"
                    "US:SHY,US:IEI,US:IEF,US:TLT,US:AGG,US:GLD,US:SLV,US:CPER,US:USO,US:BNO,US:UNG,US:CORN,US:WEAT,US:SOYB,US:CANE,"
                    "US:AAPL,US:MSFT,US:NVDA,US:AMZN,US:GOOGL,US:META,US:TSLA,US:JPM,US:XOM,US:WMT,"
                    "US:XLK,US:XLF,US:XLE,US:XLV,US:XLY,US:XLP,US:XLI,US:XLU,US:XLB,US:XLRE,US:XLC,US:DIA,US:EFA,US:EEM,US:SMH,US:GDX,US:UUP,US:VIXY,US:LQD,US:HYG"),   # + ETF nganh My / khu vuc / chu de (heatmap nganh, market pulse)   # 10 co phieu Mỹ lon (tab "Co phieu My")
}
_DEFAULT_POLL = {"dukascopy": 60, "frankfurter": 3600, "vnstock": 900, "twelvedata": 300, "stooq": 3600, "yahoo": 900,
                 "oanda": 120, "truefx": 30, "alpaca": 900, "tiingo": 21600, "fred": 21600, "yahoo_daily": 86400,
                 "crypto_ccxt": 60}


def _bool(v: str | None, default: bool) -> bool:
    return default if v is None or v == "" else v.strip().lower() in {"1", "true", "yes", "on"}


def _csv(v: str | None, default: str) -> list[str]:
    raw = default if v is None else v
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class CollectorSettings:
    service_name: str = "market-collector"
    redis_url: str = "redis://localhost:6379/0"
    port: int = 8010
    user_agent: str = "trading-system-market-collector/0.1 (contact: set USER_AGENT)"
    providers: list[str] = field(default_factory=lambda: ["dukascopy", "frankfurter", "vnstock", "twelvedata"])
    allow_risky: bool = False
    symbols: dict[str, list[str]] = field(default_factory=dict)
    poll_interval: dict[str, float] = field(default_factory=dict)
    twelvedata_key: str = ""
    twelvedata_tfs: list[str] = field(default_factory=lambda: ["H1", "D1"])
    vnstock_key: str = ""
    oanda_token: str = ""
    oanda_url: str = "https://api-fxpractice.oanda.com"
    oanda_price: str = "B"
    truefx_user: str = ""
    truefx_pass: str = ""
    alpaca_key: str = ""
    alpaca_secret: str = ""
    alpaca_tfs: list[str] = field(default_factory=lambda: ["H1", "D1"])
    alpaca_max_symbols: int = 30       # Alpaca Free: toi da 30 ma
    tiingo_token: str = ""
    tiingo_max_symbols: int = 25       # Tiingo Starter: 500 ma khac nhau/thang, 50 req/gio
    yahoo_daily_at: str = "22:30"      # gio (UTC, HH:MM) poll D1 hang ngay sau khi dong cua My
    crypto_exchanges: list[str] = field(default_factory=lambda: ["okx", "kucoin", "gate", "bitfinex"])  # uu tien -> du phong (ccxt id)
    crypto_quote_interval: float = 15.0   # giay giua 2 lan lay quote (0 = tat luong quote)
    crypto_depth_days: dict[str, int] = field(default_factory=dict)   # ghi de do sau backfill theo tf (CRYPTO_BACKFILL_D1=...)
    # doi chieu nguon (Dukascopy lam chuan)
    reconcile_enabled: bool = True
    reconcile_interval: float = 900.0
    reconcile_threshold_bps: float = 8.0         # lech trung vi OANDA/TrueFX vs Dukascopy (1 bps = 0.01%)
    reconcile_frankfurter_bps: float = 25.0      # Frankfurter (ty gia ECB 14:15 CET) vs Dukascopy cung thoi diem
    reconcile_pairs: list[str] = field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    reconcile_lag_hours: int = 1                 # cho Dukascopy xuat file gio truoc khi doi chieu
    output_tfs: list[str] = field(default_factory=lambda: list(TF_SECONDS))
    backfill_on_start: bool = True
    backfill_days: int = 7
    empty_alert_after: int = 6
    error_alert_after: int = 5  # loi tam thoi lien tiep truoc khi alert
    backfill_retry_base: float = 120.0
    backfill_retry_max: float = 1800.0
    gap_scan_interval: float = 900.0   # chu ky quet khoang trong (s); 0 = tat
    gap_scan_days: int = 7             # cua so quet (ngay)
    gap_fill_per_cycle: int = 3        # so ngay thieu toi da tai lai moi vong
    gap_alert_after: float = 21600.0   # gap ton qua 6h -> 1 alert tong hop
    dukascopy_rate_per_sec: int = 2
    dukascopy_concurrency: int = 2
    cache_dir: Path = Path("./cache")
    state_file: Path = Path("./state.json")
    backfill_token: str = ""

    def symbols_for(self, provider: str) -> list[str]:
        syms = self.symbols.get(provider, [])
        cap = {"alpaca": self.alpaca_max_symbols, "tiingo": self.tiingo_max_symbols}.get(provider)
        return syms[:cap] if cap else syms

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "CollectorSettings":
        e = os.environ if env is None else env
        providers = [p.lower() for p in _csv(e.get("PROVIDERS"), DEFAULT_PROVIDERS)]
        tfs = [t.upper() for t in _csv(e.get("OUTPUT_TFS"), ",".join(TF_SECONDS)) if t.upper() in TF_SECONDS]
        return cls(
            service_name=e.get("SERVICE_NAME", "market-collector"),
            redis_url=e.get("REDIS_URL", "redis://localhost:6379/0"),
            port=int(e.get("PORT", "8010")),
            user_agent=e.get("USER_AGENT", cls.user_agent),
            providers=providers,
            allow_risky=_bool(e.get("ALLOW_RISKY_PROVIDERS"), False),
            symbols={p: parse_symbol_list(e.get(f"{p.upper()}_SYMBOLS", _DEFAULT_SYMBOLS.get(p, ""))) for p in ALL_PROVIDERS},
            poll_interval={p: float(e.get(f"POLL_INTERVAL_{p.upper()}", _DEFAULT_POLL[p])) for p in ALL_PROVIDERS},
            twelvedata_key=e.get("TWELVEDATA_API_KEY", "").strip(),
            twelvedata_tfs=[t.upper() for t in _csv(e.get("TWELVEDATA_TFS"), "H1,D1") if t.upper() in TF_SECONDS],
            vnstock_key=e.get("VNSTOCK_API_KEY", "").strip(),
            oanda_token=e.get("OANDA_PRACTICE_TOKEN", "").strip(),
            oanda_url=e.get("OANDA_API_URL", "https://api-fxpractice.oanda.com").strip(),
            oanda_price=e.get("OANDA_PRICE", "B").strip().upper() or "B",
            truefx_user=e.get("TRUEFX_USER", "").strip(),
            truefx_pass=e.get("TRUEFX_PASS", "").strip(),
            alpaca_key=e.get("ALPACA_KEY", "").strip(),
            alpaca_secret=e.get("ALPACA_SECRET", "").strip(),
            alpaca_tfs=[t.upper() for t in _csv(e.get("ALPACA_TFS"), "H1,D1") if t.upper() in TF_SECONDS],
            alpaca_max_symbols=max(1, int(e.get("ALPACA_MAX_SYMBOLS", "30"))),
            tiingo_token=e.get("TIINGO_TOKEN", "").strip(),
            tiingo_max_symbols=max(1, int(e.get("TIINGO_MAX_SYMBOLS", "25"))),
            yahoo_daily_at=e.get("YAHOO_DAILY_AT_UTC", "22:30").strip() or "22:30",
            crypto_exchanges=[x.lower() for x in _csv(e.get("CRYPTO_EXCHANGES"), "okx,kucoin,gate,bitfinex")],
            crypto_quote_interval=max(0.0, float(e.get("CRYPTO_QUOTE_INTERVAL", "15"))),
            crypto_depth_days={tf: int(e[f"CRYPTO_BACKFILL_{tf}"]) for tf in TF_SECONDS if e.get(f"CRYPTO_BACKFILL_{tf}")},
            reconcile_enabled=_bool(e.get("RECONCILE_ENABLED"), True),
            reconcile_interval=float(e.get("RECONCILE_INTERVAL", "900")),
            reconcile_threshold_bps=float(e.get("RECONCILE_THRESHOLD_BPS", "8")),
            reconcile_frankfurter_bps=float(e.get("RECONCILE_FRANKFURTER_BPS", "25")),
            reconcile_pairs=parse_symbol_list(e.get("RECONCILE_PAIRS", "EURUSD,GBPUSD,USDJPY,XAUUSD")),
            reconcile_lag_hours=max(0, int(e.get("RECONCILE_LAG_HOURS", "1"))),
            output_tfs=tfs or list(TF_SECONDS),
            backfill_on_start=_bool(e.get("BACKFILL_ON_START"), True),
            backfill_days=int(e.get("BACKFILL_DAYS", "7")),
            empty_alert_after=int(e.get("EMPTY_ALERT_AFTER", "6")),
            error_alert_after=int(e.get("ERROR_ALERT_AFTER", "5")),
            backfill_retry_base=float(e.get("BACKFILL_RETRY_BASE", "120")),
            backfill_retry_max=float(e.get("BACKFILL_RETRY_MAX", "1800")),
            gap_scan_interval=float(e.get("GAP_SCAN_INTERVAL", "900")),
            gap_scan_days=int(e.get("GAP_SCAN_DAYS", e.get("BACKFILL_DAYS", "7"))),
            gap_fill_per_cycle=max(1, int(e.get("GAP_FILL_PER_CYCLE", "3"))),
            gap_alert_after=float(e.get("GAP_ALERT_AFTER", "21600")),
            dukascopy_rate_per_sec=max(1, int(e.get("DUKASCOPY_RATE_PER_SEC", "2"))),
            dukascopy_concurrency=max(1, int(e.get("DUKASCOPY_CONCURRENCY", "2"))),
            cache_dir=Path(e.get("CACHE_DIR", "./cache")),
            state_file=Path(e.get("STATE_FILE", "./state.json")),
            backfill_token=e.get("BACKFILL_TOKEN", "").strip(),
        )
