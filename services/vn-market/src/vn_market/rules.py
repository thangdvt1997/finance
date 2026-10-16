"""Quy tắc thị trường chứng khoán Việt Nam (hàm thuần, không I/O): biên độ giá, bước giá, lô, phiên giao dịch (giờ VN), thuế/phí.

Nguồn quy tắc: quy chế giao dịch HOSE/HNX hiện hành (biên độ HOSE +-7%, HNX +-10%, UPCOM +-15%; bước giá HOSE 10/50/100đ theo mức giá,
ETF 10đ, HNX/UPCOM 100đ; lô chẵn 100 cp). Phiên: HOSE có ATO 09:00-09:15 và ATC 14:30-14:45; HNX chỉ ATC; UPCOM khớp liên tục.
KHÔNG mô hình hoá ngày lễ (chỉ xét thứ trong tuần) và không phát hiện phiên đặc biệt/tạm ngừng giao dịch: đây là hiển thị tham khảo.
Số liệu giá trần/sàn hiển thị trong UI lấy TRỰC TIẾP từ sở (basicPrice/ceilingPrice/floorPrice); các hàm ở đây dùng để kiểm tra chéo + paper.
"""
from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

BAND = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
LOT = 100
# Thuế TNCN bán chứng khoán 0,1% trên giá trị bán (khớp paper-trader: sell_tax_bps=10). Phí CTCK tham chiếu 0,15% (commission_bps=15) mỗi chiều.
SELL_TAX = 0.001
BROKER_FEE_REF = 0.0015


def tick_size(floor: str, price: float, kind: str = "STOCK") -> float:
    """Bước giá (VND). HOSE cổ phiếu: <10.000đ:10; 10.000-<50.000đ:50; >=50.000đ:100. ETF/CCQ HOSE: 10. HNX/UPCOM: 100."""
    if floor == "HOSE":
        if kind == "ETF":
            return 10.0
        return 10.0 if price < 10_000 else 50.0 if price < 50_000 else 100.0
    return 100.0


def limit_prices(basic: float, floor: str, kind: str = "STOCK") -> tuple[float, float]:
    """(trần, sàn) theo giá tham chiếu: trần làm tròn XUỐNG, sàn làm tròn LÊN theo bước giá."""
    band = BAND.get(floor, 0.07)
    t_hi = tick_size(floor, basic * (1 + band), kind)
    t_lo = tick_size(floor, basic * (1 - band), kind)
    ceil = math.floor(round(basic * (1 + band) / t_hi, 6)) * t_hi
    flr = math.ceil(round(basic * (1 - band) / t_lo, 6)) * t_lo
    return ceil, flr


def round_to_tick(price: float, floor: str, kind: str = "STOCK") -> float:
    t = tick_size(floor, price, kind)
    return round(round(price / t) * t, 2)


def sell_proceeds(price: float, qty: float, *, fee: float = BROKER_FEE_REF) -> dict[str, float]:
    """Giá trị bán ròng: phí CTCK + thuế 0,1% trên giá trị bán."""
    gross = price * qty
    return {"gross": gross, "fee": gross * fee, "tax": gross * SELL_TAX, "net": gross * (1 - fee - SELL_TAX)}


def _t(h: int, m: int) -> time:
    return time(h, m)


# (bắt đầu, kết thúc, mã, nhãn tiếng Việt)
_HOSE = [(_t(8, 30), _t(9, 0), "pre", "Trước phiên"), (_t(9, 0), _t(9, 15), "ato", "ATO - khớp lệnh định kỳ mở cửa"),
         (_t(9, 15), _t(11, 30), "continuous", "Khớp lệnh liên tục"), (_t(11, 30), _t(13, 0), "lunch", "Nghỉ trưa"),
         (_t(13, 0), _t(14, 30), "continuous", "Khớp lệnh liên tục"), (_t(14, 30), _t(14, 45), "atc", "ATC - khớp lệnh định kỳ đóng cửa"),
         (_t(14, 45), _t(15, 0), "plo", "Giao dịch thoả thuận (sau ATC)")]
_HNX = [(_t(8, 30), _t(9, 0), "pre", "Trước phiên"), (_t(9, 0), _t(11, 30), "continuous", "Khớp lệnh liên tục"),
        (_t(11, 30), _t(13, 0), "lunch", "Nghỉ trưa"), (_t(13, 0), _t(14, 30), "continuous", "Khớp lệnh liên tục"),
        (_t(14, 30), _t(14, 45), "atc", "ATC - khớp lệnh xác định giá đóng cửa"), (_t(14, 45), _t(15, 0), "plo", "Giao dịch thoả thuận (sau ATC)")]
_UPCOM = [(_t(8, 30), _t(9, 0), "pre", "Trước phiên"), (_t(9, 0), _t(11, 30), "continuous", "Khớp lệnh liên tục"),
          (_t(11, 30), _t(13, 0), "lunch", "Nghỉ trưa"), (_t(13, 0), _t(15, 0), "continuous", "Khớp lệnh liên tục")]
SCHEDULES = {"HOSE": _HOSE, "HNX": _HNX, "UPCOM": _UPCOM}


def _at(loc: datetime, t: time) -> str:
    return loc.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).isoformat()


def session_status(now: datetime, floor: str = "HOSE") -> dict:
    """Phiên hiện tại theo giờ VN: {code, label, open, next_code, next_label, next_at}. Không xét ngày lễ."""
    loc = now.astimezone(VN_TZ)
    sched = SCHEDULES.get(floor, _HOSE)
    wk = loc.weekday() < 5
    cur = None
    if wk:
        for a, b, code, label in sched:
            if a <= loc.time() < b:
                cur = (a, b, code, label)
                break
    if cur:
        nxt = next(((a, c, lb) for a, _b, c, lb in sched if a >= cur[1]), None)
        if nxt:
            nx = {"next_code": nxt[1], "next_label": nxt[2], "next_at": _at(loc, nxt[0])}
        else:
            nx = {"next_code": "closed", "next_label": "Đóng cửa", "next_at": _at(loc, cur[1])}
        return {"floor": floor, "code": cur[2], "label": cur[3], "open": cur[2] in ("ato", "continuous", "atc", "plo"),
                "now": loc.isoformat(), **nx}
    day = loc
    for _ in range(8):  # ngoài phiên: tìm lần mở cửa kế tiếp
        if day.weekday() < 5:
            cand = day.replace(hour=sched[0][0].hour, minute=sched[0][0].minute, second=0, microsecond=0)
            if cand > loc:
                return {"floor": floor, "code": "closed", "label": "Ngoài giờ giao dịch" if wk else "Cuối tuần", "open": False,
                        "now": loc.isoformat(), "next_code": "pre", "next_label": "Trước phiên", "next_at": cand.isoformat()}
        day = (day + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"floor": floor, "code": "closed", "label": "Đóng cửa", "open": False, "now": loc.isoformat(),
            "next_code": None, "next_label": None, "next_at": None}


def last_session_date(now: datetime) -> str:
    """Ngày giao dịch gần nhất ĐÃ ĐÓNG cửa (sau 15:15 giờ VN nếu hôm nay là ngày thường). Chỉ xét thứ trong tuần, không xét ngày lễ."""
    loc = now.astimezone(VN_TZ)
    d = loc.date()
    if not (loc.weekday() < 5 and loc.time() >= time(15, 15)):
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def limit_flag(close: float | None, ceil: float | None, flr: float | None, eps: float = 0.5) -> str | None:
    """'ceiling' nếu đóng cửa = trần, 'floor' nếu = sàn."""
    if close is None or close <= 0:
        return None
    if ceil and close >= ceil - eps:
        return "ceiling"
    if flr and close <= flr + eps:
        return "floor"
    return None


def rules_summary() -> dict:
    return {
        "bands": {k: {"pct": v * 100, "label": f"±{v * 100:g}%"} for k, v in BAND.items()},
        "tick": {"HOSE": "<10.000đ: 10đ; 10.000-<50.000đ: 50đ; >=50.000đ: 100đ (ETF: 10đ)", "HNX": "100đ", "UPCOM": "100đ"},
        "lot": LOT, "sell_tax_pct": SELL_TAX * 100, "broker_fee_ref_pct": BROKER_FEE_REF * 100,
        "settlement": "T+2 (chưa xác nhận thay đổi 2026)",
        "sessions": {fl: [{"from": a.strftime("%H:%M"), "to": b.strftime("%H:%M"), "code": c, "label": lb} for a, b, c, lb in s]
                     for fl, s in SCHEDULES.items()},
        "note": "Không xét ngày lễ; không phát hiện tạm ngừng giao dịch/phiên đặc biệt.",
    }
