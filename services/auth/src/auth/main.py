from __future__ import annotations

import os

import uvicorn
from tscommon import setup_logging

from .app import create_app


def main() -> None:
    setup_logging()
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")),  # noqa: S104
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
