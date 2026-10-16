from __future__ import annotations

from ..models import Targets
from ..strategy import Strategy, StrategyContext, register


@register("buy_and_hold")
class BuyAndHold(Strategy):
    """Đối chứng (benchmark): giữ đều tỷ trọng trên universe, chỉ vào lệnh một lần (rebalance: first_only).
    params: gross (tổng tỷ trọng, mặc định 1.0), weights (tuỳ chọn {symbol: tỷ trọng})."""

    @property
    def required_history(self) -> int:
        return 1

    def targets(self, ctx: StrategyContext) -> Targets:
        avail = [s for s in ctx.universe if s in ctx.history and len(ctx.history[s]) >= 1]
        if not avail:
            return Targets(status="warming_up", meta={"reason": "chưa có dữ liệu"})
        explicit = self.params.get("weights")
        if explicit:
            w = {s: float(explicit[s]) for s in avail if s in explicit}
        else:
            gross = float(self.params.get("gross", 1.0))
            w = {s: gross / len(avail) for s in avail}
        return Targets(weights=w, kind="weight", meta={"rule": "buy_and_hold"})
