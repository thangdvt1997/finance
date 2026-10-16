"""Engine mô phỏng theo bar (thuần, KHÔNG I/O, tất định, replay được).

Mỗi bước = 1 bar đã đóng T (đóng cửa = T + tf):
  1) khớp các lệnh chờ đủ điều kiện ở GIÁ MỞ CỬA của bar T (lệnh ra quyết định ở bar trước => không look-ahead)
  2) tính swap/funding, định giá theo giá đóng cửa, cập nhật đỉnh/lỗ ngày/tuần
  3) kiểm tra kill-switch (tự khoá + tất toán), mở khoá tạm khi hết hạn
  4) tới kỳ rebalance: Strategy -> mục tiêu -> RISK ENGINE -> lệnh MÔ PHỎNG (khớp ở bar kế tiếp)
Engine KHÔNG import/gọi bất kỳ broker/MT/bridge nào."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from . import portfolio as pf
from .execution import simulate_fill
from .market import MarketView
from .models import AccountState, Instrument, Order, StepResult, Targets, TF_DELTA, utc
from .risk import RiskEngine, blocked_symbols
from .strategy import Strategy, StrategyContext

log = logging.getLogger("paper.engine")


class Engine:
    def __init__(self, account_id: str, base_ccy: str, instruments: dict[str, Instrument], universe: list[str],
                 strategy: Strategy, risk: RiskEngine, tf: str = "D1", rebalance: str = "monthly",
                 initial_capital: float = 10_000.0, max_pending_steps: int = 5, state: AccountState | None = None):
        self.account_id, self.base, self.instruments, self.universe = account_id, base_ccy, instruments, list(universe)
        self.strategy, self.risk, self.tf, self.td = strategy, risk, tf, TF_DELTA[tf]
        self.rebalance, self.max_pending = rebalance, max_pending_steps
        self.state = state or AccountState(cash=initial_capital, initial_capital=initial_capital, hwm=initial_capital,
                                           last_equity=initial_capital, day_start_equity=initial_capital,
                                           week_start_equity=initial_capital)

    # ------------------------------------------------------------------ tiện ích
    def required_symbols(self) -> list[str]:
        out = list(self.universe)
        for s in self.universe:
            for c in pf.conversion_candidates(self.instruments[s].quote, self.base):
                if c not in out:
                    out.append(c)
        return out

    def _rb_key(self, T: datetime) -> str:
        if self.rebalance == "daily":
            return T.date().isoformat()
        if self.rebalance == "weekly":
            y, w, _ = T.isocalendar()
            return f"{y}-W{w:02d}"
        if self.rebalance == "monthly":
            return f"{T.year}-{T.month:02d}"
        if self.rebalance == "first_only":
            return "once"
        raise ValueError(f"rebalance không hợp lệ: {self.rebalance}")

    def _swap_cost(self, days: float, price_of) -> float:
        if days <= 0:
            return 0.0
        total = 0.0
        for sym, pos in self.state.positions.items():
            if pos.qty == 0:
                continue
            inst = self.instruments[sym]
            px = price_of(sym)
            if px is None:
                px = pos.avg_price
            conv = pf.q2b(inst.quote, self.base, price_of) or 1.0
            rate = inst.swap_long_bps if pos.qty > 0 else inst.swap_short_bps
            total += abs(pos.qty * px * conv) * rate / 1e4 * days / 365.0
        return total

    @staticmethod
    def _event(key: str, typ: str, sev: str, msg: str, data: dict, ts: datetime) -> dict:
        return {"key": key, "type": typ, "severity": sev, "message": msg, "data": data, "ts": ts}

    # ------------------------------------------------------------------ 1 bước
    def step(self, T: datetime, view: MarketView, analytics: dict | None = None,
             windows: list[dict] | None = None) -> StepResult:
        st, T = self.state, utc(T)
        close_ts = T + self.td
        if st.last_close is not None and close_ts <= st.last_close:
            raise ValueError(f"bước {T} đã xử lý (last_close={st.last_close})")
        res = StepResult(bar_ts=T, close_ts=close_ts)
        close_px = lambda s: view.close_at(s, T)          # noqa: E731
        open_px = lambda s: view.open_at(s, T)            # noqa: E731
        prev_prices = st.last_prices
        swap = 0.0
        if st.last_close is not None:                     # khoảng nghỉ (cuối tuần/lễ) trước bar T: giữ vị thế cũ
            swap += self._swap_cost((T - st.last_close).total_seconds() / 86400.0, lambda s: prev_prices.get(s))

        # 1) khớp lệnh chờ
        still: list[Order] = []
        for o in sorted(st.pending, key=lambda x: (x.symbol, x.client_order_id)):
            bar = view.bar_at(o.symbol, T)
            o.age += 1
            if bar is not None and T >= o.eligible_from:
                inst = self.instruments[o.symbol]
                conv = pf.q2b(inst.quote, self.base, open_px)
                if conv is None:
                    o.status, o.reason = "rejected", "no_fx_rate"
                    res.order_updates.append(o)
                    continue
                f = simulate_fill(o, bar, inst, conv)
                pf.apply_fill(st, f)
                o.status = "filled"
                res.fills.append(f)
                res.order_updates.append(o)
                res.events.append(self._event(f"fill:{o.client_order_id}", "fill", "info",
                                              f"[MÔ PHỎNG] khớp {o.side} {o.qty:g} {o.symbol} @ {f.price:.6g}",
                                              {"symbol": o.symbol, "side": o.side, "qty": o.qty, "price": f.price, "ref_price": f.ref_price,
                                               "commission": f.commission, "tax": f.tax, "realized_pnl": f.realized_pnl,
                                               "client_order_id": o.client_order_id}, T))
            elif o.age > self.max_pending:
                o.status, o.reason = "expired", "no_bar"
                res.order_updates.append(o)
            else:
                still.append(o)
        st.pending = still

        # 2) swap trong bar + định giá
        swap += self._swap_cost(self.td.total_seconds() / 86400.0, close_px)
        st.cash -= swap
        st.costs["swap"] += swap
        res.swap_step = swap
        equity, gross, net, detail = pf.mark(st, self.base, self.instruments, close_px)
        st.hwm = max(st.hwm, equity)
        dd = equity / st.hwm - 1.0 if st.hwm > 0 else 0.0
        day_key, week_key = T.date().isoformat(), "{}-W{:02d}".format(*T.isocalendar()[:2])
        if st.day_key != day_key:
            st.day_start_equity, st.day_key = st.last_equity, day_key
        if st.week_key != week_key:
            st.week_start_equity, st.week_key = st.last_equity, week_key

        # 3) kill-switch
        if st.status == "halted" and st.halt_until is not None and T >= st.halt_until:
            res.events.append(self._event(f"release:{T.isoformat()}", "halt_released", "info",
                                          f"[MÔ PHỎNG] mở khoá tạm dừng ({st.halt_reason})", {"reason": st.halt_reason}, T))
            st.status, st.halt_reason, st.halt_until = "active", "", None
            st.last_rebalance_key = None                  # cho phép quyết định lại ngay
        breach = None
        if st.status != "locked":
            breach = self.risk.check_account(equity, st.hwm, st.day_start_equity, st.week_start_equity)
            if breach and st.status == "halted" and not breach.hard:
                breach = None                              # đã tạm dừng rồi
        if breach:
            self._engage(breach, T, close_ts, view, equity, res)

        # 4) quyết định
        if st.status == "active":
            key = self._rb_key(T)
            if st.last_rebalance_key != key:
                self._decide(T, close_ts, key, view, equity, analytics, windows or [], res)

        st.last_close = close_ts
        st.last_equity = equity
        st.last_prices = {s: p for s in set(self.required_symbols()) | set(st.positions) if (p := close_px(s)) is not None}
        res.equity, res.cash, res.gross, res.net, res.drawdown = equity, st.cash, gross, net, dd
        res.positions = detail
        return res

    # ------------------------------------------------------------------ kill-switch
    def _engage(self, b, T: datetime, close_ts: datetime, view: MarketView, equity: float, res: StepResult) -> None:
        st = self.state
        for o in st.pending:
            o.status, o.reason = "cancelled", f"kill_switch:{b.kind}"
            res.order_updates.append(o)
        st.pending = []
        if b.kind == "daily":
            until = datetime.combine(T.date() + timedelta(days=1), datetime.min.time(), tzinfo=T.tzinfo)
        elif b.kind == "weekly":
            until = datetime.combine(T.date() + timedelta(days=7 - T.weekday()), datetime.min.time(), tzinfo=T.tzinfo)
        else:
            until = None
        st.status = "locked" if b.hard else "halted"
        st.halt_reason, st.halt_until = f"{b.kind} {b.value:+.2%} (giới hạn {b.limit:+.2%})", until
        flat = []
        if self.risk.cfg["flatten_on_halt"]:
            for sym, pos in sorted(st.positions.items()):
                if abs(pos.qty) > 1e-9:
                    o = Order(client_order_id=f"{self.account_id}:{close_ts:%Y%m%dT%H%M%S}:{sym}:flat", account_id=self.account_id, symbol=sym,
                              side="sell" if pos.qty > 0 else "buy", qty=abs(pos.qty), decision_ts=close_ts, eligible_from=close_ts,
                              kind="flatten", reason=f"kill_switch:{b.kind}", ref_price=view.close_at(sym, T) or 0.0)
                    flat.append(o)
        st.pending.extend(flat)
        st.n_orders += len(flat)
        res.new_orders.extend(flat)
        res.events.append(self._event(f"kill:{b.kind}:{T.isoformat()}", "kill_switch", "crit",
                                      f"[MÔ PHỎNG] KILL-SWITCH {b.kind}: equity {equity:,.2f}, {st.halt_reason}; {'KHOÁ CỨNG (reset tay)' if b.hard else 'tạm dừng tới ' + str(until)}; tất toán {len(flat)} vị thế",
                                      {"kind": b.kind, "value": b.value, "limit": b.limit, "hard": b.hard, "status": st.status,
                                       "halt_until": until.isoformat() if until else None, "flatten_orders": len(flat), "equity": equity}, T))

    # ------------------------------------------------------------------ quyết định + sinh lệnh
    def _decide(self, T, close_ts, key, view: MarketView, equity, analytics, windows, res: StepResult) -> None:
        st = self.state
        hist = view.history(self.universe, T)                     # CHỈ bar đã đóng tới T
        ctx = StrategyContext(now=close_ts, tf=self.tf, universe=tuple(self.universe), history=hist, equity=equity,
                              positions={s: p.qty for s, p in st.positions.items()}, analytics=analytics,
                              params=dict(self.strategy.params))
        try:
            tg = self.strategy.targets(ctx)
            if not isinstance(tg, Targets):
                raise TypeError("Strategy.targets phải trả về Targets")
        except Exception as e:  # noqa: BLE001 - plugin lỗi không được làm sập engine
            log.exception("strategy %s lỗi", self.strategy.name)
            res.events.append(self._event(f"strategy_error:{T.isoformat()}", "strategy_error", "warn",
                                          f"[MÔ PHỎNG] chiến lược lỗi: {e}", {"error": str(e)}, T))
            return
        if tg.status != "ok":
            res.events.append(self._event(f"warmup:{self._rb_key(T) if self.rebalance != 'daily' else T.date().isoformat()}:{tg.status}", "warmup", "info",
                                          f"[MÔ PHỎNG] chiến lược '{self.strategy.name}' chưa đủ dữ liệu — đứng ngoài thị trường", dict(tg.meta), T))
            return
        for o in st.pending:                                     # lệnh cũ chưa khớp (thiếu bar) bị thay bằng quyết định mới
            o.status, o.reason = "cancelled", "superseded"
            res.order_updates.append(o)
        st.pending = []
        sized = self.risk.size(tg, hist)
        gated = self.risk.gate(sized.weights, self.universe, {s: self.instruments[s].shortable for s in self.universe})
        notes = sized.notes + gated.notes
        close_px = lambda s: view.close_at(s, T)                  # noqa: E731
        orders: list[Order] = []
        for s in self.universe:
            w = gated.weights.get(s, 0.0)
            inst = self.instruments[s]
            px, conv = close_px(s), pf.q2b(inst.quote, self.base, close_px)
            if px is None or conv is None or equity <= 0:
                notes.append({"code": "no_price_or_rate", "symbol": s})
                continue
            unit = px * conv
            lots = w * equity / unit / inst.lot
            target = math.trunc(round(lots, 6)) * inst.lot          # round(6) tránh sai số dấu phẩy động (9999.99999999 -> 10000)
            cur = st.positions.get(s).qty if s in st.positions else 0.0
            delta = target - cur
            if abs(delta) < inst.lot / 2:
                continue
            if target != 0 and abs(delta) * unit / equity < float(self.risk.cfg["min_trade_weight"]):
                continue
            orders.append(Order(client_order_id=f"{self.account_id}:{close_ts:%Y%m%dT%H%M%S}:{s}", account_id=self.account_id, symbol=s,
                                side="buy" if delta > 0 else "sell", qty=round(abs(delta), 8), decision_ts=close_ts,
                                eligible_from=close_ts, target_weight=w, ref_price=px))
        blocked = blocked_symbols(windows, self.universe, close_ts, float(self.risk.cfg["news_block_pre_min"]),
                                  float(self.risk.cfg["news_block_post_min"]), pf.symbol_ccys)
        ok, rejected = self.risk.filter_orders(orders, {s: p.qty for s, p in st.positions.items()}, blocked)
        for o, why in rejected:
            o.status, o.reason = "rejected", why
            res.new_orders.append(o)
            res.events.append(self._event(f"reject:{o.client_order_id}", "risk_reject", "warn",
                                          f"[MÔ PHỎNG] risk engine chặn lệnh {o.side} {o.qty:g} {o.symbol}: {why}",
                                          {"symbol": o.symbol, "reason": why}, T))
        st.pending.extend(ok)
        res.new_orders.extend(ok)
        st.n_orders += len(ok) + len(rejected)
        if not rejected:                                       # lệnh bị chặn (cửa sổ tin/rate limit) -> thử lại ở bar kế
            st.last_rebalance_key = key
        summary = ", ".join(f"{o.side} {o.qty:g} {o.symbol}" for o in ok) or "không đổi vị thế"
        res.events.append(self._event(f"rebalance:{close_ts.isoformat()}", "rebalance", "info",
                                      f"[MÔ PHỎNG] {self.account_id}: tái cân bằng ({self.strategy.name}) — {summary}",
                                      {"weights": {s: round(w, 6) for s, w in gated.weights.items()}, "kind": tg.kind, "notes": notes,
                                       "strategy_meta": tg.meta, "orders": [o.to_dict() for o in ok], "rejected": len(rejected),
                                       "equity": equity}, T))

    # ------------------------------------------------------------------ lệnh tay (qua API admin) — vẫn chỉ là mô phỏng
    def manual_reset(self, ts: datetime) -> dict:
        st = self.state
        prev = (st.status, st.halt_reason)
        st.status, st.halt_reason, st.halt_until = "active", "", None
        st.hwm = max(st.last_equity, 0.0)                    # đặt lại đỉnh để kill-switch drawdown không bật lại ngay
        st.last_rebalance_key = None
        return self._event(f"reset:{ts.isoformat()}", "kill_switch_reset", "warn",
                           f"[MÔ PHỎNG] reset kill-switch thủ công (trước: {prev[0]} {prev[1]})",
                           {"previous_status": prev[0], "previous_reason": prev[1], "hwm": st.hwm}, ts)

    def manual_halt(self, ts: datetime, reason: str = "manual") -> dict:
        st = self.state
        st.status, st.halt_reason, st.halt_until = "locked", f"manual: {reason}", None
        return self._event(f"halt:{ts.isoformat()}", "kill_switch", "crit", f"[MÔ PHỎNG] khoá chiến lược thủ công: {reason}",
                           {"kind": "manual", "hard": True}, ts)
