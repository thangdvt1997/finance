"""Web Push tự host (VAPID, miễn phí): đăng ký thiết bị theo chủ sở hữu + gửi thông báo khi cảnh báo của chính họ kích hoạt.

An toàn:
  - endpoint/khoá đăng ký lưu MÃ HOÁ (Fernet, PUSH_ENC_KEY); DB chỉ cho role ts_userconf; chỉ endpoint_hash dùng để tra/huỷ.
  - endpoint chỉ nhận https tới dịch vụ push đã biết (allowlist hậu tố; chống SSRF: máy chủ sẽ POST tới URL này).
  - nội dung push CHUNG (tiêu đề + liên kết), không số dư/tên tài khoản/tên nguồn dữ liệu.
  - giới hạn tần suất theo người dùng; 404/410 từ dịch vụ push -> xoá đăng ký; lỗi liên tiếp -> xoá.
  - VAPID khoá riêng + PUSH_ENC_KEY chỉ ở biến môi trường (infra/.env), KHÔNG log.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from prometheus_client import Counter

log = logging.getLogger("alert_rules.webpush")

SENT = Counter("alert_rules_push_total", "Web Push gửi", ["result"])        # ok | gone | error | throttled
MAX_SUBS_PER_USER = 5
MAX_ENDPOINT_LEN = 700
MAX_FAILS = 5
DEFAULT_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "push.services.mozilla.com", "push.apple.com",
                 "notify.windows.com", "push.microsoft.com")
PUSH_URL = "/c/#/thong-bao"
PUSH_TITLE = "Cảnh báo mới"
PUSH_BODY = "Một cảnh báo của bạn vừa kích hoạt. Mở ứng dụng để xem."


class PushError(ValueError):
    """Dữ liệu đăng ký không hợp lệ (-> 422)."""


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    h = host.lower().rstrip(".")
    return any(h == a or h.endswith("." + a) for a in allowed)


def validate_subscription(endpoint: str, p256dh: str, auth: str, allowed: tuple[str, ...]) -> None:
    if not isinstance(endpoint, str) or len(endpoint) > MAX_ENDPOINT_LEN:
        raise PushError("endpoint không hợp lệ")
    u = urlsplit(endpoint)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
        raise PushError("endpoint phải là https của dịch vụ push")
    if u.port not in (None, 443) or re.fullmatch(r"[0-9.]+|\[.*\]", u.netloc.split("@")[-1].split(":")[0]):
        raise PushError("endpoint không hợp lệ")
    if not host_allowed(u.hostname, allowed):
        raise PushError("dịch vụ push không được hỗ trợ")
    try:
        if len(b64u_decode(p256dh)) != 65 or len(b64u_decode(auth)) != 16:
            raise ValueError
    except Exception:  # noqa: BLE001
        raise PushError("khoá đăng ký không hợp lệ") from None


def generate_keys() -> dict[str, str]:
    """Sinh cặp VAPID (P-256) + khoá mã hoá đăng ký. Chỉ in ra stdout cho script nạp vào .env (KHÔNG chạy tay trên màn hình chia sẻ)."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    k = ec.generate_private_key(ec.SECP256R1())
    raw = k.private_numbers().private_value.to_bytes(32, "big")
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731
    return {"VAPID_PRIVATE_KEY": b(raw), "VAPID_PUBLIC_KEY": b(pub), "PUSH_ENC_KEY": Fernet.generate_key().decode()}


def _default_send(sub: dict, data: str, vapid_private: str, subject: str, ttl: int) -> None:
    from py_vapid import Vapid
    from pywebpush import webpush

    webpush(subscription_info=sub, data=data, vapid_private_key=Vapid.from_raw(vapid_private.encode()),
            vapid_claims={"sub": subject}, ttl=ttl, timeout=10)


class PushStatusError(Exception):
    def __init__(self, status: int):
        super().__init__(f"push status {status}")
        self.status = status


class PushService:
    def __init__(self, store, vapid_private: str = "", vapid_public: str = "", subject: str = "", enc_key: str = "",
                 allowed_hosts: tuple[str, ...] = DEFAULT_HOSTS, send_fn=None, max_per_hour: int = 20, ttl_s: int = 3600, clock=time.time):
        self.store, self.vapid_private, self.vapid_public = store, vapid_private, vapid_public
        self.subject = subject or "mailto:admin@localhost"
        self.allowed, self.max_per_hour, self.ttl_s, self.clock = allowed_hosts, max_per_hour, ttl_s, clock
        self._send = send_fn or _default_send
        self._fernet = None
        if enc_key:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(enc_key.encode())
        self._sent: dict[str, deque] = defaultdict(deque)

    @classmethod
    def from_env(cls, store) -> "PushService":
        extra = tuple(h.strip().lower() for h in os.getenv("PUSH_ALLOWED_HOSTS", "").split(",") if h.strip())
        return cls(store, os.getenv("VAPID_PRIVATE_KEY", ""), os.getenv("VAPID_PUBLIC_KEY", ""), os.getenv("VAPID_SUBJECT", ""),
                   os.getenv("PUSH_ENC_KEY", ""), DEFAULT_HOSTS + extra, max_per_hour=int(os.getenv("PUSH_MAX_PER_HOUR", "20")))

    @property
    def enabled(self) -> bool:
        return bool(self.vapid_private and self.vapid_public and self._fernet)

    def _enc(self, s: str) -> str:
        return self._fernet.encrypt(s.encode()).decode()

    def _dec(self, s: str) -> str:
        return self._fernet.decrypt(s.encode()).decode()

    @staticmethod
    def hash_endpoint(endpoint: str) -> str:
        return hashlib.sha256(endpoint.encode()).hexdigest()

    async def subscribe(self, owner: str, endpoint: str, p256dh: str, auth: str, user_agent: str | None) -> int:
        if not self.enabled:
            raise PushError("Web Push chưa được bật trên máy chủ")
        validate_subscription(endpoint, p256dh, auth, self.allowed)
        await self.store.upsert_subscription(owner, self.hash_endpoint(endpoint), self._enc(endpoint), self._enc(p256dh), self._enc(auth),
                                             (user_agent or "")[:200] or None, MAX_SUBS_PER_USER)
        return await self.store.count_subscriptions(owner)

    async def unsubscribe(self, owner: str, endpoint: str) -> int:
        await self.store.delete_subscription(owner, self.hash_endpoint(endpoint))
        return await self.store.count_subscriptions(owner)

    def _throttled(self, owner: str) -> bool:
        now, q = self.clock(), self._sent[owner]
        while q and q[0] < now - 3600:
            q.popleft()
        if len(q) >= self.max_per_hour:
            return True
        q.append(now)
        return False

    async def notify(self, owner: str) -> int:
        """Gửi thông báo CHUNG tới mọi thiết bị của `owner`. Trả số thiết bị gửi thành công. Không bao giờ ném lỗi ra ngoài."""
        if not self.enabled:
            return 0
        try:
            subs = await self.store.list_subscriptions(owner)
            if not subs:
                return 0
            if self._throttled(owner):
                SENT.labels("throttled").inc()
                return 0
            data = json.dumps({"title": PUSH_TITLE, "body": PUSH_BODY, "url": PUSH_URL}, ensure_ascii=False)
            ok = 0
            for s in subs:
                ok += await self._send_one(s, data)
            return ok
        except Exception:  # noqa: BLE001
            log.exception("notify push lỗi")
            return 0

    async def _send_one(self, s: dict, data: str) -> int:
        try:
            info = {"endpoint": self._dec(s["endpoint_enc"]), "keys": {"p256dh": self._dec(s["p256dh_enc"]), "auth": self._dec(s["auth_enc"])}}
        except Exception:  # noqa: BLE001  (khoá mã hoá đổi/hỏng -> bản ghi vô dụng)
            await self.store.delete_subscription_id(s["id"])
            return 0
        try:
            await asyncio.to_thread(self._send, info, data, self.vapid_private, self.subject, self.ttl_s)
        except Exception as e:  # noqa: BLE001
            status = getattr(e, "status", None) or getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                await self.store.delete_subscription_id(s["id"])      # thiết bị đã huỷ/hết hạn
                SENT.labels("gone").inc()
            else:
                SENT.labels("error").inc()
                if await self.store.mark_subscription_failed(s["id"]) >= MAX_FAILS:
                    await self.store.delete_subscription_id(s["id"])
                log.warning("push lỗi (status=%s, %s)", status, type(e).__name__)   # không log endpoint/khoá
            return 0
        await self.store.mark_subscription_ok(s["id"])
        SENT.labels("ok").inc()
        return 1
