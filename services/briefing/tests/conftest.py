from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from briefing.config import Settings
from briefing.llm import LLMResult

UTC = timezone.utc
NOW = datetime.now(UTC).replace(second=0, microsecond=0)   # dữ liệu giả tính tương đối so với bây giờ (API test dùng đồng hồ thật)


def mk_news(i: int, title: str, summary: str = "", *, hours_ago: float = 3, lang: str = "vi", symbols=("VN:VNINDEX",), sentiment: float = 0.1,
            importance: str = "med", label: str | None = None) -> dict:
    return {"url": f"https://example.test/bai-{i}", "title": title, "summary": summary, "ts": NOW - timedelta(hours=hours_ago), "lang": lang,
            "symbols": list(symbols), "sentiment": sentiment, "sentiment_label": label, "importance": importance}


def vn_news() -> list[dict]:
    return [
        mk_news(1, "VN-Index giảm 12,5 điểm xuống 1.730 điểm, thanh khoản thấp hơn phiên trước", "Nhóm ngân hàng chịu áp lực bán trong phiên chiều.",
                sentiment=-0.45, importance="high", label="negative"),
        mk_news(2, "Khối ngoại bán ròng 350 tỷ đồng trên sàn HOSE", "Cổ phiếu VNM và FPT bị bán ròng nhiều nhất.", symbols=("VN:VNM", "VN:FPT"),
                sentiment=-0.3, importance="high", label="negative"),
        mk_news(3, "Ngân hàng Nhà nước giữ nguyên lãi suất điều hành", "Quyết định được công bố sáng nay.", sentiment=0.7, importance="med", label="positive"),
        mk_news(4, "Xuất khẩu dệt may 9 tháng đạt 30 tỷ USD", "Tăng so với cùng kỳ năm trước.", symbols=("VN:VNINDEX",), sentiment=0.6, importance="med", label="positive"),
        mk_news(5, "Giá vàng trong nước đi ngang quanh mốc 120 triệu đồng mỗi lượng", "", symbols=("XAUUSD",), sentiment=0.0, importance="low", label="neutral"),
        mk_news(6, "Doanh nghiệp bất động sản đẩy mạnh phát hành trái phiếu", "Lãi suất trái phiếu dao động 9 phần trăm.", sentiment=-0.1, importance="med"),
    ]


def intl_news() -> list[dict]:
    return [
        mk_news(11, "Oil edges lower as US Treasuries stay closed for holiday", "Brent crude fell 0.4% in thin trade.", lang="en", symbols=("USOIL",),
                sentiment=-0.3, importance="high"),
        mk_news(12, "Fed officials signal patience on rate cuts", "Several policymakers said inflation remains above target.", lang="en", symbols=("USDJPY",),
                sentiment=-0.2, importance="high"),
        mk_news(13, "Bitcoin steady near 62000 dollars as ETF inflows slow", "", lang="en", symbols=("CRYPTO:BTCUSDT",), sentiment=0.1, importance="med"),
        mk_news(14, "Euro zone industrial output beats expectations", "", lang="en", symbols=("EURUSD",), sentiment=0.5, importance="med"),
    ]


def cal_rows() -> list[dict]:
    return [{"event_id": "e1", "country": "US", "title": "CPI y/y", "impact": "high", "ts": NOW + timedelta(hours=7), "forecast": "3.1", "previous": "3.0", "actual": None}]


@pytest.fixture
def cfg() -> Settings:
    return Settings(database_url="", db_rw_url="", redis_url="", llm_model="test-model", admin_token="tok", min_points=3, max_points=8)


def find_n(messages, sub: str) -> int:
    """Số thứ tự [n] của mục ngữ cảnh có chứa chuỗi `sub` (đọc từ prompt thật gửi cho LLM)."""
    import re
    for m in re.finditer(r"^\[(\d+)\] (.*)$", messages[1]["content"], re.M):
        if sub in m.group(2):
            return int(m.group(1))
    raise AssertionError(f"không thấy mục chứa {sub!r}")


def make_out(headline: str, pts: list[tuple[str, str]]):
    """Dựng đầu ra LLM giả: mỗi phần tử (văn bản, chuỗi-nhận-diện-mục-trích-dẫn); cites tính theo prompt thật."""
    import json

    def f(messages):
        return json.dumps({"headline": headline, "points": [{"text": t, "cites": [find_n(messages, sub)]} for t, sub in pts]}, ensure_ascii=False)
    return f


class FakeLLM:
    def __init__(self, content=None, exc: Exception | None = None):
        self.content, self.exc, self.calls = content, exc, []

    async def complete(self, messages, schema, max_tokens):
        self.calls.append((messages, schema, max_tokens))
        if self.exc:
            raise self.exc
        content = self.content(messages) if callable(self.content) else self.content
        return LLMResult(content=content or "", prompt_tokens=100, completion_tokens=50, latency_ms=1234, prompt_tps=40.0, gen_tps=5.5, model="fake")
