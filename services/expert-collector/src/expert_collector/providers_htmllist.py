"""Provider `html_list`: trang DANH SACH bai phan tich cong khai cua CTCK Viet Nam khong co RSS (render phia server, robots cho phep).
Chi lay tieu de + link + ngay (khong tai noi dung/PDF). Moi nguon 1 profile (selector/ngay) theo docs/sources/vietnam.md; id khac -> bo qua.
Doc trang qua PoliteClient (robots + rate limit + ETag); fail an toan (HTML doi cau truc -> 0 muc)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .models import OpinionInfo
from .sources.opinion_feeds import MAX_AGE, MAX_ITEMS, OpinionFeedsSource, _build, register_kind

_ICT = timezone(timedelta(hours=7))
_VCSC_CATS = ("phan-tich-doanh-nghiep", "bao-cao-nganh", "nhan-dinh-thi-truong", "bao-cao-trai-phieu-tien-te", "bao-cao-vi-mo",
              "bao-cao-chien-luoc-dau-tu", "y-kien-chuyen-gia", "phan-tich-ky-thuat")
_VCSC_LABEL = re.compile(r"\s*(?:Doanh Nghiệp|Báo Cáo Ngành|Thị Trường|Trái Phiếu & Tiền Tệ|Vĩ Mô|Chiến Lược|Ý Kiến Chuyên Gia|PT Kỹ Thuật)\s*$")


def _dmy(d: str, m: str, y: str) -> datetime | None:
    try:
        return datetime(int(y), int(m), int(d), tzinfo=_ICT).astimezone(timezone.utc)
    except ValueError:
        return None


def _vcsc(href: str, text: str):
    slug = href.rstrip("/").rsplit("/", 1)[-1]
    if "?page=" in href or slug in _VCSC_CATS:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*$", text)
    when = _dmy(*m.groups()) if m else None
    title = _VCSC_LABEL.sub("", text[: m.start()] if m else text).strip()
    return title, when


def _vdsc(href: str, text: str):
    m = re.match(r"\s*(\d{1,2}) tháng (\d{1,2}) - (\d{4})\s*(.*)$", text)
    if not m:
        return None
    return re.sub(r"\s*\d+\s*$", "", m.group(4)).strip(), _dmy(m.group(1), m.group(2), m.group(3))


def _phs(href: str, text: str):
    m = re.search(r"ban-tin-ngay-(\d{2})-(\d{2})-(\d{4})", href)
    if not text or text.lower().startswith("xem th"):
        return None
    return text, (_dmy(*m.groups()) if m else None)


def _shs(href: str, text: str):
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})\s*(.*)$", text)
    if not m:
        return None
    return re.split(r"\s+DIỄN BIẾN", m.group(4))[0].strip(), _dmy(m.group(1), m.group(2), m.group(3))


PROFILES = {
    "vn_vcsc_research": ("/trung-tam-phan-tich/", "https://www.vietcap.com.vn", _vcsc),
    "vn_vdsc_daily": ("/data/api/app/file-storage/", "https://www.vdsc.com.vn", _vdsc),
    "vn_phs_daily": ("/trung-tam-phan-tich/ban-tin-ngay-", "https://www.phs.vn", _phs),
    "vn_shs_daily": ("/nhan-dinh-thi-truong/", "https://www.shs.com.vn", _shs),
}


def parse_html_list(html: str, cfg: dict, now: datetime | None = None) -> list[OpinionInfo]:
    prof = PROFILES.get(cfg["id"])
    if not prof:
        return []
    prefix, base, fn = prof
    now = now or datetime.now(timezone.utc)
    soup = BeautifulSoup(html, "html.parser")
    out: list[OpinionInfo] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(prefix) or href in seen:
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        r = fn(href, text)
        if not r or not r[0]:
            continue
        title, when = r
        if when and (now - when > MAX_AGE or when > now + timedelta(days=1)):
            continue
        seen.add(href)
        op = _build(cfg, urljoin(base, quote(href, safe="/%?=&:@")), title, "", when)
        if op:
            out.append(op)
        if len(out) >= MAX_ITEMS:
            break
    return out


async def _fetch(src: OpinionFeedsSource, cfg: dict) -> list[OpinionInfo]:
    html = await src.client.get_text_cond(cfg["url"])
    return parse_html_list(html, cfg) if html else []


register_kind("html_list", _fetch)
