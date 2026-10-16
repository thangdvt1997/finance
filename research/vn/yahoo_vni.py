import json, urllib.request, pandas as pd
for sym in ["%5EVNINDEX.VN", "E1VFVN30.VN"]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=946684800&period2=1791000000&interval=1d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        j = json.loads(urllib.request.urlopen(req, timeout=30).read())
        r = j["chart"]["result"][0]; t = pd.to_datetime(r["timestamp"], unit="s"); c = r["indicators"]["quote"][0]["close"]
        s = pd.Series(c, index=t).dropna(); print(sym, len(s), s.index[0], s.index[-1], s.iloc[:2].tolist(), s.iloc[-1])
        s.to_frame("close").to_parquet(f"/root/research/vn/data/yahoo_{sym.replace('%5E','')}.parquet")
    except Exception as e: print(sym, "ERR", repr(e)[:200])
