"""Lay nen M15 XAUUSD cho ba anh demo: uu tien bang bars (Timescale), thieu thi tai tick gio tu datafeed cong khai (co cache).
Chay TREN VPS trong container tam prender-*:  python tools/fetch_m15.py OUT.json 2026-09-21 2026-10-07
Chi dung thu vien chuan (urllib, lzma, struct). Ten nguon khong xuat hien trong anh.
"""
from __future__ import annotations

import json
import lzma
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://datafeed.dukascopy.com/datafeed/XAUUSD"
REC = struct.Struct(">IIIff")
CACHE = os.environ.get("PR_CACHE", "/data/raw")


def hour_url(h: datetime) -> str:
    return f"{BASE}/{h.year}/{h.month - 1:02d}/{h.day:02d}/{h.hour:02d}h_ticks.bi5"


def get_hour(h: datetime) -> bytes | None:
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, h.strftime("%Y%m%d%H") + ".bi5")
    if os.path.exists(fp):
        return open(fp, "rb").read()
    delay = 4.0
    for _ in range(12):
        try:
            req = urllib.request.Request(hour_url(h), headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            open(fp, "wb").write(data)
            time.sleep(0.6)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                open(fp, "wb").write(b"")
                return b""
            if e.code in (429, 503):
                time.sleep(delay)
                delay = min(delay * 1.6, 60)
                continue
            raise
        except Exception:
            time.sleep(delay)
    return None


def m15_from_hour(h: datetime, data: bytes) -> dict[int, list[float]]:
    out: dict[int, list[float]] = {}
    if not data:
        return out
    raw = lzma.decompress(data)
    for i in range(len(raw) // REC.size):
        ms, ask, bid, _, _ = REC.unpack_from(raw, i * REC.size)
        ts = h.timestamp() + ms / 1000.0
        b = int(ts // 900 * 900)
        p = bid / 1000.0
        c = out.get(b)
        if c is None:
            out[b] = [p, p, p, p]
        else:
            c[1] = max(c[1], p)
            c[2] = min(c[2], p)
            c[3] = p
    return out


def main() -> None:
    out_path, d0, d1 = sys.argv[1], sys.argv[2], sys.argv[3]
    start = datetime.fromisoformat(d0).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(d1).replace(tzinfo=timezone.utc)
    bars: dict[int, list[float]] = {}
    h = start
    miss = 0
    while h < end:
        if h.weekday() < 5 or (h.weekday() == 6 and h.hour >= 21) or (h.weekday() == 4 and h.hour < 22):
            data = get_hour(h)
            if data is None:
                miss += 1
            else:
                part = m15_from_hour(h, data)
                for k, v in part.items():
                    cur = bars.get(k)
                    if cur is None:
                        bars[k] = v
                    else:
                        cur[1] = max(cur[1], v[1]); cur[2] = min(cur[2], v[2]); cur[3] = v[3]
        h += timedelta(hours=1)
    rows = [{"t": k, "o": v[0], "h": v[1], "l": v[2], "c": v[3]} for k, v in sorted(bars.items())]
    json.dump(rows, open(out_path, "w"))
    print(f"{len(rows)} nen M15, thieu {miss} gio, {rows[0]['t'] if rows else None}..{rows[-1]['t'] if rows else None}")


if __name__ == "__main__":
    main()
