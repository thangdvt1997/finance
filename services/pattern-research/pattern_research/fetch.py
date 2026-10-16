"""Tai du lieu M1 lich su MIEN PHI: Dukascopy (FX/vang/chi so) + Binance public data (crypto).
Chay: python -m pattern_research.fetch duka|binance  (cache tho trong OUT/raw, chay lai duoc/resumable).
Ton trong gioi han: 1 request/~0.9s toi Dukascopy, backoff khi loi."""
from __future__ import annotations

import io
import os
import struct
import sys
import time
import lzma
import urllib.request
import urllib.error
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

OUT = Path(os.environ.get("PATTERN_OUT", "/out"))
UA = "Mozilla/5.0 (research; free public data)"
DUKA = {  # ten ra : (ma Dukascopy, he so gia)
    "XAUUSD": ("XAUUSD", 1e3), "EURUSD": ("EURUSD", 1e5), "GBPUSD": ("GBPUSD", 1e5),
    "USDJPY": ("USDJPY", 1e3), "US500": ("USA500IDXUSD", 1e3),
}
BIN = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
DUKA_START = date(2023, 10, 1)
BIN_START = (2020, 10)
_REC = struct.Struct(">IIIIIf")  # t(s), open, close, low, high, vol


def _get(url: str, timeout=30) -> bytes | None:
    for i in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            wait = 30 * (2 ** i) if e.code in (429, 503) else 5 * (i + 1)
        except Exception:
            wait = 15 * (i + 1)
        time.sleep(wait)
    raise RuntimeError(f"fail {url}")


def decode_candles(blob: bytes, day: date, scale: float) -> pd.DataFrame:
    if not blob:
        return pd.DataFrame()
    raw = lzma.decompress(blob)
    rows = [_REC.unpack_from(raw, i) for i in range(0, len(raw) - len(raw) % 24, 24)]
    if not rows:
        return pd.DataFrame()
    a = pd.DataFrame(rows, columns=["t", "o", "c", "l", "h", "v"])
    base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    a["ts_open"] = pd.to_datetime(base) + pd.to_timedelta(a["t"], unit="s")
    for k in "ochl":
        a[k] = a[k] / scale
    return a[["ts_open", "o", "h", "l", "c", "v"]]


def merge_duka():
    end = date.today() - timedelta(days=1)
    for name, (code, scale) in DUKA.items():
        frames, d = [], DUKA_START
        while d <= end:
            f = OUT / "raw" / "duka" / name / f"{d:%Y}" / f"{d:%m%d}.bi5"
            if f.exists() and f.stat().st_size:
                try:
                    frames.append(decode_candles(f.read_bytes(), d, scale))
                except Exception as e:
                    print("decode err", name, d, e, flush=True)
            d += timedelta(days=1)
        if frames:
            m1 = pd.concat(frames, ignore_index=True)
            (OUT / "m1").mkdir(parents=True, exist_ok=True)
            m1.to_parquet(OUT / "m1" / f"{name}.parquet", index=False)
            print("m1", name, len(m1), m1.ts_open.min(), m1.ts_open.max(), flush=True)


def fetch_duka():
    """Moi->cu, xen ke cac ma; khi bi chan (connect timeout) thi nghi 5 phut roi thu lai (khong spam)."""
    end = date.today() - timedelta(days=1)
    d, since_merge = end, 0
    while d >= DUKA_START:
        if d.weekday() != 5:
            for name, (code, scale) in DUKA.items():
                f = OUT / "raw" / "duka" / name / f"{d:%Y}" / f"{d:%m%d}.bi5"
                if f.exists():
                    continue
                url = f"https://datafeed.dukascopy.com/datafeed/{code}/{d.year:04d}/{d.month-1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
                while True:
                    try:
                        blob = _get1(url)
                        break
                    except Exception as e:
                        print("blocked/err", name, d, str(e)[:80], "-> sleep 300", flush=True)
                        time.sleep(300)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(blob or b"")
                time.sleep(1.0)
        d -= timedelta(days=1)
        since_merge += 1
        if since_merge % 60 == 0:
            print("progress", d, flush=True)
            merge_duka()
    merge_duka()


def _get1(url: str, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


YAHOO = {"XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "US500": "ES=F"}


def fetch_yahoo():
    """Du phong mien phi (Yahoo chart API): 1h toi ~730 ngay, 15m/5m toi 60 ngay. Luu OUT/raw/yahoo."""
    import json as _j
    for name, tk in YAHOO.items():
        for iv, rng in (("1h", "730d"), ("15m", "60d"), ("5m", "60d")):
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?interval={iv}&range={rng}"
            blob = _get(url, 60)
            if blob is None:
                print("yahoo 404", name, tk, iv, flush=True)
                continue
            j = _j.loads(blob)["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            df = pd.DataFrame({"ts_open": pd.to_datetime(j["timestamp"], unit="s", utc=True),
                               "o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"], "v": q["volume"]})
            df = df.dropna(subset=["o", "h", "l", "c"])
            p = OUT / "raw" / "yahoo" / f"{name}_{iv}.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(p, index=False)
            print("yahoo", name, iv, len(df), df.ts_open.min(), df.ts_open.max(), flush=True)
            time.sleep(1.5)


def _bin_df(blob: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(blob))
    df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=[0, 1, 2, 3, 4, 5],
                     names=["t", "o", "h", "l", "c", "v"])
    t = df["t"].astype("int64")
    unit = "us" if t.iloc[0] > 10**14 else "ms"
    df["ts_open"] = pd.to_datetime(t, unit=unit, utc=True)
    return df[["ts_open", "o", "h", "l", "c", "v"]]


def fetch_binance():
    today = date.today()
    for name, sym in BIN.items():
        frames, (y, m) = [], BIN_START
        while (y, m) < (today.year, today.month):
            ck = OUT / "raw" / "binance" / name / f"{y}-{m:02d}.parquet"
            if not ck.exists():
                url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip"
                blob = _get(url, 120)
                ck.parent.mkdir(parents=True, exist_ok=True)
                (_bin_df(blob) if blob else pd.DataFrame(columns=["ts_open", "o", "h", "l", "c", "v"])).to_parquet(ck, index=False)
                time.sleep(0.3)
            frames.append(pd.read_parquet(ck))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        d = date(today.year, today.month, 1)  # thang hien tai: file ngay
        while d < today:
            ck = OUT / "raw" / "binance" / name / f"d{d:%Y%m%d}.parquet"
            if not ck.exists():
                blob = _get(f"https://data.binance.vision/data/spot/daily/klines/{sym}/1m/{sym}-1m-{d:%Y-%m-%d}.zip", 60)
                if blob:
                    _bin_df(blob).to_parquet(ck, index=False)
                time.sleep(0.3)
            if ck.exists():
                frames.append(pd.read_parquet(ck))
            d += timedelta(days=1)
        m1 = pd.concat([f for f in frames if len(f)], ignore_index=True)
        (OUT / "m1").mkdir(parents=True, exist_ok=True)
        m1.to_parquet(OUT / "m1" / f"{name}.parquet", index=False)
        print("m1", name, len(m1), m1.ts_open.min(), m1.ts_open.max(), flush=True)


if __name__ == "__main__":
    {"duka": fetch_duka, "binance": fetch_binance, "yahoo": fetch_yahoo, "merge": merge_duka}[sys.argv[1]]()
