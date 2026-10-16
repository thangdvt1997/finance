"""Lich kinh te quoc te co forecast/previous/actual: Financial Modeling Prep (FMP) `economic-calendar`.

CANH BAO / TRANG THAI XAC MINH:
- Can API key MIEN PHI cua FMP (`FMP_API_KEY`, goi Basic 250 request/ngay). Mac dinh TAT (`NC_SRC_CAL_FMP=false`);
  chi chay khi co ca co bat va key. Dieu khoan FMP: dung ca nhan/noi bo, khong phan phoi lai du lieu -> doc ToS truoc khi bat.
- CHUA kiem chung voi key that (phat trien khong co key). Dinh dang theo tai lieu FMP `/stable/economic-calendar`:
  [{date:'YYYY-MM-DD HH:MM:SS' (UTC), country:'US', event, currency, previous, estimate, actual, impact:'Low|Medium|High'}].
  Fixture trong test la MAU THEO TAI LIEU, khong phai phan hoi that -> can xac nhan lai khi co key.
- 1 request/lan poll (cua so [now-1 ngay, now+14 ngay]); poll >= 30 phut (48 req/ngay << 250).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from ..models import Emit
from .base import Context, Source
from .calendar_sources import cal_emit, event_id

log = logging.getLogger("news_collector.fmp")
FMP_URL = "https://financialmodelingprep.com/stable/economic-calendar"
_IMPACT = {"high": "high", "medium": "med", "med": "med", "low": "low"}


def _s(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def parse_fmp(body: bytes) -> list[Emit]:
    data = json.loads(body)
    if not isinstance(data, list):  # loi dang {"Error Message": ...}
        raise ValueError(f"FMP tra ve khong phai list: {str(data)[:120]}")
    out = []
    for r in data:
        try:
            ts = datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        title, country = (r.get("event") or "").strip(), (r.get("country") or None)
        if not title:
            continue
        out.append(cal_emit(eid=event_id("fmp", country or "", title, ts.isoformat()), country=country, title=title,
                            impact=_IMPACT.get(str(r.get("impact") or "").lower(), "low"), ts=ts,
                            forecast=_s(r.get("estimate")), previous=_s(r.get("previous")), actual=_s(r.get("actual")),
                            source="fmp"))
    return out


class FmpCalendarSource(Source):
    name = "cal_fmp"

    def __init__(self, api_key: str, interval: float = 3600):
        if not api_key:
            raise ValueError("FMP_API_KEY bat buoc")
        self.api_key = api_key
        self.interval = max(interval, 1800)

    async def fetch(self, ctx: Context) -> list[Emit]:
        today = ctx.now().date()
        params = {"from": (today - timedelta(days=1)).isoformat(), "to": (today + timedelta(days=14)).isoformat(),
                  "apikey": self.api_key}
        try:
            body, not_modified = await ctx.client.get(FMP_URL, params=params, use_cache=False)
        except Exception as ex:  # noqa: BLE001 - khong de key lot vao log/status qua URL trong thong diep loi
            raise RuntimeError(f"FMP loi {type(ex).__name__}: {str(ex).replace(self.api_key, '***')[:200]}") from None
        return [] if not body or not_modified else parse_fmp(body)
