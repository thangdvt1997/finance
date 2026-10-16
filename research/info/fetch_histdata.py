"""Tai nen M1 (bid) HistData.com (mien phi, ASCII M1, gio EST co dinh UTC-5) cho 4 ma x thang 2026-04..09. Thay the Dukascopy (bi chan mang)."""
import re, time, pathlib, requests
D = pathlib.Path(__file__).parent / "data" / "hd"; D.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 research-script contact:<OWNER_EMAIL>"}
for sym in ("eurusd", "gbpusd", "usdjpy", "xauusd"):
    for ym in range(202604, 202610):
        out = D / f"{sym}_{ym}.zip"
        if out.exists(): continue
        page = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{sym}/{ym // 100}/{ym % 100}"
        h = requests.get(page, headers=UA, timeout=60).text
        tk = re.search(r'name="tk" id="tk" value="([0-9a-f]+)"', h)
        if not tk: print("no token", sym, ym); continue
        r = requests.post("https://www.histdata.com/get.php", data={"tk": tk.group(1), "date": str(ym // 100), "datemonth": str(ym), "platform": "ASCII", "timeframe": "M1", "fxpair": sym.upper()},
                          headers={**UA, "Referer": page}, timeout=120)
        print(sym, ym, r.status_code, len(r.content), r.content[:2])
        if r.content[:2] == b"PK": out.write_bytes(r.content)
        time.sleep(3)
