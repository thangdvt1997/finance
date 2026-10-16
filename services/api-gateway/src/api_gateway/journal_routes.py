"""Nhat ky giao dich: /v1/journal/* -> service `journal`.

GET: chi-doc, whitelist duong dan + khoa query. GHI (PUT/DELETE) CHI cho ghi chu/tag thu cong: `.../{account}/notes/{deal|week|day}/{ref}`
(bang journal_notes). KHONG lien quan dat/sua/dong lenh hay tai khoan MT. Phong thu nhieu lop giong /v1/user/*: nginx whitelist + Origin + rate limit,
gateway kiem tra Origin/Sec-Fetch-Site, header `X-CSRF-Token` (lay tu GET /v1/user/csrf, cung bi mat HMAC), Content-Type application/json, body <= 16KB.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .authz import filter_payload, get_principal
from .user_routes import MAX_BODY, _call, csrf_binding, csrf_ok, origin_ok

ACC = r"[A-Za-z0-9_.:\-]{1,64}"
READ_OK = re.compile(rf"^(accounts|{ACC}/(summary|deals|discipline|excursions|review|notes))$")
WRITE_OK = [
    ("PUT", re.compile(rf"^{ACC}/notes/(deal|week|day)/[A-Za-z0-9_\-]{{1,40}}$")),
    ("DELETE", re.compile(rf"^{ACC}/notes/(deal|week|day)/[A-Za-z0-9_\-]{{1,40}}$")),
]
QUERY_KEYS = {"from", "to", "tz", "symbol", "group", "side", "tag", "outcome", "flagged", "sort", "order", "limit", "offset", "week", "kind",
              "revenge_gap_min", "size_up_ratio", "max_trades_day", "max_trades_hour", "daily_loss_limit_pct"}
QUERY_VAL = re.compile(r"^[A-Za-z0-9_:.+\-/]{1,64}$")


def register_journal_routes(api: APIRouter, secret_fn) -> None:
    async def journal_proxy(rest: str, request: Request):
        method = request.method
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
        if method == "PUT":
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
        base = os.getenv("JOURNAL_URL", "http://journal:8000").rstrip("/")
        qs = urllib.parse.urlencode([(k, v) for k, v in request.query_params.multi_items() if k in QUERY_KEYS and QUERY_VAL.match(v)])
        url = f"{base}/journal/{rest}" + (f"?{qs}" if qs else "")
        try:
            code, raw = await asyncio.to_thread(_call, method, url, body)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"journal không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "journal trả dữ liệu không hợp lệ") from None
        pr = get_principal(request)
        if code == 404 and method == "GET" and not pr.is_master and re.match(r"^[^/]+/summary$", rest):   # chưa có dữ liệu: 200 rỗng
            return JSONResponse({"empty": True, "account_id": rest.split("/", 1)[0], "read_only": True}, headers={"Cache-Control": "no-store"})
        payload = filter_payload(pr, "/v1/journal/" + rest, payload)   # client: chi tai khoan cua minh
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})

    for _m in ("GET", "PUT", "DELETE"):
        api.add_api_route("/journal/{rest:path}", journal_proxy, methods=[_m], tags=["journal"], operation_id=f"journal_proxy_{_m.lower()}",
                          summary="Nhật ký giao dịch (proxy whitelist tới journal): thống kê/deal/kỷ luật/MAE-MFE/review; ghi chỉ cho tag/ghi chú (CSRF)")
