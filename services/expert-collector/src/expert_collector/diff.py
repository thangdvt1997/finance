"""Ham thuan: gop vi the thanh net theo symbol va phat hien mo/dong/dao chieu."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import PositionInfo, normalize_symbol


def net_positions(positions: list[PositionInfo]) -> dict[str, dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for p in positions:
        sym = normalize_symbol(p.symbol)
        sign = 1 if p.side == "buy" else -1
        a = agg.setdefault(sym, {"net": 0.0, "notional": 0.0, "vol": 0.0, "sl": None, "tp": None, "opened_at": None})
        a["net"] += sign * p.volume
        if p.entry is not None:
            a["notional"] += p.entry * p.volume
            a["vol"] += p.volume
        if p.sl is not None:
            a["sl"] = p.sl
        if p.tp is not None:
            a["tp"] = p.tp
        if p.opened_at and (a["opened_at"] is None or p.opened_at < a["opened_at"]):
            a["opened_at"] = p.opened_at
    out: dict[str, dict[str, Any]] = {}
    for sym, a in agg.items():
        if abs(a["net"]) < 1e-9:
            continue
        out[sym] = {
            "side": "buy" if a["net"] > 0 else "sell",
            "net_volume": round(a["net"], 6),
            "avg_price": (a["notional"] / a["vol"]) if a["vol"] else None,
            "sl": a["sl"], "tp": a["tp"],
            "opened_at": a["opened_at"].isoformat() if a["opened_at"] else None,
        }
    return out


@dataclass
class Change:
    kind: str  # open|close|reverse
    symbol: str
    old: dict | None
    new: dict | None


def diff_net(prev: dict[str, dict], cur: dict[str, dict]) -> list[Change]:
    ch: list[Change] = []
    for sym in sorted(set(prev) | set(cur)):
        o, n = prev.get(sym), cur.get(sym)
        if o is None and n is not None:
            ch.append(Change("open", sym, None, n))
        elif o is not None and n is None:
            ch.append(Change("close", sym, o, None))
        elif o and n and o["side"] != n["side"]:
            ch.append(Change("reverse", sym, o, n))
    return ch
