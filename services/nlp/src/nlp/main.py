import uvicorn
from tscommon import setup_logging
from tscommon.config import get_settings

from .app import create_app


def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    uvicorn.run(create_app(), host="0.0.0.0", port=s.port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
