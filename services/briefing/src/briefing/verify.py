"""Hậu kiểm TẤT ĐỊNH đầu ra LLM (không dùng LLM để kiểm LLM).

Mỗi nhận định (point) chỉ được giữ khi: có trích dẫn [n] hợp lệ; mọi con số xuất hiện trong văn bản của CHÍNH các mục được trích;
mã/viết-tắt IN HOA có trong mục được trích; không có khuyến nghị mua/bán, không dự báo giá, không URL/markup, không chỉ thị rò rỉ, không tên nguồn;
đủ chồng lấn từ khoá với mục được trích (khi mục là tiếng Việt). Vi phạm -> LOẠI câu (ghi lý do), không sửa lại bằng LLM."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from tscommon.sources import has_source_name

from .sanitize import INJECTION_RE

CITE_RE = re.compile(r"\[\s*(\d{1,3}(?:\s*[,;]\s*\d{1,3})*)\s*\]")   # [3] hoặc [3, 22]

# tên nguồn cứng dự phòng (ngoài sources.yaml dùng chung) — gồm cả tên miền thường gặp
EXTRA_SOURCE_RE = re.compile(
    r"(?i)\b(?:reuters|bloomberg|cnbc|bbc|guardian|investing(?:live)?|oilprice|cafef|vietstock|vnexpress|tuoi\s*tre|tuổi\s*trẻ|vneconomy|baochinhphu|"
    r"dukascopy|yahoo|marketaux|gdelt|finnhub|alpaca|tiingo|twelve\s*data|binance|coinbase|kraken|okx|bybit|forexfactory|fair\s*economy|oanda)\b")

RECO_RE = re.compile(
    r"(?i)\b(?:nên|hãy|cần|khuyến nghị|đề xuất|khuyên|gợi ý|cân nhắc|should|recommend\w*|advis\w*)\s+(?:\S+\s+){0,2}?"
    r"(?:mua|bán|short|long|buy|sell|vào lệnh|đặt lệnh|chốt lời|cắt lỗ|nắm giữ|tích lũy|gom|bắt đáy|giải ngân|hold)\b"
    r"|\b(?:chốt lời|cắt lỗ|vào lệnh|đặt lệnh|canh mua|canh bán|bắt đáy|giải ngân|stop[\s-]?loss|take[\s-]?profit|target\s+price|price\s+target|"
    r"mục tiêu giá|giá mục tiêu|điểm vào lệnh|buy\s+(?:signal|now|the dip)|sell\s+(?:signal|now)|go\s+(?:long|short)|tín hiệu\s+(?:mua|bán))\b"
    r"|\bkhuyến nghị\s+(?:mua|bán|nắm giữ|đầu tư)|\b(?:nên|hãy)\s+(?:mua|bán)\b")
FORECAST_RE = re.compile(
    r"(?i)\b(?:sẽ|will|going to)\s+(?:\S+\s+)?(?:tăng|giảm|lên|xuống|đạt|vượt|phá|hồi|điều chỉnh|rise|fall|drop|increase|decrease|reach|rally|surge|plunge|break)\b"
    r"|\b(?:có thể|nhiều khả năng|khả năng|likely|may|might|could)\s+(?:sẽ\s+)?(?:tăng|giảm|lên|xuống|đạt|vượt|phá|hồi|rise|fall|drop|reach|rally|surge)\b"
    r"|\bdự\s*(?:đoán|phóng)\b|\bpredict\w*|\bprojection\b|\bkỳ vọng giá\b|\btriển vọng giá\b")
MARKUP_RE = re.compile(r"(?i)https?://|www\.|[<>{}\\`]|\bhttp\b|\[(?!\s*\d{1,3}\s*\])|(?<!\d)\]|\bmailto:|\bdata:")

COMMON_ACRONYMS = frozenset(
    "USD EUR GBP JPY AUD NZD CAD CHF CNY VND GDP CPI PPI PMI FED ECB BOJ BOE IMF OPEC ETF NFP FOMC VAT IPO USA EPS RBA RBNZ SNB PBOC PCE ISM ADP FDI "
    "RSI ADX EMA SMA GMT UTC HOSE HNX UPCOM DXY WTI BRENT".split())
STOP = frozenset("trong những nhiều được không cũng của các một này đang đến theo sau khi hơn rằng nhưng trên dưới giữa ngày năm tháng tuần phiên "
                 "thị trường mức điểm giá với cho còn vẫn đã sẽ từ hay hoặc tại về như là và".split())


def _strip_acc(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def number_forms(tok: str) -> set[str]:
    """Các cách đọc hợp lệ của 1 chuỗi số (mơ hồ '1.730': 1,73 hoặc 1730) -> tập chuỗi chuẩn hoá (Decimal bỏ số 0 thừa, không dấu)."""
    t = tok.strip().lstrip("+-−").rstrip(".,")
    if not t or not t[0].isdigit():
        return set()
    cands: list[str] = []
    if "." in t and "," in t:
        dec = "." if t.rfind(".") > t.rfind(",") else ","
        thou = "," if dec == "." else "."
        cands.append(t.replace(thou, "").replace(dec, "."))
    elif "." in t or "," in t:
        sep = "." if "." in t else ","
        parts = t.split(sep)
        if len(parts) > 2:                          # 1.234.567 -> hàng nghìn
            cands.append("".join(parts))
        else:
            cands.append(t.replace(sep, "."))      # thập phân
            if len(parts[1]) == 3:                  # 1.730 -> cũng có thể là 1730
                cands.append("".join(parts))
    else:
        cands.append(t)
    out: set[str] = set()
    for c in cands:
        try:
            d = Decimal(c)
        except InvalidOperation:
            continue
        s = format(d.normalize(), "f")
        out.add(s)
    return out


def numbers_in(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"\d[\d.,]*\d|\d", text)]


def number_set(text: str) -> set[str]:
    s: set[str] = set()
    for tok in numbers_in(text):
        s |= number_forms(tok)
    return s


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", _strip_acc(text)) if (len(w) >= 4 and w not in STOP) or (w.isdigit() and len(w) >= 2)}


@dataclass
class Item:
    n: int
    kind: str             # news | calendar | market | sentiment
    text: str             # văn bản đưa vào LLM (đã làm sạch, KHÔNG tên nguồn)
    lang: str = "vi"
    symbols: tuple[str, ...] = ()


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    cites: list[int] = field(default_factory=list)
    text: str = ""


def check_text_common(text: str) -> str | None:
    """Kiểm tra không cần ngữ cảnh: trả lý do vi phạm hoặc None."""
    if not text or len(text.strip()) < 8:
        return "rỗng/quá ngắn"
    if MARKUP_RE.search(text):
        return "có URL/markup/ký tự cấm"
    if INJECTION_RE.search(text):
        return "chứa mẫu chỉ thị"
    if RECO_RE.search(text):
        return "có khuyến nghị mua/bán"
    if FORECAST_RE.search(text):
        return "có dự báo giá"
    if has_source_name(text) or EXTRA_SOURCE_RE.search(text):
        return "nêu tên nguồn"
    return None


def verify_point(text: str, cites: list, items: dict[int, Item], max_len: int = 360) -> Verdict:
    text = (text or "").strip()
    inline = [int(x) for grp in CITE_RE.findall(text) for x in re.findall(r"\d+", grp)]
    body = CITE_RE.sub("", text)
    body = re.sub(r"\s+", " ", body).strip()
    body = re.sub(r"\s+([,.;:!?])", r"\1", body)
    try:
        cl = sorted({int(c) for c in (cites or [])} | set(inline))
    except (TypeError, ValueError):
        return Verdict(False, "trích dẫn không phải số")
    if not cl:
        return Verdict(False, "thiếu trích dẫn")
    if len(cl) > 4:
        return Verdict(False, "quá nhiều trích dẫn")
    bad = [c for c in cl if c not in items]
    if bad:
        return Verdict(False, f"trích dẫn không tồn tại: {bad}")
    if len(body) > max_len:
        return Verdict(False, "quá dài")
    why = check_text_common(body)
    if why:
        return Verdict(False, why)
    cited = " ".join(items[c].text for c in cl)
    allowed = number_set(cited)
    for tok in numbers_in(body):
        f = number_forms(tok)
        if f and not (f & allowed):
            return Verdict(False, f"số không có trong mục trích dẫn: {tok}")
    cited_up = cited.upper() + " " + " ".join(s.upper() for c in cl for s in items[c].symbols)
    for tk in re.findall(r"\b[A-Z][A-Z0-9]{2,9}\b", body):
        if tk not in COMMON_ACRONYMS and tk not in cited_up:
            return Verdict(False, f"mã/viết tắt không có trong mục trích dẫn: {tk}")
    if all(items[c].lang == "vi" or items[c].kind != "news" for c in cl):
        if len(_keywords(body) & _keywords(cited)) < 2:
            return Verdict(False, "ít chồng lấn nội dung với mục trích dẫn")
    return Verdict(True, "", cl, body)


def verify_free_text(text: str, context_numbers: set[str]) -> Verdict:
    """Cho tiêu đề: số phải có trong toàn bộ ngữ cảnh, và qua kiểm tra chung."""
    t = re.sub(r"\s+", " ", CITE_RE.sub("", text or "")).strip()
    if not (12 <= len(t) <= 140):
        return Verdict(False, "tiêu đề sai độ dài")
    why = check_text_common(t)
    if why:
        return Verdict(False, why)
    for tok in numbers_in(t):
        f = number_forms(tok)
        if f and not (f & context_numbers):
            return Verdict(False, f"số không có trong ngữ cảnh: {tok}")
    return Verdict(True, "", [], t)
