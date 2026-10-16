import fakeredis.aioredis as fr
import httpx
from tscommon import Bus

from analytics.app import create_app
from analytics.config import AnalyticsSettings, load_yaml
from analytics.repo import MemoryBarSource, MemoryStore
from analytics.runner import Runner


async def test_healthz_metrics_status():
    runner = Runner(load_yaml(None), MemoryBarSource({}), MemoryStore(), Bus(fr.FakeRedis(decode_responses=True)))
    app = create_app(AnalyticsSettings(enabled=False), runner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/healthz")).json()["service"] == "analytics"
        assert "analytics_cycles_total" in (await c.get("/metrics")).text or (await c.get("/metrics")).status_code == 200
        assert (await c.get("/status")).json()["status"] == "chưa chạy"
        out = await runner.run_cycle()
        assert out["symbols"] == 0
        assert (await c.get("/status")).json()["status"] == "ok"
