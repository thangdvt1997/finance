"""Chuan hoa + kiem tra annotation. Moi diem la {"t": ISO|epoch, "p": gia} hoac {"i": chi-so-nen, "p": gia}.
Schema day du: docs/PATTERNS_SELL.md muc 'Render'."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

LEVEL_KINDS = {"entry", "sl", "tp"}
LINE_KINDS = {"trend", "boundary", "wedge", "neckline", "horizontal"}


class SchemaError(ValueError):
    pass


def to_epoch(t: Any) -> float:
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, datetime):
        d = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        return d.timestamp()
    if isinstance(t, str):
        s = t.strip().replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
        except ValueError as e:
            raise SchemaError(f"thoi gian khong hop le: {t!r}") from e
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    raise SchemaError(f"thoi gian khong hop le: {t!r}")


def norm_candles(candles: list) -> list[dict]:
    if not candles:
        raise SchemaError("candles rong")
    out = []
    for k, c in enumerate(candles):
        if isinstance(c, (list, tuple)):
            t, o, h, l, cl = c[:5]
        else:
            t = c.get("t", c.get("ts_open", c.get("ts")))
            o, h, l, cl = c["o"], c["h"], c["l"], c["c"]
        o, h, l, cl = float(o), float(h), float(l), float(cl)
        if h < max(o, cl) - 1e-9 or l > min(o, cl) + 1e-9:
            raise SchemaError(f"nen #{k} khong nhat quan OHLC")
        out.append({"t": to_epoch(t), "o": o, "h": h, "l": l, "c": cl})
    ts = [c["t"] for c in out]
    if any(b <= a for a, b in zip(ts, ts[1:])):
        raise SchemaError("candles phai tang dan theo thoi gian, khong trung")
    return out


def _pt(d: Any, where: str) -> dict:
    if not isinstance(d, dict) or "p" not in d or not ("t" in d or "i" in d):
        raise SchemaError(f"{where}: diem can {{t|i, p}}")
    out = {"p": float(d["p"])}
    if "i" in d:
        out["i"] = float(d["i"])
    else:
        out["t"] = to_epoch(d["t"])
    return out


def validate_annotations(ann: dict | None) -> dict:
    """Tra ve ban chuan hoa (thoi gian -> epoch). Nem SchemaError neu sai."""
    a = dict(ann or {})
    r: dict[str, Any] = {"title": dict(a.get("title") or {}), "watermark": a.get("watermark", "Pattern Lab - mo phong")}
    r["tz_offset_h"] = float(a.get("tz_offset_h", 0))
    r["style"] = dict(a.get("style") or {})
    r["legs"] = []
    for k, g in enumerate(a.get("legs") or []):
        leg = {"a": _pt(g["from"], f"legs[{k}].from"), "b": _pt(g["to"], f"legs[{k}].to"),
               "arrow": bool(g.get("arrow", False)), "label": g.get("label")}
        if g.get("label_at"):
            leg["label_at"] = _pt(g["label_at"], f"legs[{k}].label_at")
        r["legs"].append(leg)
    r["lines"] = []
    for k, g in enumerate(a.get("lines") or []):
        kind = g.get("kind", "trend")
        if kind not in LINE_KINDS:
            raise SchemaError(f"lines[{k}].kind={kind!r} khong hop le")
        r["lines"].append({"kind": kind, "a": _pt(g["from"], f"lines[{k}].from"), "b": _pt(g["to"], f"lines[{k}].to"),
                           "arrow": bool(g.get("arrow", False)), "label": g.get("label"),
                           "label_at": _pt(g["label_at"], "label_at") if g.get("label_at") else None})
    r["zones"] = []
    for k, g in enumerate(a.get("zones") or []):
        r["zones"].append({"a": _pt(g["from"], f"zones[{k}].from"), "b": _pt(g["to"], f"zones[{k}].to"),
                           "label": g.get("label"), "fill": bool(g.get("fill", False))})
    r["arrows"] = []
    for k, g in enumerate(a.get("arrows") or []):
        r["arrows"].append({"a": _pt(g["from"], f"arrows[{k}].from"), "b": _pt(g["to"], f"arrows[{k}].to"),
                            "label": g.get("label")})
    r["levels"] = []
    for k, g in enumerate(a.get("levels") or []):
        kind = g.get("kind")
        if kind not in LEVEL_KINDS:
            raise SchemaError(f"levels[{k}].kind phai thuoc {sorted(LEVEL_KINDS)}")
        r["levels"].append({"kind": kind, "price": float(g["price"]), "label": g.get("label")})
    r["labels"] = [{"at": _pt(g["at"], f"labels[{k}].at"), "text": str(g["text"])} for k, g in enumerate(a.get("labels") or [])]
    return r
