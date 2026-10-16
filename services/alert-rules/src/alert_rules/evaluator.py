"""Đánh giá điều kiện cảnh báo (logic thuần + provider dữ liệu tiêm vào => test không cần DB).

Kết quả mỗi điều kiện là bộ ba: True / False / None (không đủ dữ liệu hoặc dữ liệu cũ). AND: có False -> False, có None -> None;
OR: có True -> True, có None -> None. Chỉ True mới kích hoạt (không bao giờ kích hoạt vì thiếu dữ liệu).
"""
from __future__ import annotations

import time
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Protocol

from .models import TF_SECONDS

OPS = {"gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}
OP_SYM = {"gte": "≥", "lte": "≤", "cross_up": "cắt lên", "cross_down": "cắt xuống", "abs_gte": "|Δ| ≥"}
PRICE_STALE_S = 15 * 60          # giá cũ hơn mức này: không dùng để kích hoạt
HISTORY_SAMPLE_S = 10            # mẫu giá tối đa 1 lần / 10 giây / mã
HISTORY_MAX_S = 24 * 3600 + 600
ACCOUNT_STALE_S = 15 * 60
RISK_BEFORE_MIN, RISK_AFTER_MIN = 15, 30    # cửa sổ rủi ro tin: T-15..T+30 (khớp tscommon.risk_windows)
FLIP_BAND = 0.05


class Provider(Protocol):
    async def latest_price(self, symbol: str) -> dict | None: ...                       # {mid, ts(epoch), source}
    async def bar_closes(self, symbol: str, minutes: int) -> list[tuple[float, float]]: ...   # [(epoch, close)] tăng dần
    async def analytics(self, symbol: str, tf: str) -> tuple[dict, float] | None: ...    # (payload, updated_at epoch)
    async def calendar(self, impacts: list[str], start: datetime, end: datetime, country: str | None) -> list[dict]: ...
    async def sentiment(self, symbol: str, start: datetime, end: datetime) -> tuple[float | None, int]: ...
    async def accounts(self) -> list[dict]: ...                                           # account_id,balance,equity,margin,ts,peak24


@dataclass
class CondResult:
    ok: bool | None
    value: Any = None
    text: str = ""
    stale: bool = False

    def as_dict(self) -> dict:
        return {"ok": self.ok, "value": self.value, "text": self.text, "stale": self.stale}


def combine(logic: str, results: list[bool | None]) -> bool | None:
    if logic == "or":
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    if any(r is False for r in results):
        return False
    return None if any(r is None for r in results) else True


def _fmt(x: float | None, nd: int = 5) -> str:
    if x is None:
        return "—"
    return f"{x:.{nd}g}" if abs(x) < 1e6 else f"{x:,.0f}"


class MarketState:
    """Giá mới nhất từ md.quotes + lịch sử mẫu thưa theo mã (phục vụ pct_change)."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.quotes: dict[str, dict] = {}
        self.history: dict[str, deque] = {}
        self.seeded: dict[str, float] = {}

    def on_quote(self, symbol: str, bid, ask, ts: float, source: str | None) -> None:
        px = [x for x in (bid, ask) if isinstance(x, (int, float)) and x > 0]
        if not px:
            return
        mid = sum(px) / len(px)
        self.quotes[symbol] = {"mid": mid, "ts": ts, "source": source}
        h = self.history.setdefault(symbol, deque())
        if not h or ts - h[-1][0] >= HISTORY_SAMPLE_S:
            h.append((ts, mid))
        cut = ts - HISTORY_MAX_S
        while h and h[0][0] < cut:
            h.popleft()

    def seed(self, symbol: str, closes: list[tuple[float, float]]) -> None:
        h = self.history.setdefault(symbol, deque())
        merged = sorted({*h, *closes})
        h.clear()
        h.extend(merged)
        self.seeded[symbol] = self.clock()

    def price_at(self, symbol: str, t: float, slack_s: float) -> float | None:
        """Mẫu gần nhất tại/ trước t (không cũ hơn slack_s trước t)."""
        h = self.history.get(symbol)
        if not h:
            return None
        ts = [x[0] for x in h]
        i = bisect_right(ts, t) - 1
        if i < 0:
            return None
        if t - h[i][0] > slack_s:
            return None
        return h[i][1]


@dataclass
class Evaluator:
    provider: Provider
    state: MarketState
    clock: Callable[[], float] = time.time
    cache_ttl_s: float = 20.0
    sides: dict = field(default_factory=dict)       # (rule_id, idx) -> bool: giá đang ở phía >= mức?
    _cache: dict = field(default_factory=dict)

    async def _cached(self, key, fn: Callable[[], Awaitable[Any]]):
        now = self.clock()
        hit = self._cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        val = await fn()
        self._cache[key] = (now + self.cache_ttl_s, val)
        if len(self._cache) > 500:
            for k in [k for k, v in self._cache.items() if v[0] <= now]:
                self._cache.pop(k, None)
        return val

    def forget(self, rule_id: str) -> None:
        for k in [k for k in self.sides if k[0] == rule_id]:
            self.sides.pop(k, None)

    # ---- giá ----
    async def _price(self, symbol: str) -> dict | None:
        q = self.state.quotes.get(symbol)
        now = self.clock()
        if q and now - q["ts"] <= 60:
            return q
        got = await self._cached(("px", symbol), lambda: self.provider.latest_price(symbol))
        if got and (not q or got["ts"] >= q["ts"]):
            return got
        return q

    async def evaluate(self, rule_id: str, idx: int, c: dict, commit: bool) -> CondResult:
        t = c["type"]
        try:
            return await getattr(self, f"_c_{t}")(rule_id, idx, c, commit)
        except Exception as e:  # noqa: BLE001
            return CondResult(None, None, f"Không đánh giá được ({type(e).__name__})")

    async def _c_price(self, rid, idx, c, commit) -> CondResult:
        p = await self._price(c["symbol"])
        if not p:
            return CondResult(None, None, f"{c['symbol']}: chưa có giá")
        if self.clock() - p["ts"] > PRICE_STALE_S:
            return CondResult(None, p["mid"], f"{c['symbol']}: giá cũ", stale=True)
        mid, v, op = p["mid"], c["value"], c["op"]
        label = f"{c['symbol']} giá {_fmt(mid)} {OP_SYM[op]} {_fmt(v)}"
        if op in OPS:
            return CondResult(OPS[op](mid, v), mid, label)
        side = mid >= v
        key = (rid, idx)
        prev = self.sides.get(key)
        if commit:
            self.sides[key] = side
        elif prev is None:
            prev = side
        if prev is None:
            return CondResult(False, mid, label + " (chờ mốc đầu)")
        hit = (not prev and side) if op == "cross_up" else (prev and not side)
        return CondResult(bool(hit), mid, label)

    async def _c_pct_change(self, rid, idx, c, commit) -> CondResult:
        sym, win = c["symbol"], c["window_min"]
        p = await self._price(sym)
        if not p or self.clock() - p["ts"] > PRICE_STALE_S:
            return CondResult(None, None, f"{sym}: chưa có giá mới")
        now = self.clock()
        if self.state.seeded.get(sym, 0) < now - 600 and not self._covered(sym, win, now):
            closes = await self.provider.bar_closes(sym, min(1440, win + 15))
            self.state.seed(sym, closes)
        past = self.state.price_at(sym, now - win * 60, slack_s=max(120.0, win * 60 * 0.15))
        if past is None or past <= 0:
            return CondResult(None, None, f"{sym}: chưa đủ lịch sử {win} phút")
        chg = (p["mid"] - past) / past * 100
        op, v = c["op"], c["value"]
        ok = abs(chg) >= v if op == "abs_gte" else OPS[op](chg, v)
        return CondResult(ok, round(chg, 4), f"{sym} {win} phút: {chg:+.3f}% {OP_SYM[op]} {_fmt(v)}%")

    def _covered(self, sym: str, win_min: int, now: float) -> bool:
        h = self.state.history.get(sym)
        return bool(h) and h[0][0] <= now - win_min * 60

    async def _c_indicator(self, rid, idx, c, commit) -> CondResult:
        got = await self._cached(("an", c["symbol"], c["tf"]), lambda: self.provider.analytics(c["symbol"], c["tf"]))
        if not got:
            return CondResult(None, None, f"{c['symbol']} {c['tf']}: chưa có phân tích")
        payload, upd = got
        val = payload.get(c["field"])
        stale = self.clock() - upd > max(900, 3 * TF_SECONDS.get(c["tf"], 3600))
        if val is None or stale:
            return CondResult(None, val, f"{c['symbol']} {c['tf']} {c['field']}: dữ liệu {'cũ' if stale else 'trống'}", stale=stale)
        return CondResult(OPS[c["op"]](val, c["value"]), val,
                          f"{c['symbol']} {c['tf']} {c['field'].upper()} {_fmt(val, 4)} {OP_SYM[c['op']]} {_fmt(c['value'])}")

    async def _c_state(self, rid, idx, c, commit) -> CondResult:
        got = await self._cached(("an", c["symbol"], c["tf"]), lambda: self.provider.analytics(c["symbol"], c["tf"]))
        if not got:
            return CondResult(None, None, f"{c['symbol']} {c['tf']}: chưa có phân tích")
        payload, upd = got
        val = payload.get(c["field"])
        stale = self.clock() - upd > max(900, 3 * TF_SECONDS.get(c["tf"], 3600))
        want = c.get("is", c.get("is_"))
        if val is None or stale:
            return CondResult(None, val, f"{c['symbol']} {c['tf']} {c['field']}: dữ liệu {'cũ' if stale else 'trống'}", stale=stale)
        return CondResult(val == want, val, f"{c['symbol']} {c['tf']} {c['field']} = {val} (cần {want})")

    async def _c_news_window(self, rid, idx, c, commit) -> CondResult:
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        impacts = ["high"] if c["impact"] == "high" else ["med", "high"]
        if c.get("phase", "upcoming") == "active":
            start, end = now - timedelta(minutes=RISK_AFTER_MIN), now + timedelta(minutes=RISK_BEFORE_MIN)
        else:
            start, end = now, now + timedelta(minutes=c["within_min"])
        key = ("cal", tuple(impacts), c.get("country"), c.get("phase"), c.get("within_min"))
        rows = await self._cached(key, lambda: self.provider.calendar(impacts, start, end, c.get("country")))
        label = "tin " + ("cao" if c["impact"] == "high" else "vừa+cao")
        if not rows:
            return CondResult(False, None, f"Không có {label} trong {'cửa sổ rủi ro' if c.get('phase') == 'active' else str(c['within_min']) + ' phút tới'}")
        nxt = min(rows, key=lambda r: abs((r["ts"] - now).total_seconds()))
        mins = round((nxt["ts"] - now).total_seconds() / 60)
        return CondResult(True, nxt["title"], f"{nxt['title']} ({nxt.get('country') or '—'}) {'sau' if mins >= 0 else 'cách đây'} {abs(mins)} phút")

    async def _c_sentiment(self, rid, idx, c, commit) -> CondResult:
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        w = timedelta(hours=c["window_h"])
        sym = c["symbol"]
        cur = await self._cached(("sent", sym, c["window_h"], 0), lambda: self.provider.sentiment(sym, now - w, now))
        avg, n = cur
        if avg is None or n < 2:
            return CondResult(None, avg, f"{sym}: chưa đủ tin để tính sentiment ({n})")
        op = c["op"]
        if op in OPS:
            return CondResult(OPS[op](avg, c["value"]), round(avg, 3), f"{sym} sentiment {c['window_h']}h {avg:+.2f} {OP_SYM[op]} {_fmt(c['value'], 3)}")
        prev = await self._cached(("sent", sym, c["window_h"], 1), lambda: self.provider.sentiment(sym, now - 2 * w, now - w))
        pavg, pn = prev
        if pavg is None or pn < 2:
            return CondResult(None, round(avg, 3), f"{sym}: chưa đủ tin kỳ trước")
        ok = (pavg <= -FLIP_BAND and avg >= FLIP_BAND) if op == "flip_up" else (pavg >= FLIP_BAND and avg <= -FLIP_BAND)
        return CondResult(ok, round(avg, 3), f"{sym} sentiment {pavg:+.2f} -> {avg:+.2f} ({'đảo lên' if op == 'flip_up' else 'đảo xuống'})")

    async def _c_account(self, rid, idx, c, commit) -> CondResult:
        rows = await self._cached(("acct",), lambda: self.provider.accounts())
        want = c.get("account_id")
        now = self.clock()
        cand, stale = [], 0
        for r in rows:
            if want and r["account_id"] != want:
                continue
            if now - r["ts"] > ACCOUNT_STALE_S:
                stale += 1
                continue
            m = self._metric(c["metric"], r)
            if m is not None:
                cand.append((r["account_id"], m))
        if not cand:
            return CondResult(None, None, "Tài khoản: chưa có số liệu mới" + (" (snapshot cũ)" if stale else ""), stale=bool(stale))
        op = c["op"]
        hits = [(a, m) for a, m in cand if OPS[op](m, c["value"])]
        pick = hits[0] if hits else (min(cand, key=lambda x: x[1]) if op == "lte" else max(cand, key=lambda x: x[1]))
        names = {"margin_level": "Margin level", "equity_drawdown_24h": "Sụt equity 24h", "floating_pl_pct": "Lãi/lỗ thả nổi"}
        return CondResult(bool(hits), round(pick[1], 3), f"{names[c['metric']]} {pick[0]}: {pick[1]:.2f}% {OP_SYM[op]} {_fmt(c['value'])}%")

    @staticmethod
    def _metric(metric: str, r: dict) -> float | None:
        eq, bal, mg = r.get("equity"), r.get("balance"), r.get("margin")
        if metric == "margin_level":
            return eq / mg * 100 if eq is not None and mg and mg > 0 else None
        if metric == "equity_drawdown_24h":
            peak = r.get("peak24")
            return (peak - eq) / peak * 100 if eq is not None and peak and peak > 0 else None
        if metric == "floating_pl_pct":
            return (eq - bal) / bal * 100 if eq is not None and bal and bal > 0 else None
        return None

    async def evaluate_rule(self, rid: str, spec: dict, commit: bool = True) -> tuple[bool | None, list[CondResult]]:
        res = [await self.evaluate(rid, i, c, commit) for i, c in enumerate(spec["conditions"])]
        return combine(spec.get("logic", "and"), [r.ok for r in res]), res
