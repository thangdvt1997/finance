from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
STEP = {"H1": timedelta(hours=1), "H4": timedelta(hours=4), "D1": timedelta(days=1)}


def make_bars(n: int, tf: str = "H1", start_price: float = 100.0, drift: float = 0.0, vol: float = 0.2,
              seed: int = 1, wave: float = 0.0, end: datetime | None = None) -> list[dict]:
    """Chuỗi nến giả định tất định (random walk + drift + sóng sin). ts_open kết thúc tại `end` (mặc định cố định)."""
    rnd = np.random.default_rng(seed)
    step = STEP[tf]
    end = end or (START + step * n)
    price = start_price
    rows = []
    for i in range(n):
        o = price
        price = max(0.5, o + drift + wave * np.sin(i / 7.0) + rnd.normal(0, vol))
        c = price
        h = max(o, c) + abs(rnd.normal(0, vol / 2)) + 0.01
        lo = min(o, c) - abs(rnd.normal(0, vol / 2)) - 0.01
        rows.append({"ts_open": end - step * (n - i), "o": float(o), "h": float(h), "l": float(lo), "c": float(c),
                     "v": float(100 + i % 7), "source": "t"})
    return rows


@pytest.fixture
def up_bars():
    return make_bars(400, drift=0.15, vol=0.3, seed=3)


@pytest.fixture
def down_bars():
    return make_bars(400, start_price=200.0, drift=-0.15, vol=0.3, seed=4)
