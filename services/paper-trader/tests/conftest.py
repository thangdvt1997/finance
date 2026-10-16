from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from paper_trader import strategies  # noqa: F401  (đăng ký built-in)
from paper_trader.engine import Engine
from paper_trader.market import MarketView, frame_from_rows
from paper_trader.models import Instrument
from paper_trader.risk import RiskConfig, RiskEngine
from paper_trader.strategy import build

START = datetime(2026, 1, 5, tzinfo=timezone.utc)   # thứ Hai
DAY = timedelta(days=1)


def rows_from_closes(closes: list[float], start: datetime = START, opens: list[float] | None = None, spread: float = 0.0) -> list[dict]:
    """Nến D1 tất định: open = close hôm trước (hoặc `opens`), high/low = ±spread quanh max/min."""
    rows = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = opens[i] if opens else prev
        rows.append({"ts_open": start + DAY * i, "o": o, "h": max(o, c) + spread, "l": min(o, c) - spread, "c": c, "v": 100.0})
        prev = c
    return rows


def view_of(data: dict[str, list[dict]], now: datetime | None = None, tf: str = "D1") -> MarketView:
    frames = {s: frame_from_rows(r) for s, r in data.items()}
    return MarketView(frames, tf, now or (START + DAY * 4000))


def fx_inst(sym="EURUSD", **kw) -> Instrument:
    base = dict(kind="fx", quote=sym[3:6], lot=1.0, spread_bps=0.0, slippage_bps=0.0, slip_range_frac=0.0, commission_bps=0.0,
                swap_long_bps=0.0, swap_short_bps=0.0)
    base.update(kw)
    return Instrument(symbol=sym, **base)


def make_engine(strategy="buy_and_hold", params=None, universe=("EURUSD",), risk=None, rebalance="first_only", capital=10_000.0,
                instruments=None, base="USD", ppy=252) -> Engine:
    inst = instruments or {s: fx_inst(s) for s in universe}
    rc = RiskConfig.build(risk or {"max_leverage": 5.0, "max_weight": 5.0, "min_trade_weight": 0.0})
    return Engine("acct", base, inst, list(universe), build(strategy, params), RiskEngine(rc, ppy), tf="D1", rebalance=rebalance, initial_capital=capital)


@pytest.fixture
def rng():
    return np.random.default_rng(7)
