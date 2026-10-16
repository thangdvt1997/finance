"""Proxy CHỈ-ĐỌC (GET) tới service `risk-monitor`: /v1/risk/accounts, /v1/risk/accounts/{id}, /v1/risk/config.
Không chuyển tiếp phương thức khác. Số liệu rủi ro là ƯỚC TÍNH, READ-ONLY."""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .authz import filter_payload, get_principal

ALLOWED = re.compile(r"^(accounts|config|accounts/[A-Za-z0-9_.:\-]{1,64})$")


def _fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def register_riskmon_routes(api: APIRouter) -> None:
    @api.get("/risk/{rest:path}", tags=["risk"],
             summary="Rủi ro tài khoản MT/paper (proxy chỉ-đọc tới risk-monitor): margin, exposure, drawdown, VaR/ES, stress, ngân sách")
    async def risk_proxy(rest: str, request: Request):
        if not ALLOWED.match(rest):
            raise HTTPException(404, "đường dẫn risk không tồn tại")
        base = os.getenv("RISK_MONITOR_URL", "http://risk-monitor:8000").rstrip("/")
        try:
            code, body = await asyncio.to_thread(_fetch, f"{base}/risk/{rest}")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"risk-monitor không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(502, "risk-monitor trả dữ liệu không hợp lệ") from None
        pr = get_principal(request)
        if code == 404 and not pr.is_master and re.match(r"^accounts/[^/]+$", rest):   # tài khoản đã qua kiểm quyền nhưng chưa có dữ liệu EA: 200 rỗng (tránh 404 đỏ ở console)
            return JSONResponse({"empty": True, "account_id": rest.split("/", 1)[1], "read_only": True}, headers={"Cache-Control": "no-store"})
        return JSONResponse(filter_payload(pr, "/v1/risk/" + rest, payload), status_code=code)   # client: chi tai khoan cua minh
