"""Realtime hub: MỘT consumer Redis Streams dùng chung -> fan-out tới nhiều WebSocket/SSE (docs/REALTIME.md).

Khác `/v1/stream` (legacy, mỗi kết nối một XREAD, giữ nguyên cho tương thích) — `/v1/rt` (WS) và `/v1/rt/sse` (SSE):
- Hub đọc bus MỘT lần (XREAD) bất kể số kết nối; mỗi sự kiện được tuần tự hoá MỘT lần rồi chia sẻ chuỗi cho mọi người đăng ký.
- Topic: q:<SYM> giá | c:<SYM>:<TF> nến đang hình thành | a:<ACC> trạng thái tài khoản | e:<ACC> sự kiện tài khoản (deal, trạng thái EA)
         | n tin quan trọng | sys cảnh báo/trạng thái hệ thống (CHỈ master).
- Topic "latest-state" (q, c, a) được gộp (coalesce) + throttle: kết nối chậm chỉ giữ bản MỚI NHẤT (bỏ tin cũ). Topic "reliable" (e, n, sys) có seq liên tục + ring để resume.
- AN TOÀN: client chỉ đăng ký a:/e: của tài khoản thuộc phiên (Principal do nginx đặt, X-Auth-Secret); sai -> lỗi forbidden đồng nhất (không oracle);
  giới hạn kết nối theo người dùng + toàn cục, topic/kết nối, tốc độ tin nhắn đến; tuổi tối đa kết nối (kết nối lại -> nginx auth_request kiểm phiên); kick theo user.
- Không lộ tên nguồn dữ liệu (scrub_obj khi HIDE_SOURCES) — quote chuẩn không mang trường source.
"""
from __future__ import annotations

import asyncio
from redis.exceptions import TimeoutError as _RedisTimeout
import contextlib
import logging
import os
import re
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

import orjson
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter, Gauge, Histogram
from tscommon.sources import scrub_obj

from .auth import token_ok
from .authz import Principal, principal_from_headers

log = logging.getLogger("gateway.rt")
PROTO = 1


def _env_int(name: str, d: int) -> int:
    try:
        return int(os.getenv(name, d))
    except ValueError:
        return d


def _env_float(name: str, d: float) -> float:
    try:
        return float(os.getenv(name, d))
    except ValueError:
        return d


class RtSettings:
    """Đọc env lúc tạo Hub (test có thể ghi đè thuộc tính)."""

    def __init__(self) -> None:
        self.enabled = os.getenv("RT_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
        self.quote_ms = _env_int("RT_QUOTE_MS", 120)          # throttle tối thiểu giữa 2 bản giá cùng symbol
        self.candle_ms = _env_int("RT_CANDLE_MS", 500)        # throttle nến đang hình thành
        self.account_ms = _env_int("RT_ACCOUNT_MS", 200)
        self.max_conns = _env_int("RT_MAX_CONNS", 2500)
        self.max_conns_user = _env_int("RT_MAX_CONNS_USER", 6)
        self.max_conns_master = _env_int("RT_MAX_CONNS_MASTER", 30)
        self.max_topics = _env_int("RT_MAX_TOPICS", 120)
        self.max_age_s = _env_int("RT_MAX_AGE_S", 1800)       # client: ngắt sau tuổi này -> kết nối lại qua nginx auth_request (phiên hết hạn => 401)
        self.max_age_master_s = _env_int("RT_MAX_AGE_MASTER_S", 3600)
        self.hb_s = _env_float("RT_HB_S", 15.0)
        self.send_timeout_s = _env_float("RT_SEND_TIMEOUT_S", 5.0)
        self.msg_rate = _env_float("RT_MSG_RATE", 20.0)       # tin nhắn đến/giây/kết nối (token bucket)
        self.msg_burst = _env_float("RT_MSG_BURST", 40.0)
        self.max_msg_bytes = _env_int("RT_MAX_MSG_BYTES", 4096)
        self.queue_max = _env_int("RT_QUEUE_MAX", 400)        # tin reliable chờ gửi tối đa/kết nối; tràn -> resync bằng snapshot
        self.ring = _env_int("RT_RING", 256)
        self.stale_s = _env_float("RT_STALE_S", 20.0)         # quote quá tuổi -> stale
        self.silent_s = _env_float("RT_SILENT_S", 90.0)       # symbol im lặng
        self.max_symbols = _env_int("RT_MAX_SYMBOLS", 5000)
        self.prio = [x.strip().lower() for x in os.getenv("RT_SOURCE_PRIORITY", "mt,dukascopy,crypto,twelvedata,oanda,tiingo,alpaca,yahoo").split(",") if x.strip()]
        self.streams = [x.strip() for x in os.getenv("RT_STREAMS", "md.quotes,md.bars,account.snapshots,account.deals,mt.account_status,alerts.out,news.enriched").split(",") if x.strip()]
        self.extra_streams = [x.strip() for x in os.getenv("RT_EXTRA_STREAMS", "").split(",") if x.strip()]   # chỉ cho kiểm thử tải (container tạm)
        self.allowed_origins = {x.strip().lower() for x in os.getenv("RT_ALLOWED_ORIGINS", "").split(",") if x.strip()}
        self.check_origin = os.getenv("RT_CHECK_ORIGIN", "1").lower() not in {"0", "false", "no", "off"}


# ---------------- metric ----------------
LAT_B = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
M_CONN = Gauge("rt_connections", "Kết nối realtime đang mở", ["kind"])
M_CONN_TOTAL = Counter("rt_conn_attempts_total", "Kết nối realtime theo kết quả", ["result"])
M_SUBS = Gauge("rt_subscriptions", "Tổng đăng ký topic đang hiệu lực")
M_TOPICS = Gauge("rt_topics_active", "Số topic có người đăng ký")
M_BUS_EVENTS = Counter("rt_bus_events_total", "Sự kiện hub đọc từ bus", ["stream"])
M_BUS_LAG = Histogram("rt_bus_to_gateway_seconds", "Event.ts (lúc bridge/collector phát) -> hub đọc", ["stream"], buckets=LAT_B)
M_E2E_GW = Histogram("rt_tick_to_gateway_seconds", "Giờ tick nguồn (payload.ts) -> hub nhận (gồm lệch đồng hồ EA)", buckets=LAT_B)
M_TICK_SEND = Histogram("rt_tick_to_send_seconds", "Giờ tick nguồn -> hub đẩy vào hàng đợi từng kết nối (gồm throttle + chu kỳ flush)", buckets=LAT_B)
M_FLUSH = Histogram("rt_flush_seconds", "Thời gian một vòng flush (fan-out)", buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1))
M_SEND = Histogram("rt_send_seconds", "Thời gian ws.send_text một khung", buckets=LAT_B)
M_FRAMES = Counter("rt_frames_sent_total", "Khung gửi tới client")
M_MSGS = Counter("rt_messages_sent_total", "Tin dữ liệu (d/snap) trong khung gửi tới client")
M_BYTES = Counter("rt_bytes_sent_total", "Byte (trước nén) gửi tới client")
M_DROP = Counter("rt_dropped_total", "Tin bị bỏ", ["reason"])    # coalesced | overflow | rate | slow
M_CLOSED = Counter("rt_closed_total", "Kết nối bị server đóng", ["reason"])
M_CLIENT_NET = Histogram("rt_client_net_seconds", "Độ trễ một chiều gateway->trình duyệt do client báo (đã hiệu chỉnh offset)", buckets=LAT_B)
M_CLIENT_RTT = Histogram("rt_client_rtt_seconds", "RTT ping/pong do client báo", buckets=LAT_B)
M_LAST_READ = Gauge("rt_hub_last_read_timestamp", "Epoch lần cuối hub đọc thành công bus")
M_SILENT = Gauge("rt_silent_symbols", "Số symbol im lặng quá RT_SILENT_S")
M_STALE = Gauge("rt_stale_symbols", "Số symbol có quote chuẩn đang stale")
M_SYMBOLS = Gauge("rt_symbols_tracked", "Số symbol hub đang theo dõi")
M_QAGE = Gauge("rt_quote_age_seconds", "Tuổi quote chuẩn theo symbol (chỉ symbol có người đăng ký hoặc im lặng)", ["symbol"])

TOPIC_RE = re.compile(r"^(q:[A-Za-z0-9:._\-]{1,32}|c:[A-Za-z0-9:._\-]{1,32}:(?:M1|M5|M15|H1|H4|D1)|a:[A-Za-z0-9_.:\-]{1,64}|e:[A-Za-z0-9_.:\-]{1,64}|sys|n)$")
TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
UTC_ALIGNED = {"M1", "M5", "M15", "H1"}      # H4/D1 theo giờ máy chủ broker -> không tự tạo nến mới bằng toán học UTC
LOSSY = ("q", "c", "a")                      # latest-state: gộp + throttle
CLOSE_CODE = {"reauth": 4401, "kicked": 4403, "slow": 1013, "rate": 1008, "shutdown": 1001, "bye": 1000}


def _reap(t: asyncio.Task) -> None:
    """done-callback cho task con đã cancel(): đọc exception để asyncio không log "never retrieved" (thay cho await gather)."""
    if not t.cancelled():
        t.exception()


def _dumps(o) -> str:
    return orjson.dumps(o, default=_default).decode()


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError


def _ms(v, default: float | None = None) -> float:
    """ISO-8601/epoch -> epoch ms."""
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).timestamp() * 1000.0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) * (1000.0 if v < 1e11 else 1.0)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.timestamp() * 1000.0
        except ValueError:
            pass
    return default if default is not None else time.time() * 1000.0


def _num(v) -> float | None:
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if f == f and abs(f) != float("inf") else None


# ---------------- quote engine ----------------
class QuoteEngine:
    """Gộp quote nhiều nguồn -> MỘT quote chuẩn/symbol (ưu tiên RT_SOURCE_PRIORITY; nguồn tươi + ưu tiên cao nhất thắng); đánh dấu stale; phát hiện im lặng.
    Tên nguồn không bao giờ ra khỏi engine."""

    def __init__(self, prio: list[str], stale_s: float, silent_s: float, max_symbols: int = 5000):
        self.prio, self.stale_ms, self.silent_ms, self.max_symbols = prio, stale_s * 1000.0, silent_s * 1000.0, max_symbols
        self.by: dict[str, dict[str, list]] = {}      # sym -> src -> [bid, ask, tick_ms, rx_ms]
        self.cur: dict[str, dict] = {}                 # sym -> quote chuẩn {s,b,a,t,q}
        self.silent: set[str] = set()

    def rank(self, src: str) -> int:
        s = src.lower()
        for i, p in enumerate(self.prio):
            if s.startswith(p):
                return i
        return len(self.prio)

    def _pick(self, sym: str, now_ms: float) -> dict | None:
        srcs = self.by.get(sym)
        if not srcs:
            return None
        fresh = [(self.rank(k), -v[3], k) for k, v in srcs.items() if now_ms - v[3] <= self.stale_ms]
        if fresh:
            k, stale = min(fresh)[2], 0
        else:
            k, stale = max(srcs, key=lambda x: srcs[x][3]), 1
        b, a, t, _rx = srcs[k]
        return {"s": sym, "b": b, "a": a, "t": int(t), "q": stale}

    def update(self, sym: str, src: str, bid, ask, tick_ms: float, now_ms: float) -> bool:
        b, a = _num(bid), _num(ask)
        if b is None and a is None:
            return False
        b = a if b is None else b
        a = b if a is None else a
        if sym not in self.by:
            if len(self.by) >= self.max_symbols:
                return False
            self.by[sym] = {}
        d = self.by[sym]
        old = d.get(src)
        if old is not None and tick_ms < old[2] - 1:
            return False      # tick cũ hơn tick đã có của CÙNG nguồn
        d[src] = [b, a, tick_ms, now_ms]
        if len(d) > 8:        # chặn phình: bỏ nguồn cũ nhất
            d.pop(min(d, key=lambda x: d[x][3]), None)
        new = self._pick(sym, now_ms)
        was = self.cur.get(sym)
        self.cur[sym] = new
        # KHÔNG discard khỏi self.silent ở đây: sweep() phải thấy symbol vừa có tick lại để phát 'resumed' (trước đây bị nuốt)
        return was is None or (was["b"], was["a"], was["t"], was["q"]) != (new["b"], new["a"], new["t"], new["q"])

    def sweep(self, now_ms: float) -> tuple[list[str], list[str], list[str]]:
        """-> (symbol đổi stale (cần đẩy lại), mới im lặng, hết im lặng)."""
        changed, new_silent, resumed = [], [], []
        for sym in list(self.cur):
            nq = self._pick(sym, now_ms)
            if nq["q"] != self.cur[sym]["q"]:
                self.cur[sym] = nq
                changed.append(sym)
            last_rx = max(v[3] for v in self.by[sym].values())
            if now_ms - last_rx > self.silent_ms:
                if sym not in self.silent:
                    self.silent.add(sym)
                    new_silent.append(sym)
            elif sym in self.silent:
                self.silent.discard(sym)
                resumed.append(sym)
        return changed, new_silent, resumed

    def age_s(self, sym: str, now_ms: float) -> float | None:
        srcs = self.by.get(sym)
        return (now_ms - max(v[3] for v in srcs.values())) / 1000.0 if srcs else None


# ---------------- topic / kết nối ----------------
class Topic:
    __slots__ = ("name", "kind", "seq", "ring", "subs", "last_sent", "min_s")

    def __init__(self, name: str, ring: int, min_s: float):
        self.name, self.kind = name, name.split(":", 1)[0]
        self.seq = 0
        self.ring: deque = deque(maxlen=ring if self.kind not in LOSSY else 1)
        self.subs: set["Conn"] = set()
        self.last_sent = 0.0
        self.min_s = min_s


class Conn:
    def __init__(self, principal: Principal, kind: str, st: RtSettings):
        self.id = secrets.token_hex(6)
        self.principal, self.kind, self.st = principal, kind, st
        self.uid = principal.user_id or ("svc" if principal.kind == "service" else "?")
        self.topics: set[str] = set()
        self.latest: dict[str, str] = {}          # topic -> tin mới nhất (gộp)
        self.rel: deque[str] = deque()
        self.resync: set[str] = set()
        self.wake = asyncio.Event()
        self.closed = False
        self.reason = ""
        self.t0 = time.monotonic()
        self.tokens = st.msg_burst
        self.tok_at = time.monotonic()
        self.violations = 0
        self.max_age = st.max_age_master_s if principal.is_master else st.max_age_s
        self.pre: list[str] = []                   # tin điều khiển (ok/pong/err) gửi ngay
        self.last_out = time.monotonic()           # lần cuối trả khung (sweep() dùng để đặt hb_due)
        self.hb_due = False                        # sweep() báo: đã im > hb_s -> gửi heartbeat (không dùng timer riêng cho từng kết nối)

    def put_latest(self, topic: str, msg: str) -> None:
        if topic in self.latest:
            M_DROP.labels("coalesced").inc()
        self.latest[topic] = msg
        self.wake.set()

    def put_rel(self, topic: str, msg: str) -> None:
        if topic in self.resync:
            return                                 # đã tràn: sẽ gửi snapshot thay cho mọi tin cũ của topic
        if len(self.rel) >= self.st.queue_max:
            M_DROP.labels("overflow").inc(len(self.rel) + 1)
            self.rel.clear()
            self.resync |= self.topics     # cả topic latest-state: snapshot đầu (nằm trong rel) cũng bị xoá nên phải gửi lại trạng thái hiện tại
        else:
            self.rel.append(msg)
        self.wake.set()

    def close(self, reason: str) -> None:
        if not self.closed:
            self.closed, self.reason = True, reason
        self.wake.set()

    def allow_msg(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.st.msg_burst, self.tokens + (now - self.tok_at) * self.st.msg_rate)
        self.tok_at = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class Hub:
    def __init__(self, st: RtSettings | None = None, redis=None, repo=None, hide_sources: bool = True):
        self.st = st or RtSettings()
        self.redis, self.repo, self.hide = redis, repo, hide_sources
        self.ep = secrets.token_hex(4)
        self.engine = QuoteEngine(self.st.prio, self.st.stale_s, self.st.silent_s, self.st.max_symbols)
        self.topics: dict[str, Topic] = {}
        self.conns: set[Conn] = set()
        self.by_user: dict[str, int] = {}
        self.candles: dict[tuple[str, str], dict] = {}     # (sym, tf) -> {s,f,t,o,h,l,c,v}
        self.candle_rank: dict[tuple[str, str], int] = {}
        self.candle_ts: dict[tuple[str, str], float] = {}
        self.acct: dict[str, dict] = {}                    # account_id -> payload snapshot gần nhất
        self.dirty: set[str] = set()
        self.tasks: list[asyncio.Task] = []
        self.stream_seen: dict[str, float] = {}
        self.started = time.time()

    # ---- vòng đời ----
    async def start(self) -> None:
        self.tasks = [asyncio.create_task(self._consume(), name="rt-consume"), asyncio.create_task(self._flusher(), name="rt-flush"),
                      asyncio.create_task(self._sweeper(), name="rt-sweep")]

    async def stop(self) -> None:
        for c in list(self.conns):
            c.close("shutdown")
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    # ---- tiêu thụ bus (DUY NHẤT một vòng XREAD) ----
    async def _consume(self) -> None:
        names = list(dict.fromkeys([*self.st.streams, *self.st.extra_streams]))
        last = {n: "$" for n in names}
        backoff = 0.5
        while True:
            try:
                res = await self.redis.xread(last, count=500, block=500)
                M_LAST_READ.set(time.time())
                backoff = 0.5
                for st, msgs in res or []:
                    for mid, fields in msgs:
                        last[st] = mid
                        try:
                            ev = orjson.loads(fields["e"])
                        except (KeyError, ValueError, TypeError):
                            continue
                        try:
                            self.handle_event(st, ev)
                        except Exception:  # noqa: BLE001 - một sự kiện hỏng không được làm sập hub
                            log.exception("rt handle_event lỗi stream=%s", st)
                if not res:
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except (TimeoutError, asyncio.TimeoutError, _RedisTimeout):   # hạn đọc XREAD chạm thoáng qua: thử lại ngay, không tính là lỗi
                log.debug("rt XREAD timeout — thử lại")
                await asyncio.sleep(0.05)
            except Exception as e:  # noqa: BLE001
                log.warning("rt XREAD lỗi: %s (thử lại sau %.1fs)", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    def handle_event(self, stream: str, ev: dict, now_ms: float | None = None) -> None:
        now_ms = now_ms or time.time() * 1000.0
        if not isinstance(ev, dict):
            return
        p = ev.get("payload")
        if not isinstance(p, dict):
            return
        lbl = stream if stream in self.st.streams else "extra"
        M_BUS_EVENTS.labels(lbl).inc()
        self.stream_seen[stream] = now_ms
        if ev.get("ts"):
            lag = (now_ms - _ms(ev["ts"], now_ms)) / 1000.0
            if -1 < lag < 3600:
                M_BUS_LAG.labels(lbl).observe(max(0.0, lag))
        if lbl == "extra":                       # stream kiểm thử (RT_EXTRA_STREAMS, không có trong sản xuất): định tuyến theo ev.type, mặc định quote
            kind = ev.get("type")
            if kind == "account_snapshot":
                self._on_account(p)
            elif kind == "account_status":
                self._on_status(p)
            elif kind == "deals":
                self._on_deals(p, ev)
            elif kind == "bar":
                self._on_bar(p, now_ms)
            else:
                self._on_quote(p, ev, now_ms)
        elif stream == "md.quotes":
            self._on_quote(p, ev, now_ms)
        elif stream == "md.bars":
            self._on_bar(p, now_ms)
        elif stream == "account.snapshots":
            self._on_account(p)
        elif stream == "account.deals":
            self._on_deals(p, ev)
        elif stream == "mt.account_status":
            self._on_status(p)
        elif stream == "alerts.out":
            self._pub_rel("sys", {"k": "alert", "level": p.get("level"), "title": p.get("title"), "body": p.get("body"), "tags": p.get("tags")}, scrub=True)
        elif stream == "news.enriched":
            if p.get("importance") in ("med", "high"):
                self._pub_rel("n", {k: p.get(k) for k in ("url", "title", "published_at", "sentiment", "label", "importance", "symbols") if k in p}, scrub=True)

    # ---- xử lý từng loại ----
    def _mark(self, name: str) -> None:
        t = self.topics.get(name)
        if t is not None and t.subs:
            self.dirty.add(name)

    def _on_quote(self, p: dict, ev: dict, now_ms: float) -> None:
        sym = p.get("symbol")
        if not isinstance(sym, str) or not sym or len(sym) > 32:
            return
        tick = _ms(p.get("ts") or ev.get("ts"), now_ms)
        if 0 <= now_ms - tick < 3_600_000:
            M_E2E_GW.observe((now_ms - tick) / 1000.0)
        if not self.engine.update(sym, str(p.get("source") or "?"), p.get("bid"), p.get("ask"), tick, now_ms):
            return
        self._mark(f"q:{sym}")
        q = self.engine.cur[sym]
        for tf in TF_SEC:
            if (sym, tf) in self.candles and self._tick_candle(sym, tf, q["b"], tick):
                self._mark(f"c:{sym}:{tf}")

    def _tick_candle(self, sym: str, tf: str, px: float, tick_ms: float) -> bool:
        c = self.candles[(sym, tf)]
        span = TF_SEC[tf] * 1000
        if c["t"] <= tick_ms < c["t"] + span:
            if px > c["h"]:
                c["h"] = px
            if px < c["l"]:
                c["l"] = px
            if px == c["c"]:
                return False
            c["c"] = px
            return True
        if tick_ms >= c["t"] + span and tf in UTC_ALIGNED:      # nến mới theo toán học UTC; bar chính thức từ md.bars sẽ ghi đè
            t0 = int(tick_ms // span * span)
            self.candles[(sym, tf)] = {"s": sym, "f": tf, "t": t0, "o": px, "h": px, "l": px, "c": px, "v": 0}
            return True
        return False

    def _on_bar(self, p: dict, now_ms: float) -> None:
        sym, tf = p.get("symbol"), p.get("tf")
        if not isinstance(sym, str) or tf not in TF_SEC:
            return
        o, h, lo, c = (_num(p.get(k)) for k in ("o", "h", "l", "c"))
        if None in (o, h, lo, c):
            return
        t = _ms(p.get("ts_open"), 0.0)
        if not t:
            return
        key = (sym, tf)
        rank = self.engine.rank(str(p.get("source") or "?"))
        cur = self.candles.get(key)
        if cur is not None:
            if t < cur["t"]:
                return                                  # nến cũ hơn nến đang hình thành
            if t == cur["t"] and rank > self.candle_rank.get(key, 99) and now_ms - self.candle_ts.get(key, 0) < 30_000:
                return                                  # nguồn ưu tiên thấp không ghi đè nguồn cao vừa cập nhật
        elif len(self.candles) >= self.st.max_symbols * 2:
            return
        new = {"s": sym, "f": tf, "t": int(t), "o": o, "h": h, "l": lo, "c": c, "v": _num(p.get("v")) or 0}
        if cur == new:
            return
        self.candles[key] = new
        self.candle_rank[key] = rank
        self.candle_ts[key] = now_ms
        self._mark(f"c:{sym}:{tf}")

    def _on_account(self, p: dict) -> None:
        aid = p.get("account_id")
        if not isinstance(aid, str) or not aid or len(aid) > 64:
            return
        if aid not in self.acct and len(self.acct) >= 5000:
            return
        self.acct[aid] = p
        self._mark(f"a:{aid}")

    def _on_deals(self, p: dict, ev: dict) -> None:
        aid = p.get("account_id")
        if isinstance(aid, str) and aid:
            self._pub_rel(f"e:{aid}", {"k": "deals", "deals": p.get("deals") or [], "ts": ev.get("ts")}, scrub=True, only_if_subs=True)

    def _on_status(self, p: dict) -> None:
        aid = p.get("account_id")
        d = {"k": "status", **{k: p.get(k) for k in ("account_id", "status", "reason", "pending", "ts", "last_seen_at", "latency_ms")}}
        if isinstance(aid, str) and aid:
            self._pub_rel(f"e:{aid}", d, scrub=True, only_if_subs=True)
        self._pub_rel("sys", {**d, "k": "ea_status"}, scrub=True)

    def _pub_rel(self, name: str, d: dict, scrub: bool = False, only_if_subs: bool = False) -> None:
        t = self.topics.get(name)
        if t is None and only_if_subs:
            return
        if t is None:
            t = self.topics[name] = Topic(name, self.st.ring, 0.0)
        if scrub and self.hide:
            d = scrub_obj(d)
        t.seq += 1
        msg = _dumps({"t": "d", "k": name, "q": t.seq, "d": d})
        t.ring.append((t.seq, msg))
        for c in t.subs:
            c.put_rel(name, msg)

    # ---- trạng thái -> payload ----
    def _state(self, name: str) -> dict | None:
        kind, _, rest = name.partition(":")
        if kind == "q":
            return self.engine.cur.get(rest)
        if kind == "c":
            sym, _, tf = rest.rpartition(":")
            return self.candles.get((sym, tf))
        if kind == "a":
            p = self.acct.get(rest)
            if p is None:
                return None
            return scrub_obj(p) if self.hide else p
        return None

    async def _fallback_state(self, name: str) -> dict | None:
        """Hub mới khởi động chưa thấy sự kiện: lấy bản gần nhất từ DB (một lần cho mỗi lần đăng ký)."""
        if self.repo is None:
            return None
        kind, _, rest = name.partition(":")
        try:
            if kind == "q":
                rows = await asyncio.wait_for(self.repo.quotes_latest([rest], 1), 2.0)
                if rows:
                    r = rows[0]
                    t = _ms(r["ts"])
                    return {"s": rest, "b": float(r["bid"]), "a": float(r["ask"]), "t": int(t), "q": 1 if time.time() * 1000 - t > self.st.stale_s * 1000 else 0}
            elif kind == "c":
                sym, _, tf = rest.rpartition(":")
                rows = await asyncio.wait_for(self.repo.bars(sym, tf, None, None, "desc", 1, 0), 2.0)
                if rows:
                    r = rows[0]
                    return {"s": sym, "f": tf, "t": int(_ms(r["ts_open"])), "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r.get("v") or 0)}
            elif kind == "a":
                rows = await asyncio.wait_for(self.repo.accounts_latest(), 3.0)
                for r in rows or []:
                    if r.get("account_id") == rest:
                        d = orjson.loads(orjson.dumps(dict(r), default=_default))
                        return scrub_obj(d) if self.hide else d
        except Exception:  # noqa: BLE001
            log.debug("rt fallback %s lỗi", name, exc_info=True)
        return None

    # ---- đăng ký ----
    def _topic(self, name: str) -> Topic:
        t = self.topics.get(name)
        if t is None:
            k = name.split(":", 1)[0]
            min_s = {"q": self.st.quote_ms, "c": self.st.candle_ms, "a": self.st.account_ms}.get(k, 0) / 1000.0
            t = self.topics[name] = Topic(name, self.st.ring, min_s)
        return t

    @staticmethod
    def authorize(p: Principal, name: str) -> bool:
        kind, _, rest = name.partition(":")
        if kind in ("a", "e"):
            return p.can(rest)
        if name == "sys":
            return p.is_master
        return True

    async def subscribe(self, conn: Conn, names: list, resume: dict | None = None, ep: str | None = None) -> tuple[list[str], list[list[str]]]:
        ok, errs = [], []
        resume = resume if isinstance(resume, dict) else {}
        for name in names[:50]:
            if not isinstance(name, str) or not TOPIC_RE.match(name):
                errs.append([str(name)[:40], "bad_topic"])
                continue
            if not self.authorize(conn.principal, name):
                errs.append([name, "forbidden"])           # đồng nhất cho "không tồn tại" và "của người khác"
                continue
            if name in conn.topics:
                ok.append(name)
                continue
            if len(conn.topics) >= self.st.max_topics:
                errs.append([name, "too_many_topics"])
                continue
            t = self._topic(name)
            conn.topics.add(name)
            t.subs.add(conn)
            M_SUBS.inc()
            ok.append(name)
            await self._send_initial(conn, t, resume.get(name) if ep == self.ep else None)
        M_TOPICS.set(sum(1 for x in self.topics.values() if x.subs))
        return ok, errs

    async def _send_initial(self, conn: Conn, t: Topic, last_seq) -> None:
        name = t.name
        if t.kind in LOSSY:
            d = self._state(name)
            if d is None:
                d = await self._fallback_state(name)
            conn.put_rel(name, _dumps({"t": "snap", "k": name, "q": t.seq, "ep": self.ep, "d": d}))
            return
        # reliable: resume nếu ring còn liên tục, ngược lại snapshot "reset"
        if isinstance(last_seq, int) and not isinstance(last_seq, bool) and 0 <= last_seq <= t.seq:
            if last_seq == t.seq:
                conn.put_rel(name, _dumps({"t": "snap", "k": name, "q": t.seq, "ep": self.ep, "d": None, "resumed": True}))
                return
            if t.ring and t.ring[0][0] <= last_seq + 1:
                for s, m in t.ring:
                    if s > last_seq:
                        conn.put_rel(name, m)
                return
        conn.put_rel(name, _dumps({"t": "snap", "k": name, "q": t.seq, "ep": self.ep, "d": self._sys_state() if name == "sys" else None, "reset": True}))

    def _sys_state(self) -> dict:
        return {"conns": len(self.conns), "symbols": len(self.engine.cur), "silent": len(self.engine.silent), "up_s": int(time.time() - self.started)}

    def unsubscribe(self, conn: Conn, names: list) -> list[str]:
        out = []
        for name in names[:50]:
            if isinstance(name, str) and name in conn.topics:
                conn.topics.discard(name)
                conn.latest.pop(name, None)
                t = self.topics.get(name)
                if t is not None:
                    t.subs.discard(conn)
                    M_SUBS.dec()
                    self._gc(t)
                out.append(name)
        return out

    def _gc(self, t: Topic) -> None:
        if not t.subs and t.kind in LOSSY:
            self.topics.pop(t.name, None)
            self.dirty.discard(t.name)

    # ---- kết nối ----
    def admit(self, p: Principal, kind: str) -> tuple[Conn | None, str]:
        if len(self.conns) >= self.st.max_conns:
            return None, "capacity"
        uid = p.user_id or ("svc" if p.kind == "service" else "?")
        lim = self.st.max_conns_master if p.is_master else self.st.max_conns_user
        if self.by_user.get(uid, 0) >= lim:
            return None, "user_limit"
        c = Conn(p, kind, self.st)
        self.conns.add(c)
        self.by_user[uid] = self.by_user.get(uid, 0) + 1
        M_CONN.labels(kind).inc()
        return c, ""

    def drop(self, conn: Conn) -> None:
        if conn not in self.conns:
            return
        self.conns.discard(conn)
        n = self.by_user.get(conn.uid, 1) - 1
        if n <= 0:
            self.by_user.pop(conn.uid, None)
        else:
            self.by_user[conn.uid] = n
        M_CONN.labels(conn.kind).dec()
        for name in list(conn.topics):
            t = self.topics.get(name)
            if t is not None:
                t.subs.discard(conn)
                M_SUBS.dec()
                self._gc(t)
        conn.topics.clear()
        conn.close(conn.reason or "bye")

    def kick(self, user_id: str, reason: str = "kicked") -> int:
        n = 0
        for c in list(self.conns):
            if c.uid == user_id:
                c.close(reason)
                n += 1
        return n

    # ---- flush / sweep ----
    async def _flusher(self) -> None:
        while True:
            await asyncio.sleep(0.025)
            try:
                self.flush()
            except Exception:  # noqa: BLE001
                log.exception("rt flush lỗi")

    def flush(self, now: float | None = None) -> int:
        now = now or time.monotonic()
        if not self.dirty:
            return 0
        t0 = time.perf_counter()
        n = 0
        for name in list(self.dirty):
            t = self.topics.get(name)
            if t is None or not t.subs:
                self.dirty.discard(name)
                continue
            if now - t.last_sent < t.min_s:
                continue
            d = self._state(name)
            self.dirty.discard(name)
            if d is None:
                continue
            t.last_sent = now
            t.seq += 1
            msg = _dumps({"t": "d", "k": name, "q": t.seq, "d": d})
            if t.kind == "q" and isinstance(d.get("t"), (int, float)):
                lag = time.time() - d["t"] / 1000.0
                if 0 <= lag < 3600:
                    M_TICK_SEND.observe(lag)
            for c in t.subs:
                c.put_latest(name, msg)
            n += 1
        M_FLUSH.observe(time.perf_counter() - t0)
        return n

    async def _sweeper(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                self.sweep()
            except Exception:  # noqa: BLE001
                log.exception("rt sweep lỗi")

    def sweep(self, now_ms: float | None = None) -> None:
        now_ms = now_ms or time.time() * 1000.0
        now = time.monotonic()
        for c in list(self.conns):                            # heartbeat + hết tuổi phiên (thay timer riêng của từng kết nối)
            if c.closed:
                continue
            if now - c.t0 > c.max_age:
                c.close("reauth")
            elif now - c.last_out >= self.st.hb_s and not c.hb_due:
                c.hb_due = True
                c.wake.set()
        changed, new_silent, resumed = self.engine.sweep(now_ms)
        for sym in changed:
            self._mark(f"q:{sym}")
        if new_silent:
            self._pub_rel("sys", {"k": "silent", "syms": new_silent[:200], "n": len(new_silent), "after_s": self.st.silent_s})
        if resumed:
            self._pub_rel("sys", {"k": "resumed", "syms": resumed[:200], "n": len(resumed)})
        M_SILENT.set(len(self.engine.silent))
        M_STALE.set(sum(1 for q in self.engine.cur.values() if q["q"]))
        M_SYMBOLS.set(len(self.engine.cur))
        watch = {n[2:] for n, t in self.topics.items() if t.kind == "q" and t.subs} | self.engine.silent
        for sym in list(watch)[:300]:
            a = self.engine.age_s(sym, now_ms)
            if a is not None:
                M_QAGE.labels(sym).set(a)

    def stats(self) -> dict:
        return {"conns": len(self.conns), "users": len(self.by_user), "topics": sum(1 for t in self.topics.values() if t.subs),
                "subs": sum(len(t.subs) for t in self.topics.values()), "symbols": len(self.engine.cur), "silent": len(self.engine.silent),
                "candles": len(self.candles), "accounts": len(self.acct), "ep": self.ep, "up_s": int(time.time() - self.started)}

    # ---- khung gửi ----
    @staticmethod
    def frame(msgs: list[str]) -> str:
        return '{"t":"b","st":%d,"m":[%s]}' % (time.time() * 1000, ",".join(msgs))

    def hello(self, conn: Conn) -> str:
        return _dumps({"t": "hello", "v": PROTO, "ep": self.ep, "sid": conn.id, "hb": self.st.hb_s, "now": int(time.time() * 1000),
                       "max_age": conn.max_age, "role": "master" if conn.principal.is_master else "client",
                       "limits": {"topics": self.st.max_topics, "rate": self.st.msg_rate, "quote_ms": self.st.quote_ms}})

    async def next_frame(self, conn: Conn) -> str | None:
        """Khung kế tiếp cho kết nối (WS writer và SSE dùng chung). None = kết thúc (xem conn.reason)."""
        while True:
            if conn.pre:
                msgs, conn.pre = conn.pre, []
                conn.last_out = time.monotonic()
                return self.frame(msgs)
            if conn.closed:
                return None
            if time.monotonic() - conn.t0 > conn.max_age:
                conn.close("reauth")
                return None
            if not (conn.latest or conn.rel or conn.resync):
                if conn.hb_due:                                   # heartbeat + hết tuổi do sweep() điều khiển: tránh wait_for/timer cho MỖI khung (nút thắt ở 2000 kết nối)
                    conn.hb_due = False
                    conn.last_out = time.monotonic()
                    return '{"t":"hb","st":%d}' % (time.time() * 1000)
                await conn.wake.wait()
                conn.wake.clear()
                if conn.closed:
                    return None
                await asyncio.sleep(0)                # nhường một vòng loop: flush() là đồng bộ nên mọi topic của cùng lượt đã vào conn.latest -> cùng khung
            msgs: list[str] = []
            if conn.pre:
                msgs.extend(conn.pre)
                conn.pre = []
            if conn.resync:
                rs, conn.resync = conn.resync, set()
                for name in rs:
                    t = self.topics.get(name)
                    if t is not None and name in conn.topics:
                        d = self._state(name) if t.kind in LOSSY else (self._sys_state() if name == "sys" else None)
                        msgs.append(_dumps({"t": "snap", "k": name, "q": t.seq, "ep": self.ep, "d": d, "reset": True}))
            if conn.rel:
                msgs.extend(conn.rel)
                conn.rel.clear()
            if conn.latest:
                msgs.extend(conn.latest.values())
                conn.latest.clear()
            if msgs:
                conn.last_out = time.monotonic()
                return self.frame(msgs)

    @staticmethod
    def note_sent(frame: str) -> None:
        M_FRAMES.inc()
        M_BYTES.inc(len(frame))
        M_MSGS.inc(frame.count('"t":"d"') + frame.count('"t":"snap"'))

    # ---- tin nhắn từ client ----
    async def on_client(self, conn: Conn, raw: str) -> None:
        if len(raw) > self.st.max_msg_bytes:
            conn.violations += 5
            conn.pre.append(_dumps({"t": "err", "c": "too_big"}))
            conn.wake.set()
            return
        if not conn.allow_msg():
            conn.violations += 1
            M_DROP.labels("rate").inc()
            if conn.violations > 200:
                conn.close("rate")
            return
        try:
            m = orjson.loads(raw)
        except ValueError:
            conn.violations += 2
            return
        if not isinstance(m, dict):
            return
        op = m.get("op")
        if op == "ping":
            r = _num(m.get("r"))
            if r is not None and 0 <= r < 60000:
                M_CLIENT_RTT.observe(r / 1000.0)
            conn.pre.append(_dumps({"t": "pong", "c": m.get("t"), "s": int(time.time() * 1000)}))
        elif op == "sub":
            topics = m.get("topics")
            if not isinstance(topics, list):
                return
            ok, errs = await self.subscribe(conn, topics, m.get("resume"), m.get("ep"))
            conn.pre.append(_dumps({"t": "ok", "k": ok, "e": errs}))
        elif op == "unsub":
            if isinstance(m.get("topics"), list):
                conn.pre.append(_dumps({"t": "ok", "u": self.unsubscribe(conn, m["topics"])}))
        elif op == "lat":
            s = m.get("s")
            if isinstance(s, list):
                for v in s[:50]:
                    f = _num(v)
                    if f is not None and 0 <= f < 30000:
                        M_CLIENT_NET.observe(f / 1000.0)
        else:
            conn.violations += 1
        conn.wake.set()


# ---------------- HTTP/WS ----------------
def _origin_ok(headers, allowed: set[str]) -> bool:
    o = headers.get("origin")
    if not o:
        return True
    host = (headers.get("x-forwarded-host") or headers.get("host") or "").lower().split(":")[0]
    oh = (urlparse(o).hostname or "").lower()
    return bool(oh) and (oh == host or oh in allowed or o.lower() in allowed)


def register_realtime(app: FastAPI, settings, hub: Hub | None = None) -> Hub | None:
    """Gắn /v1/rt (WS), /v1/rt/sse, /v1/rt/stats, /v1/rt/kick. Hub chạy theo lifespan của app. RT_ENABLED=0 -> không gắn."""
    st = RtSettings()
    if not st.enabled:
        return None
    hub = hub or Hub(st, hide_sources=settings.hide_sources)
    app.state.rt = hub
    orig = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with orig(_app) as state:
            hub.redis = _app.state.redis
            hub.repo = _app.state.repo
            await hub.start()
            try:
                yield state
            finally:
                await hub.stop()

    app.router.lifespan_context = lifespan

    def _principal_http(headers) -> Principal:
        if not token_ok(headers.get("x-api-key"), settings.api_tokens, settings.auth_disabled):
            raise HTTPException(401, "API key không hợp lệ hoặc thiếu", headers={"WWW-Authenticate": "ApiKey"})
        return principal_from_headers(headers, settings.auth_trust_secret)

    @app.websocket("/v1/rt")
    async def rt_ws(ws: WebSocket, topics: str | None = None):
        try:
            principal = principal_from_headers(ws.headers, settings.auth_trust_secret)
        except HTTPException:
            M_CONN_TOTAL.labels("forbidden").inc()
            await ws.close(code=1008, reason="forbidden")
            return
        if st.check_origin and not _origin_ok(ws.headers, st.allowed_origins):
            M_CONN_TOTAL.labels("bad_origin").inc()
            await ws.close(code=1008, reason="forbidden")
            return
        conn, why = hub.admit(principal, "ws")
        if conn is None:
            M_CONN_TOTAL.labels(why).inc()
            await ws.close(code=1013, reason=why)
            return
        try:
            await ws.accept()
            authed = token_ok(ws.headers.get("x-api-key"), settings.api_tokens, settings.auth_disabled)
            if not authed:
                try:
                    first = orjson.loads(await asyncio.wait_for(ws.receive_text(), 10))
                    authed = first.get("type") == "auth" and token_ok(first.get("api_key"), settings.api_tokens)
                except Exception:  # noqa: BLE001
                    authed = False
            if not authed:
                M_CONN_TOTAL.labels("unauthorized").inc()
                conn.reason = "bye"
                await ws.close(code=1008, reason="unauthorized")
                return
            M_CONN_TOTAL.labels("accepted").inc()
            await ws.send_text(hub.hello(conn))
            init = [x for x in (topics or "").split(",") if x][: st.max_topics]
            if init:
                ok, errs = await hub.subscribe(conn, init)
                conn.pre.append(_dumps({"t": "ok", "k": ok, "e": errs}))

            async def writer():
                while True:
                    fr = await hub.next_frame(conn)
                    if fr is None:
                        return
                    t0 = time.perf_counter()
                    try:
                        await asyncio.wait_for(ws.send_text(fr), st.send_timeout_s)
                    except asyncio.TimeoutError:
                        conn.close("slow")
                        M_DROP.labels("slow").inc()
                        return
                    M_SEND.observe(time.perf_counter() - t0)
                    hub.note_sent(fr)

            async def reader():
                while not conn.closed:
                    await hub.on_client(conn, await ws.receive_text())

            tasks = [asyncio.create_task(writer()), asyncio.create_task(reader())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:                           # không nuốt CancelledError, không await gather (xem /v1/stream); hub.drop ở finally ngoài là đồng bộ
                for t in tasks:
                    t.cancel()
                    t.add_done_callback(_reap)
        finally:
            reason = conn.reason
            hub.drop(conn)                     # giảm bộ đếm trước mọi await khác
            if reason and reason != "bye":
                M_CLOSED.labels(reason).inc()
            with contextlib.suppress(Exception):
                if reason and reason != "bye":
                    await asyncio.wait_for(ws.send_text(_dumps({"t": "bye", "c": reason})), 1.0)
                await ws.close(code=CLOSE_CODE.get(reason, 1000))

    @app.get("/v1/rt/sse", include_in_schema=False)
    async def rt_sse(request: Request, topics: str = Query("", max_length=4000)):
        p = _principal_http(request.headers)
        if st.check_origin and not _origin_ok(request.headers, st.allowed_origins):
            raise HTTPException(403, "Không có quyền truy cập")
        conn, why = hub.admit(p, "sse")
        if conn is None:
            M_CONN_TOTAL.labels(why).inc()
            raise HTTPException(429, "quá nhiều kết nối", headers={"Retry-After": "5"})
        M_CONN_TOTAL.labels("accepted").inc()
        init = [x for x in topics.split(",") if x][: st.max_topics]
        ok, errs = await hub.subscribe(conn, init)
        conn.pre.append(_dumps({"t": "ok", "k": ok, "e": errs}))

        async def gen():
            try:
                yield "retry: 3000\n\n"
                yield f"data: {hub.hello(conn)}\n\n"
                while True:
                    fr = await hub.next_frame(conn)
                    if fr is None:
                        yield f"data: {_dumps({'t': 'bye', 'c': conn.reason or 'bye'})}\n\n"
                        break
                    hub.note_sent(fr)
                    yield f"data: {fr}\n\n"
            finally:
                hub.drop(conn)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/v1/rt/stats", include_in_schema=False)
    async def rt_stats(request: Request):
        if not _principal_http(request.headers).is_master:
            raise HTTPException(403, "Không có quyền truy cập")
        return hub.stats()

    @app.post("/v1/rt/kick", include_in_schema=False)
    async def rt_kick(request: Request):
        if not _principal_http(request.headers).is_master:
            raise HTTPException(403, "Không có quyền truy cập")
        try:
            uid = str((await request.json()).get("user_id", ""))[:64]
        except Exception:  # noqa: BLE001
            return JSONResponse({"detail": "bad request"}, status_code=400)
        return {"kicked": hub.kick(uid) if uid else 0}

    return hub
