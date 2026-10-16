"""FakeMT5: gia lap module `MetaTrader5` (chi cac ham doc) de test khong can terminal that.

Hinh dang du lieu bam theo tai lieu MetaTrader5 (namedtuple/numpy rows); thoi gian = epoch
'gio server dong goi' giong that. Day la GIA LAP - chua doi chieu voi terminal that.
"""
from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timezone
from typing import Any, Optional

AccountInfo = namedtuple(
    "AccountInfo",
    "login trade_mode leverage trade_allowed margin_mode balance credit profit equity margin margin_free margin_level currency server name",
)
TradePosition = namedtuple(
    "TradePosition", "ticket time type magic identifier volume price_open sl tp price_current swap profit symbol comment"
)
TradeOrder = namedtuple(
    "TradeOrder", "ticket time_setup type state magic volume_initial volume_current price_open sl tp price_current symbol comment"
)
Tick = namedtuple("Tick", "time bid ask last volume time_msc")


class FakeMT5:
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15 = 1, 5, 15
    TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 16385, 16388, 16408
    COPY_TICKS_ALL = 3

    def __init__(self, *, account: Optional[AccountInfo] = None):
        self.account = account
        self.positions: list[TradePosition] = []
        self.orders: list[TradeOrder] = []
        self.rates: dict[tuple[str, int], list[dict]] = {}  # (symbol, tf_const) -> rows (dict: time open high low close tick_volume)
        self.ticks: dict[str, Tick] = {}
        self.initialized = False
        self.init_ok = True
        self.calls: list[str] = []  # nhat ky de test khang dinh KHONG co lenh ghi
        self._err = (1, "Success")

    # --- vong doi ---
    def initialize(self, **kw: Any) -> bool:
        self.calls.append("initialize")
        self.initialized = self.init_ok
        if not self.init_ok:
            self._err = (-6, "Authorization failed")
        return self.init_ok

    def shutdown(self) -> None:
        self.calls.append("shutdown")
        self.initialized = False

    def last_error(self):
        return self._err

    # --- doc ---
    def account_info(self):
        self.calls.append("account_info")
        return self.account if self.initialized else None

    def positions_get(self, **kw: Any):
        self.calls.append("positions_get")
        return tuple(self.positions) if self.initialized else None

    def orders_get(self, **kw: Any):
        self.calls.append("orders_get")
        return tuple(self.orders) if self.initialized else None

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        self.calls.append("symbol_select")
        return True

    def symbol_info_tick(self, symbol: str):
        self.calls.append("symbol_info_tick")
        return self.ticks.get(symbol)

    def copy_rates_from_pos(self, symbol: str, tf: int, start_pos: int, count: int):
        self.calls.append("copy_rates_from_pos")
        rows = self.rates.get((symbol, tf))
        if rows is None or not self.initialized:
            return None
        # start_pos=0 la nen moi nhat; tra theo thu tu tang dan thoi gian nhu that
        end = len(rows) - start_pos
        return rows[max(0, end - count): end]

    def copy_rates_range(self, symbol: str, tf: int, a: datetime, b: datetime):
        self.calls.append("copy_rates_range")
        rows = self.rates.get((symbol, tf))
        if rows is None or not self.initialized:
            return None
        ta = a.replace(tzinfo=timezone.utc).timestamp()
        tb = b.replace(tzinfo=timezone.utc).timestamp()
        return [r for r in rows if ta <= r["time"] <= tb]

    def copy_ticks_from(self, symbol: str, frm: datetime, count: int, flags: int):
        self.calls.append("copy_ticks_from")
        t = self.ticks.get(symbol)
        return [t] if t else []
