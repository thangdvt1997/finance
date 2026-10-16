"""BrokerGateway: giao dien CHI DOC.

Phase nay KHONG co phuong thuc ghi (dat/sua/dong lenh). Phuong thuc ghi (place_order(client_id),
modify, close) se duoc them o phase sau trong gateway/service rieng (`execution`), khong sua loi nay.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .models import Account, Bar, GatewayHealth, PendingOrder, Position, Quote


class BrokerGateway(ABC):
    account_id: str

    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_orders(self) -> list[PendingOrder]: ...

    @abstractmethod
    def get_rates(
        self, symbol: str, tf: str, count: int = 100, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> list[Bar]:
        """Nen DA DONG, tang dan theo ts_open (UTC). `symbol` la ten chuan hoa."""

    @abstractmethod
    def get_quotes(self, symbols: Optional[list[str]] = None) -> list[Quote]:
        """Gia moi nhat (bid/ask) cho cac symbol chuan hoa (None = tat ca dang theo doi)."""

    @abstractmethod
    def health(self) -> GatewayHealth: ...

    def get_ticks(self, symbol: str, since: datetime, count: int = 1000) -> list[Quote]:
        """Tick lich su (tuy chon; adapter khong ho tro thi tra rong)."""
        return []
