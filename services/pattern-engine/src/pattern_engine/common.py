"""Khối dựng dùng chung cho các kịch bản: sóng dẫn hướng, nến nhấn chìm, cụm nén, đường xu hướng, mức SL/TP gợi ý."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .series import Series
from .zigzag import Pivot


@dataclass
class Ctx:
    s: Series
    pv: list[Pivot]   # pivot đã xác nhận + cực trị tạm thời, xen kẽ H/L
    i: int            # chỉ số nến đã đóng mới nhất
    cache: dict = field(default_factory=dict)  # bộ nhớ đệm sóng dẫn (khoá theo pivot -> không đổi theo thời gian)
    fine: list[Pivot] | None = None            # pivot thang MỊN nhất (chi tiết bên trong vùng tích luỹ); mặc định = pv


@dataclass
class Setup:
    pattern: str
    key: str
    state: str                       # forming | armed
    steps: list[dict]
    score: float
    levels: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)
    anchor_i: int = 0
    last_i: int = 0                  # nến cuối cùng thuộc cấu trúc (để hết hạn)
    points: list[dict] = field(default_factory=list)   # toạ độ pivot để vẽ [{label,t ISO,p}] — chỉ hiển thị, không dùng cho logic

    @property
    def family(self) -> str:
        """'KB-2:<ts đáy neo>' — các thang swing khác nhau của cùng 1 neo thuộc cùng 1 họ (chỉ phát 1 chuỗi sự kiện/họ)."""
        return ":".join(self.key.split(":")[:2])


def step(sid: int, label: str, ok: bool, detail: str = "", q: float | None = None) -> dict:
    return {"id": sid, "label": label, "ok": bool(ok), "detail": detail, "q": (1.0 if ok else 0.0) if q is None else float(q)}


def closeness(value: float, target: float, tol: float) -> float:
    return max(0.0, 1.0 - abs(value - target) / tol) if tol > 0 else 0.0


def score_of(steps: list[dict], total: int | None = None) -> float:
    total = total or len(steps)
    return round(100.0 * sum(st["q"] if st["ok"] else 0.0 for st in steps) / total, 1)


# ---------------------------------------------------------------------------- sóng dẫn hướng
def lead_wave(c: Ctx, h0: Pivot, l1: Pivot, P: dict) -> dict | None:
    """Sóng dẫn hướng giảm h0 -> l1. Trả None nếu không đạt. Chỉ dùng nến <= l1.i."""
    s = c.s
    if l1.i <= h0.i or h0.price <= l1.price:
        return None
    height = h0.price - l1.price
    atr = s.atr[l1.i]
    hn = height / atr
    if hn < P["lead_min_atr"]:
        return None
    ck = (P.get("_id"), h0.i, h0.price, l1.i, l1.price)
    if ck in c.cache:
        return c.cache[ck]
    c.cache[ck] = r = _lead_wave(c, h0, l1, P, height, hn)
    return r


def _lead_wave(c: Ctx, h0: Pivot, l1: Pivot, P: dict, height: float, hn: float) -> dict | None:
    s = c.s
    if s.hi(h0.i, l1.i) > h0.price + 1e-12 or s.lo(h0.i, l1.i) < l1.price - 1e-12:
        return None  # h0 phải là đỉnh cao nhất, l1 đáy thấp nhất của nhịp
    a = h0.i + 1
    w = int(P.get("lead_impulse_bars", 0))
    b = l1.i if w <= 0 else min(l1.i, h0.i + w)
    n = b - a + 1
    if n < 3:
        return None
    longred = s.longred_count(a, b)
    green = s.green_body_share(a, b)
    if longred < P["lead_min_long_red"] or green > P["lead_max_green"]:
        return None
    return {"h0": h0, "l1": l1, "height": height, "hn": hn, "longred": longred, "green": green, "bars": l1.i - h0.i}


def all_leads(c: Ctx, pv: list[Pivot], k: int, P: dict) -> list[dict]:
    """Mọi sóng dẫn hợp lệ kết thúc tại đáy pv[k] (đỉnh h0 là pivot trước đó), sắp theo độ cao giảm dần."""
    l1 = pv[k]
    out = []
    lo = max(0, k - int(P.get("lead_max_pivots_back", 14)))
    for j in range(k - 1, lo - 1, -1):
        h0 = pv[j]
        if not h0.is_high:
            continue
        r = lead_wave(c, h0, l1, P)
        if r:
            out.append(r)
    out.sort(key=lambda r: -r["height"])
    return out


def best_lead(c: Ctx, k: int, P: dict) -> dict | None:
    """Với l1 = c.pv[k] (đáy), sóng dẫn hợp lệ DÀI NHẤT."""
    ls = all_leads(c, c.pv, k, P)
    return ls[0] if ls else None


# ---------------------------------------------------------------------------- nến
def bear_engulf(s: Series, i: int, P: dict) -> tuple[bool, dict]:
    """Nhấn chìm giảm tại nến i (đã đóng): thân đỏ dài, bao thân nến trước, đóng dưới đáy nến trước."""
    if i < 1:
        return False, {}
    atr = s.atr_ref(i)
    eps = float(P.get("engulf_eps_atr", 0.1)) * atr
    body = s.o[i] - s.c[i]
    bn = body / atr
    pt, pb = max(s.o[i - 1], s.c[i - 1]), min(s.o[i - 1], s.c[i - 1])
    ok = (body > 0 and bn >= P["trigger_body_atr"] and s.o[i] >= pt - eps and s.c[i] <= pb + eps and s.c[i] < s.l[i - 1])
    return ok, {"body_atr": round(bn, 2)}


def small_cluster(s: Series, i: int, P: dict) -> tuple[bool, dict]:
    """Cụm n nến thân nhỏ liên tiếp kết thúc tại nến i, biên độ cụm hẹp."""
    n = int(P.get("cluster_bars", 3))
    if i - n + 1 < 1:
        return False, {}
    a = i - n + 1
    atr = s.atr_ref(i)
    bodies = [s.body(j) / s.atr_ref(j) for j in range(a, i + 1)]
    rng = (s.hi(a, i) - s.lo(a, i)) / atr
    ok = max(bodies) <= P["small_body_atr"] and rng <= P["cluster_range_atr"]
    return ok, {"max_body_atr": round(max(bodies), 2), "range_atr": round(rng, 2), "hi": s.hi(a, i), "lo": s.lo(a, i)}


def linfit(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Hồi quy tuyến tính bình phương tối thiểu y = a + b·(x - x0). Trả (b, a, x0) với x0 = x đầu."""
    x0 = pts[0][0]
    n = len(pts)
    mx = sum(x - x0 for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - x0 - mx) ** 2 for x, _ in pts)
    b = sum((x - x0 - mx) * (y - my) for x, y in pts) / sxx if sxx > 0 else 0.0
    return b, my - b * mx, x0


def line_through(a: Pivot, b: Pivot) -> tuple[float, float]:
    """(độ dốc, y tại x=a.i) của đường qua hai pivot."""
    dx = b.i - a.i
    return ((b.price - a.price) / dx if dx else 0.0), a.price


def line_at(line: tuple[float, float], x0: int, x: int) -> float:
    return line[1] + line[0] * (x - x0)


# ---------------------------------------------------------------------------- mức gợi ý (chỉ thông tin)
def suggest_levels(s: Series, i: int, top: float, P: dict, extra: dict[str, float] | None = None) -> dict[str, float]:
    atr = s.atr_ref(i)
    entry = s.c[i]
    sl = top + float(P.get("sl_buffer_atr", 0.25)) * atr
    r = sl - entry
    lv = {"entry": entry, "sl": sl, "r": r, "atr": atr}
    for m in P.get("tp_r", [1.0, 2.0, 3.0]):
        lv[f"tp_{m:g}r"] = entry - m * r
    if extra:
        lv.update(extra)
    return lv
