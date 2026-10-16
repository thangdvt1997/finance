"""Adapter MT5 (CHI DOC) dung package Python chinh hang `MetaTrader5` (chi Windows).

- Import luoi: tren Linux/CI khong can package; test dung `FakeMT5` (fake_mt5.py).
- Dung mat khau INVESTOR (chi doc). Neu tai khoan cho phep giao dich (trade_allowed) va
  require_investor=True -> tu choi ket noi.
- Chi goi cac ham doc: account_info, positions_get, orders_get, copy_rates_*, copy_ticks_*,
  symbol_info_tick, symbol_select. KHONG goi bat ky ham giao dich nao cua package.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..accounts import AccountConfig
from ..gateway import BrokerGateway
from ..models import TF_SECONDS, Account, Bar, GatewayHealth, PendingOrder, Position, Quote

log = logging.getLogger("mtbridge.mt5")

_ORDER_KINDS = {2: "buy_limit", 3: "sell_limit", 4: "buy_stop", 5: "sell_stop"}


def _f(row: Any, name: str, default: Any = None) -> Any:
    """Doc truong tu namedtuple / numpy.void / dict / object."""
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        return row[name]  # numpy structured row
    except (TypeError, IndexError, KeyError, ValueError):
        return getattr(row, name, default)


def load_mt5_module() -> Any:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as e:  # pragma: no cover - phu thuoc nen tang
        raise RuntimeError(
            "Package MetaTrader5 chi co tren Windows (pip install MetaTrader5). "
            "Tren Linux dung duong EA agent (transport=agent)."
        ) from e
    return mt5


class MT5Gateway(BrokerGateway):
    def __init__(
        self,
        cfg: AccountConfig,
        mt5: Any = None,
        *,
        password: Optional[str] = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.cfg = cfg
        self.account_id = cfg.account_id
        self._mt5 = mt5
        self._password = password if password is not None else cfg.password()
        self._clock = clock
        self._lock = threading.Lock()  # package MT5 khong thread-safe
        self._connected = False
        self._last_seen: Optional[datetime] = None
        self._detail = "not connected"

    # ---- ket noi ----
    @property
    def mt5(self) -> Any:
        if self._mt5 is None:
            self._mt5 = load_mt5_module()
        return self._mt5

    def connect(self) -> None:
        m = self.mt5
        kwargs: dict[str, Any] = {"login": self.cfg.login, "password": self._password, "server": self.cfg.server}
        if self.cfg.terminal_path:
            kwargs["path"] = self.cfg.terminal_path
        with self._lock:
            if not m.initialize(**kwargs):
                self._connected, self._detail = False, f"initialize failed: {m.last_error()}"
                raise ConnectionError(self._detail)
            info = m.account_info()
            if info is None:
                self._connected, self._detail = False, f"account_info None: {m.last_error()}"
                raise ConnectionError(self._detail)
            if bool(_f(info, "trade_allowed", False)):
                msg = "tai khoan cho phep giao dich: KHONG phai mat khau investor"
                if self.cfg.require_investor:
                    m.shutdown()
                    self._connected, self._detail = False, msg
                    raise PermissionError(msg + " - dung INVESTOR password (read-only)")
                log.warning("%s: %s", self.account_id, msg)
            self._connected, self._detail = True, "ok"
            self._last_seen = self._clock()

    def close(self) -> None:
        with self._lock:
            if self._mt5 is not None:
                self._mt5.shutdown()
            self._connected = False

    def _ok(self) -> None:
        self._last_seen = self._clock()
        self._connected, self._detail = True, "ok"

    def _fail(self, what: str) -> None:
        self._connected = False
        self._detail = f"{what}: {self.mt5.last_error()}"
        raise ConnectionError(self._detail)

    def _utc(self, epoch: float) -> datetime:
        return self.cfg.server_epoch_to_utc(epoch)

    # ---- doc ----
    def get_account(self) -> Account:
        with self._lock:
            info = self.mt5.account_info()
            if info is None:
                self._fail("account_info")
            self._ok()
        margin = float(_f(info, "margin", 0.0))
        ml = float(_f(info, "margin_level", 0.0))
        mm = _f(info, "margin_mode", None)
        mode = "hedging" if mm == 2 else ("netting" if mm in (0, 1) else "unknown")
        return Account(
            account_id=self.account_id,
            platform="mt5",
            login=int(_f(info, "login", self.cfg.login)),
            server=str(_f(info, "server", self.cfg.server)),
            currency=str(_f(info, "currency", "")),
            leverage=int(_f(info, "leverage", 0)),
            balance=float(_f(info, "balance", 0.0)),
            equity=float(_f(info, "equity", 0.0)),
            margin=margin,
            free_margin=float(_f(info, "margin_free", 0.0)),
            margin_level=ml if margin > 0 else None,
            margin_mode=mode,
            ts=self._clock(),
        )

    def get_positions(self) -> list[Position]:
        with self._lock:
            rows = self.mt5.positions_get()
            if rows is None:
                self._fail("positions_get")
            self._ok()
        out = []
        for r in rows:
            bs = str(_f(r, "symbol"))
            out.append(
                Position(
                    position_id=str(_f(r, "ticket")),
                    symbol=self.cfg.to_canonical(bs),
                    broker_symbol=bs,
                    side="buy" if int(_f(r, "type")) == 0 else "sell",
                    volume=float(_f(r, "volume")),
                    price_open=float(_f(r, "price_open")),
                    price_current=float(_f(r, "price_current")),
                    sl=float(_f(r, "sl", 0.0)),
                    tp=float(_f(r, "tp", 0.0)),
                    profit=float(_f(r, "profit", 0.0)),
                    swap=float(_f(r, "swap", 0.0)),
                    magic=int(_f(r, "magic", 0)),
                    comment=str(_f(r, "comment", "")),
                    time_open=self._utc(_f(r, "time")),
                )
            )
        return sorted(out, key=lambda p: p.position_id)

    def get_orders(self) -> list[PendingOrder]:
        with self._lock:
            rows = self.mt5.orders_get()
            if rows is None:
                self._fail("orders_get")
            self._ok()
        out = []
        for r in rows:
            bs = str(_f(r, "symbol"))
            out.append(
                PendingOrder(
                    order_id=str(_f(r, "ticket")),
                    symbol=self.cfg.to_canonical(bs),
                    broker_symbol=bs,
                    kind=_ORDER_KINDS.get(int(_f(r, "type")), "other"),
                    volume=float(_f(r, "volume_current")),
                    price=float(_f(r, "price_open")),
                    sl=float(_f(r, "sl", 0.0)),
                    tp=float(_f(r, "tp", 0.0)),
                    magic=int(_f(r, "magic", 0)),
                    comment=str(_f(r, "comment", "")),
                    time_setup=self._utc(_f(r, "time_setup")),
                )
            )
        return sorted(out, key=lambda o: o.order_id)

    def get_rates(self, symbol, tf, count=100, start=None, end=None) -> list[Bar]:
        if tf not in TF_SECONDS:
            raise ValueError(f"tf khong ho tro: {tf}")
        m, bs = self.mt5, self.cfg.to_broker(symbol)
        mtf = getattr(m, f"TIMEFRAME_{tf}")
        with self._lock:
            if start is not None and end is not None:
                a = datetime.fromtimestamp(self.cfg.utc_to_server_epoch(start), timezone.utc).replace(tzinfo=None)
                b = datetime.fromtimestamp(self.cfg.utc_to_server_epoch(end), timezone.utc).replace(tzinfo=None)
                rows = m.copy_rates_range(bs, mtf, a, b)
            else:
                rows = m.copy_rates_from_pos(bs, mtf, 0, count + 1)  # +1: bo nen dang chay
            if rows is None:
                self._fail(f"copy_rates {bs} {tf}")
            self._ok()
        now = self._clock()
        bars: list[Bar] = []
        for r in rows:
            t_open = self._utc(_f(r, "time"))
            if t_open + timedelta(seconds=TF_SECONDS[tf]) > now:
                continue  # nen chua dong
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    broker_symbol=bs,
                    tf=tf,  # type: ignore[arg-type]
                    ts_open=t_open,
                    o=float(_f(r, "open")),
                    h=float(_f(r, "high")),
                    l=float(_f(r, "low")),
                    c=float(_f(r, "close")),
                    v=float(_f(r, "tick_volume", 0)),
                    source=f"mt5:{self.account_id}",
                )
            )
        bars.sort(key=lambda b: b.ts_open)
        return bars[-count:] if (start is None or end is None) else bars

    def get_quotes(self, symbols=None) -> list[Quote]:
        syms = symbols if symbols is not None else self.cfg.watch_symbols
        out = []
        with self._lock:
            for s in syms:
                bs = self.cfg.to_broker(s)
                self.mt5.symbol_select(bs, True)
                t = self.mt5.symbol_info_tick(bs)
                if t is None:
                    continue
                out.append(
                    Quote(
                        symbol=s.upper(),
                        broker_symbol=bs,
                        bid=float(_f(t, "bid")),
                        ask=float(_f(t, "ask")),
                        ts=self._utc(_f(t, "time")),
                        source=f"mt5:{self.account_id}",
                    )
                )
            self._ok()
        return out

    def get_ticks(self, symbol, since, count=1000) -> list[Quote]:
        bs = self.cfg.to_broker(symbol)
        frm = datetime.fromtimestamp(self.cfg.utc_to_server_epoch(since), timezone.utc).replace(tzinfo=None)
        with self._lock:
            rows = self.mt5.copy_ticks_from(bs, frm, count, self.mt5.COPY_TICKS_ALL)
            if rows is None:
                self._fail(f"copy_ticks {bs}")
            self._ok()
        return [
            Quote(
                symbol=symbol.upper(),
                broker_symbol=bs,
                bid=float(_f(r, "bid")),
                ask=float(_f(r, "ask")),
                ts=self._utc(_f(r, "time")),
                source=f"mt5:{self.account_id}",
            )
            for r in rows
        ]

    def health(self) -> GatewayHealth:
        return GatewayHealth(
            account_id=self.account_id,
            platform="mt5",
            connected=self._connected,
            last_seen=self._last_seen,
            detail=self._detail,
        )
