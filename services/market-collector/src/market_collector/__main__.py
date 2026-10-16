import uvicorn
from tscommon import setup_logging

from .app import create_app
from .config import CollectorSettings


def main() -> None:
    cfg = CollectorSettings.from_env()
    setup_logging()  # httpx -> WARNING, bo access log /healthz,/metrics
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port)


if __name__ == "__main__":
    main()
