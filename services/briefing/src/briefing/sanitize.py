"""Phòng thủ prompt-injection cho NỘI DUNG TIN (dữ liệu không đáng tin).

Nguyên tắc: tin chỉ là DỮ LIỆU. (1) làm sạch ký tự/thẻ/URL/mẫu chat-template; (2) tin có dấu hiệu chỉ thị cho AI bị LOẠI HẲN khỏi ngữ cảnh
(không thể được trích dẫn); (3) văn bản còn lại bị cắt độ dài và đóng khung bằng delimiter ngẫu nhiên mỗi lần chạy (xem prompt.py).
Hàm thuần, không I/O."""
from __future__ import annotations

import re
import unicodedata

# Dấu hiệu chỉ thị cho mô hình (Anh + Việt). Khớp -> loại cả tin khỏi ngữ cảnh LLM.
_INJ = [
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|preceding)?\s*(?:instructions?|prompts?|rules?|directions?)",
    r"disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier)?\s*(?:instructions?|prompts?|rules?)",
    r"forget\s+(?:all\s+|everything|your\s+|the\s+)(?:previous\s+|prior\s+|above\s+)?(?:instructions?|rules?|prompts?|context)?",
    r"(?:system|developer)\s*(?:prompt|message|instruction)s?",
    r"you\s+are\s+now\b", r"act\s+as\s+(?:an?\s+)?(?:unrestricted|jailbroken|dan|developer)", r"\bjailbreak", r"\bdan\s+mode\b", r"developer\s+mode",
    r"new\s+instructions?\s*:", r"override\s+(?:the\s+)?(?:instructions?|rules?|safety)", r"reveal\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions?)",
    r"(?:respond|reply|answer|output)\s+(?:only\s+)?(?:with|in)\s*[:\"']", r"\bdo\s+not\s+(?:cite|follow|mention)\b",
    r"b(?:ỏ|o)\s+qua\s+(?:m(?:ọ|o)i\s+|t(?:ấ|a)t\s+c(?:ả|a)\s+|c(?:á|a)c\s+)?(?:h(?:ư|u)(?:ớ|o)ng\s+d(?:ẫ|a)n|ch(?:ỉ|i)\s+d(?:ẫ|a)n|l(?:ệ|e)nh|quy\s+t(?:ắ|a)c|ch(?:ỉ|i)\s+th(?:ị|i))",
    r"qu(?:ê|e)n\s+(?:h(?:ế|e)t\s+|m(?:ọ|o)i\s+|c(?:á|a)c\s+)?(?:h(?:ư|u)(?:ớ|o)ng\s+d(?:ẫ|a)n|ch(?:ỉ|i)\s+d(?:ẫ|a)n|quy\s+t(?:ắ|a)c)",
    r"(?:b(?:â|a)y\s+gi(?:ờ|o)\s+)?b(?:ạ|a)n\s+l(?:à|a)\s+(?:m(?:ộ|o)t\s+)?(?:tr(?:ợ|o)\s+l(?:ý|y)|ai|chatbot|m(?:ô|o)\s+h(?:ì|i)nh|chuy(?:ê|e)n\s+gia\s+kh(?:ô|o)ng)",
    r"h(?:ư|u)(?:ớ|o)ng\s+d(?:ẫ|a)n\s+m(?:ớ|o)i", r"prompt\s+h(?:ệ|e)\s+th(?:ố|o)ng", r"ch(?:ế|e)\s+(?:độ|do)\s+(?:nh(?:à|a)\s+ph(?:á|a)t\s+tri(?:ể|e)n|jailbreak)",
    r"(?:h(?:ã|a)y|vui\s+l(?:ò|o)ng)\s+(?:tr(?:ả|a)\s+l(?:ờ|o)i|vi(?:ế|e)t|in\s+ra|xu(?:ấ|a)t|n(?:ó|o)i)\s+(?:r(?:ằ|a)ng|ch(?:ỉ|i)|duy\s+nh(?:ấ|a)t)",
    r"(?:h(?:ã|a)y|vui\s+l(?:ò|o)ng|you\s+must|please)\s+(?:mua|b(?:á|a)n|buy|sell|chuy(?:ể|e)n\s+ti(?:ề|e)n|transfer|truy\s+c(?:ậ|a)p|visit|click|g(?:ọ|o)i\s+h(?:à|a)m|call\s+the)\b",
    r"<\s*/?\s*(?:system|assistant|user|instructions?|prompt|script|iframe)\b", r"\[/?(?:inst|sys|system|assistant|user)\]",
    r"t(?:ừ|u)\s+gi(?:ờ|o)\s+(?:tr(?:ả|a)\s+l(?:ờ|o)i|h(?:ã|a)y|ch(?:ỉ|i))", r"(?:tr(?:ả|a)\s+l(?:ờ|o)i|reply|respond|answer)\s+(?:ch(?:ỉ|i)\s+)?(?:b(?:ằ|a)ng|only|with|exactly)",
    r"important\s+(?:system\s+)?(?:message|notice|instruction)", r"<\|[^>]{0,40}\|>", r"###\s*(?:system|instruction|human|assistant)",
    r"nh(?:ắ|a)c\s+l(?:ạ|a)i\s+(?:to(?:à|a)n\s+b(?:ộ|o)|n(?:ộ|o)i\s+dung|c(?:á|a)c\s+(?:ch(?:ỉ|i)|h(?:ư|u)(?:ớ|o)ng))", r"repeat\s+(?:the\s+)?(?:text|words|everything|content)\s+(?:above|before)",
    r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/])",   # chuỗi base64 dài (giấu chỉ thị)
    r"^\s*(?:system|assistant|user|human)\s*:", r"\bBEGIN\s+(?:SYSTEM|INSTRUCTIONS?)\b", r"\bEND\s+OF\s+(?:DATA|CONTEXT|INPUT)\b",
]
INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJ), re.I | re.M)

_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿­‪‫‬‭‮⁦⁧⁨⁩"), None)
_URL = re.compile(r"(?:https?://|ftp://|www\.)\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|vn|io|info|biz|co|me|ly|xyz|top)\b(?:/\S*)?", re.I)
_TAG = re.compile(r"<[^>]{0,200}>")
_CITE = re.compile(r"\[\s*\d{1,3}\s*\]")            # tin giả không được tự gắn [n] giả
_DELIM = re.compile(r"(?:<{2,}|>{2,}|`{2,}|~{3,}|={4,}|-{4,}|\{\{|\}\}|\|\|)")
_WS = re.compile(r"\s+")


def clean_text(s: object, limit: int) -> str:
    """Chuẩn hoá Unicode, bỏ ký tự điều khiển/zero-width/thẻ HTML/URL/dấu phân cách khung, gộp khoảng trắng, cắt độ dài."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s).translate(_ZW)
    t = "".join(ch for ch in t if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    t = _TAG.sub(" ", t)
    t = _URL.sub(" ", t)
    t = _CITE.sub(" ", t)
    t = _DELIM.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


# Biến thể che giấu: chữ rời "i g n o r e", leetspeak "1gn0re", đồng hình Cyrillic/Greek, ký tự phân cách chèn giữa. Chuẩn hoá về chữ cái Latin liền nhau rồi tìm cụm lõi.
_HOMO = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ѕ": "s", "ј": "j", "ο": "o", "α": "a", "ε": "e", "ι": "i", "ν": "v", "ρ": "p", "τ": "t",
                       "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
_SQUASH_RE = re.compile(
    r"ignore(?:all|any|the|your)?(?:previous|prior|above|earlier|preceding)?(?:instructions?|prompts?|rules?|directions?)|disregard(?:all|any|the|your)?(?:previous|prior|above|earlier)?(?:instructions?|prompts?|rules?)"
    r"|(?:system|developer)(?:prompt|message|instructions?)|youarenow|jailbreak|developermode|newinstructions?|overridethe(?:instructions?|rules?|safety)|reveal(?:your|the)?(?:system)?(?:prompt|instructions?)"
    r"|(?:disclose|show|print|repeat|translate)(?:your|the|all)?(?:hidden|secret|system|initial|original)?(?:guidelines?|instructions?|prompt|rules)|notetothe(?:summar|assistant|model|ai)|psassistant")


def _squash(s: str) -> str:
    t = unicodedata.normalize("NFKC", s).translate(_ZW).lower().translate(_HOMO)
    return re.sub(r"[^a-z]+", "", t)


def looks_injected(*texts: object) -> str | None:
    """Trả mẫu khớp (đoạn ngắn) nếu bất kỳ văn bản nào chứa chỉ thị cho AI; None nếu sạch. Kiểm trên cả bản thô lẫn bản đã chuẩn hoá."""
    for s in texts:
        if not isinstance(s, str) or not s:
            continue
        for v in (s, unicodedata.normalize("NFKC", s).translate(_ZW)):
            m = INJECTION_RE.search(v)
            if m:
                return m.group(0)[:60]
        m = _SQUASH_RE.search(_squash(s))
        if m:
            return "squash:" + m.group(0)[:50]
    return None
