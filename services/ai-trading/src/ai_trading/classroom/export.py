"""Hồ sơ -> YAML kịch bản theo schema 'Dạy kịch bản' (ai_trading.scenario_schema). Không bịa giá trị thiếu: thiếu thì báo lỗi để hỏi tiếp."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import yaml

from ..scenario_schema import ALLOWED_TF, MAX_RULES, SYMBOL, SchemaError, validate
from .extract import fold
from .profile import Profile


@dataclass
class ExportReport:
    ok: bool
    yaml: str = ""
    scenario: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def slug(name: str, n: int = 14) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")
    return (s or "kb")[:n].strip("-") or "kb"


def scenario_id(p: Profile) -> str:
    h = hashlib.sha1((p.room + p.all_text()).encode()).hexdigest()[:4]
    return f"CL-{slug(p.name)}-v{p.version}{h}"[:32]


def export_scenario(p: Profile) -> ExportReport:
    m, errs, warns = p.merged(), [], []
    if m["side"] == "buy":
        errs.append("Schema hiện chỉ hỗ trợ kịch bản Sell; bản Buy cần chờ DSL mở rộng (dùng gợi ý “Đối xứng” để ghi nhận).")
    if m["side"] is None:
        warns.append("Hồ sơ chưa nêu rõ buy/sell: mặc định xuất bản sell.")
    if m["side"] == "both":
        warns.append("Hồ sơ nêu cả buy và sell: chỉ xuất phiên bản sell.")
    syms = [s for s in m["symbols"] if SYMBOL.match(s)][:4]
    tfs = [t for t in m["tfs"] if t in ALLOWED_TF][:3]
    if not syms:
        errs.append("Thiếu mã (ví dụ EURUSD).")
    if not tfs:
        errs.append("Thiếu khung (M15, H1, H4, D1).")
    if not m["rules"]:
        errs.append("Chưa có luật định lượng nhận ra được (nhịp ATR/nến, bóng %, RSI, MA...). Hãy trả lời bước 'điều kiện hình thành' bằng số.")
    if len(m["rules"]) > MAX_RULES:
        warns.append(f"Chỉ lấy {MAX_RULES} luật đầu.")
    lv = m["levels"]
    if "sl" not in lv:
        errs.append("Thiếu SL (theo ATR hoặc trên đỉnh N nến).")
    if "tp_r" not in lv:
        errs.append("Thiếu TP theo bội số R.")
    if errs:
        return ExportReport(False, errors=errs, warnings=warns)
    sl = dict(lv["sl"])
    doc = {"id": scenario_id(p), "name": p.name[:120] if len(p.name) >= 3 else "Kịch bản lớp học", "side": "sell", "family": f"CL-{slug(p.name)}"[:32],
           "summary": (p.current("formation").text if p.current("formation") else "")[:400],
           "notes": f"Xuất từ AI Training Class, hồ sơ phiên bản {p.version}. Chưa kiểm chứng; các phản ví dụ/giả định còn mở: {len(p.assumptions)}.",
           "symbols": syms, "tfs": tfs, "detector": {"rules": m["rules"][:MAX_RULES], "cooldown_bars": 6},
           "levels": {"sl": sl, "tp_r": lv["tp_r"], "max_hold": lv.get("max_hold", 100)}}
    try:
        sc = validate(doc)
    except SchemaError as e:
        return ExportReport(False, errors=[str(e)], warnings=warns)
    low = [k for k in p.answered() if p.current(k).confidence == "thấp"]
    if low:
        warns.append("Các phần độ chắc chắn thấp: " + ", ".join(low))
    return ExportReport(True, yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), sc, [], warns)
