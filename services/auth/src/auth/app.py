"""API đăng nhập master/client (docs/AUTH.md). Mọi route dưới /auth/. nginx auth_request gọi GET /auth/verify (nội bộ, không công khai)."""
import asyncio
import contextlib
import hmac
import logging
import re
from importlib import resources
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_client import Counter
from pydantic import BaseModel, ConfigDict, Field, field_validator
from tscommon import make_app

from . import __version__
from . import roles as R
from .config import AuthSettings
from .fleet_api import register_fleet, start_background
from .service import AuthError, AuthService, Principal
from .store import Store

log = logging.getLogger("auth.app")

LOGINS = Counter("auth_logins_total", "Đăng nhập", ["result"])
SID_RE = r"^[0-9a-f]{64}$"
UUID_RE = r"^[0-9a-fA-F-]{36}$"
ACC_RE = r"^[\w.:\-]{1,64}$"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; "
       "base-uri 'none'; frame-ancestors 'none'")
STATIC = {"login.js": "application/javascript; charset=utf-8", "login.css": "text/css; charset=utf-8"}


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(_S):
    platform: Literal["master", "mt4", "mt5"]
    login: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._\-]+$")
    secret: str = Field(min_length=1, max_length=256)
    server: str | None = Field(default=None, max_length=64)
    totp: str | None = Field(default=None, max_length=12)

    @field_validator("login", mode="before")
    @classmethod
    def _login_str(cls, v):
        return str(v) if isinstance(v, int) else v


class ChangePwIn(_S):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PairIn(_S):
    platform: Literal["mt4", "mt5"]
    login: str = Field(min_length=1, max_length=16, pattern=r"^\d+$")
    pairing_code: str = Field(min_length=4, max_length=40)
    new_password: str = Field(min_length=1, max_length=256)
    server: str | None = Field(default=None, max_length=64)

    @field_validator("login", mode="before")
    @classmethod
    def _login_str(cls, v):
        return str(v) if isinstance(v, int) else v


class TotpEnableIn(_S):
    code: str = Field(min_length=6, max_length=12)


class TotpDisableIn(_S):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(default="", max_length=12)


class AccountIn(_S):
    platform: Literal["mt4", "mt5"]
    login: int = Field(gt=0, le=2**53)
    server: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=500)


class AccountPatch(_S):
    label: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)
    server: str | None = Field(default=None, max_length=64)


class LinkIn(_S):
    account_id: str = Field(pattern=ACC_RE)


class ViewAsIn(_S):
    account_id: str = Field(pattern=ACC_RE)


def client_ip(request: Request) -> str:
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    return re.sub(r"[^0-9a-fA-F.:]", "", ip)[:45]


def origin_ok(request: Request) -> bool:
    """CSRF cho route đổi trạng thái: Origin (nếu có) phải trùng host công khai; Sec-Fetch-Site: cross-site bị từ chối."""
    h = request.headers
    if h.get("sec-fetch-site", "") == "cross-site":
        return False
    origin = h.get("origin")
    if origin is None:
        return True      # không phải trình duyệt (curl/test nội bộ); cookie SameSite=Strict vẫn chặn gửi chéo site
    return re.sub(r"^https?://", "", origin) == (h.get("x-forwarded-host") or h.get("host", ""))


def create_app(settings: AuthSettings | None = None, service: AuthService | None = None) -> FastAPI:
    cfg = settings or AuthSettings()
    app = make_app("auth", __version__)
    app.title = "Trading System Auth"
    app.state.svc = service

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        own = False
        if _app.state.svc is None:
            if not cfg.db_url:
                raise RuntimeError("AUTH_DB_URL chưa đặt")
            _app.state.svc = AuthService(await Store.connect(cfg.db_url), cfg)
            own = True
            if not _app.state.svc.vault.ok:
                log.error("AUTH_SECRET_KEY thiếu/không hợp lệ: không thể tạo tài khoản MT / TOTP (đăng nhập vẫn hoạt động)")

        async def janitor():
            while True:
                await asyncio.sleep(3600)
                with contextlib.suppress(Exception):
                    await _app.state.svc.store.purge_sessions()
        task = asyncio.create_task(janitor())
        fleet_task = start_background(_app) if own else None     # quét sự cố mất EA / hết snooze (chỉ khi service tự tạo; test inject không chạy)
        try:
            yield
        finally:
            task.cancel()
            if fleet_task:
                fleet_task.cancel()
            if own:
                await _app.state.svc.store.close()

    app.router.lifespan_context = lifespan

    def svc() -> AuthService:
        return app.state.svc

    @app.middleware("http")
    async def sec_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.exception_handler(AuthError)
    async def auth_error(_r: Request, e: AuthError):
        h = {"Retry-After": str(e.extra["retry_after"])} if "retry_after" in e.extra else None
        body = {"detail": e.message, **{k: v for k, v in e.extra.items() if k != "retry_after"}}
        return JSONResponse(body, status_code=e.status, headers=h)

    def set_cookie(resp: Response, sid: str, role: str) -> None:
        ttl = (cfg.master_ttl_h if role == "master" else cfg.client_ttl_h) * 3600
        resp.set_cookie(cfg.cookie_name, sid, max_age=ttl, httponly=True, secure=cfg.cookie_secure, samesite="strict", path="/")

    def drop_cookie(resp: Response) -> None:
        resp.delete_cookie(cfg.cookie_name, path="/", httponly=True, secure=cfg.cookie_secure, samesite="strict")

    async def principal(request: Request) -> Principal:
        p = await svc().verify_session(request.cookies.get(cfg.cookie_name))
        if not p:
            raise HTTPException(401, "Chưa đăng nhập")
        return p

    async def active_principal(p: Annotated[Principal, Depends(principal)]) -> Principal:
        if p.must_change_password:
            raise HTTPException(403, "Cần đổi mật khẩu trước khi tiếp tục", headers={"X-Auth-Reason": "password_change_required"})
        return p

    async def master(p: Annotated[Principal, Depends(active_principal)]) -> Principal:
        if p.role != "master":
            raise HTTPException(403, "Chỉ master")
        return p

    async def csrf(request: Request) -> None:
        if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_ok(request):
            raise HTTPException(403, "origin")

    async def admin_any(p: Annotated[Principal, Depends(active_principal)]) -> Principal:
        if not R.is_admin_role(p.role):
            raise HTTPException(403, "Không có quyền")
        return p

    def perm(name: str):
        async def dep(p: Annotated[Principal, Depends(active_principal)]) -> Principal:
            if not R.has_perm(p.role, name):
                raise HTTPException(403, "Không đủ quyền")
            return p
        return dep

    Csrf = Depends(csrf)
    AdminAny = Annotated[Principal, Depends(admin_any)]
    AuditReader = Annotated[Principal, Depends(perm("audit.read"))]
    Any_ = Annotated[Principal, Depends(principal)]
    Active = Annotated[Principal, Depends(active_principal)]
    Master = Annotated[Principal, Depends(master)]

    # ------------------------------------------------------------ nginx auth_request (nội bộ)
    @app.get("/auth/verify", include_in_schema=False)
    async def verify(request: Request):
        uri = request.headers.get("x-original-uri", "")
        if svc().public_path(uri):
            return Response(status_code=200, headers={"X-Role": "anon", "X-User-Id": "-", "X-Accounts": ""})
        p = await svc().verify_session(request.cookies.get(cfg.cookie_name))
        if not p:
            return Response(status_code=401)
        if p.must_change_password and not uri.startswith("/auth/"):
            return Response(status_code=401, headers={"X-Auth-Reason": "password_change_required"})
        if svc().totp_gate(p, uri):
            return Response(status_code=401, headers={"X-Auth-Reason": "totp_setup_required"})
        accounts = ",".join(p.accounts)
        if len(accounts) > 3500:        # vượt bộ đệm header nginx -> từ chối (an toàn) thay vì cắt
            log.error("user %s có quá nhiều tài khoản cho header", p.login_key)
            return Response(status_code=500)
        return Response(status_code=200, headers={"X-User-Id": p.user_id, "X-Role": p.role, "X-Accounts": accounts})

    # ------------------------------------------------------------ trang đăng nhập tối giản (dự phòng; client-ui/web-ui có trang riêng)
    @app.get("/auth/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page():
        html = resources.files("auth").joinpath("web/login.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})

    @app.get("/auth/static/{name}", include_in_schema=False)
    async def static(name: str):
        if name not in STATIC:
            raise HTTPException(404)
        return Response(resources.files("auth").joinpath(f"web/{name}").read_bytes(), media_type=STATIC[name].split(";")[0],
                        headers={"Content-Security-Policy": CSP, "Cache-Control": "no-cache"})

    # ------------------------------------------------------------ phiên
    @app.post("/auth/login", dependencies=[Csrf], tags=["auth"], summary="Đăng nhập bằng ID MT (nền tảng + số tài khoản) hoặc master")
    async def login(body: LoginIn, request: Request):
        try:
            sid, p = await svc().login(body.platform, body.login, body.secret, body.server, body.totp, client_ip(request),
                                       request.headers.get("user-agent", ""))
        except AuthError as e:
            LOGINS.labels("totp" if e.extra.get("totp_required") else "fail").inc()
            raise
        LOGINS.labels("ok").inc()
        resp = JSONResponse({"ok": True, **p.me()})
        set_cookie(resp, sid, p.role)
        return resp

    @app.post("/auth/logout", dependencies=[Csrf], tags=["auth"])
    async def logout(request: Request):
        p = await svc().verify_session(request.cookies.get(cfg.cookie_name))
        if p:
            await svc().logout(p, client_ip(request))
        resp = JSONResponse({"ok": True})
        drop_cookie(resp)
        return resp

    @app.get("/auth/me", tags=["auth"], summary="Người dùng hiện tại + danh sách tài khoản MT được phép")
    async def me(p: Any_):
        return p.me()

    @app.post("/auth/change-password", dependencies=[Csrf], tags=["auth"])
    async def change_password(body: ChangePwIn, request: Request, p: Any_):
        await svc().change_password(p, body.current_password, body.new_password, client_ip(request))
        return {"ok": True}

    @app.post("/auth/pair", dependencies=[Csrf], tags=["auth"], summary="Ghép cặp lần đầu bằng mã (EA/master cấp) và đặt mật khẩu")
    async def pair(body: PairIn, request: Request):
        await svc().pair(body.platform, body.login, body.pairing_code, body.new_password, body.server, client_ip(request))
        return {"ok": True}

    @app.get("/auth/sessions", tags=["auth"], summary="Phiên đăng nhập của tôi")
    async def my_sessions(p: Active):
        return {"items": await svc().my_sessions(p)}

    @app.post("/auth/sessions/{sid}/revoke", dependencies=[Csrf], tags=["auth"])
    async def revoke_mine(sid: str, request: Request, p: Active):
        if not re.fullmatch(SID_RE, sid):
            raise HTTPException(404)
        if not await svc().revoke_my_session(p, sid, client_ip(request)):
            raise HTTPException(404, "Phiên không tồn tại")
        return {"ok": True}

    @app.post("/auth/logout-all", dependencies=[Csrf], tags=["auth"])
    async def logout_all(request: Request, p: Active):
        n = await svc().logout_all(p, client_ip(request))
        resp = JSONResponse({"ok": True, "revoked": n})
        drop_cookie(resp)
        return resp

    # ------------------------------------------------------------ TOTP (master)
    @app.post("/auth/totp/setup", dependencies=[Csrf], tags=["auth"])
    async def totp_setup(request: Request, p: AdminAny):
        return await svc().totp_setup(p, client_ip(request))

    @app.post("/auth/totp/enable", dependencies=[Csrf], tags=["auth"])
    async def totp_enable(body: TotpEnableIn, request: Request, p: AdminAny):
        await svc().totp_enable(p, body.code, client_ip(request))
        return {"ok": True}

    @app.post("/auth/totp/disable", dependencies=[Csrf], tags=["auth"])
    async def totp_disable(body: TotpDisableIn, request: Request, p: AdminAny):
        await svc().totp_disable(p, body.password, body.code, client_ip(request))
        return {"ok": True}

    # ------------------------------------------------------------ quản trị (chỉ master)
    adm = "/auth/admin"

    @app.get(f"{adm}/accounts", tags=["admin"])
    async def adm_accounts(_p: Master):
        return {"items": await svc().list_accounts()}

    @app.post(f"{adm}/accounts", dependencies=[Csrf], status_code=201, tags=["admin"], summary="Tạo tài khoản MT + client; trả passcode/pairing/EA token/HMAC MỘT lần")
    async def adm_create(body: AccountIn, request: Request, p: Master):
        return await svc().create_account(p, body.platform, body.login, body.server, body.label, body.notes, client_ip(request))

    @app.get(adm + "/accounts/{account_id}", tags=["admin"])
    async def adm_get(account_id: str, _p: Master):
        if not re.fullmatch(ACC_RE, account_id):
            raise HTTPException(404)
        return await svc().get_account(account_id)

    def acc_id(account_id: str) -> str:
        if not re.fullmatch(ACC_RE, account_id):
            raise HTTPException(404, "account_id không hợp lệ")
        return account_id

    @app.patch(adm + "/accounts/{account_id}", dependencies=[Csrf], tags=["admin"])
    async def adm_patch(account_id: str, body: AccountPatch, request: Request, p: Master):
        return await svc().update_account(p, acc_id(account_id), body.model_dump(), client_ip(request))

    @app.delete(adm + "/accounts/{account_id}", dependencies=[Csrf], tags=["admin"])
    async def adm_delete(account_id: str, request: Request, p: Master):
        return await svc().delete_account(p, acc_id(account_id), client_ip(request))

    @app.post(adm + "/accounts/{account_id}/suspend", dependencies=[Csrf], tags=["admin"])
    async def adm_suspend(account_id: str, request: Request, p: Master):
        return await svc().set_account_status(p, acc_id(account_id), True, client_ip(request))

    @app.post(adm + "/accounts/{account_id}/activate", dependencies=[Csrf], tags=["admin"])
    async def adm_activate(account_id: str, request: Request, p: Master):
        return await svc().set_account_status(p, acc_id(account_id), False, client_ip(request))

    @app.post(adm + "/accounts/{account_id}/reset-passcode", dependencies=[Csrf], tags=["admin"])
    async def adm_reset(account_id: str, request: Request, p: Master):
        return await svc().reset_passcode(p, acc_id(account_id), client_ip(request))

    @app.post(adm + "/accounts/{account_id}/rotate-ea-token", dependencies=[Csrf], tags=["admin"])
    async def adm_rot_token(account_id: str, request: Request, p: Master):
        return await svc().rotate_ea_token(p, acc_id(account_id), client_ip(request))

    @app.post(adm + "/accounts/{account_id}/rotate-hmac", dependencies=[Csrf], tags=["admin"])
    async def adm_rot_hmac(account_id: str, request: Request, p: Master):
        return await svc().rotate_hmac(p, acc_id(account_id), client_ip(request))

    @app.post(adm + "/accounts/{account_id}/pairing-code", dependencies=[Csrf], tags=["admin"])
    async def adm_pairing(account_id: str, request: Request, p: Master):
        return await svc().new_pairing_code(p, acc_id(account_id), client_ip(request))

    @app.get(f"{adm}/users", tags=["admin"])
    async def adm_users(_p: Master):
        return {"items": await svc().list_users()}

    @app.post(adm + "/users/{user_id}/{action}", dependencies=[Csrf], tags=["admin"], summary="unlock | revoke-sessions | suspend | activate")
    async def adm_user_action(user_id: str, action: str, request: Request, p: Master):
        if not re.fullmatch(UUID_RE, user_id):
            raise HTTPException(404)
        return await svc().user_action(p, user_id, action, client_ip(request))

    @app.post(adm + "/users/{user_id}/accounts", dependencies=[Csrf], tags=["admin"])
    async def adm_link(user_id: str, body: LinkIn, request: Request, p: Master):
        if not re.fullmatch(UUID_RE, user_id):
            raise HTTPException(404)
        await svc().link_account(p, user_id, body.account_id, client_ip(request))
        return {"ok": True}

    @app.delete(adm + "/users/{user_id}/accounts/{account_id}", dependencies=[Csrf], tags=["admin"])
    async def adm_unlink(user_id: str, account_id: str, request: Request, p: Master):
        if not re.fullmatch(UUID_RE, user_id):
            raise HTTPException(404)
        await svc().unlink_account(p, user_id, acc_id(account_id), client_ip(request))
        return {"ok": True}

    @app.get(f"{adm}/sessions", tags=["admin"])
    async def adm_sessions(_p: Master, user_id: Annotated[str | None, Query(pattern=UUID_RE)] = None, active: bool = True):
        return {"items": await svc().all_sessions(user_id, active)}

    @app.post(adm + "/sessions/{sid}/revoke", dependencies=[Csrf], tags=["admin"])
    async def adm_revoke(sid: str, request: Request, p: Master):
        if not re.fullmatch(SID_RE, sid):
            raise HTTPException(404)
        await svc().admin_revoke_session(p, sid, client_ip(request))
        return {"ok": True}

    @app.get(f"{adm}/audit", tags=["admin"])
    async def adm_audit(_p: AuditReader, limit: Annotated[int, Query(ge=1, le=500)] = 100, action: Annotated[str | None, Query(pattern=r"^[a-z_]{1,60}$")] = None,
                        before_id: Annotated[int | None, Query(ge=1, le=2147483647)] = None, target: Annotated[str | None, Query(max_length=200)] = None):
        rows = await svc().store.list_audit(limit, action, before_id, target)
        return {"items": [{**r, "actor_user_id": str(r["actor_user_id"]) if r["actor_user_id"] else None, "ts": r["ts"].isoformat()} for r in rows]}

    @app.get(f"{adm}/audit/verify", tags=["admin"], summary="Kiểm tra toàn vẹn chuỗi băm của audit_log")
    async def adm_audit_verify(_p: AuditReader):
        return await svc().store.verify_audit_chain()

    # xem-như-khách: xem fleet_api.py (lý do bắt buộc + hết hạn + audit)
    register_fleet(app, active=active_principal, csrf=csrf, client_ip=client_ip, cfg=cfg)

    # ------------------------------------------------------------ NỘI BỘ cho mt-bridge (token dịch vụ; KHÔNG route qua nginx công khai)
    async def internal_ok(request: Request) -> None:
        tok = cfg.internal_token
        if not tok:
            raise HTTPException(503, "service token chưa cấu hình")
        supplied = request.headers.get("authorization", "")
        if not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:].strip().encode(), tok.encode()):
            raise HTTPException(401, "unauthorized")

    Internal = Depends(internal_ok)

    @app.get("/internal/mt-accounts", dependencies=[Internal], include_in_schema=False)
    async def int_list():
        return await svc().internal_list()

    @app.post("/internal/mt-accounts/register", dependencies=[Internal], include_in_schema=False)
    async def int_register(body: dict):
        st, out = await svc().ea_register(body)
        return JSONResponse(out, status_code=st, headers={"Cache-Control": "no-store"})

    @app.post("/internal/mt-accounts/seen", dependencies=[Internal], include_in_schema=False)
    async def int_seen(body: dict):
        items = body.get("items")
        return {"updated": await svc().ea_seen(items if isinstance(items, list) else [])}

    @app.post("/internal/mt-accounts/audit", dependencies=[Internal], include_in_schema=False)
    async def int_audit(body: dict):
        await svc().ea_audit(str(body.get("account_id") or ""), str(body.get("action") or ""), body.get("detail"))
        return {"ok": True}

    @app.get("/internal/mt-accounts/{account_id}", dependencies=[Internal], include_in_schema=False)
    async def int_get(account_id: str):
        rec = await svc().internal_get(account_id) if re.fullmatch(ACC_RE, account_id) else None
        if rec is None:
            raise HTTPException(404, "không có tài khoản")
        return rec

    @app.get("/readyz", include_in_schema=False)
    async def readyz():
        try:
            ok = await asyncio.wait_for(svc().store.ping(), 3)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            raise HTTPException(503, "db unavailable")
        return {"status": "ready"}

    return app
