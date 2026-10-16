"""Bang xep hang / thanh tich chuyen gia: /v1/experts/{leaderboard,consensus,feed,methodology,chain/verify,{id}/track-record} -> service `track-record`.

CHI GET, chi-doc. Du lieu chuyen gia la CONG KHAI (khong chua du lieu tai khoan): master + client deu doc duoc (authz.CLIENT_ALLOW);
`chain/verify` chi master/service (kiem tra o day, lop 2). Cac route KHONG nhan account_id; moi tham so query la whitelist + validate chat
(sai -> 422), khoa la bi bo, KHONG chuyen tiep header nguoi dung xuong service. Hop dong: services/track-record/CONTRACT.md.
Phai dang ky TRUOC moi route /experts/{id} (hien chua co); middleware hide_sources van scrub phan hoi (nhan thuc the trung tinh, khong ten website).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .authz import get_principal
from .user_routes import _call

ENTITY_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,96}$")
SCOPE_RE = re.compile(r"^(all|forex|metal|index|commodity|crypto|stock_us|stock_vn|etf|bond|sym:[A-Za-z0-9_.:\-]{1,32})$")
KIND_RE = re.compile(r"^(analyst|central_bank|media|positioning|signal_provider|other)$")
LANG_RE = re.compile(r"^(vi|en|other)$")
SYMBOL_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,32}$")


def _int(lo: int, hi: int):
    def f(v: str) -> str:
        if not re.fullmatch(r"\d{1,4}", v) or not lo <= int(v) <= hi:
            raise ValueError
        return str(int(v))
    return f


def _rx(rx: re.Pattern):
    def f(v: str) -> str:
        if not rx.fullmatch(v):
            raise ValueError
        return v
    return f


def _iso(v: str) -> str:
    if len(v) > 40:
        raise ValueError
    datetime.fromisoformat(v.replace("Z", "+00:00"))
    return v


def _bool(v: str) -> str:
    if v.lower() not in ("true", "false", "1", "0"):
        raise ValueError
    return "true" if v.lower() in ("true", "1") else "false"


_H = _rx(re.compile(r"1D|1W|1M"))
# khoa query cho phep theo tung duong (khoa khac -> bi bo, gom ca account_id)
QUERY_SPEC: dict[str, dict] = {
    "leaderboard": {"horizon": _H, "scope": _rx(SCOPE_RE), "kind": _rx(KIND_RE), "lang": _rx(LANG_RE), "min_n": _int(1, 1000),
                    "include_insufficient": _bool, "limit": _int(1, 200)},
    "consensus": {"window_days": _int(1, 90), "scope": _rx(SCOPE_RE), "min_experts": _int(1, 100)},
    "feed": {"limit": _int(1, 200), "symbol": _rx(SYMBOL_RE), "direction": _rx(re.compile(r"bullish|bearish")), "entity_id": _rx(ENTITY_RE), "before": _iso},
    "methodology": {},
    "chain/verify": {},
    "track-record": {"horizon": _H, "scope": _rx(SCOPE_RE)},
}


def build_query(kind: str, request: Request) -> str:
    spec = QUERY_SPEC[kind]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for k, v in request.query_params.multi_items():
        if k not in spec:
            continue                       # khoa la (account_id, token...) -> bi bo, khong bao gio toi service
        if k in seen:
            raise HTTPException(422, f"tham số {k} chỉ được truyền một lần")
        seen.add(k)
        try:
            out.append((k, spec[k](v)))
        except ValueError:
            raise HTTPException(422, f"tham số {k} không hợp lệ") from None
    return urllib.parse.urlencode(out)


def register_track_routes(api: APIRouter) -> None:
    async def proxy(kind: str, path: str, request: Request):
        qs = build_query(kind, request)
        base = os.getenv("TRACKREC_URL", "http://track-record:8000").rstrip("/")
        url = f"{base}/track/{path}" + (f"?{qs}" if qs else "")
        try:
            code, raw = await asyncio.to_thread(_call, "GET", url, None)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, f"track-record không khả dụng: {type(e).__name__}", headers={"Retry-After": "15"}) from None
        if code >= 500:
            raise HTTPException(503, "track-record không khả dụng", headers={"Retry-After": "15"})
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(503, "track-record trả dữ liệu không hợp lệ", headers={"Retry-After": "15"}) from None
        return JSONResponse(payload, status_code=code, headers={"Cache-Control": "no-store"})

    async def leaderboard(request: Request):
        return await proxy("leaderboard", "leaderboard", request)

    async def consensus(request: Request):
        return await proxy("consensus", "consensus", request)

    async def feed(request: Request):
        return await proxy("feed", "feed", request)

    async def methodology(request: Request):
        return await proxy("methodology", "methodology", request)

    async def chain_verify(request: Request):
        if not get_principal(request).is_master:      # lop 2 (lop 1 = CLIENT_ALLOW khong co duong nay): chi master/service
            raise HTTPException(403, "Không có quyền truy cập")
        return await proxy("chain/verify", "chain/verify", request)

    async def track_record(entity_id: str, request: Request):
        if not ENTITY_RE.match(entity_id) or ".." in entity_id:
            raise HTTPException(422, "entity_id không hợp lệ")
        return await proxy("track-record", f"experts/{urllib.parse.quote(entity_id, safe='')}/track-record", request)

    # THU TU: duong tinh truoc, duong dong {entity_id} sau (va truoc bat ky /experts/{id} nao khac)
    for p, fn, summ in (
        ("/experts/leaderboard", leaderboard, "Bảng xếp hạng chuyên gia (thống kê có kiểm định, n, KTC; chưa đủ mẫu không xếp hạng)"),
        ("/experts/consensus", consensus, "Đồng thuận chuyên gia có trọng số theo thành tích (chỉ tham khảo)"),
        ("/experts/feed", feed, "Dòng quan điểm chuyên gia mới nhất (nhãn trung lập)"),
        ("/experts/methodology", methodology, "Phương pháp chấm điểm chuyên gia"),
        ("/experts/chain/verify", chain_verify, "Kiểm tra chuỗi băm bất biến (chỉ master/service)"),
        ("/experts/{entity_id}/track-record", track_record, "Hồ sơ thành tích một chuyên gia"),
    ):
        api.add_api_route(p, fn, methods=["GET"], tags=["track-record"], summary=summ,
                          operation_id="track_" + re.sub(r"\W+", "_", p).strip("_") + "_get")
