"""Guardrail rủi ro cho sổ PAPER (mô-đun 7 của tab AI Trading). CHỈ nghiên cứu/paper: không có đường tới lệnh thật.

Phần thuần (không I/O, tất định, có test):
- position_size / sizing_table: kích thước vị thế theo % rủi ro và khoảng dừng lỗ (SL thật hoặc ATR x hệ số).
- daily_loss_r: tổng R đã đóng trong ngày UTC (bỏ replay) -> chặn khi vượt giới hạn.
- news_blocked: cửa sổ tin (tscommon.risk_windows) quanh sự kiện lớn.
Lớp Guardrail ghép: kill-switch (cờ Redis `aitrading:killswitch`, CHỈ master bật/tắt qua ai-trading) -> lỗ ngày -> cửa sổ tin -> cỡ vị thế.
Fail-open có ghi nhận cho NGUỒN PHỤ (Redis/lịch tin lỗi) vì đây là paper; trạng thái `degraded` hiện trên tab."""
from __future__ import annotations

import json
import math
from collections import deque
from datetime import datetime, timezone
from typing import Awaitable, Callable

KILL_KEY = "aitrading:killswitch"
DEFAULTS = {
    "enabled": True,                 # guardrail ÁP DỤNG mặc định cho sổ paper
    "equity": 10000.0,               # vốn paper danh nghĩa để tính cỡ vị thế
    "risk_pct": 0.5,                 # % vốn rủi ro mỗi lệnh (1R)
    "max_risk_pct": 2.0,             # trần cứng của risk_pct
    "atr_mult": 1.5,                 # khoảng dừng = atr_mult x ATR khi không có SL
    "lot_step": 0.01,
    "max_daily_loss_r": 3.0,         # lỗ ngày (R, UTC) >= ngưỡng -> chặn tín hiệu paper mới tới hết ngày
    "news_window": True,
    "recent": 50,
}


def cfg_of(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    out.update((cfg or {}).get("guardrail") or {})
    out["risk_pct"] = min(max(float(out["risk_pct"]), 0.0), float(out["max_risk_pct"]))
    return out


def position_size(equity: float, risk_pct: float, entry: float | None = None, sl: float | None = None, atr: float | None = None,
                  atr_mult: float = 1.5, value_per_unit: float = 1.0, lot_step: float = 0.01, max_risk_pct: float = 2.0) -> dict:
    """Cỡ vị thế = (equity x risk%) / (khoảng dừng x giá trị mỗi đơn vị giá). Khoảng dừng: |entry-sl| nếu có SL, nếu không atr x atr_mult.
    Làm tròn XUỐNG theo lot_step (không bao giờ vượt rủi ro). Lỗi đầu vào -> units 0 + lý do (không ném)."""
    def bad(why):
        return {"ok": False, "units": 0.0, "risk_amount": 0.0, "stop_distance": None, "reason": why}
    try:
        equity, risk_pct = float(equity), float(risk_pct)
    except (TypeError, ValueError):
        return bad("đầu vào không phải số")
    if not (math.isfinite(equity) and equity > 0) or not (math.isfinite(risk_pct) and risk_pct > 0):
        return bad("vốn hoặc % rủi ro không hợp lệ")
    risk_pct = min(risk_pct, float(max_risk_pct))
    if entry is not None and sl is not None and math.isfinite(float(entry)) and math.isfinite(float(sl)) and float(entry) != float(sl):
        dist = abs(float(entry) - float(sl))
    elif atr is not None and math.isfinite(float(atr)) and float(atr) > 0:
        dist = float(atr) * float(atr_mult)
    else:
        return bad("không có SL hoặc ATR để tính khoảng dừng")
    risk_amount = equity * risk_pct / 100.0
    raw = risk_amount / (dist * float(value_per_unit))
    step = float(lot_step) if float(lot_step) > 0 else 0.01
    units = math.floor(raw / step + 1e-9) * step
    if units <= 0:
        return {"ok": False, "units": 0.0, "risk_amount": 0.0, "stop_distance": dist, "reason": "dưới bước tối thiểu (rủi ro quá nhỏ so với khoảng dừng)"}
    return {"ok": True, "units": round(units, 8), "risk_amount": round(units * dist * float(value_per_unit), 4), "stop_distance": dist,
            "risk_pct": risk_pct, "reason": None}


def sizing_table(equity: float = 10000.0, atrs=(0.0005, 0.0050, 1.0, 20.0), risk_pcts=(0.25, 0.5, 1.0, 2.0), atr_mult: float = 1.5,
                 lot_step: float = 0.01) -> list[dict]:
    """Bảng thử: mỗi (ATR, risk%) -> units + số tiền rủi ro thực (<= equity x risk%). Giá trị mỗi đơn vị giá = 1 (danh nghĩa)."""
    return [{"atr": a, "risk_pct": rp, **{k: v for k, v in position_size(equity, rp, atr=a, atr_mult=atr_mult, lot_step=lot_step).items()
                                          if k in ("units", "risk_amount", "stop_distance", "ok")}}
            for a in atrs for rp in risk_pcts]


def _day(v) -> str | None:
    if v is None:
        return None
    d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).date().isoformat()


def daily_loss_r(trades: list[dict], now: datetime) -> float:
    """Tổng R đã đóng trong ngày UTC của `now` (bỏ lệnh replay). Âm = lỗ."""
    today = _day(now)
    return round(sum(float(t["result_r"]) for t in trades
                     if t.get("status") == "closed" and t.get("result_r") is not None and not t.get("replay")
                     and _day(t.get("closed_at")) == today), 4)


def news_blocked(events: list[dict], symbol: str, now: datetime, cfg: dict) -> dict | None:
    from tscommon.risk_windows import risk_state
    st = risk_state(events, symbol, now, cfg, horizon_h=1)
    if st["in_window"]:
        cur = (st.get("current") or [{}])[0]
        return {"title": cur.get("title"), "minutes_to_end": st.get("minutes_to_end")}
    return None


class Guardrail:
    def __init__(self, cfg: dict, kill_reader: Callable[[], Awaitable[str | None]] | None = None,
                 events_reader: Callable[[datetime], Awaitable[list[dict]]] | None = None,
                 trades_reader: Callable[[], Awaitable[list[dict]]] | None = None, news_cfg: dict | None = None):
        self.c = cfg_of(cfg)
        self.kill_reader, self.events_reader, self.trades_reader, self.news_cfg = kill_reader, events_reader, trades_reader, news_cfg
        self.recent: deque = deque(maxlen=int(self.c["recent"]))
        self.counts = {"allowed": 0, "kill_switch": 0, "daily_loss": 0, "news_window": 0}
        self.degraded: list[str] = []
        self._seen: deque = deque(maxlen=500)     # setup đã ghi nhận bị chặn (repair chạy lại không đếm trùng)

    async def kill_state(self) -> dict:
        if self.kill_reader is None:
            return {"on": False, "known": False}
        try:
            raw = await self.kill_reader()
        except Exception:  # noqa: BLE001
            self._deg("kill_switch")
            return {"on": False, "known": False}
        if not raw:
            return {"on": False, "known": True}
        try:
            d = json.loads(raw if isinstance(raw, str) else raw.decode())
            return {"on": bool(d.get("on")), "known": True, "by": d.get("by"), "at": d.get("at"), "reason": d.get("reason")}
        except (ValueError, AttributeError):
            return {"on": True, "known": True, "reason": "cờ không đọc được -> coi như BẬT (an toàn)"}

    def _deg(self, what: str) -> None:
        if what not in self.degraded:
            self.degraded.append(what)

    async def check(self, p: dict, now: datetime) -> dict:
        """Quyết định cho 1 tín hiệu paper sắp mở. Trả {allow, reason, size}."""
        if not self.c["enabled"]:
            return {"allow": True, "reason": None, "size": None, "disabled": True}
        ks = await self.kill_state()
        if ks["on"]:
            return self._rec(p, now, "kill_switch", "Kill-switch đang BẬT (master)")
        if self.trades_reader is not None:
            try:
                dl = daily_loss_r(await self.trades_reader(), now)
                if dl <= -float(self.c["max_daily_loss_r"]):
                    return self._rec(p, now, "daily_loss", f"Lỗ ngày {dl:+.2f}R vượt giới hạn -{self.c['max_daily_loss_r']}R")
            except Exception:  # noqa: BLE001
                self._deg("daily_loss")
        if self.c["news_window"] and self.events_reader is not None:
            try:
                nb = news_blocked(await self.events_reader(now), p["symbol"], now, self.news_cfg or _news_cfg())
                if nb:
                    return self._rec(p, now, "news_window", f"Cửa sổ tin: {nb['title']} (còn {nb['minutes_to_end']} phút)")
            except Exception:  # noqa: BLE001
                self._deg("news_window")
        lv = p.get("levels") or {}
        size = position_size(self.c["equity"], self.c["risk_pct"], lv.get("entry"), lv.get("sl"), atr_mult=self.c["atr_mult"],
                             lot_step=self.c["lot_step"], max_risk_pct=self.c["max_risk_pct"])
        self.counts["allowed"] += 1
        return {"allow": True, "reason": None, "size": {k: size[k] for k in ("units", "risk_amount", "risk_pct") if k in size}}

    def _rec(self, p: dict, now: datetime, kind: str, why: str) -> dict:
        key = (p.get("setup_id"), p.get("symbol"), p.get("tf"))
        if key in self._seen:
            return {"allow": False, "kind": kind, "reason": why, "size": None}
        self._seen.append(key)
        self.counts[kind] += 1
        self.recent.appendleft({"at": now.isoformat(), "kind": kind, "symbol": p.get("symbol"), "pattern": p.get("pattern"),
                                "tf": p.get("tf"), "reason": why})
        return {"allow": False, "kind": kind, "reason": why, "size": None}

    async def state(self, now: datetime) -> dict:
        ks = await self.kill_state()
        dl = None
        if self.trades_reader is not None:
            try:
                dl = daily_loss_r(await self.trades_reader(), now)
            except Exception:  # noqa: BLE001
                self._deg("daily_loss")
        return {"enabled": self.c["enabled"], "kill_switch": ks, "daily_loss_r": dl, "limits": {
                    "max_daily_loss_r": self.c["max_daily_loss_r"], "risk_pct": self.c["risk_pct"], "max_risk_pct": self.c["max_risk_pct"],
                    "equity": self.c["equity"], "atr_mult": self.c["atr_mult"], "news_window": self.c["news_window"]},
                "daily_blocked": dl is not None and dl <= -float(self.c["max_daily_loss_r"]),
                "counts": dict(self.counts), "recent_blocks": list(self.recent), "degraded": list(self.degraded),
                "sizing_table": sizing_table(self.c["equity"], atr_mult=self.c["atr_mult"], lot_step=self.c["lot_step"]), "as_of": now.isoformat()}


def _news_cfg() -> dict:
    from tscommon.risk_windows import load_config
    return load_config()
