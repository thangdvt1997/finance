from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Awaitable, Callable

import httpx

from email.utils import parsedate_to_datetime

from ..errors import FatalError, RateLimited, RetryableError, ServiceUnavailable
from ..models import Bar, Quote
from ..ratelimit import RateLimiter
from ..retry import retry_async


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After: so giay hoac HTTP-date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from datetime import timezone
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class Provider(ABC):
    """Plugin nguon gia. Moi provider tu khai bao tf goc, kich thuoc chunk backfill, chu ky cap nhat."""

    name: str = "base"
    fetch_tfs: list[str] = ["D1"]      # tf goc provider tra ve. "M1" => collector tu resample len cac tf cao.
    chunk: timedelta = timedelta(days=1)  # PHAI la boi so cua 1 ngay (de bucket resample khong bi cat doi)
    lookback: timedelta = timedelta(hours=2)  # cua so cho lan cap nhat dinh ky
    poll_interval: float = 60.0
    has_quotes: bool = False
    resample_m1: bool = True           # fetch_tfs co 'M1' => collector tu resample len cac tf cao; False = nguon co nen goc cho moi tf (vd crypto)
    trades_weekends: bool = False      # True (vd crypto 24/7): khong ap lich cuoi tuan FX khi kiem tra gap
    quote_stream_interval: float = 0.0  # >0: collector chay them vong lap `latest_quotes()` chu ky nay (giay)

    @abstractmethod
    def supports(self, symbol: str) -> bool: ...

    @abstractmethod
    async def fetch_bars(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
        """Tra ve nen [start, end) UTC, tang dan theo ts_open."""

    async def latest_quote(self, symbol: str) -> Quote | None:
        return None

    # ---- hook tuy chon (mac dinh giu hanh vi cu) ----
    def chunk_for(self, tf: str) -> timedelta:
        """Kich thuoc chunk backfill theo tf (boi so cua 1 ngay)."""
        return self.chunk

    def backfill_start(self, tf: str, default: datetime, now: datetime) -> datetime:
        """Moc bat dau backfill khi khoi dong cho tung tf (mac dinh = cua so chung `BACKFILL_DAYS`)."""
        return default

    def poll_tfs(self, symbol: str, now: datetime) -> list[str]:
        """Cac tf can poll o vong nay (mac dinh: tat ca `fetch_tfs`)."""
        return self.fetch_tfs

    def poll_start(self, symbol: str, tf: str, now: datetime) -> datetime | None:
        """Moc bat dau cua so poll; None = mac dinh cua collector (00:00 UTC cua `now - lookback`)."""
        return None

    def rewind(self, symbol: str, tf: str, to: datetime) -> None:
        """Goi khi phat nen that bai sau khi fetch: provider co trang thai 'nen cuoi da thay' phai lui ve `to`."""
        return None

    async def latest_quotes(self) -> list[Quote]:
        """Chi dung khi `quote_stream_interval` > 0: lay quote moi nhat cua MOI symbol trong 1 lan goi."""
        return []

    def next_poll_delay(self, now: datetime) -> float:
        """Giay cho den lan poll ke tiep (mac dinh = poll_interval; provider co the dat lich co dinh trong ngay)."""
        return self.poll_interval

    def expects_data(self, now: datetime, symbol: str) -> bool:
        """False khi thi truong dong cua (de khong bao dong 'rong' gia). Mac dinh: ngay thuong."""
        return now.weekday() < 5

    def find_missing_days(self, symbol: str, tf: str, start: datetime, end: datetime) -> list[datetime]:
        """Cac ngay UTC (00:00) trong [start,end) con thieu du lieu ma provider tu biet duoc (vd qua cache dia).
        Mac dinh: khong biet -> []."""
        return []

    async def aclose(self) -> None:
        return None


class HttpProvider(Provider):
    """Provider goi HTTP: gom rate limit + retry/backoff + dich loi status thanh ngoai le."""

    backoff: dict = {}  # ghi de base_delay/factor/max_delay/jitter/retry_after_cap cho retry_async

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter, *, attempts: int = 4,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, backoff: dict | None = None):
        self.client, self.limiter, self.attempts, self._sleep = client, limiter, attempts, sleep
        if backoff is not None:
            self.backoff = backoff

    # hook cho provider can throttle thich ung (vd Dukascopy)
    async def _before_attempt(self) -> None:
        return None

    def _on_success(self) -> None:
        return None

    def _on_throttle(self, retry_after: float | None) -> None:
        return None

    async def _request(self, url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        async def once() -> httpx.Response:
            await self._before_attempt()
            await self.limiter.acquire()
            try:
                r = await self.client.get(url, params=params, headers=headers)
            except httpx.TransportError as e:
                # khong dua URL/params (co the chua API key) vao thong diep loi
                raise RetryableError(f"{self.name}: loi mang {type(e).__name__}") from None
            ra = parse_retry_after(r.headers.get("Retry-After"))
            if r.status_code == 429:
                self._on_throttle(ra)
                raise RateLimited(f"{self.name}: 429", ra)
            if r.status_code >= 500:
                self._on_throttle(ra)
                raise ServiceUnavailable(f"{self.name}: HTTP {r.status_code}", ra, r.status_code)
            self._on_success()
            if r.status_code in (401, 403):
                raise FatalError(f"{self.name}: HTTP {r.status_code} (kiem tra key/quyen)")
            return r

        return await retry_async(once, attempts=self.attempts, sleep=self._sleep, **self.backoff)
