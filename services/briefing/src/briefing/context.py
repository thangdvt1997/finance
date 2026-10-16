"""Dựng NGỮ CẢNH có đánh số [n] cho LLM từ dữ liệu thật: tin 24h (đã gắn mã/tâm lý), lịch HIGH, biến động giá D1/chỉ số VN, tâm lý tổng hợp.

Quy tắc: (1) KHÔNG đưa tên nguồn vào ngữ cảnh (chỉ tiêu đề + nội dung + thời gian); (2) tin có dấu hiệu chỉ thị AI bị loại hẳn;
(3) mọi số trong ngữ cảnh do mã tạo (tất định) hoặc trích nguyên từ tiêu đề/nội dung tin; (4) hiển thị cho UI chỉ gồm tiêu đề + liên kết."""
from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from tscommon import assets
from tscommon.sources import scrub_sources

from .sanitize import clean_text, looks_injected
from .verify import Item, number_set

VN_INTL_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "US:SPY", "US:QQQ", "US:USO", "CRYPTO:BTCUSDT", "CRYPTO:ETHUSDT"]
VN_CAL_COUNTRIES = {"VN", "US", "CN"}
IMP = {"high": 3.0, "med": 2.0, "low": 1.0}
TREND_VI = {"up": "tăng", "down": "giảm", "side": "đi ngang"}
TITLE_MAX, SUMMARY_MAX = 200, 260


def fnum(x: float | None, d: int = 2, sign: bool = False) -> str:
    """Số kiểu Việt: dấu phẩy thập phân, KHÔNG dấu nghìn (tránh mơ hồ 1.730)."""
    if x is None:
        return "n/a"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace(".", ",")


def label_of(sent: float | None, lab: str | None) -> str | None:
    if sent is None and not lab:
        return None
    m = {"positive": "tích cực", "negative": "tiêu cực", "neutral": "trung tính"}.get(lab or "")
    if m:
        return m
    if sent is None:
        return None
    return "tích cực" if sent > 0.25 else "tiêu cực" if sent < -0.25 else "trung tính"


def is_vn_news(r: dict) -> bool:
    return (r.get("lang") == "vi") or any(str(s).startswith("VN:") for s in (r.get("symbols") or []))


def _dedupe_key(title: str) -> str:
    t = unicodedata.normalize("NFD", title.lower().replace("đ", "d"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", t)[:9])


def _hhmm(ts: datetime, tz: ZoneInfo) -> str:
    return ts.astimezone(tz).strftime("%H:%M %d/%m")


@dataclass
class Context:
    scope: str
    edition: str
    now: datetime
    window_start: datetime
    items: list[Item] = field(default_factory=list)
    display: list[dict] = field(default_factory=list)        # cho UI/DB: n, kind, title, url, ts, symbols
    blocked: list[dict] = field(default_factory=list)        # tin bị loại vì nghi chỉ thị (không lưu nội dung đầy đủ)
    stats: dict = field(default_factory=dict)                # sentiment tổng hợp (số thật)
    calendar: list[dict] = field(default_factory=list)       # sự kiện HIGH đã định dạng (cho mục 'cần theo dõi')
    nonce: str = field(default_factory=lambda: secrets.token_hex(6))

    def by_n(self) -> dict[int, Item]:
        return {i.n: i for i in self.items}

    def numbers(self) -> set[str]:
        s: set[str] = set()
        for i in self.items:
            s |= number_set(i.text)
        s.add("24")
        return s

    def render(self) -> str:
        """Khối dữ liệu đóng khung bằng delimiter ngẫu nhiên: LLM được dặn mọi thứ trong khung là DỮ LIỆU KHÔNG ĐÁNG TIN."""
        order = [("news", "TIN TỨC (24 giờ qua)"), ("calendar", "LỊCH SỰ KIỆN TÁC ĐỘNG CAO"), ("market", "SỐ LIỆU THỊ TRƯỜNG"), ("sentiment", "TÂM LÝ TIN TỨC TỔNG HỢP")]
        out = [f"<<<DU_LIEU_{self.nonce}>>>"]
        for kind, head in order:
            its = [i for i in self.items if i.kind == kind]
            if its:
                out.append(f"## {head}")
                out += [f"[{i.n}] {i.text}" for i in its]
        out.append(f"<<<HET_DU_LIEU_{self.nonce}>>>")
        return "\n".join(out)


def build_context(scope: str, edition: str, now: datetime, tzname: str, news: list[dict], cal: list[dict], closes: dict, analytics: dict,
                  vn_idx: list[dict], max_news: int = 22) -> Context:
    tz = ZoneInfo(tzname)
    ctx = Context(scope=scope, edition=edition, now=now, window_start=now - timedelta(hours=24))
    n = 0

    def add(kind: str, text: str, title: str, url: str | None = None, ts: datetime | None = None, lang: str = "vi", symbols: tuple = ()) -> int:
        nonlocal n
        n += 1
        ctx.items.append(Item(n, kind, text, lang, tuple(symbols)))
        ctx.display.append({"n": n, "kind": kind, "title": title, "url": url, "ts": ts.astimezone(timezone.utc).isoformat() if ts else None, "symbols": list(symbols)})
        return n

    # ---------- tin ----------
    pool = [r for r in news if (scope == "vn") == is_vn_news(r)]
    clean: list[dict] = []
    for r in pool:
        hit = looks_injected(r.get("title"), r.get("summary"))
        if hit:
            ctx.blocked.append({"reason": "nghi chỉ thị cho AI", "match": hit[:40], "title_len": len(r.get("title") or "")})
            continue
        title = scrub_sources(clean_text(r.get("title"), TITLE_MAX), "")
        if len(title) < 12:
            continue
        summ = scrub_sources(clean_text(r.get("summary"), SUMMARY_MAX), "")
        if summ and _dedupe_key(summ) == _dedupe_key(title):
            summ = ""
        clean.append({**r, "_title": title, "_summary": summ})
    # thống kê tâm lý: trên TOÀN BỘ tin có điểm trong phạm vi (không chỉ top)
    scored = [r for r in pool if r.get("sentiment") is not None]
    labs = [label_of(r.get("sentiment"), r.get("sentiment_label")) for r in scored]
    if scored:
        by_sym: dict[str, list[float]] = {}
        for r in scored:
            for s in r.get("symbols") or []:
                by_sym.setdefault(s, []).append(float(r["sentiment"]))
        top = sorted(by_sym.items(), key=lambda kv: -len(kv[1]))[:4]
        ctx.stats = {"n": len(scored), "avg": round(mean(float(r["sentiment"]) for r in scored), 2), "pos": labs.count("tích cực"), "neg": labs.count("tiêu cực"),
                     "neu": labs.count("trung tính"), "top": [(s, len(v), round(mean(v), 2)) for s, v in top]}

    def score(r: dict) -> float:
        age_h = max(0.0, (now - r["ts"]).total_seconds() / 3600)
        return (IMP.get((r.get("importance") or "low"), 1.0) + abs(float(r.get("sentiment") or 0)) * 0.8 + (0.3 if r.get("symbols") else 0)
                + max(0.0, 1 - age_h / 24) * 0.6)

    seen: set[str] = set()
    for r in sorted(clean, key=score, reverse=True):
        k = _dedupe_key(r["_title"])
        if k in seen:
            continue
        seen.add(k)
        lab = label_of(r.get("sentiment"), r.get("sentiment_label"))
        syms = tuple(str(s) for s in (r.get("symbols") or [])[:4])
        text = f"{r['_title']}." + (f" {r['_summary']}" if r["_summary"] else "") + f" (lúc {_hhmm(r['ts'], tz)}" + (f"; mã: {', '.join(syms)}" if syms else "") \
            + (f"; tâm lý tin: {lab}" if lab else "") + ")"
        add("news", text, r["_title"], r.get("url"), r["ts"], r.get("lang") or "vi", syms)
        if len([d for d in ctx.display if d["kind"] == "news"]) >= max_news:
            break

    # ---------- lịch ----------
    evs = [e for e in cal if (scope == "intl" or e.get("country") in VN_CAL_COUNTRIES)]
    for e in evs[:10]:
        title = scrub_sources(clean_text(e.get("title"), 120), "")
        if looks_injected(title) or len(title) < 4:
            continue
        parts = []
        for lab_, k in (("dự báo", "forecast"), ("kỳ trước", "previous"), ("thực tế", "actual")):
            if e.get(k) not in (None, ""):
                parts.append(f"{lab_} {e[k]}")
        txt = f"Sự kiện tác động cao {e.get('country') or ''}: {title}, lúc {_hhmm(e['ts'], tz)} (giờ VN)" + (f"; {'; '.join(parts)}" if parts else "")
        nn = add("calendar", txt, f"{e.get('country') or ''} {title}".strip(), None, e["ts"])
        ctx.calendar.append({"n": nn, "event": e, "title": title, "text": txt})

    # ---------- số liệu thị trường ----------
    if scope == "vn":
        for r in vn_idx[:5]:
            code = re.sub(r"[^A-Za-z0-9]", "", str(r["code"]))[:12]
            if r.get("close") is None:
                continue
            txt = (f"Chỉ số {code} phiên {r['d'].strftime('%d/%m')}: đóng cửa {fnum(r['close'])} điểm"
                   + (f", thay đổi {fnum(r.get('pct'), 2, True)}%" if r.get("pct") is not None else "")
                   + (f"; {r['advances']} mã tăng, {r['declines']} mã giảm" if r.get("advances") is not None and r.get("declines") is not None else "")
                   + (f"; {r['ceiling_n']} mã trần, {r['floor_n']} mã sàn" if r.get("ceiling_n") is not None and r.get("floor_n") is not None else ""))
            add("market", txt, f"Chỉ số {code} phiên {r['d'].strftime('%d/%m')}", None, None, "vi", (f"VN:{code}",))
    else:
        for s in VN_INTL_SYMBOLS:
            rows = closes.get(s) or []
            if len(rows) < 2:
                continue
            last, prev = rows[0], rows[1]
            if (now - last["ts"]).days > 5 or not prev["c"]:
                continue
            info = assets.asset_info(s)
            prec = int(getattr(info, "precision", 4) or 4)
            pct = (last["c"] / prev["c"] - 1) * 100
            an = analytics.get(s) or {}
            name = getattr(info, "name", None) or s
            if "ETF" in name:   # ETF là giá quỹ, KHÔNG phải điểm chỉ số: nói rõ để LLM không gọi nhầm là "chỉ số"
                name = f"Giá quỹ ETF {s.split(':')[-1]}"
            txt = (f"{name} ({s}) nến D1 ngày {last['ts'].strftime('%d/%m')}: giá gần nhất {fnum(last['c'], prec)}, thay đổi {fnum(pct, 2, True)}% so với nến D1 liền trước"
                   + (f"; xu hướng {TREND_VI.get(an.get('trend'), an.get('trend'))}" if an.get("trend") else "")
                   + (f"; RSI {fnum(an.get('rsi'), 1)}" if an.get("rsi") is not None else ""))
            add("market", txt, f"{name} ({s}) nến D1 {last['ts'].strftime('%d/%m')}", None, last["ts"], "vi", (s,))

    # ---------- tâm lý tổng hợp ----------
    if ctx.stats:
        st = ctx.stats
        top = "; ".join(f"{s} {c} tin, điểm trung bình {fnum(a, 2, True)}" for s, c, a in st["top"])
        txt = (f"Tâm lý tin tức 24 giờ qua: {st['n']} tin có điểm; điểm trung bình {fnum(st['avg'], 2, True)}; {st['pos']} tin tích cực, {st['neg']} tin tiêu cực, "
               f"{st['neu']} tin trung tính" + (f"; nhiều tin nhất: {top}" if top else ""))
        nn = add("sentiment", txt, "Tâm lý tin tức tổng hợp 24 giờ")
        ctx.stats["n_item"] = nn
    return ctx
