"""Proxy CHỈ-ĐỌC (GET) tới service `vn-market` (chứng khoán Việt Nam cuối ngày): /v1/vn/*.
Whitelist tường minh; không chuyển tiếp phương thức khác. Dữ liệu là cuối ngày (VNDirect finfo), KHÔNG realtime, KHÔNG có đường đặt lệnh."""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

ALLOWED = re.compile(r"^(status|rules|session|overview|indices|heatmap|sectors|movers|limits|breadth|liquidity|foreign|screener|symbols|events|news"
                     r"|index/[A-Za-z0-9]{2,12}|symbol/[A-Za-z0-9:]{2,16})$")
QUERY_KEY = re.compile(r"^[A-Za-z0-9_]{1,24}$")
CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def register_vn_routes(api: APIRouter) -> None:
    @api.get("/vn/{rest:path}", tags=["vn"],
             summary="Chứng khoán Việt Nam cuối ngày (proxy chỉ-đọc tới vn-market): tổng quan, heatmap ngành, top, trần/sàn, độ rộng, khối ngoại, screener, sự kiện, tin")
    async def vn_proxy(rest: str, request: Request):
        if not ALLOWED.match(rest):
            raise HTTPException(404, "đường dẫn vn không tồn tại")
        base = os.getenv("VN_MARKET_URL", "http://vn-market:8000").rstrip("/")
        qs = urllib.parse.urlencode([(k, v) for k, v in request.query_params.multi_items()
                                     if QUERY_KEY.match(k) and len(v) <= 64 and not CTRL.search(v)])
        url = f"{base}/vn/{rest}" + (f"?{qs}" if qs else "")
        try:
            code, body = await asyncio.to_thread(_fetch, url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"vn-market không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(502, "vn-market trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "private, max-age=30"})
