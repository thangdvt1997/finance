"""VaR/ES + tương quan + đóng góp rủi ro cho danh mục HIỆN TẠI, dựng từ lợi suất ngày (bars D1) của từng mã.
P&L ngày giả định = Σ_i V_i · r_i,t  với V_i = exposure ròng có dấu (tiền tệ tài khoản), r = lợi suất đơn giản."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import riskmath as rm


def align_returns(closes: pd.DataFrame, symbols: list[str], lookback: int, ffill_limit: int = 3) -> pd.DataFrame:
    """Lợi suất đơn giản ngày, căn theo ngày chung (ffill tối đa `ffill_limit` ngày nghỉ lễ), bỏ dòng còn NaN."""
    cols = [s for s in symbols if s in closes.columns]
    if not cols:
        return pd.DataFrame()
    c = closes[cols].sort_index().ffill(limit=ffill_limit)
    r = c.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="any")
    return r.tail(lookback)


def _pct(x: float | None, eq: float | None) -> float | None:
    return None if x is None or not eq else x / eq * 100.0


def portfolio_risk(net_values: dict[str, float], closes: pd.DataFrame, equity: float | None, cfg: dict) -> dict:
    """net_values: {symbol: exposure ròng có dấu}. Trả dict VaR/ES, tương quan, đóng góp rủi ro (hoặc {available: False, reason})."""
    vcfg = cfg.get("var", {})
    alphas = vcfg.get("alphas", [0.95, 0.99])
    es_alpha = vcfg.get("es_alpha", 0.975)
    horizons = vcfg.get("horizons", [1, 10])
    lam = float(cfg.get("ewma_lambda", 0.94))
    min_hist = int(cfg.get("min_history_days", 60))
    lookback = int(cfg.get("returns_lookback_days", 750))

    held = {s: v for s, v in net_values.items() if abs(v) > 0}
    if not held:
        return {"available": False, "reason": "Không có vị thế mở"}
    rets = align_returns(closes, list(held), lookback)
    have = list(rets.columns)
    missing = [s for s in held if s not in have]
    if len(rets) < min_hist or not have:
        return {"available": False, "reason": f"Thiếu lịch sử D1 (có {len(rets)} ngày chung, cần ≥{min_hist})", "missing": missing}
    v = np.array([held[s] for s in have], dtype=float)
    pnl = rets.to_numpy() @ v
    n = len(pnl)
    covered = float(sum(abs(held[s]) for s in have) / sum(abs(x) for x in held.values()))

    hist, param = {}, {}
    for a in alphas:
        var, es = rm.hist_var_es(pnl, a)
        hist[f"{round(a * 100)}"] = {"var": var, "es": es, "var_pct": _pct(var, equity), "es_pct": _pct(es, equity)}
    var_e, es_e = rm.hist_var_es(pnl, es_alpha)
    es_key = f"{es_alpha * 100:g}"
    hist["es"] = {"alpha": es_alpha, "key": es_key, "var": var_e, "es": es_e, "var_pct": _pct(var_e, equity), "es_pct": _pct(es_e, equity)}

    sigma_u = float(np.std(pnl, ddof=1))
    sigma_e = rm.ewma_sigma(pnl, lam)
    for name, sg in (("normal", sigma_u), ("ewma", sigma_e)):
        d = {"sigma": sg, "sigma_pct": _pct(sg, equity)}
        for a in alphas:
            var, es = rm.param_var_es(sg, a)
            d[f"{round(a * 100)}"] = {"var": var, "es": es, "var_pct": _pct(var, equity), "es_pct": _pct(es, equity)}
        var, es = rm.param_var_es(sg, es_alpha)
        d["es"] = {"alpha": es_alpha, "var": var, "es": es, "var_pct": _pct(var, equity), "es_pct": _pct(es, equity)}
        param[name] = d

    scaled = {}
    for h in horizons:
        scaled[str(h)] = {"hist95_var": rm.horizon_scale(hist["95"]["var"], h) if "95" in hist else None,
                          "hist_es": rm.horizon_scale(hist["es"]["es"], h),
                          "hist_es_pct": _pct(rm.horizon_scale(hist["es"]["es"], h), equity)}

    # backtest: VaR95 tham số EWMA dự báo hôm trước vs P&L hôm sau của chính danh mục hiện tại (giả định giữ nguyên vị thế)
    backtest = None
    init_n = 30
    if n > init_n + 20:
        path = rm.ewma_sigma_path(pnl, lam, init_n)           # path[i] = σ dự báo cho ngày index init_n-1+i+1
        z = rm.param_var_es(1.0, 0.95)[0]
        actual = pnl[init_n:]
        sig = path[:len(actual)]
        tail = slice(-250, None)
        act, sg = actual[tail], sig[tail]
        x = int(np.sum(act < -z * sg))
        lr, p = rm.kupiec_pof(len(act), x, 0.05)
        backtest = {"model": "ewma95", "days": int(len(act)), "exceptions": x, "expected": round(0.05 * len(act), 1),
                    "kupiec_lr": lr, "kupiec_p": p, "verdict": "đạt" if p >= 0.05 else "VaR đánh giá thấp/cao: nên xem lại"}

    order = np.argsort(pnl)[:5]
    worst = [{"date": str(rets.index[i].date()), "pnl": float(pnl[i]), "pnl_pct": _pct(float(pnl[i]), equity)} for i in order]
    skew = float(pd.Series(pnl).skew())
    kurt = float(pd.Series(pnl).kurt())

    # tương quan + đóng góp rủi ro
    w = min(int(cfg.get("corr_window_days", 120)), n)
    rr = rets.tail(w)
    corr = rr.corr().fillna(0.0) if len(have) > 1 else pd.DataFrame([[1.0]], index=have, columns=have)
    cov = rets.tail(min(250, n)).cov().to_numpy() if len(have) > 1 else np.array([[float(rets.iloc[:, 0].var())]])
    rc = rm.risk_contributions(v, cov)
    pairs = []
    for i in range(len(have)):
        for j in range(i + 1, len(have)):
            rho = float(corr.iloc[i, j])
            same_dir = (v[i] > 0) == (v[j] > 0)
            pairs.append({"a": have[i], "b": have[j], "rho": rho,
                          "effective_same_bet": bool((same_dir and rho >= 0.7) or (not same_dir and rho <= -0.7))})
    pairs.sort(key=lambda p: -abs(p["rho"]))
    off = [abs(float(corr.iloc[i, j])) for i in range(len(have)) for j in range(i + 1, len(have))]
    contrib = sorted(({"symbol": s, "value": float(vi), "risk_share": float(r), "vol_pct": float(math.sqrt(max(cov[i, i], 0)) * 100)}
                      for i, (s, vi, r) in enumerate(zip(have, v, rc["rc"]))), key=lambda d: -abs(d["risk_share"]))
    return {
        "available": True, "days": n, "from": str(rets.index[0].date()), "to": str(rets.index[-1].date()),
        "symbols": have, "missing": missing, "coverage_pct": covered * 100.0,
        "hist": hist, "normal": param["normal"], "ewma": param["ewma"], "horizons": scaled, "backtest": backtest,
        "worst_days": worst, "skew": skew, "excess_kurtosis": kurt,
        "sigma_daily": float(sigma_u), "sigma_daily_pct": _pct(sigma_u, equity),
        "correlation": {
            "window_days": int(w), "symbols": have, "matrix": [[round(float(x), 4) for x in row] for row in corr.to_numpy()],
            "top_pairs": pairs[:8], "avg_abs_corr": (float(np.mean(off)) if off else None),
        },
        "risk_contrib": {"sigma_p": rc["sigma_p"], "diversification_ratio": rc["diversification_ratio"],
                         "effective_bets": rc["effective_bets"], "items": contrib[:15]},
        "notes": ["VaR/ES dựng từ lợi suất D1 lịch sử áp lên vị thế HIỆN TẠI (giả định giữ nguyên vị thế).",
                  "Gap cuối tuần/sự kiện cực đoan (CHF 2015) thường vượt VaR: xem thêm stress test."],
    }
