"""AccountRegistry: nguon cau hinh/xac thuc tai khoan EA cho mt-bridge (READ-ONLY).

Quyet dinh thiet ke (docs/CLIENT_PLATFORM.md "Giao uoc noi bo mt-bridge <-> auth"):
- KHONG doc DB cua service khac (CONTRACTS.md). mt-bridge goi HTTP noi bo `auth:8000/internal/mt-accounts*` bang token dich vu
  (`BRIDGE_AUTH_TOKEN`), cache RAM TTL ngan (`BRIDGE_AUTH_TTL_S`, mac dinh 15s) + endpoint thu hoi tuc thi `POST /internal/invalidate`.
- Ba hien thuc: StaticRegistry (accounts.yaml, tuong thich), HttpRegistry (auth), InMemoryRegistry (test); CompositeRegistry
  ghep (dong truoc, tinh sau). Token EA chi luu dang BAM (sha256); so sanh hang so thoi gian; secret HMAC chi o RAM.
- Stale-if-error: auth tam thoi down -> dung ban cache toi `max_stale_s` (mac dinh 10 phut) roi fail-closed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .accounts import AccountConfig, BridgeConfig
from .protocol import hash_token

log = logging.getLogger("mtbridge.registry")

STATUSES = ("pending", "active", "suspended")
# khoa cau hinh tuy chon master/auth duoc phep ghi de cho tai khoan dong (khong cho dat token/transport/mat khau)
CONFIG_OVERRIDE_KEYS = {"symbol_prefix", "symbol_suffix", "symbol_aliases", "watch_symbols", "timeframes", "server_tz", "server_utc_offset_hours", "rules"}


@dataclass
class AccountRecord:
    account_id: str
    platform: str
    cfg: AccountConfig
    status: str = "active"            # pending | active | suspended
    token_hash: str = ""              # sha256 hex cua token EA ("" = chua co token -> khong xac thuc duoc)
    hmac_secret: str = ""             # secret HMAC (chi RAM)
    require_hmac: Optional[bool] = None  # None = suy theo cau hinh toan cuc/co secret
    rev: int = 0
    source: str = "auth"              # yaml | auth | mem


@dataclass
class RegisterResult:
    status: str                       # unknown | pending | active | suspended | rejected | rate_limited | error
    account_id: str = ""
    message: str = ""
    pairing_code: str = ""            # ma ghep cap de EA hien thi cho client (nhap o cong /c/ hoac dua master)
    token: str = ""                   # CHI tra 1 lan khi ghep cap thanh cong (auth quyet dinh)
    hmac_secret: str = ""

    def public(self) -> dict:
        d: dict[str, Any] = {"ok": self.status in ("pending", "active"), "status": self.status}
        for k in ("account_id", "message", "pairing_code", "token", "hmac_secret"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d


def record_from_dict(d: dict) -> AccountRecord:
    """Parse ban ghi tu auth (`GET /internal/mt-accounts`). Thieu truong an toan -> mac dinh an toan (pending/HMAC bat)."""
    aid, platform = str(d["account_id"]), str(d["platform"])
    status = d.get("status", "pending")
    if status not in STATUSES:
        status = "suspended"  # gia tri la -> fail-closed
    over = {k: v for k, v in (d.get("config") or {}).items() if k in CONFIG_OVERRIDE_KEYS}
    try:
        cfg = AccountConfig(account_id=aid, platform=platform, transport="agent", **over)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        log.warning("config ghi de cua %s khong hop le (%s) -> dung mac dinh", aid, type(e).__name__)
        cfg = AccountConfig(account_id=aid, platform=platform, transport="agent")  # type: ignore[arg-type]
    req = d.get("require_hmac", True)  # HMAC BAT mac dinh cho tai khoan dong
    return AccountRecord(
        account_id=aid, platform=platform, cfg=cfg, status=status,
        token_hash=str(d.get("ea_token_hash") or d.get("token_hash") or "").lower(),
        hmac_secret=str(d.get("hmac_secret") or ""), require_hmac=None if req is None else bool(req),
        rev=int(d.get("rev") or 0), source="auth",
    )


class AccountRegistry(ABC):
    """get() dong bo (doc cache RAM, nong tren duong ingest); ensure()/refresh()/register()... bat dong bo (co the cham mang)."""

    @abstractmethod
    def get(self, account_id: str) -> Optional[AccountRecord]: ...

    @abstractmethod
    def ids(self) -> list[str]: ...

    async def ensure(self, account_id: str) -> None:  # lam moi cache neu thieu/cu (mac dinh: khong lam gi)
        return None

    async def refresh(self) -> None:
        return None

    def invalidate(self, account_id: str) -> None:
        return None

    @property
    def healthy(self) -> bool:
        return True

    async def register(self, info: dict) -> RegisterResult:
        return RegisterResult("unknown", message="dang ky dong khong duoc bat (registry tinh)")

    async def report_seen(self, items: list[dict]) -> None:
        return None

    async def audit(self, account_id: str, action: str, detail: dict) -> None:
        log.warning("audit %s %s %s", account_id, action, detail)


# --------------------------------------------------------------------------------------------- YAML (tinh)
class StaticRegistry(AccountRegistry):
    """accounts.yaml: token/secret doc tu bien moi truong luc get() (xoay env + restart/recreate la du)."""

    def __init__(self, cfg: BridgeConfig):
        self._cfgs = {a.account_id: a for a in cfg.accounts if a.transport == "agent"}

    def get(self, account_id: str) -> Optional[AccountRecord]:
        c = self._cfgs.get(account_id)
        if c is None:
            return None
        tok = c.token()
        req = c.require_hmac if c.require_hmac is not None else (True if c.hmac_secret_env else None)  # co khai bao env HMAC => bat buoc (fail-closed neu env rong)
        return AccountRecord(c.account_id, c.platform, c, "active", hash_token(tok) if tok else "", c.hmac_secret(), req, 0, "yaml")

    def ids(self) -> list[str]:
        return list(self._cfgs)


# --------------------------------------------------------------------------------------------- in-memory (test)
class InMemoryRegistry(AccountRegistry):
    """Mo phong auth service: tao tai khoan, xoay token/HMAC, dinh chi, ma ghep cap 1 lan. Dung cho test/loadtest."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._recs: dict[str, AccountRecord] = {}
        self._codes: dict[str, str] = {}      # hash(pair_code) -> account_id
        self._delivered: set[str] = set()     # account_id da nhan credential qua ghep cap
        self.seen: list[dict] = []
        self.audits: list[tuple[str, str, dict]] = []
        self.available = True

    def create(self, platform: str, login: int, *, status: str = "pending", require_hmac: Optional[bool] = True, config: Optional[dict] = None) -> dict:
        aid = f"{platform}:{login}"
        token, hsec, code = secrets.token_urlsafe(32), secrets.token_hex(32), secrets.token_hex(4).upper()
        over = {k: v for k, v in (config or {}).items() if k in CONFIG_OVERRIDE_KEYS}
        cfg = AccountConfig(account_id=aid, platform=platform, transport="agent", **over)  # type: ignore[arg-type]
        self._recs[aid] = AccountRecord(aid, platform, cfg, status, hash_token(token), hsec, require_hmac, 1, "mem")
        self._codes[hash_token(code)] = aid
        return {"account_id": aid, "token": token, "hmac_secret": hsec, "pair_code": code}

    def get(self, account_id: str) -> Optional[AccountRecord]:
        return self._recs.get(account_id) if self.available else None

    def ids(self) -> list[str]:
        return list(self._recs)

    @property
    def healthy(self) -> bool:
        return self.available

    def set_status(self, account_id: str, status: str) -> None:
        r = self._recs[account_id]
        r.status, r.rev = status, r.rev + 1

    def rotate_token(self, account_id: str) -> str:
        r = self._recs[account_id]
        tok = secrets.token_urlsafe(32)
        r.token_hash, r.rev = hash_token(tok), r.rev + 1
        return tok

    def rotate_hmac(self, account_id: str) -> str:
        r = self._recs[account_id]
        r.hmac_secret, r.rev = secrets.token_hex(32), r.rev + 1
        return r.hmac_secret

    async def register(self, info: dict) -> RegisterResult:
        code = info.get("pair_code", "")
        aid = self._codes.get(hash_token(code)) if code else None
        if aid is None:
            return RegisterResult("rejected", message="ma ghep cap khong hop le hoac da het han")
        r = self._recs[aid]
        if (r.platform, int(aid.split(":")[1])) != (info.get("platform"), int(info.get("login", -1))):
            return RegisterResult("rejected", message="ma ghep cap khong khop tai khoan")
        if r.status == "suspended":
            return RegisterResult("suspended", aid, "tai khoan bi dinh chi")
        if aid in self._delivered:
            return RegisterResult(r.status, aid, "credential da cap truoc do (xoay token tren master de cap lai)")
        self._delivered.add(aid)
        self._codes.pop(hash_token(code), None)  # dung 1 lan
        tok = self.rotate_token(aid)             # token chi hien 1 lan: sinh moi o thoi diem giao
        if r.status == "pending":
            r.status = "active"
        return RegisterResult(r.status, aid, "ghep cap thanh cong", token=tok, hmac_secret=r.hmac_secret)

    async def report_seen(self, items: list[dict]) -> None:
        self.seen.extend(items)

    async def audit(self, account_id: str, action: str, detail: dict) -> None:
        self.audits.append((account_id, action, detail))


# --------------------------------------------------------------------------------------------- HTTP -> auth
Fetch = Callable[[str, str, Optional[dict]], Awaitable[tuple[int, Any]]]


class HttpRegistry(AccountRegistry):
    def __init__(self, base_url: str, service_token: str, *, ttl_s: float = 15.0, max_stale_s: float = 600.0, timeout_s: float = 3.0,
                 clock: Callable[[], float] = time.time, fetch: Optional[Fetch] = None):
        self.base, self.token, self.ttl, self.max_stale, self.timeout, self.clock = base_url.rstrip("/"), service_token, ttl_s, max_stale_s, timeout_s, clock
        self._fetch = fetch or self._urllib_fetch
        self._cache: dict[str, tuple[AccountRecord, float]] = {}
        self._neg: dict[str, float] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._ok = True

    # ---- transport (stdlib, chay trong thread: khong them phu thuoc httpx vao image) ----
    async def _urllib_fetch(self, method: str, path: str, body: Optional[dict]) -> tuple[int, Any]:
        def run() -> tuple[int, Any]:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - URL noi bo tu cau hinh
                    raw = r.read(8_000_000)
                    return r.status, (json.loads(raw) if raw else None)
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read(1_000_000) or b"null")
                except Exception:  # noqa: BLE001
                    return e.code, None
        return await asyncio.to_thread(run)

    # ---- cache ----
    def get(self, account_id: str) -> Optional[AccountRecord]:
        e = self._cache.get(account_id)
        if e is None or self.clock() - e[1] > self.max_stale:
            return None
        return e[0]

    def ids(self) -> list[str]:
        now = self.clock()
        return [k for k, (_, t) in self._cache.items() if now - t <= self.max_stale]

    @property
    def healthy(self) -> bool:
        return self._ok

    def invalidate(self, account_id: str) -> None:
        self._cache.pop(account_id, None)
        self._neg.pop(account_id, None)

    async def refresh(self) -> None:
        try:
            st, data = await self._fetch("GET", "/internal/mt-accounts", None)
            if st != 200 or not isinstance(data, dict):
                raise RuntimeError(f"HTTP {st}")
            now, new = self.clock(), {}
            for d in data.get("accounts", []):
                try:
                    rec = record_from_dict(d)
                except Exception:  # noqa: BLE001 - 1 ban ghi hong khong lam hong ca danh sach
                    log.warning("bo qua ban ghi tai khoan hong")
                    continue
                new[rec.account_id] = (rec, now)
            self._cache = new
            self._ok = True
        except Exception as e:  # noqa: BLE001
            self._ok = False
            log.warning("lam moi danh sach tai khoan tu auth that bai: %s (dung cache toi %ss)", type(e).__name__, self.max_stale)

    async def ensure(self, account_id: str) -> None:
        now = self.clock()
        e = self._cache.get(account_id)
        if e is not None and now - e[1] <= self.ttl * 2:
            return  # refresh() dinh ky giu cache moi; chi hoi le khi thieu/cu bat thuong
        if self._neg.get(account_id, 0) > now:
            return
        fut = self._inflight.get(account_id)
        if fut is not None:
            await asyncio.shield(fut)
            return
        fut = asyncio.get_running_loop().create_future()
        self._inflight[account_id] = fut
        try:
            st, data = await self._fetch("GET", "/internal/mt-accounts/" + urllib.parse.quote(account_id, safe=""), None)
            if st == 200 and isinstance(data, dict):
                self._cache[account_id] = (record_from_dict(data), self.clock())
                self._ok = True
            elif st == 404:
                self._cache.pop(account_id, None)
                self._neg[account_id] = self.clock() + 5.0  # chong do quet tai khoan la
                self._ok = True
            else:
                raise RuntimeError(f"HTTP {st}")
        except Exception as ex:  # noqa: BLE001
            self._ok = False
            log.warning("tra cuu %s that bai: %s", account_id, type(ex).__name__)
        finally:
            self._inflight.pop(account_id, None)
            fut.set_result(None)

    async def register(self, info: dict) -> RegisterResult:
        try:
            st, data = await self._fetch("POST", "/internal/mt-accounts/register", info)
        except Exception as e:  # noqa: BLE001
            return RegisterResult("error", message=f"auth khong kha dung ({type(e).__name__})")
        if st == 429:
            return RegisterResult("rate_limited", message="thu lai sau")
        if not isinstance(data, dict) or st >= 500:
            return RegisterResult("error", message=f"auth loi HTTP {st}")
        status = data.get("status", "rejected")
        return RegisterResult(
            status if status in ("unknown", "pending", "active", "suspended", "rejected") else "rejected",
            str(data.get("account_id") or ""), str(data.get("message") or "")[:200], str(data.get("pairing_code") or "")[:32],
            str(data.get("token") or ""), str(data.get("hmac_secret") or ""),
        )

    async def report_seen(self, items: list[dict]) -> None:
        if not items:
            return
        try:
            st, _ = await self._fetch("POST", "/internal/mt-accounts/seen", {"items": items})
            if st >= 400:
                log.warning("report_seen -> HTTP %s", st)
        except Exception as e:  # noqa: BLE001
            log.warning("report_seen that bai: %s", type(e).__name__)

    async def audit(self, account_id: str, action: str, detail: dict) -> None:
        log.warning("audit %s %s %s", account_id, action, detail)
        try:
            await self._fetch("POST", "/internal/mt-accounts/audit", {"account_id": account_id, "action": action, "detail": detail})
        except Exception as e:  # noqa: BLE001
            log.warning("audit gui that bai: %s", type(e).__name__)


# --------------------------------------------------------------------------------------------- ghep
class CompositeRegistry(AccountRegistry):
    """Dong (auth) uu tien, tinh (YAML) du phong/tuong thich. Tai khoan YAML cu van chay khi chua co auth."""

    def __init__(self, dynamic: AccountRegistry, static: AccountRegistry):
        self.dynamic, self.static = dynamic, static

    def get(self, account_id: str) -> Optional[AccountRecord]:
        return self.dynamic.get(account_id) or self.static.get(account_id)

    def ids(self) -> list[str]:
        return sorted(set(self.dynamic.ids()) | set(self.static.ids()))

    async def ensure(self, account_id: str) -> None:
        await self.dynamic.ensure(account_id)

    async def refresh(self) -> None:
        await self.dynamic.refresh()

    def invalidate(self, account_id: str) -> None:
        self.dynamic.invalidate(account_id)

    @property
    def healthy(self) -> bool:
        return self.dynamic.healthy

    async def register(self, info: dict) -> RegisterResult:
        return await self.dynamic.register(info)

    async def report_seen(self, items: list[dict]) -> None:
        await self.dynamic.report_seen([i for i in items if self.dynamic.get(i["account_id"]) is not None])

    async def audit(self, account_id: str, action: str, detail: dict) -> None:
        await self.dynamic.audit(account_id, action, detail)
