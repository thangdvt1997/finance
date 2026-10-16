"""Hiệu suất MỞ RỘNG có khoảng tin cậy: CAGR/vol/Sharpe/Sortino/Calmar/MaxDD/%ngày lãi + CI95 (stationary bootstrap, hạt giống cố định),
rolling Sharpe/DD, so với benchmark (alpha/beta, tương quan, TE/IR, up/down capture), đóng góp theo lớp tài sản, đòn bẩy theo thời gian.
Tính thuần numpy/pandas (không I/O). Mẫu ngắn -> trả `ci=None` kèm lý do thay vì số điểm trần: Sharpe đo trên < 1 năm không có nghĩa thống kê."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .perf import MIN_DAYS_CAGR, MIN_DAYS_RELIABLE, daily_returns, equity_series

MIN_DAYS_CI = 20          # dưới ngưỡng này không đưa CI (bootstrap vô nghĩa)
METRICS = ("cagr", "vol", "sharpe", "sortino", "calmar", "max_dd", "hit_rate")


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ------------------------------------------------------------------------------------------------ chỉ số trên MA TRẬN lợi suất (B x n)
def metrics_matrix(R: np.ndarray, ppy: int) -> dict[str, np.ndarray]:
    """Tính 7 chỉ số cho từng hàng của R (mỗi hàng = một chuỗi lợi suất ngày). Công thức khớp empyrical (kiểm thử đối chiếu)."""
    R = np.atleast_2d(R).astype(float)
    n = R.shape[1]
    mean, sd = R.mean(1), (R.std(1, ddof=1) if n > 1 else np.zeros(R.shape[0]))
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(sd > 1e-12, mean / sd * math.sqrt(ppy), np.nan)
        dn = np.sqrt(np.mean(np.minimum(R, 0.0) ** 2, axis=1))
        sortino = np.where(dn > 1e-12, mean / dn * math.sqrt(ppy), np.nan)
        lg = np.where(R > -1.0, np.log1p(np.where(R > -1.0, R, 0.0)), np.nan)
        cagr = np.exp(lg.sum(1) * ppy / n) - 1.0
        cum = np.cumprod(1.0 + R, axis=1)
        cum = np.concatenate([np.ones((R.shape[0], 1)), cum], axis=1)
        dd = cum / np.maximum.accumulate(cum, axis=1) - 1.0
        maxdd = dd.min(1)
        calmar = np.where(maxdd < -1e-12, cagr / np.abs(maxdd), np.nan)
    return {"cagr": cagr, "vol": sd * math.sqrt(ppy), "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
            "max_dd": maxdd, "hit_rate": (R > 0).mean(1)}


def stationary_indices(n: int, B: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Chỉ số bootstrap dừng (Politis–Romano): mỗi bước tiếp tục khối với xác suất 1-1/L, ngược lại nhảy tới vị trí ngẫu nhiên."""
    restart = rng.random((B, n)) < (1.0 / max(mean_block, 1.0))
    restart[:, 0] = True
    rand = rng.integers(0, n, size=(B, n))
    t = np.arange(n)[None, :]
    start_t = np.maximum.accumulate(np.where(restart, t, 0), axis=1)
    base = np.take_along_axis(rand, start_t, axis=1)
    return (base + (t - start_t)) % n


def bootstrap_ci(r: np.ndarray, ppy: int, level: float = 0.95, B: int | None = None, seed: int | None = None) -> dict[str, list[float] | None]:
    n = len(r)
    if n < MIN_DAYS_CI:
        return {m: None for m in METRICS}
    B = B or int(max(300, min(2000, 2_500_000 // n)))
    rng = np.random.default_rng(seed if seed is not None else 1000003 * n + 17)
    L = float(min(20.0, max(2.0, round(1.5 * n ** (1.0 / 3.0)))))
    idx = stationary_indices(n, B, L, rng)
    m = metrics_matrix(r[idx], ppy)
    lo, hi = (1 - level) / 2 * 100, (1 + level) / 2 * 100
    out: dict[str, list[float] | None] = {}
    for k in METRICS:
        v = m[k][np.isfinite(m[k])]
        out[k] = [float(np.percentile(v, lo)), float(np.percentile(v, hi))] if len(v) >= 0.5 * B else None
    out["_meta"] = {"B": B, "mean_block": L, "level": level, "method": "stationary_bootstrap"}      # type: ignore[assignment]
    return out


def point_metrics(r: np.ndarray, ppy: int) -> dict[str, float | None]:
    m = metrics_matrix(r[None, :], ppy)
    return {k: _f(v[0]) for k, v in m.items()}


# ------------------------------------------------------------------------------------------------ rolling
def rolling_table(r: pd.Series, ppy: int, windows: tuple[int, ...] = (30, 90), max_points: int = 400) -> dict:
    """Rolling Sharpe (kèm sai số chuẩn Lo-2002 -> dải 95%) và rolling max drawdown trong cửa sổ. Chỉ trả cửa sổ đã đủ dữ liệu."""
    out: dict[str, Any] = {"windows": [w for w in windows if len(r) >= w], "points": []}
    if not out["windows"]:
        return out
    v = r.to_numpy(float)
    cols: dict[int, dict[str, np.ndarray]] = {}
    for w in out["windows"]:
        sw = np.lib.stride_tricks.sliding_window_view(v, w)
        mean, sd = sw.mean(1), sw.std(1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sh = np.where(sd > 1e-12, mean / sd * math.sqrt(ppy), np.nan)
        se = np.sqrt((1.0 + 0.5 * (sh / math.sqrt(ppy)) ** 2) / w) * math.sqrt(ppy)       # Lo (2002), i.i.d. xấp xỉ
        cum = np.concatenate([np.ones((sw.shape[0], 1)), np.cumprod(1.0 + sw, axis=1)], axis=1)
        dd = (cum / np.maximum.accumulate(cum, axis=1) - 1.0).min(1)
        cols[w] = {"sharpe": sh, "se": se, "dd": dd}
    ts = r.index
    first = min(out["windows"]) - 1
    step = max(1, (len(r) - first) // max_points)
    for i in range(first, len(r), step):
        row: dict[str, Any] = {"ts": ts[i].isoformat()}
        for w in out["windows"]:
            j = i - (w - 1)
            if j >= 0:
                s, se = cols[w]["sharpe"][j], cols[w]["se"][j]
                row[f"sharpe{w}"] = _f(s)
                row[f"sharpe{w}_lo"] = _f(s - 1.96 * se) if np.isfinite(s) else None
                row[f"sharpe{w}_hi"] = _f(s + 1.96 * se) if np.isfinite(s) else None
                row[f"dd{w}"] = _f(cols[w]["dd"][j])
        out["points"].append(row)
    return out


# ------------------------------------------------------------------------------------------------ benchmark
def compare_benchmark(r: pd.Series, br: pd.Series, ppy: int, total_s: float | None, total_b: float | None) -> dict:
    j = pd.concat([r.rename("s"), br.rename("b")], axis=1).dropna()
    out: dict[str, Any] = {"n": int(len(j)), "total_return": total_s, "benchmark_total_return": total_b,
                           "excess_total_return": None if total_s is None or total_b is None else total_s - total_b}
    if len(j) < MIN_DAYS_CI:
        out["note"] = f"cần ≥ {MIN_DAYS_CI} ngày chung để ước lượng alpha/beta/tương quan"
        return out
    s, b = j["s"].to_numpy(), j["b"].to_numpy()
    n = len(j)
    vb = float(np.var(b, ddof=1))
    ex = s - b
    te = float(ex.std(ddof=1) * math.sqrt(ppy))
    out["tracking_error"] = _f(te)
    out["information_ratio"] = _f(ex.mean() * ppy / te) if te > 1e-12 else None
    out["correlation"] = _f(np.corrcoef(s, b)[0, 1]) if vb > 1e-14 and np.var(s) > 1e-14 else None
    if vb > 1e-14:
        beta = float(np.cov(s, b, ddof=1)[0, 1] / vb)
        a_d = float(s.mean() - beta * b.mean())
        resid = s - a_d - beta * b
        s2 = float((resid ** 2).sum() / max(n - 2, 1))
        se_beta = math.sqrt(s2 / (vb * (n - 1)))
        se_a = math.sqrt(s2 * (1.0 / n + b.mean() ** 2 / (vb * (n - 1))))
        out.update(beta=_f(beta), beta_ci=[_f(beta - 1.96 * se_beta), _f(beta + 1.96 * se_beta)],
                   alpha_ann=_f(a_d * ppy), alpha_ci=[_f((a_d - 1.96 * se_a) * ppy), _f((a_d + 1.96 * se_a) * ppy)],
                   alpha_t=_f(a_d / se_a) if se_a > 0 else None)
    up, dn = b > 0, b < 0
    out["up_capture"] = _f(s[up].mean() / b[up].mean()) if up.sum() >= 5 and abs(b[up].mean()) > 1e-12 else None
    out["down_capture"] = _f(s[dn].mean() / b[dn].mean()) if dn.sum() >= 5 and abs(b[dn].mean()) > 1e-12 else None
    out["ci_note"] = "CI alpha/beta: OLS, giả định phần dư độc lập (xấp xỉ); mẫu ngắn -> rất rộng."
    return out


# ------------------------------------------------------------------------------------------------ lớp tài sản
def asset_class(symbol: str) -> str:
    try:
        from .strategies.slow_trend_multiasset import asset_info
        return asset_info(symbol)[0]
    except Exception:  # noqa: BLE001
        return "other"


def attribution(fills: list[dict], positions: list[dict], initial: float, equity_last: float | None, swap_cost: float, base_ccy: str) -> dict:
    """Đóng góp lãi/lỗ theo lớp tài sản (đơn vị tiền tài khoản): đã chốt (đã gồm spread/trượt giá trong giá khớp) − phí − thuế + chưa chốt.
    Phần còn lại sau swap/funding là `unreconciled` (kiểm tra sổ: phải ~0)."""
    by: dict[str, dict[str, float]] = {}

    def slot(sym: str) -> dict[str, float]:
        return by.setdefault(asset_class(sym), {"realized": 0.0, "unrealized": 0.0, "commission": 0.0, "tax": 0.0})
    sym_pnl: dict[str, float] = {}
    for f in fills:
        s = slot(f["symbol"])
        s["realized"] += float(f.get("realized_pnl") or 0.0)
        s["commission"] += float(f.get("commission") or 0.0)
        s["tax"] += float(f.get("tax") or 0.0)
        sym_pnl[f["symbol"]] = sym_pnl.get(f["symbol"], 0.0) + float(f.get("realized_pnl") or 0.0) - float(f.get("commission") or 0.0) - float(f.get("tax") or 0.0)
    for p in positions:
        slot(p["symbol"])["unrealized"] += float(p.get("unrealized_pnl") or 0.0)
        sym_pnl[p["symbol"]] = sym_pnl.get(p["symbol"], 0.0) + float(p.get("unrealized_pnl") or 0.0)
    rows = []
    for c, v in sorted(by.items()):
        pnl = v["realized"] + v["unrealized"] - v["commission"] - v["tax"]
        rows.append({"class": c, **{k: round(x, 4) for k, x in v.items()}, "pnl": round(pnl, 4), "pct_initial": pnl / initial if initial else None})
    total = sum(r["pnl"] for r in rows)
    equity_pnl = None if equity_last is None else equity_last - initial
    top = sorted(sym_pnl.items(), key=lambda kv: kv[1])
    return {"ccy": base_ccy, "classes": rows, "total_trading_pnl": round(total, 4), "swap_funding": round(-swap_cost, 4),
            "equity_pnl": equity_pnl, "unreconciled": None if equity_pnl is None else round(equity_pnl - total + swap_cost, 4),
            "worst_symbols": [{"symbol": s, "pnl": round(v, 4)} for s, v in top[:3]],
            "best_symbols": [{"symbol": s, "pnl": round(v, 4)} for s, v in top[::-1][:3]]}


def leverage_series(eq_rows: list[dict], max_points: int = 300) -> dict:
    pts = [(r["ts"], float(r["gross_exposure"] or 0.0) / float(r["equity"]), float(r["net_exposure"] or 0.0) / float(r["equity"]))
           for r in eq_rows if r.get("equity") and float(r["equity"]) > 0]
    if not pts:
        return {"series": []}
    g = np.array([p[1] for p in pts])
    step = max(1, len(pts) // max_points)
    return {"current_gross": float(g[-1]), "current_net": float(pts[-1][2]), "mean_gross": float(g.mean()), "max_gross": float(g.max()),
            "series": [{"ts": p[0].isoformat() if hasattr(p[0], "isoformat") else p[0], "gross": p[1], "net": p[2]} for p in pts[::step]]}


# ------------------------------------------------------------------------------------------------ báo cáo tổng
def report(eq_rows: list[dict], benches: dict[str, list[dict]], initial: float, ppy: int = 252, fills: list[dict] | None = None,
           positions: list[dict] | None = None, swap_cost: float = 0.0, base_ccy: str = "USD", expectation: dict | None = None) -> dict:
    eq = equity_series(eq_rows)
    r = daily_returns(eq, initial)
    n = len(r)
    out: dict[str, Any] = {"days": n, "reliable": n >= MIN_DAYS_RELIABLE, "ppy": ppy}
    if eq.empty:
        out["note"] = "chưa có điểm equity"
        return out
    base = initial if initial else float(eq.iloc[0])
    out.update(start=eq.index[0].isoformat(), end=eq.index[-1].isoformat(), equity=float(eq.iloc[-1]), total_return=_f(eq.iloc[-1] / base - 1.0))
    if n >= 2:
        pm = point_metrics(r.to_numpy(float), ppy)
        if n < MIN_DAYS_CAGR:
            pm["cagr"] = pm["calmar"] = None
        ci = bootstrap_ci(r.to_numpy(float), ppy)
        meta = ci.pop("_meta", None)
        out["metrics"] = {k: {"value": pm.get(k), "ci95": ci.get(k)} for k in METRICS}
        out["ci_method"] = meta
        out["ci_note"] = None if meta else f"CI cần ≥ {MIN_DAYS_CI} ngày ({n} ngày hiện có): chỉ số điểm CHƯA có ý nghĩa thống kê."
        if n >= MIN_DAYS_RELIABLE:
            out["ci_note"] = None
        elif meta:
            out["ci_note"] = f"Mẫu ngắn ({n} ngày < {MIN_DAYS_RELIABLE}): CI rất rộng, đừng diễn giải số điểm."
        if expectation:
            out["backtest_reference"] = expectation
    else:
        out["note"] = "chưa đủ 2 ngày lợi suất"
    out["rolling"] = rolling_table(r, ppy)
    bm: dict[str, Any] = {}
    for bid, rows in (benches or {}).items():
        if not rows:
            continue
        be = equity_series(rows)
        if be.empty:
            continue
        brn = daily_returns(be, float(rows[0]["equity"]) if rows else None)
        bm[bid] = compare_benchmark(r, brn, ppy, out["total_return"], _f(be.iloc[-1] / float(rows[0]["equity"]) - 1.0))
    out["benchmarks"] = bm
    out["leverage"] = leverage_series(eq_rows)
    if fills is not None:
        out["attribution"] = attribution(fills, positions or [], base, float(eq.iloc[-1]), swap_cost, base_ccy)
    return out
