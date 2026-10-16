"""Phạm vi chủ sở hữu cho API nội bộ của alert-rules (docs/CLIENT_PLATFORM.md, docs/AUTH.md).

Danh tính KHÔNG do alert-rules xác thực: api-gateway (đã tin header nginx/auth) gắn `X-Owner-Role/X-Owner-User/X-Owner-Accounts`
khi gọi xuống (gateway luôn dựng header này từ đầu, không chuyển tiếp từ client). alert-rules chỉ nằm trong mạng nội bộ (không publish cổng).
  - không có header phạm vi nào  -> service/master (thấy mọi quy tắc, không có user_id: không dùng được Web Push)
  - X-Owner-Role=master + user    -> master (thấy mọi quy tắc); user_id dùng cho Web Push của chính họ
  - X-Owner-Role=client + user    -> client: CHỈ quy tắc/sự kiện/đăng ký push của user đó; điều kiện tài khoản chỉ trên tài khoản của họ
  - header lạ/thiếu user cho client -> 403 (đóng)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from .models import AccountCond, RuleIn

USER_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
ACC_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
CLIENT_CHANNELS = ("app", "push")        # client KHÔNG được dùng kênh toàn cục (ntfy/telegram/log): sẽ lộ cho người vận hành/người khác
MIN_CLIENT_COOLDOWN_MIN = 5
FORBIDDEN = "Không có quyền truy cập"


@dataclass(frozen=True)
class Scope:
    role: str = "service"              # service | master | client
    user_id: str | None = None
    accounts: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_client(self) -> bool:
        return self.role == "client"

    @property
    def owner(self) -> str | None:
        """Giá trị lọc theo chủ sở hữu: client -> user_id (bắt buộc); master/service -> None (không lọc)."""
        return self.user_id if self.is_client else None


def scope_from_headers(headers) -> Scope:
    role, user, accs = headers.get("x-owner-role"), headers.get("x-owner-user"), headers.get("x-owner-accounts")
    if not any((role, user, accs)):
        return Scope()
    if user is not None and not USER_RE.match(user):
        raise HTTPException(403, FORBIDDEN)
    if role == "master":
        return Scope("master", user)
    if role == "client" and user:
        return Scope("client", user, frozenset(a for a in (accs or "").split(",") if ACC_RE.match(a)))
    raise HTTPException(403, FORBIDDEN)


def scope_dep(request: Request) -> Scope:
    return scope_from_headers(request.headers)


def require_user(sc: Scope) -> str:
    if not sc.user_id:
        raise HTTPException(403, FORBIDDEN)
    return sc.user_id


def clientize(rule: RuleIn, accounts: frozenset[str]) -> RuleIn:
    """Ép quy tắc của client vào phạm vi an toàn. Ném HTTPException(422) khi vi phạm.
    - điều kiện `account`: BẮT BUỘC gắn 1 tài khoản thuộc tập của họ (không có -> nếu họ chỉ có 1 tài khoản thì tự điền, ngược lại 422);
    - kênh chỉ `app`/`push` (kênh khác bị bỏ; rỗng -> app); cooldown tối thiểu 5 phút."""
    conds = []
    for c in rule.conditions:
        if isinstance(c, AccountCond):
            acc = c.account_id
            if acc is None:
                if len(accounts) != 1:
                    raise HTTPException(422, "điều kiện tài khoản cần chọn một tài khoản")
                acc = next(iter(accounts))
            if acc not in accounts:
                raise HTTPException(422, "tài khoản không hợp lệ")
            c = c.model_copy(update={"account_id": acc})
        conds.append(c)
    chans = [x for x in rule.channels if x in CLIENT_CHANNELS] or ["app"]
    return rule.model_copy(update={"conditions": conds, "channels": chans, "cooldown_min": max(rule.cooldown_min, MIN_CLIENT_COOLDOWN_MIN)})


def account_of(spec: dict) -> str | None:
    """Tài khoản mà quy tắc gắn với (điều kiện `account` đầu tiên có account_id)."""
    for c in spec.get("conditions") or []:
        if c.get("type") == "account" and c.get("account_id"):
            return c["account_id"]
    return None
