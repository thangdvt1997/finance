"""Trich 'quan diem co huong' bang QUY TAC (khong sinh van ban). Ham thuan, khong I/O.

Nguon -> entity: ten website/feed id KHONG BAO GIO xuat hien trong label/API (chi dung de BAM ra entity_id on dinh va PHAN LOAI).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from .config import MAX_SYMBOLS_PER_ARTICLE, SENT_THRESHOLD, UTC

SALT = "tr-ent-v1"
CB_RE = re.compile(r"^(boe|boj|fed|ecb|snb|boc|rba|rbnz|pboc|bis|riksbank|norges|boc)_", re.I)
PAPER_RE = re.compile(r"^(cafef|vnexpress|vneconomy|vietstock|tuoitre|baochinhphu|nhandan|thanhnien|dantri|bbc|guardian|reuters|ft|wsj|cnbc)", re.I)
VI_RE = re.compile(r"^(cafef|vnexpress|vneconomy|vietstock|tuoitre|baochinhphu|nhandan|thanhnien|dantri)", re.I)
GOV_RE = re.compile(r"^(bls|sec|fred|bea|census)_?", re.I)

GROUP_CB, GROUP_PAPER, GROUP_STREAM, GROUP_EXPERT, GROUP_SIGNAL = "Ngân hàng trung ương", "Báo kinh tế", "Luồng tin", "Chuyên gia", "Nguồn tín hiệu"


def entity_id(ns: str, key: str) -> str:
    return "ent:" + hashlib.sha256(f"{SALT}|{ns}|{key}".encode()).hexdigest()[:8]


EXPERT_PREFIX = "expert:"


def classify_source(src: str, lang_hint: Optional[str] = None, meta: Optional[dict] = None) -> dict:
    """-> {kind, lang, group, label}. Chi dua tren id nguon; ket qua khong chua id.
    Nguon 'expert:<expert_id>' (y kien chuyen gia do expert-collector phat qua news) -> entity la CHINH chuyen gia/to chuc do (nhan = ten hien thi)."""
    if src.startswith(EXPERT_PREFIX):
        m = (meta or {}).get(src[len(EXPERT_PREFIX):]) or {}
        ot = m.get("org_type")
        kind = "central_bank" if ot == "central_bank" else ("media" if ot == "media" else "analyst")
        return {"kind": kind, "lang": "vi" if lang_hint == "vi" else "en", "group": GROUP_EXPERT, "label": (m.get("name") or "").strip() or None}
    if CB_RE.match(src):
        return {"kind": "central_bank", "lang": "en", "group": GROUP_CB}
    lang = "vi" if VI_RE.match(src) else ("vi" if lang_hint == "vi" else "en")
    if PAPER_RE.match(src):
        return {"kind": "media", "lang": lang, "group": GROUP_PAPER}
    if GOV_RE.match(src):
        return {"kind": "other", "lang": lang, "group": GROUP_STREAM}
    return {"kind": "media", "lang": lang, "group": GROUP_STREAM}


def view_ref(ent: str, symbol: str, day: date) -> str:
    return hashlib.sha256(f"v1|{ent}|{symbol}|{day.isoformat()}".encode()).hexdigest()[:32]


def _aware(d: Any) -> Optional[datetime]:
    if not isinstance(d, datetime):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def news_views(rows: Iterable[dict], has_price: Callable[[str], bool], now: datetime, meta: Optional[dict] = None) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        s = r.get("sentiment")
        syms = r.get("symbols") or []
        if s is None or abs(float(s)) < SENT_THRESHOLD or not syms:
            continue
        ing = _aware(r.get("ingested_at"))
        pub = _aware(r.get("published_at"))
        if pub is None or (ing is not None and pub > ing + timedelta(hours=1)) or pub > now:
            pub = ing                                          # published_at khong hop le/tuong lai -> dung thoi diem ta ghi nhan
        if pub is None:
            continue
        obs = max([x for x in (pub, ing, _aware(r.get("enriched_at"))) if x is not None])
        if obs > now:
            continue
        src = r["source"]
        cls = classify_source(src, r.get("lang"), meta)
        eid = entity_id("news", src)
        direction = "bullish" if float(s) > 0 else "bearish"
        seen, k = set(), 0
        for sym in syms:
            if sym in seen or not has_price(sym):
                continue
            seen.add(sym)
            out.append({"entity_id": eid, "kind": cls["kind"], "lang": cls["lang"], "group": cls["group"], "label": cls.get("label"), "symbol": sym, "direction": direction,
                        "published_at": pub, "observed_at": obs, "invalidation": None, "horizon_hint": None, "basis": "news"})
            k += 1
            if k >= MAX_SYMBOLS_PER_ARTICLE:
                break
    return out


def signal_views(rows: Iterable[dict], names: dict[str, str], now: datetime) -> list[dict]:
    out = []
    for r in rows:
        side = (r.get("side") or "").lower()
        if side not in ("buy", "sell"):
            continue
        t = _aware(r.get("opened_at"))
        if t is None or t > now:
            continue
        eid = entity_id("expert", r["expert_id"])
        sl = r.get("sl")
        out.append({"entity_id": eid, "kind": "signal_provider", "lang": "other", "group": GROUP_SIGNAL, "label": (names.get(r["expert_id"]) or "").strip() or None,
                    "symbol": r["symbol"], "direction": "bullish" if side == "buy" else "bearish", "published_at": t, "observed_at": t,
                    "invalidation": float(sl) if sl not in (None, 0) and float(sl) > 0 else None, "horizon_hint": None, "basis": "signal"})
    return out


def _cot_label(sym: str) -> str:
    s = sym.replace("US:", "")
    if len(s) == 6 and s.isalpha():
        if s.endswith("USD") and s != "USDUSD":
            return s[:3]
        if s.startswith("USD"):
            return s[3:]
    return s


def cot_published_at(as_of: datetime) -> datetime:
    """COT: vi the tinh thu Ba (as_of), cong bo thu Sau 15:30 ET ~ 20:30 UTC = as_of(00:00) + 3 ngay + 20:30. KHONG dung as_of lam thoi diem cong bo."""
    a = _aware(as_of)
    return a.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=3, hours=20, minutes=30)


def cot_views(rows: Iterable[dict], now: datetime) -> list[dict]:
    out = []
    for r in rows:
        if (r.get("source") or "").lower() != "cftc":
            continue
        raw = r.get("raw") or {}
        try:
            net = float(raw["noncomm_long"]) - float(raw["noncomm_short"]) if "noncomm_long" in raw and "noncomm_short" in raw else float(r.get("net_volume"))
            pd = int(raw.get("pair_direction", 1)) or 1
        except (TypeError, ValueError):
            continue
        if net == 0:
            continue
        pub = cot_published_at(r["as_of"])
        if pub > now:
            continue
        out.append({"entity_id": entity_id("cot", r["expert_id"]), "kind": "positioning", "lang": "other", "group": None,
                    "label": "Vị thế đầu cơ — " + _cot_label(r["symbol"]), "symbol": r["symbol"],
                    "direction": "bullish" if (net > 0) == (pd > 0) else "bearish", "published_at": pub, "observed_at": pub, "invalidation": None,
                    "horizon_hint": None, "basis": "cot"})
    return out


def merge_daily(cands: Iterable[dict], closed_before: date) -> list[dict]:
    """1 view / entity / symbol / ngay (UTC theo observed_at). Mau thuan trong ngay => bo ngay do. Chi giu ngay DA DONG (< closed_before).
    ref = ham bam cua (entity,symbol,ngay) nen nap lai khong tao ban sao."""
    g: dict[tuple, list[dict]] = {}
    for c in cands:
        d = c["observed_at"].astimezone(UTC).date()
        if d >= closed_before:
            continue
        g.setdefault((c["entity_id"], c["symbol"], d), []).append(c)
    out = []
    for (eid, sym, d), lst in g.items():
        if len({c["direction"] for c in lst}) > 1:
            continue
        first = min(lst, key=lambda c: (c["observed_at"], c["published_at"]))
        v = dict(first)
        v["ref"] = view_ref(eid, sym, d)
        v["view_id"] = "v_" + v["ref"][:16]
        out.append(v)
    out.sort(key=lambda v: (v["observed_at"], v["ref"]))
    return out


def expert_keys(sigs: Iterable[dict], pos: Iterable[dict], news: Iterable[dict] = (), meta: Optional[dict] = None) -> dict[str, set[tuple[str, str]]]:
    """entity_id -> {(expert_id, source)}: anh xa NOI BO (khong lo ra API) de ghi trong so theo khoa ma expert-collector tra cuu."""
    m: dict[str, set[tuple[str, str]]] = {}
    for r in sigs:
        m.setdefault(entity_id("expert", r["expert_id"]), set()).add((r["expert_id"], r.get("source") or ""))
    seen = set()
    for r in news:
        src = r.get("source") or ""
        if src.startswith(EXPERT_PREFIX) and src not in seen:
            seen.add(src)
            ex = src[len(EXPERT_PREFIX):]
            m.setdefault(entity_id("news", src), set()).add((ex, ((meta or {}).get(ex) or {}).get("source") or "opinion_feeds"))
    for r in pos:
        if (r.get("source") or "").lower() == "cftc":
            m.setdefault(entity_id("cot", r["expert_id"]), set()).add((r["expert_id"], "cftc"))
    return m


def weight_keys(entity: str, emap: dict[str, set[tuple[str, str]]]) -> list[str]:
    """Cac khoa trong `tr:weights` cho 1 entity: entity_id + expert_id + source:expert_id (khop expert_collector.trackweights.lookup)."""
    ks = [entity]
    for ex, src in sorted(emap.get(entity, ())):
        ks.append(ex)
        if src:
            ks.append(f"{src}:{ex}")
    return ks


def merge_weight_records(entries: list[tuple[str, dict]]) -> dict[str, dict]:
    """Nhieu entity cung khoa -> chon BAO THU: trong so nho nhat."""
    out: dict[str, dict] = {}
    for k, rec in entries:
        if k not in out or rec["w"] < out[k]["w"]:
            out[k] = rec
    return out
