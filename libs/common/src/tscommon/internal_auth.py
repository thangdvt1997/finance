"""Xác thực service-to-service bằng header bí mật nội bộ `X-Internal-Token` (HARDENING §6, pentest P2).

Phía SERVICE (alert-rules, journal, risk-monitor, paper-trader, reporter, briefing...):
    install_internal_auth(app, "journal")
  -> middleware ASGI kiểm `X-Internal-Token` (so sánh hằng thời gian, hmac.compare_digest) cho MỌI đường trừ /healthz /readyz /livez /metrics.

Phía CLIENT (api-gateway, risk-monitor):
    install_urllib_client({"journal", "alert-rules", ...})
  -> handler urllib gắn header CHỈ cho host trong allowlist (không rò sang host khác; header "unredirected" nên không theo redirect).
    Hoặc gắn tay: headers={**internal_headers()}.

Biến môi trường:
  INTERNAL_TOKEN            bí mật hiện hành (hoặc INTERNAL_TOKEN_FILE = đường dẫn file chứa token).
  INTERNAL_TOKEN_PREV       (tuỳ chọn) token cũ còn được CHẤP NHẬN trong lúc xoay (client luôn gửi INTERNAL_TOKEN).
  INTERNAL_AUTH_MODE        off | log | enforce. Mặc định `log` (chỉ ghi log + đếm metric, KHÔNG chặn) để triển khai không outage;
                            `enforce` -> 401 nếu thiếu/sai; enforce mà chưa cấu hình token -> 503 (fail-closed).
Không bao giờ log giá trị token.
"""
from __future__ import annotations

import hmac
import logging
import os
import time
import urllib.request
from typing import Iterable

HEADER = "X-Internal-Token"
_HEADER_B = HEADER.lower().encode()
# Host nội bộ nhận header (client). Ghi đè bằng INTERNAL_TOKEN_HOSTS="a,b,c".
DEFAULT_HOSTS = frozenset({"alert-rules", "journal", "risk-monitor", "paper-trader", "reporter", "briefing", "track-record",
                           "pattern-engine", "pattern-render", "vn-market", "analytics", "data-keeper",
                           "market-collector", "news-collector", "expert-collector", "alert-service", "nlp", "storage-writer"})
EXEMPT_PATHS = frozenset({"/healthz", "/readyz", "/livez", "/metrics"})
MODES = ("off", "log", "enforce")

log = logging.getLogger("tscommon.internal_auth")

try:  # metric tuỳ chọn (prometheus_client có sẵn trong mọi service dùng tscommon)
    from prometheus_client import Counter

    _REQS = Counter("internal_auth_requests_total", "Yêu cầu tới endpoint nội bộ theo kết quả kiểm X-Internal-Token",
                    ["service", "result", "mode"])
except Exception:  # noqa: BLE001  # pragma: no cover
    _REQS = None


def _read_secret(name: str) -> str:
    v = os.getenv(name, "").strip()
    if v:
        return v
    path = os.getenv(f"{name}_FILE", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            log.error("không đọc được %s_FILE", name)
    return ""


def load_tokens() -> list[str]:
    """Token chấp nhận: [hiện hành, cũ(tuỳ chọn)] — bỏ rỗng/trùng."""
    out: list[str] = []
    for n in ("INTERNAL_TOKEN", "INTERNAL_TOKEN_PREV"):
        t = _read_secret(n)
        if t and t not in out:
            out.append(t)
    return out


def current_token() -> str:
    return _read_secret("INTERNAL_TOKEN")


def internal_headers() -> dict[str, str]:
    t = current_token()
    return {HEADER: t} if t else {}


def get_mode(default: str = "log") -> str:
    m = (os.getenv("INTERNAL_AUTH_MODE", default) or default).strip().lower()
    return m if m in MODES else default


def check_token(presented: str | bytes | None, tokens: Iterable[str]) -> bool:
    if not presented:
        return False
    p = presented if isinstance(presented, bytes) else presented.encode()
    ok = False
    for t in tokens:  # không dừng sớm: thời gian không phụ thuộc token nào khớp
        ok |= hmac.compare_digest(p, t.encode())
    return ok


class InternalTokenMiddleware:
    """ASGI middleware (http + websocket). Dùng app.add_middleware(InternalTokenMiddleware, service=..., mode=..., tokens=...)."""

    def __init__(self, app, service: str = "", mode: str | None = None, tokens: list[str] | None = None,
                 exempt: Iterable[str] = EXEMPT_PATHS, log_interval_s: float = 10.0):
        self.app, self.service = app, service or os.getenv("SERVICE_NAME", "")
        self.mode = mode if mode in MODES else get_mode()
        self.tokens = load_tokens() if tokens is None else [t for t in tokens if t]
        self.exempt = frozenset(exempt)
        self._log_every, self._last_log = log_interval_s, {}
        if self.mode == "enforce" and not self.tokens:
            log.error("INTERNAL_AUTH_MODE=enforce nhưng INTERNAL_TOKEN trống -> mọi endpoint (trừ health/metrics) trả 503")
        log.info("internal-auth service=%s mode=%s tokens=%d", self.service, self.mode, len(self.tokens))

    def _count(self, result: str) -> None:
        if _REQS is not None:
            try:
                _REQS.labels(self.service, result, self.mode).inc()
            except Exception:  # noqa: BLE001
                pass

    def _note(self, result: str, scope) -> None:
        """Log có giới hạn tần suất theo (kết quả, đường) — không log token."""
        path = scope.get("path", "")
        key = (result, scope.get("method", "WS"), path)
        now = time.monotonic()
        if now - self._last_log.get(key, 0.0) >= self._log_every:
            if len(self._last_log) > 2048:
                self._last_log.clear()
            self._last_log[key] = now
            client = (scope.get("client") or ("?",))[0]
            log.warning("internal-auth %s: %s %s từ %s (mode=%s)", result, scope.get("method", "WS"), path, client, self.mode)

    async def __call__(self, scope, receive, send):
        if self.mode == "off" or scope.get("type") not in ("http", "websocket") or scope.get("path", "") in self.exempt:
            return await self.app(scope, receive, send)
        presented = None
        for k, v in scope.get("headers") or ():
            if k == _HEADER_B:
                presented = v
                break
        if self.tokens and check_token(presented, self.tokens):
            self._count("ok")
            return await self.app(scope, receive, send)
        result = "missing" if not presented else ("unconfigured" if not self.tokens else "invalid")
        self._count(result)
        self._note(result, scope)
        if self.mode != "enforce":
            return await self.app(scope, receive, send)
        status = 503 if not self.tokens else 401
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = b'{"detail":"internal auth required"}'
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})


def install_internal_auth(app, service: str = "", **kw):
    """Gắn middleware vào FastAPI/Starlette app (gọi trước khi app bắt đầu phục vụ)."""
    app.add_middleware(InternalTokenMiddleware, service=service, **kw)
    return app


class InternalTokenHandler(urllib.request.BaseHandler):
    """urllib pre-processor: gắn X-Internal-Token cho request tới host trong allowlist (không gắn cho host khác)."""
    handler_order = 400

    def __init__(self, hosts: Iterable[str], token: str | None = None):
        self.hosts = {h.lower() for h in hosts}
        self._token = token

    def _tok(self) -> str:
        return self._token if self._token is not None else current_token()

    def http_request(self, req):
        host = (req.host or "").split(":")[0].lower()
        tok = self._tok()
        if tok and host in self.hosts and not req.has_header(HEADER.capitalize()):
            req.add_unredirected_header(HEADER, tok)
        return req

    https_request = http_request


def install_urllib_client(hosts: Iterable[str] | None = None, token: str | None = None) -> InternalTokenHandler:
    """Cài opener toàn cục cho urllib.request.urlopen: mọi lời gọi tới `hosts` (mặc định INTERNAL_TOKEN_HOSTS hoặc DEFAULT_HOSTS)
    tự kèm X-Internal-Token."""
    if hosts is None:
        env = os.getenv("INTERNAL_TOKEN_HOSTS", "").strip()
        hosts = [x.strip() for x in env.split(",") if x.strip()] if env else DEFAULT_HOSTS
    h = InternalTokenHandler(hosts, token)
    log.info("internal-auth client: %d host, token=%s", len(h.hosts), "có" if h._tok() else "TRỐNG")
    urllib.request.install_opener(urllib.request.build_opener(h))
    return h
