from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import HTTPException
from pydantic import BaseModel, Field
from tscommon.bus import Bus
from tscommon.http import make_app

from . import entities, topics
from .enrich import Enricher
from .models import build_engine
from .settings import NlpSettings
from .worker import NlpWorker

log = logging.getLogger("nlp.app")


def build_enricher(cfg: NlpSettings) -> Enricher:
    engine = build_engine(cfg.model_dir, {"en": cfg.model_en, "vi": cfg.model_vi}, cfg.model_other,
                          cfg.auto_download, cfg.hf_endpoint, cfg.threads, cfg.max_len, cfg.vi_hybrid,
                          {"enabled": cfg.vi_cal, "cues": cfg.config_dir / "vi_cues.yaml",
                           "temperature": cfg.vi_cal_temp, "margin": cfg.vi_cal_margin})
    rules, prefix = entities.load(cfg.config_dir / "entities.yaml")
    return Enricher(engine, rules, prefix, topics.load(cfg.config_dir / "topics.yaml"), cfg.summary, cfg.summary_min_chars)


class AnalyzeIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=5000)
    lang: str | None = None
    source: str = "adhoc"


def create_app(cfg: NlpSettings | None = None, bus: Bus | None = None, start_worker: bool = True,
               enricher_factory=None):
    cfg = cfg or NlpSettings()
    app = make_app("nlp", internal_auth=True)
    bus = bus or Bus.from_url(cfg.base.redis_url)
    worker = NlpWorker(cfg, bus, enricher_factory or (lambda: build_enricher(cfg)))
    app.state.worker = worker

    @asynccontextmanager
    async def lifespan(_app):
        if start_worker and cfg.base.enabled:
            await worker.start()
        yield
        await worker.stop()

    app.router.lifespan_context = lifespan

    @app.get("/status")
    async def status():
        e = worker.enricher
        return {"ready": worker.ready, "processed": worker.processed, "queue": worker.queue.qsize(),
                "models": e.engine.loaded if e else {}, "group": cfg.group, "consumer": cfg.consumer}

    @app.get("/v1/sentiment")
    async def sentiment(symbol: str | None = None):
        """Sentiment trung bình theo symbol (1h/24h), đọc từ bộ nhớ. Chỉ đọc."""
        snap = worker.agg.snapshot(worker.clock())
        if symbol:
            if symbol not in snap:
                raise HTTPException(404, "chưa có dữ liệu cho symbol")
            return {symbol: snap[symbol]}
        return snap

    @app.post("/v1/analyze")
    async def analyze(body: AnalyzeIn):
        """Phân tích thử 1 tiêu đề (không ghi stream). Nội dung là DỮ LIỆU, không bao giờ được thực thi."""
        import asyncio

        if worker.enricher is None:
            raise HTTPException(503, "model đang nạp")
        p = {"url": "adhoc://x", "title": body.title, "summary": body.summary, "lang": body.lang, "source": body.source}
        return (await asyncio.to_thread(worker.enricher.enrich_batch, [p]))[0]

    return app
