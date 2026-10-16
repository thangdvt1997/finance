from __future__ import annotations

from datetime import datetime, timedelta, timezone

from journal.models import Trade

UTC = timezone.utc


def dt(day: int, h: int = 0, m: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, h, m, tzinfo=UTC)


def mk(ticket, *, side="buy", vol=0.1, po=1.1, pc=1.1, to=None, tc=None, profit=0.0, swap=0.0, comm=0.0, sl=0.0, magic=0, symbol="EURUSD", kind="trade", **kw) -> Trade:
    to = to or dt(1, 8)
    tc = tc or (to + timedelta(hours=1))
    return Trade(ticket=str(ticket), kind=kind, symbol=symbol, side=side, volume=vol, price_open=po, price_close=pc, time_open=to, time_close=tc,
                 profit=profit, swap=swap, commission=comm, sl=sl, magic=magic, group="manual" if magic == 0 else f"magic:{magic}", **kw)


def five_trades() -> list[Trade]:
    """net: +100, -50, +30, -20, +60 (profit/swap/commission tach de kiem tra net = tong 3 thanh phan)."""
    return [
        mk(1, to=dt(1, 8), tc=dt(1, 9), profit=102, swap=-1, comm=-1, magic=7),
        mk(2, to=dt(1, 10), tc=dt(1, 11), profit=-48, swap=-1, comm=-1, magic=7),
        mk(3, to=dt(2, 8), tc=dt(2, 10), profit=31, comm=-1, magic=0),
        mk(4, to=dt(2, 11), tc=dt(2, 12), profit=-19, comm=-1, magic=0),
        mk(5, to=dt(3, 8), tc=dt(3, 9), profit=61, comm=-1, magic=7),
    ]
