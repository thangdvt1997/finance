class ProviderError(Exception):
    """Loi chung cua provider."""


class RetryableError(ProviderError):
    """Loi tam thoi (mang, 5xx) -> retry/backoff."""


class RateLimited(RetryableError):
    def __init__(self, msg: str = "rate limited", retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class FatalError(ProviderError):
    """Loi khong retry duoc (sai key, 401/403, tham so sai)."""


class ServiceUnavailable(RateLimited):
    """5xx (vd 503): nguon tam thoi qua tai -> thu lai sau, ton trong Retry-After."""

    def __init__(self, msg: str = "service unavailable", retry_after: float | None = None, status: int = 503):
        super().__init__(msg, retry_after)
        self.status = status


class PartialData(RetryableError):
    """Mot so gio/chunk lay duoc, mot so loi tam thoi. `bars` = phan da co, `missing` = moc thoi gian con thieu."""

    def __init__(self, msg: str, bars: list, missing: list):
        super().__init__(msg)
        self.bars, self.missing = bars, missing
