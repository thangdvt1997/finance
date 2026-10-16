"""Xuất nến M15 XAU/USD từ Twelve Data (khoá free trong infra/.env) ra CSV UTC cho golden test. Chạy trên VPS:
   python3 export_fixture_td.py /root/trading-system/infra/.env 2026-09-20 2026-10-07 out.csv"""
import csv, json, sys, urllib.parse, urllib.request

env, a, b, out = sys.argv[1:5]
key = next(l.split("=", 1)[1].strip() for l in open(env) if l.startswith("TWELVEDATA_API_KEY="))
q = urllib.parse.urlencode({"symbol": "XAU/USD", "interval": "15min", "start_date": a, "end_date": b, "outputsize": 5000,
                            "timezone": "UTC", "order": "ASC", "apikey": key})
d = json.load(urllib.request.urlopen("https://api.twelvedata.com/time_series?" + q, timeout=60))
if d.get("status") == "error" or "values" not in d:
    sys.exit("lỗi: " + str({k: d.get(k) for k in ("code", "message", "status")}))
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ts_open_utc", "o", "h", "l", "c", "v"])
    for r in d["values"]:
        w.writerow([r["datetime"].replace(" ", "T") + "Z", r["open"], r["high"], r["low"], r["close"], r.get("volume") or 0])
print("bars", len(d["values"]), d["values"][0]["datetime"], d["values"][-1]["datetime"])
