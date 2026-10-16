"""Hàm thuần: Event -> danh sách (SQL, args). Không I/O, dễ test.

SQL dùng placeholder $1.. (asyncpg). Mọi câu đều idempotent (ON CONFLICT).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Callable

from tscommon.events import Event

Stmt = tuple[str, tuple[Any, ...]]


class MappingError(ValueError):
    """Payload sai/thiếu trường -> đưa vào dead-letter, không retry."""


class InvalidBar(MappingError):
    """Nến vô lý (OHLC/volume sai quy tắc). `code` dùng làm nhãn metric."""

    def __init__(self, code: str, msg: str):
        super().__init__(f"bar không hợp lệ [{code}]: {msg}")
        self.code = code


def validate_bar(o: float, h: float, l: float, c: float, v: float | None) -> None:
    vals = {"o": o, "h": h, "l": l, "c": c}
    for k, x in vals.items():
        if not math.isfinite(x):
            raise InvalidBar("not_finite", f"{k}={x}")
        if x <= 0:
            raise InvalidBar("non_positive_price", f"{k}={x} phải > 0")
    if v is not None and (not math.isfinite(v) or v < 0):
        raise InvalidBar("bad_volume", f"v={v} phải >= 0")
    if l > min(o, c):
        raise InvalidBar("low_above_body", f"l={l} > min(o={o}, c={c})")
    if h < max(o, c):
        raise InvalidBar("high_below_body", f"h={h} < max(o={o}, c={c})")
    if h < l:
        raise InvalidBar("high_below_low", f"h={h} < l={l}")


def _req(p: dict, *keys: str) -> None:
    missing = [k for k in keys if p.get(k) is None]
    if missing:
        raise MappingError(f"thiếu trường bắt buộc: {','.join(missing)}")


def _dt(v: Any, name: str = "ts") -> datetime:
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise MappingError(f"{name} không phải ISO-8601: {v!r}") from e
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        d = datetime.fromtimestamp(v, tz=timezone.utc)
    else:
        raise MappingError(f"{name} sai kiểu: {v!r}")
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _dt_opt(v: Any, name: str) -> datetime | None:
    return None if v is None else _dt(v, name)


def _f(v: Any, name: str) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError) as e:
        raise MappingError(f"{name} không phải số: {v!r}") from e


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def _json(v: Any) -> str:
    return json.dumps(v, default=str)


def map_bar(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "symbol", "tf", "ts_open", "o", "h", "l", "c", "source")
    o, h, l, c, v = _f(p["o"], "o"), _f(p["h"], "h"), _f(p["l"], "l"), _f(p["c"], "c"), _f(p.get("v"), "v")
    validate_bar(o, h, l, c, v)
    return [(
        "INSERT INTO bars (symbol, tf, ts_open, o, h, l, c, v, source) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
        "ON CONFLICT (symbol, tf, ts_open, source) DO UPDATE SET o=EXCLUDED.o, h=EXCLUDED.h, l=EXCLUDED.l, "
        "c=EXCLUDED.c, v=EXCLUDED.v",
        (p["symbol"], p["tf"], _dt(p["ts_open"], "ts_open"), o, h, l, c, v or 0.0, p["source"]),
    )]


# Luu quote thua: ~160 ma MT5 x tick -> bang quotes phinh. Ma "day du" (QUOTE_STORE_FULL, mac dinh 7 ma canon goc) luu moi thay doi nhu cu;
# ma con lai luu toi da 1 quote / QUOTE_STORE_MIN_S giay / (symbol, nguon) (nen M1 la nguon su that cho lich su; hub realtime khong qua DB).
_QFULL = {x.strip().upper() for x in os.getenv("QUOTE_STORE_FULL", "EURUSD,GBPUSD,USDJPY,XAUUSD,US500,US30,USTEC").split(",") if x.strip()}
_QMIN_S = float(os.getenv("QUOTE_STORE_MIN_S", "1.0"))
_QLAST: dict[tuple[str, str], float] = {}


def _quote_throttled(sym: str, src: str, ts: datetime) -> bool:
    if _QMIN_S <= 0 or sym.upper() in _QFULL:
        return False
    t, k = ts.timestamp(), (sym, src)
    last = _QLAST.get(k)
    if last is not None and 0 <= t - last < _QMIN_S:
        return True
    if len(_QLAST) > 20000:
        _QLAST.clear()
    _QLAST[k] = t
    return False


def map_quote(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "symbol", "ts", "source")
    if _quote_throttled(str(p["symbol"]), str(p["source"]), _dt(p["ts"])):
        return []
    return [(
        "INSERT INTO quotes (symbol, ts, bid, ask, source) VALUES ($1,$2,$3,$4,$5) "
        "ON CONFLICT (symbol, ts, source) DO UPDATE SET bid=EXCLUDED.bid, ask=EXCLUDED.ask",
        (p["symbol"], _dt(p["ts"]), _f(p.get("bid"), "bid"), _f(p.get("ask"), "ask"), p["source"]),
    )]


def _opinions_enabled() -> bool:
    """Ghi bang expert_opinions (migration 017). Chi bat sau khi ap migration: STORAGE_EXPERT_OPINIONS=true."""
    return os.getenv("STORAGE_EXPERT_OPINIONS", "false").strip().lower() in {"1", "true", "yes", "on"}


def _opinion_stmt(p: dict) -> Stmt | None:
    x = p.get("expert")
    if not isinstance(x, dict) or not x.get("expert_id"):
        return None
    return (
        "INSERT INTO expert_opinions (url, expert_id, name, grp, title, stance, stance_score, topics, symbols, credibility, published_at, lang) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) "
        "ON CONFLICT (url) DO UPDATE SET expert_id=EXCLUDED.expert_id, name=EXCLUDED.name, grp=EXCLUDED.grp, title=EXCLUDED.title, "
        "stance=EXCLUDED.stance, stance_score=EXCLUDED.stance_score, topics=EXCLUDED.topics, symbols=EXCLUDED.symbols, credibility=EXCLUDED.credibility",
        (p["url"], x["expert_id"], x.get("author") or x.get("name"), x.get("group"), p["title"], x.get("stance"), _f(x.get("stance_score"), "stance_score"),
         list(x.get("topics") or []), list(p.get("symbols") or []), _f(x.get("credibility"), "credibility"),
         _dt_opt(p.get("published_at"), "published_at"), p.get("lang")),
    )


def map_news(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "url", "title", "source")
    return [(
        "INSERT INTO news_items (url, title, summary, published_at, source, lang, symbols, sentiment, event_id) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
        "ON CONFLICT (url) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, "
        "published_at=EXCLUDED.published_at, lang=EXCLUDED.lang, "
        # Giữ kết quả làm giàu của `nlp` khi collector phát lại cùng url: hợp nhất symbols, không ghi đè sentiment bằng NULL.
        "symbols=ARRAY(SELECT DISTINCT u FROM unnest(news_items.symbols || EXCLUDED.symbols) AS u), "
        "sentiment=COALESCE(EXCLUDED.sentiment, news_items.sentiment), event_id=EXCLUDED.event_id",
        (p["url"], p["title"], p.get("summary"), _dt_opt(p.get("published_at"), "published_at"), p["source"],
         p.get("lang"), list(p.get("symbols") or []), _f(p.get("sentiment"), "sentiment"), ev.id),
    )] + ([o] if _opinions_enabled() and (o := _opinion_stmt(p)) else [])


def _calendar_extra_enabled() -> bool:
    """Ghi cot calendar_events.extra (nhom, nguon forecast/actual, surprise). Chi bat sau khi ap migration 003: STORAGE_CALENDAR_EXTRA=true."""
    return os.getenv("STORAGE_CALENDAR_EXTRA", "false").strip().lower() in {"1", "true", "yes", "on"}


def map_calendar(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "event_id", "title", "ts", "source")
    args = (str(p["event_id"]), p["source"], p.get("country"), p["title"], p.get("impact"), _dt(p["ts"]),
            _s(p.get("forecast")), _s(p.get("previous")), _s(p.get("actual")))
    if _calendar_extra_enabled():
        return [(
            "INSERT INTO calendar_events (event_id, source, country, title, impact, ts, forecast, previous, actual, extra) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb) "
            "ON CONFLICT (event_id, source) DO UPDATE SET country=EXCLUDED.country, title=EXCLUDED.title, "
            "impact=EXCLUDED.impact, ts=EXCLUDED.ts, forecast=COALESCE(EXCLUDED.forecast, calendar_events.forecast), previous=COALESCE(EXCLUDED.previous, calendar_events.previous), "
            "actual=COALESCE(EXCLUDED.actual, calendar_events.actual), extra=EXCLUDED.extra, updated_at=now()",
            args + (_json(p["extra"]) if p.get("extra") else None,),
        )]
    return [(
        "INSERT INTO calendar_events (event_id, source, country, title, impact, ts, forecast, previous, actual) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
        "ON CONFLICT (event_id, source) DO UPDATE SET country=EXCLUDED.country, title=EXCLUDED.title, "
        "impact=EXCLUDED.impact, ts=EXCLUDED.ts, forecast=COALESCE(EXCLUDED.forecast, calendar_events.forecast), previous=COALESCE(EXCLUDED.previous, calendar_events.previous), "
        "actual=COALESCE(EXCLUDED.actual, calendar_events.actual), updated_at=now()",
        args,
    )]


_EXPERT_UPSERT = "INSERT INTO experts (expert_id, source) VALUES ($1,$2) ON CONFLICT (expert_id) DO NOTHING"


def map_expert_profile(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "expert_id", "source")
    return [(
        "INSERT INTO experts (expert_id, source, display_name, url, reputation, tracked) "
        "VALUES ($1,$2,$3,$4,$5::jsonb,$6) "
        "ON CONFLICT (expert_id) DO UPDATE SET source=EXCLUDED.source, display_name=EXCLUDED.display_name, "
        "url=EXCLUDED.url, reputation=EXCLUDED.reputation, tracked=EXCLUDED.tracked",
        (p["expert_id"], p["source"], p.get("display_name"), p.get("url"),
         _json(p.get("reputation") or {}), bool(p.get("tracked", True))),
    )]


def map_expert_signal(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "expert_id", "source", "symbol", "side", "opened_at")
    if p["side"] not in ("buy", "sell", "flat"):
        raise MappingError(f"side không hợp lệ: {p['side']!r}")
    return [
        (_EXPERT_UPSERT, (p["expert_id"], p["source"])),
        (
            "INSERT INTO expert_signals (expert_id, source, symbol, side, opened_at, entry, sl, tp, status, url, raw) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb) "
            "ON CONFLICT (expert_id, source, symbol, opened_at, side) DO UPDATE SET entry=EXCLUDED.entry, "
            "sl=EXCLUDED.sl, tp=EXCLUDED.tp, status=EXCLUDED.status, url=EXCLUDED.url, raw=EXCLUDED.raw, "
            "updated_at=now()",
            (p["expert_id"], p["source"], p["symbol"], p["side"], _dt(p["opened_at"], "opened_at"),
             _f(p.get("entry"), "entry"), _f(p.get("sl"), "sl"), _f(p.get("tp"), "tp"),
             p.get("status") or "open", p.get("url"), _json(p.get("raw"))),
        ),
    ]


def map_expert_position(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "expert_id", "source", "symbol", "as_of")
    return [
        (_EXPERT_UPSERT, (p["expert_id"], p["source"])),
        (
            "INSERT INTO expert_positions (expert_id, source, symbol, as_of, net_volume, avg_price, raw) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb) "
            "ON CONFLICT (expert_id, source, symbol, as_of) DO UPDATE SET net_volume=EXCLUDED.net_volume, "
            "avg_price=EXCLUDED.avg_price, raw=EXCLUDED.raw",
            (p["expert_id"], p["source"], p["symbol"], _dt(p["as_of"], "as_of"),
             _f(p.get("net_volume"), "net_volume"), _f(p.get("avg_price"), "avg_price"), _json(p.get("raw"))),
        ),
    ]


_ORDER_KINDS = ("buy_limit", "sell_limit", "buy_stop", "sell_stop", "other")
MAX_ORDERS = 500


def _currency(v: Any) -> str | None:
    """Mã tiền tệ tài khoản (USD, EUR, JPY...): chữ-số/chữ cái tối đa 8, chuẩn hoá HOA; rỗng/lạ -> None."""
    if v is None:
        return None
    c = str(v).strip().upper()
    return c if 0 < len(c) <= 8 and c.isalnum() else None


def map_account_snapshot(ev: Event) -> list[Stmt]:
    """`account.snapshots` -> account_snapshots (+ currency) và, khi payload có `orders` (danh sách lệnh chờ HIỆN TẠI, có thể rỗng),
    đồng bộ bảng account_orders: upsert từng lệnh (status=open, last_seen_at = ts snapshot) rồi đánh dấu `removed` các lệnh
    của tài khoản còn `open` mà KHÔNG có trong danh sách và có last_seen_at cũ hơn snapshot này (snapshot đến muộn/lệch thứ tự
    không xoá lệnh mới hơn). Không có khoá `orders` (EA/bridge cũ) -> không đụng account_orders."""
    p = ev.payload
    _req(p, "account_id", "platform", "ts")
    ts = _dt(p["ts"])
    stmts: list[Stmt] = [(
        "INSERT INTO account_snapshots (account_id, platform, ts, balance, equity, margin, positions, currency) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8) "
        "ON CONFLICT (account_id, ts) DO UPDATE SET platform=EXCLUDED.platform, balance=EXCLUDED.balance, "
        "equity=EXCLUDED.equity, margin=EXCLUDED.margin, positions=EXCLUDED.positions, "
        "currency=COALESCE(EXCLUDED.currency, account_snapshots.currency)",
        (p["account_id"], p["platform"], ts, _f(p.get("balance"), "balance"),
         _f(p.get("equity"), "equity"), _f(p.get("margin"), "margin"), _json(p.get("positions") or []), _currency(p.get("currency"))),
    )]
    orders = p.get("orders")
    if orders is None:
        return stmts
    if not isinstance(orders, list):
        raise MappingError("orders phải là list")
    if len(orders) > MAX_ORDERS:
        raise MappingError(f"orders quá nhiều ({len(orders)} > {MAX_ORDERS})")
    tickets: list[str] = []
    for o in orders:
        if not isinstance(o, dict):
            raise MappingError("order phải là object")
        tid = o.get("order_id", o.get("ticket"))
        if tid is None or str(tid) == "":
            raise MappingError("order thiếu order_id")
        tid = str(tid)[:40]
        kind = o.get("kind") if o.get("kind") in _ORDER_KINDS else "other"
        vals = {k: _f(o.get(k), k) for k in ("volume", "price", "sl", "tp")}
        if any(v is not None and not math.isfinite(v) for v in vals.values()):
            raise MappingError("order có giá trị không hữu hạn")
        tickets.append(tid)
        stmts.append((
            "INSERT INTO account_orders (account_id, ticket, platform, symbol, broker_symbol, kind, volume, price, sl, tp, magic, comment, "
            "time_setup, status, first_seen_at, last_seen_at, removed_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'open',$14,$14,NULL) "
            "ON CONFLICT (account_id, ticket) DO UPDATE SET platform=EXCLUDED.platform, symbol=EXCLUDED.symbol, broker_symbol=EXCLUDED.broker_symbol, "
            "kind=EXCLUDED.kind, volume=EXCLUDED.volume, price=EXCLUDED.price, sl=EXCLUDED.sl, tp=EXCLUDED.tp, magic=EXCLUDED.magic, "
            "comment=EXCLUDED.comment, time_setup=COALESCE(EXCLUDED.time_setup, account_orders.time_setup), status='open', "
            "last_seen_at=EXCLUDED.last_seen_at, removed_at=NULL "
            "WHERE account_orders.last_seen_at <= EXCLUDED.last_seen_at",
            (p["account_id"], tid, p["platform"], str(o.get("symbol") or "")[:32], str(o.get("broker_symbol") or "")[:48], kind,
             vals["volume"], vals["price"], vals["sl"], vals["tp"], int(o.get("magic") or 0), str(o.get("comment") or "")[:64],
             _dt_opt(o.get("time_setup"), "time_setup"), ts),
        ))
    stmts.append((
        "UPDATE account_orders SET status='removed', removed_at=$3 WHERE account_id=$1 AND status='open' "
        "AND last_seen_at < $3 AND NOT (ticket = ANY($2::text[]))",
        (p["account_id"], tickets, ts),
    ))
    return stmts


_DEAL_SIDES = ("buy", "sell", "balance")


def map_account_deals(ev: Event) -> list[Stmt]:
    """`account.deals` (lich su deal DA DONG tu EA qua mt-bridge) -> bang account_deals, upsert theo (account_id, ticket).
    Idempotent: gui lai cung deal khong tao ban sao. 1 event = 1 lo (toi da 500 deal) -> nhieu cau lenh."""
    p = ev.payload
    _req(p, "account_id", "deals")
    if not isinstance(p["deals"], list):
        raise MappingError("deals phải là list")
    stmts: list[Stmt] = []
    for d in p["deals"]:
        if not isinstance(d, dict):
            raise MappingError("deal phải là object")
        _req(d, "ticket", "side", "time_close")
        if d["side"] not in _DEAL_SIDES:
            raise MappingError(f"side không hợp lệ: {d['side']!r}")
        vals = {k: _f(d.get(k), k) for k in ("volume", "price_open", "price_close", "sl", "tp", "profit", "swap", "commission")}
        for k in ("volume", "profit", "swap", "commission"):
            if vals[k] is None or not math.isfinite(vals[k]):
                raise MappingError(f"{k} không hợp lệ: {d.get(k)!r}")
        tclose = _dt(d["time_close"], "time_close")
        topen = _dt(d.get("time_open") or d["time_close"], "time_open")
        stmts.append((
            "INSERT INTO account_deals (account_id, ticket, position_id, platform, symbol, broker_symbol, side, volume, price_open, price_close, "
            "sl, tp, time_open, time_close, profit, swap, commission, magic, comment, reason, source) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21) "
            "ON CONFLICT (account_id, ticket) DO UPDATE SET position_id=EXCLUDED.position_id, platform=EXCLUDED.platform, symbol=EXCLUDED.symbol, "
            "broker_symbol=EXCLUDED.broker_symbol, side=EXCLUDED.side, volume=EXCLUDED.volume, price_open=EXCLUDED.price_open, "
            "price_close=EXCLUDED.price_close, sl=EXCLUDED.sl, tp=EXCLUDED.tp, time_open=EXCLUDED.time_open, time_close=EXCLUDED.time_close, "
            "profit=EXCLUDED.profit, swap=EXCLUDED.swap, commission=EXCLUDED.commission, magic=EXCLUDED.magic, comment=EXCLUDED.comment, "
            "reason=EXCLUDED.reason, source=EXCLUDED.source",
            (p["account_id"], str(d["ticket"]), str(d.get("position_id") or d["ticket"]), p.get("platform") or d.get("platform") or "mt",
             d.get("symbol") or "", d.get("broker_symbol") or "", d["side"], vals["volume"], vals["price_open"], vals["price_close"],
             vals["sl"], vals["tp"], topen, tclose, vals["profit"], vals["swap"], vals["commission"], int(d.get("magic") or 0),
             str(d.get("comment") or "")[:64], str(d.get("reason") or ""), str(d.get("source") or "mt")),
        ))
    return stmts


def map_alert(ev: Event) -> list[Stmt]:
    p = ev.payload
    _req(p, "level", "title")
    if p["level"] not in ("info", "warn", "crit"):
        raise MappingError(f"level không hợp lệ: {p['level']!r}")
    # Cần migration 001 (cột event_id UNIQUE) để idempotent theo Event.id.
    return [(
        "INSERT INTO alerts (ts, level, title, body, tags, dedupe_key, event_id) VALUES ($1,$2,$3,$4,$5,$6,$7) "
        "ON CONFLICT (event_id) DO NOTHING",
        (_dt(ev.ts), p["level"], p["title"], p.get("body"),
         list(p.get("tags") or []), p.get("dedupe_key"), ev.id),
    )]


def map_alert_delivered(ev: Event) -> list[Stmt]:
    """alert-service báo kết quả gửi. Upsert theo event_id nên không phụ thuộc thứ tự với map_alert."""
    p = ev.payload
    _req(p, "alert_event_id", "delivered", "level", "title")
    if p["level"] not in ("info", "warn", "crit"):
        raise MappingError(f"level không hợp lệ: {p['level']!r}")
    return [(
        "INSERT INTO alerts (ts, level, title, body, tags, dedupe_key, event_id, delivered) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
        "ON CONFLICT (event_id) DO UPDATE SET delivered = alerts.delivered OR EXCLUDED.delivered",
        (_dt(p.get("ts") or ev.ts), p["level"], p["title"], p.get("body"),
         list(p.get("tags") or []), p.get("dedupe_key"), p["alert_event_id"], bool(p["delivered"])),
    )]


# Cột mở rộng cho kết quả `nlp` (migration infra/db/migrations/002_news_enrichment.sql). Mặc định TẮT để không
# lỗi khi chưa áp migration; bật bằng env STORAGE_ENRICH_EXTENDED=true.
def _extended_enabled() -> bool:
    return os.getenv("STORAGE_ENRICH_EXTENDED", "false").strip().lower() in {"1", "true", "yes", "on"}


def map_news_enriched(ev: Event) -> list[Stmt]:
    """`news.enriched` -> làm giàu hàng news_items theo url. Idempotent, KHÔNG phụ thuộc thứ tự với `news.items`:
    nếu hàng chưa tồn tại thì chèn tối thiểu (title/source lấy từ payload) rồi `news.items` upsert sẽ bổ sung phần còn lại.
    Không đổi event_id (giữ id sự kiện news.items gốc)."""
    p = ev.payload
    _req(p, "url", "title", "source", "model_version")
    sent = _f(p.get("sentiment"), "sentiment")
    if sent is not None and not -1.0 <= sent <= 1.0:
        raise MappingError(f"sentiment ngoài [-1,1]: {sent}")
    symbols = list(p.get("symbols") or [])
    base_cols = "url, title, source, sentiment, symbols"
    sets = ("sentiment=EXCLUDED.sentiment, "
            "symbols=ARRAY(SELECT DISTINCT u FROM unnest(news_items.symbols || EXCLUDED.symbols) AS u)")
    args: list[Any] = [p["url"], p["title"], p["source"], sent, symbols]
    if _extended_enabled():
        base_cols += ", lang, sentiment_label, sentiment_conf, topics, importance, nlp_model, enriched_at"
        sets += (", lang=COALESCE(news_items.lang, EXCLUDED.lang), sentiment_label=EXCLUDED.sentiment_label, "
                 "sentiment_conf=EXCLUDED.sentiment_conf, topics=EXCLUDED.topics, importance=EXCLUDED.importance, "
                 "nlp_model=EXCLUDED.nlp_model, enriched_at=EXCLUDED.enriched_at")
        args += [p.get("lang"), p.get("label"), _f(p.get("confidence"), "confidence"),
                 list(p.get("topics") or []), p.get("importance"), p["model_version"], _dt(ev.ts, "ts")]
    ph = ",".join(f"${i}" for i in range(1, len(args) + 1))
    return [(f"INSERT INTO news_items ({base_cols}) VALUES ({ph}) ON CONFLICT (url) DO UPDATE SET {sets}", tuple(args))]


MAPPERS: dict[str, Callable[[Event], list[Stmt]]] = {
    "md.bars": map_bar,
    "md.quotes": map_quote,
    "news.items": map_news,
    "news.enriched": map_news_enriched,
    "calendar.events": map_calendar,
    "expert.profiles": map_expert_profile,
    "expert.signals": map_expert_signal,
    "expert.positions": map_expert_position,
    "account.snapshots": map_account_snapshot,
    "account.deals": map_account_deals,
    "alerts.out": map_alert,
    "alerts.delivery": map_alert_delivered,
}


def map_event(stream: str, ev: Event) -> list[Stmt]:
    try:
        fn = MAPPERS[stream]
    except KeyError as e:
        raise MappingError(f"stream không hỗ trợ: {stream}") from e
    return fn(ev)
