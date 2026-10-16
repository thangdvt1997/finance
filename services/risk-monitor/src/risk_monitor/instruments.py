"""Phân loại công cụ + kích thước hợp đồng + tỷ giá quy đổi sang tiền tệ tài khoản. Thuần tính toán, không I/O."""
from __future__ import annotations

import re
from dataclasses import dataclass

FX_CCY = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "SGD", "HKD", "CNH", "CNY",
          "MXN", "ZAR", "TRY", "PLN", "CZK", "HUF", "THB", "ILS"}
METALS = {"XAU": "gold", "XAG": "silver"}
CRYPTO = {"BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "DOGE"}
INDEX_NAMES = {"US30", "US500", "SPX500", "NAS100", "USTEC", "US100", "GER40", "DE40", "DAX40", "UK100", "JP225", "FRA40",
               "EU50", "HK50", "AUS200"}
INDEX_QUOTE = {"GER40": "EUR", "DE40": "EUR", "DAX40": "EUR", "FRA40": "EUR", "EU50": "EUR", "UK100": "GBP", "JP225": "JPY",
               "HK50": "HKD", "AUS200": "AUD"}
BOND_ETF = {"AGG", "IEF", "IEI", "SHY", "TLT", "BND", "LQD", "HYG", "TIP"}
GOLD_ETF = {"GLD", "IAU"}
COMMODITY_ETF = {"USO", "BNO", "UNG", "CPER", "CORN", "CANE", "SOYB", "WEAT", "DBC", "SLV", "DBA"}

CLASSES = ("fx", "equity", "bond", "gold", "commodity", "crypto", "index", "other")


@dataclass(frozen=True)
class Spec:
    symbol: str
    kind: str          # fx | metal | crypto | index | equity | bond | commodity | other
    cls: str           # nhóm cho stress/tập trung: fx|equity|bond|gold|commodity|crypto|index|other
    base: str | None
    quote: str
    contract: float    # đơn vị / 1 lot (MT); paper dùng qty trực tiếp nên không dùng


def _core(symbol: str) -> str:
    """Bỏ hậu tố broker thường gặp (.m, .pro, _i, #) để nhận dạng."""
    return re.split(r"[.#_]", symbol.upper(), maxsplit=1)[0]


def classify(symbol: str, cfg: dict | None = None, default_quote: str = "USD") -> Spec:
    cfg = cfg or {}
    ov = (cfg.get("instruments") or {}).get(symbol) or {}
    contracts = cfg.get("contracts") or {}
    s = symbol
    core = _core(symbol)
    if ":" in symbol:  # US:SPY, VN:VNM
        mkt, tick = symbol.split(":", 1)
        tick = tick.upper()
        quote = "VND" if mkt.upper() == "VN" else default_quote
        if tick in BOND_ETF:
            spec = Spec(s, "bond", "bond", None, quote, 1.0)
        elif tick in GOLD_ETF:
            spec = Spec(s, "equity", "gold", None, quote, 1.0)
        elif tick in COMMODITY_ETF:
            spec = Spec(s, "commodity", "commodity", None, quote, 1.0)
        else:
            spec = Spec(s, "equity", "equity", None, quote, 1.0)
    elif len(core) == 6 and core[:3] in FX_CCY and core[3:] in FX_CCY:
        spec = Spec(s, "fx", "fx", core[:3], core[3:], float(contracts.get(s, contracts.get("fx", 100000))))
    elif len(core) == 6 and core[:3] in METALS and core[3:] in FX_CCY:
        gold = METALS[core[:3]] == "gold"
        spec = Spec(s, "metal", "gold" if gold else "commodity", core[:3], core[3:],
                    float(contracts.get(s, contracts.get(core, 100 if gold else 5000))))
    elif core[:3] in CRYPTO and (core[3:] in FX_CCY or core[3:] == "USDT"):
        spec = Spec(s, "crypto", "crypto", core[:3], "USD" if core[3:] == "USDT" else core[3:],
                    float(contracts.get(s, contracts.get("crypto", 1))))
    elif core in INDEX_NAMES:
        spec = Spec(s, "index", "index", None, INDEX_QUOTE.get(core, "USD"), float(contracts.get(s, contracts.get("index", 1))))
    else:
        spec = Spec(s, "other", "other", None, default_quote, 1.0)
    if ov:
        spec = Spec(s, ov.get("kind", spec.kind), ov.get("cls", ov.get("class", spec.cls)), ov.get("base", spec.base),
                    ov.get("quote", spec.quote), float(ov.get("contract", spec.contract)))
    return spec


def fx_rate(frm: str, to: str, prices: dict[str, float], _depth: int = 0) -> float | None:
    """Giá trị 1 đơn vị `frm` tính bằng `to`. Dùng cặp trực tiếp/đảo ngược trong `prices`, hoặc bắc cầu qua USD. None nếu không có."""
    if frm == to:
        return 1.0
    if (p := prices.get(frm + to)) and p > 0:
        return p
    if (p := prices.get(to + frm)) and p > 0:
        return 1.0 / p
    if _depth == 0 and "USD" not in (frm, to):
        a = fx_rate(frm, "USD", prices, 1)
        b = fx_rate("USD", to, prices, 1)
        if a is not None and b is not None:
            return a * b
    return None
