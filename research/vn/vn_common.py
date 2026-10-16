"""Hang so + tai du lieu cho backtest co phieu VN. Moi thu doc/ghi tu $RDATA (mac dinh /root/research/vn/data), ket qua ra $ROUT, hinh ra $RFIG."""
import gzip, json, os, pathlib, sys
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # research/engine.py (metrics, bootstrap, DSR) -- khi chay tren VPS engine.py nam cung thu muc
DATA = pathlib.Path(os.environ.get("RDATA", "/root/research/vn/data"))
OUT = pathlib.Path(os.environ.get("ROUT", "/root/research/vn/results")); OUT.mkdir(parents=True, exist_ok=True)
FIG = pathlib.Path(os.environ.get("RFIG", "/root/research/vn/figures")); FIG.mkdir(parents=True, exist_ok=True)
ANN = 252
RF = 0.045            # lai suat tien gui/tien mat gia dinh hang so (4,5%/nam): gia dinh KHONG kiem chung duoc, kiem tra do nhay rf=0 va 7%
COMMISSION = 0.0015   # 0,15%/chieu (phi CTCK tham chieu, khop vn_market.rules.BROKER_FEE_REF)
SELL_TAX = 0.001      # thue ban 0,1%
LOT = 100
PRICE_MULT = 1000.0   # nguon tra nghin dong


def tick_size(price, etf=False):
    """Buoc gia HOSE (VND): <10.000: 10; 10.000-<50.000: 50; >=50.000: 100 (ETF 10). Vector hoa theo price."""
    p = np.asarray(price, dtype=float)
    t = np.where(p < 10_000, 10.0, np.where(p < 50_000, 50.0, 100.0))
    return np.where(etf, 10.0, t)


def load_raw(path=None):
    """Doc raw/*.json.gz -> DataFrame dai da chuan hoa (gia VND)."""
    raw = (path or DATA) / "raw"; frames = []
    for f in sorted(raw.glob("*.json.gz")):
        with gzip.open(f, "rt") as fh: rows = json.load(fh)
        if rows: frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    for c in ["basicPrice", "ceilingPrice", "floorPrice", "open", "high", "low", "close", "average", "adOpen", "adHigh", "adLow", "adClose", "adAverage"]:
        df[c] = pd.to_numeric(df[c], errors="coerce") * PRICE_MULT
    for c in ["nmVolume", "nmValue", "ptVolume", "ptValue", "pctChange"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close", "adClose"]); df = df[(df.close > 0) & (df.adClose > 0)]
    df = df.sort_values(["code", "date"]).drop_duplicates(["code", "date"], keep="last")
    return df


def sharpe(r, rf=RF):
    r = pd.Series(r).dropna()
    if len(r) < 30 or r.std() == 0: return np.nan
    return float((r.mean() - rf / ANN) / r.std() * np.sqrt(ANN))
