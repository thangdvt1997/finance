"""Phân tích thị trường VN từ snapshot cuối ngày (hàm thuần, không I/O -> test không cần DB/mạng).

Đầu vào `rows` = danh sách dict từ Store.snapshot(d): mỗi dòng 1 mã (giá VND, volume cp, value VND, pct %, marketcap VND, pe, pb ...).
Các chỉ số SUY RA (đánh dấu `_est`): EPS = giá/PE, ROE = PB/PE (đúng khi PE, PB dùng cùng kỳ). Nguồn không cung cấp ROE/EPS trực tiếp.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from . import rules

FLOORS = ("HOSE", "HNX", "UPCOM")
UNIVERSES = {"all": "Toàn thị trường", "hose": "HOSE", "hnx": "HNX", "upcom": "UPCoM", "vn30": "VN30", "vn100": "VN100", "hnx30": "HNX30", "etf": "ETF"}


def num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def in_universe(r: dict, u: str) -> bool:
    u = (u or "all").lower()
    if u == "all":
        return True
    if u in ("hose", "hnx", "upcom"):
        return r.get("floor") == u.upper() and r.get("kind") != "ETF"
    if u == "vn30":
        return bool(r.get("in_vn30"))
    if u == "vn100":
        return bool(r.get("in_vn100"))
    if u == "hnx30":
        return bool(r.get("in_hnx30"))
    if u == "etf":
        return r.get("kind") == "ETF"
    return True


def flag(r: dict) -> str | None:
    if (num(r.get("volume")) or 0) <= 0:
        return None
    return rules.limit_flag(num(r.get("close")), num(r.get("ceil")), num(r.get("flr")))


def traded(r: dict) -> bool:
    return (num(r.get("volume")) or 0) > 0


def eps_est(r: dict) -> float | None:
    pe, c = num(r.get("pe")), num(r.get("close"))
    return round(c / pe, 2) if pe and pe > 0 and c else None


def roe_est(r: dict) -> float | None:
    pe, pb = num(r.get("pe")), num(r.get("pb"))
    return round(pb / pe * 100, 2) if pe and pe > 0 and pb and pb > 0 else None


def brief(r: dict) -> dict:
    """Dòng gọn dùng cho bảng top/limit/foreign."""
    return {"code": r["code"], "name": r.get("short_name") or r.get("name"), "floor": r.get("floor"), "kind": r.get("kind"),
            "industry": r.get("industry_name"), "close": num(r.get("close")), "basic": num(r.get("basic")), "pct": num(r.get("pct")),
            "volume": num(r.get("volume")), "value": num(r.get("value")), "pt_value": num(r.get("pt_value")),
            "ceil": num(r.get("ceil")), "flr": num(r.get("flr")), "limit": flag(r), "marketcap": num(r.get("marketcap")),
            "f_net": num(r.get("f_net")), "vn30": bool(r.get("in_vn30"))}


# ---- độ rộng thị trường -----------------------------------------------------------------------------------------------------
def _blank() -> dict:
    return {"advances": 0, "declines": 0, "unchanged": 0, "no_trade": 0, "ceiling": 0, "floor": 0, "value": 0.0, "pt_value": 0.0, "volume": 0.0, "total": 0}


def breadth(rows: Iterable[dict], include_etf: bool = False) -> dict:
    by: dict[str, dict] = {f: _blank() for f in FLOORS}
    by["ALL"] = _blank()
    for r in rows:
        if r.get("kind") == "ETF" and not include_etf:
            continue
        fl = r.get("floor") if r.get("floor") in FLOORS else None
        buckets = [by["ALL"]] + ([by[fl]] if fl else [])
        pct = num(r.get("pct")) or 0.0
        for b in buckets:
            b["total"] += 1
            b["value"] += num(r.get("value")) or 0.0
            b["pt_value"] += num(r.get("pt_value")) or 0.0
            b["volume"] += num(r.get("volume")) or 0.0
            if not traded(r):
                b["no_trade"] += 1
            elif pct > 0:
                b["advances"] += 1
            elif pct < 0:
                b["declines"] += 1
            else:
                b["unchanged"] += 1
            fg = flag(r)
            if fg == "ceiling":
                b["ceiling"] += 1
            elif fg == "floor":
                b["floor"] += 1
    for b in by.values():
        tr = b["advances"] + b["declines"] + b["unchanged"]
        b["adv_ratio"] = round(b["advances"] / tr, 4) if tr else None
        b["ad_line"] = b["advances"] - b["declines"]
    return by


# ---- top tăng/giảm/khối lượng/giá trị --------------------------------------------------------------------------------------
SORTS = {"gainers": ("pct", True), "losers": ("pct", False), "volume": ("volume", True), "value": ("value", True),
         "foreign_buy": ("f_net", True), "foreign_sell": ("f_net", False)}


def movers(rows: Iterable[dict], by: str = "gainers", universe: str = "all", n: int = 20, min_value: float = 1e9) -> list[dict]:
    """Top theo `by`. Với gainers/losers chỉ xét mã có GTGD khớp lệnh >= min_value (mặc định 1 tỷ) để loại mã thanh khoản mỏng."""
    key, desc = SORTS[by]
    cand = [r for r in rows if in_universe(r, universe) and traded(r) and num(r.get(key)) is not None]
    if by in ("gainers", "losers"):
        cand = [r for r in cand if (num(r.get("value")) or 0) >= min_value]
    if by == "gainers":
        cand = [r for r in cand if (num(r.get("pct")) or 0) > 0]
    elif by == "losers":
        cand = [r for r in cand if (num(r.get("pct")) or 0) < 0]
    elif by == "foreign_buy":
        cand = [r for r in cand if (num(r.get("f_net")) or 0) > 0]
    elif by == "foreign_sell":
        cand = [r for r in cand if (num(r.get("f_net")) or 0) < 0]
    cand.sort(key=lambda r: num(r.get(key)) or 0.0, reverse=desc)
    return [brief(r) for r in cand[:max(1, min(n, 100))]]


def limit_hits(rows: Iterable[dict], universe: str = "all") -> dict:
    out: dict[str, list[dict]] = {"ceiling": [], "floor": []}
    for r in rows:
        if not in_universe(r, universe):
            continue
        fg = flag(r)
        if fg:
            out[fg].append(brief(r))
    for k in out:
        out[k].sort(key=lambda x: x["value"] or 0.0, reverse=True)
    return {**out, "ceiling_n": len(out["ceiling"]), "floor_n": len(out["floor"])}


# ---- heatmap ngành + tổng hợp ngành --------------------------------------------------------------------------------------
def _size(r: dict, size_by: str) -> float:
    if size_by == "value":
        return num(r.get("value")) or 0.0
    return num(r.get("marketcap")) or 0.0


def heatmap(rows: Iterable[dict], universe: str = "vn100", size_by: str = "marketcap", per_sector: int = 25) -> dict:
    """Cây ECharts treemap: ngành -> mã. Kích thước = vốn hoá (hoặc GTGD); màu do UI tô theo `pct`."""
    sectors: dict[str, list[dict]] = {}
    for r in rows:
        if not in_universe(r, universe) or r.get("kind") == "ETF":
            continue
        sz = _size(r, size_by)
        if sz <= 0:
            continue
        sectors.setdefault(r.get("industry_name") or "Khác", []).append(r)
    children = []
    for name, items in sectors.items():
        items.sort(key=lambda r: _size(r, size_by), reverse=True)
        items = items[:per_sector]
        tot = sum(_size(r, size_by) for r in items)
        wsum = sum((num(r.get("pct")) or 0.0) * _size(r, size_by) for r in items)
        children.append({
            "name": name, "value": tot, "pct": round(wsum / tot, 3) if tot else 0.0, "n": len(items),
            "children": [{"name": r["code"], "value": _size(r, size_by), "pct": num(r.get("pct")) or 0.0, "close": num(r.get("close")),
                          "marketcap": num(r.get("marketcap")), "tvalue": num(r.get("value")), "limit": flag(r), "floor": r.get("floor")} for r in items]})
    children.sort(key=lambda c: c["value"], reverse=True)
    return {"universe": universe, "size_by": size_by, "sectors": children, "count": sum(c["n"] for c in children)}


def sector_summary(rows: Iterable[dict], universe: str = "all") -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        if not in_universe(r, universe) or r.get("kind") == "ETF":
            continue
        a = agg.setdefault(r.get("industry_name") or "Khác", {"sector": r.get("industry_name") or "Khác", "n": 0, "marketcap": 0.0, "value": 0.0,
                                                               "advances": 0, "declines": 0, "f_net": 0.0, "_w": 0.0, "_wp": 0.0})
        a["n"] += 1
        mc = num(r.get("marketcap")) or 0.0
        a["marketcap"] += mc
        a["value"] += num(r.get("value")) or 0.0
        a["f_net"] += num(r.get("f_net")) or 0.0
        pct = num(r.get("pct")) or 0.0
        if traded(r):
            a["advances"] += pct > 0
            a["declines"] += pct < 0
        if mc > 0:
            a["_w"] += mc
            a["_wp"] += mc * pct
    out = []
    for a in agg.values():
        a["pct_w"] = round(a["_wp"] / a["_w"], 3) if a["_w"] else None
        del a["_w"], a["_wp"]
        out.append(a)
    out.sort(key=lambda a: a["marketcap"], reverse=True)
    return out


# ---- thanh khoản -----------------------------------------------------------------------------------------------------------
def liquidity(series: list[dict], window: int = 20) -> dict:
    """series: [{d, floor, value, pt_value, volume, traded}] -> tổng theo ngày + so sánh trung bình `window` phiên trước đó."""
    by: dict[Any, dict] = {}
    for s in series:
        a = by.setdefault(s["d"], {"d": s["d"], "value": 0.0, "pt_value": 0.0, "volume": 0.0, "by_floor": {}})
        v = num(s.get("value")) or 0.0
        a["value"] += v
        a["pt_value"] += num(s.get("pt_value")) or 0.0
        a["volume"] += num(s.get("volume")) or 0.0
        a["by_floor"][s["floor"]] = v
    days = [by[k] for k in sorted(by)]
    last = days[-1] if days else None
    prev = days[:-1][-window:]
    avg = sum(x["value"] for x in prev) / len(prev) if prev else None
    ratio = (last["value"] / avg) if last and avg else None
    label = None
    if ratio is not None:
        label = "sôi động" if ratio >= 1.3 else "trên trung bình" if ratio >= 1.05 else "bình thường" if ratio >= 0.85 else "thấp" if ratio >= 0.65 else "rất thấp"
    return {"days": days, "last": last, "avg_prev": avg, "ratio": round(ratio, 3) if ratio is not None else None, "label": label, "window": len(prev)}


# ---- khối ngoại ------------------------------------------------------------------------------------------------------------
def foreign_summary(rows: list[dict], n: int = 15, universe: str = "all") -> dict:
    sel = [r for r in rows if in_universe(r, universe) and r.get("f_net") is not None]
    tot: dict[str, dict] = {}
    for r in sel:
        t = tot.setdefault(r.get("floor") or "?", {"buy": 0.0, "sell": 0.0, "net": 0.0})
        t["buy"] += num(r.get("f_buy")) or 0.0
        t["sell"] += num(r.get("f_sell")) or 0.0
        t["net"] += num(r.get("f_net")) or 0.0
    all_t = {k: sum(t[k] for t in tot.values()) for k in ("buy", "sell", "net")} if tot else {"buy": 0.0, "sell": 0.0, "net": 0.0}

    def fo(r: dict) -> dict:
        tr, cr = num(r.get("total_room")), num(r.get("current_room"))
        return {**brief(r), "f_buy": num(r.get("f_buy")), "f_sell": num(r.get("f_sell")),
                "own_pct": round((1 - cr / tr) * 100, 2) if tr and cr is not None and tr > 0 else None,
                "room_left_pct": round(cr / tr * 100, 2) if tr and cr is not None and tr > 0 else None}
    ordered = sorted(sel, key=lambda r: num(r.get("f_net")) or 0.0)
    return {"totals": {**tot, "ALL": all_t}, "top_buy": [fo(r) for r in reversed(ordered[-n:]) if (num(r.get("f_net")) or 0) > 0],
            "top_sell": [fo(r) for r in ordered[:n] if (num(r.get("f_net")) or 0) < 0], "count": len(sel)}


# ---- kỹ thuật + screener ---------------------------------------------------------------------------------------------------
def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


def technicals(close_rows: list[dict]) -> dict[str, dict]:
    """close_rows: [{code, d, ad_close, close, value}] đã sắp theo code,d -> {code: {rsi14, ma20, ma50, above_ma50, avg_value_20d}}."""
    by: dict[str, list[dict]] = {}
    for r in close_rows:
        by.setdefault(r["code"], []).append(r)
    out = {}
    for code, rs in by.items():
        cl = [num(r.get("ad_close")) or num(r.get("close")) for r in rs]
        cl = [c for c in cl if c]
        if len(cl) < 15:
            continue
        ma20 = sum(cl[-20:]) / min(20, len(cl))
        ma50 = sum(cl[-50:]) / len(cl[-50:]) if len(cl) >= 50 else None
        vals = [num(r.get("value")) or 0.0 for r in rs][-20:]
        out[code] = {"rsi14": rsi(cl), "ma20": round(ma20, 2), "ma50": round(ma50, 2) if ma50 else None,
                     "above_ma50": (cl[-1] > ma50) if ma50 else None, "avg_value_20d": sum(vals) / len(vals) if vals else None}
    return out


RANGE_KEYS = ("marketcap", "pe", "pb", "roe", "eps", "div_yield", "beta", "rsi14", "pct", "value", "avg_value_20d", "chg_1m", "chg_3m", "chg_1y", "price")
SORT_KEYS = set(RANGE_KEYS) | {"code", "foreign_net"}


def screener_row(r: dict, tech: dict | None) -> dict:
    t = tech or {}
    dy = num(r.get("div_yield"))
    return {
        "code": r["code"], "name": r.get("short_name") or r.get("name"), "floor": r.get("floor"), "industry": r.get("industry_name"),
        "vn30": bool(r.get("in_vn30")), "price": num(r.get("close")), "pct": num(r.get("pct")), "value": num(r.get("value")),
        "marketcap": num(r.get("marketcap")), "pe": num(r.get("pe")), "pb": num(r.get("pb")), "ps": num(r.get("ps")),
        "eps": eps_est(r), "roe": roe_est(r), "div_yield": round(dy * 100, 2) if dy is not None else None, "beta": num(r.get("beta")),
        "chg_1m": _pc(r.get("chg_1m")), "chg_3m": _pc(r.get("chg_3m")), "chg_1y": _pc(r.get("chg_1y")),
        "hi_52w": num(r.get("hi_52w")), "lo_52w": num(r.get("lo_52w")),
        "rsi14": t.get("rsi14"), "above_ma50": t.get("above_ma50"), "avg_value_20d": t.get("avg_value_20d"),
        "foreign_net": num(r.get("f_net")), "limit": flag(r),
    }


def _pc(x: Any) -> float | None:
    v = num(x)
    return round(v * 100, 2) if v is not None else None


def screen(rows: Iterable[dict], techs: dict[str, dict], filters: dict[str, tuple[float | None, float | None]], *, universe: str = "vn100",
           industry: str | None = None, sort: str = "marketcap", desc: bool = True, limit: int = 50) -> dict:
    """filters: {key: (min, max)} với key thuộc RANGE_KEYS. Mã thiếu dữ liệu của một tiêu chí bị loại khỏi tiêu chí đó."""
    res = []
    for r in rows:
        if not in_universe(r, universe) or r.get("kind") == "ETF":
            continue
        if industry and (r.get("industry_name") or "") != industry:
            continue
        row = screener_row(r, techs.get(r["code"]))
        ok = True
        for k, (lo, hi) in filters.items():
            v = row.get(k)
            if v is None or (lo is not None and v < lo) or (hi is not None and v > hi):
                ok = False
                break
        if ok:
            res.append(row)
    sk = sort if sort in SORT_KEYS else "marketcap"
    if sk == "code":
        res.sort(key=lambda x: x["code"], reverse=desc)
    else:
        have = sorted((x for x in res if x.get(sk) is not None), key=lambda x: x[sk], reverse=desc)
        res = have + [x for x in res if x.get(sk) is None]
    return {"total": len(res), "rows": res[:max(1, min(limit, 500))]}
