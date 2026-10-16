"""Logic nghiệp vụ đăng nhập/phiên/quản trị. Không phụ thuộc FastAPI (dễ test). Lỗi nghiệp vụ -> AuthError(status, message)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pyotp

from . import security as sec
from .config import AuthSettings
from .store import Store

log = logging.getLogger("auth")

GENERIC_FAIL = "ID hoặc mật khẩu không đúng"
MASTER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
ACCOUNT_ID_RE = re.compile(r"^[\w.:\-]{1,64}$")
SERVER_RE = re.compile(r"^[\w .:\-/()]{0,64}$")


class AuthError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


@dataclass
class Principal:
    user_id: str
    role: str                      # master | client
    login_key: str
    display_name: str
    accounts: list[str]
    must_change_password: bool = False
    totp_enabled: bool = False
    session_hash: str = ""
    expires_at: datetime | None = None
    extra: dict = field(default_factory=dict)
    scope_all: bool = False
    totp_setup_required: bool = False

    def me(self) -> dict:
        from .roles import perms_of
        out = {"user_id": self.user_id, "role": self.role, "login": self.login_key, "display_name": self.display_name,
               "accounts": self.accounts, "must_change_password": self.must_change_password, "totp_enabled": self.totp_enabled,
               "expires_at": self.expires_at.isoformat() if self.expires_at else None, "perms": perms_of(self.role),
               "totp_setup_required": self.totp_setup_required}
        if self.role not in ("master", "client"):
            out["scope"] = {"all": self.scope_all, "groups": self.extra.get("scope_groups", [])}
        return out


def now() -> datetime:
    return datetime.now(timezone.utc)


def _device(ua: str) -> str:
    u = ua or ""
    br = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in u), "")
    os_ = next((n for k, n in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if k in u), "")
    return " · ".join(x for x in (br, os_) if x) or (u[:40] or "không rõ")


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:24]


class AuthService:
    def __init__(self, store: Store, settings: AuthSettings | None = None):
        self.store = store
        self.cfg = settings or AuthSettings()
        self.vault = sec.Vault(self.cfg.secret_key)
        self.fail_key = sec.SlidingWindow(self.cfg.max_fails, self.cfg.lock_minutes * 60)
        self.fail_ip = sec.SlidingWindow(self.cfg.ip_fail_limit, self.cfg.ip_window_s)
        self._cache: dict[str, tuple[float, dict]] = {}
        self._totp_last: dict[str, int] = {}
        self.reg_ip = sec.SlidingWindow(self.cfg.self_register_per_ip_h, 3600)   # số tài khoản EA tự đăng ký / giờ / IP
        self.reg_fail = sec.SlidingWindow(10, 600)                                  # sai mã ghép cặp qua EA theo (platform, login)

    # ------------------------------------------------------------ cache phiên (TTL ngắn; thu hồi xoá ngay trong tiến trình)
    def _cache_get(self, h: str) -> dict | None:
        v = self._cache.get(h)
        if v and v[0] > time.monotonic():
            return v[1]
        self._cache.pop(h, None)
        return None

    def _cache_put(self, h: str, row: dict) -> None:
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[h] = (time.monotonic() + 5.0, row)

    def _cache_drop_user(self, user_id: str) -> None:
        for k in [k for k, (_, r) in self._cache.items() if str(r["user_id"]) == str(user_id)]:
            self._cache.pop(k, None)

    def _ttl(self, role: str) -> tuple[timedelta, timedelta]:
        c = self.cfg
        return ((timedelta(hours=c.master_ttl_h), timedelta(hours=c.master_idle_h)) if role != "client"
                else (timedelta(hours=c.client_ttl_h), timedelta(hours=c.client_idle_h)))

    def public_path(self, uri: str) -> bool:
        """Đường dẫn không cần phiên (vỏ tĩnh client-ui). /api/ và /auth/admin không bao giờ công khai."""
        p = (uri or "").split("?", 1)[0]
        # X-Original-URI là $request_uri CHƯA chuẩn hoá: cấm mã hoá phần trăm, `..`, `//`, `;`, dấu gạch ngược, NUL (vd /c/%2e%2e/index.html lách nginx -> vỏ master không cần đăng nhập)
        if p.startswith("/api/") or p.startswith("/auth/admin") or any(x in p for x in ("..", "%", "//", ";", chr(92), chr(0))):
            return False
        return any(p.startswith(x) for x in self.cfg.public_prefixes)

    # ------------------------------------------------------------ đăng nhập
    async def _resolve_user(self, platform: str, login: str, server: str | None) -> tuple[dict | None, str]:
        """Trả (user_row|None, khoá để đếm sai). Không phân biệt 'không tồn tại' / 'sai mật khẩu' ra bên ngoài."""
        if platform == "master":
            key = f"master:{login.lower()}"
            return await self.store.get_user_by_key(key), key
        key = f"{platform}:{login}"
        if not login.isdigit() or len(login) > 16:
            return None, key
        accs = await self.store.find_accounts(platform, int(login), server or None)
        accs = [a for a in accs if a["client_id"]]
        if len(accs) != 1:
            return None, key + (f"@{server}" if server else "")
        user = await self.store.get_user(str(accs[0]["client_id"]))
        return user, f"{platform}:{login}"

    async def login(self, platform: str, login: str, secret: str, server: str | None, totp: str | None, ip: str, ua: str) -> tuple[str, Principal]:
        if self.fail_ip.blocked(ip):
            await self.store.audit(None, "", "login_blocked_ip", "", ip, {})
            raise AuthError(429, "Quá nhiều lần thử. Vui lòng thử lại sau.", retry_after=self.fail_ip.retry_after(ip))
        user, key = await self._resolve_user(platform, login, server)
        lock_mem = self.fail_key.blocked(key)
        lock_db = bool(user and user["locked_until"] and user["locked_until"] > now())
        ok = await sec.averify(user["password_hash"] if user else None, secret)   # luôn băm (cân bằng thời gian)
        if not user or lock_mem or lock_db or user["status"] != "active" or not ok:
            self.fail_ip.hit(ip)
            reason = "unknown" if not user else "locked" if (lock_mem or lock_db) else "inactive" if user["status"] != "active" else "bad_password"
            if user and ok is False and not (lock_mem or lock_db):
                self.fail_key.hit(key)
                r = await self.store.record_fail(str(user["user_id"]), self.cfg.max_fails, self.cfg.lock_minutes)
                if r["locked_until"] and r["locked_until"] > now():
                    await self.store.audit(str(user["user_id"]), key, "account_locked", key, ip, {"minutes": self.cfg.lock_minutes})
            elif not user:
                self.fail_key.hit(key)
            await self.store.audit(str(user["user_id"]) if user else None, key, "login_fail", key, ip, {"reason": reason})
            raise AuthError(401, GENERIC_FAIL)
        if user["role"] != "client" and user["totp_enabled"]:
            if not totp:
                raise AuthError(401, "Cần mã xác thực 2 bước", totp_required=True)
            if not self._totp_ok(user, totp):
                self.fail_ip.hit(ip)
                self.fail_key.hit(key)
                await self.store.record_fail(str(user["user_id"]), self.cfg.max_fails, self.cfg.lock_minutes)
                await self.store.audit(str(user["user_id"]), key, "login_fail", key, ip, {"reason": "bad_totp"})
                raise AuthError(401, GENERIC_FAIL)
        if sec.needs_rehash(user["password_hash"]):
            await self.store.set_password(str(user["user_id"]), await sec.ahash(secret), bool(user["must_change_password"]))
        self.fail_key.reset(key)
        await self.store.record_success(str(user["user_id"]))
        sid = sec.gen_session_id()
        ttl, _ = self._ttl(user["role"])
        exp = now() + ttl
        await self.store.create_session(sec.hash_session(sid), str(user["user_id"]), exp, ip, ua)
        await self.store.audit(str(user["user_id"]), key, "login_ok", key, ip, {"role": user["role"]})
        accounts = await self._accounts_for(user["role"], str(user["user_id"]), bool(user.get("scope_all")), None)
        p = Principal(str(user["user_id"]), user["role"], user["login_key"], user["display_name"], accounts, bool(user["must_change_password"]),
                      bool(user["totp_enabled"]), sec.hash_session(sid), exp, scope_all=bool(user.get("scope_all")),
                      totp_setup_required=self._totp_setup_required(user["role"], bool(user["totp_enabled"])))
        if user["role"] not in ("master", "client"):
            p.extra["scope_groups"] = await self._fleet_store().staff_scope(str(user["user_id"]))
        return sid, p

    def _fleet_store(self):
        from .fleet_store import FleetStore
        return FleetStore(self.store.pool)

    def _totp_setup_required(self, role: str, enabled: bool) -> bool:
        return bool(role == "master" and self.cfg.master_totp_required and not enabled)


    def totp_gate(self, p: "Principal", uri: str) -> bool:

        """AUTH_MASTER_TOTP_ENFORCE=1 (mặc định TẮT): master CHƯA bật TOTP bị chặn mọi /api/* (trừ /api/v1/me) cho tới khi bật TOTP;

        vẫn tải được giao diện + /auth/* (đăng nhập, /auth/totp/setup|enable). True = chặn. Chưa có luồng UI riêng -> chỉ bật khi master đã bật TOTP."""

        if not (self.cfg.master_totp_enforce and p.role == "master" and not p.totp_enabled):

            return False

        path = (uri or "").split("?", 1)[0]

        return path.startswith("/api/") and path not in ("/api/v1/me",)

    async def _accounts_for(self, role: str, user_id: str, scope_all: bool, row_accounts) -> list[str]:
        if role == "master":
            return ["*"]
        if role == "client":
            return list(row_accounts) if row_accounts is not None else await self.store.accounts_of_user(user_id)
        return await self._fleet_store().staff_accounts(user_id, scope_all)     # support/analyst/auditor: chỉ trong phạm vi nhóm (mặc định rỗng)

    def _totp_ok(self, user: dict, code: str) -> bool:
        secret = self.vault.dec(user["totp_secret_enc"] or "")
        code = re.sub(r"\s", "", code or "")
        if not secret or not re.fullmatch(r"\d{6}", code):
            return False
        t = pyotp.TOTP(secret)
        step = int(time.time() // 30)
        uid = str(user["user_id"])
        for off in (0, -1, 1):          # chấp nhận lệch ±30s; mỗi mã chỉ dùng được một lần (chống phát lại)
            if t.at((step + off) * 30) == code and step + off > self._totp_last.get(uid, 0):
                self._totp_last[uid] = step + off
                return True
        return False

    # ------------------------------------------------------------ xác minh phiên (nginx auth_request)
    async def verify_session(self, sid: str | None) -> Principal | None:
        if not sid or len(sid) > 128:
            return None
        h = sec.hash_session(sid)
        row = self._cache_get(h)
        if row is None:
            row = await self.store.get_session(h)
            if row is None:
                return None
            self._cache_put(h, row)
        t = now()
        _, idle = self._ttl(row["role"])
        if row["revoked"] or row["expires_at"] <= t or t - row["last_seen_at"] > idle or row["user_status"] != "active":
            self._cache.pop(h, None)
            return None
        if t - row["last_seen_at"] > timedelta(seconds=60):     # trượt hạn idle, tránh ghi DB mỗi request
            await self.store.touch_session(h)
            row = {**row, "last_seen_at": t}
            self._cache_put(h, row)
        accounts = await self._accounts_for(row["role"], str(row["user_id"]), bool(row.get("scope_all")), row["accounts"])
        p = Principal(str(row["user_id"]), row["role"], row["login_key"], row["display_name"], accounts, bool(row["must_change_password"]),
                      bool(row["totp_enabled"]), h, row["expires_at"], scope_all=bool(row.get("scope_all")),
                      totp_setup_required=self._totp_setup_required(row["role"], bool(row["totp_enabled"])))
        if row["role"] not in ("master", "client"):
            p.extra["scope_groups"] = await self._fleet_store().staff_scope(str(row["user_id"]))
        return p

    async def logout(self, p: Principal, ip: str) -> None:
        await self.store.revoke_session(p.session_hash)
        self._cache.pop(p.session_hash, None)
        await self.store.audit(p.user_id, p.login_key, "logout", p.login_key, ip, {})

    # ------------------------------------------------------------ mật khẩu / ghép cặp
    async def change_password(self, p: Principal, current: str, new: str, ip: str) -> None:
        user = await self.store.get_user(p.user_id)
        if self.fail_ip.blocked(ip) or not user or not await sec.averify(user["password_hash"], current):
            self.fail_ip.hit(ip)
            await self.store.audit(p.user_id, p.login_key, "password_change_fail", p.login_key, ip, {})
            raise AuthError(401 if user else 400, "Mật khẩu hiện tại không đúng")
        err = sec.check_password_policy(new, min_len=self.cfg.min_password_len, login=p.login_key.split(":", 1)[-1], old=current)
        if err:
            raise AuthError(422, err)
        await self.store.set_password(p.user_id, await sec.ahash(new), False)
        n = len(await self.store.revoke_user_sessions(p.user_id, except_hash=p.session_hash))
        self._cache_drop_user(p.user_id)
        await self.store.audit(p.user_id, p.login_key, "password_changed", p.login_key, ip, {"other_sessions_revoked": n})

    async def pair(self, platform: str, login: str, code: str, new_password: str, server: str | None, ip: str) -> None:
        bad = AuthError(400, "Mã ghép cặp không hợp lệ hoặc đã hết hạn")
        if self.fail_ip.blocked(ip):
            raise AuthError(429, "Quá nhiều lần thử. Vui lòng thử lại sau.", retry_after=self.fail_ip.retry_after(ip))
        key = f"pair:{platform}:{login}"
        if self.fail_key.blocked(key) or not login.isdigit() or len(login) > 16:
            self.fail_ip.hit(ip)
            raise bad
        accs = await self.store.find_accounts(platform, int(login), server or None)
        want = sec.hash_code(code)
        match = [a for a in accs if a["pairing_code_hash"] and a["pairing_expires_at"] and a["pairing_expires_at"] > now() and a["status"] != "suspended"
                 and sec.const_eq(a["pairing_code_hash"], want)]
        if len(match) != 1:
            self.fail_ip.hit(ip)
            self.fail_key.hit(key)
            await self.store.audit(None, key, "pair_fail", key, ip, {})
            raise bad
        a = match[0]
        err = sec.check_password_policy(new_password, min_len=self.cfg.min_password_len, login=login)
        if err:
            raise AuthError(422, err)
        u = await self.store.claim_account(a["account_id"], str(a["client_id"]) if a["client_id"] else None, await sec.ahash(new_password),
                                           a["label"] or a["account_id"])
        await self.store.revoke_user_sessions(str(u["user_id"]))
        self._cache_drop_user(str(u["user_id"]))
        self.fail_key.reset(key)
        await self.store.audit(str(u["user_id"]), a["account_id"], "pair_ok", a["account_id"], ip, {})
        await self.notify_bridge(a["account_id"])   # pending -> active: bridge nhận dữ liệu ngay

    # ------------------------------------------------------------ TOTP (master)
    async def totp_setup(self, p: Principal, ip: str) -> dict:
        if p.role == "client":
            raise AuthError(403, "Chỉ master")
        secret = pyotp.random_base32()
        await self.store.set_totp(p.user_id, self.vault.enc(secret), False)
        await self.store.audit(p.user_id, p.login_key, "totp_setup", p.login_key, ip, {})
        return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=p.login_key, issuer_name=self.cfg.totp_issuer)}

    async def totp_enable(self, p: Principal, code: str, ip: str) -> None:
        user = await self.store.get_user(p.user_id)
        if not user or user["role"] == "client" or not user["totp_secret_enc"] or not self._totp_ok(user, code):
            raise AuthError(400, "Mã xác thực không đúng")
        await self.store.set_totp(p.user_id, user["totp_secret_enc"], True)
        await self.store.revoke_user_sessions(p.user_id, except_hash=p.session_hash)
        self._cache_drop_user(p.user_id)
        await self.store.audit(p.user_id, p.login_key, "totp_enabled", p.login_key, ip, {})

    async def totp_disable(self, p: Principal, password: str, code: str, ip: str) -> None:
        user = await self.store.get_user(p.user_id)
        if not user or not await sec.averify(user["password_hash"], password) or (user["totp_enabled"] and not self._totp_ok(user, code)):
            raise AuthError(400, "Mật khẩu hoặc mã xác thực không đúng")
        await self.store.set_totp(p.user_id, None, False)
        await self.store.audit(p.user_id, p.login_key, "totp_disabled", p.login_key, ip, {})

    # ------------------------------------------------------------ phiên của chính mình
    async def my_sessions(self, p: Principal) -> list[dict]:
        rows = await self.store.list_sessions(p.user_id)
        return [self._sess_out(r, current=p.session_hash) for r in rows]

    async def revoke_my_session(self, p: Principal, sid: str, ip: str) -> bool:
        ok = await self.store.revoke_session(sid, p.user_id)
        self._cache.pop(sid, None)
        if ok:
            await self.store.audit(p.user_id, p.login_key, "session_revoked", sid[:12], ip, {"self": True})
        return ok

    async def logout_all(self, p: Principal, ip: str) -> int:
        ids = await self.store.revoke_user_sessions(p.user_id)
        self._cache_drop_user(p.user_id)
        await self.store.audit(p.user_id, p.login_key, "logout_all", p.login_key, ip, {"n": len(ids)})
        return len(ids)

    @staticmethod
    def _sess_out(r: dict, current: str = "") -> dict:
        return {"id": r["session_id"], "user_id": str(r["user_id"]), "login": r["login_key"], "role": r["role"], "created_at": r["created_at"].isoformat(),
                "last_seen_at": r["last_seen_at"].isoformat(), "expires_at": r["expires_at"].isoformat(), "ip": r["ip"], "user_agent": r["user_agent"],
                "revoked": r["revoked"], "current": bool(current) and r["session_id"] == current, "device": _device(r["user_agent"])}

    # ------------------------------------------------------------ quản trị (master)
    @staticmethod
    def _acc_out(a: dict) -> dict:
        out = {k: a[k] for k in ("account_id", "platform", "login", "server", "label", "status", "created_at", "last_seen_at", "notes", "pairing_expires_at")
               if k in a}
        out["client_id"] = str(a["client_id"]) if a.get("client_id") else None
        out["has_pairing"] = bool(a.get("pairing_code_hash") or a.get("has_pairing"))
        out["has_ea_token"] = bool(a.get("ea_token_hash") or a.get("has_ea_token"))
        out["has_hmac"] = bool(a.get("ea_hmac_secret_enc") or a.get("has_hmac"))
        for k in ("rev", "require_hmac", "ea_status", "ea_reason", "ea_latency_ms", "ea_skew_s", "ea_version", "ea_build", "ea_broker", "ea_remote_addr"):
            if k in a:
                out[k] = a[k]
        if a.get("ea_health_at"):
            out["ea_health_at"] = a["ea_health_at"].isoformat()
        for k in ("client_login", "client_name", "client_status", "client_must_change", "client_last_login", "client_locked_until"):
            if k in a:
                out[k] = a[k]
        for k in ("created_at", "last_seen_at", "pairing_expires_at", "client_last_login", "client_locked_until"):
            if out.get(k) is not None:
                out[k] = out[k].isoformat()
        return out

    async def list_accounts(self) -> list[dict]:
        return [self._acc_out(a) for a in await self.store.list_accounts()]

    async def get_account(self, account_id: str) -> dict:
        a = await self.store.get_account(account_id)
        if not a:
            raise AuthError(404, "Không có tài khoản này")
        return self._acc_out(a)

    async def create_account(self, actor: Principal, platform: str, login: int, server: str, label: str, notes: str, ip: str, suffix: str = "") -> dict:
        if platform not in ("mt4", "mt5") or login <= 0 or login > 2**53 or not SERVER_RE.match(server):
            raise AuthError(422, "Dữ liệu tài khoản không hợp lệ")
        if not self.vault.ok:
            raise AuthError(503, "Thiếu AUTH_SECRET_KEY (không thể mã hoá HMAC secret)")
        existing = await self.store.find_accounts(platform, login)
        if suffix:   # tai khoan phu cung (nen tang, so, may chu), vd EA market-feed `mt5:<login>-feed`: id tuong minh, ghep cap phan biet theo account_id
            if not re.fullmatch(r"[a-z0-9]{1,16}", suffix):
                raise AuthError(422, "Hậu tố không hợp lệ")
            account_id = f"{platform}:{login}-{suffix}"
            if await self.store.get_account(account_id):
                raise AuthError(409, "Tài khoản đã tồn tại")
        elif any((e["server"] or "").lower() == server.lower() for e in existing):
            raise AuthError(409, "Tài khoản (nền tảng + số + máy chủ) đã tồn tại")
        else:
            account_id = f"{platform}:{login}"
        if existing and not suffix:                     # trùng số khác broker -> phân biệt bằng hậu tố máy chủ
            account_id += "-" + (slug(server) or "x")
            if not ACCOUNT_ID_RE.match(account_id) or await self.store.get_account(account_id):
                raise AuthError(409, "Tài khoản đã tồn tại")
        passcode, pairing, token, hsecret = sec.gen_passcode(), sec.gen_pairing_code(), sec.gen_ea_token(), sec.gen_hmac_secret()
        expires = now() + timedelta(days=self.cfg.pairing_days)
        try:
            _, a = await self.store.create_client_account(
                account_id=account_id, platform=platform, login=login, server=server, label=label[:80], notes=notes[:500],
                password_hash=await sec.ahash(passcode), display_name=(label or account_id)[:80], ea_token_hash=sec.sha256_hex(token),
                hmac_enc=self.vault.enc(hsecret), pairing_hash=sec.hash_code(pairing), pairing_expires=expires)
        except Exception as e:  # noqa: BLE001 (vi phạm UNIQUE do chạy đua)
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise AuthError(409, "Tài khoản đã tồn tại") from None
            raise
        await self.store.audit(actor.user_id, actor.login_key, "account_created", account_id, ip, {"platform": platform, "server": server})
        return {"account": self._acc_out(a), "secrets": {
            "passcode": passcode, "pairing_code": pairing, "pairing_expires_at": expires.isoformat(), "ea_token": token, "hmac_secret": hsecret,
            "note": "Các giá trị này chỉ hiển thị MỘT lần. Passcode = mật khẩu cổng ban đầu (bắt buộc đổi khi đăng nhập lần đầu)."}}

    async def update_account(self, actor: Principal, account_id: str, fields: dict, ip: str) -> dict:
        allowed = {k: v for k, v in fields.items() if k in ("label", "notes", "server") and v is not None}
        if "server" in allowed and not SERVER_RE.match(allowed["server"]):
            raise AuthError(422, "Máy chủ không hợp lệ")
        if not allowed:
            raise AuthError(422, "Không có trường hợp lệ để cập nhật")
        a = await self.store.update_account(account_id, **allowed)
        if not a:
            raise AuthError(404, "Không có tài khoản này")
        await self.store.audit(actor.user_id, actor.login_key, "account_updated", account_id, ip, {"fields": sorted(allowed)})
        await self.notify_bridge(account_id)
        return self._acc_out(a)

    async def set_account_status(self, actor: Principal, account_id: str, suspend: bool, ip: str) -> dict:
        a = await self.store.get_account(account_id)
        if not a:
            raise AuthError(404, "Không có tài khoản này")
        a = await self.store.update_account(account_id, status="suspended" if suspend else "active")   # kích hoạt = master DUYỆT (pending -> active)
        if a["client_id"]:
            uid = str(a["client_id"])
            if suspend:
                if not await self.store.accounts_of_user(uid):
                    await self.store.set_user_status(uid, "suspended")
                await self.store.revoke_user_sessions(uid)
            else:
                await self.store.set_user_status(uid, "active")
            self._cache_drop_user(uid)
        await self.store.audit(actor.user_id, actor.login_key, "account_suspended" if suspend else "account_activated", account_id, ip, {})
        await self.notify_bridge(account_id)
        return self._acc_out(a)

    async def _ensure_owner(self, a: dict, passcode: str) -> str:
        """Trả user_id chủ tài khoản; tạo user client nếu EA tự đăng ký chưa có chủ."""
        if a["client_id"]:
            return str(a["client_id"])
        u = await self.store.create_user("client", a["account_id"], (a["label"] or a["account_id"])[:80], await sec.ahash(passcode), True)
        await self.store.link_account(str(u["user_id"]), a["account_id"])
        await self.store.update_account(a["account_id"], client_id=u["user_id"])
        return str(u["user_id"])

    async def reset_passcode(self, actor: Principal, account_id: str, ip: str) -> dict:
        a = await self.store.get_account(account_id)
        if not a:
            raise AuthError(404, "Không có tài khoản này")
        passcode = sec.gen_passcode()
        uid = await self._ensure_owner(a, passcode)
        await self.store.set_password(uid, await sec.ahash(passcode), True)
        await self.store.set_user_status(uid, "active" if a["status"] != "suspended" else "suspended")
        await self.store.revoke_user_sessions(uid)
        self._cache_drop_user(uid)
        self.fail_key.reset(f"{a['platform']}:{a['login']}")
        await self.store.audit(actor.user_id, actor.login_key, "passcode_reset", account_id, ip, {})
        return {"passcode": passcode, "note": "Chỉ hiển thị MỘT lần; khách hàng phải đổi khi đăng nhập lần đầu."}

    async def rotate_ea_token(self, actor: Principal, account_id: str, ip: str) -> dict:
        token = sec.gen_ea_token()
        if not await self.store.update_account(account_id, ea_token_hash=sec.sha256_hex(token)):
            raise AuthError(404, "Không có tài khoản này")
        await self.store.audit(actor.user_id, actor.login_key, "ea_token_rotated", account_id, ip, {})
        await self.notify_bridge(account_id)
        return {"ea_token": token, "note": "Token cũ vô hiệu ngay. Nhập token mới vào input của EA."}

    async def rotate_hmac(self, actor: Principal, account_id: str, ip: str) -> dict:
        if not self.vault.ok:
            raise AuthError(503, "Thiếu AUTH_SECRET_KEY")
        secret = sec.gen_hmac_secret()
        if not await self.store.update_account(account_id, ea_hmac_secret_enc=self.vault.enc(secret)):
            raise AuthError(404, "Không có tài khoản này")
        await self.store.audit(actor.user_id, actor.login_key, "ea_hmac_rotated", account_id, ip, {})
        await self.notify_bridge(account_id)
        return {"hmac_secret": secret, "note": "Secret cũ vô hiệu ngay. Nhập secret mới vào input HmacSecret của EA."}

    async def new_pairing_code(self, actor: Principal, account_id: str, ip: str) -> dict:
        code = sec.gen_pairing_code()
        exp = now() + timedelta(days=self.cfg.pairing_days)
        if not await self.store.update_account(account_id, pairing_code_hash=sec.hash_code(code), pairing_expires_at=exp):
            raise AuthError(404, "Không có tài khoản này")
        await self.store.audit(actor.user_id, actor.login_key, "pairing_code_issued", account_id, ip, {})
        return {"pairing_code": code, "pairing_expires_at": exp.isoformat()}

    async def delete_account(self, actor: Principal, account_id: str, ip: str) -> dict:
        r = await self.store.delete_account(account_id)
        if not r:
            raise AuthError(404, "Không có tài khoản này")
        if r["client_id"]:
            self._cache_drop_user(r["client_id"])
        await self.store.audit(actor.user_id, actor.login_key, "account_deleted", account_id, ip, {"user_deleted": r["user_deleted"]})
        await self.notify_bridge(account_id)
        return r

    async def list_users(self) -> list[dict]:
        out = []
        for u in await self.store.list_users():
            out.append({**u, "user_id": str(u["user_id"]), "accounts": list(u["accounts"]),
                        **{k: (u[k].isoformat() if u[k] else None) for k in ("created_at", "last_login_at", "locked_until")}})
        return out

    async def user_action(self, actor: Principal, user_id: str, action: str, ip: str) -> dict:
        u = await self.store.get_user(user_id)
        if not u:
            raise AuthError(404, "Không có người dùng này")
        if action == "unlock":
            await self.store.unlock(user_id)
            self.fail_key.reset(u["login_key"])
        elif action == "revoke-sessions":
            n = len(await self.store.revoke_user_sessions(user_id))
            self._cache_drop_user(user_id)
            await self.store.audit(actor.user_id, actor.login_key, "sessions_revoked", u["login_key"], ip, {"n": n})
            return {"revoked": n}
        elif action in ("suspend", "activate"):
            if u["user_id"] and str(u["user_id"]) == actor.user_id and action == "suspend":
                raise AuthError(400, "Không thể tự đình chỉ")
            await self.store.set_user_status(user_id, "suspended" if action == "suspend" else "active")
            if action == "suspend":
                await self.store.revoke_user_sessions(user_id)
            self._cache_drop_user(user_id)
        else:
            raise AuthError(404, "Hành động không hợp lệ")
        await self.store.audit(actor.user_id, actor.login_key, f"user_{action}", u["login_key"], ip, {})
        return {"ok": True}

    async def link_account(self, actor: Principal, user_id: str, account_id: str, ip: str) -> None:
        u, a = await self.store.get_user(user_id), await self.store.get_account(account_id)
        if not u or not a or u["role"] != "client":
            raise AuthError(404, "Không tìm thấy người dùng client hoặc tài khoản")
        await self.store.link_account(user_id, account_id)
        self._cache_drop_user(user_id)
        await self.store.audit(actor.user_id, actor.login_key, "account_linked", account_id, ip, {"user": u["login_key"]})

    async def unlink_account(self, actor: Principal, user_id: str, account_id: str, ip: str) -> None:
        if not await self.store.unlink_account(user_id, account_id):
            raise AuthError(404, "Liên kết không tồn tại")
        self._cache_drop_user(user_id)
        await self.store.audit(actor.user_id, actor.login_key, "account_unlinked", account_id, ip, {"user": user_id})

    async def admin_revoke_session(self, actor: Principal, sid: str, ip: str) -> None:
        if not await self.store.revoke_session(sid):
            raise AuthError(404, "Phiên không tồn tại")
        self._cache.pop(sid, None)
        await self.store.audit(actor.user_id, actor.login_key, "session_revoked", sid[:12], ip, {"self": False})

    async def all_sessions(self, user_id: str | None, active_only: bool) -> list[dict]:
        return [self._sess_out(r) for r in await self.store.list_sessions(user_id, active_only)]

    # ------------------------------------------------------------ CLI: tài khoản master
    async def create_master(self, name: str, password: str, display_name: str = "") -> dict:
        name = name.lower()
        if not MASTER_NAME_RE.match(name):
            raise AuthError(422, "Tên master không hợp lệ")
        err = sec.check_password_policy(password, min_len=self.cfg.min_password_len, login=name)
        if err:
            raise AuthError(422, err)
        if await self.store.get_user_by_key(f"master:{name}"):
            raise AuthError(409, "Master đã tồn tại")
        u = await self.store.create_user("master", f"master:{name}", display_name or name, await sec.ahash(password), True)
        await self.store.audit(str(u["user_id"]), f"master:{name}", "master_created", f"master:{name}", "cli", {})
        return u

    async def reset_master(self, name: str, password: str) -> None:
        u = await self.store.get_user_by_key(f"master:{name.lower()}")
        if not u:
            raise AuthError(404, "Không có master này")
        await self.store.set_password(str(u["user_id"]), await sec.ahash(password), True)
        await self.store.set_user_status(str(u["user_id"]), "active")
        await self.store.set_totp(str(u["user_id"]), None, False)    # khôi phục: tắt luôn TOTP (mất thiết bị 2FA)
        await self.store.revoke_user_sessions(str(u["user_id"]))
        await self.store.audit(str(u["user_id"]), u["login_key"], "master_reset_cli", u["login_key"], "cli", {})


    # ------------------------------------------------------------ nội bộ: mt-bridge <-> auth (docs/CLIENT_PLATFORM.md)
    async def notify_bridge(self, account_id: str) -> None:
        """Báo bridge bỏ cache + nạp lại NGAY (xoay token/HMAC, đình chỉ, kích hoạt, xoá). Lỗi chỉ log: bridge vẫn tự làm mới theo TTL 15s."""
        if not self.cfg.internal_token or not self.cfg.bridge_url:
            return

        def go():
            req = urllib.request.Request(self.cfg.bridge_url + "/internal/invalidate", data=json.dumps({"account_id": account_id}).encode(), method="POST",
                                         headers={"Authorization": f"Bearer {self.cfg.internal_token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2):  # noqa: S310 (URL nội bộ từ cấu hình)
                pass
        try:
            await asyncio.to_thread(go)
        except Exception as e:  # noqa: BLE001
            log.warning("báo bridge thu hồi %s thất bại: %s", account_id, type(e).__name__)

    def mt_record(self, a: dict) -> dict:
        cfg = a.get("config") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg or "{}")
        return {"account_id": a["account_id"], "platform": a["platform"], "status": a["status"], "ea_token_hash": a["ea_token_hash"] or "",
                "hmac_secret": self.vault.dec(a["ea_hmac_secret_enc"] or "") or "", "require_hmac": bool(a.get("require_hmac", True)),
                "rev": int(a.get("rev") or 1), "config": cfg}

    async def internal_list(self) -> dict:
        return {"rev": await self.store.accounts_rev(), "accounts": [self.mt_record(a) for a in await self.store.list_accounts_full()]}

    async def internal_get(self, account_id: str) -> dict | None:
        a = await self.store.get_account(account_id)
        return self.mt_record(a) if a else None

    async def ea_register(self, info: dict) -> tuple[int, dict]:
        """EA/bridge hỏi: ghép cặp bằng mã (trả token+HMAC MỘT lần) hoặc tự đăng ký (pending + mã ghép cặp để client nhập ở /auth/pair)."""
        platform, server = str(info.get("platform") or ""), str(info.get("server") or "")[:64]
        ip, code, broker = str(info.get("remote_addr") or "-")[:64], str(info.get("pair_code") or ""), str(info.get("company") or "")
        try:
            login = int(info.get("login") or 0)
        except (TypeError, ValueError):
            login = 0
        if platform not in ("mt4", "mt5") or login <= 0 or login > 2**53:
            return 200, {"status": "rejected", "message": "dữ liệu đăng ký không hợp lệ"}
        key = f"reg:{platform}:{login}"
        if self.fail_ip.blocked(ip) or self.reg_fail.blocked(key):
            return 429, {"status": "rejected", "message": "thử lại sau"}
        cands = await self.store.find_accounts(platform, login)
        want = str(info.get("account_id") or "")
        if want and any(c["account_id"] == want for c in cands):   # EA khai ro account_id (vd mt5:<login>-feed) -> khong mo ho theo may chu
            cands = [c for c in cands if c["account_id"] == want]
        if len(cands) > 1:
            cands = [c for c in cands if (c["server"] or "").lower() == server.lower()]
        if len(cands) > 1:   # cung may chu: khong khai account_id -> tai khoan chinh `<platform>:<login>` (khong pha EA cu)
            cands = [c for c in cands if c["account_id"] == f"{platform}:{login}"]
        a = cands[0] if len(cands) == 1 else None
        if len(cands) > 1 or (a is not None and a["server"] and server and a["server"].lower() != server.lower() and not code):
            return 200, {"status": "rejected", "message": "tài khoản không xác định rõ (máy chủ không khớp)"}
        if code:
            ok = (a is not None and a["client_id"] is not None and a["pairing_code_hash"] and a["pairing_expires_at"] and a["pairing_expires_at"] > now()
                  and sec.const_eq(a["pairing_code_hash"], sec.hash_code(code)))
            if not ok:
                self.fail_ip.hit(ip)
                self.reg_fail.hit(key)
                await self.store.audit(None, "mt-bridge", "ea_pair_fail", f"{platform}:{login}", ip, {})
                return 200, {"status": "suspended" if a is not None and a["status"] == "suspended" else "rejected", "message": "mã ghép cặp không hợp lệ hoặc đã hết hạn"}
            if a["status"] == "suspended":
                return 200, {"status": "suspended", "account_id": a["account_id"]}
            token, hsecret = sec.gen_ea_token(), sec.gen_hmac_secret()
            await self.store.update_account(a["account_id"], ea_token_hash=sec.sha256_hex(token), ea_hmac_secret_enc=self.vault.enc(hsecret),
                                            pairing_code_hash=None, pairing_expires_at=None, status="active", ea_cred_pending_enc=None, ea_remote_addr=ip)
            self.reg_fail.reset(key)
            await self.store.audit(None, "mt-bridge", "ea_paired", a["account_id"], ip, {})
            await self.notify_bridge(a["account_id"])
            return 200, {"status": "active", "account_id": a["account_id"], "token": token, "hmac_secret": hsecret}
        if a is not None:
            if a["status"] == "suspended":
                return 200, {"status": "suspended", "account_id": a["account_id"]}
            if a["ea_cred_pending_enc"] and a["client_id"] and a["status"] == "active" and a["ea_remote_addr"] == ip:   # giao thông tin đăng nhập một lần cho EA tự đăng ký đã được client ghép cặp
                cred = json.loads(self.vault.dec(a["ea_cred_pending_enc"]) or "{}")
                await self.store.update_account(a["account_id"], ea_cred_pending_enc=None)
                if cred.get("token") and cred.get("hmac"):
                    await self.store.audit(None, "mt-bridge", "ea_credentials_delivered", a["account_id"], ip, {})
                    return 200, {"status": "active", "account_id": a["account_id"], "token": cred["token"], "hmac_secret": cred["hmac"]}
            if a["client_id"] is None and a["status"] == "pending":   # chưa ai ghép cặp: cấp mã mới (mã cũ chỉ lưu băm nên không hiện lại được)
                pc = sec.gen_pairing_code()
                await self.store.update_account(a["account_id"], pairing_code_hash=sec.hash_code(pc), pairing_expires_at=now() + timedelta(days=self.cfg.pairing_days), ea_remote_addr=ip)
                return 200, {"status": "pending", "account_id": a["account_id"], "pairing_code": pc, "message": "nhập mã này ở trang đăng nhập (Ghép cặp)"}
            return 200, {"status": a["status"], "account_id": a["account_id"], "message": "nhập PairCode do quản trị cấp, hoặc Token + HmacSecret"}
        # tài khoản chưa có: tự đăng ký (giới hạn theo IP + tổng số chưa ghép cặp)
        if not self.cfg.self_register or not self.vault.ok:
            return 200, {"status": "unknown", "message": "tài khoản chưa được cấp; liên hệ quản trị"}
        if self.reg_ip.blocked(ip) or await self.store.count_unclaimed() >= self.cfg.max_unclaimed:
            return 429, {"status": "rejected", "message": "thử lại sau"}
        self.reg_ip.hit(ip)
        token, hsecret, pc = sec.gen_ea_token(), sec.gen_hmac_secret(), sec.gen_pairing_code()
        account_id = f"{platform}:{login}"
        try:
            await self.store.create_selfreg_account(
                account_id=account_id, platform=platform, login=login, server=server, pairing_hash=sec.hash_code(pc),
                pairing_expires=now() + timedelta(days=self.cfg.pairing_days), cred_enc=self.vault.enc(json.dumps({"token": token, "hmac": hsecret})),
                token_hash=sec.sha256_hex(token), hmac_enc=self.vault.enc(hsecret), remote_addr=ip, broker=broker,
                ea_version=str(info.get("ea") or ""), build=int(info.get("build") or 0) or None)
        except Exception:  # noqa: BLE001 (chạy đua trùng khoá)
            return 200, {"status": "rejected", "message": "tài khoản đã tồn tại"}
        await self.store.audit(None, "mt-bridge", "ea_self_registered", account_id, ip, {"server": server})
        return 200, {"status": "pending", "account_id": account_id, "pairing_code": pc, "message": "nhập mã này ở trang đăng nhập (Ghép cặp)"}

    async def ea_seen(self, items: list) -> int:
        def ts(v):
            if isinstance(v, (int, float)) and v > 0:
                return datetime.fromtimestamp(v, timezone.utc)
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        def num(v, f=int):
            try:
                return f(v) if v is not None else None
            except (TypeError, ValueError):
                return None
        rows = []
        for it in items[:500]:
            if not isinstance(it, dict) or not ACCOUNT_ID_RE.match(str(it.get("account_id") or "")):
                continue
            st = str(it.get("status") or "offline")
            rows.append({"account_id": it["account_id"], "last_seen_at": ts(it.get("last_seen_at")), "status": st if st in ("online", "degraded", "offline") else "offline",
                         "reason": str(it.get("reason") or "")[:60], "latency_ms": num(it.get("latency_ms")), "skew_s": num(it.get("skew_s"), float),
                         "ea_version": str(it.get("ea_version") or "")[:16], "build": num(it.get("build")), "broker": str(it.get("broker") or "")[:64],
                         "remote_addr": str(it.get("remote_addr") or "")[:64], "server": str(it.get("server") or "")[:64]})
        return await self.store.update_health(rows) if rows else 0

    async def ea_audit(self, account_id: str, action: str, detail) -> None:
        if not ACCOUNT_ID_RE.match(account_id or ""):
            return
        action = action if re.fullmatch(r"[a-z_]{1,40}", action or "") else "ea_event"
        d = detail if isinstance(detail, dict) and len(json.dumps(detail, default=str)) < 1000 else {}
        await self.store.audit(None, "mt-bridge", action, account_id, "", d)
