"""Proxy CHỈ-ĐỌC (GET) tới service `reporter`: danh sách báo cáo + tải file HTML/PDF.
KHÔNG chuyển tiếp /generate (chỉ gọi nội bộ trực tiếp reporter). Tên file kiểm bằng regex chặt (chống path traversal)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

KIND_RE = re.compile(r"^(daily|weekly)$")
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(html|pdf)$")
MEDIA = {"html": "text/html; charset=utf-8", "pdf": "application/pdf"}
MAX_BYTES = 20 * 1024 * 1024


def _fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return r.status, r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_BYTES + 1)


def register_reports_routes(api: APIRouter) -> None:
    """Gắn route vào router /v1 đã có auth."""

    def base() -> str:
        return os.getenv("REPORTER_URL", "http://reporter:8000").rstrip("/")

    @api.get("/reports", summary="Danh sách báo cáo ngày/tuần (proxy chỉ-đọc tới reporter)", tags=["reports"])
    async def reports_list():
        try:
            code, body = await asyncio.to_thread(_fetch, f"{base()}/reports")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"reporter không khả dụng: {type(e).__name__}") from None
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(502, "reporter trả dữ liệu không hợp lệ") from None
        return JSONResponse(payload, status_code=code)

    @api.get("/reports/{kind}/{name}", summary="Tải báo cáo: {YYYY-MM-DD}.html hoặc .pdf", tags=["reports"])
    async def report_file(kind: str, name: str):
        m = NAME_RE.fullmatch(name)
        if not KIND_RE.fullmatch(kind) or not m:
            raise HTTPException(404, "không tìm thấy báo cáo")
        period, ext = m.groups()
        try:
            code, body = await asyncio.to_thread(_fetch, f"{base()}/reports/{kind}/{period}.{ext}")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"reporter không khả dụng: {type(e).__name__}") from None
        if code == 404:
            raise HTTPException(404, "không tìm thấy báo cáo")
        if code != 200 or len(body) > MAX_BYTES:
            raise HTTPException(502, "reporter trả dữ liệu không hợp lệ")
        disp = f'attachment; filename="{kind}-{period}.pdf"' if ext == "pdf" else "inline"
        return Response(body, media_type=MEDIA[ext], headers={"Content-Disposition": disp, "Cache-Control": "no-store",
                                                             "X-Content-Type-Options": "nosniff"})
