from __future__ import annotations

import numpy as np

from ..models import Targets
from ..strategy import Strategy, StrategyContext, register


@register("slow_trend_simple")
class SlowTrendSimple(Strategy):
    """[LEGACY, KHÔNG khớp backtest] Trend chậm đơn giản: momentum 12-1 tháng + lọc MA200, kích thước bởi vol targeting (risk engine).
    Long khi momentum>0 VÀ giá>MA; short (nếu allow_short) khi momentum<0 VÀ giá<MA; còn lại đứng ngoài.
    params: momentum_days=252, skip_days=21, ma_days=200, allow_short=true, min_symbols=1.
    Trả về 'conviction' (-1/0/+1); risk engine đổi sang tỷ trọng theo biến động (nghịch đảo vol, KHÔNG ngân sách theo lớp).
    Giữ lại để test đường ống/smoke; plugin dùng cho forward test là `slow_trend_multiasset` (ensemble đúng backtest)."""

    @property
    def required_history(self) -> int:
        p = self.params
        return max(int(p.get("momentum_days", 252)) + int(p.get("skip_days", 21)) + 1, int(p.get("ma_days", 200)))

    def targets(self, ctx: StrategyContext) -> Targets:
        need = self.required_history
        mom_d, skip, ma_d = int(self.params.get("momentum_days", 252)), int(self.params.get("skip_days", 21)), int(self.params.get("ma_days", 200))
        allow_short = bool(self.params.get("allow_short", True))
        sig: dict[str, float] = {}
        short_hist: dict[str, int] = {}
        for sym in ctx.universe:
            df = ctx.history.get(sym)
            n = 0 if df is None else len(df)
            if n < need:
                short_hist[sym] = n
                continue
            c = df["c"].to_numpy(dtype=float)
            last = c[-1]
            mom = c[-1 - skip] / c[-1 - skip - mom_d] - 1.0     # lợi suất [t-12m, t-1m] (bỏ tháng gần nhất)
            ma = float(np.mean(c[-ma_d:]))
            if mom > 0 and last > ma:
                sig[sym] = 1.0
            elif mom < 0 and last < ma and allow_short:
                sig[sym] = -1.0
            else:
                sig[sym] = 0.0
        if len(sig) < int(self.params.get("min_symbols", 1)):
            return Targets(status="warming_up", meta={"need_bars": need, "have_bars": short_hist})
        return Targets(weights=sig, kind="conviction", meta={"need_bars": need, "short_history": short_hist})
