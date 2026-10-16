"""Schema + kiểm tra "Kịch bản mới" (YAML khai báo, KHÔNG chạy mã người dùng): dùng chung API (ai-trading) và worker.

Một kịch bản = luật phát hiện trên nến ĐÃ ĐÓNG (AND các luật) + cách đặt SL/TP gợi ý. CHỈ nghiên cứu/paper, không có đường đặt lệnh.
Chống tấn công YAML: size tối đa, safe_load, cấm anchor/alias (billion laughs), cấm khoá lạ, mọi số có biên.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

MAX_YAML = 16 * 1024
SC_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")
SYMBOL = re.compile(r"^[A-Z][A-Z0-9._]{2,11}$")
IMG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,58}\.(png|jpg|jpeg|webp)$")
ALLOWED_TF = ("M15", "H1", "H4", "D1")
MAX_IMAGES = 5
MAX_IMG_BYTES = 700 * 1024
MAX_SYMBOLS = 4
MAX_RULES = 8
MAX_GRID = 12

_TOP = {"id", "name", "summary", "side", "family", "symbols", "tfs", "detector", "levels", "golden", "images", "notes"}


class SchemaError(ValueError):
    pass


def _num(v: Any, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not (lo <= v <= hi):
        raise SchemaError(f"{what}: cần số trong [{lo}, {hi}]")
    return float(v)


def _int(v: Any, lo: int, hi: int, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise SchemaError(f"{what}: cần số nguyên trong [{lo}, {hi}]")
    return v


def _only(d: dict, allowed: set[str], what: str) -> None:
    extra = set(d) - allowed
    if extra:
        raise SchemaError(f"{what}: khoá không hợp lệ {sorted(map(str, extra))[:3]}")


def _numlist(v: Any, lo: float, hi: float, what: str, maxn: int = 4) -> list[float]:
    vs = v if isinstance(v, list) else [v]
    if not 1 <= len(vs) <= maxn:
        raise SchemaError(f"{what}: 1..{maxn} giá trị")
    return [_num(x, lo, hi, what) for x in vs]


def parse_yaml(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise SchemaError("YAML rỗng")
    if len(text.encode("utf-8")) > MAX_YAML:
        raise SchemaError(f"YAML quá lớn (> {MAX_YAML // 1024} KB)")
    try:
        for ev in yaml.parse(text):
            if isinstance(ev, yaml.AliasEvent) or getattr(ev, "anchor", None):
                raise SchemaError("không cho phép anchor/alias YAML")
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        raise SchemaError("YAML không hợp lệ") from None
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise SchemaError("YAML phải là 1 tài liệu dạng map")
    return docs[0]


# ---- luật phát hiện (mỗi luật: tham số có biên) ----
def _rule(r: Any) -> dict:
    if not isinstance(r, dict) or "rule" not in r:
        raise SchemaError("mỗi luật là map có khoá 'rule'")
    k = r["rule"]
    if k == "move_atr":          # biến động giá >= min ATR trong `bars` nến kết thúc `ago` nến trước nến hiện tại
        _only(r, {"rule", "dir", "bars", "min", "ago"}, "move_atr")
        if r.get("dir") not in ("down", "up"):
            raise SchemaError("move_atr.dir: down|up")
        return {"rule": k, "dir": r["dir"], "bars": _int(r.get("bars"), 2, 60, "move_atr.bars"),
                "min": _num(r.get("min"), 0.3, 40, "move_atr.min"), "ago": _int(r.get("ago", 0), 0, 60, "move_atr.ago")}
    if k == "bear_body":         # nến giảm thân dài
        _only(r, {"rule", "min_atr"}, "bear_body")
        return {"rule": k, "min_atr": _num(r.get("min_atr"), 0.2, 5, "bear_body.min_atr")}
    if k == "bear_engulf":       # nến giảm nhấn chìm thân nến trước
        _only(r, {"rule"}, "bear_engulf")
        return {"rule": k}
    if k == "upper_wick":        # bóng trên >= tỷ lệ biên độ nến
        _only(r, {"rule", "min_ratio"}, "upper_wick")
        return {"rule": k, "min_ratio": _num(r.get("min_ratio"), 0.1, 0.95, "upper_wick.min_ratio")}
    if k == "break_low":         # đóng cửa thủng đáy `bars` nến trước
        _only(r, {"rule", "bars"}, "break_low")
        return {"rule": k, "bars": _int(r.get("bars"), 2, 120, "break_low.bars")}
    if k == "ma":                # đóng cửa trên/dưới MA
        _only(r, {"rule", "side", "kind", "period"}, "ma")
        if r.get("side") not in ("above", "below") or r.get("kind", "ema") not in ("ema", "sma"):
            raise SchemaError("ma: side above|below, kind ema|sma")
        return {"rule": k, "side": r["side"], "kind": r.get("kind", "ema"), "period": _int(r.get("period"), 5, 250, "ma.period")}
    if k == "rsi":
        _only(r, {"rule", "period", "op", "value"}, "rsi")
        if r.get("op") not in (">=", "<="):
            raise SchemaError("rsi.op: >= hoặc <=")
        return {"rule": k, "period": _int(r.get("period", 14), 2, 50, "rsi.period"), "op": r["op"], "value": _num(r.get("value"), 1, 99, "rsi.value")}
    if k == "hours":             # giờ mở nến (UTC) trong [from, to), cho phép vòng qua nửa đêm
        _only(r, {"rule", "from", "to"}, "hours")
        return {"rule": k, "from": _int(r.get("from"), 0, 23, "hours.from"), "to": _int(r.get("to"), 1, 24, "hours.to")}
    raise SchemaError(f"luật không hỗ trợ: {str(k)[:24]}")


def validate(text_or_doc: str | dict, taken_ids: set[str] | None = None) -> dict:
    """Trả scenario đã chuẩn hoá (dict thuần). Ném SchemaError với thông báo tiếng Việt."""
    d = parse_yaml(text_or_doc) if isinstance(text_or_doc, str) else text_or_doc
    _only(d, _TOP, "gốc")
    sid = d.get("id")
    if not isinstance(sid, str) or not SC_ID.match(sid):
        raise SchemaError("id: chữ cái đầu, 3-32 ký tự [A-Za-z0-9_-]")
    if taken_ids and sid in taken_ids:
        raise SchemaError("id đã tồn tại (mỗi lần sửa luật phải là id mới để đếm đúng số lần thử)")
    name = d.get("name")
    if not isinstance(name, str) or not 3 <= len(name) <= 120:
        raise SchemaError("name: 3-120 ký tự")
    summ = str(d.get("summary", ""))[:400]
    notes = str(d.get("notes", ""))[:800]
    if d.get("side", "sell") != "sell":
        raise SchemaError("side: hiện chỉ hỗ trợ 'sell' (mô phỏng paper)")
    fam = d.get("family", sid)
    if not isinstance(fam, str) or not SC_ID.match(fam):
        raise SchemaError("family: cùng dạng id")
    syms = d.get("symbols")
    if not isinstance(syms, list) or not 1 <= len(syms) <= MAX_SYMBOLS or not all(isinstance(s, str) and SYMBOL.match(s) for s in syms):
        raise SchemaError(f"symbols: 1..{MAX_SYMBOLS} mã chữ hoa")
    tfs = d.get("tfs")
    if not isinstance(tfs, list) or not 1 <= len(tfs) <= 3 or not all(t in ALLOWED_TF for t in tfs):
        raise SchemaError(f"tfs: 1..3 khung thuộc {list(ALLOWED_TF)}")
    det = d.get("detector")
    if not isinstance(det, dict):
        raise SchemaError("detector: bắt buộc")
    _only(det, {"rules", "cooldown_bars"}, "detector")
    rules = det.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= MAX_RULES:
        raise SchemaError(f"detector.rules: 1..{MAX_RULES} luật")
    lv = d.get("levels")
    if not isinstance(lv, dict):
        raise SchemaError("levels: bắt buộc")
    _only(lv, {"sl", "tp_r", "max_hold"}, "levels")
    sl = lv.get("sl")
    if not isinstance(sl, dict) or sl.get("type") not in ("swing_high", "atr"):
        raise SchemaError("levels.sl.type: swing_high|atr")
    if sl["type"] == "swing_high":
        _only(sl, {"type", "bars", "buffer_atr"}, "levels.sl")
        slc = {"type": "swing_high", "bars": _int(sl.get("bars"), 2, 120, "sl.bars"), "values": _numlist(sl.get("buffer_atr", 0.25), 0.0, 3.0, "sl.buffer_atr", 3)}
    else:
        _only(sl, {"type", "mult"}, "levels.sl")
        slc = {"type": "atr", "values": _numlist(sl.get("mult"), 0.3, 8.0, "sl.mult", 3)}
    tps = _numlist(lv.get("tp_r"), 0.5, 6.0, "levels.tp_r", 4)
    if len(tps) * len(slc["values"]) > MAX_GRID:
        raise SchemaError(f"lưới tham số tối đa {MAX_GRID} cấu hình")
    golden = d.get("golden") or []
    if not isinstance(golden, list) or len(golden) > 5:
        raise SchemaError("golden: tối đa 5 mục")
    gl = []
    for g in golden:
        if not isinstance(g, dict):
            raise SchemaError("golden: mỗi mục là map")
        _only(g, {"image", "symbol", "tf", "bar_ts", "expect"}, "golden")
        if not (isinstance(g.get("symbol"), str) and SYMBOL.match(g["symbol"])) or g.get("tf") not in ALLOWED_TF:
            raise SchemaError("golden: symbol/tf không hợp lệ")
        ts = str(g.get("bar_ts", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(Z|\+00:00)?", ts):
            raise SchemaError("golden.bar_ts: dạng YYYY-MM-DDTHH:MM (UTC, giờ mở nến kích hoạt)")
        img = g.get("image")
        if img is not None and not (isinstance(img, str) and IMG_NAME.match(img)):
            raise SchemaError("golden.image: tên tệp ảnh không hợp lệ")
        gl.append({"image": img, "symbol": g["symbol"], "tf": g["tf"], "bar_ts": ts, "expect": bool(g.get("expect", True))})
    images = d.get("images") or []
    if not isinstance(images, list) or len(images) > MAX_IMAGES or not all(isinstance(i, str) and IMG_NAME.match(i) for i in images):
        raise SchemaError(f"images: tối đa {MAX_IMAGES} tên tệp ảnh (png/jpg/webp)")
    return {
        "id": sid, "name": name, "summary": summ, "notes": notes, "side": "sell", "family": fam, "symbols": list(syms), "tfs": list(tfs),
        "detector": {"rules": [_rule(r) for r in rules], "cooldown_bars": _int(det.get("cooldown_bars", 6), 0, 100, "cooldown_bars")},
        "levels": {"sl": slc, "tp_r": tps, "max_hold": _int(lv.get("max_hold", 100), 10, 300, "max_hold")},
        "golden": gl, "images": list(images),
    }


def grid_of(sc: dict) -> list[dict]:
    """Lưới cấu hình (tp_r × tham số SL) — thứ tự cố định; DSR/PBO tính theo kích thước lưới này."""
    return [{"tp_r": tp, "sl_param": v} for tp in sc["levels"]["tp_r"] for v in sc["levels"]["sl"]["values"]]


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None
