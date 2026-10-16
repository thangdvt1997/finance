"""Truy cap du lieu cho /v1/intel/* (chi DOC). PgRepo -> SQL tham so hoa; InMemoryRepo -> loc list (cho test).

Chuoi nen tra ve: dict[symbol -> list[Bar]] tang dan theo thoi gian; khi nhieu nguon cung (symbol, tf, ts_open) giu 1 nen
(DISTINCT ON ... ORDER BY source, giong /v1/symbols va docs/DATA_SOURCE_PRIORITY.md). Cache TTL ngan trong tien trinh.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from .intel_calc import Bar

_CACHE: dict[Any, tuple[float, Any]] = {}
_LOCKS: dict[Any, Any] = {}


async def cached(key: Any, ttl: float, factory: Callable[[], Awaitable[Any]]) -> Any:
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = await factory()
    _CACHE[key] = (time.monotonic(), val)
    if len(_CACHE) > 400:                       # cat bo bo nho: bo muc cu nhat
        for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:100]:
            _CACHE.pop(k, None)
    return val


def clear_cache() -> None:
    _CACHE.clear()


def _is_pg(repo) -> bool:
    return hasattr(repo, "pool") and hasattr(repo, "_q")


async def bars(repo, tf: str, since: datetime, symbols: list[str] | None = None) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    if _is_pg(repo):
        rows = await repo._q(
            "SELECT symbol, ts_open, o, h, l, c, v FROM (SELECT DISTINCT ON (symbol, ts_open) symbol, ts_open, o, h, l, c, v FROM bars "
            "WHERE tf = $1 AND ts_open > $2 AND ($3::text[] IS NULL OR symbol = ANY($3)) ORDER BY symbol, ts_open, source) d "
            "ORDER BY symbol, ts_open", tf, since, symbols or None)
    else:
        seen: dict[tuple, dict] = {}
        for r in repo.t.get("bars", []):
            if r["tf"] == tf and r["ts_open"] > since and (not symbols or r["symbol"] in symbols):
                seen.setdefault((r["symbol"], r["ts_open"]), r)
        rows = sorted(seen.values(), key=lambda r: (r["symbol"], r["ts_open"]))
    for r in rows:
        out.setdefault(r["symbol"], []).append((r["ts_open"], float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"] or 0)))
    return out


async def daily(repo, days: int = 400, symbols: list[str] | None = None) -> dict[str, list[Bar]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    if symbols:
        return await bars(repo, "D1", since, symbols)
    return await cached(("d1", id(repo), days), 60, lambda: bars(repo, "D1", since))


async def intraday(repo, tf: str, days: int, symbols: list[str] | None = None) -> dict[str, list[Bar]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return await cached(("intra", id(repo), tf, days, tuple(symbols or ())), 30, lambda: bars(repo, tf, since, symbols))


async def quotes(repo) -> dict[str, dict]:
    rows = await cached(("quotes", id(repo)), 15, lambda: repo.quotes_latest(None, 10_000))
    return {r["symbol"]: r for r in rows}


def with_quote(bs: list[Bar], q: dict | None, now: datetime, fresh: timedelta = timedelta(hours=3)) -> tuple[list[Bar], float | None]:
    """Gop quote moi (<= fresh) vao chuoi D1: quote sang ngay UTC moi -> them nen tong hop (dong cua truoc -> gia quote); cung ngay -> cap nhat dong cua."""
    if not bs or not q or not q.get("ts") or now - q["ts"] > fresh:
        return bs, None
    vals = [x for x in (q.get("bid"), q.get("ask")) if x and x > 0]
    if not vals:
        return bs, None
    px = sum(vals) / len(vals)
    qd = q["ts"].astimezone(timezone.utc).date()
    last = bs[-1]
    if qd > last[0].astimezone(timezone.utc).date():
        syn = (datetime(qd.year, qd.month, qd.day, tzinfo=timezone.utc), last[4], max(last[4], px), min(last[4], px), px, 0.0)
        return bs + [syn], px
    return bs[:-1] + [(last[0], last[1], max(last[2], px), min(last[3], px), px, last[5])], px


# ---------------------------------------------------------------------------------------------------- tin tuc / lich / vi the
async def news_rows(repo, since: datetime, until: datetime | None, symbol: str | None, words: list[str], limit: int = 700) -> list[dict]:
    if _is_pg(repo):
        pats = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
        return await repo._q(
            "SELECT url, title, summary, COALESCE(published_at, ingested_at) AS ts, lang, symbols, sentiment, sentiment_label, topics, importance FROM news_items "
            "WHERE COALESCE(source,'') <> 'qa' AND COALESCE(published_at, ingested_at) >= $1 AND ($2::timestamptz IS NULL OR COALESCE(published_at, ingested_at) < $2) "
            "AND ($3::text IS NULL OR $3 = ANY(symbols)) "
            "AND ($4::text[] IS NULL OR (title || ' ' || COALESCE(summary, '')) ILIKE ALL($4)) "
            "ORDER BY COALESCE(published_at, ingested_at) DESC NULLS LAST, url LIMIT $5", since, until, symbol, pats or None, limit)
    out = []
    for r in repo.t.get("news_items", []):
        ts = r.get("published_at") or r.get("ingested_at")
        if ts is None or ts < since or (until and ts >= until) or (symbol and symbol not in (r.get("symbols") or [])):
            continue
        text = (r["title"] + " " + (r.get("summary") or "")).lower()
        if all(w.lower() in text for w in words):
            out.append({**r, "ts": ts})
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out[:limit]


async def news_by_url(repo, url: str) -> dict | None:
    if _is_pg(repo):
        rows = await repo._q("SELECT url, title, summary, COALESCE(published_at, ingested_at) AS ts, lang, symbols, sentiment, sentiment_label, topics, importance FROM news_items WHERE url = $1 AND COALESCE(source,'') <> 'qa' LIMIT 1", url)
        return rows[0] if rows else None
    for r in repo.t.get("news_items", []):
        if r["url"] == url:
            return {**r, "ts": r.get("published_at") or r.get("ingested_at")}
    return None


async def calendar_indicators(repo, days: int = 800) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    if _is_pg(repo):
        return await repo._q(
            "SELECT title, country, count(*) AS n, count(actual) AS n_actual, max(ts) AS last_ts, "
            "(array_agg(impact ORDER BY ts DESC))[1] AS impact FROM calendar_events WHERE COALESCE(source,'') <> 'qa' AND ts > $1 AND ts < now() + interval '400 days' "
            "GROUP BY title, country HAVING count(*) >= 2 ORDER BY count(*) DESC, title LIMIT 400", since)
    agg: dict[tuple, dict] = {}
    for r in repo.t.get("calendar_events", []):
        a = agg.setdefault((r["title"], r.get("country")), {"title": r["title"], "country": r.get("country"), "n": 0, "n_actual": 0, "last_ts": r["ts"], "impact": r.get("impact")})
        a["n"] += 1
        a["n_actual"] += 1 if r.get("actual") else 0
        a["last_ts"] = max(a["last_ts"], r["ts"])
    return sorted((a for a in agg.values() if a["n"] >= 2), key=lambda a: -a["n"])


async def calendar_history(repo, title: str, country: str | None, limit: int) -> list[dict]:
    if _is_pg(repo):
        return await repo._q(
            "SELECT ts, actual, forecast, previous, impact, extra FROM calendar_events WHERE title = $1 AND country IS NOT DISTINCT FROM $2 "
            "ORDER BY ts DESC LIMIT $3", title, country, limit)
    rows = [r for r in repo.t.get("calendar_events", []) if r["title"] == title and r.get("country") == country]
    return sorted(rows, key=lambda r: r["ts"], reverse=True)[:limit]


async def positions_weekly(repo, kind: str = "cftc") -> list[dict]:
    """Lich su vi the dau co lon (bao cao hang tuan) theo symbol: [{expert_id, symbol, as_of, net_volume}] tang dan."""
    if _is_pg(repo):
        return await repo._q(
            "SELECT expert_id, symbol, as_of, net_volume FROM expert_positions WHERE source = $1 AND net_volume IS NOT NULL ORDER BY symbol, as_of", kind)
    rows = [r for r in repo.t.get("expert_positions", []) if r.get("source") == kind and r.get("net_volume") is not None]
    return sorted(rows, key=lambda r: (r["symbol"], r["as_of"]))
