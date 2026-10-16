"""Trích xuất CÓ CẤU TRÚC tất định từ câu trả lời tự do (regex trên bản bỏ dấu). LLM không tham gia. Kết quả dùng cho độ chắc chắn + xuất YAML."""
from __future__ import annotations

import re
import unicodedata

CCY = {"EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "XAU", "XAG", "BTC", "ETH"}
_N = r"(\d+(?:[.,]\d+)?)"
VAGUE = ("tuy", "cam giac", "khoang", "kha kha", "chung chung", "khong chac", "tuy y", "nhin thay", "truc quan", "kiem kiem", "gan gan", "hinh nhu", "co the")
SKIP = ("bo qua", "khong biet", "chua ro", "chua nghi", "tam thoi chua", "khong co", "skip", "n/a", "pass")


def fold(s: str) -> str:
    t = unicodedata.normalize("NFKD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in t if not unicodedata.combining(c))


def f(x: str) -> float:
    return float(x.replace(",", "."))


def numbers(text: str) -> list[float]:
    return [f(m) for m in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?", text or "")]


def is_skip(text: str) -> bool:
    t = fold(text).strip()
    return len(t) < 40 and any(t.startswith(k) or t == k for k in SKIP)


def vague(text: str) -> bool:
    t = fold(text)
    return any(w in t for w in VAGUE)


def symbols(text: str) -> list[str]:
    out: list[str] = []
    for m in re.findall(r"\b[A-Z]{6}\b", text or ""):
        if m[:3] in CCY and m[3:] in CCY and m not in out:
            out.append(m)
    return out


def timeframes(text: str) -> list[str]:
    t = fold(text)
    out: list[str] = []
    for pat, tf in ((r"\bm15\b|\b15\s*(?:phut|m\b|min)", "M15"), (r"\bh1\b|\b1\s*(?:gio|h\b)|\bhourly\b", "H1"), (r"\bh4\b|\b4\s*(?:gio|h\b)", "H4"),
                    (r"\bd1\b|\bdaily\b|\bkhung\s+ngay\b|\b1d\b", "D1")):
        if re.search(pat, t) and tf not in out:
            out.append(tf)
    return out


def side_of(text: str) -> str | None:
    t = fold(text)
    s = bool(re.search(r"\bsell\b|\bshort\b|kich ban ban\b|lenh ban\b|(?<!kich )\bban\b(?!\s*(?:kinh|do))", t))
    b = bool(re.search(r"\bbuy\b|kich ban mua\b|lenh mua\b|(?<!qua )\bmua\b(?!\s*(?:vao\s+)?(?:khi|lai))", t))
    return "both" if s and b else "sell" if s else "buy" if b else None


def rules_of(text: str) -> list[dict]:
    """Luật theo schema DSL hiện có (chỉ những gì khớp rõ ràng)."""
    t = fold(text)
    out: list[dict] = []
    m = re.search(r"(tang|giam|rally|up|down)[^.;\n]{0,40}?" + _N + r"\s*atr[^.;\n]{0,30}?(\d+)\s*nen", t) or None
    if m:
        out.append({"rule": "move_atr", "dir": "up" if m.group(1) in ("tang", "rally", "up") else "down", "bars": int(m.group(3)), "min": f(m.group(2))})
    else:
        m = re.search(r"(tang|giam|rally)[^.;\n]{0,30}?(\d+)\s*nen[^.;\n]{0,30}?" + _N + r"\s*atr", t)
        if m:
            out.append({"rule": "move_atr", "dir": "up" if m.group(1) in ("tang", "rally") else "down", "bars": int(m.group(2)), "min": f(m.group(3))})
    m = re.search(r"bong tren[^.;\n]{0,30}?" + _N + r"\s*%", t)
    if m:
        out.append({"rule": "upper_wick", "min_ratio": round(f(m.group(1)) / 100, 4)})
    if re.search(r"nen giam[^.;\n]{0,30}?than[^.;\n]{0,25}?" + _N + r"\s*atr|than[^.;\n]{0,25}?" + _N + r"\s*atr[^.;\n]{0,20}nen giam", t):
        m = re.search(r"than[^.;\n]{0,25}?" + _N + r"\s*atr", t)
        out.append({"rule": "bear_body", "min_atr": f(m.group(1))})
    if re.search(r"nhan chim|engulf", t):
        out.append({"rule": "bear_engulf"})
    m = re.search(r"(?:thung|pha|break)[^.;\n]{0,20}?day[^.;\n]{0,15}?(\d+)\s*nen|day\s*(\d+)\s*nen", t)
    if m:
        out.append({"rule": "break_low", "bars": int(m.group(1) or m.group(2))})
    m = re.search(r"(duoi|tren)\s*(ema|sma|ma)\s*(\d+)", t)
    if m:
        out.append({"rule": "ma", "side": "below" if m.group(1) == "duoi" else "above", "kind": "sma" if m.group(2) == "sma" else "ema", "period": int(m.group(3))})
    m = re.search(r"rsi\s*(?:\(?(\d+)\)?)?[^.;\n]{0,15}?(>=|<=|>|<|tren|duoi|lon hon|nho hon)\s*" + _N, t)
    if m:
        up = m.group(2) in (">=", ">", "tren", "lon hon")
        out.append({"rule": "rsi", "period": int(m.group(1) or 14), "op": ">=" if up else "<=", "value": f(m.group(3))})
    elif "rsi" in t and "qua mua" in t:
        out.append({"rule": "rsi", "period": 14, "op": ">=", "value": 70.0})
    m = re.search(r"(?:phien|gio|utc|hours)[^.;\n]{0,20}?(\d{1,2})\s*(?:h|gio)?\s*(?:-|den)\s*(\d{1,2})\b|(\d{1,2})\s*(?:h|gio)?\s*(?:-|den)\s*(\d{1,2})\s*(?:h\b|gio|utc)", t)
    if m:
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if 0 <= int(a) <= 23 and 1 <= int(b) <= 24 and int(a) != int(b):
            out.append({"rule": "hours", "from": int(a), "to": int(b)})
    return out


def levels_of(text: str) -> dict:
    t = fold(text)
    lv: dict = {}
    m = re.search(r"(?:tren dinh|swing high|dinh)[^.;\n]{0,20}?(\d+)\s*nen", t)
    if m and re.search(r"\bsl\b|cat lo|stop", t):
        buf = re.search(r"(?:\+|cong|dem|buffer)[^.;\n]{0,10}?" + _N + r"\s*atr", t)
        lv["sl"] = {"type": "swing_high", "bars": int(m.group(1)), "buffer_atr": f(buf.group(1)) if buf else 0.25}
    else:
        m = re.search(r"(?:\bsl\b|cat lo|stop[\s-]?loss)[^.;\n]{0,40}?" + _N + r"\s*atr", t)
        if m:
            lv["sl"] = {"type": "atr", "mult": f(m.group(1))}
    m = re.search(r"(?:\btp\b|chot loi|muc tieu|take[\s-]?profit)([^\n]{0,80})", t)
    if m:
        rs = [f(x) for x in re.findall(_N + r"\s*r\b", m.group(1))]
        if rs:
            lv["tp_r"] = rs[:4]
    m = re.search(r"(?:giu toi da|toi da|max hold|het han)[^.;\n]{0,15}?(\d+)\s*nen", t)
    if m:
        lv["max_hold"] = int(m.group(1))
    return lv


def extract(text: str) -> dict:
    d: dict = {"numbers": numbers(text), "vague": vague(text)}
    for k, v in (("symbols", symbols(text)), ("tfs", timeframes(text)), ("rules", rules_of(text)), ("levels", levels_of(text))):
        if v:
            d[k] = v
    s = side_of(text)
    if s:
        d["side"] = s
    return d


def confidence(text: str, quantitative: bool, fields: dict) -> str:
    """cao/vừa/thấp tất định. Câu mơ hồ ('khoảng', 'cảm giác'...) không bao giờ 'cao'."""
    n, ln = len(fields.get("numbers", [])), len((text or "").strip())
    vg = bool(fields.get("vague"))
    if quantitative:
        if (n >= 2 or fields.get("rules") or fields.get("levels")) and not vg and ln >= 25:
            return "cao"
        if n >= 1 or ln >= 40:
            return "vừa"
        return "thấp"
    if ln >= 80 and not vg:
        return "cao"
    if ln >= 30:
        return "vừa"
    return "thấp"
