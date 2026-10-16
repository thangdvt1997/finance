import uvicorn

from tscommon import get_settings, setup_logging

from .app import create_app

if __name__ == "__main__":
    setup_logging()
    uvicorn.run(create_app(), host="0.0.0.0", port=get_settings().port)
