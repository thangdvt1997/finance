"""Hang so + phan loai tai san. Moi tham so thong ke o day duoc ghi vao /track/methodology."""
from __future__ import annotations

from datetime import datetime, timezone

METHOD_VERSION = "tr-1.0"
DISCLAIMER = "Chỉ tham khảo, quá khứ không đảm bảo tương lai. Đa số ý kiến công khai không vượt được ngẫu nhiên."
UTC = timezone.utc

HORIZONS = {"1D": 1, "1W": 5, "1M": 21}          # so nen D1 tinh tu nen vao (nen thu k = nen vao + k-1)
MIN_N = 30                                         # so quan diem DOC LAP toi thieu de duoc xep hang
FDR_Q = 0.10
SENT_THRESHOLD = 0.35
MAX_SYMBOLS_PER_ARTICLE = 3
N_PERM = 2000
N_BOOT = 1000
N_BAND = 400                                       # so hoan vi dung cho dai ngau nhien duong equity
MAX_PERM_N = 5000                                  # chan tren n (lay moi nhat) de gioi han chi phi
SEED = 20261012
MAX_ENTRY_GAP_DAYS = 6                             # nen vao cach observed_at > 6 ngay => thieu du lieu gia, khong cham

# Tien nghiem Beta theo loai: (k = do manh tien nghiem tinh bang "so quan diem ao", tilt cua trung binh so voi 0.5; |tilt| <= 0.02)
PRIORS = {
    "analyst": (20.0, 0.0),
    "central_bank": (20.0, 0.0),
    "media": (30.0, -0.01),            # tin tuc tho: nhieu cao, alpha thap (docs/research/INFO_SIGNALS_STUDY.md)
    "positioning": (30.0, 0.0),        # COT: khong co tin hieu kiem chung duoc (muc 4.1 cua nghien cuu)
    "signal_provider": (25.0, -0.01),  # thien lech song sot
    "other": (30.0, 0.0),
}
KINDS = tuple(PRIORS)
ASSET_CLASSES = ("forex", "metal", "index", "commodity", "crypto", "stock_us", "stock_vn", "etf", "bond")
REGIMES = ("trend", "range", "high_vol", "low_vol")

_CCY = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNH", "CNY", "VND", "SGD", "HKD", "SEK", "NOK", "MXN", "ZAR", "TRY"}
_METALS = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}
_COMMODITY = {"USOIL", "UKOIL", "NGAS", "US:USO", "US:BNO", "US:UNG", "US:CANE", "US:CORN", "US:CPER", "US:SOYB", "US:WEAT"}
_METAL_ETF = {"US:GLD", "US:SLV", "US:GDX"}
_BOND = {"US:TLT", "US:SHY", "US:IEF", "US:IEI", "US:AGG", "US:LQD", "US:HYG"}
_INDEX = {"US:SPX", "US:NDX", "US:DJI", "DXY"}
_ETF = {"US:SPY", "US:QQQ", "US:IWM", "US:DIA", "US:EEM", "US:EFA", "US:EWA", "US:EWG", "US:EWH", "US:EWJ", "US:EWQ", "US:EWU", "US:EWY", "US:EWZ",
        "US:FEZ", "US:INDA", "US:VNM", "US:SMH", "US:UUP", "US:VIXY"} | {f"US:XL{c}" for c in "BCEFIKPUVY"} | {"US:XLRE"}
_VN_INDEX_CODES = {"VNINDEX", "VN30", "VN100", "VNALL", "VNMID", "VNSML", "HNX", "HNX30", "UPCOM", "VNX50", "VN50"}


def asset_class(sym: str) -> str:
    s = sym.upper()
    if s.startswith("CRYPTO:") or s in {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"}:
        return "crypto"
    if s in _METALS or s in _METAL_ETF:
        return "metal" if s in _METALS else "metal"
    if s in _COMMODITY:
        return "commodity"
    if s in _BOND or s.startswith("FRED:"):
        return "bond"
    if s in _INDEX:
        return "index"
    if s.startswith("VN:"):
        return "index" if s[3:] in _VN_INDEX_CODES else "stock_vn"
    if s in _ETF:
        return "etf"
    if s.startswith("US:"):
        return "stock_us"
    if len(s) == 6 and s[:3] in _CCY and s[3:] in _CCY:
        return "forex"
    return "forex" if len(s) == 6 and s.isalpha() else "etf"


def utcnow() -> datetime:
    return datetime.now(UTC)
