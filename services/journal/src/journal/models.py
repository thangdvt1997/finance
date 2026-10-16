"""Mo hinh noi bo cua journal. READ-ONLY: Trade chi mo ta giao dich DA DONG (lich su)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass
class Trade:
    """1 giao dich da dong (hoac thao tac so du khi kind='balance'). Tien theo tien te tai khoan."""

    ticket: str
    kind: str  # trade | balance
    symbol: str
    side: str  # buy | sell | balance
    volume: float
    price_open: float
    price_close: float
    time_open: datetime  # UTC
    time_close: datetime  # UTC
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0  # am = chi phi (quy uoc MT)
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 0
    group: str = ""  # nhan EA/chien luoc: "magic:7" | "manual" | ten chien luoc paper
    comment: str = ""
    reason: str = ""
    source: str = ""
    position_id: str = ""
    spread_cost: Optional[float] = None  # chi paper (da nam trong gia khop)
    slippage_cost: Optional[float] = None

    @property
    def net(self) -> float:
        return self.profit + self.swap + self.commission

    @property
    def hold_s(self) -> float:
        return max(0.0, (self.time_close - self.time_open).total_seconds())

    @property
    def sign(self) -> int:
        return 1 if self.side == "buy" else -1

    @property
    def risk_dist(self) -> Optional[float]:
        """Khoang cach gia vao -> SL ban dau (dung cho R-multiple theo gia). None khi khong co SL hop le."""
        if self.kind != "trade" or self.sl <= 0 or self.price_open <= 0:
            return None
        d = abs(self.price_open - self.sl)
        return d if d > 0 else None

    @property
    def r_multiple(self) -> Optional[float]:
        """R theo GIA (gross, chua tinh phi): (gia_dong - gia_vao) * huong / |gia_vao - SL|."""
        d = self.risk_dist
        if d is None or self.price_close <= 0:
            return None
        return self.sign * (self.price_close - self.price_open) / d


def group_label(magic: int) -> str:
    return "manual" if magic == 0 else f"magic:{magic}"


TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_:.\-]{0,31}$")
KINDS = ("deal", "week", "day")
REF_RE = {"deal": re.compile(r"^[A-Za-z0-9_\-]{1,40}$"), "week": re.compile(r"^\d{4}-W\d{2}$"), "day": re.compile(r"^\d{4}-\d{2}-\d{2}$")}


class NoteIn(BaseModel):
    """Ghi chu/tag thu cong (ghi duy nhat vao journal_notes)."""

    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field(default_factory=list, max_length=12)
    note: str = Field(default="", max_length=4000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = t.strip().lower()
            if not TAG_RE.match(t):
                raise ValueError(f"tag không hợp lệ: {t!r} (a-z 0-9 _ : . -, tối đa 32 ký tự)")
            if t not in out:
                out.append(t)
        return out

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        return "".join(ch for ch in v if ch == "\n" or ch == "\t" or ord(ch) >= 32)
