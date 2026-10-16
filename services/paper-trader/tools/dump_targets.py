"""Xuất mục tiêu danh mục của một tài khoản (KHÔNG giao dịch, chỉ đọc bars) ra JSON — để đối chiếu với backtest.
Chạy trong container paper-trader:  docker exec -i tradingsys-paper-trader python - <account_id> [YYYY-MM-DD] < tools/dump_targets.py
Tham số 2 (tuỳ chọn): cắt lịch sử tới ngày đó (as-of) để so cùng ngày với backtest."""
import asyncio
import json
import sys

import pandas as pd

from paper_trader.config import Settings, instrument_for, load_yaml
from paper_trader.market import frame_from_rows
from paper_trader.repo import PgBarSource
from paper_trader.runner import load_params
from paper_trader.strategy import StrategyContext, build, load_plugins


async def main(aid: str, asof: str | None):
    st = Settings()
    cfg = load_yaml(st.config_path)
    load_plugins(st.strategy_dir)
    acfg = next(a for a in cfg["accounts"] if a["id"] == aid)
    src = await PgBarSource.connect(st.read_url)
    n = int(cfg.get("history_bars", 520))
    hist = {}
    for s in acfg["universe"]:
        df = frame_from_rows(await src.bars(s, cfg.get("tf", "D1"), n))
        if asof:
            df = df[df.index <= pd.Timestamp(asof, tz="UTC")]
        if not df.empty:
            hist[s] = df
    strat = build(acfg["strategy"], load_params(acfg))
    last = max(df.index[-1] for df in hist.values())
    ctx = StrategyContext(now=last.to_pydatetime(), tf="D1", universe=tuple(acfg["universe"]), history=hist, equity=float(acfg["initial_capital"]),
                          positions={}, params=dict(strat.params))
    tg = strat.targets(ctx)
    print(json.dumps({"account": aid, "status": tg.status, "kind": tg.kind, "weights": tg.weights, "meta": tg.meta, "asof": str(last.date())}, default=str))
    await src.close()


asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
