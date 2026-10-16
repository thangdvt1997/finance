"""HTTP client lich su: User-Agent ro rang, rate limit theo host, cache TTL, ton trong robots.txt."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable
from urllib import robotparser
from urllib.parse import urlsplit

import httpx


class RobotsDenied(Exception):
    pass


class PoliteClient:
    def __init__(self, user_agent: str, min_interval: float = 2.0, cache_ttl: float = 120.0,
                 respect_robots: bool = True, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep, timeout: float = 20.0,
                 host_intervals: dict[str, float] | None = None):
        self.ua = user_agent
        self.min_interval = min_interval
        self.host_intervals = host_intervals or {}
        self._validators: dict[str, tuple[str | None, str | None]] = {}
        self.cache_ttl = cache_ttl
        self.respect_robots = respect_robots
        self._clock, self._sleep = clock, sleep
        self._client = httpx.AsyncClient(headers={"User-Agent": user_agent}, transport=transport,
                                         timeout=timeout, follow_redirects=True)
        self._last: dict[str, float] = {}
        self._cache: dict[str, tuple[float, str]] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._lock = asyncio.Lock()
        self.requests = 0  # so request that su ra mang (de test)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self, host: str) -> None:
        async with self._lock:
            wait = self._last.get(host, -1e9) + self.host_intervals.get(host, self.min_interval) - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._last[host] = self._clock()

    async def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        sp = urlsplit(url)
        origin = f"{sp.scheme}://{sp.netloc}"
        if origin not in self._robots:
            rp: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
            try:
                await self._throttle(sp.netloc)
                r = await self._client.get(origin + "/robots.txt")
                self.requests += 1
                if r.status_code >= 500:
                    rp = None  # khong xac dinh duoc -> tu choi (an toan)
                elif r.status_code >= 400:
                    rp.parse([])  # khong co robots -> cho phep
                else:
                    rp.parse([ln for ln in r.text.splitlines() if ln.strip()])  # bo dong trong: robotparser coi dong trong = het nhom (SEC bi sot Disallow)
            except httpx.HTTPError:
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return rp is not None and rp.can_fetch(self.ua, url)

    async def get_text(self, url: str, params: dict[str, Any] | None = None, *, cache: bool = True,
                       robots: bool = True) -> str:
        key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        hit = self._cache.get(key)
        if cache and hit and self._clock() - hit[0] < self.cache_ttl:
            return hit[1]
        if robots and not await self._allowed(url):
            raise RobotsDenied(url)
        await self._throttle(urlsplit(url).netloc)
        r = await self._client.get(url, params=params)
        self.requests += 1
        r.raise_for_status()
        if cache:
            self._cache[key] = (self._clock(), r.text)
        return r.text

    async def get_text_cond(self, url: str, params: dict[str, Any] | None = None) -> str | None:
        """GET co dieu kien (ETag/Last-Modified). Tra None neu 304 (khong doi). Ton trong robots + rate limit theo host."""
        key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        if not await self._allowed(url):
            raise RobotsDenied(url)
        await self._throttle(urlsplit(url).netloc)
        etag, lm = self._validators.get(key, (None, None))
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if lm:
            headers["If-Modified-Since"] = lm
        r = await self._client.get(url, params=params, headers=headers)
        self.requests += 1
        if r.status_code == 304:
            return None
        r.raise_for_status()
        if r.headers.get("etag") or r.headers.get("last-modified"):
            self._validators[key] = (r.headers.get("etag"), r.headers.get("last-modified"))
        return r.text
