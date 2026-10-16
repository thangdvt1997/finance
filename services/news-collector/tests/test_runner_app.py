from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from conftest import NOW, fx
from news_collector.app import build_sources, create_app
from news_collector.models import Emit
from news_collector.runner import Runner
from news_collector.settings import NewsSettings
from news_collector.sources.base import Source
from news_collector.sources.calendar_sources import parse_faireconomy


class StubSource(Source):
    name = "stub"

    def __init__(self, emits):
        self.emits = emits

    async def fetch(self, ctx):
        return self.emits


class BoomSource(Source):
    name = "boom"

    async def fetch(self, ctx):
        raise RuntimeError("x")


async def stream_len(bus, stream):
    return await bus.r.xlen(stream)


async def test_publish_dedupes_by_url(bus, make_ctx):
    e = Emit("news", "news", {"url": "u1", "title": "t"}, "news:u1")
    src = StubSource([e, Emit("news", "news", {"url": "u1", "title": "t"}, "news:u1"),
                      Emit("news", "news", {"url": "u2", "title": "t"}, "news:u2")])
    r = Runner(bus, make_ctx(lambda q: httpx.Response(200)), [src])
    assert await r.run_once(src) == 2
    assert await r.run_once(src) == 0  # lan 2 toan trung
    assert await stream_len(bus, "news.items") == 2
    msg = (await bus.r.xrange("news.items"))[0][1]["e"]
    assert '"type":"news"' in msg and '"source":"news-collector"' in msg


async def test_error_isolated_and_recorded(bus, make_ctx):
    boom = BoomSource()
    r = Runner(bus, make_ctx(lambda q: httpx.Response(200)), [boom])
    assert await r.run_once(boom) == 0
    assert "RuntimeError" in r.status["boom"]["last_error"]


async def test_alert_pipeline_publishes_once(bus, make_ctx):
    emits = parse_faireconomy(fx("ff_week.json"))
    nfp_ts = datetime.fromisoformat(emits[0].payload["ts"])
    now = [nfp_ts - timedelta(minutes=20)]
    ctx = make_ctx(lambda q: httpx.Response(200))
    ctx.now = lambda: now[0]
    src = StubSource(emits)
    src.name = "stub"
    r = Runner(bus, ctx, [src])
    await r.run_once(src)
    assert await stream_len(bus, "calendar.events") == 3
    assert await r.check_alerts() == 1
    assert await r.check_alerts() == 0  # dedupe_key: khong lap
    assert await stream_len(bus, "alerts.out") == 1
    # su kien qua han bi don khoi cache
    now[0] = nfp_ts + timedelta(hours=1)
    await r.check_alerts()
    assert all(datetime.fromisoformat(v["ts"]) >= now[0] for v in r.calendar_cache.values())


async def test_calendar_actual_update_republished(bus, make_ctx):
    import json
    rows = json.loads(fx("ff_week.json"))
    r = Runner(bus, make_ctx(lambda q: httpx.Response(200)), [StubSource([])])
    await r.publish("t", parse_faireconomy(json.dumps(rows).encode()))
    rows[2]["actual"] = "2.3%"
    n = await r.publish("t", parse_faireconomy(json.dumps(rows).encode()))
    assert n == 1


def test_source_toggles_by_env(monkeypatch):
    monkeypatch.setenv("NC_SRC_RSS", "false")
    monkeypatch.setenv("NC_SRC_GDELT", "0")
    monkeypatch.setenv("NC_SRC_COT", "false")
    names = [s.name for s in build_sources(NewsSettings())]
    # FF (nguoi dung dong y, ca nhan) + actuals BAT mac dinh; FMP + 13F mac dinh TAT
    assert names == ["cal_official", "cal_central_banks", "cal_faireconomy", "cal_actuals"]
    monkeypatch.setenv("NC_SRC_CAL_FAIRECONOMY", "false")
    monkeypatch.setenv("NC_SRC_CAL_ACTUALS", "false")
    monkeypatch.setenv("NC_SRC_SEC13F", "true")
    names = {s.name for s in build_sources(NewsSettings())}
    assert "sec13f" in names and not {"cal_faireconomy", "cal_actuals"} & names


def test_defaults_ff_on_13f_fmp_off(monkeypatch):
    for k in ("NC_SRC_CAL_FAIRECONOMY", "NC_SRC_SEC13F", "NC_SRC_CAL_FMP", "NC_SRC_CAL_ACTUALS", "NC_RISK_ALERTS"):
        monkeypatch.delenv(k, raising=False)
    s = NewsSettings()
    assert s.src_cal_faireconomy is True and s.src_cal_actuals is True and s.risk_enabled is True
    assert s.src_sec13f is False and s.src_cal_fmp is False


def test_http_endpoints(bus):
    app = create_app(NewsSettings(), bus=bus, start_runner=False)
    with TestClient(app) as c:
        assert c.get("/healthz").json()["status"] == "ok"
        assert "nc_items_published_total" in c.get("/metrics").text or c.get("/metrics").status_code == 200
        assert "sources" in c.get("/status").json()
