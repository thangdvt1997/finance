"""CFTC Commitments of Traders (Legacy, futures only) qua Socrata API cong khai (khong key).

Phat: (1) expert.positions expert_id='CFTC:<contract_code>' net_volume = long - short nhom non-commercial;
      (2) 1 news_item tom tat moi bao cao hang tuan.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..models import Emit, iso
from .base import Context, Source, news_emit

log = logging.getLogger("news_collector.cot")
API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_cot(rows: list[dict], contracts: dict, ctx: Context) -> list[Emit]:
    out: list[Emit] = []
    summary_lines: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        code = str(r.get("cftc_contract_market_code", "")).strip()
        spec = contracts.get(code)
        if not spec:
            continue
        long_, short = _f(r.get("noncomm_positions_long_all")), _f(r.get("noncomm_positions_short_all"))
        if long_ is None or short is None:
            continue
        try:
            as_of = datetime.fromisoformat(r["report_date_as_yyyy_mm_dd"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        net = long_ - short
        payload = {"expert_id": f"CFTC:{code}", "source": "cftc", "symbol": spec["symbol"], "net_volume": net,
                   "avg_price": None, "as_of": iso(as_of),
                   "raw": {"contract": r.get("market_and_exchange_names"), "noncomm_long": long_, "noncomm_short": short,
                           "open_interest": _f(r.get("open_interest_all")),
                           "change_noncomm_long": _f(r.get("change_in_noncomm_long_all")),
                           "change_noncomm_short": _f(r.get("change_in_noncomm_short_all")),
                           "pair_direction": -1 if spec.get("invert") else 1,
                           "note": "net_volume = net non-commercial cua hop dong futures; pair_direction=-1: dao dau so voi cap"}}
        out.append(Emit("expert_positions", "expert_position", payload, f"cot:{code}:{payload['as_of']}"))
        summary_lines.setdefault(payload["as_of"], []).append(
            (spec["symbol"], f"{spec['symbol']}: net {net:+,.0f} (L {long_:,.0f} / S {short:,.0f})"))
    latest = max(summary_lines, default=None)   # chi tom tat bao cao MOI NHAT thanh tin (limit lon = backfill lich su vi the, khong tao tin cu)
    for as_of, items in summary_lines.items():
        if as_of != latest:
            continue
        d = as_of[:10]
        out.append(news_emit(ctx, url=f"https://www.cftc.gov/dea/futures/deacmesf.htm#{d}",
                             title=f"CFTC COT {d}: vi the non-commercial",
                             summary="; ".join(sorted(t for _, t in items)),
                             published_at=datetime.fromisoformat(as_of), source="cftc", lang="en",
                             default_symbols=[s for s, _ in items]))
    return out


class CotSource(Source):
    name = "cot"

    def __init__(self, interval: float = 21600):
        self.interval = interval

    async def fetch(self, ctx: Context) -> list[Emit]:
        cfg = ctx.load_yaml("cot_contracts.yaml")
        contracts = {str(k): v for k, v in cfg.get("contracts", {}).items()}
        codes = ",".join(f"'{c}'" for c in contracts)
        params = {"$where": f"cftc_contract_market_code in({codes})", "$order": "report_date_as_yyyy_mm_dd DESC",
                  "$limit": str(cfg.get("limit", len(contracts) * 2))}
        body, _ = await ctx.client.get(API, params=params, use_cache=False)
        return parse_cot(json.loads(body), contracts, ctx)
