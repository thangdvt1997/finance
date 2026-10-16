from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import HTTPException
from tscommon import Bus, get_settings, make_app

from . import DISCLAIMER
from .collector import Collector
from .config import ECConfig
from .httpclient import PoliteClient
from .registry import build_sources


def build_app(collector: Collector, run_loop: bool = True):
    app = make_app("expert-collector", internal_auth=True)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(collector.run()) if run_loop else None
        yield
        if task:
            task.cancel()

    app.router.lifespan_context = lifespan

    @app.get("/experts")
    async def experts(tracked: bool = False):
        return {"disclaimer": DISCLAIMER, "items": await collector.list_experts_api(tracked)}

    @app.get("/opinions")
    async def opinions(group: str | None = None, limit: int = 100):
        return {"disclaimer": DISCLAIMER, "items": await collector.list_opinions_api(group, limit)}

    @app.get("/experts/{expert_id:path}")
    async def expert(expert_id: str):
        for i in await collector.list_experts_api():
            if i["expert_id"] == expert_id:
                return i
        raise HTTPException(404, "not found")

    return app


def create_app():
    st = get_settings()
    logging.basicConfig(level=st.log_level)
    cfg = ECConfig.from_env()
    client = PoliteClient(st.user_agent, cfg.http_min_interval, cfg.http_cache_ttl, cfg.respect_robots,
                          host_intervals={"www.sec.gov": 0.2, "public.api.bsky.app": 0.5})
    bus = Bus.from_url(st.redis_url)
    collector = Collector(build_sources(cfg, client), bus, cfg)
    return build_app(collector, run_loop=st.enabled)
