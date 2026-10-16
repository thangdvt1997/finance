"""Cấu hình logging chung: format thống nhất, hạ log ồn của thư viện HTTP (mỗi request 1 dòng INFO)."""
from __future__ import annotations

import logging
import os

NOISY = ("httpx", "httpcore", "hpack", "asyncio")


def setup_logging(level: str | None = None) -> None:
    logging.basicConfig(level=(level or os.getenv("LOG_LEVEL", "INFO")).upper(),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _DropProbeAccess) for f in access.filters):
        access.addFilter(_DropProbeAccess())


class _DropProbeAccess(logging.Filter):
    """Bỏ dòng access log của healthcheck/metrics (Docker + Prometheus gọi mỗi vài giây)."""

    PATHS = ("/healthz ", "/metrics ", "/readyz ")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self.PATHS)
