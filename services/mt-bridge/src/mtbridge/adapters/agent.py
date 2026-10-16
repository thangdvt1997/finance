"""Adapter 'agent': nhan du lieu do EA (MQL4 hoac MQL5) chu dong day toi bridge, giu trang thai moi nhat.

MT4 khong co package Python chinh hang -> day la duong duy nhat cho MT4. Cung dung duoc cho MT5
(vi du terminal chay tren Wine/VPS). EA KHONG nhan lenh; bridge khong gui gi nguoc lai.
Y tuong tham khao: darwinex/dwxconnect (EA <-> Python); o day dao chieu thanh outbound-only + HTTP.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..accounts import AccountConfig
from ..gateway import BrokerGateway
from ..models import TF_SECONDS, Account, Bar, Deal, GatewayHealth, PendingOrder, Position, Quote
from ..protocol import Batch

_ORDER_KINDS = {2: "buy_limit", 3: "sell_limit", 4: "buy_stop", 5: "sell_stop"}
MAX_BARS_PER_SERIES = 2000


@dataclass
class IngestResult:
    account: Optional[Account] = None
    positions: Optional[list[Position]] = None
    orders: Optional[list[PendingOrder]] = None
    quotes: list[Quote] = field(default_factory=list)
    bars: list[Bar] = field(default_factory=list)  # chi nen moi/doi so voi lan truoc (de publish)
    trade_allowed_warning: bool = False
    deals: list[Deal] = field(default_factory=list)  # lich su da dong (idempotent theo (account_id, ticket)); bridge khong giu trang thai


class AgentGateway(BrokerGateway):
    def __init__(self, cfg: AccountConfig, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.cfg = cfg
        self.account_id = cfg.account_id
        self.platform = cfg.platform
        self._clock = clock
        self._account: Optional[Account] = None
        self._positions: list[Position] = []
        self._orders: list[PendingOrder] = []
        self._quotes: dict[str, Quote] = {}
        self._bars: dict[tuple[str, str], OrderedDict[datetime, Bar]] = {}
        self._last_seen: Optional[datetime] = None
        self._last_seq = -1
        self._offset_s: Optional[float] = None

    # ---- ingest ----
    def ingest(self, b: Batch) -> IngestResult:
        c = self.cfg
        if b.server_time is not None:
            raw = b.server_time - b.ts
            self._offset_s = round(raw / 900.0) * 900.0  # lam tron 15 phut (do tre mang)
        off = self._offset_s
        src = f"{b.platform}:{self.account_id}"
        res = IngestResult()
        now = self._clock()
        self._last_seen = now
        self._last_seq = max(self._last_seq, b.seq)

        if b.account is not None:
            a = b.account
            margin_level = a.margin_level if a.margin_level not in (None, 0) else None
            if margin_level is None and a.margin > 0:
                margin_level = a.equity / a.margin * 100.0
            if a.margin <= 0:
                margin_level = None
            res.account = self._account = Account(
                account_id=self.account_id,
                platform=b.platform,
                login=a.login,
                server=a.server,
                currency=a.currency,
                leverage=a.leverage,
                balance=a.balance,
                equity=a.equity,
                margin=a.margin,
                free_margin=a.free_margin,
                margin_level=margin_level,
                margin_mode=a.margin_mode if b.platform == "mt5" else "hedging",
                ts=datetime.fromtimestamp(b.ts, timezone.utc),
            )
            res.trade_allowed_warning = bool(a.trade_allowed)

        if b.positions is not None:
            res.positions = self._positions = sorted(
                (
                    Position(
                        position_id=str(p.ticket),
                        symbol=c.to_canonical(p.symbol),
                        broker_symbol=p.symbol,
                        side="buy" if p.type == 0 else "sell",
                        volume=p.lots,
                        price_open=p.open_price,
                        price_current=p.price,
                        sl=p.sl,
                        tp=p.tp,
                        profit=p.profit,
                        swap=p.swap,
                        magic=p.magic,
                        comment=p.comment,
                        time_open=c.server_epoch_to_utc(p.open_time, off),
                    )
                    for p in b.positions
                ),
                key=lambda x: x.position_id,
            )
        if b.orders is not None:
            res.orders = self._orders = sorted(
                (
                    PendingOrder(
                        order_id=str(o.ticket),
                        symbol=c.to_canonical(o.symbol),
                        broker_symbol=o.symbol,
                        kind=_ORDER_KINDS.get(o.type, "other"),
                        volume=o.lots,
                        price=o.price,
                        sl=o.sl,
                        tp=o.tp,
                        magic=o.magic,
                        comment=o.comment,
                        time_setup=c.server_epoch_to_utc(o.setup_time, off),
                    )
                    for o in b.orders
                ),
                key=lambda x: x.order_id,
            )
        for q in b.quotes:
            quote = Quote(
                symbol=c.to_canonical(q.symbol),
                broker_symbol=q.symbol,
                bid=q.bid,
                ask=q.ask,
                ts=c.server_epoch_to_utc(q.time, off),
                source=src,
            )
            self._quotes[quote.symbol] = quote
            res.quotes.append(quote)
        for br in b.bars:
            bar = Bar(
                symbol=c.to_canonical(br.symbol),
                broker_symbol=br.symbol,
                tf=br.tf,
                ts_open=c.server_epoch_to_utc(br.time, off),
                o=br.o,
                h=br.h,
                l=br.l,
                c=br.c,
                v=br.v,
                source=src,
            )
            series = self._bars.setdefault((bar.symbol, bar.tf), OrderedDict())
            if series.get(bar.ts_open) != bar:
                series[bar.ts_open] = bar
                res.bars.append(bar)
                while len(series) > MAX_BARS_PER_SERIES:
                    series.popitem(last=False)
        for d in b.deals or []:
            res.deals.append(
                Deal(
                    account_id=self.account_id,
                    platform=b.platform,
                    ticket=str(d.ticket),
                    position_id=str(d.position_id or d.ticket),
                    symbol=c.to_canonical(d.symbol) if d.symbol else "",
                    broker_symbol=d.symbol,
                    side="balance" if d.type == 2 else ("buy" if d.type == 0 else "sell"),
                    volume=d.lots,
                    price_open=d.open_price,
                    price_close=d.close_price,
                    sl=d.sl,
                    tp=d.tp,
                    time_open=c.server_epoch_to_utc(d.open_time or d.close_time, off),
                    time_close=c.server_epoch_to_utc(d.close_time, off),
                    profit=d.profit,
                    swap=d.swap,
                    commission=d.commission,
                    magic=d.magic,
                    comment=d.comment,
                    reason=d.reason,
                    source=src,
                )
            )
        return res

    # ---- BrokerGateway ----
    def get_account(self) -> Account:
        if self._account is None:
            raise LookupError(f"{self.account_id}: chua nhan snapshot nao tu EA")
        return self._account

    def get_positions(self) -> list[Position]:
        return list(self._positions)

    def get_orders(self) -> list[PendingOrder]:
        return list(self._orders)

    def get_rates(self, symbol, tf, count=100, start=None, end=None) -> list[Bar]:
        series = self._bars.get((symbol.upper(), tf))
        if not series:
            return []
        bars = sorted(series.values(), key=lambda b: b.ts_open)
        if start is not None and end is not None:
            return [b for b in bars if start <= b.ts_open <= end]
        return bars[-count:]

    def get_quotes(self, symbols=None) -> list[Quote]:
        if symbols is None:
            return sorted(self._quotes.values(), key=lambda q: q.symbol)
        return [self._quotes[s.upper()] for s in symbols if s.upper() in self._quotes]

    def health(self) -> GatewayHealth:
        return GatewayHealth(
            account_id=self.account_id,
            platform=self.platform,
            connected=self._last_seen is not None,
            last_seen=self._last_seen,
            detail="agent" if self._last_seen else "waiting for EA",
        )

    @property
    def last_seen(self) -> Optional[datetime]:
        return self._last_seen


MT4Gateway = AgentGateway  # MT4 chi co duong agent
