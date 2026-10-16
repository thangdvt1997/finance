"""POST /internal/notify — risk-monitor nhờ gửi push CHUNG cho khách đã opt-in khi luật sát/vi phạm (FLEET_MGMT mục 3-4).
Chỉ mạng backend/ops; xác thực Bearer FLEET_INTERNAL_TOKEN (so sánh hằng thời gian); thiếu token cấu hình -> 503.
Nội dung push là mẫu chung có sẵn (PushService.notify): không lộ số liệu/tên tài khoản/nguồn. Throttle theo người dùng nằm trong PushService."""
from __future__ import annotations

import hmac
import os
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

router = APIRouter()


class NotifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str
    kind: str = "rule"


@router.post("/internal/notify", tags=["internal"], include_in_schema=False)
async def internal_notify(body: NotifyIn, request: Request):
    token = os.getenv("FLEET_INTERNAL_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "chưa cấu hình FLEET_INTERNAL_TOKEN")
    auth = request.headers.get("authorization", "")
    given = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(401, "không được phép")
    if not UUID_RE.match(body.owner):
        raise HTTPException(422, "owner phải là UUID")
    if body.kind != "rule":
        raise HTTPException(422, "kind không hỗ trợ")
    push = request.app.state.push
    return {"sent": await push.notify(body.owner) if push is not None else 0}
