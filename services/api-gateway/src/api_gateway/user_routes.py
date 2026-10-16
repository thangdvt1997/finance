"""Cấu hình người dùng: /v1/user/* -> service `alert-rules` (quy tắc cảnh báo + tuỳ chọn watchlist/layout).

ĐÂY LÀ NHÓM ROUTE GHI DUY NHẤT của gateway, và CHỈ cho cấu hình cảnh báo/ tuỳ chọn giao diện (KHÔNG liên quan đặt lệnh/tài khoản MT).
Whitelist tường minh (regex bên dưới); mọi đường dẫn/method khác -> 404/405. Phòng thủ nhiều lớp (nginx cũng whitelist + Origin + rate limit):
  - ghi cần header `X-CSRF-Token` (HMAC theo giờ từ API token; chỉ lấy được qua GET /v1/user/csrf cùng origin, trình duyệt khác origin không đọc được),
  - Content-Type phải là application/json (ép preflight CORS nếu bị gọi chéo origin), body <= 16KB,
  - nếu có `Origin` thì host phải khớp `Host`; `Sec-Fetch-Site: cross-site` bị từ chối.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .authz import FORBIDDEN, get_principal

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
READ_OK = re.compile(r"^(rules|rule-events|prefs|push|limits|limits/history|notifications|client-prefs|push/devices|tickets)$")
WRITE_OK = [  # (method, path regex)
    ("POST", re.compile(r"^rules$")),
    ("POST", re.compile(r"^rules/preview$")),
    ("POST", re.compile(rf"^rules/{UUID}/preview$")),
    ("PUT", re.compile(rf"^rules/{UUID}$")),
    ("DELETE", re.compile(rf"^rules/{UUID}$")),
    ("PUT", re.compile(r"^prefs$")),
    ("POST", re.compile(r"^push/(subscribe|unsubscribe|test)$")),   # Web Push: đăng ký/huỷ thiết bị CỦA CHÍNH MÌNH (alert-rules kiểm chủ sở hữu)
    # Giới hạn/mục tiêu, thông báo, cài đặt đồng bộ, thiết bị push, ticket (2026-10-12). Không có đường nội bộ /internal/* ở đây.
    ("PUT", re.compile(r"^limits$")),
    ("POST", re.compile(r"^notifications/read$")),
    ("PUT", re.compile(r"^client-prefs$")),
    ("DELETE", re.compile(r"^push/devices/[0-9a-f]{16}$")),
    ("POST", re.compile(r"^tickets$")),
    ("PUT", re.compile(r"^tickets/[0-9]{1,12}$")),                    # CHỈ master (không nằm trong CLIENT_REST/CLIENT_ALLOW)
]
# Phần client được dùng (authz.CLIENT_ALLOW cũng chặn ở lớp trước). `prefs` (toàn cục) KHÔNG nằm đây.
CLIENT_REST = re.compile(rf"^(rules|rules/preview|rules/{UUID}|rules/{UUID}/preview|rule-events|push|push/subscribe|push/unsubscribe|push/test"
                         r"|limits|limits/history|notifications|notifications/read|client-prefs|push/devices|push/devices/[0-9a-f]{16}|tickets)$")
USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
MAX_BODY = 16 * 1024
CSRF_STEP_S = 3600
QUERY_RX = {   # khoá query được chuyển tiếp -> regex giá trị chặt; khoá/giá trị khác bị bỏ
    "rule_id": re.compile(r"^[0-9a-fA-F-]{1,40}$"),
    "limit": re.compile(r"^[0-9]{1,3}$"),
    "account_id": re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$"),
    "kind": re.compile(r"^(rule|limit|report|briefing|support|system)$"),
    "unread": re.compile(r"^[01]$"),
    "before": re.compile(r"^[0-9]{1,18}$"),
}
QUERY_KEYS = set(QUERY_RX)


# CSRF gắn PHIÊN (pentest 2026-10-14): token = HMAC(bí mật, giờ + danh tính phiên) -> token lấy từ phiên A không dùng được cho phiên B.
# CSRF_BIND=global quay về token dùng chung toàn hệ thống (rollback nhanh, không cần build). Cookie phiên: AUTH_COOKIE_NAME (mặc định ts_session).
CSRF_BIND = os.getenv("CSRF_BIND", "session").strip().lower()
SESSION_COOKIE = os.getenv("AUTH_COOKIE_NAME", "ts_session")


def csrf_binding(request) -> str:
    """Danh tính gắn vào token: loại principal + vai trò + user_id + băm cookie phiên (không lưu/ghi log cookie)."""
    if CSRF_BIND == "global":
        return ""
    p = get_principal(request)
    sid = request.cookies.get(SESSION_COOKIE, "") if hasattr(request, "cookies") else ""
    sh = hashlib.sha256(sid.encode()).hexdigest()[:32] if sid else "-"
    return f"{p.kind}|{p.role}|{p.user_id}|{sh}"


def csrf_token(secret: str, bucket: int, bind: str = "") -> str:
    msg = f"csrf:{bucket}:{bind}" if bind else f"csrf:{bucket}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:40]


def csrf_ok(secret: str, supplied: str | None, now: float | None = None, bind: str = "") -> bool:
    if not supplied or not secret:
        return False
    b = int((now if now is not None else time.time()) // CSRF_STEP_S)
    return any(hmac.compare_digest(supplied, csrf_token(secret, x, bind)) for x in (b, b - 1))


def origin_ok(headers) -> bool:
    if headers.get("sec-fetch-site", "") == "cross-site":
        return False
    origin = headers.get("origin")
    if origin is None:
        return True  # client không phải trình duyệt (curl/script nội bộ): vẫn bị chặn bởi CSRF token
    host = headers.get("x-forwarded-host") or headers.get("host", "")
    return re.sub(r"^https?://", "", origin) == host


def _call(method: str, url: str, body: bytes | None, extra: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers={"Accept": "application/json", **({"Content-Type": "application/json"} if body is not None else {}), **(extra or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (URL nội bộ từ cấu hình; đường dẫn đã whitelist)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _owner_headers(p) -> dict:
    """Header phạm vi gửi xuống alert-rules. client: BẮT BUỘC có user_id hợp lệ (nếu không -> 403), kèm tập tài khoản của phiên.
    master có user_id: chỉ để quản lý đăng ký push của chính mình. service (API key nội bộ): không có header = quyền master."""
    if p.kind == "service":
        return {}
    if not USER_ID_RE.match(p.user_id or ""):
        if p.kind == "client":
            raise HTTPException(403, FORBIDDEN)
        return {}
    h = {"X-Owner-Role": p.kind, "X-Owner-User": p.user_id}
    if p.kind == "client":
        h["X-Owner-Accounts"] = ",".join(sorted(p.accounts))
    return h


def register_user_routes(api: APIRouter, secret_fn) -> None:
    """secret_fn() -> chuỗi bí mật để dẫn xuất CSRF (API token đầu tiên)."""

    @api.get("/user/csrf", tags=["user"], summary="Token CSRF cho các route ghi cấu hình (hiệu lực 1-2 giờ)")
    async def csrf(request: Request):
        b = int(time.time() // CSRF_STEP_S)
        return JSONResponse({"token": csrf_token(secret_fn(), b, csrf_binding(request)), "ttl_s": CSRF_STEP_S}, headers={"Cache-Control": "no-store"})

    async def user_proxy(rest: str, request: Request):
        method = request.method
        p = get_principal(request)
        scope = _owner_headers(p)       # danh tính chủ sở hữu CHỈ do gateway đặt (từ header tin cậy của nginx), không bao giờ chuyển tiếp từ client
        if p.kind == "client" and not CLIENT_REST.match(rest):
            raise HTTPException(403, FORBIDDEN)
        if method == "GET":
            if not READ_OK.match(rest):
                raise HTTPException(404, "đường dẫn không tồn tại")
        else:
            if not any(m == method and rx.match(rest) for m, rx in WRITE_OK):
                raise HTTPException(404, "đường dẫn không tồn tại")
            if not origin_ok(request.headers):
                raise HTTPException(403, "origin")
            if not csrf_ok(secret_fn(), request.headers.get("x-csrf-token"), bind=csrf_binding(request)):
                raise HTTPException(403, "csrf")
        body = None
        if method in ("POST", "PUT"):
            raw_in = await request.body()
            if len(raw_in) > MAX_BODY:
                raise HTTPException(413, "body quá lớn")
            if raw_in:
                if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    raise HTTPException(415, "cần Content-Type: application/json")
                try:
                    json.loads(raw_in)
                except ValueError:
                    raise HTTPException(400, "JSON không hợp lệ") from None
                body = raw_in
            else:
                body = b"{}"
        base = os.getenv("ALERT_RULES_URL", "http://alert-rules:8000").rstrip("/")
        qs = urllib.parse.urlencode([(k, v) for k, v in request.query_params.multi_items() if k in QUERY_RX and QUERY_RX[k].match(v)])
        url = f"{base}/{rest}" + (f"?{qs}" if qs else "")
        try:
            code, raw = await asyncio.to_thread(_call, method, url, body, *([scope] if scope else []))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"alert-rules không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "alert-rules trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})

    for _m in ("GET", "POST", "PUT", "DELETE"):
        api.add_api_route("/user/{rest:path}", user_proxy, methods=[_m], tags=["user"], operation_id=f"user_proxy_{_m.lower()}",
                          summary="Proxy whitelist tới alert-rules: quy tắc cảnh báo + tuỳ chọn (ghi cần CSRF)")
