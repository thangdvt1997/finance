"""Dukascopy: tai file tick .bi5 theo gio (LZMA), giai ma -> tick -> nen M1 (gia BID).

Giao thuc cong khai cua datafeed (khong can key):
  {base}/{SYMBOL}/{YYYY}/{MM-1:02d}/{DD}/{HH}h_ticks.bi5   (thang 0-based!)
Moi ban ghi 20 byte big-endian: ms_offset(u32) ask(u32) bid(u32) ask_vol(f32) bid_vol(f32);
gia nguyen = gia * scale (1e5 cho phan lon FX, 1e3 cho cap JPY va kim loai).
Da tham chieu cac wrapper OSS (dukascopy-node, duka) -- decoder viet lai ~30 dong, khong them dependency.
"""
from __future__ import annotations

import asyncio
import lzma
import random
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..errors import PartialData, RetryableError
from ..models import Bar, Quote, ensure_utc, floor_ts, utcnow
from ..ratelimit import RateLimiter
from ..resample import resample
from ..symbols import is_fx_pair
from .base import HttpProvider

_REC = struct.Struct(">IIIff")
BASE_URL = "https://datafeed.dukascopy.com/datafeed"
_SCALE_1E3 = {"XAUUSD", "XAGUSD"}


def price_scale(symbol: str) -> float:
    return 1e3 if symbol in _SCALE_1E3 or symbol.endswith("JPY") else 1e5


@dataclass(frozen=True, slots=True)
class Tick:
    ts: datetime
    bid: float
    ask: float
    bid_vol: float
    ask_vol: float


def decode_bi5(data: bytes, hour_start: datetime, scale: float) -> list[Tick]:
    if not data:
        return []
    raw = lzma.decompress(data)
    hs = ensure_utc(hour_start)
    n = len(raw) // _REC.size
    out: list[Tick] = []
    for i in range(n):
        ms, ask, bid, av, bv = _REC.unpack_from(raw, i * _REC.size)
        out.append(Tick(hs + timedelta(milliseconds=ms), bid / scale, ask / scale, float(bv), float(av)))
    return out


def ticks_to_m1(ticks: list[Tick], symbol: str, source: str = "dukascopy") -> list[Bar]:
    """Nen M1 tu gia BID; volume = tong (bid_vol + ask_vol) cua tick trong phut."""
    buckets: dict[datetime, list[Tick]] = {}
    for t in ticks:
        buckets.setdefault(floor_ts(t.ts, "M1"), []).append(t)
    bars = []
    for ts in sorted(buckets):
        ts_ = buckets[ts]
        prices = [t.bid for t in ts_]
        bars.append(Bar(symbol, "M1", ts, prices[0], max(prices), min(prices), prices[-1],
                        sum(t.bid_vol + t.ask_vol for t in ts_), source))
    return bars


class DukascopyProvider(HttpProvider):
    name = "dukascopy"
    fetch_tfs = ["M1"]
    chunk = timedelta(days=1)
    lookback = timedelta(hours=3)
    has_quotes = True

    # datafeed hay tra 503 khi bi don dap -> backoff dai hon + jitter lon, thu nhieu lan hon
    backoff = {"base_delay": 2.0, "factor": 2.0, "max_delay": 60.0, "jitter": 0.5, "retry_after_cap": 300.0}
    MAX_PACE = 30.0

    def __init__(self, client: httpx.AsyncClient, cache_dir: Path, *, rate_per_sec: int = 2,
                 concurrency: int = 2, base_url: str = BASE_URL, poll_interval: float = 60.0, **kw):
        kw.setdefault("attempts", 5)
        super().__init__(client, RateLimiter(rate_per_sec, 1.0), **kw)
        self._pace = 0.0  # tre them truoc moi request; tang khi gap 503/429, giam khi thanh cong
        self.cache_dir = Path(cache_dir) / "dukascopy"
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self._sem = asyncio.Semaphore(concurrency)

    def supports(self, symbol: str) -> bool:
        return is_fx_pair(symbol)

    # ---- throttle thich ung ----
    async def _before_attempt(self) -> None:
        if self._pace > 0:
            await self._sleep(self._pace * (0.5 + random.random()))

    def _on_success(self) -> None:
        self._pace = 0.0 if self._pace < 0.5 else self._pace / 2

    def _on_throttle(self, retry_after: float | None) -> None:
        self._pace = min(self.MAX_PACE, max(1.0, self._pace * 2))
        if retry_after:
            self._pace = min(self.MAX_PACE, max(self._pace, retry_after))

    def expects_data(self, now: datetime, symbol: str) -> bool:
        """False khi thi truong dong cua / ngay le (404 luc nay la binh thuong, khong phai loi)."""
        wd, h = now.weekday(), now.hour
        if (now.month, now.day) in {(12, 25), (1, 1)}:
            return False
        return not (wd == 5 or (wd == 4 and h >= 22) or (wd == 6 and h < 21))

    def find_missing_days(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[datetime]:
        """Gio da dong (>2h), thi truong dang mo, ma KHONG co file cache (tai that bai/chua tung tai) -> ngay thieu.
        File cache chi duoc ghi khi tai thanh cong (ke ca 404 xac nhan), nen vang mat = chua co du lieu."""
        end = ensure_utc(end)
        days: set[datetime] = set()
        h = floor_ts(start, "H1")
        while h + timedelta(hours=2) <= end:
            if h.weekday() != 5 and self.expects_data(h, symbol) and not self._cache_path(symbol, h).exists():
                days.add(floor_ts(h, "D1"))
            h += timedelta(hours=1)
        return sorted(days)

    def _url(self, symbol: str, hour: datetime) -> str:
        return f"{self.base_url}/{symbol}/{hour.year:04d}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"

    def _cache_path(self, symbol: str, hour: datetime) -> Path:
        return self.cache_dir / symbol / f"{hour.year:04d}" / f"{hour.month:02d}" / f"{hour.day:02d}" / f"{hour.hour:02d}h_ticks.bi5"

    async def _hour_bytes(self, symbol: str, hour: datetime) -> bytes:
        """404 = gio khong co du lieu (cuoi tuan/ngay le/chua phat hanh) -> b''; 5xx/429 -> loi tam thoi (retry)."""
        path = self._cache_path(symbol, hour)
        if path.exists():
            return path.read_bytes()
        async with self._sem:
            r = await self._request(self._url(symbol, hour))
        if r.status_code == 404:
            data = b""
        elif r.status_code != 200:
            raise RetryableError(f"dukascopy: HTTP {r.status_code}")
        else:
            data = r.content
        # chi cache gio da dong han (tranh luu file chua day cua gio hien tai)
        if hour + timedelta(hours=2) <= utcnow():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return data

    async def fetch_ticks(self, symbol: str, start: datetime, end: datetime) -> tuple[list[Tick], list[datetime]]:
        """Tra ve (ticks, gio_loi). Gio da tai thanh cong duoc cache dia -> lan thu lai chi tai phan con thieu."""
        scale = price_scale(symbol)
        hours, h = [], floor_ts(start, "H1")
        while h < end:
            if h.weekday() != 5:  # thu Bay khong co du lieu FX
                hours.append(h)
            h += timedelta(hours=1)
        results = await asyncio.gather(*(self._hour_bytes(symbol, hh) for hh in hours), return_exceptions=True)
        ticks: list[Tick] = []
        missing: list[datetime] = []
        for hh, res in zip(hours, results):
            if isinstance(res, BaseException):
                if not isinstance(res, RetryableError):
                    raise res
                missing.append(hh)
                continue
            ticks.extend(decode_bi5(res, hh, scale))
        return ticks, missing

    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        start, end = ensure_utc(start), ensure_utc(end)
        ticks, missing = await self.fetch_ticks(symbol, start, end)
        m1 = [b for b in ticks_to_m1(ticks, symbol) if start <= b.ts_open < end]
        bars = m1 if tf == "M1" else resample(m1, tf)
        if missing:
            raise PartialData(f"dukascopy {symbol}: thieu {len(missing)} gio (503/loi tam thoi), "
                              f"dau tien {missing[0]:%Y-%m-%d %Hh}", bars, missing)
        return bars

    async def latest_quote(self, symbol: str) -> Quote | None:
        now = utcnow()
        for back in (0, 1):  # gio hien tai co the chua co file -> lui 1 gio
            hour = floor_ts(now - timedelta(hours=back), "H1")
            try:
                blob = await self._hour_bytes(symbol, hour)
            except RetryableError:
                continue  # 503 tam thoi: bo qua quote vong nay (khong spam log)
            ticks = decode_bi5(blob, hour, price_scale(symbol))
            if ticks:
                t = ticks[-1]
                return Quote(symbol, t.bid, t.ask, t.ts, self.name)
        return None
