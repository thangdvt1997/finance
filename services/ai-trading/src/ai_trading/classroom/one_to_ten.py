"""'Học 1 hiểu 10': từ hồ sơ sinh biến thể/đối xứng/khung-mã khác/kịch bản liên quan-đối lập/phản ví dụ/điều kiện biên/giả định ngầm.
Phần tất định do mã; LLM (tuỳ chọn) chỉ gợi ý thêm, đánh dấu 'chưa kiểm chứng'."""
from __future__ import annotations

from .extract import fold
from .prompts import suggest_messages
from .profile import Profile

TF_ORDER = ["M15", "H1", "H4", "D1"]
GROUPS = [("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"), ("USDJPY", "EURJPY", "GBPJPY", "AUDJPY"), ("USDCHF", "EURCHF"), ("XAUUSD", "XAGUSD"), ("BTCUSDT", "ETHUSDT", "BTCUSD", "ETHUSD")]
# (khoá luật, tham số) -> (nhãn, biên [lo, hi])
_PARAMS = {("move_atr", "min"): ("ngưỡng nhịp (ATR)", (0.3, 40)), ("move_atr", "bars"): ("số nến của nhịp", (2, 60)), ("bear_body", "min_atr"): ("thân nến (ATR)", (0.2, 5)),
           ("upper_wick", "min_ratio"): ("tỷ lệ bóng nến", (0.1, 0.95)), ("break_low", "bars"): ("số nến phá đáy", (2, 120)), ("ma", "period"): ("chu kỳ MA", (5, 250)),
           ("rsi", "value"): ("ngưỡng RSI", (1, 99)), ("rsi", "period"): ("chu kỳ RSI", (2, 50))}


def _scale(base: float, lo: float, hi: float, integer: bool) -> list[float]:
    vals = []
    for m in (0.75, 1.0, 1.25):
        v = base * m
        v = int(round(v)) if integer else round(v, 3)
        v = min(max(v, lo), hi)
        if v not in vals:
            vals.append(v)
    return vals


def param_variants(p: Profile) -> list[dict]:
    m, out = p.merged(), []
    for r in m["rules"]:
        for (rk, pk), (label, (lo, hi)) in _PARAMS.items():
            if r["rule"] == rk and pk in r:
                base = r[pk]
                out.append({"param": f"{rk}.{pk}", "label": label, "base": base, "range": _scale(float(base), lo, hi, isinstance(base, int))})
    lv = m["levels"]
    sl = lv.get("sl")
    if sl:
        k, lab = ("mult", "SL (bội ATR)") if sl["type"] == "atr" else ("buffer_atr", "đệm SL (ATR)")
        if k in sl:
            out.append({"param": f"sl.{k}", "label": lab, "base": sl[k], "range": _scale(float(sl[k]), 0.1, 8.0, False)})
    if lv.get("tp_r"):
        out.append({"param": "tp_r", "label": "TP (R)", "base": lv["tp_r"][0], "range": sorted({0.5 if lv["tp_r"][0] < 1 else round(lv["tp_r"][0] * x, 2) for x in (0.5, 1, 1.5, 2)})})
    return out


def mirror(p: Profile) -> dict:
    """Đối xứng sell<->buy theo luật DSL; đánh dấu phần không đối xứng thật cần hỏi."""
    items, asym = [], []
    for r in p.merged()["rules"]:
        k = r["rule"]
        if k == "move_atr":
            items.append(f"nhịp {'giảm' if r['dir'] == 'up' else 'tăng'} >= {r['min']} ATR trong {r['bars']} nến")
        elif k == "upper_wick":
            items.append(f"bóng DƯỚI >= {int(r['min_ratio'] * 100)}% biên độ"); asym.append("bóng trên/dưới có thật sự đối xứng ở tài sản này (thiên lệch tăng của chỉ số/vàng)?")
        elif k == "bear_body":
            items.append(f"nến tăng thân >= {r['min_atr']} ATR")
        elif k == "bear_engulf":
            items.append("nến tăng nhấn chìm thân nến trước")
        elif k == "break_low":
            items.append(f"đóng cửa vượt ĐỈNH {r['bars']} nến trước")
        elif k == "ma":
            items.append(f"đóng cửa {'dưới' if r['side'] == 'above' else 'trên'} {r['kind'].upper()}{r['period']}")
        elif k == "rsi":
            items.append(f"RSI{r['period']} {'<=' if r['op'] == '>=' else '>='} {round(100 - r['value'], 2)}"); asym.append("ngưỡng RSI đối xứng 100-x có hợp lý không (RSI thường lệch)?")
        elif k == "hours":
            items.append(f"giờ {r['from']}-{r['to']} UTC (giữ nguyên)")
    return {"rules": items, "needs_confirm": asym, "dsl_supported": False,
            "note": "Schema DSL hiện chỉ chạy side=sell; bản buy đối xứng ghi nhận để chuyên gia xác nhận, chạy test khi DSL hỗ trợ."}


def other_tf_symbols(p: Profile) -> dict:
    m = p.merged()
    tfs = []
    for t in m["tfs"]:
        i = TF_ORDER.index(t) if t in TF_ORDER else -1
        for j in (i - 1, i + 1):
            if 0 <= j < len(TF_ORDER) and TF_ORDER[j] not in m["tfs"] and TF_ORDER[j] not in tfs:
                tfs.append(TF_ORDER[j])
    syms = []
    for s in m["symbols"]:
        for g in GROUPS:
            if s in g:
                syms += [x for x in g if x != s and x not in m["symbols"] and x not in syms]
    return {"tfs": tfs, "symbols": syms[:4], "note": "Chỉ là ứng viên để kiểm chứng; khung khác đổi ý nghĩa của 'số nến' và chi phí tương đối."}


def related_opposite(p: Profile) -> dict:
    t = fold(p.all_text())
    rev = any(w in t for w in ("dao chieu", "tu choi", "bong tren", "dinh", "reversal", "nhan chim"))
    brk = any(w in t for w in ("pha vo", "breakout", "thung", "tiep dien", "continuation"))
    related, opposite = [], []
    if rev or not brk:
        related += ["Cùng bối cảnh nhưng VÀO KHI ĐÃ THỦNG đáy (xác nhận muộn hơn)", "Cùng hình dạng nến nhưng tại vùng cung/cầu khung lớn hơn"]
        opposite += ["Tiếp diễn xu hướng (giá bứt phá thay vì đảo chiều) cùng bối cảnh: kịch bản đối lập để so sánh"]
    if brk:
        related += ["Phá vỡ giả (false breakout) rồi quay lại: kịch bản đảo chiều đi kèm"]
        opposite += ["Vào ngược (fade) tại điểm phá vỡ"]
    return {"related": related, "opposite": opposite}


def counterexamples(p: Profile) -> list[str]:
    out = []
    for v in param_variants(p):
        if v["param"] in ("tp_r", "sl.buffer_atr", "sl.mult"):
            continue
        lo = v["range"][0]
        out.append(f"Phản ví dụ: {v['label']} chỉ đạt {lo} (dưới ngưỡng {v['base']}): AI sẽ KHÔNG vào. Đúng không?")
    out.append("Phản ví dụ: đúng hình dạng nhưng nằm cuối tuần/ngay trước tin mạnh: có vào không?")
    return out[:6]


def boundaries(p: Profile) -> list[str]:
    out = [f"Điều kiện biên: {v['label']} đúng bằng {v['base']} (>= hay >)?" for v in param_variants(p) if v["param"] not in ("tp_r",)][:4]
    out += ["Điều kiện biên: nến kích hoạt là nến đầu phiên sau khoảng trống (gap)?", "Điều kiện biên: hai tín hiệu liên tiếp trong vài nến (cooldown bao lâu)?",
            "Điều kiện biên: SL và TP cùng nằm trong một nến: coi SL trước (bảo thủ) có đồng ý không?"]
    return out


def implicit_assumptions(p: Profile) -> list[dict]:
    t = fold(p.all_text())
    A = [("closed", True, "Chỉ xét nến ĐÃ ĐÓNG (không nhìn nến đang chạy).", "Đồng ý chỉ dùng nến đã đóng?"),
         ("entry", not any(w in t for w in ("mo nen", "gia dong", "dong cua")), "Vào ở giá mở của nến kế tiếp sau nến kích hoạt.", "Vào ở giá đóng cửa nến kích hoạt hay giá mở nến kế tiếp?"),
         ("cost", "spread" not in t, "Chi phí/spread cố định theo mô hình chi phí của hệ thống.", "Có cần giới hạn spread tối đa riêng không?"),
         ("samebar", True, "Nếu SL và TP cùng nằm trong một nến thì tính SL trước (bảo thủ).", "Đồng ý quy ước bảo thủ này?"),
         ("atr", "atr" in t and "atr14" not in t and "atr(14)" not in t, "ATR tính chu kỳ 14.", "ATR chu kỳ 14 hay giá trị khác?"),
         ("utc", "gio" in t or "utc" in t or "phien" in t, "Mọi giờ tính theo UTC.", "Giờ bạn nêu là UTC hay giờ máy chủ/địa phương?"),
         ("news", "tin" not in t, "Không loại trừ giai đoạn có tin mạnh.", "Có cần tránh khung giờ tin mạnh không?"),
         ("one", True, "Một lệnh mô phỏng tại một thời điểm cho mỗi mã; có thời gian nghỉ (cooldown) giữa hai tín hiệu.", "Có cho nhiều lệnh chồng nhau không?"),
         ("regime", True, "Quy tắc được kỳ vọng đúng ở mọi chế độ thị trường trong lịch sử, trừ khi bạn chỉ định bối cảnh.", "Có giai đoạn lịch sử nào cần loại ra không?")]
    return [{"id": i, "text": x, "question": q, "status": "pending"} for i, c, x, q in A if c]


def add_assumptions(p: Profile) -> list[dict]:
    have = {a["id"] for a in p.assumptions}
    new = [a for a in implicit_assumptions(p) if a["id"] not in have]
    p.assumptions.extend(new)
    return new


def expand(p: Profile) -> dict:
    return {"param_variants": param_variants(p), "mirror": mirror(p), "other": other_tf_symbols(p), **related_opposite(p),
            "counterexamples": counterexamples(p), "boundaries": boundaries(p), "assumptions": implicit_assumptions(p)}


def render(e: dict) -> str:
    L = ["**Từ một kịch bản, AI suy ra các hướng sau (chưa kiểm chứng):**"]
    if e["param_variants"]:
        L.append("Biến thể tham số: " + "; ".join(f"{v['label']} {v['range']}" for v in e["param_variants"]))
    if e["mirror"]["rules"]:
        L.append("Đối xứng (buy): " + "; ".join(e["mirror"]["rules"]))
    o = e["other"]
    if o["tfs"] or o["symbols"]:
        L.append(f"Khung/mã khác: khung {', '.join(o['tfs']) or '-'}; mã {', '.join(o['symbols']) or '-'}")
    if e["related"] or e["opposite"]:
        L.append("Liên quan: " + "; ".join(e["related"]) + (" | Đối lập: " + "; ".join(e["opposite"]) if e["opposite"] else ""))
    L += [f"- {x}" for x in e["counterexamples"][:3] + e["boundaries"][:3]]
    L.append("Giả định ngầm cần xác nhận: " + " / ".join(a["question"] for a in e["assumptions"][:4]))
    return "\n".join(L)


def llm_suggestions(guard, p: Profile) -> list[str]:
    """Gợi ý thêm từ LLM (đã hậu kiểm, không thêm số ngoài hồ sơ); lỗi -> rỗng."""
    from .safety import numbers_in
    known = numbers_in(p.all_text()) | {"1", "2", "3"}

    def valid(t: str) -> str | None:
        return "số lạ" if numbers_in(t) - known else None

    text, used = guard.generate(suggest_messages(p.lines()[:8]), "", valid, 300)
    if not used:
        return []
    return [ln.strip("- ").strip() for ln in text.splitlines() if ln.strip().startswith("-")][:3]
