"""Gắn mã cổ phiếu VN vào tin tiếng Việt đã có trong news_items (RSS CafeF/VnExpress/Vietstock/...), không cần sửa news-collector.

Quy tắc bảo thủ để hạn chế khớp nhầm: chỉ xét tin tiếng Việt; khớp MÃ IN HOA nguyên từ (VCB, HPG...) có phân biệt hoa/thường; bỏ các từ viết tắt
phổ biến không phải mã (GDP, USD, CPI...); bỏ tiêu đề viết hoa toàn bộ (dễ khớp nhầm). Mã trùng từ thường gặp -> có thể sai: xem là GỢI Ý.
"""
from __future__ import annotations

import re
from typing import Iterable

STOP = frozenset("""GDP CPI PPI PMI USD VND EUR JPY CNY GBP ETF IPO CEO CFO CTO FED ECB BOJ FDI ODA VAT VAR API CEO AI IT
OPEC IMF WTO WHO NATO ASEAN APEC OECD FTA CPTPP EVFTA RCEP USA EU UK UN LNG LPG OTC ESG KPI ROE ROA EPS PE PB EBIT PCE NFP TPP BOT PPP SME FED
HCM HN NEW TOP ONE ALL TV PC XU AND THE FOR PRO MAX DNA GPS SMS SIM CPU GPU USB LED OLED QR SEA ASIA NET WEB VIP VIETNAM
""".split())

_upper_ratio = lambda s: (sum(1 for c in s if c.isupper()) / max(1, sum(1 for c in s if c.isalpha())))  # noqa: E731


def build_pattern(codes: Iterable[str]) -> re.Pattern | None:
    cs = sorted({c.upper() for c in codes if 2 <= len(c) <= 12 and c.isalnum() and c.upper() not in STOP}, key=lambda c: (-len(c), c))
    if not cs:
        return None
    return re.compile(r"(?<![A-Za-z0-9.])(" + "|".join(re.escape(c) for c in cs) + r")(?![A-Za-z0-9])")


def tag_item(item: dict, pat: re.Pattern) -> list[str]:
    title = item.get("title") or ""
    if len(title) > 12 and _upper_ratio(title) > 0.7:
        return []
    text = f"{title} {item.get('summary') or ''}"
    return list(dict.fromkeys(pat.findall(text)))


def tag_news(items: Iterable[dict], codes: Iterable[str]) -> list[dict]:
    pat = build_pattern(codes)
    if pat is None:
        return []
    out = []
    for it in items:
        tags = tag_item(it, pat)
        if tags:
            out.append({"url": it["url"], "title": it["title"], "source": it.get("source"), "published_at": it.get("published_at") or it.get("ingested_at"),
                        "codes": tags[:8]})
    return out
