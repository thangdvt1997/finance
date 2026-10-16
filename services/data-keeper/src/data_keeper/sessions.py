"""Lịch phiên theo mã (UTC-aware, thuần hàm, không I/O).

Nhóm: crypto 24/7; fx 24/5 (CN 22:00 -> T6 22:00 UTC); metal = fx + nghỉ ngày 22:00-23:00; index theo khu vực (giờ sàn địa phương,
có DST qua zoneinfo); cổ phiếu Mỹ/VN theo sàn. Nghỉ lễ: 25/12, 1/1 cả ngày; 24/12 và 31/12 sau 21:00 UTC (không áp cho crypto).
Quy ước đồng bộ với docs/handoff/FEED_ALL_contract.md (luật feed:market_open). Bảng chỉ số tinh chỉnh ở INDEX_REGIONS.
API: is_market_open(symbol, ts), session_gaps_expected(symbol, tf, t0, t1), expected_slots(symbol, tf, t0, t1), open_since(symbol, ts), group_of(symbol).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

UTC = timezone.utc
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800}

# khu vực chỉ số: (tz, giờ mở, giờ đóng) giờ địa phương, T2-T6. CFD thường rộng hơn giờ sàn: có đệm đầu/cuối.
INDEX_REGIONS = {
    "uk": ("Europe/London", (7, 55), (16, 40)),
    "eu": ("Europe/Berlin", (8, 55), (17, 40)),
    "us": ("America/New_York", None, None),            # CFD Mỹ theo hợp đồng tương lai ~23h: dùng lịch kim loại
    "jp": ("Asia/Tokyo", (8, 55), (15, 15)),
    "au": ("Australia/Sydney", (9, 55), (16, 10)),
    "hk": ("Asia/Hong_Kong", (9, 15), (16, 10)),
    "ca": ("America/Toronto", (9, 25), (16, 5)),
    "za": ("Africa/Johannesburg", (8, 55), (17, 5)),
}
INDEX_REGION_OF = {
    "UK100": "uk", "JPN225": "jp", "AUS200": "au", "HK50": "hk", "CHINA50": "hk", "CHINAH": "hk", "CA60": "ca", "SA40": "za",
    "US500": "us", "US30": "us", "USTEC": "us", "US2000": "us", "US30M": "us", "US500M": "us", "USTECH100M": "us",
}  # còn lại (DE40, FRA40, ESP35, EUSTX50, IT40, NETH25, NOR25, SE30, SWI20, MIDDE50, TECHDE30) -> "eu"
US_EQUITY = ("America/New_York", (9, 30), (16, 0))
VN_EQUITY = ("Asia/Ho_Chi_Minh", [((9, 0), (11, 30)), ((13, 0), (15, 0))])


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def _is_crypto(s: str) -> bool:
    return s.startswith("CRYPTO:")


# Mã nhà môi giới có trong danh sách nhưng KHÔNG có báo giá/nến (đã kiểm: 0 tick 7 ngày, 0 nến M1 30 ngày): coi như không có nguồn,
# tính CLOSED (note no_data) để không báo giả BROKEN và không kích heal/restart feed. Gỡ khỏi tập khi có dữ liệu.
NO_SOURCE = frozenset({"AUDHUF", "AUDTHB", "AUDZAR", "CADDKK", "CADMXN", "CADPLN", "CADSEK", "CHFMXN", "CHFTRY", "DKKJPY", "DKKNOK",
                       "EURILS", "NOKDKK", "NZDHUF", "NZDMXN", "NZDNOK", "SEKNOK", "UK100", "USDARS", "USDGEL"})
# FX thị trường mới nổi chỉ báo giá theo giờ hẹp (quan sát 14:00-20:00 UTC): cửa sổ an toàn rộng hơn, T2-T6.
# Mã báo giá thưa (ít tick/ngày, có thể im hàng giờ trong phiên): im lặng KHÔNG phải feed hỏng -> SLOW "thin_quotes", không BROKEN.
THIN_QUOTES = frozenset({"USDRUB", "USDRUR", "EURRUB", "EURRUR", "USDNGN", "USTECH100M", "CRYPTO:TONUSDT"})


def is_thin(symbol: str) -> bool:
    return symbol.upper() in THIN_QUOTES


# TECHDE30: broker chỉ báo giá 08:00-14:30 UTC (quan sát 14 ngày: 0 tick ngoài giờ này) -> cửa sổ hẹp, tránh BROKEN giả lúc 07:00-08:00.
EM_FX_WINDOW = {"USDBRL": (12, 21), "USDCLP": (12, 21), "USDCOP": (12, 21), "USTECH100M": (9, 22), "TECHDE30": (8, 15)}


def _strip(symbol: str) -> str:
    return symbol.upper().split(":", 1)[-1] if ":" in symbol and not symbol.upper().startswith("CRYPTO:") else symbol.upper()


@lru_cache(maxsize=4096)
def session_key(symbol: str) -> str:
    """Khoá luật phiên (hashable): crypto | fx | metal | index:<region> | us_equity | vn_equity."""
    s = symbol.upper()
    if _is_crypto(s):
        return "crypto"
    if s in NO_SOURCE:
        return "nosource"
    if s in EM_FX_WINDOW:
        return "limited:" + s
    if s.startswith("US:"):
        return "us_equity"
    if s.startswith("VN:"):
        return "vn_equity"
    if s in INDEX_REGION_OF or s in _INDEX_ALL:
        return "index:" + INDEX_REGION_OF.get(s, "eu")
    if s.startswith(("XAU", "XAG", "XPT", "XPD")):
        return "metal"
    return "fx"


_INDEX_ALL = {"DE40", "FRA40", "ESP35", "EUSTX50", "IT40", "NETH25", "NOR25", "SE30", "SWI20", "MIDDE50", "TECHDE30"} | set(INDEX_REGION_OF)


def group_of(symbol: str) -> str:
    k = session_key(symbol)
    if k.startswith("limited:") and symbol.upper() in _INDEX_ALL:
        return "index"
    return "index" if k.startswith("index:") else ("fx" if k.startswith("limited:") else k)


def _holiday_closed(t: datetime) -> bool:
    md = (t.month, t.day)
    if md in ((12, 25), (1, 1)):
        return True
    return md in ((12, 24), (12, 31)) and t.hour >= 21


def _fx_open(t: datetime, daily_break: bool) -> bool:
    wd, h = t.weekday(), t.hour
    if wd == 5 or (wd == 4 and h >= 22) or (wd == 6 and h < 22):
        return False
    if daily_break and h == 22 and wd not in (4, 5, 6):   # T2-T5 22:00-23:00 nghỉ (CN mở lại 22:00; ca CN 22-23 cũng nghỉ với kim loại)
        return False
    if daily_break and wd == 6 and h == 22:
        return False
    return not _holiday_closed(t)


def _local_window_open(t: datetime, tz: str, start, end) -> bool:
    lt = t.astimezone(ZoneInfo(tz))
    if lt.weekday() >= 5 or _holiday_closed(t):
        return False
    m = lt.hour * 60 + lt.minute
    return start[0] * 60 + start[1] <= m < end[0] * 60 + end[1]


@lru_cache(maxsize=200_000)
def _open_key(key: str, minute: int) -> bool:
    """Mở cửa theo khoá luật tại phút epoch `minute`."""
    t = datetime.fromtimestamp(minute * 60, UTC)
    if key == "crypto":
        return True
    if key == "nosource":
        return False
    if key.startswith("limited:"):
        a, b = EM_FX_WINDOW[key[8:]]
        return t.weekday() < 5 and a <= t.hour < b and not _holiday_closed(t)
    if key == "fx":
        return _fx_open(t, False)
    if key == "metal":
        return _fx_open(t, True)
    if key.startswith("index:"):
        tz, st, en = INDEX_REGIONS[key[6:]]
        return _fx_open(t, True) if st is None else _local_window_open(t, tz, st, en)
    if key == "us_equity":
        return _local_window_open(t, *US_EQUITY)
    if key == "vn_equity":
        return any(_local_window_open(t, VN_EQUITY[0], a, b) for a, b in VN_EQUITY[1])
    return _fx_open(t, False)


def is_market_open(symbol: str, ts: datetime) -> bool:
    return _open_key(session_key(symbol), int(_utc(ts).timestamp()) // 60)


def open_since(symbol: str, ts: datetime, max_back_h: int = 48) -> float | None:
    """Số giây thị trường đã mở liên tục tính tới ts (None nếu đang đóng; tối đa max_back_h)."""
    t = _utc(ts)
    k = session_key(symbol)
    m = int(t.timestamp()) // 60
    if not _open_key(k, m):
        return None
    lim = m - max_back_h * 60
    while m > lim and _open_key(k, m - 1):
        m -= 1
    return max(0.0, t.timestamp() - m * 60)


def last_open_end(symbol: str, ts: datetime, max_back_h: int = 24 * 8) -> datetime | None:
    """Thời điểm phiên gần nhất kết thúc (nếu đang đóng); None nếu đang mở / không thấy."""
    t = _utc(ts)
    k = session_key(symbol)
    m = int(t.timestamp()) // 60
    if _open_key(k, m):
        return None
    lim = m - max_back_h * 60
    while m > lim:
        m -= 1
        if _open_key(k, m):
            return datetime.fromtimestamp((m + 1) * 60, UTC)
    return None


def slot_expected(symbol: str, tf: str, slot_start: datetime) -> bool:
    """Nến [slot_start, +tf) kỳ vọng tồn tại nếu thị trường mở tại đầu nến (tf nhỏ) hoặc ở bất kỳ điểm lấy mẫu trong nến (tf >= H1)."""
    sec = TF_SECONDS[tf]
    k = session_key(symbol)
    base = int(_utc(slot_start).timestamp())
    if sec <= 900:
        return _open_key(k, base // 60)
    return any(_open_key(k, (base + off) // 60) for off in (0, sec // 3, 2 * sec // 3, sec - 60))


def _slots(tf: str, t0: datetime, t1: datetime):
    sec = TF_SECONDS[tf]
    a = int(_utc(t0).timestamp())
    a = a - a % sec + (sec if a % sec else 0)
    b = int(_utc(t1).timestamp())
    while a + sec <= b:
        yield a
        a += sec


def expected_slots(symbol: str, tf: str, t0: datetime, t1: datetime) -> int:
    """Số nến kỳ vọng trong [t0, t1) (chỉ đếm nến nằm trọn trong khoảng)."""
    return sum(1 for a in _slots(tf, t0, t1) if slot_expected(symbol, tf, datetime.fromtimestamp(a, UTC)))


def session_gaps_expected(symbol: str, tf: str, t0: datetime, t1: datetime) -> list[tuple[datetime, datetime]]:
    """Các khoảng ĐÓNG CỬA (không kỳ vọng nến) trong [t0,t1), đã gộp liền kề: dùng để loại khỏi 'thiếu nến'."""
    out: list[tuple[datetime, datetime]] = []
    sec = TF_SECONDS[tf]
    for a in _slots(tf, t0, t1):
        if not slot_expected(symbol, tf, datetime.fromtimestamp(a, UTC)):
            s, e = datetime.fromtimestamp(a, UTC), datetime.fromtimestamp(a + sec, UTC)
            if out and out[-1][1] == s:
                out[-1] = (out[-1][0], e)
            else:
                out.append((s, e))
    return out


def missing_slots(symbol: str, tf: str, present: set[int], t0: datetime, t1: datetime) -> list[datetime]:
    """Các nến kỳ vọng nhưng không có (present = tập epoch giây ts_open). Cho backfill (A3)."""
    return [datetime.fromtimestamp(a, UTC) for a in _slots(tf, t0, t1)
            if a not in present and slot_expected(symbol, tf, datetime.fromtimestamp(a, UTC))]
