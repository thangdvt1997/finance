"""Chế độ xem /v1/analytics/*: lọc/sắp xếp/tổng hợp trên snapshot do service `analytics` ghi (không tính chỉ báo ở đây).

Hợp đồng snapshot (kind -> key): summary/detail `SYMBOL:TF`, correlation `TF`, sessions `SYMBOL`. Xem services/analytics/README.md.
Mọi dữ liệu là chỉ báo kỹ thuật, KHÔNG phải khuyến nghị đầu tư.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DISCLAIMER = "Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư."
TF_ORDER = ["M1", "M5", "M15", "H1", "H4", "D1"]
SORT_KEYS = {"heat", "bias", "rsi", "adx", "atr_percentile", "atr_pct", "ema200_dist_pct", "stoch_k", "symbol", "close"}
TRENDS, MOMENTUMS, VOLS = {"up", "down", "side"}, {"overbought", "oversold", "bullish", "bearish", "neutral"}, {"squeeze", "high", "normal", "low"}

Row = dict[str, Any]


def _updated(rows: list[Row]) -> datetime | None:
    ts = [r["updated_at"] for r in rows if r.get("updated_at")]
    return max(ts) if ts else None


def _meta(rows: list[Row]) -> dict:
    u = _updated(rows)
    now = datetime.now(timezone.utc)
    return {"generated_at": now, "updated_at": u, "age_seconds": (now - u).total_seconds() if u else None, "disclaimer": DISCLAIMER}


def _sorted_tfs(tfs) -> list[str]:
    return sorted(set(tfs), key=lambda t: TF_ORDER.index(t) if t in TF_ORDER else 99)


def overview(rows: list[Row]) -> dict:
    items = [r["payload"] for r in rows]
    syms = sorted({i["symbol"] for i in items})
    by_tf: dict[str, dict] = {}
    for tf in _sorted_tfs(i["tf"] for i in items):
        sub = [i for i in items if i["tf"] == tf]
        by_tf[tf] = {
            "n": len(sub),
            "up": sum(i["trend"] == "up" for i in sub), "down": sum(i["trend"] == "down" for i in sub),
            "side": sum(i["trend"] == "side" for i in sub),
            "overbought": sum(i["momentum"] == "overbought" for i in sub), "oversold": sum(i["momentum"] == "oversold" for i in sub),
            "squeeze": sum(bool(i.get("squeeze")) for i in sub), "high_vol": sum(i["volatility"] == "high" for i in sub),
        }
    top = sorted(items, key=lambda i: -i["heat"])[:8]
    return {**_meta(rows), "symbols": syms, "tfs": list(by_tf), "items": sorted(items, key=lambda i: (i["symbol"], TF_ORDER.index(i["tf"]) if i["tf"] in TF_ORDER else 99)),
            "summary": {"by_tf": by_tf, "top_heat": [{k: i[k] for k in ("symbol", "tf", "heat", "bias", "trend")} for i in top]}}


def symbol_detail(rows: list[Row], sessions: list[Row]) -> dict:
    tfs = {r["payload"]["tf"]: r["payload"] for r in rows}
    return {**_meta(rows), "symbol": rows[0]["payload"]["symbol"] if rows else None,
            "tfs": {t: tfs[t] for t in _sorted_tfs(tfs)}, "sessions": sessions[0]["payload"] if sessions else None}


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def screener(rows: list[Row], *, tf: str, trend: str | None, momentum: str | None, volatility: str | None, state: str | None,
             rsi_min: float | None, rsi_max: float | None, adx_min: float | None, heat_min: float | None,
             bias_min: float | None, bias_max: float | None, atr_pctile_min: float | None, q: str | None,
             sort: str, order: str, limit: int) -> dict:
    wt, wm, wv, ws = set(_csv(trend)), set(_csv(momentum)), set(_csv(volatility)), _csv(state)
    qq = (q or "").strip().lower()

    def ok(i: dict) -> bool:
        if i["tf"] != tf:
            return False
        if wt and i["trend"] not in wt or wm and i["momentum"] not in wm or wv and i["volatility"] not in wv:
            return False
        if ws:
            have = {s["code"] for s in i.get("states", [])}
            if not set(ws) <= have:
                return False
        for val, lo, hi in ((i.get("rsi"), rsi_min, rsi_max), (i.get("bias"), bias_min, bias_max)):
            if lo is not None and (val is None or val < lo) or hi is not None and (val is None or val > hi):
                return False
        if adx_min is not None and (i.get("adx") is None or i["adx"] < adx_min):
            return False
        if heat_min is not None and i["heat"] < heat_min:
            return False
        if atr_pctile_min is not None and (i.get("atr_percentile") is None or i["atr_percentile"] < atr_pctile_min):
            return False
        return not qq or qq in i["symbol"].lower()

    hit = [r["payload"] for r in rows if ok(r["payload"])]
    rev = order == "desc"
    present = [i for i in hit if i.get(sort) is not None]
    missing = [i for i in hit if i.get(sort) is None]
    present.sort(key=lambda i: (i[sort], i["symbol"]) if sort != "symbol" else i["symbol"], reverse=rev)
    out = (present + missing)[:limit]
    return {**_meta(rows), "tf": tf, "total": len(hit), "count": len(out), "items": out}


def correlation(rows: list[Row], tf: str, min_delta: float = 0.8) -> dict:
    if not rows:
        return {**_meta(rows), "tf": tf, "symbols": [], "matrix": [], "matrix_prev": None, "window": None, "top_pairs": [], "flips": []}
    p = rows[0]["payload"]
    s, m, prev = p["symbols"], p["matrix"], p.get("matrix_prev")
    pairs, flips = [], []
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            a = m[i][j]
            if a is None:
                continue
            b = prev[i][j] if prev else None
            pairs.append({"a": s[i], "b": s[j], "corr": a, "prev": b})
            if b is not None and a * b < 0 and abs(a - b) >= min_delta:
                flips.append({"a": s[i], "b": s[j], "now": a, "prev": b, "delta": round(a - b, 3)})
    pairs.sort(key=lambda x: -abs(x["corr"]))
    return {**_meta(rows), "tf": tf, "symbols": s, "matrix": m, "matrix_prev": prev, "window": p.get("window"),
            "as_of": p.get("as_of"), "method": p.get("method"), "top_pairs": pairs[:12],
            "flips": sorted(flips, key=lambda x: -abs(x["delta"]))}


def sessions(rows: list[Row]) -> dict:
    return {**_meta(rows), "items": [r["payload"] for r in rows]}
