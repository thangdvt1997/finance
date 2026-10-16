"""API nội bộ của reporter cho báo cáo THEO TÀI KHOẢN (chỉ mạng backend; phân quyền do api-gateway đảm nhiệm).
Đường dẫn: /account-reports*, /account-report-schedules*. Không có đường nào chạm tới lệnh giao dịch."""
from __future__ import annotations

from datetime import date
from typing import Callable

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from .account_service import AccountReporter
from .account_store import KIND_RE, MEDIA, PERIOD_RE, clean_schedule, valid_account, valid_name


def build_router(get_rep: Callable[[], AccountReporter]) -> APIRouter:
    r = APIRouter(tags=["account-reports"])

    def _acc(account_id: str) -> str:
        if not valid_account(account_id):
            raise HTTPException(422, "account_id không hợp lệ")
        return account_id

    @r.get("/account-reports", summary="Danh sách báo cáo của một tài khoản")
    async def list_reports(account_id: str = Query(min_length=1, max_length=64), released_only: int = 0):
        rep = get_rep()
        return {"read_only": True, "account_id": _acc(account_id), "items": rep.store.items(account_id, released_only=bool(released_only))}

    @r.post("/account-reports/generate", summary="Sinh báo cáo ngay (master; mặc định chưa phát hành)")
    async def generate(body: dict = Body(...)):  # noqa: B008
        rep = get_rep()
        acc, kind, period = body.get("account_id"), body.get("kind"), body.get("period")
        if not isinstance(acc, str) or not valid_account(acc) or not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
            raise HTTPException(422, "account_id/kind không hợp lệ")
        if period is not None:
            if not isinstance(period, str) or not PERIOD_RE.fullmatch(period):
                raise HTTPException(422, "period phải là YYYY-MM-DD")
            try:
                date.fromisoformat(period)
            except ValueError:
                raise HTTPException(422, "period không hợp lệ") from None
        out = await rep.generate(acc, kind, period, release=bool(body.get("release", False)), force=True)
        if out.get("skipped") == "no_data":
            raise HTTPException(409, "tài khoản chưa có dữ liệu trong kỳ này")
        if out.get("skipped") == "running":
            raise HTTPException(409, "báo cáo này đang được tạo")
        return out

    @r.post("/account-reports/release", summary="Phát hành / thu hồi báo cáo cho khách")
    async def release(body: dict = Body(...)):  # noqa: B008
        rep = get_rep()
        acc, kind, period, rel = body.get("account_id"), body.get("kind"), body.get("period"), body.get("released")
        if (not isinstance(acc, str) or not valid_account(acc) or not isinstance(kind, str) or not KIND_RE.fullmatch(kind)
                or not isinstance(period, str) or not PERIOD_RE.fullmatch(period) or not isinstance(rel, bool)):
            raise HTTPException(422, "account_id/kind/period/released không hợp lệ")
        it = rep.store.set_released(acc, kind, period, rel)
        if it is None:
            raise HTTPException(404, "không tìm thấy báo cáo")
        return it

    @r.get("/account-reports/{account_id}/{period}/{ext}", summary="Tải file báo cáo (html|pdf)")
    async def get_file(account_id: str, period: str, ext: str, kind: str | None = None, released_only: int = 0):
        rep = get_rep()
        if not valid_account(account_id) or not PERIOD_RE.fullmatch(period) or ext not in MEDIA or (kind is not None and not KIND_RE.fullmatch(kind)):
            raise HTTPException(404, "không tìm thấy báo cáo")
        ro = bool(released_only)
        it = rep.store.find(account_id, kind, period) if kind else rep.store.find_period(account_id, period, released_only=ro)
        if not it or (ro and not it.get("released")):
            raise HTTPException(404, "không tìm thấy báo cáo")
        k = it["kind"]
        if not valid_name(account_id, k, period, ext):
            raise HTTPException(404, "không tìm thấy báo cáo")
        p = rep.store.path(account_id, k, period, ext)
        if not p.is_file():
            raise HTTPException(404, "không tìm thấy báo cáo")
        return FileResponse(p, media_type=MEDIA[ext], filename=f"{k}-{period}.pdf" if ext == "pdf" else None,
                            content_disposition_type="attachment" if ext == "pdf" else "inline",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Report-Kind": k})

    @r.delete("/account-reports/{account_id}", summary="Xoá mọi báo cáo của một tài khoản (nội bộ; dọn dữ liệu)")
    async def purge(account_id: str):
        return {"deleted": get_rep().store.purge(_acc(account_id))}

    # ---------------- lịch ----------------
    @r.get("/account-report-schedules", summary="Bảng lịch báo cáo theo tài khoản")
    async def list_schedules():
        return {"schedules": get_rep().schedules.list()}

    @r.put("/account-report-schedules", summary="Thay toàn bộ bảng lịch (đã kiểm tra)")
    async def put_schedules(body: dict = Body(...)):  # noqa: B008
        try:
            return {"schedules": get_rep().schedules.replace(body.get("schedules"))}
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @r.post("/account-report-schedules", summary="Thêm/sửa một lịch")
    async def post_schedule(body: dict = Body(...)):  # noqa: B008
        try:
            return get_rep().schedules.upsert(body)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @r.delete("/account-report-schedules/{schedule_id}", summary="Xoá một lịch")
    async def delete_schedule(schedule_id: str):
        if not get_rep().schedules.delete(schedule_id):
            raise HTTPException(404, "không tìm thấy lịch")
        return {"ok": True}

    return r


__all__ = ["build_router", "clean_schedule"]
