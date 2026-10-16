"""Nguon Y KIEN chuyen gia/to chuc: danh muc `opinion_catalog` + `config/sources.d/*.yaml` (xem sources_loader).
Moi muc = 1 "chuyen gia"; moi bai = 1 OpinionInfo (tieu de + link + tom tat ngan + chu de + ma lien quan + xu huong theo quy tac).
Loai (kind): rss (RSS/Atom, YouTube/podcast/Mastodon cung la RSS), bsky (Bluesky public AppView, khong xac thuc), form4 (Form 4 giao dich noi bo).
Mo rong: `register_kind("ten", async_fn(source, entry) -> list[OpinionInfo])` trong module providers_<ten>.py.
KHONG sinh khuyen nghi mua/ban: chi nhan tham khao. Ton trong robots/ToS/rate limit (PoliteClient)."""
from __future__ import annotations

import calendar
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import feedparser

from ..httpclient import PoliteClient
from ..models import ExpertInfo, OpinionInfo
from ..stance import classify_stance, detect_topics, is_finance_relevant, tag_symbols
from .base import ExpertSource

log = logging.getLogger(__name__)

MAX_ITEMS = 15
MAX_AGE = timedelta(days=30)
BSKY_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"

_KINDS: dict[str, Callable[["OpinionFeedsSource", dict], Awaitable[list[OpinionInfo]]]] = {}


def register_kind(name: str, fn: Callable[["OpinionFeedsSource", dict], Awaitable[list[OpinionInfo]]]) -> None:
    _KINDS[name] = fn


def clean_text(s: str, limit: int) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    if "&" in t:
        t = html.unescape(t)   # nguon ma hoa kep (T&amp;amp;T) -> QA vong 3
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


# pubDate "10/14/2026 6:54:00 PM" (tuoitre, baochinhphu; gio VN) feedparser khong hieu -> published_at NULL (QA vong 4)
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


def _ts(e: Any, cfg: dict | None = None) -> datetime | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    if t:
        return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)   # struct_time cua feedparser la UTC (mktime = gio dia phuong)
    cfg = cfg or {}
    tz_h = float(cfg.get("tz_offset_h", 7 if cfg.get("lang") == "vi" else 0))
    for k in ("published", "updated"):
        got = _parse_mdy(e.get(k) or "", tz_h)
        if got:
            return got
    return None


def _norm_url(url: str, feed_url: str) -> str:
    """Chuan hoa link bai: tuong doi -> tuyet doi (theo URL feed); http -> https khi cung host voi feed https (cung bai khong co 2 URL: QA vong 2/3, N1)."""
    if not url:
        return url
    feed_url = feed_url or ""
    if not url.startswith(("http://", "https://")) and feed_url.startswith("http"):
        url = urljoin(feed_url, url)
    if url.startswith("http://") and feed_url.startswith("https://"):
        fh = urlsplit(feed_url).hostname
        if fh and urlsplit(url).hostname == fh:
            return "https://" + url[len("http://"):]
    return url


def _build(entry_cfg: dict, url: str, title: str, summary: str, when: datetime | None, author: str = "", extra: dict | None = None) -> OpinionInfo | None:
    title = clean_text(title, 220)
    url = _norm_url(url, str(entry_cfg.get("url") or "")) if entry_cfg.get("kind") == "rss" else url
    now = datetime.now(timezone.utc)
    if when and when > now + timedelta(days=1):
        when = None   # ngay tuong lai = ngay su kien/hoi thao (vd PIIE), khong phai ngay dang bai
    elif when and when > now + timedelta(hours=1):
        when = now    # ban tin "ngay mai" dang toi hom truoc, chi co ngay 00:00 gio VN (vd PHS) -> lay gio thu thap (QA vong 4)
    if not url or not title:
        return None
    text = f"{title} {summary}"
    if entry_cfg.get("kw") and not is_finance_relevant(text, 1 if entry_cfg["kind"] == "bsky" else 2):
        return None
    mode = entry_cfg.get("mode", "mkt")
    stance, score = classify_stance(title, summary, mode)
    return OpinionInfo(url=url, title=title, summary=summary, published_at=when, lang=entry_cfg.get("lang", "en"),
                       symbols=tag_symbols(text, entry_cfg.get("symbols") or ()), topics=detect_topics(title, summary, entry_cfg.get("topics") or ()),
                       stance=stance, stance_score=score, author=author, raw={"group": entry_cfg["group"], **(extra or {})})


def parse_rss_opinions(xml: str, cfg: dict, now: datetime | None = None) -> list[OpinionInfo]:
    now = now or datetime.now(timezone.utc)
    d = feedparser.parse(xml)
    out: list[OpinionInfo] = []
    for e in d.entries[:50]:
        when = _ts(e, cfg)
        if when and now - when > MAX_AGE:
            continue
        smax = int(cfg.get("summary_max", 300))
        summary = clean_text(e.get("summary", "") or (e.get("content") or [{}])[0].get("value", ""), smax)
        author = clean_text(e.get("author", ""), 80) if cfg.get("author") else ""
        op = _build(cfg, e.get("link", ""), e.get("title", ""), summary, when, author)
        if op:
            out.append(op)
        if len(out) >= MAX_ITEMS:
            break
    return out


def parse_bsky_opinions(js: dict, cfg: dict, now: datetime | None = None) -> list[OpinionInfo]:
    """getAuthorFeed (filter=posts_no_replies): chi bai CUA CHINH tai khoan (bo repost/tra loi), bai >= 40 ky tu va lien quan tai chinh."""
    now = now or datetime.now(timezone.utc)
    handle = cfg["url"]
    out: list[OpinionInfo] = []
    for it in js.get("feed", []):
        if it.get("reason"):  # repost/pin
            continue
        post = it.get("post") or {}
        author = (post.get("author") or {}).get("handle", "")
        rec = post.get("record") or {}
        if author != handle or rec.get("reply"):
            continue
        text = clean_text(rec.get("text", ""), 600)
        if len(text) < 40:
            continue
        try:
            when = datetime.fromisoformat(str(rec.get("createdAt", "")).replace("Z", "+00:00"))
        except ValueError:
            when = None
        if when and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when and now - when > MAX_AGE:
            continue
        rkey = (post.get("uri") or "").rsplit("/", 1)[-1]
        url = f"https://bsky.app/profile/{handle}/post/{rkey}"
        title = text if len(text) <= 140 else text[:139].rstrip() + "…"
        op = _build(cfg, url, title, text[:300], when, extra={"kind": "social_post"})
        if op:
            out.append(op)
        if len(out) >= MAX_ITEMS:
            break
    return out


# ---------------- Form 4 (giao dich noi bo): dung providers_insiders (daily-index, robots cho phep /Archives) ----------------
def signal_to_opinion(sig) -> OpinionInfo:
    """SignalInfo (insider_buy/insider_sell) -> OpinionInfo tieng Viet; KHONG phai khuyen nghi: stance chi mo ta chieu giao dich."""
    r = sig.raw
    buy = sig.side == "buy"
    owner = r.get("owner") or "Nguoi noi bo"
    role = r.get("title") or ", ".join(r.get("roles") or []) or "Nguoi noi bo"
    ticker = sig.symbol.split(":", 1)[-1]
    shares, val, px = float(r.get("shares") or 0), float(r.get("value_usd") or 0), float(r.get("price") or 0)
    verb = "MUA" if buy else "BAN"
    title = f"Giao dich noi bo: {owner} ({role}) {verb} {shares:,.0f} cp {ticker} ~${val:,.0f} (gia TB ${px:,.2f})"
    summary = f"{r.get('issuer') or ticker}: {verb.lower()} thi truong mo, khong theo ke hoach 10b5-1."
    if r.get("cluster"):
        summary += f" {r['cluster']} nguoi noi bo cung mua {ticker} (cum)."
    summary += " Du lieu ho so phap ly (Form 4); ban thuong do thue/da dang hoa nen tin hieu yeu hon mua. Chi la tham khao."
    slug = re.sub(r"[^a-z0-9]+", "-", owner.lower()).strip("-")[:40]
    strength = float(r.get("strength") or 0.3)
    return OpinionInfo(url=f"{sig.url}#{slug}-{sig.side}", title=title, summary=summary, published_at=sig.opened_at, lang="vi",
                       symbols=[sig.symbol], topics=["co_phieu"], stance="bullish" if buy else "bearish",
                       stance_score=round((0.5 if buy else -0.25) * strength + (0.1 if buy else -0.05), 2), author=owner,
                       raw={"group": "insider", "kind": r.get("kind"), "value_usd": val, "shares": shares, "role": role,
                            "cluster": r.get("cluster", 0), "strength": strength, "ticker": ticker})


class OpinionFeedsSource(ExpertSource):
    name = "opinion_feeds"
    tos_risk = "low"
    warning = ("Chi nguon cong khai co RSS/API hop le; ton trong robots/rate limit. Y kien tham khao, KHONG phai khuyen nghi. "
               "Nguon cam/chong bot/yeu cau dang nhap (TradingView, YouTube /feeds/, Myfxbook...) khong duoc them.")

    def __init__(self, client: PoliteClient, entries: list[dict], clock=None):
        import time as _t
        self.client = client
        self.entries = [e for e in entries if e.get("enabled", True)]
        self._by_id = {f"op:{e['id']}": e for e in self.entries}
        self._clock = clock or _t.monotonic
        self._next: dict[str, float] = {}
        self._seen_f4: set[str] = set()
        self._f4 = None
        unsupported = [e['id'] for e in self.entries if e['kind'] not in {'rss', 'bsky', 'form4'} and e['kind'] not in _KINDS]
        if unsupported:
            log.warning('opinion_feeds: %d nguon chua co provider (bo qua): %s', len(unsupported), ','.join(unsupported[:10]))
            self.entries = [e for e in self.entries if e['id'] not in unsupported]
            self._by_id = {f"op:{e['id']}": e for e in self.entries}

    async def list_experts(self) -> list[ExpertInfo]:
        out = []
        for e in self.entries:
            url = f"https://bsky.app/profile/{e['url']}" if e["kind"] == "bsky" else e["url"]
            out.append(ExpertInfo(expert_id=f"op:{e['id']}", source=self.name, display_name=e["name"], url=url,
                                  reputation={"kind": "opinion", "credibility": e["cred"], "group": e["group"], "org_type": e.get("org_type", ""),
                                              "lang": e.get("lang", "en"), "bias": e.get("bias", ""), "mode": e.get("mode", "mkt")}))
        return out

    def _due(self, eid: str, every: float) -> bool:
        now = self._clock()
        if now < self._next.get(eid, 0.0):
            return False
        self._next[eid] = now + every
        return True

    async def fetch_opinions(self, expert: ExpertInfo) -> list[OpinionInfo]:
        cfg = self._by_id.get(expert.expert_id)
        if not cfg or not self._due(expert.expert_id, float(cfg.get("every", 3600))):
            return []
        kind = cfg["kind"]
        if kind == "rss":
            xml = await self.client.get_text_cond(cfg["url"])
            return parse_rss_opinions(xml, cfg) if xml else []
        if kind == "bsky":
            txt = await self.client.get_text_cond(BSKY_API, {"actor": cfg["url"], "limit": 30, "filter": "posts_no_replies"})
            return parse_bsky_opinions(json.loads(txt), cfg) if txt else []
        if kind == "form4":
            return await self._fetch_form4(cfg)
        fn = _KINDS.get(kind)
        if fn:
            return await fn(self, cfg)
        log.warning("kind chua ho tro: %s (%s)", kind, cfg["id"])
        return []

    async def _fetch_form4(self, cfg: dict, max_new: int = 300) -> list[OpinionInfo]:
        from ..providers_insiders import InsiderForm4Source, SEC_ARCHIVES, _accession_from_path, build_signals, extract_ownership_xml, parse_form4
        if self._f4 is None:
            self._f4 = InsiderForm4Source(self.client, lookback_days=1, use_atom=False)
        txs = []
        fetched = 0
        for f in await self._f4._filings():
            path = f["path"]
            if path in self._seen_f4:
                continue
            if fetched >= max_new:
                break
            self._seen_f4.add(path)
            fetched += 1
            try:
                doc = await self.client.get_text(SEC_ARCHIVES + path, cache=False)
            except Exception:  # noqa: BLE001
                continue
            xml = extract_ownership_xml(doc)
            if xml:
                txs += parse_form4(xml, _accession_from_path(path))
        if len(self._seen_f4) > 20000:
            self._seen_f4 = set(list(self._seen_f4)[-8000:])
        return [signal_to_opinion(sg) for sg in build_signals(txs)]
