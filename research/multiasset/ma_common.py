"""Danh muc tai san + gia dinh chi phi cho nghien cuu da tai san. Moi tai san -> chuoi loi suat 'excess' (vuot tien mat USD), tuong duong hop dong tuong lai/ETF co don bay."""
import os, pathlib
DATA = pathlib.Path(os.environ.get("RDATA", "/root/research/data"))
OUT = pathlib.Path(os.environ.get("ROUT", "/root/research/results"))
FIG = pathlib.Path(os.environ.get("RFIG", "/root/research/figures"))
# name: (class, one-way cost bps [nua spread + hoa hong + truot gia, bao thu], q = ty suat co tuc gia dinh cho chi so gia (price index) %/nam, nguon)
ASSETS = {
    # equities (index futures / ETF). q: chi so gia -> cong co tuc; ^GDAXI la performance index (da gom co tuc) -> q=0
    "SPX": ("eq", 2.5, 2.0, "^GSPC"), "NDX": ("eq", 3.0, 0.9, "^IXIC"), "RUT": ("eq", 4.0, 1.3, "^RUT"),
    "DAX": ("eq", 3.0, 0.0, "^GDAXI"), "SX5E": ("eq", 3.0, 3.3, "^STOXX50E"), "CAC": ("eq", 3.0, 3.0, "^FCHI"),
    "FTSE": ("eq", 3.0, 3.8, "^FTSE"), "N225": ("eq", 4.0, 1.8, "^N225"), "HSI": ("eq", 6.0, 3.2, "^HSI"),
    "ASX": ("eq", 4.0, 4.0, "^AXJO"), "KOSPI": ("eq", 6.0, 1.5, "^KS11"), "SENSEX": ("eq", 8.0, 1.3, "^BSESN"),
    "BVSP": ("eq", 8.0, 4.0, "^BVSP"), "VNM": ("eq", 12.0, None, "VNM"),   # VNM: ETF US-listed (proxy VN-Index), adj close
    # bonds: proxy tu lai suat constant-maturity FRED (dinh gia lai trai phieu par), maturity nam
    "UST2": ("bond", 1.0, 2, "DGS2"), "UST5": ("bond", 1.5, 5, "DGS5"), "UST10": ("bond", 2.0, 10, "DGS10"), "UST30": ("bond", 3.0, 30, "DGS30"),
    # FX majors (ECB), carry tu lai suat lien ngan hang 3M
    "EURUSD": ("fx", 1.0, None, None), "GBPUSD": ("fx", 1.5, None, None), "USDJPY": ("fx", 1.2, None, None), "AUDUSD": ("fx", 1.5, None, None),
    "USDCAD": ("fx", 1.8, None, None), "USDCHF": ("fx", 1.8, None, None), "NZDUSD": ("fx", 2.0, None, None),
    # commodities
    "GOLD": ("metal", 3.0, None, "GC=F>GLD"), "SILVER": ("metal", 8.0, None, "SI=F>SLV"), "COPPER": ("metal", 6.0, None, "HG=F"),
    "WTI": ("energy", 6.0, None, "FRED:DCOILWTICO>USO"), "BRENT": ("energy", 8.0, None, "FRED:DCOILBRENTEU>BNO"), "NATGAS": ("energy", 15.0, None, "UNG"),
    "CORN": ("agri", 10.0, None, "CORN"), "WHEAT": ("agri", 10.0, None, "WEAT"), "SOY": ("agri", 10.0, None, "SOYB"), "SUGAR": ("agri", 12.0, None, "CANE"),
    # tuy chon (khong thuoc loi)
    "BTC": ("crypto", 15.0, None, "BTC-USD"), "ETH": ("crypto", 20.0, None, "ETH-USD"),
}
CORE = [k for k, v in ASSETS.items() if v[0] != "crypto"]
CLASSES = ["eq", "bond", "fx", "metal", "energy", "agri"]
