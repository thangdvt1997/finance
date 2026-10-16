"""Pipeline grounded: dữ liệu thật -> ngữ cảnh đánh số -> LLM (chỉ tóm tắt) -> HẬU KIỂM tất định -> bản tin; vi phạm/lỗi -> loại câu hoặc BẢN MẪU không LLM.

Các mục "cần theo dõi" (lịch + cửa sổ rủi ro tin) và "tâm lý chung" do MÃ sinh từ số liệu thật (không để LLM viết). LLM chỉ viết tiêu đề + ý chính."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tscommon import risk_windows as rw
from tscommon.sources import has_source_name, scrub_obj, scrub_sources

from . import __version__
from .config import Settings
from .context import VN_INTL_SYMBOLS, Context, build_context, fnum
from .llm import LLM, parse_json
from .prompt import build_messages, schema
from .source import Source
from .verify import EXTRA_SOURCE_RE, verify_free_text, verify_point

log = logging.getLogger("briefing.pipeline")
DISCLAIMER = "Bản tin do AI tạo từ dữ liệu của hệ thống, chỉ để tham khảo, không phải khuyến nghị đầu tư. Không có lệnh giao dịch nào được tạo hoặc gửi."
EDITIONS = {"morning": "Bản tin sáng", "close": "Bản tin cuối phiên"}
SCOPES = {"vn": "Việt Nam", "intl": "Quốc tế"}


def mood_section(ctx: Context) -> dict | None:
    st = ctx.stats
    if not st:
        return None
    avg = st["avg"]
    label = "nghiêng tích cực" if avg > 0.15 else "nghiêng tiêu cực" if avg < -0.15 else "trung tính"
    txt = (f"Tâm lý tin tức 24 giờ qua {label}: điểm trung bình {fnum(avg, 2, True)} trên {st['n']} tin có điểm "
           f"({st['pos']} tích cực, {st['neg']} tiêu cực, {st['neu']} trung tính).")
    return {"text": txt, "label": label, "avg": avg, "pos": st["pos"], "neg": st["neg"], "neu": st["neu"], "n": st["n"],
            "top": [{"symbol": s, "count": c, "avg": a} for s, c, a in st["top"]], "cites": [st["n_item"]]}


def watch_section(ctx: Context, now: datetime, tzname: str) -> list[dict]:
    """Sự kiện lịch HIGH sắp tới (và vừa diễn ra) + cửa sổ rủi ro tin quanh sự kiện. Tất định, từ calendar_events."""
    tz = ZoneInfo(tzname)
    try:
        cfg = rw.load_config()
    except Exception:  # noqa: BLE001
        cfg = None
    out: list[dict] = []
    for c in ctx.calendar:
        e = c["event"]
        ts = e["ts"]
        if ts < now - timedelta(hours=3) or ts > now + timedelta(hours=36):
            continue
        before = after = None
        if cfg is not None:
            try:
                before, after, _ = rw.widths(e, None, cfg)
            except Exception:  # noqa: BLE001
                pass
        when = ts.astimezone(tz).strftime("%H:%M %d/%m")
        txt = f"{when} — {e.get('country') or ''} {c['title']}".strip()
        det = [f"{k} {e[f]}" for k, f in (("dự báo", "forecast"), ("kỳ trước", "previous"), ("thực tế", "actual")) if e.get(f) not in (None, "")]
        if det:
            txt += " (" + "; ".join(det) + ")"
        win = None
        if before is not None:
            a, b = ts - timedelta(minutes=before), ts + timedelta(minutes=after)
            win = f"{a.astimezone(tz).strftime('%H:%M')}–{b.astimezone(tz).strftime('%H:%M %d/%m')} (giờ VN)"
            txt += f". Cửa sổ rủi ro tin: {win}"
        out.append({"text": txt, "cites": [c["n"]], "ts": ts.astimezone(timezone.utc).isoformat(), "window": win, "status": "đã diễn ra" if ts < now else "sắp tới"})
    return out[:8]


def template_points(ctx: Context, max_points: int) -> list[dict]:
    """Bản mẫu KHÔNG LLM: trích tiêu đề tin quan trọng nhất + số liệu thị trường. Chắc chắn bám dữ liệu."""
    news = [i for i in ctx.items if i.kind == "news"]
    market = [i for i in ctx.items if i.kind == "market"]
    disp = {d["n"]: d for d in ctx.display}
    pts: list[dict] = []
    for i in market[:2]:
        pts.append({"text": i.text.rstrip(".") + ".", "cites": [i.n]})
    for i in news:
        if len(pts) >= max_points:
            break
        m = re.search(r"tâm lý tin: ([^)]+)\)$", i.text)
        pts.append({"text": disp[i.n]["title"].rstrip(".") + (f" (tâm lý tin: {m.group(1)})" if m else "") + ".", "cites": [i.n]})
    return pts[:max_points]


def template_headline(scope: str, edition: str, local: datetime, ctx: Context) -> str:
    return f"{EDITIONS[edition]} {SCOPES[scope]} ngày {local.strftime('%d/%m/%Y')}"


async def generate(cfg: Settings, src: Source, llm: LLM | None, scope: str, edition: str, now: datetime | None = None) -> dict:
    """Sinh 1 bản tin. Không bao giờ ném lỗi do LLM/hậu kiểm (rơi về bản mẫu); lỗi dữ liệu nguồn được ném lên cho caller."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tz = ZoneInfo(cfg.tz)
    local = now.astimezone(tz)
    start = now - timedelta(hours=24)
    news = await src.news(start, now)
    cal = await src.calendar(now - timedelta(hours=12), now + timedelta(hours=36))
    closes = await src.d1_closes(VN_INTL_SYMBOLS) if scope == "intl" else {}
    an = await src.analytics(VN_INTL_SYMBOLS) if scope == "intl" else {}
    vn = await src.vn_indices() if scope == "vn" else []
    ctx = build_context(scope, edition, now, cfg.tz, news, cal, closes, an, vn, cfg.max_news)
    bn = ctx.by_n()

    q: dict = {"n_context": len(ctx.items), "n_news_pool": len([n for n in news]), "blocked_injection": len(ctx.blocked), "dropped": [], "raw_points": 0}
    status, points, headline, llm_info = "fallback", [], None, {}
    err = None
    if cfg.llm_enabled and llm is not None and any(i.kind == "news" for i in ctx.items):
        try:
            res = await llm.complete(build_messages(ctx, local.strftime("%H:%M %d/%m/%Y"), 5, cfg.max_points), schema(cfg.max_points), cfg.llm_max_tokens)
            llm_info = {"latency_ms": res.latency_ms, "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
                        "prompt_tps": res.prompt_tps, "gen_tps": res.gen_tps}
            data = parse_json(res.content)
            if data is None or not isinstance(data.get("points"), list):
                err = "đầu ra LLM không phải JSON đúng schema"
            else:
                seen: set[str] = set()
                for p in data["points"][:20]:
                    q["raw_points"] += 1
                    if not isinstance(p, dict):
                        q["dropped"].append({"reason": "phần tử không phải đối tượng"})
                        continue
                    v = verify_point(str(p.get("text") or ""), p.get("cites") or [], bn)
                    key = re.sub(r"\W+", "", v.text.lower())[:60]
                    if v.ok and key in seen:
                        v.ok, v.reason = False, "trùng ý"
                    if not v.ok:
                        q["dropped"].append({"reason": v.reason, "text": scrub_sources(str(p.get("text") or ""))[:160]})
                        continue
                    seen.add(key)
                    points.append({"text": v.text, "cites": v.cites})
                    if len(points) >= cfg.max_points:
                        break
                hv = verify_free_text(str(data.get("headline") or ""), ctx.numbers())
                if hv.ok:
                    headline = hv.text
                else:
                    q["dropped"].append({"reason": "tiêu đề: " + hv.reason, "text": scrub_sources(str(data.get("headline") or ""))[:120]})
        except Exception as e:  # noqa: BLE001  (LLM tắt/quá hạn/lỗi mạng -> bản mẫu)
            err = f"LLM lỗi: {type(e).__name__}: {str(e)[:120]}"
            log.warning(err)
    elif not cfg.llm_enabled:
        err = "LLM tắt (BRIEFING_LLM_ENABLED=false)"
    else:
        err = "không có tin để tóm tắt"
    if len(points) >= cfg.min_points:
        status = "llm"
    else:
        if not err:
            err = f"chỉ {len(points)} ý qua hậu kiểm (< {cfg.min_points})"
        q["fallback_reason"] = err
        points = template_points(ctx, cfg.max_points)
        headline = None
    if err and status == "llm":
        q["note"] = err
    if not headline:
        headline = template_headline(scope, edition, local, ctx)
    q["n_points"] = len(points)

    def assemble(points, headline, status):
        body = scrub_obj({"headline": headline, "points": points, "watch": watch_section(ctx, now, cfg.tz), "mood": mood_section(ctx), "disclaimer": DISCLAIMER})
        return {
            "id": str(uuid.uuid4()), "edition": edition, "scope": scope, "for_date": local.date(), "generated_at": now, "window_start": ctx.window_start, "window_end": now,
            "status": status, "model": cfg.llm_model if status == "llm" else "template", "runtime": "llama.cpp" if status == "llm" else "none",
            "latency_ms": llm_info.get("latency_ms"), "prompt_tokens": llm_info.get("prompt_tokens"), "completion_tokens": llm_info.get("completion_tokens"),
            "title": f"{EDITIONS[edition]} {SCOPES[scope]} — {local.strftime('%d/%m/%Y')}", "headline": headline, "body": body,
            "context": {"items": ctx.display, "stats": {k: v for k, v in ctx.stats.items() if k != "top"} if ctx.stats else None},
            "quality": {**q, "llm": llm_info, "version": __version__, "context_numbers": len(ctx.numbers())},
            "disclaimer": DISCLAIMER,
        }

    brief = assemble(points, headline, status)
    if leaks_source(brief) and status == "llm":  # chốt chặn cuối: không bao giờ lưu bản có tên nguồn
        q["leak_guard"] = "bản LLM chứa tên nguồn -> dùng bản mẫu"
        brief = assemble(template_points(ctx, cfg.max_points), template_headline(scope, edition, local, ctx), "fallback")
    if leaks_source(brief):
        raise RuntimeError("bản tin chứa tên nguồn, từ chối lưu")
    return brief


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _strings(v)


def leaks_source(brief: dict) -> bool:
    """Chốt chặn cuối: có tên nguồn trong bất kỳ chuỗi hiển thị nào (title/headline/body/tiêu đề mục trích dẫn) không. Kiểm từng chuỗi (không gộp JSON)."""
    parts = [brief["title"], brief["headline"], brief["body"], [d["title"] for d in brief["context"]["items"]]]
    return any(has_source_name(x) or bool(EXTRA_SOURCE_RE.search(x)) for x in _strings(parts))


def to_text(brief: dict, max_points: int = 3) -> str:
    """Văn bản ngắn cho thông báo ntfy (không tên nguồn, không số trích dẫn)."""
    b = brief["body"]
    lines = [b["headline"]] + [f"• {p['text']}" for p in b["points"][:max_points]]
    if b.get("mood"):
        lines.append(b["mood"]["text"])
    return scrub_sources("\n".join(lines))
