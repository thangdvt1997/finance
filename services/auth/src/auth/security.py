"""Nguyên liệu bảo mật: băm mật khẩu (argon2id), sinh mã ngẫu nhiên, mã hoá bí mật (Fernet), TOTP, giới hạn tốc độ, chính sách mật khẩu.
Không có hàm nào ghi log giá trị bí mật."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

# argon2id (mặc định argon2-cffi: t=3, m=64MiB, p=4). Tối đa 4 phép băm song song để không nghẽn container.
_ph = PasswordHasher()
_sem = asyncio.Semaphore(4)
_DUMMY = _ph.hash("dummy-password-for-timing-equalisation")

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # bỏ ký tự dễ nhầm (I,L,O,0,1)


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(h: str, pw: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(h: str) -> bool:
    try:
        return _ph.check_needs_rehash(h)
    except InvalidHashError:
        return True


async def averify(h: str | None, pw: str) -> bool:
    """Xác minh bất đồng bộ; h=None -> băm giả (cân bằng thời gian, chống dò tài khoản tồn tại)."""
    async with _sem:
        if h is None:
            await asyncio.to_thread(verify_password, _DUMMY, pw)
            return False
        return await asyncio.to_thread(verify_password, h, pw)


async def ahash(pw: str) -> str:
    async with _sem:
        return await asyncio.to_thread(hash_password, pw)


def _grouped(n: int, group: int = 4) -> str:
    s = "".join(secrets.choice(ALPHABET) for _ in range(n))
    return "-".join(s[i:i + group] for i in range(0, n, group))


def gen_passcode() -> str:
    """Mật khẩu cổng ban đầu: 16 ký tự (~80 bit) dạng XXXX-XXXX-XXXX-XXXX. Hiển thị MỘT lần."""
    return _grouped(16)


def gen_pairing_code() -> str:
    """Mã ghép cặp: 12 ký tự (~60 bit), hết hạn sau AUTH_PAIRING_DAYS, dùng một lần."""
    return _grouped(12)


def norm_code(code: str) -> str:
    """Chuẩn hoá mã ghép cặp để băm: chữ hoa, bỏ mọi ký tự không phải chữ-số (mt-bridge dùng đúng quy tắc này)."""
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def hash_code(code: str) -> str:
    return sha256_hex(norm_code(code))


def gen_ea_token() -> str:
    return secrets.token_urlsafe(32)          # 256 bit; EA gửi, bridge so khớp băm sha256 (mtbridge.protocol.hash_token)


def gen_hmac_secret() -> str:
    return secrets.token_hex(32)


def gen_session_id() -> str:
    return secrets.token_urlsafe(32)          # 256 bit ngẫu nhiên; DB chỉ lưu sha256


def hash_session(sid: str) -> str:
    return sha256_hex(sid)


class Vault:
    """Mã hoá đối xứng (Fernet) cho HMAC secret EA + TOTP secret. Key rỗng/sai -> mọi thao tác mã hoá báo lỗi (fail-closed)."""

    def __init__(self, key: str):
        self._f = None
        if key:
            try:
                self._f = Fernet(key.encode())
            except (ValueError, TypeError):
                self._f = None

    @property
    def ok(self) -> bool:
        return self._f is not None

    def enc(self, s: str) -> str:
        if not self._f:
            raise RuntimeError("AUTH_SECRET_KEY thiếu/không hợp lệ")
        return self._f.encrypt(s.encode()).decode()

    def dec(self, s: str) -> str | None:
        if not self._f or not s:
            return None
        try:
            return self._f.decrypt(s.encode()).decode()
        except InvalidToken:
            return None


def check_password_policy(pw: str, *, min_len: int, login: str = "", old: str | None = None) -> str | None:
    """Trả mã lỗi (tiếng Việt, hiển thị cho người dùng) hoặc None nếu hợp lệ."""
    if len(pw) < min_len:
        return f"Mật khẩu tối thiểu {min_len} ký tự"
    if len(pw) > 128:
        return "Mật khẩu tối đa 128 ký tự"
    if len(set(pw)) < 5:
        return "Mật khẩu quá đơn giản"
    low = pw.lower()
    if login and (login.lower() in low or low in login.lower()):
        return "Mật khẩu không được chứa ID đăng nhập"
    if old is not None and pw == old:
        return "Mật khẩu mới phải khác mật khẩu cũ"
    if low in {"password123", "123456789012", "qwertyuiop", "1234567890"} or re.fullmatch(r"(.)\1+", pw):
        return "Mật khẩu quá dễ đoán"
    return None


def const_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class SlidingWindow:
    """Đếm sự kiện trong cửa sổ trượt (bộ nhớ). Dùng cho giới hạn theo IP và theo khoá đăng nhập (cả khoá không tồn tại)."""

    def __init__(self, limit: int, window_s: float, max_keys: int = 50_000):
        self.limit, self.window, self.max_keys = limit, window_s, max_keys
        self._d: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque:
        q = self._d[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            self._d.pop(key, None)
            return deque()
        return q

    def count(self, key: str, now: float | None = None) -> int:
        return len(self._prune(key, now if now is not None else time.monotonic()))

    def blocked(self, key: str, now: float | None = None) -> bool:
        return self.count(key, now) >= self.limit

    def hit(self, key: str, now: float | None = None) -> None:
        now = now if now is not None else time.monotonic()
        if len(self._d) > self.max_keys:      # chống phình bộ nhớ khi bị quét khoá ngẫu nhiên
            for k in list(self._d)[: self.max_keys // 10]:
                self._d.pop(k, None)
        self._prune(key, now)
        self._d[key].append(now)

    def reset(self, key: str) -> None:
        self._d.pop(key, None)

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        q = self._prune(key, now)
        return int(max(1, self.window - (now - q[0]))) if q else 1
