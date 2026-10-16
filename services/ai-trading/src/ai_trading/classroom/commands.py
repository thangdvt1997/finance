"""Bộ hành động nội bộ (allow-list; giao diện chỉ hiện nhãn tự nhiên, không bắt gõ /). Parser CHỈ trả 'ý định' có cấu trúc; lớp backend thực thi. Không có lệnh nào tự do/đặt lệnh/mở test khoá."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import fold
from .safety import clean_text, looks_injected


class CommandError(ValueError):
    def __init__(self, msg: str, suggestions: list[str] | None = None):
        super().__init__(msg)
        self.suggestions = suggestions or []


@dataclass
class Intent:
    command: str
    action: str                     # tên action trong ALLOWED_ACTIONS
    params: dict = field(default_factory=dict)
    local: bool = False             # True: lõi tự trả lời (không cần backend)
    requires_confirm: bool = False  # backend phải hỏi xác nhận người dùng trước khi chạy
    paper_only: bool = True


# lệnh -> (action, local, requires_confirm, mô tả)
COMMANDS = {
    "test": ("backtest", False, True, "Backtest trung thực (đăng ký giả thuyết trước, walk-forward, baseline ngẫu nhiên); test khoá không mở được từ chat"),
    "quet": ("scan_history", False, False, "Quét lịch sử tìm lần xuất hiện + 6-10 ảnh nến để gắn nhãn ĐÚNG/SAI/GẦN ĐÚNG"),
    "bien-the": ("variants", True, False, "Liệt kê biến thể tham số/khung/mã/kịch bản liên quan-đối lập"),
    "doi-xung": ("mirror", True, False, "Phiên bản đối xứng buy/sell + điểm bất đối xứng"),
    "so-sanh": ("compare", False, False, "So sánh với mua-giữ / baseline ngẫu nhiên / kịch bản khác"),
    "giai-thich": ("explain", True, False, "AI giải thích cách hiểu một phần của hồ sơ"),
    "tom-tat": ("summary", True, False, "Tóm tắt 'AI hiểu như sau' + độ chắc chắn"),
    "luu": ("save_version", False, False, "Lưu phiên bản hồ sơ kịch bản"),
    "hoi-them": ("ask_more", True, False, "AI hỏi tiếp (giả định ngầm, phản ví dụ, điều kiện biên)"),
    "ve": ("draw_annotation", False, False, "Vẽ chú thích lên biểu đồ (đỉnh/đáy/vùng/điểm vào/sóng)"),
    "dat-lai": ("reset", True, True, "Đặt lại phiên dạy (hồ sơ đã lưu phiên bản vẫn giữ)"),
}
ALLOWED_ACTIONS = frozenset(a for a, *_ in COMMANDS.values())
_ALIAS = {"bienthe": "bien-the", "doixung": "doi-xung", "sosanh": "so-sanh", "giaithich": "giai-thich", "tomtat": "tom-tat", "hoithem": "hoi-them", "datlai": "dat-lai",
          "backtest": "test", "scan": "quet", "save": "luu", "draw": "ve", "reset": "dat-lai", "summary": "tom-tat", "explain": "giai-thich", "mirror": "doi-xung", "compare": "so-sanh", "variants": "bien-the"}
_KV = re.compile(r"^([a-z_]{1,16})=([A-Za-z0-9_.,:\-]{1,40})$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")
_TFS = {"m15", "h1", "h4", "d1"}
_KINDS = {"dinh", "day", "vung", "diem-vao", "song", "cung", "cau"}


def _norm(c: str) -> str:
    c = fold(c).replace("_", "-")
    c = re.sub(r"[^a-z\-]", "", c)
    return _ALIAS.get(c, _ALIAS.get(c.replace("-", ""), c))


def parse_command(text: str) -> Intent | None:
    """None nếu không phải lệnh. Ném CommandError (kèm gợi ý) nếu lệnh lạ/tham số sai."""
    t = (text or "").strip()
    if not t.startswith("/"):
        return None
    parts = t[1:].split()
    if not parts:
        raise CommandError("Lệnh trống.", ["/" + c for c in COMMANDS])
    cmd = _norm(parts[0])
    if cmd not in COMMANDS:
        raise CommandError(f"Lệnh không có trong danh sách cho phép: /{parts[0][:20]}", ["/" + c for c in COMMANDS])
    action, local, confirm, _ = COMMANDS[cmd]
    kv: dict = {}
    free: list[str] = []
    for tok in parts[1:]:
        m = _KV.match(tok)
        if m:
            kv[m.group(1)] = m.group(2)
        elif "=" in tok or ";" in tok:
            raise CommandError("Tham số không hợp lệ (chỉ dạng khoá=giá trị đơn giản).")
        else:
            free.append(tok)
    ftxt = clean_text(" ".join(free), 300)
    if looks_injected(" ".join(free)):
        raise CommandError("Tham số có mẫu chỉ thị cho AI nên bị từ chối.")
    p: dict = {}
    if cmd == "test":
        _only(kv, {"version", "mode", "lock"}, cmd)
        if kv.get("lock", "no") != "no":
            raise CommandError("Test khoá không mở được từ chat; master mở bằng nút xác nhận riêng.")
        mode = kv.get("mode", "walkforward")
        if mode not in ("dev", "walkforward"):
            raise CommandError("mode chỉ nhận dev hoặc walkforward.")
        p = {"mode": mode, "version": _int(kv.get("version"), 1, 9999, "version"), "lock": "no"}
    elif cmd == "quet":
        _only(kv, {"limit", "symbol", "tf"}, cmd)
        tf = kv.get("tf", "").lower()
        if tf and tf not in _TFS:
            raise CommandError("tf thuộc m15|h1|h4|d1.")
        sym = kv.get("symbol", "").upper()
        if sym and not re.fullmatch(r"[A-Z][A-Z0-9._]{2,11}", sym):
            raise CommandError("symbol không hợp lệ.")
        p = {"limit": _int(kv.get("limit", "8"), 6, 10, "limit"), "symbol": sym or None, "tf": tf.upper() or None}
    elif cmd == "so-sanh":
        _only(kv, {"vs"}, cmd)
        vs = kv.get("vs", "buy_hold")
        if vs not in ("buy_hold", "random") and not _ID.match(vs):
            raise CommandError("vs: buy_hold | random | mã kịch bản.")
        p = {"vs": vs}
    elif cmd == "luu":
        _only(kv, set(), cmd)
        p = {"note": ftxt[:200]}
    elif cmd == "ve":
        _only(kv, {"kind"}, cmd)
        kind = fold(kv.get("kind", "vung"))
        if kind not in _KINDS:
            raise CommandError("kind thuộc " + "|".join(sorted(_KINDS)))
        p = {"kind": kind, "note": ftxt[:200]}
    elif cmd in ("giai-thich", "hoi-them"):
        _only(kv, set(), cmd)
        p = {"topic": ftxt[:200]}
    elif cmd == "dat-lai":
        _only(kv, {"xacnhan"}, cmd)
        p = {"confirmed": kv.get("xacnhan") == "co"}
    else:
        _only(kv, set(), cmd)
    return Intent(cmd, action, p, local, confirm)


def _only(kv: dict, ok: set, cmd: str) -> None:
    bad = set(kv) - ok
    if bad:
        raise CommandError(f"/{cmd}: tham số không hợp lệ {sorted(bad)[:3]}")


def _int(v, lo: int, hi: int, name: str):
    if v is None:
        return None
    if not str(v).isdigit() or not lo <= int(v) <= hi:
        raise CommandError(f"{name}: số nguyên {lo}..{hi}")
    return int(v)


def chips_for(phase: str, step_key: str | None, missing_required: list[str], n_answered: int = 0) -> list[dict]:
    """Chip gợi ý nhanh dưới ô nhập, đổi theo ngữ cảnh: {label, text, send}. send=True: gửi ngay; False: chỉ điền vào ô."""
    chips: list[dict] = []
    if phase == "intake":
        return [{"label": "Mô tả kịch bản trong 3 câu", "text": "", "send": False}, {"label": "Dán ghi chú/ảnh chú thích", "text": "", "send": False}]
    if phase == "interview":
        chips += [{"label": "Bỏ qua câu này", "text": "bỏ qua", "send": True}, {"label": "Tóm tắt AI hiểu", "text": "/tom-tat", "send": True}]
        hint = {"formation": "Nhịp tăng 2 ATR trong 6 nến, sau đó nến đóng giảm", "sl_tp": "SL trên đỉnh 6 nến + 0,25 ATR; TP 1R và 2R; giữ tối đa 60 nến",
                "symbol_tf": "EURUSD H1", "filters": "Chỉ phiên 7-16 UTC; tránh 30 phút quanh tin mạnh", "sizing": "Rủi ro 0,5% mỗi lệnh"}.get(step_key or "")
        if hint:
            chips.append({"label": "Mẫu trả lời", "text": hint, "send": False})
        chips.append({"label": "AI hỏi thêm", "text": "/hoi-them", "send": True})
        return chips
    chips += [{"label": "Biến thể", "text": "/bien-the", "send": True}, {"label": "Đối xứng", "text": "/doi-xung", "send": True}]
    if not missing_required:
        chips += [{"label": "Quét ví dụ lịch sử", "text": "/quet limit=8", "send": True}, {"label": "Test trung thực", "text": "/test", "send": True},
                  {"label": "So với mua-giữ", "text": "/so-sanh vs=buy_hold", "send": True}]
    else:
        chips.append({"label": "Còn thiếu: " + ", ".join(missing_required), "text": "/hoi-them", "send": True})
    chips += [{"label": "Lưu phiên bản", "text": "/luu", "send": True}, {"label": "Giải thích", "text": "/giai-thich", "send": True}]
    return chips
