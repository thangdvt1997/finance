"""Proxy tới service `ai-trading` (tab AI Trading): /v1/ai-trading/*. CHỈ đọc + paper, KHÔNG có đường đặt lệnh.
Phân quyền: master/service xem tất cả; client (và vai trò phụ) CHỈ overview/strategies/strategies/{id}/arena (bản rút gọn: ép audience=client ->
không ảnh/ví dụ). lab, ledger.csv, media, jobs = chỉ master (không nằm trong CLIENT_ALLOW -> 403, kiểm thêm tại route). Dữ liệu là chung, không gắn
tài khoản -> không có tham số id tài khoản; id chiến lược/job được kiểm regex + tra registry (404 đồng nhất), job id là uuid ngẫu nhiên."""
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

from .authz import FORBIDDEN, get_principal
from .user_routes import MAX_BODY, csrf_binding, csrf_ok, origin_ok

SID = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,47}$"
MAX_CSV = 8 * 1024 * 1024
SYMQ = r"^[A-Za-z0-9][A-Za-z0-9:_.\-]{0,23}$"
MAX_SC_BODY = 6 * 1024 * 1024        # YAML + tối đa 5 ảnh x 700KB (base64)
SC_SID = r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$"


def _hdrs() -> dict:
    try:
        from tscommon.internal_auth import internal_headers
        return internal_headers()
    except Exception:  # noqa: BLE001
        return {}


def _call(method: str, url: str, body: bytes | None = None) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Accept": "application/json, image/png, text/csv", **_hdrs(), **({"Content-Type": "application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (URL nội bộ từ cấu hình; đường dẫn đã whitelist)
            return r.status, r.read(MAX_CSV + 1), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_CSV + 1), e.headers.get("Content-Type", "") if e.headers else ""


def register_ai_trading_routes(api: APIRouter, secret_fn) -> None:
    def base() -> str:
        return os.getenv("AI_TRADING_URL", "http://ai-trading:8000").rstrip("/")

    async def up(method: str, path: str, params: dict | None = None, body: bytes | None = None) -> tuple[int, bytes, str]:
        qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        try:
            return await asyncio.to_thread(_call, method, f"{base()}{path}" + (f"?{qs}" if qs else ""), body)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"ai-trading không khả dụng: {type(e).__name__}") from None

    def js(code: int, raw: bytes, ok=(200, 202)) -> JSONResponse:
        try:
            data = json.loads(raw)
        except ValueError:
            raise HTTPException(502, "ai-trading trả dữ liệu không hợp lệ") from None
        if code not in ok:
            raise HTTPException(code if code in (404, 409, 422, 429, 503) else 502, data.get("detail", "lỗi") if isinstance(data, dict) else "lỗi")
        return JSONResponse(data, status_code=code, headers={"Cache-Control": "private, no-store"})

    def aud(request: Request) -> str:
        return "master" if get_principal(request).is_master else "client"

    def master_only(request: Request) -> None:
        if not get_principal(request).is_master:
            raise HTTPException(403, FORBIDDEN)

    @api.get("/ai-trading/overview", tags=["ai-trading"], summary="Tổng quan AI Trading: thẻ chiến lược + cảnh báo trung thực + arena paper")
    async def overview(request: Request):
        return js(*(await up("GET", "/ai/overview", {"audience": aud(request)}))[:2])

    @api.get("/ai-trading/strategies", tags=["ai-trading"], summary="Danh sách thẻ chiến lược/mô hình")
    async def strategies(request: Request):
        return js(*(await up("GET", "/ai/strategies", {"audience": aud(request)}))[:2])

    @api.get("/ai-trading/strategies/{sid}", tags=["ai-trading"], summary="Chi tiết chiến lược (client: rút gọn, không ảnh/ví dụ)")
    async def strategy(request: Request, sid: Annotated[str, Path(pattern=SID)]):
        return js(*(await up("GET", f"/ai/strategies/{urllib.parse.quote(sid, safe='')}", {"audience": aud(request)}))[:2])

    @api.get("/ai-trading/arena", tags=["ai-trading"], summary="Bảng xếp hạng paper")
    async def arena():
        return js(*(await up("GET", "/ai/arena"))[:2])

    @api.get("/ai-trading/lab", tags=["ai-trading"], summary="Lab: thí nghiệm đã chạy + backlog ý tưởng [master]")
    async def lab(request: Request):
        master_only(request)
        return js(*(await up("GET", "/ai/lab"))[:2])

    @api.get("/ai-trading/media/{kind}/{name}", tags=["ai-trading"], summary="Ảnh biểu đồ/ví dụ backtest [master]")
    async def media(request: Request, kind: Annotated[str, Path(pattern=r"^(charts|examples)$")],
                    name: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}$")]):
        master_only(request)
        code, body, ctype = await up("GET", f"/ai/media/{kind}/{urllib.parse.quote(name, safe='')}")
        if code != 200 or not ctype.startswith("image/png") or not body.startswith(b"\x89PNG"):
            raise HTTPException(404, "không có ảnh")
        return Response(body, media_type="image/png", headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})

    @api.get("/ai-trading/ledger.csv", tags=["ai-trading"], summary="Tải sổ lệnh CSV của 1 chiến lược [master]")
    async def ledger(request: Request, strategy: Annotated[str, Query(pattern=SID)],
                     source: Annotated[str, Query(pattern=r"^(backtest_test|backtest_dev|paper)$")] = "backtest_test"):
        master_only(request)
        code, body, _ = await up("GET", "/ai/ledger.csv", {"strategy": strategy, "source": source})
        if code == 404:
            raise HTTPException(404, "không có sổ lệnh")
        if code != 200 or len(body) > MAX_CSV:
            raise HTTPException(502, "ai-trading trả dữ liệu không hợp lệ")
        return Response(body, media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="ledger-{strategy}-{source}.csv"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    # ---- ghi (chỉ master + Origin + CSRF; body JSON có giới hạn) ----
    async def write_body(request: Request, limit: int) -> dict:
        p = get_principal(request)
        if not p.is_master:
            raise HTTPException(403, FORBIDDEN)
        if not origin_ok(request.headers):
            raise HTTPException(403, "origin")
        if p.kind != "service" and not csrf_ok(secret_fn(), request.headers.get("x-csrf-token"), bind=csrf_binding(request)):
            raise HTTPException(403, "csrf")
        try:
            if int(request.headers.get("content-length", "0")) > limit:
                raise HTTPException(413, "body quá lớn")
        except ValueError:
            raise HTTPException(400, "content-length") from None
        raw = await request.body()
        if len(raw) > limit:
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

    @api.get("/ai-trading/guardrail", tags=["ai-trading"], summary="[master] Guardrail rủi ro của sổ paper: kill-switch, lỗ ngày, cửa sổ tin, cỡ vị thế, hash-chain")
    async def guardrail(request: Request):
        master_only(request)
        return js(*(await up("GET", "/ai/guardrail"))[:2])

    @api.get("/ai-trading/ledger/verify", tags=["ai-trading"], summary="[master] Xác minh hash-chain sổ lệnh paper (có neo ngoài DB)")
    async def ledger_verify(request: Request):
        master_only(request)
        return js(*(await up("GET", "/ai/ledger/verify"))[:2])

    @api.post("/ai-trading/guardrail/killswitch", tags=["ai-trading"], summary="[master + Origin + CSRF] Bật/tắt kill-switch của sổ paper")
    async def killswitch(request: Request):
        d = await write_body(request, MAX_BODY)
        body = {k: d[k] for k in ("on", "reason") if k in d}
        return js(*(await up("POST", "/ai/guardrail/killswitch", body=json.dumps(body).encode()))[:2])

    @api.post("/ai-trading/jobs", tags=["ai-trading"], status_code=202, summary="Master: tạo job nền cho kịch bản người dùng nạp (type + strategy_id [+ confirm])")
    async def create_job(request: Request):
        d = await write_body(request, MAX_BODY)
        body = {k: d[k] for k in ("type", "strategy_id", "confirm") if k in d}
        return js(*(await up("POST", "/ai/jobs", body=json.dumps(body).encode()))[:2])

    @api.post("/ai-trading/scenarios", tags=["ai-trading"], status_code=201, summary="Master: nạp Kịch bản mới (YAML + ảnh mẫu base64, tối đa 5 ảnh x 700KB)")
    async def create_scenario(request: Request):
        d = await write_body(request, MAX_SC_BODY)
        body = {k: d[k] for k in ("yaml", "images") if k in d}
        return js(*(await up("POST", "/ai/scenarios", body=json.dumps(body).encode()))[:2], ok=(200, 201))

    @api.post("/ai-trading/scenarios/{sid}/jobs", tags=["ai-trading"], status_code=202,
              summary="Master: chạy job nền (detector_test | backtest | final_test cần confirm = id kịch bản)")
    async def create_scenario_job(request: Request, sid: Annotated[str, Path(pattern=SC_SID)]):
        d = await write_body(request, MAX_BODY)
        body = {k: d[k] for k in ("type", "confirm") if k in d}
        return js(*(await up("POST", f"/ai/scenarios/{sid}/jobs", body=json.dumps(body).encode()))[:2])

    @api.get("/ai-trading/scenarios/{sid}/jobs", tags=["ai-trading"], summary="Master: lịch sử job của kịch bản")
    async def scenario_jobs(request: Request, sid: Annotated[str, Path(pattern=SC_SID)]):
        master_only(request)
        return js(*(await up("GET", f"/ai/scenarios/{sid}/jobs"))[:2])

    @api.get("/ai-trading/scenarios/{sid}/images/{name}", tags=["ai-trading"], summary="Master: ảnh mẫu của kịch bản")
    async def scenario_image(request: Request, sid: Annotated[str, Path(pattern=SC_SID)],
                             name: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,58}\.(png|jpg|jpeg|webp)$")]):
        master_only(request)
        code, body, ctype = await up("GET", f"/ai/scenarios/{sid}/images/{urllib.parse.quote(name, safe='')}")
        okk = (ctype.startswith("image/png") and body.startswith(b"\x89PNG")) or (ctype.startswith("image/jpeg") and body.startswith(b"\xff\xd8\xff")) \
            or (ctype.startswith("image/webp") and body[8:12] == b"WEBP")
        if code != 200 or not okk:
            raise HTTPException(404, "không có ảnh")
        return Response(body, media_type=ctype.split(";")[0], headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                                                                       "Content-Security-Policy": "default-src 'none'; sandbox"})

    @api.get("/ai-trading/jobs/{jid}", tags=["ai-trading"], summary="Master: trạng thái job")
    async def get_job(request: Request, jid: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]):
        master_only(request)
        return js(*(await up("GET", f"/ai/jobs/{jid}"))[:2])

    # ---- C2: regime + đồng thuận (client: bản rút gọn) + AI analyst (chỉ master; LLM cục bộ qua service briefing) ----
    @api.get("/ai-trading/regime", tags=["ai-trading"], summary="Regime thị trường (HMM/k-means) + báo cáo trung thực; client: rút gọn")
    async def regime(request: Request, symbol: Annotated[str | None, Query(pattern=SYMQ)] = None):
        return js(*(await up("GET", "/ai/regime", {"audience": aud(request), "symbol": symbol}))[:2])

    @api.get("/ai-trading/consensus", tags=["ai-trading"], summary="Đồng thuận chuyên gia + độ tin cậy (client: rút gọn)")
    async def consensus(request: Request, symbol: Annotated[str | None, Query(pattern=SYMQ)] = None):
        return js(*(await up("GET", "/ai/consensus", {"audience": aud(request), "symbol": symbol}))[:2])

    @api.get("/ai-trading/analyst", tags=["ai-trading"], summary="[master] AI analyst: bối cảnh + giải thích kịch bản (AI tạo, không phải lời khuyên)")
    async def analyst(request: Request, symbol: Annotated[str, Query(pattern=SYMQ)]):
        master_only(request)
        base_b = os.getenv("BRIEFING_URL", "http://briefing:8000").rstrip("/")
        try:
            code, raw, _ = await asyncio.to_thread(_call, "GET", f"{base_b}/analyst?" + urllib.parse.urlencode({"symbol": symbol}), None)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"analyst không khả dụng: {type(e).__name__}") from None
        return js(code, raw, ok=(200,))

    from .class_routes import register_class_routes   # AI Training Class (master + vai expert): /ai-trading/class/*
    register_class_routes(api, secret_fn)
