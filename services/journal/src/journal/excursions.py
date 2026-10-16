"""MAE/MFE tu nen (HAM THUAN). MAE = muc bat loi toi da, MFE = muc co loi toi da trong thoi gian giu lenh (tinh theo GIA).

Nen thuoc khung lon hon thoi gian giu lenh se lam MAE/MFE phong dai (nen bao gom ca doan ngoai lenh) - chon khung nen nho (xem `pick_tf`).
Chi la xap xi tu nen (khong phai tick): MAE/MFE that co the lon hon neu gia quet qua trong 1 nen nho hon khung dang dung.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from .models import Trade

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def pick_tf(hold_s: float) -> str:
    if hold_s <= 6 * 3600:
        return "M1"
    if hold_s <= 2 * 86400:
        return "M5"
    if hold_s <= 14 * 86400:
        return "H1"
    return "D1"


def excursion(t: Trade, bars: list[dict], tf: str) -> Optional[dict]:
    """bars: [{ts: datetime (mo nen, UTC), h, l}] cung khung `tf`. None neu khong co nen phu khoang giu lenh."""
    if t.kind != "trade" or t.price_open <= 0:
        return None
    secs = TF_SECONDS[tf]
    sel = [b for b in bars if b["ts"] < t.time_close and b["ts"] + timedelta(seconds=secs) > t.time_open]
    if not sel:
        return None
    hi, lo = max(b["h"] for b in sel), min(b["l"] for b in sel)
    o = t.price_open
    if t.side == "buy":
        mfe, mae = max(0.0, hi - o), max(0.0, o - lo)
    else:
        mfe, mae = max(0.0, o - lo), max(0.0, hi - o)
    realized = t.sign * (t.price_close - o)
    rd = t.risk_dist
    return {
        "ticket": t.ticket, "symbol": t.symbol, "side": t.side, "tf": tf, "bars": len(sel),
        "mae": round(mae, 6), "mfe": round(mfe, 6), "mae_pct": round(mae / o * 100, 4), "mfe_pct": round(mfe / o * 100, 4),
        "mae_r": round(mae / rd, 3) if rd else None, "mfe_r": round(mfe / rd, 3) if rd else None,
        "capture": round(realized / mfe, 3) if mfe > 0 and realized > 0 else None,  # ty le MFE da chot (lenh thang)
        "left_on_table_pct": round((1 - realized / mfe) * 100, 1) if mfe > 0 and realized > 0 else None,
        "net": round(t.net, 2),
    }


def summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if r is not None]
    if not ok:
        return {"n": 0, "avg_mae_pct": None, "avg_mfe_pct": None, "avg_capture": None, "winners_avg_mae_pct": None, "losers_avg_mfe_pct": None}

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 4) if xs else None

    win = [r for r in ok if r["net"] > 0]
    los = [r for r in ok if r["net"] < 0]
    return {"n": len(ok), "avg_mae_pct": avg(r["mae_pct"] for r in ok), "avg_mfe_pct": avg(r["mfe_pct"] for r in ok),
            "avg_capture": avg(r["capture"] for r in ok), "winners_avg_mae_pct": avg(r["mae_pct"] for r in win),
            "losers_avg_mfe_pct": avg(r["mfe_pct"] for r in los)}
