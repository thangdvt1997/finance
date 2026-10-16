"""QA vong 4: /v1/news bo trung hien thi khi cung tieu de (chuan hoa) + cung ngay tu nhieu nguon (bao dang lai/ repost)."""
from datetime import datetime, timedelta, timezone

import pytest

from api_gateway.repo import InMemoryRepo

T = datetime(2026, 10, 14, 9, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_news_dedupe_same_title_same_day_prefers_news_source():
    rows = [
        {"url": "https://a.vn/1", "title": "Bán 6 lượng vàng, ...", "published_at": T + timedelta(hours=1), "source": "expert:op:vn_tp_economy", "symbols": []},
        {"url": "https://b.vn/1", "title": "bán 6 lượng vàng", "published_at": T + timedelta(hours=2), "source": "cafef_chungkhoan", "symbols": []},
        {"url": "https://c.vn/1", "title": "Bán 6 lượng vàng", "published_at": T - timedelta(days=1), "source": "cafef_chungkhoan", "symbols": []},
        {"url": "https://d.vn/1", "title": "Tin khác", "published_at": T, "source": "x", "symbols": []},
    ]
    r = InMemoryRepo(news_items=rows)
    got = await r.news(None, None, 10, 0)
    assert [x["url"] for x in got] == ["https://b.vn/1", "https://d.vn/1", "https://c.vn/1"]
