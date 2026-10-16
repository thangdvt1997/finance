"""Lich kinh te: Fair Economy JSON (ca nhan, mac dinh TAT) + nguon chinh thuc (BLS ICS, FOMC tu YAML)."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar

from ..models import Emit, iso
from .base import Context, Source

log = logging.getLogger("news_collector.calendar")
FAIR_ECONOMY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
NY = ZoneInfo("America/New_York")


def event_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def cal_emit(*, eid: str, country: str | None, title: str, impact: str, ts: datetime, forecast=None,
             previous=None, actual=None, source: str) -> Emit:
    payload = {"event_id": eid, "country": country, "title": title, "impact": impact, "ts": iso(ts),
               "forecast": forecast or None, "previous": previous or None, "actual": actual or None, "source": source}
    # doi actual/forecast/gio => phat lai (upsert phia storage)
    key = f"cal:{source}:{eid}:{payload['ts']}:{payload['forecast']}:{payload['actual']}"
    return Emit("calendar", "calendar", payload, key)


def classify_impact(title: str, cfg: dict) -> str:
    t = title.lower()
    if any(k.lower() in t for k in cfg.get("low_override", [])):  # vd 'Employment Situation of Veterans' != NFP
        return "low"
    for level in ("high", "med"):
        if any(k.lower() in t for k in cfg.get(level, [])):
            return level
    return "low"


# ---- Fair Economy -------------------------------------------------------------------------------
_IMPACT = {"high": "high", "medium": "med", "low": "low"}
# Fair Economy ghi 'country' la MA TIEN TE (USD, EUR...) -> chuan hoa ve ma quoc gia nhu cac nguon khac (BLS='US')
CURRENCY_COUNTRY = {"USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP", "AUD": "AU", "CAD": "CA", "CHF": "CH",
                    "NZD": "NZ", "CNY": "CN"}


def parse_faireconomy(body: bytes) -> list[Emit]:
    """event_id ON DINH khi nguon doi gio du kien (QA vong 4, R3-14: CN M2/New Loans/Trade Balance 08:03 -> 09:03 -> 09:00
    tao 3 dong trung): id = (tien te, tieu de, NGAY theo gio goc cua nguon, thu tu xuat hien trong ngay) thay vi gio chinh xac.
    Su kien lap trong ngay (vd 2 lan phat bieu) van tach nhau nho thu tu."""
    parsed = []
    for r in json.loads(body):
        try:
            local = datetime.fromisoformat(r["date"])
        except (KeyError, ValueError, TypeError):
            continue
        title, cur = r.get("title", "").strip(), r.get("country")
        if not title:
            continue
        parsed.append((local, title, cur, r))
    seen: dict[tuple, int] = {}
    occ: dict[int, int] = {}   # vi tri trong `parsed` -> thu tu trong ngay (theo gio); dau ra giu thu tu nguon
    for i in sorted(range(len(parsed)), key=lambda i: parsed[i][0].astimezone(timezone.utc)):
        k = (parsed[i][2] or "", parsed[i][1], parsed[i][0].date().isoformat())
        occ[i] = seen.get(k, 0)
        seen[k] = occ[i] + 1
    out = []
    for i, (local, title, cur, r) in enumerate(parsed):
        ts = local.astimezone(timezone.utc)
        k = (cur or "", title, local.date().isoformat())
        idx = occ[i]
        country = CURRENCY_COUNTRY.get(cur or "", None if cur in (None, "", "All") else cur)
        out.append(cal_emit(eid=event_id("ff2", cur or "", title, k[2], str(idx)), country=country, title=title,
                            impact=_IMPACT.get((r.get("impact") or "").lower(), "low"), ts=ts,
                            forecast=r.get("forecast"), previous=r.get("previous"), actual=r.get("actual"),
                            source="faireconomy"))
    return out


class FairEconomySource(Source):
    """CANH BAO ToS: du lieu goc ForexFactory; chi dung ca nhan, khong phan phoi lai. Mac dinh TAT."""
    name = "cal_faireconomy"

    def __init__(self, interval: float = 3600):
        self.interval = max(interval, 1800)  # nguon rate-limit chat, khong poll day

    async def fetch(self, ctx: Context) -> list[Emit]:
        body, not_modified = await ctx.client.get(FAIR_ECONOMY_URL)
        return [] if not_modified or body is None else parse_faireconomy(body)


# ---- Nguon chinh thuc -----------------------------------------------------------------------------
def parse_bls_ics(body: bytes, impact_cfg: dict) -> list[Emit]:
    cal = Calendar.from_ical(body)
    out = []
    for comp in cal.walk("VEVENT"):
        title = str(comp.get("SUMMARY", "")).strip()
        if not title:
            continue
        dt = comp.decoded("DTSTART")
        if isinstance(dt, datetime):
            ts = dt.replace(tzinfo=NY) if dt.tzinfo is None else dt
        elif isinstance(dt, date):  # su kien ca ngay: BLS phat hanh 08:30 ET
            ts = datetime(dt.year, dt.month, dt.day, 8, 30, tzinfo=NY)
        else:
            continue
        ts = ts.astimezone(timezone.utc)
        out.append(cal_emit(eid=str(comp.get("UID") or event_id("bls", title, iso(ts))), country="US", title=title,
                            impact=classify_impact(title, impact_cfg), ts=ts, source="bls"))
    return out


def parse_fomc(cfg: dict) -> list[Emit]:
    """Lich FOMC trong config/fomc_dates.yaml (ngay quyet dinh, 14:00 ET). Phai doi chieu federalreserve.gov hang nam."""
    out = []
    for d in cfg.get("decision_dates", []):
        d = d if isinstance(d, date) else date.fromisoformat(str(d))
        ts = datetime(d.year, d.month, d.day, 14, 0, tzinfo=NY).astimezone(timezone.utc)
        out.append(cal_emit(eid=f"fomc-{d.isoformat()}", country="US", title="FOMC Rate Decision", impact="high",
                            ts=ts, source="fed"))
    return out


class OfficialCalendarSource(Source):
    name = "cal_official"

    def __init__(self, interval: float = 3600):
        self.interval = interval

    async def fetch(self, ctx: Context) -> list[Emit]:
        out = parse_fomc(ctx.load_yaml("fomc_dates.yaml"))
        try:
            body, not_modified = await ctx.client.get(BLS_ICS_URL)
            if body and not not_modified:
                out += parse_bls_ics(body, ctx.load_yaml("calendar_impact.yaml"))
        except Exception as ex:
            log.warning("BLS ICS loi: %s", ex)
        return out
