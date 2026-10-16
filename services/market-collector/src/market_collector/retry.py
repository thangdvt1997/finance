from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from .errors import RateLimited, RetryableError

T = TypeVar("T")


async def retry_async(fn: Callable[[], Awaitable[T]], *, attempts: int = 4, base_delay: float = 1.0,
                      factor: float = 2.0, max_delay: float = 30.0, jitter: float = 0.1, retry_after_cap: float = 120.0,
                      retry_on: tuple[type[BaseException], ...] = (RetryableError,),
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> T:
    """Exponential backoff; ton trong Retry-After khi bi 429."""
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            if i == attempts - 1:
                raise
            delay = min(max_delay, base_delay * factor**i)
            if isinstance(e, RateLimited) and e.retry_after:
                delay = max(delay, min(e.retry_after, retry_after_cap))
            await sleep(delay * (1 + random.random() * jitter))
    raise AssertionError("unreachable")
