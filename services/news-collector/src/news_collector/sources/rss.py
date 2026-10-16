"""RSS/Atom qua feedparser. Danh sách feed ở config/feeds.yaml."""
from __future__ import annotations

import calendar
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import feedparser

from ..models import Emit
from .base import Context, Source, news_emit

log = logging.getLogger("news_collector.rss")
_TAG = re.compile(r"<[^>]+>")
MAX_AGE_DAYS = 180


# pubDate kieu "10/14/2026 6:54:00 PM" (tuoitre, baochinhphu): feedparser khong hieu -> published_at NULL (QA vong 4)
_MDY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?\s*$")


def _parse_mdy(raw: str, tz_h: float) -> datetime | None:
    m = _MDY.match(raw or "")
    if not m:
        return None
    mo, d, y, h, mi, sec, ap = m.groups()
    h = int(h)
    if ap:
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    try:
        local = datetime(int(y), int(mo), int(d), h, int(mi), int(sec or 0), tzinfo=timezone(timedelta(hours=tz_h)))
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def _dt(entry, feed: dict | None = None) -> datetime | None:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    feed = feed or {}
    # chuoi ngay khong co mui gio: dung tz_offset_h cua feed, mac dinh +7 cho bao tieng Viet, 0 cho con lai
    tz_h = float(feed.get("tz_offset_h", 7 if feed.get("lang") == "vi" else 0))
    for k in ("published", "updated"):
        got = _parse_mdy(entry.get(k) or "", tz_h)
        if got:
            return got
    return None


def _upgrade_scheme(url: str, feed_url: str) -> str:
    """Nguon RSS https nhung ban tin tra link http:// (vd BOJ) -> cung bai co 2 URL (http/https) => tin trung (QA vong 2).
    Chi nang cap khi cung host voi URL cua feed (feed da la https)."""
    if url.startswith("http://") and feed_url.startswith("https://"):
        fh = urlsplit(feed_url).hostname
        if fh and urlsplit(url).hostname == fh:
            return "https://" + url[len("http://"):]
    return url


def parse_feed(body: bytes, feed: dict, ctx: Context) -> list[Emit]:
    d = feedparser.parse(body)
    out: list[Emit] = []
    for e in d.entries:
        url = e.get("link")
        title = e.get("title")
        if not url or not title:
            continue
        url = _upgrade_scheme(url, feed.get("url") or "")
        when = _dt(e, feed)
        # feed luu tru (BLS archives) / bai cu tai xuat (Guardian 2014) -> bo bai qua cu (QA vong 4: published_at >1 nam)
        if when and when < ctx.now() - timedelta(days=float(feed.get("max_age_days", MAX_AGE_DAYS))):
            continue
        raw = e.get("summary", "") or (e.get("content") or [{}])[0].get("value", "")
        summary = html.unescape(_TAG.sub(" ", raw or ""))
        cap = feed.get("summary_max")  # bao thuong mai: gioi han tom tat ngan (headline syndication)
        if cap and len(summary) > cap:
            summary = summary[:cap].rstrip() + "…"
        out.append(news_emit(ctx, url=url, title=html.unescape(title), summary=summary or None,
                             published_at=when, source=feed["id"], lang=feed.get("lang"),
                             default_symbols=feed.get("symbols", [])))
    return out


class RssSource(Source):
    name = "rss"

    def __init__(self, interval: float = 900):
        self.interval = interval

    async def fetch(self, ctx: Context) -> list[Emit]:
        cfg = ctx.load_yaml("feeds.yaml")
        out: list[Emit] = []
        for feed in cfg.get("feeds", []):
            if not feed.get("enabled", True):
                continue
            try:
                body, not_modified = await ctx.client.get(feed["url"])
            except Exception as ex:  # một feed lỗi không làm hỏng feed khác
                log.warning("rss %s lỗi: %s", feed["id"], ex)
                continue
            if not_modified or body is None:
                continue
            out.extend(parse_feed(body, feed, ctx))
        return out
