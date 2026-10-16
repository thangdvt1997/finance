"""Bản tin thị trường do AI tóm tắt: GET /v1/briefing/latest | /list | /{id} -> service `briefing`. CHỈ ĐỌC (whitelist đường dẫn + khoá query).
Việc chạy tay nằm ở endpoint NỘI BỘ của service (không qua gateway/nginx)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .user_routes import _call

READ_OK = re.compile(r"^(latest|list|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$")
QUERY_VAL = {"edition": re.compile(r"^(morning|close)$"), "scope": re.compile(r"^(vn|intl)$"), "limit": re.compile(r"^\d{1,3}$")}


def register_briefing_routes(api: APIRouter) -> None:
    async def briefing_proxy(rest: str, request: Request):
        if not READ_OK.match(rest):
            raise HTTPException(404, "đường dẫn không tồn tại")
        base = os.getenv("BRIEFING_URL", "http://briefing:8000").rstrip("/")
        qs = urllib.parse.urlencode([(k, v) for k, v in request.query_params.multi_items() if k in QUERY_VAL and QUERY_VAL[k].match(v)])
        url = f"{base}/briefing/{rest}" + (f"?{qs}" if qs else "")
        try:
            code, raw = await asyncio.to_thread(_call, "GET", url, None)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"briefing không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "briefing trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})

    api.add_api_route("/briefing/{rest:path}", briefing_proxy, methods=["GET"], tags=["briefing"], operation_id="briefing_proxy_get",
                      summary="Bản tin thị trường do AI tóm tắt (chỉ đọc): mới nhất / danh sách / chi tiết; có trích dẫn tới tin gốc")
