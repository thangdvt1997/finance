from __future__ import annotations

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def make_app(service_name: str, version: str = "0.1.0", internal_auth: bool = False) -> FastAPI:
    """FastAPI tối thiểu với /healthz và /metrics; service thêm route của mình.
    internal_auth=True: kiểm header X-Internal-Token (tscommon.internal_auth; INTERNAL_AUTH_MODE off|log|enforce, miễn /healthz /metrics)."""
    app = FastAPI(title=service_name, version=version)
    if internal_auth:
        from .internal_auth import install_internal_auth
        install_internal_auth(app, service_name)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "service": service_name, "version": version}

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
