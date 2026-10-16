"""Trang "Dữ liệu" (data-keeper): proxy whitelist tới service data-keeper. CHỈ master/service.
GET  /v1/data/health | /v1/data/report/daily | /v1/data/decisions?limit=N   (chỉ đọc)
POST /v1/data/recheck                                                      (hành động nhẹ: kiểm kê lại; master + Origin + CSRF)
Client/vai trò phụ -> 403. Đầu ra đã lọc ở service (không tên nguồn/tài khoản); gateway còn scrub_obj một lớp nữa."""
from __future__ import annotations

import asyncio
import json
import os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from tscommon.sources import scrub_obj

from .authz import FORBIDDEN, get_principal
from .user_routes import _call, csrf_binding, csrf_ok, origin_ok

READ_OK = {"health": "/v1/data/health", "report/daily": "/v1/data/report/daily", "decisions": "/v1/data/decisions"}
QUERY_VAL = {"limit": re.compile(r"^\d{1,3}$"), "fresh": re.compile(r"^(0|1|true|false)$")}


def register_datakeeper_routes(api: APIRouter, secret_fn) -> None:
    def base() -> str:
        return os.getenv("DATA_KEEPER_URL", "http://data-keeper:8000").rstrip("/")

    def master(request: Request):
        p = get_principal(request)
        if not p.is_master:
            raise HTTPException(403, FORBIDDEN)
        return p

    async def go(method: str, path: str, qs: str = "") -> JSONResponse:
        url = base() + path + (f"?{qs}" if qs else "")
        try:
            code, raw = await asyncio.to_thread(_call, method, url, None)   # X-Internal-Token do tscommon.internal_auth gắn tự động cho host trong allowlist
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"data-keeper không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "data-keeper trả dữ liệu không hợp lệ") from None
        if code not in (200, 429):
            raise HTTPException(502 if code >= 500 else code, "data-keeper từ chối yêu cầu")
        return JSONResponse(scrub_obj(payload, drop_keys=False, neutral="luồng giá"), status_code=code, headers={"Cache-Control": "no-store"})

    @api.get("/data/{rest:path}", tags=["data-keeper"], operation_id="data_keeper_get", summary="[master] Phủ dữ liệu mã x khung, báo cáo ngày, nhật ký quyết định")
    async def data_get(rest: str, request: Request):
        master(request)
        path = READ_OK.get(rest)
        if not path:
            raise HTTPException(404, "đường dẫn không tồn tại")
        qs = "&".join(f"{k}={v}" for k, v in request.query_params.multi_items() if k in QUERY_VAL and QUERY_VAL[k].match(v))
        return await go("GET", path, qs)

    @api.post("/data/recheck", tags=["data-keeper"], operation_id="data_keeper_recheck", summary="[master + Origin + CSRF] Kiểm tra lại dữ liệu ngay (nhẹ, giới hạn tần suất)")
    async def data_recheck(request: Request):
        p = master(request)
        if not origin_ok(request.headers):
            raise HTTPException(403, "origin")
        if p.kind != "service" and not csrf_ok(secret_fn(), request.headers.get("x-csrf-token"), bind=csrf_binding(request)):
            raise HTTPException(403, "csrf")
        return await go("POST", "/v1/data/recheck")
