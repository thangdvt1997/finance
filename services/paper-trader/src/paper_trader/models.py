"""Mô hình dữ liệu lõi (thuần Python, không I/O). Toàn bộ thời gian là datetime UTC (aware)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

TF_DELTA = {"M1": timedelta(minutes=1), "M5": timedelta(minutes=5), "M15": timedelta(minutes=15),
            "H1": timedelta(hours=1), "H4": timedelta(hours=4), "D1": timedelta(days=1)}


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return utc(dt).isoformat() if dt else None


def parse_ts(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return utc(v)
    return utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))


@dataclass(frozen=True)
class Instrument:
    symbol: str
    kind: str = "fx"                 # fx | metal | equity
    quote: str = "USD"               # tiền tệ định giá (đơn vị của giá)
    lot: float = 1.0                 # bước khối lượng (làm tròn về phía 0)
    spread_bps: float = 1.0          # spread TOÀN PHẦN (bid-ask) theo bps của giá; khớp nửa spread mỗi chiều
    slippage_bps: float = 0.5        # trượt giá cố định mỗi chiều (bps)
    slip_range_frac: float = 0.0     # thêm trượt giá = frac * (high-low)/open của bar khớp (bảo thủ khi biến động mạnh)
    commission_bps: float = 0.0      # phí theo giá trị khớp (mỗi chiều)
    min_fee: float = 0.0             # phí tối thiểu mỗi lệnh (đơn vị tiền tài khoản)
    sell_tax_bps: float = 0.0        # thuế bán (cổ phiếu VN 0,1%)
    swap_long_bps: float = 0.0       # chi phí giữ lệnh mua: bps/NĂM trên giá trị danh nghĩa (dương = tốn tiền)
    swap_short_bps: float = 0.0      # chi phí giữ lệnh bán (dương = tốn tiền)
    shortable: bool = True


@dataclass
class Bar:
    ts_open: datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


@dataclass
class Order:
    client_order_id: str
    account_id: str
    symbol: str
    side: str                        # buy | sell
    qty: float
    decision_ts: datetime            # thời điểm ra quyết định = đóng cửa bar tín hiệu
    eligible_from: datetime          # chỉ khớp ở bar có ts_open >= mốc này (chống look-ahead)
    kind: str = "rebalance"          # rebalance | flatten
    status: str = "pending"          # pending | filled | rejected | cancelled | expired
    reason: str = ""
    target_weight: float = 0.0
    ref_price: float = 0.0           # giá đóng cửa bar tín hiệu (để ước lượng)
    age: int = 0                     # số bước đã chờ

    def to_dict(self) -> dict:
        return {"client_order_id": self.client_order_id, "account_id": self.account_id, "symbol": self.symbol,
                "side": self.side, "qty": self.qty, "decision_ts": iso(self.decision_ts),
                "eligible_from": iso(self.eligible_from), "kind": self.kind, "status": self.status,
                "reason": self.reason, "target_weight": self.target_weight, "ref_price": self.ref_price, "age": self.age}

    @classmethod
    def from_dict(cls, d: dict) -> "Order":
        d = dict(d)
        d["decision_ts"], d["eligible_from"] = parse_ts(d["decision_ts"]), parse_ts(d["eligible_from"])
        return cls(**d)


@dataclass
class Fill:
    client_order_id: str
    account_id: str
    symbol: str
    side: str
    qty: float
    ts: datetime                     # ts_open của bar khớp
    ref_price: float                 # giá mở cửa (mid) của bar khớp
    price: float                     # giá khớp đã gồm spread + trượt giá
    spread_cost: float               # đơn vị tiền tài khoản
    slippage_cost: float
    commission: float
    tax: float
    realized_pnl: float = 0.0
    q2b: float = 1.0                 # tỷ giá quote -> tiền tài khoản tại lúc khớp

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["ts"] = iso(self.ts)
        return d


@dataclass
class Position:
    qty: float = 0.0
    avg_price: float = 0.0


@dataclass
class Targets:
    """Đầu ra của Strategy: MỤC TIÊU danh mục, KHÔNG phải lệnh.
    kind='weight'    : weights = tỷ trọng danh nghĩa/vốn (có dấu), vd 0.25 = 25% vốn long.
    kind='conviction': weights ∈ [-1,1] = hướng/độ tin cậy; risk engine đổi sang tỷ trọng (vol targeting / ATR)."""
    weights: dict[str, float] = field(default_factory=dict)
    kind: str = "weight"
    status: str = "ok"               # ok | warming_up | skip
    meta: dict = field(default_factory=dict)


@dataclass
class AccountState:
    cash: float
    initial_capital: float
    positions: dict[str, Position] = field(default_factory=dict)
    pending: list[Order] = field(default_factory=list)
    last_close: datetime | None = None          # close_ts của bar đã xử lý gần nhất
    inception_ts: datetime | None = None
    last_rebalance_key: str | None = None
    hwm: float = 0.0
    last_equity: float = 0.0
    day_key: str = ""
    day_start_equity: float = 0.0
    week_key: str = ""
    week_start_equity: float = 0.0
    status: str = "active"                      # active | halted (tạm, tự mở) | locked (kill-switch cứng, phải reset tay)
    halt_reason: str = ""
    halt_until: datetime | None = None
    costs: dict[str, float] = field(default_factory=lambda: {"spread": 0.0, "slippage": 0.0, "commission": 0.0, "tax": 0.0, "swap": 0.0})
    traded_notional: float = 0.0
    n_orders: int = 0
    n_fills: int = 0
    last_prices: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"cash": self.cash, "initial_capital": self.initial_capital,
                "positions": {s: {"qty": p.qty, "avg_price": p.avg_price} for s, p in self.positions.items()},
                "pending": [o.to_dict() for o in self.pending], "last_close": iso(self.last_close),
                "inception_ts": iso(self.inception_ts), "last_rebalance_key": self.last_rebalance_key, "hwm": self.hwm,
                "last_equity": self.last_equity, "day_key": self.day_key, "day_start_equity": self.day_start_equity,
                "week_key": self.week_key, "week_start_equity": self.week_start_equity, "status": self.status,
                "halt_reason": self.halt_reason, "halt_until": iso(self.halt_until), "costs": dict(self.costs),
                "traded_notional": self.traded_notional, "n_orders": self.n_orders, "n_fills": self.n_fills,
                "last_prices": dict(self.last_prices)}

    @classmethod
    def from_dict(cls, d: dict) -> "AccountState":
        st = cls(cash=float(d["cash"]), initial_capital=float(d["initial_capital"]))
        st.positions = {s: Position(float(p["qty"]), float(p["avg_price"])) for s, p in (d.get("positions") or {}).items()}
        st.pending = [Order.from_dict(o) for o in d.get("pending") or []]
        st.last_close, st.inception_ts, st.halt_until = parse_ts(d.get("last_close")), parse_ts(d.get("inception_ts")), parse_ts(d.get("halt_until"))
        for k in ("last_rebalance_key", "hwm", "last_equity", "day_key", "day_start_equity", "week_key", "week_start_equity",
                  "status", "halt_reason", "traded_notional", "n_orders", "n_fills"):
            if k in d:
                setattr(st, k, d[k])
        st.costs = {**st.costs, **(d.get("costs") or {})}
        st.last_prices = dict(d.get("last_prices") or {})
        return st


@dataclass
class StepResult:
    bar_ts: datetime
    close_ts: datetime
    equity: float = 0.0
    cash: float = 0.0
    gross: float = 0.0
    net: float = 0.0
    drawdown: float = 0.0
    swap_step: float = 0.0
    new_orders: list[Order] = field(default_factory=list)
    order_updates: list[Order] = field(default_factory=list)   # lệnh đổi trạng thái (filled/cancelled/expired)
    fills: list[Fill] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)           # {key,type,severity,message,data,ts}
    positions: dict[str, dict] = field(default_factory=dict)
