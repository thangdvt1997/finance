"""Phan tich / dinh dang gia tri lich kinh te ('0.3%', '150K', '7.2M', '4.5|1.8') va tinh 'surprise'. Ham thuan, de test."""
from __future__ import annotations

import math
import re

_NUM = re.compile(r"^\s*[<>~]?\s*([+-]?\d+(?:[.,]\d+)?)\s*([%KMBT]?)\s*$", re.I)
MULT = {"": 1.0, "%": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_value(s) -> tuple[float, str] | None:
    """'0.3%' -> (0.3, '%'); '150K' -> (150.0, 'K'); '<0.1%' -> (0.1, '%'); '4.5|1.8' (bid-to-cover|...) -> (4.5, '')."""
    if s is None:
        return None
    t = str(s).strip().split("|")[0].replace("−", "-")
    m = _NUM.match(t)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return v, m.group(2).upper()


def to_base(v: float, unit: str) -> float:
    return v * MULT.get(unit, 1.0)


def decimals_of(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"\d[.,](\d+)", str(s).split("|")[0])
    return len(m.group(1)) if m else 0


def format_value(v: float, unit: str, decimals: int) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    v = round(v, decimals)
    if v == 0:
        v = 0.0  # tranh '-0.0'
    return f"{v:.{decimals}f}{unit}"


def format_like(v: float, unit: str, template: str | None, default_decimals: int) -> str:
    """Dinh dang gia tri `v` (don vi `unit`) theo mau cua forecast (suffix + so chu so thap phan) de so sanh truc quan."""
    p = parse_value(template)
    if p is None:
        return format_value(v, unit, default_decimals)
    _, tu = p
    if tu != unit and not (tu in ("", "%") and unit in ("", "%")):
        v = to_base(v, unit) / MULT.get(tu, 1.0)
        unit = tu
    return format_value(v, unit if tu else "", decimals_of(template) or 0)


def pick_rule(title: str, rules: list[dict]) -> dict:
    for r in rules or []:
        if re.search(r["match"], title, re.I):
            return r
    return {}


def surprise(actual, forecast, title: str, cfg: dict | None = None) -> dict | None:
    """surprise = actual - forecast (don vi cua forecast); z = surprise / scale; verdict theo 'polarity' cua chi so.

    polarity +1: cao hon du bao = tot cho dong tien (CPI, viec lam, ban le...); -1: cao hon = xau (that nghiep, xin tro cap).
    scale: do lech 'dien hinh' (config theo quy tac, mac dinh: % -> 0.1 diem %, con lai 10% |forecast|). verdict: good|bad|neutral.
    """
    a, f = parse_value(actual), parse_value(forecast)
    if a is None or f is None:
        return None
    cfg = cfg or {}
    rule = pick_rule(title, cfg.get("rules", []))
    fu = f[1]
    diff = (to_base(a[0], a[1]) - to_base(f[0], fu)) / MULT.get(fu, 1.0)
    if rule.get("scale") is not None:
        scale = float(rule["scale"])
    elif fu in ("%", ""):
        scale = float(cfg.get("default_scale_pct", 0.1)) if fu == "%" else max(abs(f[0]) * 0.1, 0.01)
    else:
        scale = max(abs(f[0]) * 0.1, 1e-9)
    z = diff / scale if scale else 0.0
    pol = int(rule.get("polarity", cfg.get("default_polarity", 1)))
    thr = float(cfg.get("inline_z", 0.3))
    direction = "inline" if abs(z) < thr else ("above" if diff > 0 else "below")
    verdict = "neutral" if direction == "inline" else ("good" if diff * pol > 0 else "bad")
    return {"value": round(diff, 6), "z": round(z, 2), "direction": direction, "verdict": verdict, "polarity": pol, "unit": fu}
