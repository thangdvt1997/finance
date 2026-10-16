"""Thống kê hiệu suất bằng OSS empyrical-reloaded (CAGR, vol, Sharpe, Sortino, Calmar, MaxDD, alpha/beta).
Mẫu ngắn -> cờ `reliable=false` (không diễn giải Sharpe/CAGR khi < 60 ngày; CAGR ẩn khi < 30 ngày)."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

MIN_DAYS_CAGR = 30
MIN_DAYS_RELIABLE = 60


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def equity_series(rows: list[dict]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([float(r["equity"]) for r in rows], index=pd.to_datetime([r["ts"] for r in rows], utc=True)).sort_index()
    return s[~s.index.duplicated(keep="last")]


def daily_returns(eq: pd.Series, initial: float | None = None) -> pd.Series:
    if eq.empty:
        return pd.Series(dtype=float)
    d = eq.resample("1D").last().dropna()
    if initial and initial > 0:
        d = pd.concat([pd.Series([initial], index=[d.index[0] - pd.Timedelta(days=1)]), d])
    return d.pct_change().dropna()


def stats(eq_rows: list[dict], bench_rows: list[dict] | None = None, initial: float | None = None, ppy: int = 252) -> dict:
    import empyrical as ep
    eq = equity_series(eq_rows)
    out: dict[str, Any] = {"points": len(eq), "reliable": False}
    if eq.empty:
        return out
    r = daily_returns(eq, initial)
    n = len(r)
    base = initial if initial else float(eq.iloc[0])
    out.update(start=eq.index[0].isoformat(), end=eq.index[-1].isoformat(), days=n, equity=float(eq.iloc[-1]),
               total_return=_f(eq.iloc[-1] / base - 1.0))
    run_max = eq.cummax()
    out["current_drawdown"] = _f((eq / run_max - 1.0).iloc[-1])
    out["reliable"] = n >= MIN_DAYS_RELIABLE
    if n >= 2:
        out["max_drawdown"] = _f(ep.max_drawdown(r))
        out["annual_volatility"] = _f(ep.annual_volatility(r, period="daily", annualization=ppy))
        out["sharpe"] = _f(ep.sharpe_ratio(r, annualization=ppy))
        out["sortino"] = _f(ep.sortino_ratio(r, annualization=ppy))
        out["cagr"] = _f(ep.cagr(r, annualization=ppy)) if n >= MIN_DAYS_CAGR else None
        out["calmar"] = _f(ep.calmar_ratio(r, annualization=ppy)) if n >= MIN_DAYS_CAGR else None
        out["best_day"], out["worst_day"] = _f(r.max()), _f(r.min())
        out["hit_rate"] = _f((r > 0).mean())
    if bench_rows:
        be = equity_series(bench_rows)
        br = daily_returns(be, initial)
        j = pd.concat([r.rename("s"), br.rename("b")], axis=1).dropna()
        if len(j) >= 2 and not be.empty:
            out["benchmark_total_return"] = _f(be.iloc[-1] / (initial if initial else float(be.iloc[0])) - 1.0)
            out["excess_total_return"] = _f((out.get("total_return") or 0) - (out["benchmark_total_return"] or 0))
            ex = j["s"] - j["b"]
            te = float(ex.std(ddof=1) * np.sqrt(ppy))
            out["tracking_error"] = _f(te)
            out["information_ratio"] = _f(float(ex.mean() * ppy) / te) if te > 1e-12 else None
            if len(j) >= MIN_DAYS_CAGR:
                a, b = ep.alpha_beta(j["s"], j["b"], annualization=ppy)
                out["alpha"], out["beta"] = _f(a), _f(b)
    return out


def normalized(rows: list[dict], base: float | None = None) -> list[dict]:
    """Chuẩn hoá về 100 tại điểm đầu (để vẽ equity vs benchmark)."""
    if not rows:
        return []
    b = base if base else float(rows[0]["equity"])
    return [{"ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else r["ts"], "equity": float(r["equity"]),
             "index": 100.0 * float(r["equity"]) / b} for r in rows]
