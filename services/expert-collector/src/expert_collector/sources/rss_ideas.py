"""Nguon RSS/Atom cong khai do nguoi dung cau hinh (EC_RSS_FEEDS): y tuong cua tac gia, bao cao CTCK VN.
Chi dung cho feed ma chu site CHO PHEP (RSS la kenh phat hanh cong khai). Parser la ham thuan."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from time import mktime
from typing import Any

import feedparser

from ..httpclient import PoliteClient
from ..models import ExpertInfo, SignalInfo, normalize_symbol
from .base import ExpertSource

_BUY = r"(?:mua|khả quan|kha quan|outperform|long(?![- ]?term)|buy|bullish|tích cực|tang trong)"
_SELL = r"(?:bán|ban|kém khả quan|kem kha quan|underperform|short(?![- ]?term)|sell|bearish|giảm tỷ trọng)"
_FXCCY = "EUR|USD|GBP|JPY|CHF|AUD|NZD|CAD"
_FX_RE = re.compile(rf"\b((?:{_FXCCY})[/ ]?(?:{_FXCCY})|XAU[/ ]?USD|XAG[/ ]?USD|BTC[/ ]?USD|ETH[/ ]?USD)\b", re.I)
_VN_A = re.compile(rf"\b({_BUY}|{_SELL})\b[^A-Za-z0-9]{{0,20}}(?:cổ phiếu|cp|mã)?\s*((?-i:[A-Z]{{3}}))\b", re.I)
# ma co phieu phai VIET HOA that (re.I khong duoc bien 'giá', 'các' thanh ma); da gap 'VN:GIA' khi thu voi RSS that
_VN_B = re.compile(rf"\b((?-i:[A-Z]{{3}}))\b\s*[:\-–]\s*({_BUY}|{_SELL})\b", re.I)
_TARGET = re.compile(r"(?:giá mục tiêu|target(?: price)?|tp)\D{0,6}([0-9][0-9.,]*)", re.I)
_NOT_TICKERS = {"CEO", "GDP", "CPI", "USD", "EUR", "FED", "ETF", "IPO", "PMI", "BUY", "THE", "VND"}


def classify_side(text: str) -> str | None:
    t = text.lower()
    sell = re.search(rf"\b{_SELL}\b", t)
    buy = re.search(rf"\b{_BUY}\b", t)
    # 'kém khả quan' chua 'khả quan' -> uu tien sell neu khop truoc/dai hon
    if sell and (not buy or sell.start() <= buy.start()):
        return "sell"
    if buy:
        return "buy"
    return None


def extract_symbol_and_side(title: str, summary: str = "") -> tuple[str, str] | None:
    """Tra ve (symbol_chuan_hoa, side) hoac None neu khong du chac chan."""
    # FX: cap/vang phai nam trong TIEU DE va huong cung lay tu tieu de (than bai co 'long/short/buy' trong van xuoi
    # sinh tin hieu rac khi kiem chung voi RSS that 2026-10-11).
    m = _FX_RE.search(title)
    if m:
        side = classify_side(title)
        return (normalize_symbol(m.group(1)), side) if side else None
    for rx, order in ((_VN_A, "side-first"), (_VN_B, "sym-first")):
        for mm in rx.finditer(title) or []:
            side_s, sym = (mm.group(1), mm.group(2)) if order == "side-first" else (mm.group(2), mm.group(1))
            sym = sym.upper()
            if sym in _NOT_TICKERS or not sym.isalpha():
                continue
            side = classify_side(side_s)
            if side:
                return f"VN:{sym}", side
    return None


_OUTLOOK_TITLE = re.compile(
    rf"^\s*((?:{_FXCCY})[/ ]?(?:{_FXCCY})|XAU[/ ]?USD|XAG[/ ]?USD)\s+Weekly\s+(?:Outlook|Report)\b", re.I)
_UP = re.compile(r"\bfurther\s+(?:rise|gain|rally|upside|advance)\b", re.I)
_DOWN = re.compile(r"\bfurther\s+(?:decline|fall|downside|drop|loss)\b", re.I)
_HOLDS = re.compile(r"as long as\s+([0-9][0-9.,]*)\s+(?:minor\s+|key\s+)?(?:support|resistance)\s+holds", re.I)


def extract_technical_bias(title: str, summary: str) -> tuple[str, str, float | None] | None:
    """Mau 'EUR/USD Weekly Outlook' (ActionForex): 'Initial bias remains neutral ... further decline is expected as long as
    1.3310 resistance holds'. Tra ve (symbol, side, muc_vo_hieu_hoa) hoac None neu khong co huong ro rang.
    Huong = cum 'further rise/decline' xuat hien DAU TIEN trong van ban."""
    m = _OUTLOOK_TITLE.match(title)
    if not m:
        return None
    text = re.sub(r"\s+", " ", summary)
    up, down = _UP.search(text), _DOWN.search(text)
    if not up and not down:
        return None
    side = "buy" if (up and (not down or up.start() < down.start())) else "sell"
    h = _HOLDS.search(text)
    level = float(h.group(1).replace(",", "")) if h else None
    return normalize_symbol(m.group(1)), side, level


def parse_feed(xml: str, expert_id: str, source: str = "rss_ideas", mode: str = "ideas") -> list[SignalInfo]:
    """mode='ideas' (tieu de co long/short/mua/ban...) | 'technical_outlook' (ban tin 'XXX/YYY Weekly Outlook')."""
    d = feedparser.parse(xml)
    out: list[SignalInfo] = []
    for e in d.entries:
        title = e.get("title", "")
        summary = re.sub(r"<[^>]+>", " ", e.get("summary", ""))
        if mode == "technical_outlook":
            tb = extract_technical_bias(title, summary)
            if tb:
                ts = e.get("published_parsed") or e.get("updated_parsed")
                out.append(SignalInfo(symbol=tb[0], side=tb[1], sl=tb[2],
                                      opened_at=datetime.fromtimestamp(mktime(ts), tz=timezone.utc) if ts else None,
                                      status="open", url=e.get("link", ""),
                                      raw={"title": title, "guid": e.get("id", ""), "expert_id": expert_id,
                                           "kind": "technical_outlook", "note": "huong tuan; sl = muc vo hieu hoa neu co"}))
            continue
        hit = extract_symbol_and_side(title, summary)
        if not hit:
            continue
        sym, side = hit
        ts = e.get("published_parsed") or e.get("updated_parsed")
        opened = datetime.fromtimestamp(mktime(ts), tz=timezone.utc) if ts else None
        tm = _TARGET.search(f"{title} {summary}")
        tp = None
        if tm:
            try:
                tp = float(tm.group(1).replace(",", ""))
            except ValueError:
                tp = None
        out.append(SignalInfo(symbol=sym, side=side, tp=tp, opened_at=opened, status="open",
                              url=e.get("link", ""), raw={"title": title, "guid": e.get("id", ""), "expert_id": expert_id}))
    return out


class RssIdeasSource(ExpertSource):
    name = "rss_ideas"
    tos_risk = "low"
    warning = ("Chi them feed ma chu site cong bo RSS cong khai. TradingView: co RSS /feed/ nhung ToS cam thu thap tu dong "
               "va dung phi hien thi -> KHONG dung.")

    def __init__(self, client: PoliteClient, feeds: list[dict[str, Any]]):
        self.client, self.feeds = client, feeds
        self._mode = {(f.get("expert_id") or f"rss:{f['name']}"): f.get("mode", "ideas") for f in feeds}

    async def list_experts(self) -> list[ExpertInfo]:
        out = []
        for f in self.feeds:
            eid = f.get("expert_id") or f"rss:{f['name']}"
            out.append(ExpertInfo(expert_id=eid, source=self.name, display_name=f.get("name", eid),
                                  url=f["url"], reputation=dict(f.get("reputation") or {})))
        return out

    async def fetch_signals(self, expert: ExpertInfo) -> list[SignalInfo]:
        xml = await self.client.get_text(expert.url)
        return parse_feed(xml, expert.expert_id, self.name, self._mode.get(expert.expert_id, "ideas"))
