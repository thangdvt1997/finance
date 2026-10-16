"""Marketaux Free: tin tai chinh gan THUC THE (entity) + sentiment (-1..1). CAN MARKETAUX_TOKEN (mien phi); thieu => nguon tu tat.

Gioi han free: 100 request/NGAY, moi request toi da 3 bai -> tiet kiem:
- 1 request/lan poll, xoay vong qua cac truy van o config/marketaux_queries.yaml (thuc the co phieu truoc, tu khoa vi mo sau);
- tran ngay `daily_budget` (mac dinh 70 < 100, chua du dia cho khoi dong lai container vi bo dem nam trong RAM);
- `published_after` = moc bai moi nhat da thay (khong tai lai bai cu); HTTP 402/429 => nghi het hang muc den 00:00 UTC.
- sentiment bai = trung binh sentiment_score cac entity khop; symbols = luat symbol_map + entity co phieu My -> `US:<ticker>`.
Token di qua query `api_token` (Marketaux khong co header) -> moi loi deu bi lam sach, token KHONG bao gio vao log/status.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..models import Emit
from .base import Context, Source, news_emit

log = logging.getLogger("news_collector.marketaux")
API = "https://api.marketaux.com/v1/news/all"
US_EXCHANGES = ("NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "CBOE")


def _entity_symbol(e: dict) -> str | None:
    sym, ex = (e.get("symbol") or "").upper(), (e.get("exchange") or "").upper()
    if sym and sym.replace("-", "").replace(".", "").isalnum() and any(x in ex for x in US_EXCHANGES):
        return f"US:{sym}"
    return None


def parse_articles(body: bytes, ctx: Context, query_id: str = "") -> tuple[list[Emit], datetime | None]:
    """-> (emits, published_at moi nhat)."""
    data = json.loads(body)
    if not isinstance(data, dict) or "data" not in data:
        raise ValueError(f"Marketaux tra ve khong hop le: {str(data)[:120]}")
    out, newest = [], None
    for a in data.get("data") or []:
        url, title = a.get("url"), a.get("title")
        if not url or not title:
            continue
        try:
            pub = datetime.fromisoformat(str(a["published_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError):
            pub = None
        newest = max(newest, pub) if newest and pub else (pub or newest)
        ents = a.get("entities") or []
        scores = [float(e["sentiment_score"]) for e in ents if e.get("sentiment_score") is not None]
        extra = " ".join(str(e.get("name") or "") for e in ents)
        e = news_emit(ctx, url=url, title=title, summary=a.get("description") or a.get("snippet"), published_at=pub,
                      source=f"marketaux:{a.get('source') or query_id}", lang=a.get("language") or "en", extra_text=extra)
        syms = list(e.payload["symbols"])
        for ent in ents:
            s = _entity_symbol(ent)
            if s and s not in syms:
                syms.append(s)
        e.payload["symbols"] = syms
        if scores:
            e.payload["sentiment"] = max(-1.0, min(1.0, round(sum(scores) / len(scores), 4)))
        out.append(e)
    return out, newest


class MarketauxSource(Source):
    name = "news_marketaux"

    def __init__(self, token: str, interval: float = 1200, daily_budget: int = 70):
        if not token:
            raise ValueError("MARKETAUX_TOKEN bat buoc")
        self.token = token
        self.interval = max(interval, 600)           # >= 10 phut -> toi da 144 lan/ngay, tran ngay chan o daily_budget
        self.daily_budget = max(1, min(daily_budget, 95))
        self._rr = 0
        self._day: str | None = None
        self.calls_today = 0
        self._blocked_day: str | None = None         # het hang muc trong ngay UTC nay
        self._after: dict[str, datetime] = {}        # query id -> published_at moi nhat

    def info(self) -> dict:
        return {"calls_today": self.calls_today, "daily_budget": self.daily_budget, "exhausted": self._blocked_day == self._day}

    async def fetch(self, ctx: Context) -> list[Emit]:
        now = ctx.now()
        day = now.strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self.calls_today = day, 0
        if self._blocked_day == day or self.calls_today >= self.daily_budget:
            return []
        queries = [q for q in ctx.load_yaml("marketaux_queries.yaml").get("queries", []) if q.get("enabled", True)]
        if not queries:
            return []
        q = queries[self._rr % len(queries)]
        self._rr += 1
        after = self._after.get(q["id"]) or (now - timedelta(hours=int(q.get("lookback_hours", 6))))
        params = {"api_token": self.token, "language": q.get("language", "en"), "limit": 3, "sort": "published_at",
                  "published_after": (after + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")}
        for k in ("symbols", "search", "countries", "industries", "filter_entities", "min_match_score"):
            if q.get(k) not in (None, ""):
                params[k] = str(q[k]).lower() if isinstance(q[k], bool) else q[k]
        self.calls_today += 1
        try:
            body, _ = await ctx.client.get(API, params=params, use_cache=False)
        except httpx.HTTPStatusError as ex:
            code = ex.response.status_code if ex.response is not None else 0
            if code in (402, 429):
                self._blocked_day = day
                log.warning("marketaux: het hang muc/bi gioi han (HTTP %s) -> nghi den het ngay UTC", code)
                return []
            raise RuntimeError(f"Marketaux HTTP {code}") from None
        except Exception as ex:  # noqa: BLE001 - khong de token lot vao log/status qua URL trong thong diep loi
            raise RuntimeError(f"Marketaux loi {type(ex).__name__}: {str(ex).replace(self.token, '***')[:150]}") from None
        emits, newest = parse_articles(body or b"{}", ctx, q["id"])
        if newest:
            self._after[q["id"]] = max(newest, self._after.get(q["id"], newest))
        return emits
