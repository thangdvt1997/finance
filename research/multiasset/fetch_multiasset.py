"""Thu thap du lieu da tai san dai han (>=15-20 nam) tu nguon cong khai, chay TREN VPS trong container research-*.
Dau ra: $DATA/raw_yahoo.parquet (close, adjclose), fred.parquet, ecb.parquet, rates3m.parquet, vnindex.parquet (neu co).
Nguon: Yahoo chart API (can User-Agent, ~1 req/s), FRED fredgraph.csv (khong can key), Frankfurter/ECB, vnstock (tuy chon).
Khong dung: Stooq (JS challenge tu VPS), Dukascopy (429), Binance API (451; chi data.binance.vision)."""
import os, io, sys, time, json, pathlib, requests, pandas as pd, numpy as np
DATA = pathlib.Path(os.environ.get("RDATA", "/root/research/data")); DATA.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-fetch"}
YAHOO = ["^GSPC","^IXIC","^RUT","^GDAXI","^STOXX50E","^FTSE","^N225","^HSI","^AXJO","^FCHI","^KS11","^BSESN","^BVSP",
         "VNM","EEM","EFA","SPY","TLT","IEF","SHY","AGG","GLD","SLV","CPER","DBB","USO","BNO","UNG","DBA","CORN","WEAT","SOYB","CANE","DBC",
         "GC=F","SI=F","HG=F","BTC-USD","ETH-USD","^VNINDEX"]
FRED = ["DGS2","DGS5","DGS10","DGS20","DGS30","DTB3","DCOILWTICO","DCOILBRENTEU"]
FRED_RATES = {"USD":"IR3TIB01USM156N","EUR":"IR3TIB01EZM156N","GBP":"IR3TIB01GBM156N","JPY":"IR3TIB01JPM156N",
              "AUD":"IR3TIB01AUM156N","CAD":"IR3TIB01CAM156N","CHF":"IR3TIB01CHM156N","NZD":"IR3TIB01NZM156N"}

def yahoo(t, tries=6):
    for k in range(tries):
        r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(t)}",
                         params={"period1": 0, "period2": int(time.time()) + 86400, "interval": "1d", "events": "div,splits"}, headers=UA, timeout=60)
        if r.status_code == 429: time.sleep(5 * (k + 1)); continue
        if r.status_code != 200: return None
        j = r.json()["chart"]["result"]
        if not j: return None
        j = j[0]; ts = pd.to_datetime(j["timestamp"], unit="s")
        q = j["indicators"]["quote"][0]; ac = j["indicators"].get("adjclose", [{}])[0].get("adjclose")
        df = pd.DataFrame({"close": q["close"], "adjclose": ac if ac else q["close"]}, index=ts.normalize()).dropna()
        return df[~df.index.duplicated(keep="last")]
    return None

def main():
    rows = {}; log = []
    for t in YAHOO:
        df = yahoo(t); time.sleep(1.2)
        if df is None or df.empty: log.append((t, "NO DATA")); print(t, "NO DATA", flush=True); continue
        rows[t] = df; log.append((t, len(df), str(df.index.min().date()), str(df.index.max().date())))
        print(t, len(df), df.index.min().date(), df.index.max().date(), flush=True)
    raw = pd.concat(rows, axis=1, sort=True); raw.to_parquet(DATA / "raw_yahoo.parquet")
    out = {}
    for s in FRED:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}", timeout=60, headers=UA); r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True); out[s] = pd.to_numeric(d.iloc[:, 0], errors="coerce")
        print(s, out[s].dropna().index.min().date(), out[s].dropna().index.max().date(), flush=True)
    pd.DataFrame(out).to_parquet(DATA / "fred.parquet")
    out = {}
    for c, s in FRED_RATES.items():
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}", timeout=60, headers=UA); r.raise_for_status()
        d = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True); out[c] = pd.to_numeric(d.iloc[:, 0], errors="coerce")
    pd.DataFrame(out).to_parquet(DATA / "rates3m.parquet")
    # ECB qua Frankfurter (v1), chia khoang 3 nam
    rows = {}
    for y in range(1999, 2027, 3):
        r = requests.get(f"https://api.frankfurter.dev/v1/{y}-01-01..{min(y+2,2026)}-12-31", params={"base": "USD", "symbols": "EUR,GBP,JPY,AUD,CAD,CHF,NZD"}, timeout=60)
        r.raise_for_status()
        for d, v in r.json()["rates"].items(): rows[d] = v
    df = pd.DataFrame(rows).T; df.index = pd.to_datetime(df.index); df = df.sort_index()
    pd.DataFrame({"EURUSD": 1/df.EUR, "GBPUSD": 1/df.GBP, "USDJPY": df.JPY, "AUDUSD": 1/df.AUD, "USDCAD": df.CAD, "USDCHF": df.CHF, "NZDUSD": 1/df.NZD}).to_parquet(DATA / "ecb.parquet")
    print("ECB", df.index.min().date(), df.index.max().date())
    # VN-Index qua vnstock (tuy chon; neu loi thi dung ETF VNM)
    try:
        from vnstock import Vnstock
        d = Vnstock().stock(symbol="VNINDEX", source="VCI").quote.history(start="2000-01-01", end=str(pd.Timestamp.today().date()), interval="1D")
        d["time"] = pd.to_datetime(d["time"]); d.set_index("time")[["close"]].to_parquet(DATA / "vnindex.parquet"); print("vnindex", len(d), d.time.min(), d.time.max())
    except Exception as e:
        print("vnstock FAIL", repr(e)[:200])
    json.dump(log, open(DATA / "fetch_log.json", "w"))

if __name__ == "__main__": main()
