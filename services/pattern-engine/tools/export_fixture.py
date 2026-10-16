"""Xuất nến M15 từ tick .bi5 công khai (giá BID, giống market-collector) ra CSV cho golden test.
Chạy trên VPS:  python3 export_fixture.py XAUUSD 2026-09-20 2026-10-07 out.csv
CSV: ts_open_utc,o,h,l,c,v   (chỉ stdlib; không ghi DB)"""
from __future__ import annotations

import csv
import lzma
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REC = struct.Struct(">IIIff")
BASE = "https://datafeed.dukascopy.com/datafeed"


def hour_ticks(sym: str, h: datetime, scale: float):
    url = f"{BASE}/{sym}/{h.year:04d}/{h.month - 1:02d}/{h.day:02d}/{h.hour:02d}h_ticks.bi5"
    for attempt in range(10):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tradingsys-fixture/1.0"})
            raw = urllib.request.urlopen(req, timeout=30).read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            time.sleep(15 * (attempt + 1) if e.code == 429 else 3 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"không tải được {url}")
    if not raw:
        return []
    d = lzma.decompress(raw)
    out = []
    for i in range(len(d) // REC.size):
        ms, ask, bid, av, bv = REC.unpack_from(d, i * REC.size)
        out.append((h + timedelta(milliseconds=ms), bid / scale, float(av) + float(bv)))
    return out


def main(sym: str, a: str, b: str, path: str) -> None:
    scale = 1e3 if sym in {"XAUUSD", "XAGUSD"} or sym.endswith("JPY") else 1e5
    t0 = datetime.fromisoformat(a).replace(tzinfo=timezone.utc)
    t1 = datetime.fromisoformat(b).replace(tzinfo=timezone.utc)
    buckets: dict[datetime, list] = {}
    h = t0
    while h < t1:
        wd = h.weekday()
        if wd == 5 or (wd == 4 and h.hour >= 22) or (wd == 6 and h.hour < 21):   # thị trường đóng cửa cuối tuần
            h += timedelta(hours=1)
            continue
        print(h.isoformat(), flush=True)
        for ts, px, v in hour_ticks(sym, h, scale):
            k = ts.replace(minute=ts.minute - ts.minute % 15, second=0, microsecond=0)
            buckets.setdefault(k, []).append((px, v))
        h += timedelta(hours=1)
        time.sleep(1.5)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_open_utc", "o", "h", "l", "c", "v"])
        for k in sorted(buckets):
            p = [x[0] for x in buckets[k]]
            w.writerow([k.strftime("%Y-%m-%dT%H:%M:%SZ"), p[0], max(p), min(p), p[-1], round(sum(x[1] for x in buckets[k]), 3)])
    print("bars", len(buckets))


if __name__ == "__main__":
    main(*sys.argv[1:5])
