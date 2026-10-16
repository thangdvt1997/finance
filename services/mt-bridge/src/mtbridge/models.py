"""Mo hinh chuan hoa (khong phu thuoc MT4/MT5). READ-ONLY: khong co model lenh dat/sua/dong."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

Platform = Literal["mt4", "mt5"]
Side = Literal["buy", "sell"]
MarginMode = Literal["hedging", "netting", "unknown"]
Timeframe = Literal["M1", "M5", "M15", "H1", "H4", "D1"]
TIMEFRAMES: tuple[str, ...] = ("M1", "M5", "M15", "H1", "H4", "D1")
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(_M):
    """Vi the chuan hoa.

    - MT4: luon hedging, 1 ticket = 1 position.
    - MT5 hedging: 1 position ticket = 1 position.
    - MT5 netting: toi da 1 position / symbol (volume la tong rong). Dung `net_exposure()`
      de tinh exposure dung cho ca hai che do.
    """

    position_id: str
    symbol: str  # chuan hoa (EURUSD)
    broker_symbol: str
    side: Side
    volume: float  # lot, luon duong
    price_open: float
    price_current: float
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    magic: int = 0
    comment: str = ""
    time_open: datetime  # UTC


class PendingOrder(_M):
    order_id: str
    symbol: str
    broker_symbol: str
    kind: Literal["buy_limit", "sell_limit", "buy_stop", "sell_stop", "other"]
    volume: float
    price: float
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 0
    comment: str = ""
    time_setup: datetime  # UTC


class Deal(_M):
    """Giao dich DA DONG (lich su) chuan hoa. side=balance: thao tac so du (profit = so tien). Khoa: (account_id, ticket)."""

    account_id: str
    platform: Platform
    ticket: str
    position_id: str
    symbol: str  # chuan hoa; rong khi side=balance
    broker_symbol: str
    side: Literal["buy", "sell", "balance"]  # huong cua vi the da dong
    volume: float
    price_open: float
    price_close: float
    sl: float = 0.0
    tp: float = 0.0
    time_open: datetime  # UTC
    time_close: datetime  # UTC
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    magic: int = 0
    comment: str = ""
    reason: str = ""
    source: str = ""


class Account(_M):
    account_id: str
    platform: Platform
    login: int
    server: str = ""
    currency: str = ""
    leverage: int = 0
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: Optional[float] = None  # %, None khi margin == 0
    margin_mode: MarginMode = "unknown"
    ts: datetime  # UTC


class Quote(_M):
    symbol: str
    broker_symbol: str
    bid: float
    ask: float
    ts: datetime  # UTC
    source: str


class Bar(_M):
    symbol: str
    broker_symbol: str
    tf: Timeframe
    ts_open: datetime  # UTC
    o: float
    h: float
    l: float
    c: float
    v: float
    source: str


class GatewayHealth(_M):
    account_id: str
    platform: Platform
    connected: bool
    last_seen: Optional[datetime] = None
    detail: str = ""


def net_exposure(positions: list[Position]) -> dict[str, float]:
    """Exposure rong theo symbol (lot, buy duong / sell am) - dung chung cho hedging & netting."""
    out: dict[str, float] = {}
    for p in positions:
        out[p.symbol] = round(out.get(p.symbol, 0.0) + (p.volume if p.side == "buy" else -p.volume), 8)
    return out
