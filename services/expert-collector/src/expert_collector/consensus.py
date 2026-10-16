"""Ham thuan: dong thuan giua cac chuyen gia uy tin."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Consensus:
    symbol: str
    side: str
    experts: list[str]
    total: int


def compute_consensus(stances: dict[str, dict[str, dict]], now: datetime, window: timedelta,
                      min_experts: int = 3, min_ratio: float = 0.7) -> list[Consensus]:
    """stances: expert_id -> symbol -> {side, ts(iso)}. Chi tinh stance con trong cua so thoi gian."""
    by_sym: dict[str, dict[str, list[str]]] = {}
    for eid, syms in stances.items():
        for sym, st in syms.items():
            ts = datetime.fromisoformat(st["ts"])
            if now - ts > window or st["side"] not in ("buy", "sell"):
                continue
            by_sym.setdefault(sym, {"buy": [], "sell": []})[st["side"]].append(eid)
    out = []
    for sym, d in sorted(by_sym.items()):
        total = len(d["buy"]) + len(d["sell"])
        for side in ("buy", "sell"):
            n = len(d[side])
            if n >= min_experts and n / total >= min_ratio:
                out.append(Consensus(sym, side, sorted(d[side]), total))
    return out


@dataclass
class WeightedConsensus(Consensus):
    weight: float = 0.0           # tong trong so phia dong thuan
    weight_total: float = 0.0     # tong trong so ca hai phia
    weight_ratio: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)   # expert_id -> trong so hieu dung (phia dong thuan)


def _w(v, default: float = 1.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(f) else min(max(f, 0.0), 3.0)


def compute_weighted_consensus(stances: dict[str, dict[str, dict]], now: datetime, window: timedelta,
                               weights: dict[str, float] | None = None, prior: dict[str, float] | None = None,
                               min_experts: int = 3, min_ratio: float = 0.7,
                               min_weight: float | None = None, min_weight_ratio: float | None = None) -> list[WeightedConsensus]:
    """Dong thuan CO TRONG SO. Trong so chuyen gia = weights.get(id, 1) x prior.get(id, 1) (prior = tien nghiem cu, mac dinh 1).
    Dong thuan khi CA BA dieu kien: so chuyen gia cung chieu >= min_experts; tong trong so cung chieu >= min_weight (mac dinh = min_experts);
    ty le trong so cung chieu >= min_weight_ratio (mac dinh = min_ratio). Trong so deu = 1 -> ket qua GIONG compute_consensus.
    Nguoi thanh tich kem (w nho) khong du de tao dong thuan; w > 1 khong ha nguong so luong chuyen gia."""
    weights, prior = weights or {}, prior or {}
    min_weight = float(min_experts) if min_weight is None else float(min_weight)
    min_weight_ratio = min_ratio if min_weight_ratio is None else float(min_weight_ratio)
    by_sym: dict[str, dict[str, list[str]]] = {}
    eff: dict[str, float] = {}
    for eid, syms in stances.items():
        eff[eid] = _w(weights.get(eid), 1.0) * _w(prior.get(eid), 1.0)
        for sym, st in syms.items():
            ts = datetime.fromisoformat(st["ts"])
            if now - ts > window or st["side"] not in ("buy", "sell"):
                continue
            by_sym.setdefault(sym, {"buy": [], "sell": []})[st["side"]].append(eid)
    out = []
    for sym, d in sorted(by_sym.items()):
        total = len(d["buy"]) + len(d["sell"])
        wt = sum(eff[e] for e in d["buy"]) + sum(eff[e] for e in d["sell"])
        for side in ("buy", "sell"):
            n = len(d[side])
            ws = sum(eff[e] for e in d[side])
            ratio = ws / wt if wt > 0 else 0.0
            if n >= min_experts and ws >= min_weight and wt > 0 and ratio >= min_weight_ratio:
                out.append(WeightedConsensus(sym, side, sorted(d[side]), total, round(ws, 4), round(wt, 4), round(ratio, 4),
                                             {e: round(eff[e], 4) for e in sorted(d[side])}))
    return out
