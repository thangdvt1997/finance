"""Thu thập dữ liệu công khai -> research/data/*.parquet. Chạy: python fetch_data.py"""
import io, sys, time, pathlib, requests, pandas as pd
import pq
D = pathlib.Path(__file__).parent / "data"; D.mkdir(exist_ok=True)
YF = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","AUDUSD":"AUDUSD=X","USDCAD":"USDCAD=X",
      "USDCHF":"USDCHF=X","NZDUSD":"NZDUSD=X","XAUUSD":"GC=F","XAGUSD":"SI=F","WTI":"CL=F","SPY":"SPY"}
def yf_all():
    import yfinance as yf
    out = {}
    for k, t in YF.items():
        df = yf.download(t, start="1999-01-01", auto_adjust=True, progress=False, multi_level_index=False)
        s = df["Close"].dropna(); s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        out[k] = s; print(k, t, len(s), s.index.min().date(), s.index.max().date())
    pq.save(pd.DataFrame(out), D/"yahoo_close.parquet")
def frankfurter():
    # ECB reference (14:15 CET), từ 1999; chia khoảng 5 năm
    rows = {}
    for y in range(1999, 2027, 4):
        r = requests.get(f"https://api.frankfurter.app/{y}-01-01..{min(y+3,2026)}-12-31",
                         params={"from":"USD","to":"EUR,GBP,JPY,AUD,CAD,CHF,NZD"}, timeout=60)
        r.raise_for_status()
        for d, v in r.json()["rates"].items(): rows[d] = v
    df = pd.DataFrame(rows).T; df.index = pd.to_datetime(df.index); df = df.sort_index()
    out = pd.DataFrame({"EURUSD":1/df.EUR,"GBPUSD":1/df.GBP,"USDJPY":df.JPY,"AUDUSD":1/df.AUD,
                        "USDCAD":df.CAD,"USDCHF":df.CHF,"NZDUSD":1/df.NZD})
    pq.save(out, D/"ecb_close.parquet"); print("ECB", out.shape, out.index.min().date(), out.index.max().date())
FRED = {"USD":"IR3TIB01USM156N","EUR":"IR3TIB01EZM156N","GBP":"IR3TIB01GBM156N","JPY":"IR3TIB01JPM156N",
        "AUD":"IR3TIB01AUM156N","CAD":"IR3TIB01CAM156N","CHF":"IR3TIB01CHM156N","NZD":"IR3TIB01NZM156N"}
def fred():
    out = {}
    for c, sid in FRED.items():
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=60); r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True); out[c] = pd.to_numeric(df.iloc[:,0], errors="coerce")
        print(c, sid, out[c].dropna().index.min().date(), out[c].dropna().index.max().date())
    pq.save(pd.DataFrame(out), D/"rates_3m.parquet")
if __name__ == "__main__":
    for f in (frankfurter, fred, yf_all):
        try: f()
        except Exception as e: print("FAIL", f.__name__, repr(e)[:300])
