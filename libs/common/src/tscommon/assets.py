"""Registry loai tai san: symbol chuan hoa -> class / ten / nhom / tien te bao gia / phien / so le.

Nguon: `assets.yaml` (dong goi cung thu vien; ghi de bang env ASSETS_CONFIG). Dung chung cho api-gateway (`/v1/symbols`),
analytics, UI. Khong phu thuoc mang/DB. Xem docs/CONTRACTS.md muc "Loai tai san".
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

CLASSES = ("forex", "crypto", "metal", "commodity", "index", "etf", "stock_us", "stock_vn", "bond")
OTHER = "other"


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    cls: str
    name: str
    name_en: str
    group: str | None
    quote_currency: str | None
    session: str
    precision: int
    registered: bool = True

    def as_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("cls")
        return d


@lru_cache(maxsize=1)
def _load() -> dict:
    path = os.getenv("ASSETS_CONFIG", "").strip()
    text = Path(path).read_text(encoding="utf-8") if path and Path(path).is_file() else \
        resources.files("tscommon").joinpath("assets.yaml").read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    reg: dict[str, tuple[str, dict]] = {}
    gen = {}
    if not path:   # danh muc MT5 sinh tu dong (infra/ops/gen_assets_mt5.py): nap TRUOC -> muc viet tay trong assets.yaml thang
        try:
            gen = (yaml.safe_load(resources.files("tscommon").joinpath("assets_mt5.yaml").read_text(encoding="utf-8")) or {}).get("symbols") or {}
        except (FileNotFoundError, OSError, yaml.YAMLError):
            gen = {}
    for src in (gen, raw.get("symbols") or {}):
        for cls, items in src.items():
            for it in items or []:
                reg[str(it["s"]).upper()] = (cls, it)
    return {"sessions": raw.get("sessions") or {}, "classes": raw.get("classes") or {},
            "patterns": raw.get("patterns") or [], "reg": reg}


def reload() -> None:
    _load.cache_clear()


def _strip(symbol: str) -> str:
    return symbol.split(":", 1)[1] if ":" in symbol else symbol


def _fx_precision(symbol: str) -> int:
    return 3 if symbol.endswith("JPY") else 5


def classify(symbol: str) -> str:
    """Class cua symbol (mot trong CLASSES hoac 'other')."""
    s = symbol.strip().upper()
    cfg = _load()
    hit = cfg["reg"].get(s)
    if hit:
        return hit[0]
    for p in cfg["patterns"]:
        if ("match" in p and fnmatch.fnmatchcase(s, str(p["match"]).upper())) or \
                ("regex" in p and re.fullmatch(p["regex"], s)):
            return p["class"]
    return OTHER


def asset_info(symbol: str) -> AssetInfo:
    s = symbol.strip().upper()
    cfg = _load()
    cls_default = lambda c: cfg["classes"].get(c, {})  # noqa: E731
    hit = cfg["reg"].get(s)
    if hit:
        cls, it = hit
        d = cls_default(cls)
        quote = it.get("quote", d.get("quote"))
        if cls == "forex" and "quote" not in it and len(s) == 6:
            quote = s[3:]
        prec = it.get("precision", _fx_precision(s) if cls == "forex" else d.get("precision", 4))
        return AssetInfo(s, cls, it.get("name") or _strip(s), it.get("name_en") or it.get("name") or _strip(s),
                         it.get("group"), quote, it.get("session", d.get("session", "eod_daily")), int(prec))
    cls = classify(s)
    d = cls_default(cls)
    tick = _strip(s)
    quote = d.get("quote")
    prec = d.get("precision", 4)
    if cls == "forex":
        quote, prec = s[3:], _fx_precision(s)
        tick = f"{s[:3]}/{s[3:]}"
    elif cls == "crypto":
        for q in ("USDT", "USDC", "USD"):
            if tick.endswith(q) and len(tick) > len(q):
                tick, quote = f"{tick[:-len(q)]}/{q}", q
                break
    return AssetInfo(s, cls, tick, tick, None, quote, d.get("session", "eod_daily"), int(prec), registered=False)


def class_infos() -> list[dict]:
    """Danh sach loai (theo thu tu hien thi): [{class, name, name_en, order, session, precision, quote_currency}]."""
    out = []
    for c, d in _load()["classes"].items():
        out.append({"class": c, "name": d["name"], "name_en": d.get("name_en", d["name"]), "order": int(d.get("order", 99)),
                    "session": d.get("session"), "precision": d.get("precision"), "quote_currency": d.get("quote")})
    return sorted(out, key=lambda x: x["order"])


def session_info(key: str) -> dict:
    return dict(_load()["sessions"].get(key) or {"name": key, "name_en": key, "kind": "eod"})


def registered_symbols(cls: str | None = None) -> list[str]:
    return sorted(s for s, (c, _) in _load()["reg"].items() if cls is None or c == cls)


# ---------------------------------------------------------------- phien giao dich (khong tinh ngay le)
_DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def _nth_sunday(year: int, month: int, n: int) -> datetime:
    d = datetime(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    return d


def _us_offset_hours(utc: datetime) -> int:
    """New York: UTC-4 (EDT) tu CN thu 2 thang 3 02:00 local den CN dau thang 11 02:00 local; con lai UTC-5."""
    y = utc.year
    start = _nth_sunday(y, 3, 2).replace(hour=7)      # 02:00 EST = 07:00 UTC
    end = _nth_sunday(y, 11, 1).replace(hour=6)       # 02:00 EDT = 06:00 UTC
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def _offset(tz: str, utc: datetime) -> timedelta:
    if tz == "us_eastern":
        return timedelta(hours=_us_offset_hours(utc))
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", tz or "+00:00")
    if not m:
        return timedelta(0)
    sign = -1 if m.group(1) == "-" else 1
    return sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))


def _hm(s: str) -> int:
    h, _, m = s.partition(":")
    return int(h) * 60 + int(m or 0)


def session_open(key: str, now: datetime | None = None) -> bool | None:
    """True/False neu xac dinh duoc phien dang mo (theo gio + thu trong tuan, KHONG xet ngay le); None neu khong ap dung (so lieu cuoi ngay)."""
    now = (now or datetime.now(timezone.utc))
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    s = _load()["sessions"].get(key)
    if not s:
        return None
    kind = s.get("kind")
    if kind == "always":
        return True
    if kind == "week":
        od, ot = s["open"].split(); cd, ct = s["close"].split()
        o, c = _DAYS[od] * 1440 + _hm(ot), _DAYS[cd] * 1440 + _hm(ct)
        t = now.weekday() * 1440 + now.hour * 60 + now.minute
        return (o <= t < c) if o < c else (t >= o or t < c)
    if kind == "daily":
        local = now + _offset(str(s.get("tz", "+00:00")), now)
        if local.weekday() not in s.get("days", [0, 1, 2, 3, 4]):
            return False
        t = local.hour * 60 + local.minute
        return any(_hm(w.split("-")[0]) <= t < _hm(w.split("-")[1]) for w in s.get("windows", []))
    return None


def known_class_values() -> tuple[str, ...]:
    return CLASSES


def as_public(info: AssetInfo, now: datetime | None = None) -> dict[str, Any]:
    d = info.as_dict()
    d["session_open"] = session_open(info.session, now)
    return d
