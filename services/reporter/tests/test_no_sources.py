"""UI_NO_SOURCES: bao cao ngay/tuan (HTML + PDF) khong chua ten nguon du lieu."""
from __future__ import annotations

import io
import re
from datetime import timedelta

import pytest

from conftest import NOW, make_gateway
from reporter.build import build
from reporter.collect import collect
from reporter.render import render_html, render_pdf

BANNED_WORDS = ("dukascopy", "yahoo", "frankfurter", "twelvedata", "twelve data", "cafef", "vietstock", "reuters", "actionforex",
                "forexfactory", "faireconomy", "myfxbook", "mql5", "oanda", "gdelt", "marketaux", "ccxt")
_T = lambda h: (NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
SRC_ALERTS = {"/v1/alerts": {"items": [
    {"id": 1, "ts": _T(2), "level": "warn", "title": "dukascopy lỗi lấy dữ liệu GBPUSD M1"},
    {"id": 2, "ts": _T(3), "level": "crit", "title": "Lech gia EURUSD: yahoo_daily vs dukascopy"}]}}


async def _html(cfg, kind="daily", **kw):
    raw = await collect(cfg, kind, NOW, make_gateway(cfg, **kw))
    ctx = build(kind, "2026-10-12", raw, cfg, NOW)
    return ctx, render_html(ctx)


@pytest.mark.parametrize("kind", ["daily", "weekly"])
async def test_report_html_has_no_source_names(cfg, kind):
    ctx, html = await _html(cfg, kind, overrides=SRC_ALERTS)
    low = html.lower()
    text = re.sub(r"<[^>]+>", " ", low)
    for w in BANNED_WORDS:
        assert w not in low, w
        assert w not in str(ctx).lower(), w
        assert w not in text, w
    assert "dữ liệu giá gbpusd m1: lỗi cập nhật" in low  # alert kỹ thuật được viết lại trung tính
    assert "<th>Nguồn</th>" not in html and "Nguồn dữ liệu thị trường" not in html
    assert "Trạng thái dữ liệu thị trường" in html


async def test_report_pdf_text_has_no_source_names(cfg):
    pypdf = pytest.importorskip("pypdf")
    _, html = await _html(cfg, overrides=SRC_ALERTS)
    try:
        pdf = render_pdf(html)
    except OSError as e:
        pytest.skip(f"thiếu thư viện hệ thống cho WeasyPrint: {e}")
    txt = "".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf)).pages).lower()
    assert txt
    for w in BANNED_WORDS:
        assert w not in txt, w


async def test_render_html_final_scrub_catches_leaks(cfg):
    ctx, _ = await _html(cfg)
    ctx["summary"] = ctx["summary"] + ["Nguồn: dukascopy, tin từ Reuters"]
    html = render_html(ctx)
    assert "dukascopy" not in html.lower() and "reuters" not in html.lower()
