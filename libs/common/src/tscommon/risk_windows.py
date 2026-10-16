"""Bo loc rui ro tin: ham THUAN (khong I/O) tinh cua so rui ro quanh su kien lich HIGH impact theo tung symbol.

Dung chung boi `news-collector` (phat alert khi sap/vao/ra cua so) va `api-gateway` (REST /v1/risk-windows) de hai noi luon
cung mot ket qua. Cau hinh YAML (xem risk_windows.yaml): do rong cua so theo loai su kien/symbol, anh xa quoc gia->tien te->symbol.
Su kien dau vao la dict dang calendar.events: {event_id, source, country, title, impact, ts (ISO UTC hoac datetime), extra?}.
"""
from __future__ import annotations

import fnmatch
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

DEFAULT_PATH = Path(__file__).with_name("risk_windows.yaml")
_FX = re.compile(r"^([A-Z]{3})([A-Z]{3})$")


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path or os.getenv("RISK_WINDOWS_CONFIG") or DEFAULT_PATH)
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    d = cfg.setdefault("default", {})
    d.setdefault("before_min", 15)
    d.setdefault("after_min", 30)
    d.setdefault("warn_before_min", 30)
    cfg.setdefault("impacts", ["high"])
    cfg.setdefault("overrides", [])
    cfg.setdefault("universe", [])
    cfg.setdefault("symbol_currencies", {})
    cfg.setdefault("country_currency", {})
    cfg.setdefault("ignore_title_any", [])
    return cfg


def parse_ts(v: Any) -> datetime:
    dt = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _mins(delta: timedelta) -> int:
    """So phut lam tron LEN (con 0:30 -> 1 phut) de banner khong hien '0 phut' khi chua het."""
    return math.ceil(delta.total_seconds() / 60)


def event_currency(country: str | None, cfg: dict) -> str | None:
    if not country:
        return None
    return cfg.get("country_currency", {}).get(str(country).strip().upper())


def symbol_currencies(symbol: str, cfg: dict) -> set[str]:
    """Tap tien te ma symbol phoi nhiem. Cap forex AAABBB -> {AAA,BBB}; vang/bac -> {XAU|XAG, USD}; map YAML cho chi so/co phieu."""
    s = symbol.strip().upper()
    for pat, cur in cfg.get("symbol_currencies", {}).items():
        if fnmatch.fnmatchcase(s, str(pat).upper()):
            return {str(c).upper() for c in cur}
    m = _FX.match(s)
    return {m.group(1), m.group(2)} if m else set()


def _match_any(text: str, needles: Iterable[str]) -> bool:
    t = text.lower()
    return any(n.lower() in t for n in needles)


def widths(ev: dict, symbol: str | None, cfg: dict) -> tuple[int, int, int]:
    """(before_min, after_min, warn_before_min) cho cap (su kien, symbol)."""
    d = cfg["default"]
    b, a, w = d["before_min"], d["after_min"], d["warn_before_min"]
    for o in cfg.get("overrides", []):
        if o.get("title_any") and not _match_any(ev.get("title", ""), o["title_any"]):
            continue
        if o.get("symbols_any") and not (symbol and any(fnmatch.fnmatchcase(symbol.upper(), str(p).upper()) for p in o["symbols_any"])):
            continue
        return o.get("before_min", b), o.get("after_min", a), o.get("warn_before_min", w)
    return b, a, w


def is_risk_event(ev: dict, cfg: dict) -> bool:
    if ev.get("impact") not in cfg["impacts"]:
        return False
    if cfg["ignore_title_any"] and _match_any(ev.get("title", ""), cfg["ignore_title_any"]):
        return False
    return event_currency(ev.get("country"), cfg) is not None


def affects(ev: dict, symbol: str, cfg: dict) -> bool:
    cur = event_currency(ev.get("country"), cfg)
    return cur is not None and cur in symbol_currencies(symbol, cfg)


def affected_symbols(ev: dict, symbols: Iterable[str], cfg: dict) -> list[str]:
    return [s for s in symbols if affects(ev, s, cfg)]


@dataclass
class Window:
    event_id: str
    source: str
    title: str
    country: str | None
    impact: str | None
    ts: datetime
    start: datetime
    end: datetime
    warn_at: datetime
    group: str | None = None

    def phase(self, now: datetime) -> str:
        if now < self.warn_at:
            return "scheduled"
        if now < self.start:
            return "imminent"
        if now <= self.end:
            return "active"
        return "past"

    def as_dict(self, now: datetime) -> dict:
        return {"event_id": self.event_id, "source": self.source, "title": self.title, "country": self.country,
                "impact": self.impact, "ts": self.ts, "window_start": self.start, "window_end": self.end,
                "phase": self.phase(now), "minutes_to_event": _mins(self.ts - now),
                "minutes_to_start": max(0, _mins(self.start - now)), "minutes_to_end": max(0, _mins(self.end - now)),
                "group": self.group}


def windows_for_symbol(events: Iterable[dict], symbol: str, cfg: dict) -> list[Window]:
    out, seen = [], set()
    for ev in events:
        if not is_risk_event(ev, cfg) or not affects(ev, symbol, cfg):
            continue
        k = (ev.get("source"), str(ev.get("event_id")))
        if k in seen:
            continue
        seen.add(k)
        ts = parse_ts(ev["ts"])
        b, a, w = widths(ev, symbol, cfg)
        out.append(Window(str(ev.get("event_id")), str(ev.get("source")), ev.get("title", ""), ev.get("country"),
                          ev.get("impact"), ts, ts - timedelta(minutes=b), ts + timedelta(minutes=a), ts - timedelta(minutes=w),
                          (ev.get("extra") or {}).get("group")))
    return sorted(out, key=lambda w: (w.start, w.ts))


def risk_state(events: Iterable[dict], symbol: str, now: datetime, cfg: dict, horizon_h: float = 24) -> dict:
    """Trang thai rui ro cua 1 symbol tai `now`.

    state: active (dang trong cua so; `minutes_to_end` = so phut con lai) | imminent (T-warn .. bat dau cua so) | clear.
    `current` = su kien dang tac dong (active + imminent); `upcoming` = cua so bat dau trong `horizon_h` gio toi;
    `next_window` = cua so ke tiep. Cua so cua nhieu su kien trung/noi nhau duoc gop (window_end = muon nhat cua chuoi).
    """
    now = parse_ts(now)
    horizon = now + timedelta(hours=horizon_h)
    wins = windows_for_symbol(events, symbol, cfg)
    cur = [w for w in wins if w.start <= now <= w.end]
    imm = [w for w in wins if w.warn_at <= now < w.start]
    up = [w for w in wins if w.start > now and w.start <= horizon]
    end = max((w.end for w in cur), default=None)
    if end:  # gop chuoi cua so noi nhau
        grown = True
        while grown:
            grown = False
            for w in wins:
                if w.start <= end < w.end:
                    end, grown = w.end, True
    state = "active" if cur else ("imminent" if imm else "clear")
    nxt = up[0] if up else None
    return {
        "symbol": symbol, "now": now, "state": state, "in_window": bool(cur),
        "currencies": sorted(symbol_currencies(symbol, cfg)),
        "window_start": min((w.start for w in cur), default=None) or (min(w.start for w in imm) if imm else None),
        "window_end": end or (max(w.end for w in imm) if imm else None),
        "minutes_to_end": max(0, _mins(end - now)) if end else None,
        "minutes_to_start": max(0, _mins(min(w.start for w in imm) - now)) if imm and not cur else None,
        "current": [w.as_dict(now) for w in cur + [w for w in imm if w not in cur]],
        "upcoming": [w.as_dict(now) for w in up],
        "next_window": ({"start": nxt.start, "minutes_to_start": max(0, _mins(nxt.start - now)), "title": nxt.title}
                        if nxt else None),
    }


def risk_alerts(events: Iterable[dict], now: datetime, cfg: dict, symbols: Iterable[str] | None = None,
                grace_min: float = 10) -> list[dict]:
    """Alert chuyen pha cho moi NHOM su kien (cung group + cung gio): pre (T-warn), enter (bat dau cua so), exit (ket thuc).

    Ham thuan, idempotent: chay moi phut; ben goi dedupe theo `dedupe_key`. `exit` chi phat trong `grace_min` phut sau khi ket thuc
    de khong phat lai su kien cu khi restart. Tra ve list dict {phase, level, title, body, tags, dedupe_key, symbols, ts}.
    """
    now = parse_ts(now)
    syms = list(symbols if symbols is not None else cfg.get("universe", []))
    groups: dict[tuple, dict] = {}
    for ev in events:
        if not is_risk_event(ev, cfg):
            continue
        aff = affected_symbols(ev, syms, cfg)
        ts = parse_ts(ev["ts"])
        # cung nhom ban phat hanh (extra.group) hoac, neu khong co, cung tien te + cung phut -> 1 alert chung
        g = (ev.get("extra") or {}).get("group") or f"{event_currency(ev.get('country'), cfg)}@{ts:%Y%m%dT%H%M}"
        slot = groups.setdefault((g, ts.replace(second=0, microsecond=0)),
                                 {"events": [], "syms": set(), "b": 0, "a": 0, "w": 0, "ts": ts,
                                  "cur": event_currency(ev.get("country"), cfg)})
        slot["events"].append(ev)
        slot["syms"].update(aff)
        for s in (aff or [None]):
            b, a, w = widths(ev, s, cfg)
            slot["b"], slot["a"], slot["w"] = max(slot["b"], b), max(slot["a"], a), max(slot["w"], w)
    out = []
    for (g, _), slot in groups.items():
        ts = slot["ts"]
        start, end, warn = ts - timedelta(minutes=slot["b"]), ts + timedelta(minutes=slot["a"]), ts - timedelta(minutes=slot["w"])
        titles = sorted({e.get("title", "") for e in slot["events"]})
        head = ", ".join(titles[:3]) + ("..." if len(titles) > 3 else "")
        country = slot["events"][0].get("country") or ""
        affected = sorted(slot["syms"])
        tail = f" Anh huong: {', '.join(affected)}." if affected else ""
        key = f"risk:{g}:{ts.strftime('%Y%m%dT%H%M')}"
        if warn <= now < start:
            phase, level = "pre", "warn"
            title = f"Sap vao cua so rui ro tin: {country} {head}"
            body = (f"{head} ({country}) luc {ts:%Y-%m-%d %H:%M} UTC; cua so khong vao lenh bat dau sau "
                    f"{_mins(start - now)} phut (T-{slot['b']}..T+{slot['a']}).{tail}")
        elif start <= now <= end:
            phase, level = "enter", "warn"
            title = f"VAO cua so rui ro tin: {country} {head}"
            body = (f"Tam dung vao lenh/giam co lenh toi {end:%H:%M} UTC (con {_mins(end - now)} phut). "
                    f"{head} ({country}) luc {ts:%H:%M} UTC.{tail}")
        elif end < now <= end + timedelta(minutes=grace_min):
            phase, level = "exit", "info"
            title = f"Het cua so rui ro tin: {country} {head}"
            body = f"Cua so rui ro cua {head} ({country}) da ket thuc luc {end:%H:%M} UTC.{tail}"
        else:
            continue
        out.append({"phase": phase, "level": level, "title": title.replace("  ", " "), "body": body,
                    "tags": ["risk-window", (slot["cur"] or country or "").lower(), phase],
                    "dedupe_key": f"{key}:{phase}", "symbols": affected, "ts": ts})
    return sorted(out, key=lambda a: (a["ts"], a["phase"]))
