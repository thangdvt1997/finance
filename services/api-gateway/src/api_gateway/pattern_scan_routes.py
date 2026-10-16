"""Proxy CHỈ-ĐỌC (GET) tới service `pattern-scan`: tín hiệu kịch bản Sell gộp theo setup + ảnh + lệnh PAPER + thống kê + thư viện ví dụ.
CHỈ thông tin/mô phỏng (không lệnh). Phân quyền: master/service xem mọi trạng thái; client (và vai trò phụ) bị ép `audience=client`
-> pattern-scan chỉ trả setup đã armed/triggered (không forming/invalid, không lý do huỷ) và chỉ ảnh của sự kiện armed/triggered.
Dữ liệu là tín hiệu CHUNG (không gắn tài khoản người dùng) nên không cần lọc theo tài khoản."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from .authz import get_principal

SYM = r"^[A-Za-z0-9:._\-]{1,32}$"
TF = r"^(M1|M5|M15|M30|H1|H4|D1)$"
KB = r"^KB-[0-9]{1,2}$"


def _hdrs() -> dict:
    try:
        from tscommon.internal_auth import internal_headers
        return internal_headers()
    except Exception:  # noqa: BLE001 - tscommon cũ chưa có internal_auth
        return {}


def _fetch(url: str) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json, image/png", **_hdrs()}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "") if e.headers else ""


def _base() -> str:
    return os.getenv("PATTERN_SCAN_URL", "http://pattern-scan:8000").rstrip("/")


async def _get(path: str, params: dict | None = None) -> tuple[int, bytes, str]:
    qs = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    try:
        return await asyncio.to_thread(_fetch, f"{_base()}{path}{qs}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"pattern-scan không khả dụng: {type(e).__name__}") from None


def _json(code: int, body: bytes) -> JSONResponse:
    try:
        data = json.loads(body)
    except ValueError:
        raise HTTPException(502, "pattern-scan trả dữ liệu không hợp lệ") from None
    if code >= 400:
        raise HTTPException(code if code in (400, 404, 422) else 502, data.get("detail", "lỗi") if isinstance(data, dict) else "lỗi")
    return JSONResponse(data, status_code=code)


def _aud(request: Request) -> str:
    return "master" if get_principal(request).is_master else "client"


def _png(code: int, body: bytes, ctype: str) -> Response:
    if code != 200 or not ctype.startswith("image/png") or not body.startswith(b"\x89PNG"):
        raise HTTPException(404, "không có ảnh")
    return Response(body, media_type="image/png", headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


def register_pattern_scan_routes(api: APIRouter) -> None:
    @api.get("/patterns/live", tags=["patterns"], summary="Setup kịch bản Sell theo trạng thái (hiện tại/lịch sử) + ảnh + lệnh paper (CHỈ thông tin)")
    async def live(request: Request, view: Annotated[str, Query(pattern=r"^(active|history|all)$")] = "active",
                   symbol: Annotated[str | None, Query(pattern=SYM)] = None, tf: Annotated[str | None, Query(pattern=TF)] = None,
                   pattern: Annotated[str | None, Query(pattern=KB)] = None,
                   state: Annotated[str | None, Query(pattern=r"^(forming|armed|triggered|invalid)$")] = None,
                   days: Annotated[int, Query(ge=1, le=90)] = 14, limit: Annotated[int, Query(ge=1, le=200)] = 100):
        code, body, _ = await _get("/scan/setups", {"view": view, "symbol": symbol, "tf": tf, "pattern": pattern, "state": state,
                                                    "days": days, "limit": limit, "audience": _aud(request)})
        return _json(code, body)

    @api.get("/patterns/setup", tags=["patterns"], summary="Chi tiết 1 setup: sự kiện, checklist, mức gợi ý, điểm đánh dấu biểu đồ")
    async def setup(request: Request, setup_id: Annotated[str, Query(min_length=4, max_length=80, pattern=r"^KB-[0-9A-Za-z:_\-]+$")],
                    symbol: Annotated[str, Query(pattern=SYM)], tf: Annotated[str, Query(pattern=TF)]):
        code, body, _ = await _get("/scan/setup", {"setup_id": setup_id, "symbol": symbol, "tf": tf, "audience": _aud(request)})
        return _json(code, body)

    @api.get("/patterns/media/{eid}.png", tags=["patterns"], summary="Ảnh kịch bản (PNG) của 1 sự kiện")
    async def media(request: Request, eid: Annotated[int, Path(ge=1, le=2**62)]):
        return _png(*await _get(f"/scan/media/{eid}.png", {"audience": _aud(request)}))

    @api.get("/patterns/trades", tags=["patterns"], summary="Lệnh PAPER (mô phỏng) của tín hiệu đã kích hoạt")
    async def trades(status: Annotated[str, Query(pattern=r"^(open|closed|all)$")] = "all",
                     pattern: Annotated[str | None, Query(pattern=KB)] = None, symbol: Annotated[str | None, Query(pattern=SYM)] = None,
                     limit: Annotated[int, Query(ge=1, le=500)] = 200):
        code, body, _ = await _get("/scan/trades", {"status": status, "pattern": pattern, "symbol": symbol, "limit": limit})
        return _json(code, body)

    @api.get("/patterns/stats", tags=["patterns"], summary="Thống kê paper (đơn vị R) theo KB/khung/mã + kiểm sổ cái hash-chain")
    async def stats():
        return _json(*(await _get("/scan/stats"))[:2])

    @api.get("/patterns/examples", tags=["patterns"], summary="Thư viện ví dụ kịch bản (mẫu chuẩn + tín hiệu đã kích hoạt)")
    async def examples(limit: Annotated[int, Query(ge=1, le=200)] = 60):
        return _json(*(await _get("/scan/examples", {"limit": limit}))[:2])

    @api.get("/patterns/examples/{xid}.png", tags=["patterns"], summary="Ảnh ví dụ (PNG)")
    async def example_png(xid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_.\-]{1,80}$")]):
        if ".." in xid:
            raise HTTPException(404, "không có ảnh")
        return _png(*await _get(f"/scan/examples/{xid}.png"))

    # ---- Hiện vật backtest: CHỈ master/service (client không nằm trong CLIENT_ALLOW -> 403; kiểm thêm tại route) ----
    def _master_only(request: Request) -> None:
        if not get_principal(request).is_master:
            raise HTTPException(403, "Không có quyền truy cập")

    @api.get("/patterns/backtest/summary", tags=["patterns"], summary="Tóm tắt backtest kịch bản Sell (dev/val/test khoá) + danh sách hiện vật [master]")
    async def bt_summary(request: Request):
        _master_only(request)
        code, body, _ = await _get("/scan/backtest/summary")
        if code == 404:   # backtest đang dừng/ chưa có hiện vật: 200 rỗng thay vì 404 (UI không báo lỗi console)
            return JSONResponse({"available": False, "artifacts": [], "detail": "chưa có hiện vật backtest"})
        return _json(code, body)

    @api.get("/patterns/backtest/{kind}/{name}", tags=["patterns"], summary="Ảnh biểu đồ/ví dụ backtest hoặc CSV tải về [master]")
    async def bt_file(request: Request, kind: Annotated[str, Path(pattern=r"^(charts|examples|download)$")],
                      name: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}$")]):
        _master_only(request)
        code, body, ctype = await _get(f"/scan/backtest/{kind}/{name}")
        if kind == "download":
            if code != 200 or name not in ("ledger_summary.csv", "ledger_test.csv.gz"):
                raise HTTPException(404, "không có tệp")
            return Response(body, media_type=ctype.split(";")[0] if name.endswith(".gz") else ctype,
                            headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
        return _png(code, body, ctype)
