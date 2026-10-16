"""HTTP client lịch sự: User-Agent từ Settings, rate limit theo host, ETag/Last-Modified cache, retry nhẹ."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger("news_collector.http")


@dataclass
class CacheEntry:
    etag: str | None
    last_modified: str | None
    body: bytes


class HostCoolingDown(Exception):
    """Host dang bi 429 -> nghi (circuit breaker), khong gui request nua cho den het cooldown."""

    def __init__(self, host: str, retry_in: float):
        super().__init__(f"{host} dang bi gioi han toc do, thu lai sau {retry_in:.0f}s")
        self.host, self.retry_in = host, retry_in


class PoliteClient:
    def __init__(self, user_agent: str, min_interval: dict[str, float] | None = None,
                 default_interval: float = 1.0, transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 30.0, max_retries: int = 2, sleep=asyncio.sleep, clock=time.monotonic,
                 strict_hosts: set[str] | None = None, cooldown_base: float = 60.0, cooldown_max: float = 900.0):
        self._client = httpx.AsyncClient(headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
                                         transport=transport, timeout=timeout, follow_redirects=True)
        self.min_interval = min_interval or {}
        self.default_interval = default_interval
        self.max_retries = max_retries
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[str, CacheEntry] = {}
        self._sleep, self._clock = sleep, clock
        # host nghiem ngat (vd GDELT): 429 -> KHONG retry, cooldown tang dan (jitter) cho ca host
        self.strict_hosts = strict_hosts or set()
        self.cooldown_base, self.cooldown_max = cooldown_base, cooldown_max
        self._blocked_until: dict[str, float] = {}
        self._streak: dict[str, int] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def cooldown_left(self, host: str) -> float:
        return max(0.0, self._blocked_until.get(host, 0.0) - self._clock())

    def note_rate_limited(self, host: str, retry_after: float | None = None) -> float:
        """Ghi nhan host bi gioi han toc do; tra ve so giay cooldown."""
        n = self._streak[host] = self._streak.get(host, 0) + 1
        delay = min(self.cooldown_max, self.cooldown_base * 2 ** (n - 1))
        if retry_after:
            delay = max(delay, min(retry_after, self.cooldown_max))
        delay *= 1 + random.random() * 0.2
        self._blocked_until[host] = self._clock() + delay
        return delay

    def note_ok(self, host: str) -> None:
        self._streak.pop(host, None)

    async def _throttle(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            gap = self.min_interval.get(host, self.default_interval)
            wait = self._last.get(host, -1e9) + gap - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._last[host] = self._clock()

    async def get(self, url: str, params: dict | None = None, use_cache: bool = True,
                  headers: dict | None = None) -> tuple[bytes | None, bool]:
        """Trả (body, from_cache_not_modified). 304 -> (body_cũ, True). Lỗi cuối -> raise."""
        host = urlparse(url).netloc
        key = url + ("?" + "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "")
        hdrs = dict(headers or {})
        cached = self._cache.get(key) if use_cache else None
        if cached:
            if cached.etag:
                hdrs["If-None-Match"] = cached.etag
            if cached.last_modified:
                hdrs["If-Modified-Since"] = cached.last_modified
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if (left := self.cooldown_left(host)) > 0:
                raise HostCoolingDown(host, left)
            await self._throttle(host)
            try:
                r = await self._client.get(url, params=params, headers=hdrs)
            except httpx.TransportError as e:
                last_exc = e
                await self._sleep(2 ** attempt)
                continue
            if r.status_code == 304 and cached:
                return cached.body, True
            if r.status_code == 429 and host in self.strict_hosts:
                ra = r.headers.get("Retry-After")
                raise HostCoolingDown(host, self.note_rate_limited(host, float(ra) if ra and ra.isdigit() else None))
            if r.status_code in (429, 503) or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                delay = float(ra) if ra and ra.isdigit() else 2 ** (attempt + 1)
                last_exc = httpx.HTTPStatusError(f"{r.status_code} {url}", request=r.request, response=r)
                if attempt < self.max_retries:
                    await self._sleep(min(delay, 60))
                continue
            r.raise_for_status()
            self.note_ok(host)
            if use_cache and (r.headers.get("etag") or r.headers.get("last-modified")):
                self._cache[key] = CacheEntry(r.headers.get("etag"), r.headers.get("last-modified"), r.content)
            return r.content, False
        assert last_exc is not None
        raise last_exc

    async def post_json(self, url: str, body, headers: dict | None = None) -> bytes:
        """POST JSON (API khong ho tro GET: BLS, StatCan). Cung throttle theo host + retry nhe nhu get()."""
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if (left := self.cooldown_left(host)) > 0:
                raise HostCoolingDown(host, left)
            await self._throttle(host)
            try:
                r = await self._client.post(url, json=body, headers=headers or {})
            except httpx.TransportError as e:
                last_exc = e
                await self._sleep(2 ** attempt)
                continue
            if r.status_code == 429:
                raise HostCoolingDown(host, self.note_rate_limited(host, None))
            if r.status_code >= 500:
                last_exc = httpx.HTTPStatusError(f"{r.status_code} {url}", request=r.request, response=r)
                if attempt < self.max_retries:
                    await self._sleep(min(2 ** (attempt + 1), 60))
                continue
            r.raise_for_status()
            self.note_ok(host)
            return r.content
        assert last_exc is not None
        raise last_exc
