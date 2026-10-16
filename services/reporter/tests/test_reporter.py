from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import NOW, XSS, make_gateway
from reporter import notify
from reporter.app import create_app
from reporter.build import build
from reporter.collect import collect
from reporter.render import render_html, render_pdf
from reporter.scheduler import due, last_slot, loop
from reporter.service import Reporter
from reporter.store import Store, valid_name


async def _html(cfg, kind="daily", **kw):
    raw = await collect(cfg, kind, NOW, make_gateway(cfg, **kw))
    ctx = build(kind, "2026-10-12", raw, cfg, NOW)
    return ctx, render_html(ctx)


async def test_daily_html_sections_and_vietnamese(cfg):
    ctx, html = await _html(cfg)
    for s in ("Tổng quan thị trường", "Lịch sự kiện", "Tin quan trọng", "Đồng thuận tín hiệu chuyên gia", "Tài khoản MT", "Hiệu suất mô phỏng",
              "Sức khoẻ hệ thống", "Tóm tắt 5 dòng", "READ-ONLY", "Chỉ đọc / mô phỏng, không phải lời khuyên đầu tư",
              "Tham khảo - không phải khuyến nghị", "Chưa có tài khoản MT hoạt động", "<svg", "NGAY-2026-10-12"):
        assert s in html, s
    assert len(ctx["summary"]) == 5
    assert "UTC" in html and "giờ VN" in html
    assert "acc1" in html and "old" not in ctx["sections"]["paper"]["rows"][0]["id"]   # tài khoản ngừng dùng bị loại
    assert "Sự cố &lt;b&gt;nặng&lt;/b&gt;" in html and "quá cũ" not in html            # chỉ cảnh báo trong kỳ + escape
    assert "mt-bridge" in html                                                          # service ngừng được nêu


async def test_html_escapes_news_title_xss(cfg):
    _, html = await _html(cfg)
    assert "<script>" not in html and "&lt;script&gt;" in html


async def test_failed_sources_give_nodata_but_report_renders(cfg):
    ctx, html = await _html(cfg, fail={"/v1/news", "/v1/calendar", "/v1/system", "/v1/data-sources", "/v1/alerts", "/v1/paper"})
    assert "Chưa có dữ liệu" in html
    assert {"news", "calendar", "system", "paper"} <= set(ctx["fail"])
    assert "market" in ctx["ok"] and "Tổng quan thị trường" in html


async def test_risk_endpoint_missing_is_graceful_and_present_is_used(cfg):
    ctx, html = await _html(cfg, "weekly")
    assert "Rủi ro &amp; stress nổi bật" in html and "risk" in ctx["fail"] and "/v1/risk/accounts chưa khả dụng" in html
    risk = {"accounts": [{"account_id": "demo-mt5-01", "kind": "mt", "platform": "mt5", "currency": "USD", "equity": 5000, "margin_level": 420,
                          "leverage_effective": 3.1, "day_pnl_pct": -0.5, "dd_from_peak_pct": -2.0, "var95_1d_pct": 1.4, "es975_1d_pct": 2.0,
                          "worst_stress": {"name": "USD +3%", "pnl_pct": -6.2}, "budget_status": "warn", "warnings": ["Đòn bẩy cao"], "stale": False}]}
    ctx, html = await _html(cfg, "weekly", overrides={"/v1/risk/accounts": risk})
    assert "risk" in ctx["ok"] and "demo-mt5-01" in html and "USD +3%" in html and "Đòn bẩy cao" in html
    assert "Lịch tuần tới" in html


async def test_pdf_real_with_vietnamese_text(cfg):
    pypdf = pytest.importorskip("pypdf")
    _, html = await _html(cfg)
    try:
        pdf = render_pdf(html)
    except OSError as e:  # thiếu pango/harfbuzz trong container test trần (image reporter thật có đủ: libpango, fonts-dejavu)
        pytest.skip(f"thiếu thư viện hệ thống cho WeasyPrint: {e}")
    assert pdf.startswith(b"%PDF")
    rd = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(rd.pages) >= 1
    txt = "".join(p.extract_text() or "" for p in rd.pages)
    assert "Tổng quan thị trường" in txt or "Tong quan thi truong" in txt.lower() or "quan" in txt
    assert any(ch in txt for ch in "ổưệạằ"), "PDF mất dấu tiếng Việt"


async def test_idempotent_force_and_index(cfg):
    calls = []

    def fake_pdf(html):
        calls.append(1)
        return b"%PDF-1.7 fake"
    rep = Reporter(cfg, gateway=make_gateway(cfg), pdf=fake_pdf, clock=lambda: NOW)
    e1 = await rep.generate("daily", "2026-10-12")
    assert e1["status"] in ("ok", "degraded") and not e1.get("skipped")
    e2 = await rep.generate("daily", "2026-10-12")
    assert e2.get("skipped") and len(calls) == 1
    await rep.generate("daily", "2026-10-12", force=True)
    assert len(calls) == 2
    idx = rep.store.load()["items"]
    assert len(idx) == 1 and idx[0]["sha256"] and idx[0]["bytes"] > 1000 and idx[0]["sections_ok"]
    assert (cfg.reports_dir / "daily" / "2026-10-12.html").is_file() and (cfg.reports_dir / "index.json").is_file()


async def test_pdf_failure_still_saves_html_degraded(cfg):
    def boom(html):
        raise RuntimeError("pdf")
    rep = Reporter(cfg, gateway=make_gateway(cfg), pdf=boom, clock=lambda: NOW)
    e = await rep.generate("weekly", "2026-10-11")
    assert e["status"] == "degraded" and e["pdf_bytes"] == 0 and "pdf" in e["sections_fail"]


def test_retention_prunes_old(cfg, tmp_path):
    st = Store(tmp_path / "r", keep_daily=3, keep_weekly=2)
    for d in range(1, 7):
        st.save("daily", f"2026-10-0{d}", "<html></html>", b"%PDF", ["market"], [])
    items = [i["period"] for i in st.items() if i["kind"] == "daily"]
    assert items == ["2026-10-06", "2026-10-05", "2026-10-04"]
    assert not (tmp_path / "r" / "daily" / "2026-10-01.html").exists()


async def test_notification_payload_published(cfg):
    import fakeredis.aioredis as fr
    from tscommon import Bus
    bus = Bus(fr.FakeRedis(decode_responses=True))
    rep = Reporter(cfg, gateway=make_gateway(cfg), bus=bus, pdf=lambda h: b"%PDF", clock=lambda: NOW)
    await rep.generate("daily", "2026-10-12")
    msgs = await bus.r.xrange("alerts.out")
    assert len(msgs) == 1
    import json
    p = json.loads(msgs[0][1]["e"])["payload"]
    assert p["level"] == "info" and p["title"] == "Báo cáo ngày 2026-10-12 đã sẵn sàng" and p["tags"] == ["report", "daily"]
    assert p["dedupe_key"] == "report:daily:2026-10-12" and "#/bao-cao" in p["body"]
    assert notify.alert_payload("weekly", "2026-10-11", ["a"], "https://x.y", False)["body"].endswith("https://x.y/#/bao-cao")


# ---------- lịch ----------
def vn(y, m, d, h, mi):
    from zoneinfo import ZoneInfo
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")).astimezone(timezone.utc)


def test_scheduler_picks_right_slot(cfg):
    # Thứ Hai 12/10/2026 06:29 VN -> chưa tới 06:30: kỳ ngày vẫn là 11/10; tuần = Chủ nhật 11/10 19:00 chưa tới -> 04/10
    assert last_slot("daily", vn(2026, 10, 12, 6, 29), cfg)[0] == "2026-10-11"
    assert last_slot("daily", vn(2026, 10, 12, 6, 30), cfg)[0] == "2026-10-12"
    assert last_slot("weekly", vn(2026, 10, 11, 18, 59), cfg)[0] == "2026-10-04"
    assert last_slot("weekly", vn(2026, 10, 11, 19, 0), cfg)[0] == "2026-10-11"
    assert last_slot("weekly", vn(2026, 10, 14, 10, 0), cfg)[0] == "2026-10-11"      # chạy bù giữa tuần
    done = {("daily", "2026-10-12")}
    assert due(vn(2026, 10, 12, 9, 0), cfg, lambda k, p: (k, p) in done) == [("weekly", "2026-10-11")]   # khởi động muộn: bù báo cáo tuần
    assert due(vn(2026, 10, 12, 9, 0), cfg, lambda k, p: True) == []
    assert last_slot("daily", datetime(2026, 10, 11, 23, 45, tzinfo=timezone.utc), cfg)[0] == "2026-10-12"   # 06:45 VN ngày 12


async def test_loop_runs_due_once_and_retries_throttled(cfg):
    now = vn(2026, 10, 12, 7, 0)
    ran, stop = [], asyncio.Event()

    async def gen(kind, period):
        ran.append((kind, period))
        if len(ran) >= 3:
            stop.set()
    t = asyncio.create_task(loop(cfg, gen, lambda k, p: False, stop, clock=lambda: now))
    await asyncio.wait_for(asyncio.sleep(0.15), 1)
    stop.set()
    await t
    assert sorted(set(ran)) == [("daily", "2026-10-12"), ("weekly", "2026-10-11")]
    assert len(ran) == 2        # không lặp lại trong 30 phút dù vòng lặp quay nhiều lần


# ---------- API + chống traversal ----------
def test_valid_name_regex():
    assert valid_name("daily", "2026-10-12", "pdf") and valid_name("weekly", "2026-10-11", "html")
    for bad in [("monthly", "2026-10-12", "pdf"), ("daily", "../2026-10-12", "pdf"), ("daily", "2026-10-12", "exe"),
                ("daily/..", "2026-10-12", "html"), ("daily", "2026-10-12\n", "html"), ("daily", "2026-10-1", "html"), ("daily", "", "html")]:
        assert not valid_name(*bad), bad


def test_api_list_download_and_traversal(cfg):
    rep = Reporter(cfg, gateway=make_gateway(cfg), pdf=lambda h: b"%PDF-1.7 fake", clock=lambda: NOW)
    asyncio.run(rep.generate("daily", "2026-10-12"))
    secret = cfg.data_dir / "secret.txt"
    secret.write_text("s")
    with TestClient(create_app(cfg, rep, run_scheduler=False)) as c:
        j = c.get("/reports").json()
        assert j["read_only"] and j["items"][0]["period"] == "2026-10-12" and "daily" in j["next_runs"]
        h = c.get("/reports/daily/2026-10-12.html")
        assert h.status_code == 200 and h.headers["content-type"].startswith("text/html") and "READ-ONLY" in h.text
        p = c.get("/reports/daily/2026-10-12.pdf")
        assert p.status_code == 200 and p.content.startswith(b"%PDF") and "attachment" in p.headers["content-disposition"]
        for bad in ["/reports/daily/..%2f..%2fsecret.txt", "/reports/daily/2026-10-13.html", "/reports/daily/2026-10-12.txt",
                    "/reports/weekly/2026-10-12.html", "/reports/daily/..%2Fsecret.txt", "/reports/../secret.txt"]:
            assert c.get(bad).status_code == 404, bad
        assert c.get("/healthz").status_code == 200 and "reporter_reports_total" in c.get("/metrics").text
        r = c.post("/generate?kind=daily&force=1")
        assert r.status_code == 200 and c.post("/generate?kind=monthly").status_code == 422


async def test_weekly_journal_section_uses_review_and_skips_sim(cfg):
    ctx, html = await _html(cfg, "weekly")  # khong co /v1/journal/* trong fixture -> muc loi nhung bao cao van render
    assert "journal" in ctx["fail"] and "Nhật ký giao dịch" in html
    review = {"week": "2026-W41", "summary": {"n": 12, "net": 84.5, "win_rate": 0.58, "profit_factor": 1.4, "expectancy": 7.04, "avg_r": 0.31},
              "delta": {"net": -20.0}, "streaks": {"max_loss_streak": 3},
              "discipline": {"score": 75.0, "n_flagged": 3, "net_flagged": -40.0, "net_clean": 124.5,
                             "rules": [{"rule": "no_sl", "label": "Vào lệnh không đặt SL", "count": 3, "net": -40.0}, {"rule": "x", "label": "y", "count": 0, "net": 0}]},
              "insights": ["Chuỗi thua dài nhất 3 lệnh <b>x</b>"]}
    jr = {"/v1/journal/accounts": {"items": [
        {"account_id": "demo-mt5-01", "kind": "mt", "n_trades": 12, "source": "mt5:demo-mt5-01"},
        {"account_id": "sim-journal", "kind": "mt", "n_trades": 181, "source": "sim:journal-fixture"},   # mo phong: khong dua vao bao cao
        {"account_id": "empty", "kind": "mt", "n_trades": 0}]},
        "/v1/journal/demo-mt5-01/review": review}
    ctx, html = await _html(cfg, "weekly", overrides=jr)
    assert "journal" in ctx["ok"] and "demo-mt5-01" in html and "75/100" in html and "+84.50" in html and "Tuần 2026-W4" in html
    assert "sim-journal" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert any("Nhật ký" in l for l in ctx["summary"])
    ctx, html = await _html(cfg, "daily")
    assert "journal" not in ctx["order"]  # chi bao cao tuan


async def test_daily_has_ai_briefing_section_without_source_names(cfg):
    ctx, html = await _html(cfg)
    assert "briefing" in ctx["order"] and ctx["sections"]["briefing"]["ok"]
    for s in ("Bản tin thị trường (AI tóm tắt)", "Bản tin sáng — Việt Nam", "VN-Index giảm về 1.730 điểm", "AI test-model", "không phải khuyến nghị đầu tư",
              "[2][1]", "Căn cứ: [1] VN-Index giảm 12,5 điểm"):
        assert s in html, s
    assert "&lt;b&gt;350&lt;/b&gt;" in html          # escape
    ctx2, html2 = await _html(cfg, fail={"/v1/briefing"})
    assert "briefing" in ctx2["fail"] and "Bản tin thị trường (AI tóm tắt)" in html2         # báo cáo vẫn dựng khi service briefing lỗi


async def test_weekly_has_no_briefing_section(cfg):
    ctx, _ = await _html(cfg, kind="weekly")
    assert "briefing" not in ctx["order"]


def test_series_gop_nguon_canon_va_nen_song():
    """Hồi quy ổn định hoá: gateway trả canon MT5 (đến hôm qua) + 1 nến sống hôm nay (source rỗng) -> báo cáo vẫn có giá FX, giá cuối = nến mới nhất."""
    from reporter.build import _series
    from reporter.collect import Raw

    def bar(d, c, src=None):
        r = {"ts_open": f"2026-10-{d:02d}T00:00:00Z", "c": c}
        if src:
            r["source"] = src
        return r
    rows = [bar(d, 1.10 + d / 1000, "canon:mt5:1") for d in range(1, 15)] + [bar(15, 1.12)]
    raw = Raw(data={"bars:EURUSD": {"items": list(reversed(rows))}})
    s = _series(raw, "EURUSD")
    assert s is not None
    bars, _src = s
    assert len(bars) == 15 and bars[-1]["c"] == 1.12 and bars[0]["ts_open"].startswith("2026-10-01")
