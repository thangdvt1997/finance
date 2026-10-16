"""Dong thuan co trong so theo thanh tich. Moi entity chi tinh quan diem MOI NHAT cua minh tren moi symbol trong cua so. Ham thuan."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from .config import asset_class


def level_of(n_experts: int, net_w: float) -> str:
    if n_experts >= 3 and abs(net_w) >= 0.6:
        return "consensus"
    if abs(net_w) >= 0.3:
        return "weak"
    return "none"


def in_scope(symbol: str, scope: str) -> bool:
    if scope == "all":
        return True
    if scope.startswith("sym:"):
        return symbol == scope[4:]
    return asset_class(symbol) == scope


def build(views: list[dict[str, Any]], entities: dict[str, dict], weights: dict[str, dict], now: datetime, window_days: int, scope: str, min_experts: int) -> list[dict]:
    """views: moi dict co entity_id, symbol, direction, published_at. weights[entity_id] = {w, status}."""
    cutoff = now - timedelta(days=window_days)
    latest: dict[tuple[str, str], dict] = {}
    for v in views:
        if v["published_at"] < cutoff or v["published_at"] > now or not in_scope(v["symbol"], scope):
            continue
        k = (v["entity_id"], v["symbol"])
        if k not in latest or v["published_at"] > latest[k]["published_at"]:
            latest[k] = v
    by_sym: dict[str, list[dict]] = {}
    for v in latest.values():
        by_sym.setdefault(v["symbol"], []).append(v)
    rows = []
    for sym, lst in by_sym.items():
        if len(lst) < min_experts:
            continue
        agg = {"bullish": {"n": 0, "weight": 0.0}, "bearish": {"n": 0, "weight": 0.0}}
        top = []
        for v in lst:
            w = weights.get(v["entity_id"], {})
            wt, st = float(w.get("w", 1.0)), w.get("status", "insufficient")
            agg[v["direction"]]["n"] += 1
            agg[v["direction"]]["weight"] += wt
            e = entities.get(v["entity_id"], {})
            top.append({"entity_id": v["entity_id"], "label": e.get("label", ""), "direction": v["direction"], "weight": round(wt, 3), "status": st, "published_at": v["published_at"].isoformat()})
        nb, ns = agg["bullish"]["n"], agg["bearish"]["n"]
        wb, ws = agg["bullish"]["weight"], agg["bearish"]["weight"]
        net_w = (wb - ws) / (wb + ws) if wb + ws > 0 else 0.0
        net_u = (nb - ns) / (nb + ns) if nb + ns > 0 else 0.0
        agree = max(wb, ws) / (wb + ws) if wb + ws > 0 else 0.0
        top.sort(key=lambda t: (-t["weight"], t["published_at"]), reverse=False)
        rows.append({"symbol": sym, "asset_class": asset_class(sym), "n_experts": len(lst),
                     "bullish": {"n": nb, "weight": round(wb, 3)}, "bearish": {"n": ns, "weight": round(ws, 3)},
                     "net_weighted": round(net_w, 4), "net_unweighted": round(net_u, 4), "agreement": round(agree, 4),
                     "level": level_of(len(lst), net_w), "latest_at": max(v["published_at"] for v in lst).isoformat(), "top": top[:5]})
    rows.sort(key=lambda r: (-r["n_experts"], -abs(r["net_weighted"]), r["symbol"]))
    return rows
