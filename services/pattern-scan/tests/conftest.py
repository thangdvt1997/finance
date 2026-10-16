from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
DT = timedelta(minutes=15)


def make_bars(n: int = 300, base: float = 2000.0):
    """Nến M15 tổng hợp: tăng tới đỉnh ở nến 100, giảm mạnh tới 140, hồi tới 170, đi ngang sau đó."""
    rows, p = [], base
    for i in range(n):
        if i < 100:
            d = 0.6
        elif i < 140:
            d = -3.0
        elif i < 170:
            d = 1.2
        else:
            d = 0.4 * math.sin(i / 3.0)
        o, c = p, p + d
        rows.append({"ts_open": T0 + i * DT, "o": o, "h": max(o, c) + 0.5, "l": min(o, c) - 0.5, "c": c})
        p = c
    return rows


def ts(i: int) -> datetime:
    return T0 + i * DT


def payload(state: str, i: int, rows, **kw):
    lv = kw.pop("levels", None)
    if lv is None and state == "triggered":
        e = rows[i]["c"]
        sl = e + 10.0
        lv = {"entry": e, "sl": sl, "r": 10.0, "atr": 4.0, "tp_1r": e - 10, "tp_2r": e - 20, "tp_3r": e - 30, "wave_high": rows[100]["h"]}
    p = {"pattern": "KB-2", "symbol": "XAUUSD", "tf": "M15", "state": state, "side": "sell", "score": 72.0,
         "levels": lv or {"wave_high": rows[100]["h"], "wave_low": rows[140]["l"]},
         "steps": [{"id": 1, "label": "Sóng dẫn hướng giảm", "ok": True, "detail": ""}, {"id": 2, "label": "Hồi", "ok": True, "detail": ""}],
         "bar_ts": ts(i).isoformat(), "ts": (ts(i) + DT).isoformat(),
         "setup_id": f"KB-2:{ts(140).strftime('%Y%m%dT%H%M')}:{ts(170).strftime('%Y%m%dT%H%M')}", "reason": None, "info_only": True}
    p.update(kw)
    return p


@pytest.fixture
def bars():
    return make_bars()
