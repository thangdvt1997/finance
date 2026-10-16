from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest
from conftest import NOW, FakeLLM, cal_rows, intl_news, make_out, vn_news
from fastapi.testclient import TestClient

from briefing.app import Runner, create_app, next_fire, parse_schedule
from briefing.source import MemSource
from briefing.store import MemStore
from tscommon import Bus
from tscommon.sources import has_source_name

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def llm_ok():
    return FakeLLM(make_out("VN-Index giảm về 1.730 điểm, khối ngoại bán ròng", [
        ("VN-Index giảm 12,5 điểm xuống 1.730 điểm, nhóm ngân hàng chịu áp lực bán.", "VN-Index giảm 12,5"),
        ("Khối ngoại bán ròng 350 tỷ đồng trên sàn HOSE, nhiều nhất ở VNM và FPT.", "Khối ngoại bán ròng"),
        ("Ngân hàng Nhà nước giữ nguyên lãi suất điều hành.", "Ngân hàng Nhà nước giữ"),
        ("Xuất khẩu dệt may 9 tháng đạt 30 tỷ USD, tăng so với cùng kỳ năm trước.", "dệt may")]))


def test_schedule_parse_and_next_fire():
    s = parse_schedule("06:15=morning,16:30=close")
    assert s == [(6, 15, "morning"), (16, 30, "close")]
    t, ed = next_fire(datetime(2026, 10, 12, 22, 0, tzinfo=timezone.utc), s, TZ)      # 05:00 VN ngày 13
    assert (t.astimezone(TZ).strftime("%H:%M %d"), ed) == ("06:15 13", "morning")
    t, ed = next_fire(datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc), s, TZ)       # 09:00 VN
    assert (t.astimezone(TZ).strftime("%H:%M %d"), ed) == ("16:30 13", "close")
    t, ed = next_fire(datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc), s, TZ)      # 17:00 VN -> sáng mai
    assert (t.astimezone(TZ).strftime("%H:%M %d"), ed) == ("06:15 14", "morning")
    with pytest.raises(ValueError):
        parse_schedule("06:15=evening")


def make_client(cfg, llm=None, bus=None):
    src = MemSource(news=vn_news() + intl_news(), calendar=cal_rows())
    store = MemStore()
    app = create_app(cfg, src, store, llm or llm_ok(), bus, start_scheduler=False)
    return TestClient(app), store


def test_api_run_requires_token_and_serves_readonly(cfg):
    c, store = make_client(cfg)
    with c:
        assert c.post("/internal/run?edition=morning&scope=vn").status_code == 403
        assert c.post("/internal/run?edition=morning&scope=vn", headers={"X-Admin-Token": "sai"}).status_code == 403
        assert c.post("/internal/run?edition=bad", headers={"X-Admin-Token": "tok"}).status_code == 422
        r = c.post("/internal/run?edition=morning&scope=vn&wait=true", headers={"X-Admin-Token": "tok"})
        assert r.status_code == 202 and r.json()["statuses"] == ["llm"]
        bid = r.json()["ids"][0]
        lat = c.get("/briefing/latest?edition=morning&scope=vn").json()
        assert lat["id"] == bid and lat["status"] == "llm" and lat["model"] == "test-model" and lat["body"]["points"] and lat["context"]["items"]
        assert c.get("/briefing/latest").json()["items"][0]["id"] == bid
        assert c.get("/briefing/latest?scope=intl").status_code == 404
        assert [x["id"] for x in c.get("/briefing/list").json()["items"]] == [bid]
        assert "body" not in c.get("/briefing/list").json()["items"][0]
        assert c.get(f"/briefing/{bid}").json()["title"].startswith("Bản tin sáng Việt Nam")
        assert c.get("/briefing/00000000-0000-0000-0000-000000000000").status_code == 404
        assert c.get("/briefing/khong-hop-le").status_code == 422
        # chỉ đọc: không có route ghi nào ngoài /internal/run
        assert c.post("/briefing/latest").status_code == 405 and c.delete(f"/briefing/{bid}").status_code == 405 and c.put(f"/briefing/{bid}").status_code == 405


def test_run_endpoint_disabled_without_admin_token(cfg):
    from dataclasses import replace
    c, _ = make_client(replace(cfg, admin_token=""))
    with c:
        assert c.post("/internal/run?edition=morning", headers={"X-Admin-Token": ""}).status_code == 503


async def test_runner_publishes_stream_and_ntfy_alert_without_source_names(cfg):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(r)
    store = MemStore()
    runner = Runner(cfg, MemSource(news=vn_news() + intl_news(), calendar=cal_rows()), store, llm_ok(), bus)
    b = await runner.run_one("vn", "morning", NOW)
    ev = await bus.consume_once("briefing.items", "t", "c")
    assert len(ev) == 1 and ev[0][1].payload["briefing_id"] == b["id"] and ev[0][1].payload["n_citations"] >= 4 and ev[0][1].type == "briefing"
    al = await bus.consume_once("alerts.out", "t", "c")
    p = al[0][1].payload
    assert p["level"] == "info" and "ch:ntfy" in p["tags"] and "briefing" in p["tags"] and p["dedupe_key"] == f"briefing:{b['id']}"
    assert "không phải khuyến nghị đầu tư" in p["body"] and not has_source_name(p["title"] + p["body"])
    assert await store.exists(b["for_date"], "morning", "vn")
    await r.aclose()


async def test_notify_off_publishes_only_stream(cfg):
    from dataclasses import replace
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(r)
    runner = Runner(replace(cfg, notify=False), MemSource(news=vn_news(), calendar=cal_rows()), MemStore(), llm_ok(), bus)
    await runner.run_one("vn", "close", NOW)
    assert await bus.consume_once("alerts.out", "t", "c") == []
    assert len(await bus.consume_once("briefing.items", "t", "c")) == 1
    await r.aclose()


async def test_run_failure_in_llm_still_stores_fallback_and_notifies(cfg):
    store = MemStore()
    runner = Runner(cfg, MemSource(news=vn_news(), calendar=cal_rows()), store, FakeLLM(exc=ConnectionError("llm chết")), None)
    b = await runner.run_one("vn", "morning", NOW)
    assert b["status"] == "fallback" and len(store.rows) == 1
