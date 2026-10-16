"""Cache phản hồi cho GET /v1/* (Redis cache-aside + stale-while-revalidate + single-flight + vô hiệu hoá theo sự kiện bus). docs/PERFORMANCE.md.

AN TOÀN DỮ LIỆU (ưu tiên số 1):
- Middleware chạy TRƯỚC dependency `authorize` của router nên TỰ kiểm: X-API-Key hợp lệ + `principal_from_headers` (X-User-Id/X-Role/X-Accounts chỉ được tin khi X-Auth-Secret khớp; giả mạo/thiếu -> bỏ qua cache,
  để app trả 401/403 như cũ). Header người dùng do client gửi KHÔNG BAO GIỜ vào khoá cache (nginx đè trước khi tới đây).
- Khoá = (phạm vi, đường dẫn, query chuẩn hoá). Phạm vi: `m` (master/service), `c` (mọi client; chỉ cho route DÙNG CHUNG), `c.<băm tập tài khoản>` (route theo tài khoản: overview/accounts/equity-history/risk accounts).
  Entry chỉ được GHI sau khi app trả 200 cho đúng phạm vi đó => quyết định phân quyền (CLIENT_ALLOW, kiểm account_id ∈ accounts) đã nằm trong khoá. user_id KHÔNG nằm trong khoá/entry.
- Chỉ cache GET + 200 + JSON; không cache /me, /user/*, /journal/*, /paper/*, /system, /alerts, /data-sources, /reports*.
- Lỗi Redis/giải nén/bất kỳ -> FAIL-OPEN (đi thẳng xuống app). Tắt khẩn cấp: CACHE_ENABLED=0 (+recreate) hoặc SET `cache:ctl:off 1` trên redis-cache (hiệu lực tức thì, kể cả cho request đang bay).
"""
from __future__ import annotations

import asyncio
from redis.exceptions import TimeoutError as _RedisTimeout
import contextlib
import hashlib
import logging
import os
import re
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable
from urllib.parse import parse_qsl

from fastapi import HTTPException
from prometheus_client import Counter, Gauge, Histogram
from starlette.datastructures import Headers

from .auth import token_ok
from .authz import principal_from_headers

try:  # tuỳ chọn (có trong requirements.lock); thiếu -> rơi về json/zlib, vẫn chạy
    import orjson

    def _dumps(o) -> bytes:
        return orjson.dumps(o)

    _loads = orjson.loads
except ImportError:  # pragma: no cover
    import json

    def _dumps(o) -> bytes:
        return json.dumps(o, separators=(",", ":")).encode()

    _loads = json.loads
try:
    import zstandard as _zstd
    _ZC, _ZD = _zstd.ZstdCompressor(level=1), _zstd.ZstdDecompressor()
except ImportError:  # pragma: no cover
    _ZC = _ZD = None

log = logging.getLogger("gateway.cache")

C_REQ = Counter("gateway_cache_requests_total", "Request qua tầng cache gateway", ["policy", "result"])   # result: hit|stale|miss|bypass|error
C_LAT = Histogram("gateway_cache_request_seconds", "Độ trễ phục vụ tại tầng cache (tính cả miss)", ["policy", "result"],
                  buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
C_RLAT = Histogram("gateway_cache_redis_seconds", "Độ trễ lệnh Redis cache", ["op"], buckets=(0.0002, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.1, 0.25))
C_ERR = Counter("gateway_cache_errors_total", "Lỗi tầng cache (fail-open)", ["kind"])
C_INV = Counter("gateway_cache_invalidations_total", "Số lần tăng version vô hiệu hoá theo sự kiện bus", ["domain"])
C_REFRESH = Counter("gateway_cache_refresh_total", "Làm mới nền", ["kind"])   # swr|warm
C_BYTES = Counter("gateway_cache_stored_bytes_total", "Byte đã ghi vào cache (sau nén)")
C_RAW = Counter("gateway_cache_stored_raw_bytes_total", "Byte đã ghi vào cache (trước nén)")
G_DOWN = Gauge("gateway_cache_circuit_open", "1 = Redis cache đang bị bỏ qua (fail-open)")
G_ON = Gauge("gateway_cache_enabled", "1 = cache bật")
G_SHARED = Counter("gateway_cache_singleflight_waits_total", "Request chờ chung 1 lần tính (chống stampede)")

SYM = r"[A-Za-z0-9:._\-]{1,32}"
TF_TTL = {"M1": 5, "M5": 10, "M15": 20, "H1": 60, "H4": 120, "D1": 300}


@dataclass(frozen=True)
class Policy:
    name: str
    rx: re.Pattern
    ttl: Callable[[re.Match, dict], float]
    scope: str = "shared"                                   # shared | account
    vers: Callable[[re.Match, dict], tuple] = lambda m, q: ()
    stale: float | None = None                               # giây còn phục vụ bản cũ trong lúc làm mới nền (mặc định min(2*ttl,120))
    label: str = ""                                          # nhãn route cho gateway_http_request_seconds khi trúng cache


def _P(name, pat, ttl, scope="shared", vers=None, stale=None, label=""):
    return Policy(name, re.compile(pat), ttl if callable(ttl) else (lambda m, q, _t=ttl: _t), scope, vers or (lambda m, q: ()), stale, label or pat)


def _bars_ttl(m, q) -> float:
    tf = q.get("tf", "H1")
    to = q.get("to")
    if to:   # lịch sử đã đóng (nến bất biến): `to` đã lùi xa quá 2 ngày -> giữ lâu
        with contextlib.suppress(ValueError):
            dt = datetime.fromisoformat(to.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - dt).total_seconds() > 2 * 86400:
                return 3600
    return TF_TTL.get(tf, 30)


def _bars_vers(m, q):
    return ("bars:all", f"bars:{q.get('symbol', '')}:{q.get('tf', '')}")


POLICIES: tuple[Policy, ...] = (
    _P("bars", r"^/v1/bars$", _bars_ttl, vers=_bars_vers, label="/v1/bars"),
    _P("quotes", r"^/v1/quotes/latest$", 1.5, stale=2, label="/v1/quotes/latest"),
    _P("symbols", r"^/v1/symbols(/classes)?$", 30, label="/v1/symbols"),
    _P("news", r"^/v1/news$", 20, vers=lambda m, q: ("news",), label="/v1/news"),
    _P("calendar", r"^/v1/calendar$", 30, vers=lambda m, q: ("calendar",), label="/v1/calendar"),
    _P("experts", r"^/v1/(experts|expert-signals|expert-opinions|expert-positions)$", 30, vers=lambda m, q: ("expert",), label="/v1/experts"),
    _P("track", r"^/v1/experts/(leaderboard|consensus|feed|methodology|[A-Za-z0-9_.:\-]{1,96}/track-record)$", 60, label="/v1/experts/track"),
    _P("analytics", rf"^/v1/analytics/(overview|screener|correlation|sessions|symbol/{SYM})$",
       lambda m, q: 60 if m.group(1) in ("correlation", "sessions") else 20, vers=lambda m, q: ("analytics",), label="/v1/analytics"),
    _P("patterns", r"^/v1/patterns(/spec)?$", lambda m, q: 300 if m.group(1) else 10, vers=lambda m, q: ("patterns",), label="/v1/patterns"),
    _P("intel_fast", r"^/v1/intel/(strength|fx|heatmap|movers|stats|pulse)$", 30, label="/v1/intel/fast"),
    _P("intel_slow", r"^/v1/intel/(correlation|correlation/rolling|distribution)$", 120, label="/v1/intel/slow"),
    _P("intel_news", r"^/v1/intel/news(/topics|/related)?$", 20, vers=lambda m, q: ("news",), label="/v1/intel/news"),
    _P("intel_cal", r"^/v1/intel/calendar/(indicators|history)$", 300, vers=lambda m, q: ("calendar",), label="/v1/intel/calendar"),
    _P("intel_cot", r"^/v1/intel/cot$", 3600, label="/v1/intel/cot"),
    _P("vn", r"^/v1/vn/(status|session)$", 10, label="/v1/vn/{rest:path}"),
    _P("vn", r"^/v1/vn/[A-Za-z0-9:/_\-]{1,64}$", 60, label="/v1/vn/{rest:path}"),
    _P("risk_windows", r"^/v1/risk-windows(/status)?$", 30, vers=lambda m, q: ("calendar",), label="/v1/risk-windows"),
    _P("risk_config", r"^/v1/risk/config$", 60, label="/v1/risk/{rest:path}"),
    _P("briefing", r"^/v1/briefing/(latest|list)$", 30, vers=lambda m, q: ("briefing",), label="/v1/briefing/{rest:path}"),
    _P("briefing_item", r"^/v1/briefing/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", 3600, label="/v1/briefing/{rest:path}"),
    # ---- theo tài khoản: khoá THEO (vai trò, tập tài khoản); app tự lọc theo principal
    _P("overview", r"^/v1/overview$", 2, scope="account", stale=2, label="/v1/overview"),
    _P("accounts", r"^/v1/accounts$", 2, scope="account", stale=2, label="/v1/accounts"),
    _P("equity", r"^/v1/equity-history$", 5, scope="account", label="/v1/equity-history"),
    _P("risk_accounts", r"^/v1/risk/accounts(/[A-Za-z0-9_.:\-]{1,64})?$", 5, scope="account", label="/v1/risk/{rest:path}"),
)

# luồng bus -> các khoá version cần tăng khi có sự kiện (payload.symbol/tf cho nến)
STREAM_DOMAINS = {"md.bars": "bars", "news.items": "news", "news.enriched": "news", "calendar.events": "calendar", "analytics.signals": "analytics",
                  "briefing.items": "briefing", "pattern.signals": "patterns", "expert.signals": "expert", "expert.positions": "expert", "expert.profiles": "expert"}

# URL luôn được làm nóng (refresh-ahead) cho master + client; còn lại làm nóng theo "độ nóng" quan sát được
SEEDS = (("/v1/symbols", "", "mc"), ("/v1/symbols/classes", "", "mc"), ("/v1/quotes/latest", "", "mc"), ("/v1/analytics/overview", "", "mc"),
         ("/v1/intel/strength", "", "mc"), ("/v1/intel/fx", "", "mc"), ("/v1/intel/heatmap", "", "mc"), ("/v1/intel/movers", "", "mc"),
         ("/v1/intel/pulse", "", "mc"), ("/v1/analytics/correlation", "tf=D1", "mc"), ("/v1/overview", "", "m"))


def _bool(name: str, d: bool) -> bool:
    v = os.getenv(name)
    return d if v is None else v.strip().lower() not in {"0", "false", "no", "off", ""}


def _blake(s: str, n: int = 12) -> str:
    return hashlib.blake2b(s.encode("utf-8", "replace"), digest_size=n).hexdigest()


class ResponseCache:
    """Trạng thái dùng chung giữa middleware + tác vụ nền. `redis` = client bytes tới redis-cache (user ts_cache); None => cache tắt (inert)."""

    def __init__(self, redis=None, *, enabled: bool = True, max_body: int = 2 * 1024 * 1024, compress_min: int = 1024, ttl_scale: float = 1.0,
                 warm: bool = True, invalidate: bool = True, warm_interval: float = 2.0, hot_window: float = 90.0, hot_max: int = 400,
                 policies: tuple[Policy, ...] = POLICIES):
        self.r = redis
        self.enabled = bool(enabled and redis is not None)
        self.max_body, self.compress_min, self.ttl_scale = max_body, compress_min, ttl_scale
        self.do_warm, self.do_inval, self.warm_interval, self.hot_window, self.hot_max = warm, invalidate, warm_interval, hot_window, hot_max
        self.policies = policies
        self._inflight: dict[str, asyncio.Task] = {}
        self._hot: dict[str, dict] = {}
        self._down_until = 0.0
        self._fails = 0
        self._tasks: list[asyncio.Task] = []
        self._bg_sem = asyncio.Semaphore(6)
        self._later: list[tuple[float, set]] = []
        self.inner = None            # ASGI app bên trong (gán bởi middleware)
        self.settings = None
        self.app_ref = None
        G_ON.set(1 if self.enabled else 0)

    # ---------- cấu hình ----------
    @classmethod
    def from_env(cls) -> "ResponseCache":
        url = os.getenv("CACHE_REDIS_URL", "").strip()
        on = _bool("CACHE_ENABLED", True) and bool(url) and not re.match(r"^redis://[^:@/]+:@", url)   # thiếu mật khẩu (biến compose rỗng) -> tắt
        r = None
        if on:
            import redis.asyncio as aioredis
            tmo = int(os.getenv("CACHE_TIMEOUT_MS", "800")) / 1000
            r = aioredis.from_url(url, decode_responses=False, socket_timeout=tmo, socket_connect_timeout=tmo, health_check_interval=30, max_connections=64)
        return cls(r, enabled=on, max_body=int(os.getenv("CACHE_MAX_BODY", 2 * 1024 * 1024)), ttl_scale=float(os.getenv("CACHE_TTL_SCALE", "1")),
                   warm=_bool("CACHE_WARM", True), invalidate=_bool("CACHE_INVALIDATE", True))

    @property
    def active(self) -> bool:
        return self.enabled and time.monotonic() >= self._down_until

    def match(self, path: str):
        if len(path) > 160:
            return None
        for p in self.policies:
            m = p.rx.match(path)
            if m:
                return p, m
        return None

    # ---------- khoá ----------
    @staticmethod
    def scope_id(principal, pol: Policy) -> str:
        if principal.is_master:
            return "m"
        if pol.scope == "shared":
            # vai trò phụ (support/analyst/auditor) KHÔNG dùng chung khoá của client: middleware cache chạy TRƯỚC `authorize`, nên bản cache của client
            # sẽ lách chính sách staff_path_allowed (vd auditor chỉ được /v1/me). Khoá riêng theo vai trò -> chỉ ghi khi app đã trả 200 cho đúng vai trò đó.
            return "s." + principal.role if getattr(principal, "role", "") else "c"
        return "c." + _blake("\x00".join(sorted(principal.accounts)), 8)

    @staticmethod
    def canon_query(qs: bytes) -> tuple[str, dict]:
        pairs = sorted(parse_qsl(qs.decode("latin-1"), keep_blank_values=True, max_num_fields=32))
        return "&".join(f"{k}={v}" for k, v in pairs), dict(pairs)

    def key_for(self, scope_id: str, path: str, canon: str) -> str:
        return f"cache:r1:{scope_id}:{path}:{_blake(canon)}"

    # ---------- Redis (mọi lỗi => fail-open) ----------
    def _fail(self, kind: str, exc: Exception | None = None) -> None:
        C_ERR.labels(kind).inc()
        self._fails += 1
        if self._fails >= 5:      # 5 lỗi liên tiếp mới mở mạch (timeout đơn lẻ khi event loop bận không được làm sập cache)
            self._down_until = time.monotonic() + 3.0
            G_DOWN.set(1)
            log.warning("cache redis lỗi (%s): %s — bỏ qua cache 3s", kind, type(exc).__name__ if exc else "")

    async def _mget(self, keys: list[str]):
        t0 = time.perf_counter()
        try:
            res = await self.r.mget(keys)
        except Exception as e:  # noqa: BLE001
            self._fail("mget", e)
            return None
        C_RLAT.labels("mget").observe(time.perf_counter() - t0)
        self._fails = 0
        if self._down_until:
            self._down_until = 0.0
            G_DOWN.set(0)
        return res

    async def lookup(self, key: str, vkeys: tuple):
        """-> (flag_off, entry|None, vers_now). entry = (meta, body) chỉ khi version khớp. None = lỗi Redis (đi thẳng app)."""
        res = await self._mget([key, "cache:ctl:off", *[f"cache:ver:{v}" for v in vkeys]])
        if res is None:
            return None
        raw, off, vers = res[0], res[1], [(x.decode() if x else "") for x in res[2:]]
        if off:
            return True, None, vers
        if not raw:
            return False, None, vers
        try:
            i = raw.index(b"\n")
            meta = _loads(raw[:i])
            if meta["v"] != vers:
                meta["inv"] = True              # bị vô hiệu hoá bởi sự kiện bus: vẫn phục vụ bản cũ (SWR) trong lúc làm mới nền — tránh dồn request chờ khi nến cập nhật liên tục
            return False, (meta, raw[i + 1:]), vers
        except Exception as e:  # noqa: BLE001  entry hỏng -> miss
            C_ERR.labels("decode").inc()
            log.warning("cache entry hỏng: %s", type(e).__name__)
            return False, None, vers

    def decode_body(self, meta: dict, body: bytes) -> bytes:
        if meta.get("z") == 1:
            return _ZD.decompress(body)
        if meta.get("z") == 2:
            return zlib.decompress(body)
        return body

    async def store(self, key: str, pol: Policy, ttl: float, vers: list, ctype: str, body: bytes) -> str:
        etag = 'W/"' + hashlib.blake2b(body, digest_size=8).hexdigest() + '"'
        z, payload = 0, body
        if len(body) >= self.compress_min:
            if _ZC is not None:
                z, payload = 1, _ZC.compress(body)
            else:
                z, payload = 2, zlib.compress(body, 1)
        stale = pol.stale if pol.stale is not None else min(2 * ttl, 120)
        meta = {"s": int((time.time() + ttl) * 1000), "tt": ttl, "v": vers, "t": etag, "c": ctype, "z": z}
        env = _dumps(meta) + b"\n" + payload
        try:
            t0 = time.perf_counter()
            await self.r.set(key, env, px=int((ttl + stale) * 1000))
            C_RLAT.labels("set").observe(time.perf_counter() - t0)
            C_BYTES.inc(len(env))
            C_RAW.inc(len(body))
        except Exception as e:  # noqa: BLE001
            self._fail("set", e)
        return etag

    # ---------- tính / điền (single-flight) ----------
    async def call_inner(self, scope: dict) -> tuple[int, str, bytes]:
        sc = dict(scope)
        sc["state"] = {}
        sc.pop("route", None)
        sc.pop("endpoint", None)
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        status, ctype, chunks = 500, "", []

        async def send(msg):
            nonlocal status, ctype
            if msg["type"] == "http.response.start":
                status = msg["status"]
                for k, v in msg.get("headers", []):
                    if k.lower() == b"content-type":
                        ctype = v.decode("latin-1")
            elif msg["type"] == "http.response.body":
                chunks.append(msg.get("body", b""))

        await self.inner(sc, receive, send)
        return status, ctype, b"".join(chunks)

    def fill(self, fkey: str, key: str, pol: Policy, ttl: float, vers: list, scope: dict) -> asyncio.Task:
        """Một tác vụ tính DUY NHẤT cho mỗi khoá (single-flight, tồn tại độc lập với request khởi tạo)."""
        t = self._inflight.get(fkey)
        if t is not None:
            G_SHARED.inc()
            return t

        async def run():
            try:
                status, ctype, body = await self.call_inner(scope)
                etag = None
                if status == 200 and "json" in ctype.lower() and len(body) <= self.max_body and self.active and not await self._off():
                    etag = await self.store(key, pol, ttl, vers, ctype, body)
                return status, ctype, body, etag
            finally:
                self._inflight.pop(fkey, None)

        t = asyncio.get_running_loop().create_task(run())
        self._inflight[fkey] = t
        t.add_done_callback(lambda f: f.cancelled() or f.exception())    # tránh cảnh báo "never retrieved"
        return t

    async def _off(self) -> bool:
        try:
            return bool(await self.r.exists("cache:ctl:off"))
        except Exception:  # noqa: BLE001
            return False

    # ---------- theo dõi độ nóng + làm nóng ----------
    def touch(self, key: str, path: str, qs: bytes, principal, scope_id: str, seed: bool = False) -> None:
        h = self._hot.get(key)
        now = time.monotonic()
        if h is None:
            if len(self._hot) >= self.hot_max:
                old = min((k for k, v in self._hot.items() if not v["seed"]), key=lambda k: self._hot[k]["last"], default=None)
                if old is None:
                    return
                self._hot.pop(old, None)
            self._hot[key] = {"path": path, "qs": qs, "kind": "master" if principal.is_master else "client",
                              "accounts": tuple(sorted(principal.accounts)), "last": now, "seed": seed, "n": 1}
        else:
            h["last"] = now
            h["n"] += 1

    def synth_scope(self, h: dict) -> dict:
        s = self.settings
        hdrs = []
        if s and s.api_tokens:
            hdrs.append((b"x-api-key", s.api_tokens[0].encode()))
        if h["kind"] == "client":
            hdrs += [(b"x-user-id", b"cache-warm"), (b"x-role", b"client"), (b"x-accounts", ",".join(h["accounts"]).encode()),
                     (b"x-auth-secret", (s.auth_trust_secret if s else "").encode())]
        return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http", "path": h["path"],
                "raw_path": h["path"].encode(), "query_string": h["qs"], "root_path": "", "headers": hdrs, "client": ("127.0.0.1", 0),
                "server": ("gateway", 8000), "state": {}, "app": self.app_ref}

    async def warm_once(self) -> int:
        """Làm mới trước hạn các khoá nóng (còn <35% TTL hoặc đã vô hiệu): request thật chỉ còn đọc cache."""
        now = time.monotonic()
        for k in [k for k, v in self._hot.items() if not v["seed"] and now - v["last"] > self.hot_window]:
            self._hot.pop(k, None)
        todo = []
        for key, h in list(self._hot.items()):
            hit = self.match(h["path"])
            if hit is None:
                continue
            pol, m = hit
            canon, q = self.canon_query(h["qs"])
            vkeys = pol.vers(m, q)
            lk = await self.lookup(key, vkeys)
            if lk is None:
                return 0
            off, ent, vers = lk
            if off:
                return 0
            ttl = pol.ttl(m, q) * self.ttl_scale
            if ttl < 10:     # TTL ngắn (quotes/overview/bars M1): để SWR + single-flight theo yêu cầu, không refresh-ahead liên tục (tốn CPU event loop vô ích)
                continue
            if ent is not None:
                left = ent[0]["s"] / 1000 - time.time()
                if left > 0.35 * ent[0]["tt"] and not ent[0].get("inv"):
                    continue
            todo.append((key, pol, ttl, list(vers), h))

        async def one(key, pol, ttl, vers, h):
            async with self._bg_sem:
                C_REFRESH.labels("warm").inc()
                with contextlib.suppress(Exception):
                    await self.fill(f"{key}", key, pol, ttl, vers, self.synth_scope(h))

        await asyncio.gather(*(one(*t) for t in todo))
        return len(todo)

    def seed(self) -> None:
        from .authz import Principal
        for path, qs, who in SEEDS:
            for w in who:
                p = Principal("master") if w == "m" else Principal("client", "seed", frozenset())
                hit = self.match(path)
                if hit is None:
                    continue
                pol, m = hit
                sid = self.scope_id(p, pol)
                canon, _ = self.canon_query(qs.encode())
                self.touch(self.key_for(sid, path, canon), path, qs.encode(), p, sid, seed=True)

    async def _warm_loop(self):
        while True:
            try:
                await asyncio.sleep(self.warm_interval)
                if self.active and self.inner is not None:
                    await self.warm_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                C_ERR.labels("warm").inc()
                log.exception("warm lỗi")

    # ---------- vô hiệu hoá theo sự kiện bus ----------
    @staticmethod
    def event_vkeys(stream: str, payload: dict) -> set[str]:
        dom = STREAM_DOMAINS.get(stream)
        if dom is None:
            return set()
        if dom == "bars":
            sym, tf = payload.get("symbol"), payload.get("tf")
            if tf in ("M1", "M5", "M15"):    # nến phút được cập nhật liên tục (collector phát lại mỗi lần poll): để TTL 5-20s + refresh-ahead quyết định, tránh vô hiệu hoá liên tục
                return set()
            return {f"bars:{sym}:{tf}"} if sym and tf else {"bars:all"}
        return {dom}

    async def bump(self, vkeys: set[str]) -> None:
        if not vkeys or self.r is None:
            return
        try:
            p = self.r.pipeline(transaction=False)
            for v in vkeys:
                k = f"cache:ver:{v}"
                p.incr(k)
                p.expire(k, 7 * 86400)
                C_INV.labels(v.split(":")[0]).inc()
            await p.execute()
        except Exception as e:  # noqa: BLE001
            self._fail("bump", e)

    async def _inval_loop(self, bus):
        """Đọc luồng bus bằng client chỉ-đọc của gateway (ts_gateway); ghi version bằng ts_cache. Bump lần 2 sau 2s (storage-writer có thể ghi DB sau sự kiện)."""
        import json as _json
        last = {s: "$" for s in STREAM_DOMAINS}
        while True:
            try:
                now = time.monotonic()
                due = [k for t, k in self._later if t <= now]
                self._later = [(t, k) for t, k in self._later if t > now]
                for k in due:
                    await self.bump(k)
                res = await bus.xread(last, count=500, block=1000)
                batch: set[str] = set()
                for st, msgs in res or []:
                    for mid, fields in msgs:
                        last[st] = mid
                        try:
                            ev = _json.loads(fields["e"])
                        except (KeyError, ValueError):
                            batch |= self.event_vkeys(st, {})
                            continue
                        batch |= self.event_vkeys(st, ev.get("payload") or {})
                if batch:
                    await self.bump(batch)
                    self._later.append((time.monotonic() + 2.0, set(batch)))
            except asyncio.CancelledError:
                raise
            except (TimeoutError, asyncio.TimeoutError, _RedisTimeout) as e:   # XREAD block chạm hạn đọc (vd. vòng sự kiện bị đứng thoáng qua) — vô hại, con trỏ `last` giữ nguyên
                log.debug("invalidate: XREAD timeout (%s) — thử lại", e)
                await asyncio.sleep(0.2)
            except Exception:  # noqa: BLE001
                C_ERR.labels("invalidate").inc()
                log.exception("invalidate lỗi")
                await asyncio.sleep(1.0)

    # ---------- vòng đời ----------
    def start(self, app) -> None:
        if not self.enabled or self._tasks:
            return
        self.app_ref = app
        if self.do_warm:
            self.seed()
            self._tasks.append(asyncio.create_task(self._warm_loop()))
        if self.do_inval and getattr(app.state, "redis", None) is not None:
            self._tasks.append(asyncio.create_task(self._inval_loop(app.state.redis)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.r is not None:
            with contextlib.suppress(Exception):
                await self.r.aclose()


def _cc(pol: Policy, ttl: float) -> tuple[bytes, bytes]:
    """(Cache-Control, X-Accel-Expires). Dữ liệu nhạy cảm theo tài khoản: private,no-store + nginx không giữ. Dữ liệu dùng chung nhưng cần phiên: `private` (KHÔNG public -> CDN/Cloudflare không phát cho người chưa đăng nhập)."""
    if pol.scope == "account":
        return b"private, no-store", b"0"
    ma = int(ttl // 4)
    return f"private, max-age={ma}, stale-while-revalidate={int(ttl * 2)}".encode(), str(max(1, int(ttl // 2)) if ttl < 3000 else int(ttl)).encode()


class CacheMiddleware:
    """ASGI thuần (nhanh hơn BaseHTTPMiddleware). Chèn NGOÀI hide_sources_mw (lưu nội dung đã gỡ tên nguồn), TRONG count_requests (SLO)."""

    def __init__(self, app, cache: ResponseCache, settings):
        self.app, self.c, self.s = app, cache, settings
        cache.inner, cache.settings = app, settings

    async def __call__(self, scope, receive, send):
        c = self.c
        if scope["type"] == "lifespan":
            async def send2(msg):
                if msg["type"] == "lifespan.startup.complete":
                    with contextlib.suppress(Exception):
                        c.start(scope["app"])
                await send(msg)

            async def recv2():
                msg = await receive()
                if msg["type"] == "lifespan.shutdown":
                    with contextlib.suppress(Exception):
                        await c.stop()
                return msg
            return await self.app(scope, recv2, send2)
        if scope["type"] != "http" or scope["method"] != "GET" or not c.enabled:
            return await self.app(scope, receive, send)
        hit = c.match(scope["path"])
        if hit is None:
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        pol, m = hit
        started = False

        async def send_(msg):
            nonlocal started
            started = True
            await send(msg)

        try:
            return await self._serve(scope, receive, send_, pol, m, t0)
        except _AppError as e:
            raise e.exc from None
        except _Passthrough:
            C_REQ.labels(pol.name, "bypass").inc()
        except Exception:  # noqa: BLE001  mọi lỗi cache -> fail-open (chỉ khi CHƯA gửi byte nào)
            C_ERR.labels("serve").inc()
            C_REQ.labels(pol.name, "error").inc()
            log.exception("cache serve lỗi")
            if started:
                raise
        return await self.app(scope, receive, send)

    async def _serve(self, scope, receive, send, pol: Policy, m: re.Match, t0: float):
        c, headers = self.c, Headers(scope=scope)
        if not token_ok(headers.get("x-api-key"), self.s.api_tokens, self.s.auth_disabled):
            raise _Passthrough
        try:
            principal = principal_from_headers(headers, self.s.auth_trust_secret)
        except HTTPException:
            raise _Passthrough from None
        qs = scope.get("query_string", b"")
        if len(qs) > 1024:
            raise _Passthrough
        canon, q = c.canon_query(qs)
        sid = c.scope_id(principal, pol)
        path = scope["path"]
        key = c.key_for(sid, path, canon)
        vkeys = pol.vers(m, q)
        # Redis lỗi/mạch hở: KHÔNG bỏ qua hẳn — vẫn single-flight trong tiến trình để không dồn N request đồng thời xuống DB (không đọc/ghi Redis)
        lk = await c.lookup(key, vkeys) if c.active else None
        if lk is None:
            lk = (False, None, [""] * len(vkeys))
        off, ent, vers = lk
        if off:
            raise _Passthrough
        route_ns = SimpleNamespace(path=pol.label)
        ttl = pol.ttl(m, q) * c.ttl_scale
        now_ms = time.time() * 1000
        inm = headers.get("if-none-match")
        origin = headers.get("origin")
        cors = origin if origin and origin in (self.s.cors_origins or ()) else None
        if ent is not None:
            meta, raw = ent
            c.touch(key, path, qs, principal, sid)
            state = "hit" if now_ms < meta["s"] and not meta.get("inv") else "stale"
            if state == "stale":
                self._refresh_bg(key, pol, ttl, vers, scope, principal, sid)
            body = c.decode_body(meta, raw)
            scope["route"] = route_ns
            await self._send(send, 200, meta["c"], body, meta["t"], pol, meta["tt"], state.upper(), inm, cors)
            C_REQ.labels(pol.name, state).inc()
            C_LAT.labels(pol.name, state).observe(time.perf_counter() - t0)
            return None
        # MISS: single-flight (1 lần tính cho mọi request cùng khoá)
        c.touch(key, path, qs, principal, sid)
        task = c.fill(key, key, pol, ttl, list(vers), scope)
        try:
            status, ctype, body, etag = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001  lỗi của APP (không phải của cache): truyền nguyên, KHÔNG gọi app lần 2
            raise _AppError(e) from e
        if status == 200 and etag:
            scope["route"] = route_ns
            await self._send(send, 200, ctype, body, etag, pol, ttl, "MISS", inm, cors)
        else:   # không cache được (lỗi/không phải JSON/quá lớn/cờ tắt): trả nguyên kết quả của app
            await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", ctype.encode("latin-1")), (b"content-length", str(len(body)).encode()),
                                                                                     (b"cache-control", b"private, no-store"), (b"x-gw-cache", b"BYPASS")]})
            await send({"type": "http.response.body", "body": body})
        C_REQ.labels(pol.name, "miss").inc()
        C_LAT.labels(pol.name, "miss").observe(time.perf_counter() - t0)
        return None

    def _refresh_bg(self, key, pol, ttl, vers, scope, principal, sid):
        c = self.c
        if key in c._inflight:
            return
        C_REFRESH.labels("swr").inc()
        sc = dict(scope)    # bản sao: tiêu thụ độc lập với request gốc (header đã xác thực ở trên, không đổi)
        task = c.fill(key, key, pol, ttl, list(vers), sc)
        task.add_done_callback(lambda f: f.cancelled() or f.exception())

    @staticmethod
    async def _send(send, status, ctype, body, etag, pol, ttl, state, inm, cors):
        cc, accel = _cc(pol, ttl)
        hdrs = [(b"etag", etag.encode()), (b"cache-control", cc), (b"x-accel-expires", accel), (b"x-gw-cache", state.encode())]
        if cors:
            hdrs += [(b"access-control-allow-origin", cors.encode()), (b"vary", b"Origin")]
        if inm and etag in [x.strip() for x in inm.split(",")]:
            await send({"type": "http.response.start", "status": 304, "headers": hdrs})
            await send({"type": "http.response.body", "body": b""})
            return
        hdrs += [(b"content-type", ctype.encode("latin-1")), (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": status, "headers": hdrs})
        await send({"type": "http.response.body", "body": body})


class _AppError(Exception):
    def __init__(self, exc: Exception):
        super().__init__(str(exc))
        self.exc = exc


class _Passthrough(Exception):
    pass
