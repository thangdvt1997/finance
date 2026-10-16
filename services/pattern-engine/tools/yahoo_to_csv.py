"""Chuyển JSON chart Yahoo (interval=15m) sang CSV UTC cho fixture. Dự phòng khi nguồn tick không tải được.
   python3 yahoo_to_csv.py gcf.json 2026-09-20 2026-10-07 out.csv"""
import csv, datetime as dt, json, sys

src, a, b, out = sys.argv[1:5]
r = json.load(open(src))["chart"]["result"][0]
ts, q = r["timestamp"], r["indicators"]["quote"][0]
t0 = dt.datetime.fromisoformat(a); t1 = dt.datetime.fromisoformat(b)
n = 0
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["ts_open_utc", "o", "h", "l", "c", "v"])
    for i, t in enumerate(ts):
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).replace(tzinfo=None)
        if not (t0 <= d < t1) or d.minute % 15 or None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
            continue
        w.writerow([d.strftime("%Y-%m-%dT%H:%M:%SZ"), round(q["open"][i], 3), round(q["high"][i], 3), round(q["low"][i], 3),
                    round(q["close"][i], 3), q["volume"][i] or 0]); n += 1
print("bars", n)
