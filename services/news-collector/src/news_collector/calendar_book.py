"""So lich kinh te hop nhat: ghep su kien giua cac nguon, dien forecast/previous/actual con thieu, tinh surprise, gan nhom.

Nguyen tac: moi nguon van phat hang (event_id, source) cua minh (storage-writer upsert theo cap nay); so nay chi LAM GIAU payload
truoc khi phat (them `extra`: group, forecast_source, actual_source, surprise...) va nho 'actual' do nguon API (BLS/StatCan/...) tra ve
de phat lai khi so lieu duoc cong bo. Khong I/O -> de test.
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .values import format_like, surprise

CURRENCY_COUNTRY = {"USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP", "AUD": "AU", "CAD": "CA", "CHF": "CH", "NZD": "NZ", "CNY": "CN"}
OFFICIAL_SOURCES = {"bls", "fed", "ecb", "boe", "boj"}
PEER_WINDOW = timedelta(minutes=90)
_SYN = [(r"y/y", "yoy"), (r"m/m", "mom"), (r"q/q", "qoq"), (r"\bprelim(inary)?\b", "prelim")]


def country_key(c: str | None) -> str:
    c = (c or "").strip().upper()
    return CURRENCY_COUNTRY.get(c, c)


@functools.lru_cache(maxsize=4096)
def norm_title(t: str) -> str:
    t = (t or "").lower()
    for a, b in _SYN:
        t = re.sub(a, b, t)
    return re.sub(r"[^a-z0-9]+", "", t)


def add_months(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    i = y * 12 + (m - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def expected_period(ts: datetime, lag_months: int) -> str:
    ts = ts.astimezone(timezone.utc)
    return add_months(f"{ts.year:04d}-{ts.month:02d}", -int(lag_months))


def indicator_value(points: dict[str, float], period: str, ind: dict) -> tuple[float | None, float | None]:
    """(gia tri ky `period`, gia tri ky truoc) sau transform + scale. None neu thieu du lieu."""
    tr, scale = ind.get("transform", "level"), float(ind.get("scale", 1))

    def at(p: str) -> float | None:
        v = points.get(p)
        if v is None:
            return None
        if tr == "level":
            return v
        if tr == "diff":
            q = points.get(add_months(p, -1))
            return None if q is None else v - q
        if tr == "mom_pct":
            q = points.get(add_months(p, -1))
            return None if not q else (v / q - 1) * 100
        if tr == "yoy_pct":
            q = points.get(add_months(p, -12))
            return None if not q else (v / q - 1) * 100
        raise ValueError(f"transform la: {tr}")

    cur, prev = at(period), at(add_months(period, -1))
    return (None if cur is None else cur * scale, None if prev is None else prev * scale)


def load_enrich_config(config_dir: Path) -> dict:
    p = Path(config_dir) / "calendar_enrich.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


class CalendarBook:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        self.raw: dict[tuple[str, str], dict] = {}
        self.ext: dict[tuple[str, str], dict] = {}
        self.attempts: dict[tuple[str, str], int] = {}
        self.published: dict[tuple[str, str], str] = {}
        self._pidx: dict[tuple[str, str], list] | None = None
        self._groups = [(g["id"], {country_key(c) for c in g["countries"]}, [t.lower() for t in g["titles"]])
                        for g in self.cfg.get("groups", [])]
        self._inds = [(country_key(i["country"]), re.compile(i["title"], re.I), i) for i in self.cfg.get("indicators", [])]
        self.schedule = [int(x) for x in self.cfg.get("poll_schedule_min", [0, 1, 2, 4, 8, 15, 30, 60, 120, 240, 480])]
        self.give_up = timedelta(hours=float(self.cfg.get("give_up_hours", 36)))

    # -- phan loai ------------------------------------------------------------------------------------
    def group_of(self, p: dict) -> str | None:
        c, t = country_key(p.get("country")), (p.get("title") or "").lower()
        for gid, countries, titles in self._groups:
            if c in countries and any(x in t for x in titles):
                return gid
        return None

    def indicator_for(self, p: dict) -> dict | None:
        c = country_key(p.get("country"))
        for ic, rx, ind in self._inds:
            if ic == c and rx.search(p.get("title") or ""):
                return ind
        return None

    # -- vao/ra ---------------------------------------------------------------------------------------
    def ingest(self, payload: dict) -> dict:
        key = (payload["source"], str(payload["event_id"]))
        self.raw[key] = dict(payload)
        self._pidx = None
        return self.merged(key)

    def prune(self, now: datetime, keep_days: int = 45) -> None:
        cut = now - timedelta(days=keep_days)
        for k in [k for k, v in self.raw.items() if datetime.fromisoformat(v["ts"]) < cut]:
            for d in (self.raw, self.ext, self.attempts, self.published):
                d.pop(k, None)
            self._pidx = None

    def _peers(self, key: tuple[str, str], p: dict):
        if self._pidx is None:  # chi muc (quoc gia, tieu de chuan hoa) -> [(key, payload, ts)]
            self._pidx = {}
            for k, q in self.raw.items():
                self._pidx.setdefault((country_key(q.get("country")), norm_title(q["title"])), []).append(
                    (k, q, datetime.fromisoformat(q["ts"])))
        ts = datetime.fromisoformat(p["ts"])
        for k, q, qts in self._pidx.get((country_key(p.get("country")), norm_title(p["title"])), ()):
            if k != key and q["source"] != p["source"] and abs(qts - ts) <= PEER_WINDOW:
                yield k, q

    def merged(self, key: tuple[str, str]) -> dict:
        p = dict(self.raw[key])
        extra = dict(p.get("extra") or {})
        if g := self.group_of(p):
            extra["group"] = g
        for f in ("forecast", "previous"):  # dien tu nguon khac khi nguon nay khong co
            if not p.get(f):
                for _, q in self._peers(key, p):
                    if q.get(f):
                        p[f] = q[f]
                        extra[f"{f}_source"] = q["source"]
                        break
        ext = self.ext.get(key)
        if not p.get("actual"):
            for _, q in self._peers(key, p):
                if q.get("actual"):
                    p["actual"], extra["actual_source"] = q["actual"], q["source"]
                    break
        if not p.get("actual") and ext:
            p["actual"] = format_like(ext["value"], ext["unit"], p.get("forecast") or p.get("previous"), ext.get("decimals", 1))
            extra["actual_source"], extra["actual_period"], extra["actual_at"] = ext["provider"], ext["period"], ext["at"]
            if not p.get("previous") and ext.get("prev") is not None:
                p["previous"] = format_like(ext["prev"], ext["unit"], p.get("forecast"), ext.get("decimals", 1))
                extra["previous_source"] = ext["provider"]
        elif p.get("actual") and "actual_source" not in extra:
            extra["actual_source"] = p["source"]
        if p.get("actual") and p.get("forecast"):
            if s := surprise(p["actual"], p["forecast"], p["title"], self.cfg.get("surprise")):
                extra["surprise"] = s
        if p.get("forecast") and "forecast_source" not in extra:
            extra["forecast_source"] = p["source"]
        p["extra"] = extra or None
        return p

    @staticmethod
    def digest(p: dict) -> str:
        core = {k: p.get(k) for k in ("title", "country", "impact", "ts", "forecast", "previous", "actual", "extra")}
        return hashlib.sha1(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:12]

    def dirty(self) -> list[dict]:
        out = []
        for k in self.raw:
            m = self.merged(k)
            if self.published.get(k) != self.digest(m):
                out.append(m)
        return out

    def mark_published(self, p: dict) -> None:
        self.published[(p["source"], str(p["event_id"]))] = self.digest(p)

    # -- actual tu API ----------------------------------------------------------------------------------
    def set_actual(self, key: tuple[str, str], value: float, prev: float | None, ind: dict, period: str, now: datetime) -> None:
        self.ext[key] = {"value": value, "prev": prev, "unit": ind.get("unit", ""), "decimals": ind.get("decimals", 1),
                         "provider": ind["provider"], "period": period, "at": now.astimezone(timezone.utc).isoformat()}

    def _next_at(self, ts: datetime, n: int) -> datetime:
        if n < len(self.schedule):
            return ts + timedelta(minutes=self.schedule[n])
        return ts + timedelta(minutes=self.schedule[-1] + (n - len(self.schedule) + 1) * 240)

    def pending(self, now: datetime) -> list[tuple[tuple[str, str], dict, dict]]:
        """Su kien da toi gio, chua co actual, co chi so API hop le va den luot tham do."""
        out = []
        for key, p in self.raw.items():
            ts = datetime.fromisoformat(p["ts"])
            if ts > now or now - ts > self.give_up or p.get("actual") or key in self.ext:
                continue
            ind = self.indicator_for(p)
            if not ind or now < self._next_at(ts, self.attempts.get(key, 0)):
                continue
            out.append((key, p, ind))
        return out

    def mark_attempt(self, key: tuple[str, str]) -> None:
        self.attempts[key] = self.attempts.get(key, 0) + 1

    def stats(self, now: datetime | None = None) -> dict:
        n = len(self.raw)
        merged = [self.merged(k) for k in self.raw]
        return {"events": n, "with_forecast": sum(1 for m in merged if m.get("forecast")),
                "with_actual": sum(1 for m in merged if m.get("actual")),
                "with_surprise": sum(1 for m in merged if (m.get("extra") or {}).get("surprise")),
                "api_actuals": len(self.ext)}
