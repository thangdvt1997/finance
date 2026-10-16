from __future__ import annotations

import re

_PREFIXES = ("VN:", "US:", "CRYPTO:")


def normalize_symbol(raw: str) -> str:
    """'eur/usd' -> EURUSD ; 'EURUSD=X' -> EURUSD ; 'vn:vnm' -> VN:VNM ; 'xau-usd' -> XAUUSD."""
    s = raw.strip().upper()
    prefix = ""
    for p in _PREFIXES:
        if s.startswith(p):
            prefix, s = p, s[len(p):]
            break
    s = re.sub(r"=X$", "", s)
    s = re.sub(r"[\s/_\-]", "", s)
    return prefix + s


def parse_symbol_list(csv: str | None) -> list[str]:
    out: list[str] = []
    for part in (csv or "").split(","):
        if part.strip():
            n = normalize_symbol(part)
            if n and n not in out:
                out.append(n)
    return out


def is_fx_pair(symbol: str) -> bool:
    """6 chu cai, khong tien to (EURUSD, XAUUSD...)."""
    return bool(re.fullmatch(r"[A-Z]{6}", symbol))   # CRYPTO:BTCUSDT co tien to nen KHONG khop


def split_pair(symbol: str) -> tuple[str, str]:
    if not is_fx_pair(symbol):
        raise ValueError(f"khong phai cap tien: {symbol}")
    return symbol[:3], symbol[3:]


def strip_prefix(symbol: str) -> str:
    for p in _PREFIXES:
        if symbol.startswith(p):
            return symbol[len(p):]
    return symbol
