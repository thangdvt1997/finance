"""Myfxbook - API CHINH THUC, chi cho tai khoan CUA BAN (login email/password trong env).

API: login.json, get-my-accounts.json, get-open-trades.json, get-history.json (myfxbook.com/api).
Gioi han free ~100 req/24h -> mac dinh cache lau; phien gan IP. Khong co endpoint bang xep hang cong khai
-> nguon nay KHONG dung de 'tim chuyen gia moi'; chi theo doi tai khoan Myfxbook ban co quyen (vd tai khoan
cua cong dong/ban be da chia se). TAT MAC DINH (can MYFXBOOK_EMAIL/PASSWORD)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..httpclient import PoliteClient
from ..models import ExpertInfo, PositionInfo, normalize_symbol
from .base import ExpertSource

BASE = "https://www.myfxbook.com/api"


class MyfxbookError(Exception):
    pass


def parse_login(text: str) -> str:
    d = json.loads(text)
    if d.get("error"):
        raise MyfxbookError(d.get("message", "login failed"))
    return d["session"]


def _months_since(first: str | None, now: datetime) -> float:
    if not first:
        return 0.0
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(first, fmt).replace(tzinfo=timezone.utc)
            return round((now - dt).days / 30.44, 1)
        except ValueError:
            continue
    return 0.0


def parse_accounts(text: str, now: datetime | None = None) -> list[ExpertInfo]:
    now = now or datetime.now(timezone.utc)
    d = json.loads(text)
    if d.get("error"):
        raise MyfxbookError(d.get("message", "error"))
    out = []
    for a in d.get("accounts", []):
        out.append(ExpertInfo(
            expert_id=f"myfxbook:{a['id']}", source="myfxbook", display_name=a.get("name", ""),
            url=f"https://www.myfxbook.com/members/{a.get('username','')}/{a['id']}" if a.get("username") else "",
            reputation={"gain_pct": a.get("gain"), "max_drawdown_pct": a.get("drawdown"),
                        "months_active": _months_since(a.get("firstTradeDate"), now), "followers": 0,
                        "demo": bool(a.get("demo"))}))
    return out


def parse_open_trades(text: str) -> list[PositionInfo]:
    d = json.loads(text)
    if d.get("error"):
        raise MyfxbookError(d.get("message", "error"))
    out = []
    for t in d.get("openTrades", []):
        side = str(t.get("action", "")).lower()
        if side not in ("buy", "sell"):
            continue
        try:
            opened = datetime.strptime(t["openTime"], "%m/%d/%Y %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            opened = None
        sz = t.get("sizing") or {}
        out.append(PositionInfo(symbol=normalize_symbol(t.get("symbol", "")), side=side,
                                volume=float(sz.get("value", t.get("size", 0)) or 0), entry=t.get("openPrice"),
                                sl=t.get("sl") or None, tp=t.get("tp") or None, opened_at=opened,
                                ticket=str(t.get("openOrderId", ""))))
    return out


def parse_history(text: str) -> list[dict]:
    d = json.loads(text)
    return [{"volume": float((h.get("sizing") or {}).get("value", 0) or 0), "profit": float(h.get("profit", 0))}
            for h in d.get("history", [])]


class MyfxbookSource(ExpertSource):
    name = "myfxbook"
    supports_positions = True
    tos_risk = "medium"
    warning = "API chinh thuc, chi tai khoan cua ban; free 100 req/24h; chia se du lieu phai theo ToS Myfxbook."

    def __init__(self, client: PoliteClient, email: str, password: str):
        self.client, self.email, self.password = client, email, password
        self._session: str | None = None

    async def _get(self, ep: str, **params) -> str:
        if self._session is None:
            self._session = parse_login(await self.client.get_text(
                f"{BASE}/login.json", {"email": self.email, "password": self.password}, cache=False, robots=False))
        return await self.client.get_text(f"{BASE}/{ep}.json", {"session": self._session, **params}, robots=False)

    async def list_experts(self) -> list[ExpertInfo]:
        if not (self.email and self.password):
            return []
        return parse_accounts(await self._get("get-my-accounts"))

    async def fetch_positions(self, expert: ExpertInfo) -> list[PositionInfo]:
        return parse_open_trades(await self._get("get-open-trades", id=expert.expert_id.split(":", 1)[1]))

    async def fetch_trades(self, expert: ExpertInfo) -> list[dict]:
        return parse_history(await self._get("get-history", id=expert.expert_id.split(":", 1)[1]))
