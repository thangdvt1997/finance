"""Dựng annotation cho pattern-render từ payload `pattern.signal` + nến ĐÃ ĐÓNG (không look-ahead: chỉ nến <= bar_ts).

Ưu tiên `payload["points"]` (nếu pattern-engine phát toạ độ đỉnh/đáy). Nếu không có, suy ra từ `setup_id`
(chứa thời điểm pivot neo, dạng YYYYmmddTHHMM) + `levels` (wave_high, neckline, support, box_low...).
Nhãn chỉ ASCII/ký hiệu đơn giản, KHÔNG chứa tên nguồn dữ liệu.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

TS_RE = re.compile(r"(\d{8}T\d{4})")
STATE_LABEL = {"forming": "dang hinh thanh", "armed": "san sang (cho nen kich hoat)", "triggered": "DA KICH HOAT", "invalid": "da huy"}


def parse_ts(s: str | datetime) -> datetime:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def anchor_times(setup_id: str) -> list[datetime]:
    return [datetime.strptime(m, "%Y%m%dT%H%M").replace(tzinfo=timezone.utc) for m in TS_RE.findall(setup_id or "")]


def _idx_at(cs: list[dict], t: datetime) -> int | None:
    e = t.timestamp()
    best, bd = None, None
    for i, c in enumerate(cs):
        d = abs(c["t"] - e)
        if bd is None or d < bd:
            best, bd = i, d
    return best


def _nearest_price_idx(cs: list[dict], lo: int, hi: int, price: float, key: str) -> int:
    lo, hi = max(0, lo), min(len(cs) - 1, hi)
    if hi < lo:
        return max(0, min(len(cs) - 1, lo))
    return min(range(lo, hi + 1), key=lambda i: abs(cs[i][key] - price))


def window_start(payload: dict, cs_times: list[float], bars_before: int) -> int:
    """Chỉ số nến bắt đầu vẽ: trước điểm neo sớm nhất `bars_before` nến (neo = points/setup_id)."""
    ts = [parse_ts(p["t"]).timestamp() for p in payload.get("points") or [] if p.get("t")]
    ts += [t.timestamp() for t in anchor_times(payload.get("setup_id", ""))]
    if not ts or not cs_times:
        return max(0, len(cs_times) - 160)
    first = min(ts)
    i = next((k for k, t in enumerate(cs_times) if t >= first), len(cs_times) - 1)
    return max(0, i - bars_before)


def build(payload: dict, cs: list[dict], tz_offset_h: float = 7) -> tuple[dict, list[dict]]:
    """cs = nến chuẩn hoá [{t(epoch),o,h,l,c}] tăng dần, nến cuối = nến làm đổi trạng thái.
    Trả (annotations cho pattern_render, marks [{t ISO, p, label, kind}] cho biểu đồ tương tác)."""
    pat, state = payload.get("pattern", "KB"), payload.get("state", "")
    lv = {k: v for k, v in (payload.get("levels") or {}).items() if isinstance(v, (int, float))}
    n = len(cs)
    last = n - 1
    bar_ts = parse_ts(payload.get("bar_ts") or datetime.fromtimestamp(cs[-1]["t"], timezone.utc))
    local = (bar_ts + timedelta(hours=tz_offset_h)).strftime("%Y-%m-%d %H:%M")
    ann: dict = {
        "title": {"symbol": payload.get("symbol", ""), "tf": payload.get("tf", ""), "scenario": f"{pat} SELL - {STATE_LABEL.get(state, state)}",
                  "time": f"{local} GMT{tz_offset_h:+g}"},
        "legs": [], "lines": [], "arrows": [], "labels": [], "levels": [], "tz_offset_h": tz_offset_h,
    }
    marks: list[dict] = []

    def iso(i: int) -> str:
        return datetime.fromtimestamp(cs[i]["t"], timezone.utc).isoformat()

    def mark(i: int, p: float, label: str, kind: str):
        marks.append({"t": iso(i), "p": round(float(p), 6), "label": label, "kind": kind})

    pts: list[tuple[int, float, str]] = []
    if payload.get("points"):
        for p in payload["points"]:
            try:
                i = _idx_at(cs, parse_ts(p["t"]))
            except Exception:  # noqa: BLE001
                continue
            if i is not None:
                pts.append((i, float(p["p"]), str(p.get("label", ""))[:12]))
    else:
        anc = [_idx_at(cs, t) for t in anchor_times(payload.get("setup_id", ""))]
        anc = [a for a in anc if a is not None]
        if pat in ("KB-1", "KB-2", "KB-4") and anc:
            l1 = anc[0]
            if "wave_high" in lv:
                h0 = _nearest_price_idx(cs, l1 - 120, l1 - 1, lv["wave_high"], "h")
                pts.append((h0, cs[h0]["h"], ""))
            pts.append((l1, lv.get("wave_low", cs[l1]["l"]), "(1)"))
            if len(anc) > 1:
                pts.append((anc[1], cs[anc[1]]["h"], "(2)"))
        elif pat == "KB-3" and anc:
            hd = anc[0]
            if "left_shoulder" in lv:
                ls = _nearest_price_idx(cs, hd - 80, hd - 1, lv["left_shoulder"], "h")
                pts.append((ls, cs[ls]["h"], "LS"))
            pts.append((hd, lv.get("head", cs[hd]["h"]), "H"))
            if "right_shoulder" in lv:
                rs = _nearest_price_idx(cs, hd + 1, last, lv["right_shoulder"], "h")
                pts.append((rs, cs[rs]["h"], "RS"))
    pts.sort(key=lambda x: x[0])
    on_leg = pat != "KB-3"             # KB-1/2/4: nhãn "(n)" cạnh sóng như ảnh mẫu; KB-3: nhãn LS/H/RS tại điểm
    for a, b in zip(pts, pts[1:]):
        if b[0] > a[0]:
            ann["legs"].append({"from": {"i": a[0], "p": a[1]}, "to": {"i": b[0], "p": b[1]},
                                "label": (b[2] or None) if on_leg else None, "arrow": on_leg and b is pts[-1]})
    for i, p, lb in pts:
        if lb:
            mark(i, p, lb, "pivot")
            if not on_leg or len(pts) == 1:
                ann["labels"].append({"at": {"i": i, "p": p}, "text": lb})
    first = pts[0][0] if pts else max(0, last - 60)
    after = next((i for i, _, lb in pts if lb == "(2)"), None)        # KB-2: cạnh nêm chỉ vẽ từ đỉnh hồi (2) tới nến hiện tại
    after = after if after is not None else max(first, last - 40)
    for key, kind, lb, st in (("neckline", "neckline", "neckline", first), ("support", "boundary", None, after),
                              ("resistance", "boundary", None, after), ("box_low", "horizontal", "box", first)):
        if key in lv and st < last:
            ann["lines"].append({"kind": kind, "from": {"i": st, "p": lv[key]}, "to": {"i": last, "p": lv[key]}, "label": lb})
    if state == "triggered":
        h = cs[last]["h"]
        rng = max(1e-9, max(c["h"] for c in cs) - min(c["l"] for c in cs))
        ann["arrows"].append({"from": {"i": last + 3, "p": h + rng * 0.08}, "to": {"i": last, "p": h + rng * 0.005}, "label": "SELL"})
        mark(last, cs[last]["c"], "SELL", "trigger")
    for k, kind, lb in (("entry", "entry", "Entry"), ("sl", "sl", "SL"), ("tp_1r", "tp", "TP1"), ("tp_2r", "tp", "TP2"), ("tp_3r", "tp", "TP3")):
        if k in lv:
            ann["levels"].append({"kind": kind, "price": lv[k], "label": lb})
    for k in ("legs", "lines", "arrows", "labels", "levels"):
        for it in ann[k]:
            if it.get("label") is None:
                it.pop("label", None)
    return ann, marks
