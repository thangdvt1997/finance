"""Giao thuc ingest v1 (EA -> bridge). Xem mt-agent/README.md.

POST /ingest/v1
  Authorization: Bearer <token cua tai khoan>
  X-MT-Account: <account_id>
  X-MT-Sig: hex(HMAC_SHA256(secret, f"{ts}.{nonce}.{raw_body}"))   # chi khi tai khoan bat hmac
Body = JSON `Batch` (duoi day). Heartbeat = Batch chi co ts/nonce.
Chong replay: ts phai trong +-skew giay cua dong ho bridge VA nonce chua tung thay (trong cua so).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SYMBOL_RE = r"^[A-Za-z0-9._#+\-]{1,32}$"
NONCE_RE = r"^[A-Za-z0-9_\-]{8,64}$"
MAX_BODY_BYTES = 1_000_000


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AccountIn(_S):
    login: int = Field(ge=0)
    server: str = Field(default="", max_length=64)
    currency: str = Field(default="", max_length=8)
    leverage: int = Field(default=0, ge=0)
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: Optional[float] = None
    margin_mode: Literal["hedging", "netting", "unknown"] = "unknown"
    trade_allowed: Optional[bool] = None  # EA bao: tai khoan co cho phep giao dich khong (canh bao neu True)


class PositionIn(_S):
    ticket: int
    symbol: str = Field(pattern=SYMBOL_RE)
    type: Literal[0, 1]  # 0 buy, 1 sell
    lots: float = Field(gt=0)
    open_price: float
    price: float
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    magic: int = 0
    comment: str = Field(default="", max_length=64)
    open_time: int  # epoch gio server


class OrderIn(_S):
    ticket: int
    symbol: str = Field(pattern=SYMBOL_RE)
    type: Literal[2, 3, 4, 5, 6, 7]  # 2 buylimit 3 selllimit 4 buystop 5 sellstop (6,7 stoplimit MT5)
    lots: float = Field(ge=0)
    price: float
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 0
    comment: str = Field(default="", max_length=64)
    setup_time: int


class QuoteIn(_S):
    symbol: str = Field(pattern=SYMBOL_RE)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    time: float  # epoch gio server (EA feed gui mili-giay giay.mmm; EA cu gui so nguyen)


class BarIn(_S):
    symbol: str = Field(pattern=SYMBOL_RE)
    tf: Literal["M1", "M5", "M15", "H1", "H4", "D1"]
    time: int  # epoch gio server cua mo nen
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


DEAL_REASONS = ("", "sl", "tp", "so", "expert", "client")


class DealIn(_S):
    """Lenh/deal DA DONG (lich su). 1 dong = 1 giao dich dong (MT4: 1 order dong; MT5: 1 deal DEAL_ENTRY_OUT/OUT_BY/INOUT,
    gop gia/thoi gian mo tu cac deal IN cung position). type 2 = thao tac so du (nap/rut/credit/phi...; profit = so tien).
    Khoa tu nhien: (account_id, ticket) -> bridge/DB upsert idempotent. READ-ONLY: chi mo ta lich su, khong the dung de dat lenh."""

    ticket: int = Field(ge=0)
    position_id: int = Field(default=0, ge=0)  # MT5: POSITION_IDENTIFIER; MT4: = ticket
    symbol: str = Field(default="", pattern=r"^(|[A-Za-z0-9._#+-]{1,32})$")  # rong khi type=2
    type: Literal[0, 1, 2]  # 0 buy, 1 sell (huong cua VI THE da dong), 2 balance op
    lots: float = Field(default=0.0, ge=0)
    open_price: float = 0.0
    close_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    open_time: int = Field(ge=0)  # epoch gio server
    close_time: int = Field(gt=0)  # epoch gio server
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    magic: int = 0
    comment: str = Field(default="", max_length=64)
    reason: Literal["", "sl", "tp", "so", "expert", "client"] = ""


ACCOUNT_ID_RE = r"^[A-Za-z0-9_\-:]{1,64}$"   # `<platform>:<login>` (vd mt5:12345678) hoac id tuy y (tai khoan YAML cu)


class AgentIn(_S):
    """Thong tin suc khoe EA (tuy chon, moi batch): master hien thi 'suc khoe EA'. KHONG chua bi mat."""

    ea: str = Field(default="", max_length=16)  # phien ban EA
    build: int = Field(default=0, ge=0)  # build terminal
    company: str = Field(default="", max_length=64)  # ten broker (ACCOUNT_COMPANY)
    rtt_ms: int = Field(default=0, ge=0, le=600_000)  # do tre WebRequest cua lan gui truoc (EA do)
    fail: int = Field(default=0, ge=0, le=1_000_000)  # so lan gui loi lien tiep truoc do


class Batch(_S):
    v: Literal[1]
    account_id: str = Field(pattern=ACCOUNT_ID_RE)
    platform: Literal["mt4", "mt5"]
    ts: int  # epoch UTC (TimeGMT())
    server_time: Optional[int] = None  # TimeCurrent() - dung suy ra offset gio server neu khong cau hinh tz
    nonce: str = Field(pattern=NONCE_RE)
    seq: int = 0
    account: Optional[AccountIn] = None
    positions: Optional[list[PositionIn]] = Field(default=None, max_length=500)
    orders: Optional[list[OrderIn]] = Field(default=None, max_length=500)
    quotes: list[QuoteIn] = Field(default_factory=list, max_length=400)
    bars: list[BarIn] = Field(default_factory=list, max_length=2000)
    deals: Optional[list[DealIn]] = Field(default=None, max_length=500)  # lich su da dong theo lo co con tro (EA giu cursor)
    agent: Optional[AgentIn] = None  # suc khoe EA (phien ban, build, broker, rtt)


class RegisterIn(_S):
    """POST /ingest/v1/register: EA tu khai bao lan dau / ghep cap. Co the khong co token (che do PairCode) hoac co token (bao cap nhat)."""

    v: Literal[1] = 1
    platform: Literal["mt4", "mt5"]
    login: int = Field(ge=0)
    server: str = Field(default="", max_length=64)
    company: str = Field(default="", max_length=64)
    build: int = Field(default=0, ge=0)
    ea: str = Field(default="", max_length=16)
    pair_code: str = Field(default="", pattern=r"^[A-Za-z0-9\-]{0,32}$")
    account_id: str = Field(default="", pattern=r"^[A-Za-z0-9_\-:]{0,64}$")
    ts: int = 0
    nonce: str = Field(default="", pattern=r"^[A-Za-z0-9_\-]{0,64}$")


class AuthError(Exception):
    def __init__(self, code: int, msg: str, retry_after: float = 0.0):
        super().__init__(msg)
        self.code, self.msg, self.retry_after = code, msg, retry_after


class NonceCache:
    """Nho nonce trong `window` giay (chi luu trong RAM; restart bridge -> van chan boi ts-skew)."""

    def __init__(self, window_s: float = 300.0, max_items: int = 100_000, clock=time.time):
        self.window, self.max_items, self.clock = window_s, max_items, clock
        self._seen: dict[tuple[str, str], float] = {}
        self._last_purge = 0.0

    def check_and_add(self, account: str, nonce: str) -> bool:
        now = self.clock()
        if len(self._seen) > self.max_items or now - self._last_purge > 30:
            self._purge(now)
        k = (account, nonce)
        exp = self._seen.get(k)
        if exp is not None and exp > now:
            return False
        self._seen[k] = now + self.window
        return True

    def _purge(self, now: float) -> None:
        self._last_purge = now
        self._seen = {k: e for k, e in self._seen.items() if e > now}


def sign(secret: str, ts: int, nonce: str, raw_body: bytes) -> str:
    msg = f"{ts}.{nonce}.".encode() + raw_body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    """Bam token EA (token ngau nhien >=128 bit -> SHA-256 du; khong can KDF cham). Dung chung voi service auth (`ea_token_hash`)."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(expected_hash: str, presented: str) -> bool:
    """So sanh hang so thoi gian bam(presented) voi bam luu tru. Rong -> False."""
    if not expected_hash or not presented:
        return False
    return hmac.compare_digest(hash_token(presented), expected_hash.lower())


def verify_token(expected: str, presented: str) -> bool:
    if not expected or not presented:
        return False
    return hmac.compare_digest(hashlib.sha256(expected.encode()).digest(), hashlib.sha256(presented.encode()).digest())


def verify_sig(secret: str, ts: int, nonce: str, raw_body: bytes, presented: str) -> bool:
    return hmac.compare_digest(sign(secret, ts, nonce, raw_body), presented or "")
