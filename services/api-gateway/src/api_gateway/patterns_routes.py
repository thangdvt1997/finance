"""Proxy CHỈ-ĐỌC (GET) tới service `pattern-engine`: /v1/patterns, /v1/patterns/spec.
Tín hiệu kịch bản Sell chỉ là THÔNG TIN (không lệnh). Phân quyền: master/service xem MỌI trạng thái (forming|armed|triggered|invalid);
client (và vai trò phụ) chỉ thấy `armed|triggered` (bỏ nhiễu forming/invalid + lý do hủy nội bộ)."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .authz import get_principal

ALL_STATES = ("forming", "armed", "triggered", "invalid")
CLIENT_STATES = ("armed", "triggered")
SYM = r"^[A-Za-z0-9:._\-]{1,32}$"


def _fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _base() -> str:
    return os.getenv("PATTERN_ENGINE_URL", "http://pattern-engine:8000").rstrip("/")


async def _get(path: str, params: dict | None = None):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    try:
        code, body = await asyncio.to_thread(_fetch, f"{_base()}{path}{qs}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"pattern-engine không khả dụng: {type(e).__name__}") from None
    try:
        return code, json.loads(body)
    except ValueError:
        raise HTTPException(502, "pattern-engine trả dữ liệu không hợp lệ") from None


def register_patterns_routes(api: APIRouter) -> None:
    @api.get("/patterns", tags=["patterns"],
             summary="Tín hiệu kịch bản Sell (KB-1..KB-4) trên nến đã đóng: trạng thái, điểm, mức gợi ý, checklist (CHỈ thông tin)")
    async def patterns(request: Request,
                       symbol: Annotated[str | None, Query(pattern=SYM)] = None,
                       tf: Annotated[str | None, Query(pattern=r"^(M1|M5|M15|M30|H1|H4|D1)$")] = None,
                       pattern: Annotated[str | None, Query(pattern=r"^KB-[0-9]{1,2}$")] = None,
                       state: Annotated[str | None, Query(description="forming|armed|triggered|invalid (phẩy). Client chỉ armed|triggered")] = None,
                       since: Annotated[str | None, Query(description="ISO-8601; chỉ tín hiệu có nến >= since", max_length=40)] = None,
                       limit: Annotated[int, Query(ge=1, le=500)] = 100):
        p = get_principal(request)
        want = [s for s in (state or "").split(",") if s in ALL_STATES]
        allowed = ALL_STATES if p.is_master else CLIENT_STATES
        states = [s for s in (want or allowed) if s in allowed]
        if not states:
            return {"items": [], "disclaimer": "Tín hiệu kỹ thuật chỉ để tham khảo/paper, không phải khuyến nghị đầu tư."}
        params = {"state": ",".join(states), "limit": limit}
        for k, v in (("symbol", symbol), ("tf", tf), ("pattern", pattern), ("since", since)):
            if v:
                params[k] = v
        code, data = await _get("/patterns", params)
        if code == 200 and not p.is_master:
            for it in data.get("items", []):
                it.pop("reason", None)
                it.pop("id", None)
        return JSONResponse(data, status_code=code)

    @api.get("/patterns/spec", tags=["patterns"], summary="Định nghĩa kịch bản Sell: tên, các bước (checklist), điều kiện huỷ, tham số")
    async def patterns_spec(request: Request):
        p = get_principal(request)
        code, data = await _get("/patterns/spec")
        if code == 200 and not p.is_master:
            for it in data.get("items", []):
                it.pop("params", None)           # tham số tinh chỉnh chỉ cho master
        return JSONResponse(data, status_code=code)
