from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    count: int


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Bar(_Row):
    symbol: str
    tf: str
    ts_open: datetime
    o: float
    h: float
    l: float
    c: float
    v: float | None = 0
    source: str


class Quote(_Row):
    symbol: str
    ts: datetime
    bid: float | None = None
    ask: float | None = None
    source: str


class NewsItem(_Row):
    url: str
    title: str
    summary: str | None = None
    published_at: datetime | None = None
    source: str
    lang: str | None = None
    symbols: list[str] = []
    sentiment: float | None = None


class CalendarEvent(_Row):
    event_id: str
    source: str
    country: str | None = None
    title: str
    impact: str | None = None
    ts: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    extra: dict[str, Any] | None = None   # group, forecast_source/actual_source, surprise{value,z,direction,verdict} (news-collector)


class Expert(_Row):
    expert_id: str
    source: str
    display_name: str | None = None
    url: str | None = None
    reputation: dict[str, Any] = {}
    tracked: bool = True


class ExpertSignal(_Row):
    expert_id: str
    source: str
    symbol: str
    side: str
    opened_at: datetime
    entry: float | None = None
    sl: float | None = None
    tp: float | None = None
    status: str | None = "open"
    url: str | None = None


class ExpertOpinion(_Row):
    """Y kien chuyen gia/to chuc (tham khao, KHONG phai khuyen nghi)."""
    url: str
    expert_id: str
    name: str | None = None
    grp: str | None = None
    title: str
    stance: str | None = None
    stance_score: float | None = None
    topics: list[str] = []
    symbols: list[str] = []
    credibility: float | None = None
    published_at: datetime | None = None
    lang: str | None = None


class ExpertPosition(_Row):
    expert_id: str
    source: str
    symbol: str
    as_of: datetime
    net_volume: float | None = None
    avg_price: float | None = None


class AccountSnapshot(_Row):
    account_id: str
    platform: str
    ts: datetime
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    positions: list[Any] = []
    currency: str | None = None        # tiền tệ tài khoản (USD/EUR/...): UI KHÔNG cộng gộp tài khoản khác tiền tệ
    orders: list[Any] = []             # lệnh chờ đang mở (order_id, symbol, kind, volume, price, sl, tp, time_setup)


class AccountOrder(_Row):
    order_id: str
    symbol: str = ""
    kind: str = "other"
    volume: float | None = None
    price: float | None = None
    sl: float | None = None
    tp: float | None = None
    magic: int | None = None
    comment: str | None = None
    time_setup: datetime | None = None
    status: str = "open"
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    removed_at: datetime | None = None


class AlertRow(_Row):
    id: int
    ts: datetime
    level: str
    title: str
    body: str | None = None
    tags: list[str] = []
    dedupe_key: str | None = None
    delivered: bool = False


class Overview(BaseModel):
    generated_at: datetime
    quotes: list[Quote]
    news: list[NewsItem]
    upcoming_events: list[CalendarEvent]
    expert_signals: list[ExpertSignal]
    accounts: list[AccountSnapshot]


class SymbolInfo(_Row):
    symbol: str
    tfs: list[str] = []
    last_bar: datetime | None = None
    last_quote: datetime | None = None


class EquityPoint(_Row):
    ts: datetime
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None


class ServiceStatus(BaseModel):
    name: str
    up: bool | None = None  # None = không rõ (không có nguồn)
    last_scrape: datetime | None = None
    detail: str | None = None


class StreamStatus(BaseModel):
    stream: str
    length: int | None = None
    last_event_at: datetime | None = None
    lag_seconds: float | None = None


class SourceFreshness(BaseModel):
    name: str
    last_ts: datetime | None = None
    count_24h: int = 0
    age_seconds: float | None = None


class SystemStatus(BaseModel):
    generated_at: datetime
    services_source: str  # prometheus | redis | none
    services: list[ServiceStatus]
    streams: list[StreamStatus]
    sources: list[SourceFreshness]
    ws_connections: int
    version: str
