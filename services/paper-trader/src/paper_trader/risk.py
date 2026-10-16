"""Risk engine: cổng CỨNG, TẤT ĐỊNH, chạy TRƯỚC mô phỏng khớp. Không có LLM, không ngẫu nhiên.
Thứ tự: (1) sizing (conviction -> tỷ trọng: vol targeting / ATR) (2) cổng tỷ trọng (whitelist, short, trần/symbol, đòn bẩy)
        (3) kiểm tra tài khoản (lỗ ngày/tuần, drawdown -> kill-switch) (4) lọc lệnh (cửa sổ tin, giới hạn lệnh/phút)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .models import Order, Targets, utc

DEFAULT_RISK = {
    "whitelist": None,                # None = mọi symbol trong universe; list = chỉ các symbol này
    "sizing": {"mode": "passthrough", "target_vol": 0.10, "vol_window": 60, "max_scale": 3.0,
               "atr_days": 14, "atr_mult": 2.0, "risk_per_trade": 0.005},
    "max_leverage": 1.0,              # tổng |tỷ trọng| tối đa / equity
    "max_weight": 0.5,                # |tỷ trọng| tối đa mỗi symbol
    "max_daily_loss": 0.03,           # lỗ trong ngày so với equity đầu ngày -> TẠM DỪNG tới hết ngày
    "max_weekly_loss": 0.06,          # lỗ trong tuần -> TẠM DỪNG tới hết tuần
    "max_drawdown": 0.15,             # drawdown từ đỉnh -> KHOÁ CỨNG (phải reset tay)
    "max_orders_per_minute": 30,
    "min_trade_weight": 0.005,        # bỏ lệnh nhỏ hơn 0,5% equity (giảm vòng quay/phí); lệnh đóng hẳn vị thế luôn được phép
    "flatten_on_halt": True,
    "news_block_pre_min": 15, "news_block_post_min": 30,
}


@dataclass
class Breach:
    kind: str            # daily | weekly | drawdown
    value: float         # mức vi phạm (số âm, vd -0.04)
    limit: float
    hard: bool           # True = khoá cứng


@dataclass
class RiskResult:
    weights: dict[str, float]
    notes: list[dict] = field(default_factory=list)


class RiskConfig(dict):
    @classmethod
    def build(cls, over: dict | None) -> "RiskConfig":
        c = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_RISK.items()}
        for k, v in (over or {}).items():
            if isinstance(v, dict) and isinstance(c.get(k), dict):
                c[k].update(v)
            else:
                c[k] = v
        return cls(c)


def _log_returns(history: dict[str, pd.DataFrame], symbols: list[str], window: int) -> pd.DataFrame:
    cols = {s: np.log(history[s]["c"].astype(float)).diff() for s in symbols if s in history and len(history[s]) > 2}
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).tail(window)


def atr(df: pd.DataFrame, n: int) -> float | None:
    if len(df) < n + 1:
        return None
    h, l, c = df["h"].astype(float), df["l"].astype(float), df["c"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    v = float(tr.tail(n).mean())
    return v if math.isfinite(v) and v > 0 else None


class RiskEngine:
    def __init__(self, cfg: RiskConfig, periods_per_year: int = 252):
        self.cfg, self.ppy = cfg, periods_per_year

    # ------------------------------------------------------------------ (1) sizing
    def size(self, tg: Targets, history: dict[str, pd.DataFrame]) -> RiskResult:
        sz = self.cfg["sizing"]
        notes: list[dict] = []
        mode = sz.get("mode", "passthrough")
        if tg.kind == "weight" or mode == "passthrough":
            return RiskResult(dict(tg.weights), notes)
        conv = dict(tg.weights)
        if mode == "atr_risk":
            w: dict[str, float] = {}
            for s, c in conv.items():
                df = history.get(s)
                a = atr(df, int(sz["atr_days"])) if df is not None else None
                if c == 0:
                    w[s] = 0.0
                elif a is None:
                    w[s] = 0.0
                    notes.append({"code": "sizing_no_atr", "symbol": s})
                else:        # rủi ro 1 vị thế = risk_per_trade*equity nếu giá đi atr_mult*ATR ngược hướng
                    w[s] = c * float(sz["risk_per_trade"]) * float(df["c"].iloc[-1]) / (float(sz["atr_mult"]) * a)
            return RiskResult(w, notes)
        if mode != "vol_target":
            raise ValueError(f"sizing.mode không hợp lệ: {mode}")
        win = int(sz["vol_window"])
        rets = _log_returns(history, [s for s, c in conv.items() if c != 0], win)
        sigma = {s: float(rets[s].std(ddof=1) * math.sqrt(self.ppy)) for s in rets.columns if rets[s].count() >= 10}
        raw: dict[str, float] = {}
        for s, c in conv.items():
            if c == 0:
                raw[s] = 0.0
            elif sigma.get(s, 0.0) > 1e-9:
                raw[s] = c / sigma[s]
            else:
                raw[s] = 0.0
                notes.append({"code": "sizing_no_vol", "symbol": s})
        act = [s for s, x in raw.items() if x != 0]
        if not act:
            return RiskResult({s: 0.0 for s in conv}, notes)
        vec = np.array([raw[s] for s in act])
        sub = rets[act].dropna()
        if len(sub) >= 10:
            cov = np.cov(sub.to_numpy().T, ddof=1).reshape(len(act), len(act)) * self.ppy
            pv = float(np.sqrt(max(vec @ cov @ vec, 0.0)))
        else:
            pv = float(np.sqrt(sum((raw[s] * sigma[s]) ** 2 for s in act)))
        scale = float(sz["max_scale"]) if pv <= 1e-12 else min(float(sz["target_vol"]) / pv, float(sz["max_scale"]))
        notes.append({"code": "vol_target", "portfolio_vol_raw": round(pv, 4), "scale": round(scale, 4)})
        return RiskResult({s: raw[s] * scale for s in conv}, notes)

    # ------------------------------------------------------------------ (2) cổng tỷ trọng
    def gate(self, weights: dict[str, float], universe: list[str], shortable: dict[str, bool]) -> RiskResult:
        c = self.cfg
        notes: list[dict] = []
        wl = set(c["whitelist"]) if c["whitelist"] else set(universe)
        out: dict[str, float] = {}
        for s, w in weights.items():
            if s not in wl or s not in universe:
                notes.append({"code": "not_whitelisted", "symbol": s})
                continue
            if w < 0 and not shortable.get(s, True):
                notes.append({"code": "short_not_allowed", "symbol": s, "weight": round(w, 4)})
                w = 0.0
            cap = float(c["max_weight"])
            if abs(w) > cap:
                notes.append({"code": "max_weight", "symbol": s, "weight": round(w, 4), "cap": cap})
                w = math.copysign(cap, w)
            out[s] = w
        gross = sum(abs(x) for x in out.values())
        if gross > float(c["max_leverage"]) + 1e-12:
            f = float(c["max_leverage"]) / gross
            notes.append({"code": "max_leverage", "gross": round(gross, 4), "cap": c["max_leverage"], "scale": round(f, 4)})
            out = {s: x * f for s, x in out.items()}
        return RiskResult(out, notes)

    # ------------------------------------------------------------------ (3) tài khoản -> kill-switch
    def check_account(self, equity: float, hwm: float, day_start: float, week_start: float) -> Breach | None:
        c = self.cfg
        dd = equity / hwm - 1.0 if hwm > 0 else 0.0
        if dd <= -float(c["max_drawdown"]):
            return Breach("drawdown", dd, -float(c["max_drawdown"]), True)
        wk = equity / week_start - 1.0 if week_start > 0 else 0.0
        if wk <= -float(c["max_weekly_loss"]):
            return Breach("weekly", wk, -float(c["max_weekly_loss"]), False)
        dy = equity / day_start - 1.0 if day_start > 0 else 0.0
        if dy <= -float(c["max_daily_loss"]):
            return Breach("daily", dy, -float(c["max_daily_loss"]), False)
        return None

    # ------------------------------------------------------------------ (4) lọc lệnh
    @staticmethod
    def is_reducing(order: Order, cur_qty: float) -> bool:
        signed = order.qty if order.side == "buy" else -order.qty
        new = cur_qty + signed
        return abs(new) < 1e-9 or (new * cur_qty > 0 and abs(new) < abs(cur_qty))

    def filter_orders(self, orders: list[Order], positions: dict[str, float],
                      blocked: dict[str, str]) -> tuple[list[Order], list[tuple[Order, str]]]:
        """blocked: {symbol: lý do} từ cửa sổ rủi ro tin — chặn lệnh TĂNG rủi ro, cho phép giảm.
        Giới hạn lệnh/phút: các lệnh cùng 1 quyết định có cùng mốc thời gian -> tối đa N lệnh, ưu tiên lệnh giảm rủi ro."""
        accepted: list[Order] = []
        rejected: list[tuple[Order, str]] = []
        ordered = sorted(orders, key=lambda o: (0 if self.is_reducing(o, positions.get(o.symbol, 0.0)) else 1, o.symbol))
        limit = int(self.cfg["max_orders_per_minute"])
        for o in ordered:
            red = self.is_reducing(o, positions.get(o.symbol, 0.0))
            if o.symbol in blocked and not red:
                rejected.append((o, f"risk_window:{blocked[o.symbol]}"))
            elif len(accepted) >= limit:
                rejected.append((o, "rate_limit"))
            else:
                accepted.append(o)
        return accepted, rejected


def blocked_symbols(windows: list[dict], symbols: list[str], ts: datetime, pre_min: float, post_min: float,
                    ccys_of) -> dict[str, str]:
    """Symbol nào đang trong cửa sổ rủi ro tin. window: {start,end(datetime),currencies[],symbols[],title}."""
    ts = utc(ts)
    out: dict[str, str] = {}
    for w in windows:
        pre, post = (0.0, 0.0) if w.get("padded") else (pre_min, post_min)      # cửa sổ từ api-gateway đã gồm T-15..T+30
        start, end = utc(w["start"]) - timedelta(minutes=pre), utc(w["end"]) + timedelta(minutes=post)
        if not (start <= ts <= end):
            continue
        wc, ws = set(w.get("currencies") or []), set(w.get("symbols") or [])
        for s in symbols:
            if s in ws or (wc and wc & set(ccys_of(s))):
                out.setdefault(s, w.get("title") or "news")
    return out
