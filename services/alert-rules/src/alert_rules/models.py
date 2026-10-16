"""Mô hình + kiểm tra dữ liệu quy tắc cảnh báo và tuỳ chọn người dùng. Mọi đầu vào từ trình duyệt đều đi qua đây (extra=forbid)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYMBOL_RE = r"^[A-Za-z0-9:._\-]{1,32}$"
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
CHANNELS = ("ntfy", "log", "telegram", "app", "push")   # app/push: kênh theo người dùng (thông báo trong ứng dụng / Web Push); ntfy/log/telegram: kênh toàn cục của master
STATE_VALUES = {
    "trend": ("up", "down", "side"),
    "momentum": ("overbought", "oversold", "bullish", "bearish", "neutral"),
    "volatility": ("squeeze", "high", "normal", "low"),
}
MAX_RULES = 50                       # quy tắc của master (toàn cục)
MAX_RULES_USER = 20                  # mỗi client
MAX_CLIENT_RULES_TOTAL = 2000        # tổng quy tắc client (chặn lạm dụng tài nguyên đánh giá)
MAX_CONDITIONS = 8
MAX_VALUE = 1e12
LIMITS = {"max_rules": MAX_RULES, "max_conditions": MAX_CONDITIONS, "channels": list(CHANNELS)}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _finite(v: float) -> float:
    if not math.isfinite(v) or abs(v) > MAX_VALUE:
        raise ValueError("giá trị phải là số hữu hạn")
    return float(v)


Symbol = Annotated[str, Field(pattern=SYMBOL_RE)]
Tf = Literal["M1", "M5", "M15", "H1", "H4", "D1"]
Num = Annotated[float, Field(allow_inf_nan=False)]


class PriceCond(_Strict):
    type: Literal["price"]
    symbol: Symbol
    op: Literal["gte", "lte", "cross_up", "cross_down"]
    value: Num

    _v = field_validator("value")(_finite)


class PctChangeCond(_Strict):
    type: Literal["pct_change"]
    symbol: Symbol
    window_min: int = Field(ge=1, le=1440)
    op: Literal["gte", "lte", "abs_gte"]
    value: Num

    _v = field_validator("value")(_finite)


class IndicatorCond(_Strict):
    type: Literal["indicator"]
    symbol: Symbol
    tf: Tf
    field: Literal["rsi", "adx", "stoch_k", "bb_pctb", "ema200_dist_pct", "atr_pct", "macd_hist", "heat", "bias"]
    op: Literal["gte", "lte"]
    value: Num

    _v = field_validator("value")(_finite)


class StateCond(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)
    type: Literal["state"]
    symbol: Symbol
    tf: Tf
    field: Literal["trend", "momentum", "volatility"]
    is_: str = Field(alias="is", max_length=16)

    @model_validator(mode="after")
    def _chk(self):
        if self.is_ not in STATE_VALUES[self.field]:
            raise ValueError(f"{self.field} phải thuộc {'|'.join(STATE_VALUES[self.field])}")
        return self


class NewsWindowCond(_Strict):
    type: Literal["news_window"]
    impact: Literal["high", "med"]
    within_min: int = Field(ge=5, le=720)
    country: str | None = Field(default=None, max_length=8, pattern=r"^[A-Za-z]{2,8}$")
    phase: Literal["upcoming", "active"] = "upcoming"


class SentimentCond(_Strict):
    type: Literal["sentiment"]
    symbol: Symbol
    window_h: int = Field(ge=1, le=72)
    op: Literal["gte", "lte", "flip_up", "flip_down"]
    value: Num = 0.0

    @field_validator("value")
    @classmethod
    def _rng(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError("sentiment phải trong [-1, 1]")
        return float(v)


class AccountCond(_Strict):
    type: Literal["account"]
    account_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.:\-]{1,64}$")
    metric: Literal["margin_level", "equity_drawdown_24h", "floating_pl_pct"]
    op: Literal["gte", "lte"]
    value: Num

    _v = field_validator("value")(_finite)


Cond = Annotated[Union[PriceCond, PctChangeCond, IndicatorCond, StateCond, NewsWindowCond, SentimentCond, AccountCond],
                 Field(discriminator="type")]


class RuleIn(_Strict):
    name: str = Field(min_length=1, max_length=60)
    enabled: bool = True
    logic: Literal["and", "or"] = "and"
    conditions: list[Cond] = Field(min_length=1, max_length=MAX_CONDITIONS)
    mode: Literal["once", "repeat"] = "once"
    cooldown_min: int = Field(default=60, ge=1, le=1440)
    expires_at: datetime | None = None
    level: Literal["info", "warn", "crit"] = "warn"
    channels: list[Literal["ntfy", "log", "telegram", "app", "push"]] = Field(default_factory=lambda: ["ntfy", "log"], max_length=5)
    note: str = Field(default="", max_length=200)

    @field_validator("expires_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

    @field_validator("channels")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v)) or ["log"]

    def spec(self) -> dict:
        """Phần lưu trong cột jsonb `spec` (name/enabled/expires_at có cột riêng)."""
        return self.model_dump(mode="json", by_alias=True, exclude={"name", "enabled", "expires_at"})


# ---- tuỳ chọn người dùng (watchlist/layout) ----
class Watchlist(_Strict):
    id: str = Field(pattern=r"^[a-z0-9-]{1,32}$")
    name: str = Field(min_length=1, max_length=40)
    symbols: list[Symbol] = Field(default_factory=list, max_length=100)
    tf: Tf = "H1"

    @field_validator("symbols")
    @classmethod
    def _uniq(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


UX_KEYS = ("theme", "accent", "density", "fontScale", "contrast", "motion", "tz", "dateFmt", "numFmt", "currency", "updown",
           "toasts", "sound", "soundVol", "browserNotif", "notifCats", "onboarded", "t")


_TM_CH = ("red", "orange", "yellow", "green", "cyan", "blue", "purple")


def _tm_int(x, lo: int, hi: int) -> int | None:
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and lo <= x <= hi else None


def _tm_widget(w) -> dict | None:
    if not isinstance(w, dict) or not isinstance(w.get("i"), str) or not isinstance(w.get("t"), str):
        return None
    o = {"i": w["i"][:12], "t": w["t"][:40]}
    for k, hi in (("x", 23), ("y", 400), ("w", 24), ("h", 60)):
        n = _tm_int(w.get(k), 0 if k in ("x", "y") else 1, hi)
        if n is None:
            return None
        o[k] = n
    c = w.get("c")
    if isinstance(c, dict) and c and len(json.dumps(c, ensure_ascii=False)) <= 2048:
        o["c"] = c
    if w.get("k") in _TM_CH:
        o["k"] = w["k"]
    if isinstance(w.get("n"), str) and w["n"].strip():
        o["n"] = w["n"][:60]
    return o


def _clean_tm(v: dict) -> dict:
    """Làm sạch workspace Terminal: chỉ giữ khoá đã biết, tối đa 12 workspace x 40 widget; sai cấu trúc thì bỏ phần đó."""
    if not isinstance(v, dict) or not isinstance(v.get("w"), dict):
        return {}
    ws: dict = {}
    order: list[str] = []
    for wid in (v.get("o") if isinstance(v.get("o"), list) else list(v["w"])):
        w = v["w"].get(wid) if isinstance(wid, str) else None
        if not isinstance(w, dict) or wid in ws or len(order) >= 12 or not 0 < len(wid) <= 16:
            continue
        items, seen = [], set()
        for it in (w.get("x") if isinstance(w.get("x"), list) else [])[:40]:
            c = _tm_widget(it)
            if c and c["i"] not in seen:
                seen.add(c["i"])
                items.append(c)
        ch = {k: s for k, s in (w.get("c") or {}).items() if k in _TM_CH and isinstance(s, str) and len(s) <= 40} if isinstance(w.get("c"), dict) else {}
        ws[wid] = {"n": str(w.get("n") or "Workspace")[:40], "l": bool(w.get("l")), "x": items, "c": ch}
        order.append(wid)
    if not order:
        return {}
    a = v.get("a") if isinstance(v.get("a"), str) and v.get("a") in ws else order[0]
    return {"v": 1, "a": a, "o": order, "w": ws}


class Prefs(BaseModel):
    """Trường lạ bị LOẠI (ignore) thay vì báo lỗi, để UI cũ/mới cùng chạy được."""
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    theme: Literal["dark", "light"] = "dark"
    default_tf: Tf = "H1"
    nav_rail: bool = False
    active_watchlist: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,32}$")
    watchlists: list[Watchlist] = Field(default_factory=list, max_length=20)
    # Cấu hình biểu đồ của UI (bản vẽ theo mã/khung, mẫu chỉ báo). Chỉ giữ khoá đã biết; tổng prefs vẫn <= 16KB.
    chart: dict = Field(default_factory=dict)

    @field_validator("chart")
    @classmethod
    def _chart(cls, v: dict) -> dict:
        return {k: v[k] for k in ("draw", "tpl", "layout") if isinstance(v.get(k), dict)}

    # Cài đặt giao diện (trang Cài đặt: giao diện, màu nhấn, múi giờ, thông báo...). Chỉ giữ khoá đã biết, giá trị đơn giản.
    ux: dict = Field(default_factory=dict)

    @field_validator("ux")
    @classmethod
    def _ux(cls, v: dict) -> dict:
        out: dict = {}
        for k in UX_KEYS:
            x = v.get(k)
            if isinstance(x, bool) or isinstance(x, (int, float)):
                out[k] = x
            elif isinstance(x, str) and len(x) <= 64:
                out[k] = x
            elif k == "notifCats" and isinstance(x, dict):
                out[k] = {str(c)[:16]: bool(f) for c, f in list(x.items())[:8]}
        return out

    # Workspace của trang Terminal (web-ui): {v, a: workspace đang mở, o: [id...], w: {id: {n, l, x:[widget], c:{kênh: mã}}}}.
    # Chỉ giữ cấu trúc đã biết, giới hạn số lượng/độ dài; cấu hình riêng từng widget (`c`) là dict tự do nhưng mỗi widget <= 2KB.
    tm: dict = Field(default_factory=dict)

    @field_validator("tm")
    @classmethod
    def _tm(cls, v: dict) -> dict:
        return _clean_tm(v)

    @model_validator(mode="after")
    def _chk(self):
        ids = [w.id for w in self.watchlists]
        if len(ids) != len(set(ids)):
            raise ValueError("id nhóm bị trùng")
        if self.active_watchlist and ids and self.active_watchlist not in ids:
            self.active_watchlist = ids[0]
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode()) > 16_384:
            raise ValueError("prefs vượt 16KB")
        return self


class PushKeys(_Strict):
    p256dh: str = Field(min_length=20, max_length=128)
    auth: str = Field(min_length=10, max_length=64)


class PushSubIn(_Strict):
    endpoint: str = Field(min_length=10, max_length=700)
    keys: PushKeys
    user_agent: str | None = Field(default=None, max_length=300)


class PushUnsubIn(_Strict):
    endpoint: str = Field(min_length=10, max_length=700)


class PrefsIn(_Strict):
    rev: int = Field(ge=0)
    prefs: dict
