"""MQL5 Signals - RUI RO ToS, TAT MAC DINH.

MQL5 khong cong bo API/RSS cho du lieu Signals; dich vu Signals co dieu khoan rieng
(mql5.com/en/signals/rules). Chi bat khi ban da DOC va CHAP NHAN dieu khoan va robots.txt
(EC_MQL5_ACCEPT_TOS=true + them 'mql5' vao EC_SOURCES). Provider chi doc trang cong khai do ban
liet ke trong EC_MQL5_URLS, ton trong robots.txt (PoliteClient), khong dang nhap, khong vuot chong bot.

LUU Y: selector duoi day la GIA DINH ve bo cuc HTML (chua kiem chung voi trang that vi nguon bi tat);
neu MQL5 doi bo cuc hoac cam, parser tra ve rong. Parser la ham thuan, test bang fixture."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..httpclient import PoliteClient
from ..models import ExpertInfo, PositionInfo, normalize_symbol
from .base import ExpertSource


def _num(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", s.replace(" ", ""))
    return float(m.group(0).replace(",", "")) if m else None


def parse_signal_page(html: str, url: str = "") -> ExpertInfo | None:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("[data-signal-id]")
    if root is None:
        return None
    sid = root["data-signal-id"]
    name = (root.select_one(".signal-name") or root).get_text(" ", strip=True)[:120]

    def val(cls: str) -> float | None:
        el = root.select_one(f".{cls}")
        return _num(el.get_text()) if el else None

    weeks = val("weeks")
    rep = {
        "gain_pct": val("growth"),
        "max_drawdown_pct": val("drawdown"),
        "months_active": round(weeks / 4.345, 1) if weeks is not None else 0,
        "followers": int(val("subscribers") or 0),
        "trades": int(val("trades") or 0) or None,
    }
    return ExpertInfo(expert_id=f"mql5:{sid}", source="mql5", display_name=name, url=url, reputation=rep)


def parse_open_positions(html: str) -> list[PositionInfo]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[PositionInfo] = []
    for tr in soup.select("table.open-trades tbody tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) < 6:
            continue
        side = c[1].lower()
        if side not in ("buy", "sell"):
            continue
        try:
            opened = datetime.strptime(c[0], "%Y.%m.%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            opened = None
        out.append(PositionInfo(symbol=normalize_symbol(c[2]), side=side, volume=_num(c[3]) or 0.0,
                                entry=_num(c[4]), sl=_num(c[5]) or None,
                                tp=_num(c[6]) or None if len(c) > 6 else None, opened_at=opened))
    return out


def parse_closed_trades(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select("table.history-trades tbody tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) >= 2 and _num(c[0]) is not None and _num(c[1]) is not None:
            out.append({"volume": _num(c[0]), "profit": _num(c[1])})
    return out


class Mql5Source(ExpertSource):
    name = "mql5"
    supports_positions = True
    tos_risk = "high"
    warning = "Khong co API/RSS cong khai; ToS Signals rieng. Tat mac dinh, can EC_MQL5_ACCEPT_TOS=true."

    def __init__(self, client: PoliteClient, urls: list[str], accept_tos: bool):
        self.client, self.urls, self.accept_tos = client, urls, accept_tos
        self._pages: dict[str, str] = {}

    async def list_experts(self) -> list[ExpertInfo]:
        if not self.accept_tos:
            return []
        out = []
        for u in self.urls:
            html = await self.client.get_text(u)
            self._pages[u] = html
            e = parse_signal_page(html, u)
            if e:
                out.append(e)
        return out

    async def fetch_positions(self, expert: ExpertInfo) -> list[PositionInfo]:
        html = self._pages.get(expert.url) or await self.client.get_text(expert.url)
        return parse_open_positions(html)

    async def fetch_trades(self, expert: ExpertInfo) -> list[dict]:
        html = self._pages.get(expert.url) or await self.client.get_text(expert.url)
        return parse_closed_trades(html)
