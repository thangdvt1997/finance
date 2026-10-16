"""Loader `config/sources.d/*.yaml`: HOP NHAT cac nguon y kien chuyen gia do nhieu nguoi/agent them vao voi danh muc dung san (opinion_catalog.CATALOG).

Schema moi muc (xem config/sources.d/README.md):
  id, name_display, type (rss|atom|youtube|bluesky|json|form4|house_trades|...), url, lang, group, institution_type,
  prior_score (0-1), topics[], symbols_hint[], enabled (mac dinh true), poll_minutes, notes
Quy tac: muc loi -> BO QUA (ghi log + dem `invalid`), KHONG lam sap loader; dedupe theo id va theo url (muc dau tien thang;
muc YAML co `override: true` va trung id voi muc dung san thi GHI DE cac truong cho phep, vd enabled:false de tat 1 nguon dung san).
Chay kiem tra: python -m expert_collector.sources_loader [thu_muc_hoac_file.yaml ...]
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

TYPES = {"rss", "atom", "youtube", "bluesky", "json", "form4", "house_trades", "senate_trades", "sec13d", "podcast", "mastodon", "html_list", "reddit"}
# type -> kind noi bo (dispatcher trong sources/opinion_feeds.py); kind la RSS/Atom khi doc bang feedparser
_KIND = {"rss": "rss", "atom": "rss", "youtube": "rss", "podcast": "rss", "mastodon": "rss", "reddit": "rss", "bluesky": "bsky", "form4": "form4"}
GROUPS_CB = {"cb_speech", "central_bank", "cb"}
_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")
_OVERRIDE_MAP = {"enabled": "enabled", "poll_minutes": "every", "prior_score": "cred", "notes": "bias", "topics": "topics",
                 "symbols_hint": "symbols", "name_display": "name", "keywords_only": "kw"}


class SourceError(ValueError):
    pass


def default_dir() -> Path:
    env = os.getenv("EC_SOURCES_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for p in (Path("/app/services/expert-collector/config/sources.d"), here.parents[2] / "config" / "sources.d"):
        if p.is_dir():
            return p
    return here.parents[2] / "config" / "sources.d"


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate 1 muc YAML -> dict theo schema danh muc noi bo (cung truong voi opinion_catalog). Nem SourceError neu sai."""
    if not isinstance(raw, dict):
        raise SourceError("muc phai la mapping")
    sid = str(raw.get("id") or "").strip().lower()
    if not _ID_RX.match(sid):
        raise SourceError(f"id khong hop le: {raw.get('id')!r} (a-z0-9_- , 2-64 ky tu)")
    typ = str(raw.get("type") or "rss").strip().lower()
    if typ not in TYPES:
        raise SourceError(f"{sid}: type {typ!r} khong ho tro ({', '.join(sorted(TYPES))})")
    url = str(raw.get("url") or "").strip()
    if not url and typ == "bluesky":
        url = str(raw.get("handle") or "").strip().lstrip("@")
    if not url and typ == "youtube" and raw.get("channel_id"):
        url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + str(raw["channel_id"]).strip()
    if not url:
        raise SourceError(f"{sid}: thieu url")
    if typ == "bluesky" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]{2,252}", url):
        raise SourceError(f"{sid}: handle bluesky khong hop le: {url!r}")
    if typ != "bluesky" and typ in {"rss", "atom", "youtube", "podcast", "mastodon", "json", "html_list", "form4", "house_trades", "senate_trades", "sec13d"} and not url.startswith("https://"):
        raise SourceError(f"{sid}: url phai https://")
    name = str(raw.get("name_display") or raw.get("name") or "").strip()
    if not name:
        raise SourceError(f"{sid}: thieu name_display")
    try:
        ps = float(raw.get("prior_score", 0.5))
    except (TypeError, ValueError):
        raise SourceError(f"{sid}: prior_score khong phai so") from None
    if not 0 <= ps <= 1:
        raise SourceError(f"{sid}: prior_score phai trong [0,1]")
    try:
        poll = int(raw.get("poll_minutes", 60))
    except (TypeError, ValueError):
        raise SourceError(f"{sid}: poll_minutes khong phai so nguyen") from None
    poll = max(5, min(poll, 1440))
    group = str(raw.get("group") or "other").strip().lower()
    mode = str(raw.get("mode") or ("cb" if group in GROUPS_CB else "mkt")).lower()
    if mode not in {"cb", "mkt"}:
        raise SourceError(f"{sid}: mode phai cb|mkt")
    topics = [str(x) for x in (raw.get("topics") or [])][:6]
    syms = [str(x).upper() if ":" not in str(x) else str(x) for x in (raw.get("symbols_hint") or [])][:8]
    return {
        "id": sid, "name": name, "group": group, "org_type": str(raw.get("institution_type") or "institution"),
        "kind": _KIND.get(typ, typ), "type": typ, "url": url, "lang": str(raw.get("lang") or "en"),
        "cred": round(ps * 100), "bias": "; ".join(x for x in (str(raw.get("prior_reason") or ""), str(raw.get("notes") or "")) if x), "mode": mode,
        "kw": bool(raw.get("keywords_only", False)), "symbols": syms, "topics": topics, "every": poll * 60,
        "summary_max": int(raw.get("summary_max", 300)), "author": bool(raw.get("author_as_expert", False)),
        "enabled": bool(raw.get("enabled", True)), "override": bool(raw.get("override", False)), "origin": "yaml", "_given": set(raw),
    }


def _read_yaml(path: Path) -> list[Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if isinstance(data, dict):
        data = data.get("sources", [])
    if not isinstance(data, list):
        raise SourceError(f"{path.name}: goc phai la danh sach hoac {{sources: [...]}}")
    return data


def load_yaml_entries(paths: list[Path]) -> tuple[list[dict], list[str]]:
    out, errors = [], []
    for p in paths:
        try:
            items = _read_yaml(p)
        except Exception as e:  # noqa: BLE001 - file hong khong duoc lam sap loader
            errors.append(f"{p.name}: {e}")
            continue
        for i, raw in enumerate(items):
            try:
                e = normalize(raw)
                e["file"] = p.name
                out.append(e)
            except SourceError as ex:
                errors.append(f"{p.name}[{i}]: {ex}")
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{p.name}[{i}]: {ex!r}")
    return out, errors


def merge(builtin: list[dict], extra: list[dict], disabled: set[str] | None = None) -> tuple[list[dict], dict[str, Any]]:
    """Hop nhat: dedupe theo id/url; `override` ghi de truong cho phep; `disabled` (env EC_OPINION_DISABLE) tat theo id."""
    disabled = disabled or set()
    res: list[dict] = []
    by_id: dict[str, dict] = {}
    urls: set[str] = set()
    by_url: dict[str, dict] = {}
    stats = {"builtin": 0, "yaml": 0, "dup_id": 0, "dup_url": 0, "overridden": 0}
    for e in builtin:
        e = {**e, "enabled": e.get("enabled", True), "origin": "builtin"}
        if e["id"] in by_id or e["url"] in urls:
            stats["dup_id"] += 1
            continue
        by_id[e["id"]] = e
        urls.add(e["url"])
        by_url[e["url"]] = e
        res.append(e)
        stats["builtin"] += 1
    for e in extra:
        cur = by_id.get(e["id"])
        if cur is not None:
            if e.get("override"):
                given = e.get("_given", set())
                for raw_k, dst in _OVERRIDE_MAP.items():
                    if raw_k in given:
                        cur[dst] = e[dst]
                stats["overridden"] += 1
            else:
                stats["dup_id"] += 1
            continue
        if e["url"] in urls:
            stats["dup_url"] += 1
            by_id[e["id"]] = by_url[e["url"]]  # bi danh: override theo id nay se ap len muc giu url
            continue
        by_id[e["id"]] = e
        urls.add(e["url"])
        by_url[e["url"]] = e
        res.append(e)
        stats["yaml"] += 1
    for e in res:
        if e["id"] in disabled:
            e["enabled"] = False
    stats["enabled"] = sum(1 for e in res if e.get("enabled", True))
    stats["disabled"] = len(res) - stats["enabled"]
    return res, stats


def load_all(directory: Path | None = None, disabled: set[str] | None = None) -> tuple[list[dict], dict[str, Any], list[str]]:
    """Tra (danh sach nguon da hop nhat, thong ke, loi)."""
    from .opinion_catalog import CATALOG
    d = directory or default_dir()
    files = sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")) if d.is_dir() else []
    extra, errors = load_yaml_entries(files)
    merged, stats = merge(CATALOG, extra, disabled)
    stats["invalid"] = len(errors)
    stats["files"] = len(files)
    for m in errors:
        log.warning("sources.d: bo qua %s", m)
    _set_metrics(merged, stats)
    return merged, stats, errors


def _set_metrics(merged: list[dict], stats: dict[str, Any]) -> None:
    try:
        from prometheus_client import Gauge
        g = _gauge()
        g.labels("enabled").set(stats["enabled"])
        g.labels("disabled").set(stats["disabled"])
        g.labels("invalid").set(stats["invalid"])
        by_group: dict[str, int] = {}
        for e in merged:
            if e.get("enabled", True):
                by_group[e["group"]] = by_group.get(e["group"], 0) + 1
        gg = _group_gauge()
        for k, v in by_group.items():
            gg.labels(k).set(v)
    except Exception:  # noqa: BLE001
        pass


_G: Any = None
_GG: Any = None


def _gauge():
    global _G
    if _G is None:
        from prometheus_client import Gauge
        _G = Gauge("ec_opinion_sources", "so nguon y kien chuyen gia theo trang thai", ["state"])
    return _G


def _group_gauge():
    global _GG
    if _GG is None:
        from prometheus_client import Gauge
        _GG = Gauge("ec_opinion_sources_by_group", "so nguon y kien chuyen gia dang bat theo nhom", ["group"])
    return _GG


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    paths: list[Path] = []
    for a in argv or [str(default_dir())]:
        p = Path(a)
        paths += sorted(p.glob("*.y*ml")) if p.is_dir() else [p]
    extra, errors = load_yaml_entries(paths)
    merged, stats = merge(__import__("expert_collector.opinion_catalog", fromlist=["CATALOG"]).CATALOG, extra)
    print(f"files={len(paths)} yaml_ok={len(extra)} invalid={len(errors)} -> {stats}")
    by_group: dict[str, int] = {}
    for e in merged:
        if e["enabled"]:
            by_group[e["group"]] = by_group.get(e["group"], 0) + 1
    print("theo nhom:", dict(sorted(by_group.items())))
    for m in errors:
        print("LOI:", m)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
