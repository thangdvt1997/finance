"""Chuyen paper_fills (lenh MO PHONG, tung lan khop) thanh cac giao dich DA DONG de dung CHUNG engine thong ke voi MT.

Moi lan khop giam/dong/dao chieu vi the tao 1 'trade' cho phan DONG. Phi (commission + thue) cua lan khop dong + phi vao lenh
da tich luy duoc phan bo theo ty le khoi luong. profit = realized_pnl (gross, da quy doi sang tien te goc nho q2b); spread/slippage da nam trong gia khop.
Khong co SL trong paper -> R-multiple/no_sl khong ap dung (journal dat require_sl=False cho paper).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .models import Trade

EPS = 1e-9


@dataclass
class _Pos:
    qty: float = 0.0  # co dau (>0 long)
    avg: float = 0.0
    opened: datetime | None = None
    entry_cost: float = 0.0  # phi vao lenh con chua phan bo (duong)
    entry_spread: float = 0.0
    entry_slip: float = 0.0


def fills_to_trades(fills: Iterable[dict[str, Any]], *, account_id: str, strategy: str = "") -> list[Trade]:
    """fills: dict {fill_id, symbol, side, qty, ts, price, spread_cost, slippage_cost, commission, tax, realized_pnl} -> Trade da dong."""
    pos: dict[str, _Pos] = {}
    out: list[Trade] = []
    for f in sorted(fills, key=lambda x: (x["ts"], x.get("fill_id", 0))):
        sym, qty, price = f["symbol"], float(f["qty"]), float(f["price"])
        if qty <= 0:
            continue
        signed = qty if f["side"] == "buy" else -qty
        cost = float(f.get("commission") or 0.0) + float(f.get("tax") or 0.0)
        sp, sl = float(f.get("spread_cost") or 0.0), float(f.get("slippage_cost") or 0.0)
        p = pos.setdefault(sym, _Pos())
        old = p.qty
        if abs(old) < EPS or (old > 0) == (signed > 0):  # mo/them cung chieu
            newq = old + signed
            p.avg = (abs(old) * p.avg + qty * price) / abs(newq)
            p.qty = newq
            p.opened = p.opened if abs(old) >= EPS else f["ts"]
            p.entry_cost += cost
            p.entry_spread += sp
            p.entry_slip += sl
            continue
        # giam / dong / dao chieu
        closed = min(abs(old), qty)
        frac_pos = closed / abs(old)
        frac_fill = closed / qty
        e_cost, e_sp, e_sl = p.entry_cost * frac_pos, p.entry_spread * frac_pos, p.entry_slip * frac_pos
        side = "buy" if old > 0 else "sell"
        out.append(Trade(
            ticket=f"P{f.get('fill_id', len(out))}", kind="trade", symbol=sym, side=side, volume=closed,
            price_open=p.avg, price_close=price, time_open=p.opened or f["ts"], time_close=f["ts"],
            profit=float(f.get("realized_pnl") or 0.0),  # realized_pnl cua lan khop chi tinh phan DONG
            swap=0.0, commission=-(e_cost + cost * frac_fill), group=strategy or "paper", comment=strategy,
            reason="", source=f"paper:{account_id}", position_id=f"{account_id}:{sym}",
            spread_cost=e_sp + sp * frac_fill, slippage_cost=e_sl + sl * frac_fill))
        p.entry_cost -= e_cost
        p.entry_spread -= e_sp
        p.entry_slip -= e_sl
        newq = old + signed
        if abs(newq) < EPS:
            pos[sym] = _Pos()
        elif (newq > 0) != (old > 0):  # dao chieu: phan con lai la lenh moi o gia khop
            rest = 1.0 - frac_fill
            pos[sym] = _Pos(qty=newq, avg=price, opened=f["ts"], entry_cost=cost * rest, entry_spread=sp * rest, entry_slip=sl * rest)
        else:
            p.qty = newq
    return out
