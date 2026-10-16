"""Arena paper: xếp hạng chiến lược/kịch bản/mô hình theo kết quả FORWARD-PAPER (lệnh live đã đóng, bỏ replay). Hàm thuần, tất định.
Trung thực: mẫu nhỏ (< MIN_N) KHÔNG xếp hạng, gắn nhãn "chưa đủ mẫu"; kỳ vọng kèm CI95 (phân phối t) và p một phía từ kiểm định
đổi dấu (H0: kỳ vọng = 0, lệnh đã trừ chi phí) — mẫu tiến lên sẽ cho p thật; không "chọn lọc" gì ở đây."""
from __future__ import annotations

import math
import random
from datetime import datetime

MIN_N = 30
NOTE_EMPTY = ("Chưa có lệnh paper live nào đã đóng. Bảng sẽ tự điền khi tín hiệu kích hoạt và lệnh đóng; mẫu dưới "
              f"{MIN_N} lệnh luôn được gắn nhãn \"chưa đủ mẫu\" và không xếp hạng.")
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
         14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
         26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045}


def _tcrit(df: int) -> float:
    return _T975.get(df, 2.042 if df < 40 else 2.021 if df < 60 else 2.0 if df < 120 else 1.98 if df < 1000 else 1.96)


def max_drawdown(rs: list[float]) -> float:
    """Độ lớn dương của mức sụt vốn tối đa (R) trên đường vốn cộng dồn."""
    eq = peak = dd = 0.0
    for x in rs:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return round(dd, 4)


def sign_flip_p(rs: list[float], iters: int = 20000, seed: int = 7) -> float | None:
    """p một phía: xác suất (dưới H0 phân phối đối xứng quanh 0) để kỳ vọng >= quan sát. Chính xác khi n <= 16, ngược lại Monte Carlo seed cố định."""
    n = len(rs)
    if n < 2:
        return None
    obs = sum(rs) - 1e-12
    if n <= 16:
        ge = 0
        for m in range(1 << n):
            if sum(x if m >> i & 1 else -x for i, x in enumerate(rs)) >= obs:
                ge += 1
        return round(ge / (1 << n), 4)
    rng = random.Random(seed)
    ge = sum(1 for _ in range(iters) if sum(x if rng.random() < 0.5 else -x for x in rs) >= obs)
    return round((ge + 1) / (iters + 1), 4)


def row_stats(rs: list[float]) -> dict:
    n = len(rs)
    if n == 0:
        return {"trades": 0, "pnl_r": 0.0, "expectancy_r": None, "ci95": None, "max_dd_r": 0.0, "p_vs_random": None, "win_rate": None}
    m = sum(rs) / n
    ci = None
    if n >= 2:
        sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (n - 1))
        h = _tcrit(n - 1) * sd / math.sqrt(n)
        ci = [round(m - h, 4), round(m + h, 4)]
    return {"trades": n, "pnl_r": round(sum(rs), 4), "expectancy_r": round(m, 4), "ci95": ci, "max_dd_r": max_drawdown(rs),
            "p_vs_random": sign_flip_p(rs), "win_rate": round(sum(1 for x in rs if x > 0) / n, 4)}


def _row(rid: str, name: str, kind: str, rs: list[float], since: str | None) -> dict:
    st = row_stats(rs)
    enough = st["trades"] >= MIN_N
    return {"id": rid, "name": name, "kind": kind, "unit": "R", **st, "since": since, "enough_sample": enough,
            "label": None if enough else "chưa đủ mẫu"}


def _dd_pct(spark: list[dict]) -> float | None:
    idx = [float(p["index"]) for p in spark if p.get("index") is not None]
    if not idx:
        return None
    peak, dd = idx[0], 0.0
    for v in idx:
        peak = max(peak, v)
        dd = max(dd, (peak - v) / peak * 100)
    return round(dd, 3)


def portfolio_row(a: dict) -> dict:
    """Tài khoản paper dạng danh mục (đường vốn, không có lệnh R): ghi nhận để so sánh với đối chứng, KHÔNG xếp hạng."""
    spark = a.get("spark") or []
    days = len(spark)
    tr = a.get("total_return")
    return {"id": "paper:" + str(a.get("account_id")), "name": a.get("name") or a.get("account_id"), "kind": "portfolio", "unit": "%",
            "trades": None, "pnl_r": None, "pnl_pct": None if tr is None else round(float(tr) * 100, 3), "expectancy_r": None, "ci95": None,
            "max_dd_r": None, "max_dd_pct": _dd_pct(spark), "p_vs_random": None, "win_rate": None, "since": a.get("inception"),
            "days": days, "enough_sample": False, "label": "chưa đủ mẫu" if days < 60 else "không xếp hạng (danh mục, không có lệnh R)"}


def build(closed: list[dict], known: dict[str, str], portfolios: list[dict] | None = None) -> dict:
    """closed: [{pattern, closed_at, opened_at, result_r}]; known: id -> tên (thẻ registry kịch bản). Trả {items, ranked, note}."""
    by: dict[str, list[dict]] = {}
    for t in closed:
        if t.get("pattern") and t.get("result_r") is not None:
            by.setdefault(str(t["pattern"]), []).append(t)
    rows = []
    for rid in sorted(set(known) | set(by)):
        ts = sorted(by.get(rid, []), key=lambda t: str(t.get("closed_at")))
        since = min((str(t["opened_at"]) for t in ts if t.get("opened_at")), default=None)
        rows.append(_row(rid, known.get(rid, rid), "pattern", [float(t["result_r"]) for t in ts], since))
    ranked = sorted([r for r in rows if r["enough_sample"]], key=lambda r: r["expectancy_r"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    rest = sorted([r for r in rows if not r["enough_sample"]], key=lambda r: (-r["trades"], r["id"]))
    for r in rest:
        r["rank"] = None
    items = ranked + rest + [portfolio_row(a) for a in (portfolios or [])]
    for r in items:
        r.setdefault("rank", None)
    total = sum(r["trades"] or 0 for r in items if r["kind"] == "pattern")
    return {"items": items, "ranked": len(ranked), "total_trades": total, "min_n": MIN_N,
            "note": NOTE_EMPTY if total == 0 else (f"Chỉ xếp hạng khi đủ {MIN_N} lệnh đóng; dưới ngưỡng là kết quả chưa có ý nghĩa thống kê.")}
