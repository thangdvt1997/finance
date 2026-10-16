"""Điều phối: nạp dữ liệu (I/O) -> tính (hàm thuần) -> báo cáo rủi ro mỗi tài khoản. READ-ONLY."""
from __future__ import annotations

import json
import asyncio
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import budget as bd
from . import stress as st
from .drawdown import drawdown_report
from .exposure import margin_metrics, mt_holdings, paper_holdings, summarize
from .portfolio import portfolio_risk
from .sources import RiskSource

DISCLAIMER = "READ-ONLY: số liệu ước tính từ snapshot/lịch sử, không phải lời khuyên đầu tư và không thay số margin của broker."


def _positions(v) -> list[dict]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return [p for p in (v or []) if isinstance(p, dict) and p.get("symbol")]


class RiskService:
    def __init__(self, source: RiskSource, cfg: dict, clock=lambda: datetime.now(timezone.utc)):
        self.src = source
        self.cfg = cfg
        self.clock = clock
        self._cache: dict[str, tuple[float, dict]] = {}
        self._closes_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}      # nến D1 đổi chậm -> dùng chung giữa các tài khoản + chu kỳ nền
        self._closes_lock = asyncio.Lock()

    async def _closes(self, symbols, start, end=None) -> pd.DataFrame:
        """src.closes có cache (TTL closes_cache_seconds, mặc định 600 s): truy vấn bars là phần nặng nhất của báo cáo (QA 2026-10-15)."""
        key = (tuple(symbols), start.date().isoformat(), end.date().isoformat() if end else None)
        ttl = float(self.cfg.get("closes_cache_seconds", 600))
        hit = self._closes_cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        async with self._closes_lock:
            hit = self._closes_cache.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            df = await self.src.closes(symbols, start, end)
            if len(self._closes_cache) > 256:
                self._closes_cache.clear()
            self._closes_cache[key] = (time.monotonic(), df)
            return df

    async def accounts(self) -> list[dict]:
        out = []
        for r in await self.src.mt_accounts():
            out.append({"account_id": r["account_id"], "kind": "mt", "platform": r["platform"], "ts": r["ts"]})
        for r in await self.src.paper_accounts():
            out.append({"account_id": r["account_id"], "kind": "paper", "platform": "paper", "ts": r["ts"],
                        "meaningful": bool(r["meaningful"])})
        return out

    async def report(self, account_id: str, use_cache: bool = True, max_age: float | None = None) -> dict | None:
        hit = self._cache.get(account_id)
        ttl = float(self.cfg.get("cache_seconds", 20)) if max_age is None else max_age
        if use_cache and hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        rep = await self._build(account_id)
        if rep is not None:
            self._cache[account_id] = (time.monotonic(), rep)
        return rep

    async def summaries(self) -> list[dict]:
        out = []
        # Vòng nền (interval_seconds) đã tính nóng cache từng tài khoản: tóm tắt chấp nhận bản <= 1,5 chu kỳ
        # để GET /risk/accounts không phải tính lạnh (1,6-8 s với 19 tài khoản; QA 2026-10-15).
        warm = float(self.cfg.get("interval_seconds", 60)) * 1.5
        for a in await self.accounts():
            try:
                rep = await self.report(a["account_id"], max_age=warm)
            except Exception as e:  # noqa: BLE001
                out.append({"account_id": a["account_id"], "kind": a["kind"], "error": type(e).__name__})
                continue
            if rep:
                out.append(summary(rep))
        return out

    async def _build(self, account_id: str) -> dict | None:
        now = self.clock()
        mt = {r["account_id"]: r for r in await self.src.mt_accounts()}
        if account_id in mt:
            return await self._build_mt(mt[account_id], now)
        pa = {r["account_id"]: r for r in await self.src.paper_accounts()}
        if account_id in pa:
            return await self._build_paper(pa[account_id], now)
        return None

    async def _closes_for(self, symbols: list[str], now: datetime) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        cfg = self.cfg
        if not symbols:
            return pd.DataFrame(), {}
        hist = await self._closes(symbols, now - timedelta(days=int(cfg.get("returns_lookback_days", 750)) * 1.5 + 10), now)
        by: dict[str, pd.DataFrame] = {}
        for s in cfg.get("scenarios", []):
            if s.get("type") == "replay":
                a = datetime.fromisoformat(s["start"]).replace(tzinfo=timezone.utc) - timedelta(days=8)
                b = datetime.fromisoformat(s["end"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
                by[s["id"]] = await self._closes(symbols, a, b)
        return hist, by

    async def _finish(self, *, account: dict, kind: str, holdings, equity, margin, eq_series, now, warns) -> dict:
        cfg = self.cfg
        exp = summarize(holdings, equity, account.get("platform", ""), account.get("margin_mode") or "unknown")
        syms = sorted({h.symbol for h in holdings})
        hist, by = await self._closes_for(syms, now)
        net = {r["symbol"]: r["net_value"] for r in exp["by_symbol"]}
        var = portfolio_risk(net, hist, equity, cfg)
        so_eq = margin["stop_out_equity"] if margin and margin.get("margin_used") else None
        scen = st.run_all(cfg.get("scenarios", []), holdings, by, equity, so_eq)
        dd = drawdown_report(eq_series, now)
        es_pct = var["hist"]["es"]["es_pct"] if var.get("available") else None
        items = bd.evaluate(
            cfg, kind, account["account_id"],
            day_pnl_pct=dd.get("day", {}).get("pnl_pct") if dd.get("available") else None,
            week_pnl_pct=dd.get("week", {}).get("pnl_pct") if dd.get("available") else None,
            dd_from_peak_pct=dd.get("dd_from_peak_pct") if dd.get("available") else None,
            leverage_gross=exp["leverage_gross"], margin_level=(margin or {}).get("margin_level_pct"),
            es_1d_pct=es_pct, ccy_conc_pct=exp["max_ccy_conc_pct"], positions=exp["positions"])
        age = (now - account["ts"]).total_seconds() if account.get("ts") else None
        return {
            "read_only": True, "disclaimer": DISCLAIMER, "generated_at": now.isoformat(),
            "account": {**{k: account.get(k) for k in ("account_id", "kind", "platform", "currency", "equity", "balance",
                                                       "margin_mode", "leverage", "name", "strategy", "meaningful")},
                        "ts": account["ts"].isoformat() if account.get("ts") else None, "age_seconds": age},
            "margin": margin, "exposure": exp, "drawdown": dd, "var": var, "stress": scen,
            "budget": {"items": items, "status": bd.worst_status(items)},
            "warnings": warns + exp["warnings"] + ([] if var.get("available") else [f"VaR: {var.get('reason')}"]),
        }

    async def _build_mt(self, row: dict, now: datetime) -> dict:
        cfg = self.cfg
        meta = await self.src.mt_meta(row["account_id"])
        ccy = meta.get("currency") or cfg.get("default_currency", "USD")
        pos = _positions(row["positions"])
        syms = {p["symbol"] for p in pos}
        # tỷ giá quy đổi: nến D1 gần nhất của mọi cặp FX cần thiết (thêm cặp USD cầu nối)
        fxs = {s for s in syms} | {f"{c}USD" for c in ("EUR", "GBP", "AUD", "NZD")} | {f"USD{c}" for c in ("JPY", "CHF", "CAD")}
        px_df = await self._closes(sorted(fxs), now - timedelta(days=10), now)
        prices = {c: float(px_df[c].dropna().iloc[-1]) for c in px_df.columns if not px_df[c].dropna().empty}
        holdings, warns = mt_holdings(pos, ccy, prices, cfg)
        mt = cfg["mt"]
        exp0 = summarize(holdings, row["equity"], row["platform"], meta.get("margin_mode") or "unknown")
        margin = margin_metrics(row["equity"], row["balance"], row["margin"], exp0["gross_notional"], exp0["net_notional_abs"],
                                meta.get("leverage"), mt["stop_out_pct"], mt["margin_call_pct"], mt["margin_level_warn_pct"])
        eq_series = await self.src.mt_equity(row["account_id"], int(cfg.get("equity_history_days", 30)))
        acct = {"account_id": row["account_id"], "kind": "mt", "platform": row["platform"], "currency": ccy, "equity": row["equity"],
                "balance": row["balance"], "margin_mode": meta.get("margin_mode") or exp0["mode"], "leverage": meta.get("leverage"),
                "ts": row["ts"]}
        rep = await self._finish(account=acct, kind="mt", holdings=holdings, equity=row["equity"], margin=margin,
                                 eq_series=eq_series, now=now, warns=warns)
        if not meta:
            rep["warnings"].append("Chưa đọc được metadata tài khoản từ Redis (tiền tệ/đòn bẩy): dùng mặc định cấu hình")
        return rep

    async def _build_paper(self, row: dict, now: datetime) -> dict:
        cfg = self.cfg
        pos = await self.src.paper_positions(row["account_id"])
        ccy = row["base_ccy"]
        holdings = paper_holdings(pos, ccy, cfg)
        eq_series = await self.src.paper_equity(row["account_id"], int(cfg.get("equity_history_days", 30)) * 3)
        equity = row["equity"] if row["equity"] is not None else row["initial_capital"]
        acct = {"account_id": row["account_id"], "kind": "paper", "platform": "paper", "currency": ccy, "equity": equity,
                "balance": row["cash"], "name": row["name"], "strategy": row["strategy"], "meaningful": bool(row["meaningful"]),
                "ts": row["ts"] or now}
        rep = await self._finish(account=acct, kind="paper", holdings=holdings, equity=equity, margin=None, eq_series=eq_series,
                                 now=now, warns=[])
        if not row["meaningful"]:
            rep["warnings"].append("Tài khoản paper replay/thử nghiệm (không đại diện): chỉ dùng để kiểm chứng engine")
        return rep


def summary(rep: dict) -> dict:
    a, dd, var, mg = rep["account"], rep["drawdown"], rep["var"], rep.get("margin") or {}
    ok = dd.get("available")
    worst = rep["stress"][0] if rep["stress"] else None
    return {
        "account_id": a["account_id"], "kind": a["kind"], "platform": a["platform"], "currency": a.get("currency"),
        "name": a.get("name"), "meaningful": a.get("meaningful"), "equity": a.get("equity"), "ts": a.get("ts"),
        "margin_level": mg.get("margin_level_pct"), "margin_status": mg.get("status"),
        "leverage_effective": rep["exposure"]["leverage_gross"], "positions": rep["exposure"]["positions"],
        "day_pnl_pct": dd["day"]["pnl_pct"] if ok else None,
        "dd_from_peak_pct": dd["dd_from_peak_pct"] if ok else None, "max_dd_pct": dd["max_dd_pct"] if ok else None,
        "var95_1d_pct": var["hist"]["95"]["var_pct"] if var.get("available") else None,
        "es975_1d_pct": var["hist"]["es"]["es_pct"] if var.get("available") else None,
        "worst_stress": ({"name": worst["name"], "pnl_pct": worst["pnl_pct"]} if worst else None),
        "budget_status": rep["budget"]["status"], "warnings": rep["warnings"],
        "stale": bool(a.get("age_seconds") is not None and a["age_seconds"] > (900 if a["kind"] == "mt" else 4 * 86400)),
    }
