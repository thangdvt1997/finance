from __future__ import annotations

import os

import uvicorn
from tscommon import setup_logging
from tscommon.internal_auth import install_urllib_client

from .app import create_app


def main() -> None:
    setup_logging()
    install_urllib_client({"alert-rules"})  # X-Internal-Token khi gọi alert-rules /internal/notify (tscommon.internal_auth)
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")))  # noqa: S104


if __name__ == "__main__":
    main()
