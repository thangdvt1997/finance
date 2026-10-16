"""Proxy CHỈ-ĐỌC (GET) tới service `paper-trader` (giao dịch MÔ PHỎNG): /v1/paper/...
Chỉ cho phép các đường dẫn đã liệt kê; KHÔNG chuyển tiếp POST/lệnh quản trị (kill-switch reset/halt chỉ gọi trực tiếp paper-trader).
Mọi dữ liệu là MÔ PHỎNG, không phải tiền thật."""
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

ALLOWED = re.compile(r"^(overview|strategies|events|status|verify|governance|accounts|accounts/[A-Za-z0-9_.\-]{1,64}"
                     r"(/(equity|positions|orders|fills|events|kill-switch|stats|performance|tca|drift|card|verify|config-versions))?)$")


def _fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (URL từ cấu hình nội bộ, chỉ GET)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def register_paper_routes(api: APIRouter) -> None:
    """Gắn route vào router /v1 đã có auth (gọi trong create_app trước include_router)."""

    @api.get("/paper/{rest:path}", summary="Giao dịch MÔ PHỎNG (proxy chỉ-đọc tới paper-trader): tài khoản, equity, vị thế, lệnh, kill-switch, thống kê",
             tags=["paper"])
    async def paper_proxy(rest: str, request: Request):
        if not ALLOWED.match(rest):
            raise HTTPException(404, "đường dẫn paper không tồn tại")
        base = os.getenv("PAPER_TRADER_URL", "http://paper-trader:8000").rstrip("/")
        qs = urllib.parse.urlencode([(k, v) for k, v in request.query_params.multi_items() if re.fullmatch(r"[A-Za-z_]{1,20}", k) and len(v) <= 64])
        url = f"{base}/paper/{rest}" if rest != "status" else f"{base}/status"
        if qs:
            url += "?" + qs
        try:
            code, body = await asyncio.to_thread(_fetch, url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"paper-trader không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(502, "paper-trader trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code)
