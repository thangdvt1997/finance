from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def walk(n: int, seed: int = 1, start: float = 1.1, vol: float = 0.007, t0: datetime = T0) -> list[tuple[datetime, float, float]]:
    """Random walk D1 (o = c truoc do, c moi). Lien tuc moi ngay (ke ca cuoi tuan) cho don gian."""
    rng = np.random.default_rng(seed)
    px, out = start, []
    for i in range(n):
        o = px
        px = o * math.exp(float(rng.normal(0, vol)))
        out.append((t0 + timedelta(days=i), o, px))
    return out


def make_items(entity: str, n: int, hit_p: float, seed: int, symbol: str = "EURUSD", cls: str = "forex") -> list[dict]:
    """n quan diem doc lap (cach nhau 1 ngay). Huong dung voi xac suat hit_p; do lon |ret| ngau nhien (khong phu thuoc huong)."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        mag = abs(float(rng.normal(0, 0.01))) + 1e-4
        up = bool(rng.random() < 0.5)
        right = bool(rng.random() < hit_p)
        raw = mag if up else -mag
        direction = ("bullish" if up else "bearish") if right else ("bearish" if up else "bullish")
        e = T0 + timedelta(days=i)
        d = 1.0 if direction == "bullish" else -1.0
        out.append({"view_id": f"{entity}-{i}", "entity_id": entity, "symbol": symbol, "asset_class": cls, "direction": direction, "observed_at": e - timedelta(hours=1),
                    "entry_ts": e, "exit_ts": e + timedelta(hours=12), "raw": raw, "hit": d * raw > 0, "regime": "range"})
    return out
