"""Proxy AI Training Class: /v1/ai-trading/class/* -> ai-trading /class/*. Hợp đồng: docs/handoff/AI_CLASSROOM_API.md.
Vai: master/service (tất cả) hoặc "expert" (chỉ phòng mình là thành viên — service ai-trading kiểm, 404 đồng nhất). analyst/support/auditor/client -> 403.
Ghi (POST): Origin + CSRF (trừ service) + JSON có giới hạn; giới hạn tốc độ theo người dùng; audit log (không ghi nội dung). Gateway CHỈ chuyển tiếp danh sách trắng
đường dẫn; header danh tính X-Class-* do gateway đặt (không nhận từ client). Tin nhắn trả về SSE (không buffer). Không có đường đặt lệnh."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .authz import FORBIDDEN, get_principal
from .user_routes import csrf_binding, csrf_ok, origin_ok

log = logging.getLogger("gateway.class")
R = r"[0-9a-f]{32}"
I = r"[A-Za-z0-9_\-]{1,64}"   # id bộ nhớ/ phương pháp/ xung đột/ khoá canvas (không chứa '.' hay '/')
EXPORT_FMT = r"(?:md|pdf)"
GET_PATHS = [re.compile(x) for x in (
    r"^status$", r"^rooms$", r"^rooms/trash$", rf"^rooms/{R}$", rf"^rooms/{R}/(profile|labels|actions|minutes\.md|profile/diff|canvas)$", rf"^rooms/{R}/profile/versions/\d{{1,6}}$",
    rf"^rooms/{R}/media/[0-9a-f]{{16}}$", rf"^rooms/{R}/media/{R}$", rf"^rooms/{R}/actions/{R}$", rf"^rooms/{R}/memory/retrieve$",
    r"^templates$", r"^demo/script$", r"^options/stats$",
    r"^memory$", r"^memory/(conflicts|stats|export)$", rf"^memory/{I}$",
    r"^methods$", rf"^methods/{I}$", rf"^methods/{I}/(relations|canvas|plan|plan/export|messages)$")]
POST_PATHS = [(re.compile(x), lim) for x, lim in (
    (r"^rooms$", 8192), (rf"^rooms/{R}/members$", 8192), (rf"^rooms/{R}/pins$", 4096), (rf"^rooms/{R}/messages$", 8192), (rf"^rooms/{R}/messages/{R}/review$", 8192),
    (rf"^rooms/{R}/attachments$", 2_800_000), (rf"^rooms/{R}/actions$", 16384), (rf"^rooms/{R}/actions/{R}/confirm$", 2048), (rf"^rooms/{R}/labels$", 4096),
    (rf"^rooms/{R}/profile/export$", 4096), (rf"^rooms/{R}/final-test$", 2048),
    (rf"^rooms/{R}/canvas/{I}/(confirm|edit)$", 16384), (rf"^rooms/{R}/restore$", 2048), (r"^rooms/bulk-delete$", 8192),
    (rf"^rooms/{R}/understand$", 8192), (rf"^rooms/{R}/options/feedback$", 2048), (rf"^rooms/{R}/memory/extract$", 8192),
    (r"^memory$", 16384), (rf"^memory/{I}/(confirm|reject|pin|lock|revoke)$", 2048), (rf"^memory/conflicts/{I}/resolve$", 4096), (r"^memory/import$", 1_000_000),
    (r"^methods$", 16384), (rf"^methods/{I}/scenarios$", 8192), (rf"^methods/{I}/messages$", 8192), (rf"^methods/{I}/plan/recheck$", 4096),
    (rf"^methods/{I}/canvas/{I}/(edit|confirm)$", 16384), (rf"^methods/{I}/plan/(evidence|approve)$", 8192))]
PATCH_PATHS = [(re.compile(x), lim) for x, lim in ((rf"^memory/{I}$", 16384), (rf"^methods/{I}$", 16384), (rf"^methods/{I}/scenarios/{R}$", 4096))]
PUT_PATHS = [(re.compile(x), lim) for x, lim in ((rf"^methods/{I}/relations$", 16384),)]
DELETE_PATHS = [(re.compile(x), lim) for x, lim in (
    (rf"^rooms/{R}$", 2048), (rf"^rooms/{R}/purge$", 2048), (rf"^memory/{I}$", 2048), (rf"^methods/{I}$", 2048), (rf"^methods/{I}/scenarios/{R}$", 2048))]
MASTER_ONLY = re.compile(r"(^|/)(final-test|purge|plan/evidence|plan/approve|lock|revoke)$")   # test khoá + xoá vĩnh viễn: chỉ master
SSE_PATHS = re.compile(rf"^(rooms/{R}|methods/{I})/messages$")
PASS_CODES = {200, 201, 202, 400, 403, 404, 409, 413, 415, 422, 429}
UID_OK = re.compile(r"^[A-Za-z0-9_.:@\-]{1,64}$")


class _Lim:
    def __init__(self, n: int, per: float):
        self.n, self.per, self.h = n, per, defaultdict(deque)

    def ok(self, k: str) -> bool:
        t, q = time.monotonic(), self.h[k]
        while q and t - q[0] > self.per:
            q.popleft()
        if len(q) >= self.n:
            return False
        q.append(t)
        return True


def _hdrs() -> dict:
    try:
        from tscommon.internal_auth import internal_headers
        return internal_headers()
    except Exception:  # noqa: BLE001
        return {}


def register_class_routes(api: APIRouter, secret_fn) -> None:
    write_lim, msg_lim = _Lim(60, 60.0), _Lim(12, 60.0)

    def base() -> str:
        return os.getenv("AI_TRADING_URL", "http://ai-trading:8000").rstrip("/")

    def ident(request: Request) -> dict:
        p = get_principal(request)
        if p.is_master:
            uid, role = (p.user_id or ("service" if p.kind == "service" else "master")), "master"
        elif p.role == "expert" and p.user_id:
            uid, role = p.user_id, "expert"
        else:
            raise HTTPException(403, FORBIDDEN)
        if not UID_OK.match(uid):
            raise HTTPException(403, FORBIDDEN)
        return {"x-class-user": uid, "x-class-role": role, "x-class-name": urllib.parse.quote("Quản trị") if role == "master" else ""}   # header chỉ ASCII: percent-encode, ai-trading unquote

    def open_up(method: str, sub: str, qs: str, body: bytes | None, idh: dict):
        url = f"{base()}/class/{sub}" + (f"?{qs}" if qs else "")
        req = urllib.request.Request(url, data=body, method=method, headers={**_hdrs(), **idh, "Accept": "*/*", **({"Content-Type": "application/json"} if body is not None else {})})
        try:
            return urllib.request.urlopen(req, timeout=120)  # noqa: S310 (URL nội bộ từ cấu hình; đường dẫn đã whitelist bằng regex)
        except urllib.error.HTTPError as e:
            return e

    async def proxy(request: Request, sub: str, method: str, body: bytes | None, stream: bool = False):
        idh = ident(request)
        try:
            r = await asyncio.to_thread(open_up, method, sub, request.url.query if method == "GET" else "", body, idh)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Lớp học không khả dụng: {type(e).__name__}") from None
        code = getattr(r, "status", None) or getattr(r, "code", 502)
        ctype = r.headers.get("Content-Type", "application/json")
        if stream and code == 200 and ctype.startswith("text/event-stream"):
            async def gen():
                try:
                    while True:
                        line = await asyncio.to_thread(r.readline)
                        if not line:
                            break
                        yield line
                finally:
                    r.close()
            return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"})
        raw = await asyncio.to_thread(r.read, 9_000_000)
        r.close()
        if code not in PASS_CODES:
            raise HTTPException(502, "Lớp học trả dữ liệu không hợp lệ")
        h = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        for k in ("Content-Disposition", "Content-Security-Policy"):
            if r.headers.get(k):
                h[k] = r.headers[k]
        return Response(raw, status_code=code, media_type=ctype.split(";")[0] if not ctype.startswith("text/") else ctype, headers=h)

    async def read_json(request: Request, limit: int, optional: bool = False) -> bytes:
        p = get_principal(request)
        if not origin_ok(request.headers):
            raise HTTPException(403, "origin")
        if p.kind != "service" and not csrf_ok(secret_fn(), request.headers.get("x-csrf-token"), bind=csrf_binding(request)):
            raise HTTPException(403, "csrf")
        try:
            if int(request.headers.get("content-length", "0")) > limit:
                raise HTTPException(413, "body quá lớn")
        except ValueError:
            raise HTTPException(400, "content-length") from None
        raw = await request.body()
        if len(raw) > limit:
            raise HTTPException(413, "body quá lớn")
        if optional and not raw:
            return b""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "cần Content-Type: application/json")
        try:
            if not isinstance(json.loads(raw), dict):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "JSON không hợp lệ") from None
        return raw

    @api.get("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert] AI Training Class: đọc (phòng/tin/hồ sơ/nhãn/biên bản)")
    async def class_get(request: Request, sub: str):
        ident(request)
        if not any(rx.match(sub) for rx in GET_PATHS):
            raise HTTPException(404, "không tìm thấy")
        return await proxy(request, sub, "GET", None)

    @api.get("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert] AI Training Class: đọc (phòng/tin/hồ sơ/nhãn/biên bản/bộ nhớ/phương pháp)")
    async def class_get(request: Request, sub: str):
        ident(request)
        if not any(rx.match(sub) for rx in GET_PATHS):
            raise HTTPException(404, "không tìm thấy")
        return await proxy(request, sub, "GET", None)

    async def write(request: Request, sub: str, method: str, table):
        idh = ident(request)
        lim = next((n for rx, n in table if rx.match(sub)), None)
        if lim is None:
            raise HTTPException(404, "không tìm thấy")
        if MASTER_ONLY.search(sub) and idh["x-class-role"] != "master":
            raise HTTPException(403, "Chỉ master thực hiện được thao tác này")
        raw = await read_json(request, lim, optional=method == "DELETE")
        uid = idh["x-class-user"]
        is_msg = bool(SSE_PATHS.match(sub)) and method == "POST"
        if not write_lim.ok(uid) or (is_msg and not msg_lim.ok(uid)):
            raise HTTPException(429, "Thao tác quá nhanh, thử lại sau ít giây")
        log.info("class audit user=%s role=%s %s %s", uid, idh["x-class-role"], method, re.sub(R, "<id>", sub))
        return await proxy(request, sub, method, raw or None, stream=is_msg)

    @api.post("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert + Origin + CSRF] AI Training Class: ghi (tin nhắn SSE, đính kèm, action, nhãn, hồ sơ, bộ nhớ, phương pháp)")
    async def class_post(request: Request, sub: str):
        return await write(request, sub, "POST", POST_PATHS)

    @api.patch("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert + Origin + CSRF] AI Training Class: sửa")
    async def class_patch(request: Request, sub: str):
        return await write(request, sub, "PATCH", PATCH_PATHS)

    @api.put("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert + Origin + CSRF] AI Training Class: thay thế")
    async def class_put(request: Request, sub: str):
        return await write(request, sub, "PUT", PUT_PATHS)

    @api.delete("/ai-trading/class/{sub:path}", tags=["ai-classroom"], summary="[master|expert + Origin + CSRF] AI Training Class: xoá (purge: master)")
    async def class_delete(request: Request, sub: str):
        return await write(request, sub, "DELETE", DELETE_PATHS)
