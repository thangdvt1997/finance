"""Danh sach feed RSS MAC DINH (da kiem chung bang mang 2026-10-11 tu VPS <VPS_IP>, xem SOURCES.md).
Dung khi bien moi truong EC_RSS_FEEDS KHONG duoc dat. Dat EC_RSS_FEEDS='[]' de tat, hoac dat danh sach rieng de thay the.

`reputation` o day la uy tin cua TO CHUC PHAT HANH (thoi gian hoat dong), KHONG phai thanh tich giao dich da kiem chung:
diem chi de vuot nguong theo doi; consumer phai coi day la y kien tham khao (raw.kind='technical_outlook').
"""
from __future__ import annotations

PUBLISHER_REPUTATION = {"kind": "publisher", "months_active": 120, "max_drawdown_pct": 0, "gain_pct": 0, "followers": 1000}

DEFAULT_RSS_FEEDS: list[dict] = [
    {
        # ActionForex 'XXX/YYY Weekly Outlook': ban tin ky thuat hang tuan, co cau 'bias ... further rise/decline ... as long as N holds'.
        # Verified: 8 tin hieu that/tuan (EURUSD, USDJPY, GBPUSD, USDCHF, AUDUSD, USDCAD, EURGBP, EURCHF).
        "name": "ActionForex Weekly Outlook",
        "expert_id": "rss:actionforex_weekly",
        "url": "https://www.actionforex.com/feed/",
        "mode": "technical_outlook",
        "reputation": dict(PUBLISHER_REPUTATION),
    },
]
