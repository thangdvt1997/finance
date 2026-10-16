"""Lich quyet dinh lai suat NHNW quoc te tu trang lich CHINH THUC cua chinh ngan hang (ECB, BoE, BoJ).

Day la du lieu cong khai do chinh NHNW cong bo (khong ToS-risk): ngay hop + gio cong bo quyet dinh; khong co forecast
(consensus la du lieu thuong mai). BoE them `previous` = Bank Rate hien hanh (lay tu chinh trang) cho ky hop ke tiep.

Gio cong bo (co dinh theo thong le cua tung NHNW, KHONG nam trong trang -> hang so trong code):
  ECB 14:15 CET/CEST (Europe/Berlin; hop bao 14:45), BoE 12:00 gio London, BoJ ~12:00 JST (BoJ khong cong bo gio,
  thuong 11:30-13:00 -> chi la xap xi; impact=high nen canh bao truoc 30 phut van hop ly).
Parser dung regex tren HTML that (fixture: tests/fixtures/real_ecb_gc.html, real_boe_mpc.html, real_boj_mpm.html);
neu cau truc trang doi -> khong khop dong nao -> tra [] va runner ghi log (khong lam hong nguon khac).
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..models import Emit
from .base import Context, Source
from .calendar_sources import cal_emit, event_id

log = logging.getLogger("news_collector.central_banks")
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"
BOJ_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"

BERLIN, LONDON, TOKYO = ZoneInfo("Europe/Berlin"), ZoneInfo("Europe/London"), ZoneInfo("Asia/Tokyo")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _txt(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ").split())


def _month(name: str) -> int | None:
    return _MONTHS.get(name[:3].lower())


def parse_ecb(body: bytes) -> list[Emit]:
    """`<dt>dd/mm/yyyy</dt><dd>mo ta</dd>`: 'monetary policy meeting ... (Day 2)' = ngay quyet dinh; dong 'Press conference'."""
    page = body.decode("utf-8", "replace")
    out: list[Emit] = []
    for d, what in re.findall(r"<dt>\s*(\d{2}/\d{2}/\d{4})\s*</dt>\s*<dd>\s*(.*?)\s*(?:<br\s*/?>|</dd>)", page, flags=re.S):
        what, day = _txt(what), datetime.strptime(d, "%d/%m/%Y").date()
        if "monetary policy meeting" in what.lower() and "Day 2" in what:
            ts = datetime(day.year, day.month, day.day, 14, 15, tzinfo=BERLIN)
            out.append(cal_emit(eid=event_id("ecb", "decision", day.isoformat()), country="EU",
                                title="ECB Interest Rate Decision", impact="high", ts=ts, source="ecb"))
        elif what.lower().startswith("press conference"):
            ts = datetime(day.year, day.month, day.day, 14, 45, tzinfo=BERLIN)
            out.append(cal_emit(eid=event_id("ecb", "presser", day.isoformat()), country="EU",
                                title="ECB Press Conference", impact="med", ts=ts, source="ecb"))
    return out


def parse_boe(body: bytes) -> list[Emit]:
    """Bang 'YYYY confirmed dates': hang `<td>Thursday 5 February</td><td>...</td>`; Bank Rate hien hanh o `stat-figure`."""
    page = body.decode("utf-8", "replace")
    rate = re.search(r'class="stat-figure">\s*([\d.]+\s*%)', page)
    nxt = re.search(r"Next due:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", page)
    next_due = date(int(nxt[3]), _month(nxt[2]), int(nxt[1])) if nxt and _month(nxt[2]) else None
    out: list[Emit] = []
    heads = list(re.finditer(r"<h2[^>]*>\s*(\d{4}) confirmed dates\s*</h2>", page))
    for i, h in enumerate(heads):
        seg = page[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(page)]
        year = int(h[1])
        for first, rest in re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>", seg, flags=re.S):
            m = re.search(r"(\d{1,2})\s+([A-Za-z]+)", _txt(first))
            if not m or not _month(m[2]):
                continue
            day = date(year, _month(m[2]), int(m[1]))
            ts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=LONDON)
            prev = rate[1].replace(" ", "") if rate and day == next_due else None
            out.append(cal_emit(eid=event_id("boe", "decision", day.isoformat()), country="GB",
                                title="BoE Interest Rate Decision", impact="high", ts=ts, previous=prev, source="boe"))
    return out


def parse_boj(body: bytes) -> list[Emit]:
    """Bang MPM theo nam (`<h2 id="pYYYY">`): cot 1 = 'Oct. 29 (Thurs.), 30 (Fri.)' -> ngay cuoi la ngay cong bo quyet dinh."""
    page = body.decode("utf-8", "replace")
    heads = list(re.finditer(r'<h2 id="p(\d{4})">', page))
    out: list[Emit] = []
    for i, h in enumerate(heads):
        seg = page[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(page)]
        for first in re.findall(r"<tr>\s*<td[^>]*>(.*?)</td>", seg, flags=re.S):
            t = _txt(first)
            m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2})\b[^,]*(?:,\s*(\d{1,2})\b)?", t)
            if not m or not _month(m[1]):
                continue
            day = date(int(h[1]), _month(m[1]), int(m[3] or m[2]))
            ts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=TOKYO)
            out.append(cal_emit(eid=event_id("boj", "decision", day.isoformat()), country="JP",
                                title="BoJ Monetary Policy Meeting Decision", impact="high", ts=ts, source="boj"))
    return out


class CentralBankCalendarSource(Source):
    """ECB + BoE + BoJ. Moi ngan hang loi doc lap; lich doi rat cham -> poll >= 6 gio."""
    name = "cal_central_banks"
    PARSERS = (("ecb", ECB_URL, parse_ecb), ("boe", BOE_URL, parse_boe), ("boj", BOJ_URL, parse_boj))

    def __init__(self, interval: float = 21600):
        self.interval = max(interval, 3600)

    async def fetch(self, ctx: Context) -> list[Emit]:
        out: list[Emit] = []
        for name, url, parse in self.PARSERS:
            try:
                body, not_modified = await ctx.client.get(url)
                if body and not not_modified:
                    emits = parse(body)
                    if not emits:
                        log.warning("%s: khong trich duoc su kien nao (doi cau truc trang?)", name)
                    out += emits
            except Exception as ex:  # noqa: BLE001
                log.warning("%s calendar loi: %s", name, ex)
        return out
