from __future__ import annotations

import os

import uvicorn
from tscommon import setup_logging
from tscommon.internal_auth import install_urllib_client

from .app import create_app
from .tracing import setup_tracing


def main() -> None:
    setup_logging()
    install_urllib_client()  # X-Internal-Token cho lời gọi urllib tới service nội bộ (tscommon.internal_auth, HARDENING §7)
    app = create_app()
    setup_tracing(app)  # no-op nếu không có OTEL_EXPORTER_OTLP_ENDPOINT
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))  # noqa: S104


if __name__ == "__main__":
    main()
