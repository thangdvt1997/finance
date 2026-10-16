from __future__ import annotations

import logging

import httpx

from ..config import RISKY_PROVIDERS, CollectorSettings
from .alpaca import AlpacaProvider
from .base import HttpProvider, Provider
from .crypto_ccxt import CryptoCcxtProvider
from .dukascopy import DukascopyProvider
from .frankfurter import FrankfurterProvider
from .fred import FredProvider
from .oanda import OandaProvider
from .stooq import StooqProvider
from .tiingo import TiingoProvider
from .truefx import TrueFXProvider
from .twelvedata import TwelveDataProvider
from .vnstock_provider import VnstockProvider
from .yahoo import YahooProvider
from .yahoo_daily import YahooDailyProvider

log = logging.getLogger("market_collector.registry")

__all__ = ["Provider", "HttpProvider", "build_providers", "make_http_client", "provider_status", "PROVIDER_INFO"]

# Thong tin hien thi cho moi nguon: bien env can co, noi dang ky, gioi han goi free. (Khong chua gia tri bi mat.)
PROVIDER_INFO: dict[str, dict] = {
    "dukascopy": {"env": [], "signup": None, "limit": "2 req/s, cache dia", "kind": "fx"},
    "frankfurter": {"env": [], "signup": None, "limit": "30 req/phut (ECB, D1)", "kind": "fx"},
    "vnstock": {"env": [], "signup": None, "limit": "20 req/phut", "kind": "vn"},
    "twelvedata": {"env": ["TWELVEDATA_API_KEY"], "signup": "https://twelvedata.com/register", "limit": "8 req/phut, 800/ngay", "kind": "multi"},
    "oanda": {"env": ["OANDA_PRACTICE_TOKEN"], "signup": "https://www.oanda.com/forex-trading/ (tai khoan practice -> My Hub -> Manage API Access)",
              "limit": "60 req/phut (tu gioi han), nen M1", "kind": "fx"},
    "truefx": {"env": ["TRUEFX_USER", "TRUEFX_PASS"], "signup": "https://www.truefx.com/ (Register, mien phi)",
               "limit": "1 req/30s cho ca nhom cap", "kind": "fx"},
    "alpaca": {"env": ["ALPACA_KEY", "ALPACA_SECRET"], "signup": "https://app.alpaca.markets/signup (Paper/Free)",
               "limit": "200 req/phut, feed IEX, toi da 30 ma", "kind": "us"},
    "tiingo": {"env": ["TIINGO_TOKEN"], "signup": "https://www.tiingo.com/account/api/token (dang ky Starter mien phi)",
               "limit": "50 req/gio, 1000/ngay, 500 ma/thang", "kind": "us"},
    "fred": {"env": [], "signup": None, "limit": "20 req/phut (fredgraph.csv, khong can key)", "kind": "macro"},
    "crypto_ccxt": {"env": [], "signup": None, "limit": "REST cong khai qua ccxt (okx>kucoin>gate>bitfinex), tu gioi han theo san; khong can key; Binance 451/Bybit 403 tu VPS", "kind": "crypto"},
    "stooq": {"env": [], "signup": None, "limit": "10 req/phut (rui ro ToS, mac dinh TAT)", "kind": "risky"},
    "yahoo": {"env": [], "signup": None, "limit": "10 req/phut (rui ro ToS, mac dinh TAT)", "kind": "risky"},
    "yahoo_daily": {"env": [], "signup": None, "limit": "10 req/phut, 1 poll/ngay sau dong cua My (rui ro ToS, chi ca nhan, mac dinh TAT)", "kind": "risky"},
}


def make_http_client(settings: CollectorSettings) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": settings.user_agent}, timeout=httpx.Timeout(30.0), follow_redirects=True)


def _missing_env(settings: CollectorSettings, name: str) -> list[str]:
    """Danh sach bien env con thieu de bat provider `name` (rong = du dieu kien)."""
    s = settings
    need = {
        "twelvedata": {"TWELVEDATA_API_KEY": s.twelvedata_key},
        "oanda": {"OANDA_PRACTICE_TOKEN": s.oanda_token},
        "truefx": {"TRUEFX_USER": s.truefx_user, "TRUEFX_PASS": s.truefx_pass},
        "alpaca": {"ALPACA_KEY": s.alpaca_key, "ALPACA_SECRET": s.alpaca_secret},
        "tiingo": {"TIINGO_TOKEN": s.tiingo_token},
    }.get(name, {})
    return [k for k, v in need.items() if not v]


def provider_status(settings: CollectorSettings, active: list[Provider] | None = None) -> list[dict]:
    """Trang thai moi nguon: active | needs_key | disabled | risky_off | unavailable (+ bien env con thieu, symbols)."""
    act = {p.name for p in (active or [])}
    out = []
    for name, info in PROVIDER_INFO.items():
        missing = _missing_env(settings, name)
        if name in act:
            state = "active"
        elif name not in settings.providers:
            state = "disabled"
        elif name in RISKY_PROVIDERS and not settings.allow_risky:
            state = "risky_off"
        elif missing:
            state = "needs_key"
        elif name == "vnstock":
            state = "unavailable"
        else:
            state = "disabled"
        out.append({"provider": name, "state": state, "needs_env": missing if state == "needs_key" else [],
                    "env": info["env"], "signup": info["signup"], "limit": info["limit"], "kind": info["kind"],
                    "symbols": settings.symbols_for(name) if state == "active" else []})
    return out


def build_providers(settings: CollectorSettings, client: httpx.AsyncClient) -> list[Provider]:
    """Registry: tao provider theo PROVIDERS (env). Provider thieu dieu kien (key/thu vien/ToS) bi bo qua + log 1 dong."""
    out: list[Provider] = []
    pi = settings.poll_interval
    for name in settings.providers:
        if name in RISKY_PROVIDERS and not settings.allow_risky:
            log.warning("provider %s co rui ro ToS -> bo qua (can ALLOW_RISKY_PROVIDERS=true)", name)
            continue
        if name == "dukascopy":
            out.append(DukascopyProvider(client, settings.cache_dir, poll_interval=pi["dukascopy"],
                                          rate_per_sec=settings.dukascopy_rate_per_sec,
                                          concurrency=settings.dukascopy_concurrency))
        elif name == "frankfurter":
            out.append(FrankfurterProvider(client, poll_interval=pi["frankfurter"]))
        elif name == "twelvedata":
            if not settings.twelvedata_key:
                log.warning("twelvedata: thieu TWELVEDATA_API_KEY -> tat")
                continue
            out.append(TwelveDataProvider(client, settings.twelvedata_key, tfs=settings.twelvedata_tfs,
                                          poll_interval=pi["twelvedata"]))
        elif name == "oanda":
            if not settings.oanda_token:
                log.info("oanda: can OANDA_PRACTICE_TOKEN (mien phi) -> dang tat")
                continue
            out.append(OandaProvider(client, settings.oanda_token, base_url=settings.oanda_url, price=settings.oanda_price,
                                     poll_interval=pi["oanda"]))
        elif name == "truefx":
            if not (settings.truefx_user and settings.truefx_pass):
                log.info("truefx: can TRUEFX_USER + TRUEFX_PASS (dang ky mien phi) -> dang tat")
                continue
            out.append(TrueFXProvider(client, settings.truefx_user, settings.truefx_pass, settings.symbols_for("truefx"),
                                      poll_interval=pi["truefx"]))
        elif name == "alpaca":
            if not (settings.alpaca_key and settings.alpaca_secret):
                log.info("alpaca: can ALPACA_KEY + ALPACA_SECRET (goi Free) -> dang tat")
                continue
            out.append(AlpacaProvider(client, settings.alpaca_key, settings.alpaca_secret, tfs=settings.alpaca_tfs,
                                      poll_interval=pi["alpaca"]))
        elif name == "tiingo":
            if not settings.tiingo_token:
                log.info("tiingo: can TIINGO_TOKEN (Starter mien phi) -> dang tat")
                continue
            out.append(TiingoProvider(client, settings.tiingo_token, poll_interval=pi["tiingo"]))
        elif name == "fred":
            out.append(FredProvider(client, poll_interval=pi["fred"]))
        elif name == "vnstock":
            if not VnstockProvider.available():
                log.warning("vnstock: chua cai thu vien -> tat (cach cai: xem README muc \"Bat vnstock\")")
                continue
            out.append(VnstockProvider(api_key=settings.vnstock_key, poll_interval=pi["vnstock"]))
        elif name == "stooq":
            out.append(StooqProvider(client, poll_interval=pi["stooq"]))
        elif name == "yahoo":
            out.append(YahooProvider(poll_interval=pi["yahoo"]))
        elif name == "yahoo_daily":
            out.append(YahooDailyProvider(client, at_utc=settings.yahoo_daily_at))
        elif name == "crypto_ccxt":
            try:
                import ccxt.async_support  # noqa: F401
            except ImportError:
                log.warning("crypto_ccxt: chua cai thu vien ccxt -> tat")
                continue
            out.append(CryptoCcxtProvider(settings.crypto_exchanges, settings.symbols_for("crypto_ccxt"),
                                          quote_interval=settings.crypto_quote_interval, depth=settings.crypto_depth_days,
                                          poll_interval=pi["crypto_ccxt"]))
        else:
            log.warning("provider khong biet: %s", name)
    return out
