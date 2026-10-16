"""Báo cáo THEO TÀI KHOẢN (proxy tới service `reporter`; docs/FLEET_MGMT.md mục 5). CHỈ ĐỌC dữ liệu giao dịch, không có đường đặt lệnh.

Quyền (mặc định từ chối; 403 đồng nhất, không phân biệt "không tồn tại" với "của người khác"):
- master / service: mọi tài khoản, cả bản chưa phát hành; được generate / release / lịch.
- client: CHỈ tài khoản của mình và CHỈ bản đã phát hành (`released=true`); chỉ 2 đường GET (authz.CLIENT_ALLOW).
- support: như client (bản đã phát hành, trong phạm vi tài khoản được giao). analyst (perm report.read): trong phạm vi, thấy cả bản chưa phát hành.
- Ghi (POST generate/release, PUT schedules): chỉ master/service, kèm Origin + CSRF như /v1/journal (service nội bộ giữ API key không cần CSRF).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .authz import ACC_RE, FORBIDDEN, Principal, get_principal
from .user_routes import MAX_BODY, csrf_binding, csrf_ok, origin_ok

KIND_RE = re.compile(r"^(daily|weekly|monthly)$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MEDIA = {"html": "text/html; charset=utf-8", "pdf": "application/pdf"}
MAX_BYTES = 20 * 1024 * 1024
HTML_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'; sandbox")
PASS_CODES = {200, 404, 409, 422}


def _call(method: str, url: str, body: bytes | None = None, timeout: float = 20) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Accept": "application/json", **({"Content-Type": "application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL nội bộ từ cấu hình; đường dẫn đã whitelist)
            return r.status, r.read(MAX_BYTES + 1), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_BYTES + 1), dict(e.headers)


def can_view_unreleased(p: Principal) -> bool:
    return p.is_master or p.role == "analyst"


def _forbid() -> HTTPException:
    return HTTPException(403, FORBIDDEN)


def register_account_reports_routes(api: APIRouter, secret_fn) -> None:
    def base() -> str:
        return os.getenv("REPORTER_URL", "http://reporter:8000").rstrip("/")

    async def upstream(method: str, path: str, params: dict | None = None, body: bytes | None = None, timeout: float = 20) -> tuple[int, bytes, dict]:
        qs = urllib.parse.urlencode(params or {})
        url = f"{base()}{path}" + (f"?{qs}" if qs else "")
        try:
            return await asyncio.to_thread(_call, method, url, body, timeout)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"reporter không khả dụng: {type(e).__name__}") from None

    def as_json(code: int, raw: bytes) -> JSONResponse:
        if code not in PASS_CODES:
            raise HTTPException(502, "reporter trả dữ liệu không hợp lệ")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "reporter trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})

    def master_write_guard(request: Request) -> Principal:
        p = get_principal(request)
        if not p.is_master:
            raise _forbid()
        if not origin_ok(request.headers):
            raise HTTPException(403, "origin")
        if p.kind != "service" and not csrf_ok(secret_fn(), request.headers.get("x-csrf-token"), bind=csrf_binding(request)):
            raise HTTPException(403, "csrf")
        return p

    async def read_json(request: Request) -> dict:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "body quá lớn")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "cần Content-Type: application/json")
        try:
            d = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "JSON không hợp lệ") from None
        if not isinstance(d, dict):
            raise HTTPException(400, "JSON không hợp lệ")
        return d

    # ---------------- đọc (client/staff trong phạm vi) ----------------
    @api.get("/account-reports", tags=["account-reports"], summary="Danh sách báo cáo của 1 tài khoản (client: chỉ bản đã phát hành)")
    async def list_reports(request: Request):
        p = get_principal(request)
        ids = request.query_params.getlist("account_id")
        if len(ids) != 1 or not ACC_RE.fullmatch(ids[0]):
            raise _forbid() if not p.is_master else HTTPException(422, "cần đúng một account_id hợp lệ")
        acc = ids[0]
        if not p.can(acc):
            raise _forbid()
        code, raw, _ = await upstream("GET", "/account-reports", {"account_id": acc, "released_only": 0 if can_view_unreleased(p) else 1})
        return as_json(code, raw)

    @api.get("/account-reports/{account_id}/{period}/{ext}", tags=["account-reports"],
             summary="Tải báo cáo HTML/PDF của tài khoản (?kind=daily|weekly|monthly để chọn khi trùng kỳ)")
    async def report_file(account_id: str, period: str, ext: str, request: Request):
        p = get_principal(request)
        if not ACC_RE.fullmatch(account_id) or not p.can(account_id):
            raise _forbid()
        kind = request.query_params.get("kind")
        if not PERIOD_RE.fullmatch(period) or ext not in MEDIA or (kind is not None and not KIND_RE.fullmatch(kind)) \
                or len(request.query_params.getlist("kind")) > 1:
            raise HTTPException(404, "không tìm thấy báo cáo")
        params = {"released_only": 0 if can_view_unreleased(p) else 1, **({"kind": kind} if kind else {})}
        code, body, hdr = await upstream("GET", f"/account-reports/{urllib.parse.quote(account_id, safe='')}/{period}/{ext}", params, timeout=30)
        if code == 404:
            raise HTTPException(404, "không tìm thấy báo cáo")
        if code != 200 or len(body) > MAX_BYTES:
            raise HTTPException(502, "reporter trả dữ liệu không hợp lệ")
        k = next((v for h, v in hdr.items() if h.lower() == "x-report-kind"), kind or "report")
        k = k if KIND_RE.fullmatch(k or "") else "report"
        disp = f'attachment; filename="{k}-{period}.pdf"' if ext == "pdf" else "inline"
        headers = {"Content-Disposition": disp, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if ext == "html":
            headers["Content-Security-Policy"] = HTML_CSP
        return Response(body, media_type=MEDIA[ext], headers=headers)

    # ---------------- ghi (chỉ master/service) ----------------
    @api.post("/account-reports/generate", tags=["account-reports"], summary="Master: sinh báo cáo cho 1 tài khoản (mặc định CHƯA phát hành)")
    async def generate(request: Request):
        master_write_guard(request)
        d = await read_json(request)
        body = {k: d[k] for k in ("account_id", "kind", "period", "release") if k in d}
        code, raw, _ = await upstream("POST", "/account-reports/generate", body=json.dumps(body).encode(), timeout=150)
        return as_json(code, raw)

    @api.post("/account-reports/release", tags=["account-reports"], summary="Master: phát hành / thu hồi báo cáo cho khách")
    async def release(request: Request):
        master_write_guard(request)
        d = await read_json(request)
        body = {k: d[k] for k in ("account_id", "kind", "period", "released") if k in d}
        code, raw, _ = await upstream("POST", "/account-reports/release", body=json.dumps(body).encode())
        return as_json(code, raw)

    @api.get("/account-report-schedules", tags=["account-reports"], summary="Master: bảng lịch báo cáo theo phạm vi")
    async def get_schedules(request: Request):
        if not get_principal(request).is_master:
            raise _forbid()
        code, raw, _ = await upstream("GET", "/account-report-schedules")
        return as_json(code, raw)

    @api.put("/account-report-schedules", tags=["account-reports"], summary="Master: thay bảng lịch {schedules:[{schedule_id?,scope,kind,hour,enabled,auto_release}]}")
    async def put_schedules(request: Request):
        master_write_guard(request)
        d = await read_json(request)
        code, raw, _ = await upstream("PUT", "/account-report-schedules", body=json.dumps({"schedules": d.get("schedules")}).encode())
        return as_json(code, raw)
