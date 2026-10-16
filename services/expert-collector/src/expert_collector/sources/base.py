from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ExpertInfo, OpinionInfo, PositionInfo, SignalInfo


class ExpertSource(ABC):
    """Plugin nguon chuyen gia. Moi nguon khai bao ten, muc rui ro ToS va canh bao."""

    name: str = ""
    tos_risk: str = "low"  # low|medium|high
    warning: str = ""
    supports_positions: bool = False

    @abstractmethod
    async def list_experts(self) -> list[ExpertInfo]: ...

    async def fetch_signals(self, expert: ExpertInfo) -> list[SignalInfo]:
        return []

    async def fetch_positions(self, expert: ExpertInfo) -> list[PositionInfo]:
        return []

    async def fetch_trades(self, expert: ExpertInfo) -> list[dict]:
        """Lenh da dong ({volume, profit}) de phat hien martingale. Mac dinh: khong co."""
        return []

    async def fetch_opinions(self, expert: ExpertInfo) -> list[OpinionInfo]:
        """Bai viet/y kien (tin tham khao co chuyen gia, chu de, xu huong). Mac dinh: khong co."""
        return []
