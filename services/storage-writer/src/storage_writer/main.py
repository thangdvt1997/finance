from __future__ import annotations

import asyncio
import logging
import os

import redis.asyncio as aioredis
import uvicorn
from tscommon import setup_logging
from tscommon.config import get_settings
from tscommon.http import make_app

from .db import AsyncpgDB
from .writer import StorageWriter


async def amain() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    r = aioredis.from_url(s.redis_url, decode_responses=True)
    db = None
    while db is None:  # chờ DB sẵn sàng
        try:
            db = await AsyncpgDB.connect(s.database_url)
        except Exception as e:
            logging.warning("chờ DB: %s", e)
            await asyncio.sleep(3)
    w = StorageWriter(r, db, consumer=os.getenv("CONSUMER_NAME", "storage-writer-1"),
                      reclaim_min_idle_ms=int(os.getenv("RECLAIM_MIN_IDLE_MS", "60000")),
                      reclaim_interval_s=float(os.getenv("RECLAIM_INTERVAL_S", "30")),
                      max_deliveries=int(os.getenv("MAX_DELIVERIES", "5")))
    app = make_app("storage-writer", internal_auth=True)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=s.port, log_level="warning"))
    await asyncio.gather(w.run(), server.serve())


def main() -> None:
    asyncio.run(amain())
