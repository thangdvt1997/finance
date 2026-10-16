"""GDELT DOC 2.0 (không key, ~1 req/5s). Truy vấn ở config/gdelt_queries.yaml."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..httpclient import HostCoolingDown
from ..models import Emit
from .base import Context, Source, news_emit

log = logging.getLogger("news_collector.gdelt")
HOST = "api.gdeltproject.org"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
LANG = {"english": "en", "vietnamese": "vi", "spanish": "es", "french": "fr", "german": "de", "chinese": "zh", "japanese": "ja"}


def parse_seendate(s: str | None) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_articles(body: bytes, q: dict, ctx: Context) -> list[Emit]:
    try:
        data = json.loads(body)
    except ValueError:  # GDELT trả text lỗi (vd query quá ngắn / rate limit) thay vì JSON
        log.warning("gdelt %s: phản hồi không phải JSON: %.80r", q["id"], body)
        return []
    out = []
    for a in data.get("articles", []) or []:
        url, title = a.get("url"), a.get("title")
        if not url or not title:
            continue
        out.append(news_emit(ctx, url=url, title=title, summary=None, published_at=parse_seendate(a.get("seendate")),
                             source=f"gdelt:{a.get('domain') or q['id']}",
                             lang=LANG.get((a.get("language") or "").lower(), a.get("language")),
                             default_symbols=q.get("symbols", [])))
    return out


class GdeltSource(Source):
    """Hang doi tuan tu (client ep >= 6s/host). 429 -> host cooldown (tang dan), bo qua phan con lai cua vong nay
    va vong sau bat dau tu truy van bi do (round-robin) -> khong truy van nao bi bo doi. Log 1 dong/su co."""
    name = "gdelt"

    def __init__(self, interval: float = 900):
        self.interval = interval
        self._rr = 0
        self._warned = False

    async def fetch(self, ctx: Context) -> list[Emit]:
        cfg = ctx.load_yaml("gdelt_queries.yaml")
        queries = [q for q in cfg.get("queries", []) if q.get("enabled", True)]
        out: list[Emit] = []
        if not queries:
            return out
        if (left := ctx.client.cooldown_left(HOST)) > 0:
            log.debug("gdelt: dang cooldown %.0fs, bo qua vong nay", left)
            return out
        n = len(queries)
        start = self._rr % n
        errors: list[str] = []
        done = 0
        for k in range(n):
            q = queries[(start + k) % n]
            params = {"query": q["query"], "mode": "artlist", "format": "json", "sort": "datedesc",
                      "maxrecords": str(q.get("maxrecords", 50)), "timespan": q.get("timespan", "1h")}
            try:
                body, _ = await ctx.client.get(API, params=params, use_cache=False)
            except HostCoolingDown as ex:
                self._rr = start + k
                if not self._warned:
                    log.warning("gdelt: bi gioi han toc do (%d/%d truy van xong), nghi %.0fs", done, n, ex.retry_in)
                    self._warned = True
                else:
                    log.info("gdelt: van bi gioi han, nghi %.0fs", ex.retry_in)
                return out
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{q['id']}: {type(ex).__name__}")
                continue
            if b"limit requests" in body[:200].lower():  # 200 + van ban "Please limit requests to one every 5 seconds"
                delay = ctx.client.note_rate_limited(HOST)
                self._rr = start + k
                if not self._warned:
                    log.warning("gdelt: server yeu cau giam toc do, nghi %.0fs", delay)
                    self._warned = True
                return out
            done += 1
            self._warned = False
            ctx.client.note_ok(HOST)
            out.extend(parse_articles(body, q, ctx))
        self._rr = start
        if errors:
            log.warning("gdelt: %d/%d truy van loi (%s)", len(errors), n, "; ".join(errors))
        return out
