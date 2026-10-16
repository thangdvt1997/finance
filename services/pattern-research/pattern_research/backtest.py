"""Backtest TRUNG THUC cho Kich ban Sell (KB-1..KB-4) cua pattern-engine — CHI nghien cuu/paper, khong dat lenh.

Nguyen tac (xem docs/research/PATTERN_SELL_BACKTEST.md):
- Tin hieu = su kien `triggered` cua pattern_engine.Detector chay tuan tu tren nen DA DONG (khong look-ahead, da co test).
- Vao lenh SELL tai GIA MO cua nen KE TIEP nen kich hoat (tin hieu chi biet khi nen dong) - truot gia.
- Gia nen la BID. Lenh Sell: vao o bid, dong (mua lai) o ASK = bid + spread. SL/TP kich hoat theo ASK.
- SL = muc SL goi y cua engine (dinh cau truc + 0.25 ATR); TP = entry - m * R (m chon bang walk-forward); dung theo thoi gian
  sau `max_hold` nen (dong o gia dong cua + spread). Cung nen cham ca SL va TP -> tinh SL (bi quan).
- Chi phi: spread (tu du lieu MT5 neu co, toi thieu = san theo symbol) + truot gia moi lan khop lenh stop/market + commission.
- Ket qua tinh bang R (boi so rui ro ban dau, da tru chi phi).
- Baseline ngau nhien: cung so lenh, cung giai doan, cung phan bo khoang SL (theo ATR), cung TP/hold/chi phi, nhieu seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ------------------------------------------------------------------------------------------------ chi phi
# Gia dinh tai khoan retail "standard" (khong phai ECN re nhat): chi phi THUC TE-BI QUAN hon spread demo.
# spread_floor/slip/comm: don vi GIA (price units) tru khi ghi *_bps (phan van gia). point: kich thuoc 1 point MT5.
COSTS: dict[str, dict] = {
    "XAUUSD":   {"point": 0.01,   "spread_floor": 0.20,    "slip": 0.05,    "comm": 0.0},
    "XAUUSD_GC": {"point": 0.1,   "spread_floor": 0.30,    "slip": 0.10,    "comm": 0.0},
    "EURUSD":   {"point": 1e-5,   "spread_floor": 0.00010, "slip": 0.00002, "comm": 0.0},
    "GBPUSD":   {"point": 1e-5,   "spread_floor": 0.00014, "slip": 0.00002, "comm": 0.0},
    "USDJPY":   {"point": 1e-3,   "spread_floor": 0.012,   "slip": 0.002,   "comm": 0.0},
    "US500":    {"point": 0.01,   "spread_floor": 0.60,    "slip": 0.25,    "comm": 0.0},
    "US30":     {"point": 0.01,   "spread_floor": 2.0,     "slip": 1.0,     "comm": 0.0},
    "USTEC":    {"point": 0.01,   "spread_floor": 1.5,     "slip": 0.75,    "comm": 0.0},
    "US500_SPY": {"point": 0.01,  "spread_floor": 0.02,    "slip": 0.01,    "comm": 0.0},
    # crypto spot: phi taker 0.10%/chieu (=> comm_bps 20 khu hoi), spread 1 bp, truot 1 bp
    "BTCUSD":   {"point": 0.01,   "spread_bps": 1.0,       "slip_bps": 1.0, "comm_bps": 20.0},
    "ETHUSD":   {"point": 0.01,   "spread_bps": 1.0,       "slip_bps": 1.0, "comm_bps": 20.0},
}
DEFAULT_COST = {"point": 0.0, "spread_bps": 2.0, "slip_bps": 1.0, "comm_bps": 2.0}


def cost_spec(symbol: str) -> dict:
    return COSTS.get(symbol, DEFAULT_COST)


def spread_array(symbol: str, close: np.ndarray, spread_pts: np.ndarray | None, zero_cost: bool = False) -> np.ndarray:
    """Spread (gia) theo tung nen = max(spread MT5 cua nen * point, san theo symbol)."""
    if zero_cost:
        return np.zeros_like(close, dtype=float)
    cs = cost_spec(symbol)
    if "spread_bps" in cs:
        base = close * cs["spread_bps"] * 1e-4
    else:
        base = np.full_like(close, cs["spread_floor"], dtype=float)
    if spread_pts is not None and cs.get("point"):
        base = np.maximum(base, np.asarray(spread_pts, dtype=float) * cs["point"])
    return base


def slip_comm(symbol: str, price: float, zero_cost: bool = False) -> tuple[float, float]:
    """(truot gia moi lan khop market/stop, commission khu hoi) theo gia."""
    if zero_cost:
        return 0.0, 0.0
    cs = cost_spec(symbol)
    slip = cs["slip"] if "slip" in cs else price * cs["slip_bps"] * 1e-4
    comm = cs["comm"] if "comm" in cs else price * cs["comm_bps"] * 1e-4
    return slip, comm


# ------------------------------------------------------------------------------------------------ chuoi
def wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, p: int = 14) -> np.ndarray:
    """ATR Wilder giong pattern_engine.series.Series (gia tri tai i chi dung nen <= i)."""
    n = len(c)
    out = np.empty(n)
    for i in range(n):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i == 0:
            a = tr
        elif i < p:
            a = (out[i - 1] * i + tr) / (i + 1)
        else:
            a = (out[i - 1] * (p - 1) + tr) / p
        out[i] = a
    return out


@dataclass
class Bars:
    symbol: str
    tf: str
    ts: np.ndarray        # datetime64[ns] UTC (naive)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    spread: np.ndarray    # gia
    atr: np.ndarray
    zero_cost: bool = False

    @classmethod
    def from_arrays(cls, symbol, tf, ts, o, h, l, c, spread_pts=None, zero_cost=False):
        o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
        return cls(symbol, tf, np.asarray(ts), o, h, l, c, spread_array(symbol, c, spread_pts, zero_cost), wilder_atr(h, l, c),
                   zero_cost)


# ------------------------------------------------------------------------------------------------ mo phong 1 lenh
@dataclass
class Trade:
    entry_i: int
    exit_i: int
    entry: float
    exit: float
    sl: float
    tp: float
    risk: float
    r: float          # ket qua R da tru chi phi
    r_gross: float    # ket qua R truoc chi phi (theo bid, khong spread/truot/phi)
    outcome: str      # tp | sl | time | end


def simulate_sell(b: Bars, entry_i: int, sl: float, tp_r: float, max_hold: int, end_i: int | None = None,
                  zero_cost: bool = False) -> Trade | None:
    """Sell market tai gia mo nen entry_i. None neu khong vao duoc (het du lieu / gia mo da tren SL)."""
    n = len(b.c) if end_i is None else min(len(b.c), end_i)
    if entry_i >= n:
        return None
    slip, comm = slip_comm(b.symbol, b.o[entry_i], zero_cost or b.zero_cost)
    entry = b.o[entry_i] - slip                       # khop xau hon bid mo cua
    gross_entry = b.o[entry_i]
    risk = sl - entry
    if risk <= 0:
        return None                                    # gap vuot SL -> lenh khong hop le, bo qua
    tp = entry - tp_r * risk
    last = min(n - 1, entry_i + max_hold - 1)
    j = entry_i
    sp = b.spread
    while j <= last:
        ask_hi = b.h[j] + sp[j]
        ask_lo = b.l[j] + sp[j]
        if ask_hi >= sl:                               # SL truoc (bi quan neu cung nen voi TP)
            fill = max(sl, b.o[j] + sp[j]) if j > entry_i else sl   # gap qua SL o nen sau -> khop o gia mo
            ex = fill + slip
            gross_ex = max(sl, b.o[j]) if j > entry_i else sl
            return Trade(entry_i, j, entry, ex, sl, tp, risk, (entry - ex - comm) / risk, (gross_entry - gross_ex) / risk, "sl")
        if ask_lo <= tp:
            ex = tp                                    # lenh gioi han: khong truot
            return Trade(entry_i, j, entry, ex, sl, tp, risk, (entry - ex - comm) / risk, (gross_entry - tp) / risk, "tp")
        j += 1
    j = last
    ex = b.c[j] + sp[j] + slip
    outcome = "time" if last == entry_i + max_hold - 1 else "end"
    return Trade(entry_i, j, entry, ex, sl, tp, risk, (entry - ex - comm) / risk, (gross_entry - b.c[j]) / risk, outcome)


# ------------------------------------------------------------------------------------------------ thong ke
def max_drawdown(rs: np.ndarray) -> float:
    if len(rs) == 0:
        return 0.0
    eq = np.cumsum(rs)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return float(np.max(peak - eq))


def longest_losing_streak(rs: np.ndarray) -> int:
    best = cur = 0
    for x in rs:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def bootstrap_ci(rs: np.ndarray, n_boot: int = 2000, seed: int = 7, alpha: float = 0.05) -> tuple[float, float]:
    if len(rs) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(rs), size=(n_boot, len(rs)))
    m = rs[idx].mean(axis=1)
    return float(np.quantile(m, alpha / 2)), float(np.quantile(m, 1 - alpha / 2))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def deflated_sharpe(rs: np.ndarray, n_trials: int) -> dict:
    """Probabilistic / Deflated Sharpe (Bailey & Lopez de Prado 2014) tren chuoi R moi lenh.
    SR* = ky vong max Sharpe cua n_trials chien luoc vo dung (gia dinh phuong sai Sharpe giua cac thu = 1/T)."""
    T = len(rs)
    if T < 10 or np.std(rs) == 0:
        return {"sr": float("nan"), "psr0": float("nan"), "dsr": float("nan")}
    sr = float(np.mean(rs) / np.std(rs, ddof=1))
    z = (rs - rs.mean()) / rs.std()
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    g = 0.5772156649
    N = max(1, n_trials)
    v = 1.0 / T
    sr_star = 0.0 if N == 1 else math.sqrt(v) * ((1 - g) * _inv_norm(1 - 1 / N) + g * _inv_norm(1 - 1 / (N * math.e)))
    psr0 = _norm_cdf(sr * math.sqrt(T - 1) / denom)
    dsr = _norm_cdf((sr - sr_star) * math.sqrt(T - 1) / denom)
    return {"sr": round(sr, 4), "sr_star": round(sr_star, 4), "psr0": round(psr0, 4), "dsr": round(dsr, 4)}


def _inv_norm(p: float) -> float:
    # Acklam xap xi
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - pl:
        return -_inv_norm(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def summarize(rs, gross=None) -> dict:
    rs = np.asarray(rs, dtype=float)
    n = len(rs)
    if n == 0:
        return {"n": 0}
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
    lo, hi = bootstrap_ci(rs)
    out = {"n": n, "win": round(float((rs > 0).mean()), 4), "exp_r": round(float(rs.mean()), 4),
           "ci95": [round(lo, 4), round(hi, 4)], "pf": round(pf, 3) if math.isfinite(pf) else None,
           "sum_r": round(float(rs.sum()), 2), "maxdd_r": round(max_drawdown(rs), 2), "max_lose_streak": longest_losing_streak(rs)}
    if gross is not None and len(gross):
        out["exp_r_gross"] = round(float(np.mean(gross)), 4)
    return out


# ------------------------------------------------------------------------------------------------ baseline ngau nhien
def random_baseline(b: Bars, sl_atr: np.ndarray, lo_i: int, hi_i: int, tp_r: float, max_hold: int, n_seeds: int = 500,
                    seed: int = 12345, end_i: int | None = None, zero_cost: bool = False) -> np.ndarray:
    """Tra mang [n_seeds, k] R cua k lenh Sell ngau nhien/seed: entry_i ~ U[lo_i, hi_i) (gia mo nen), SL = entry + d*ATR(entry_i-1)
    voi d lay hoan vi tu phan bo SL/ATR cua tin hieu that (cung tan suat, cung SL/TP/hold/chi phi). NaN neu khong vao duoc."""
    k = len(sl_atr)
    out = np.full((n_seeds, k), np.nan)
    if k == 0 or hi_i - lo_i < 2:
        return out
    rng = np.random.default_rng(seed)
    for s in range(n_seeds):
        es = rng.integers(max(lo_i, 15), hi_i, size=k)
        ds = rng.permutation(sl_atr)
        for t in range(k):
            e = int(es[t])
            sl = b.o[e] + ds[t] * b.atr[e - 1]
            tr = simulate_sell(b, e, sl, tp_r, max_hold, end_i, zero_cost)
            if tr is not None:
                out[s, t] = tr.r
    return out


def p_value_vs_random(real_mean: float, rand: np.ndarray) -> tuple[float, float]:
    """p = P(mean ngau nhien >= mean that) (mot phia, +1 hieu chinh); tra (p, trung binh baseline)."""
    means = np.nanmean(rand, axis=1)
    means = means[np.isfinite(means)]
    if len(means) == 0:
        return float("nan"), float("nan")
    p = (1 + int((means >= real_mean).sum())) / (1 + len(means))
    return round(p, 4), round(float(means.mean()), 4)


# ------------------------------------------------------------------------------------------------ PBO (CSCV)
def pbo_cscv(m: np.ndarray, n_splits: int = 16) -> dict:
    """Probability of Backtest Overfitting (Bailey, Borwein, Lopez de Prado, Zhu 2015) bang CSCV.
    m: ma tran [T, N] hieu qua (vd R trung binh) cua N cau hinh tren T khoi thoi gian lien tiep. Chia T thanh n_splits nhom,
    moi to hop nua nhom = IS, phan con lai = OOS; PBO = ti le to hop ma cau hinh tot nhat IS co hang OOS <= trung vi."""
    from itertools import combinations
    m = np.asarray(m, dtype=float)
    T, N = m.shape
    if N < 2 or T < n_splits:
        return {"pbo": float("nan"), "n_combos": 0}
    groups = np.array_split(np.arange(T), n_splits)
    logits = []
    for is_g in combinations(range(n_splits), n_splits // 2):
        is_idx = np.concatenate([groups[g] for g in is_g])
        oos_idx = np.concatenate([groups[g] for g in range(n_splits) if g not in is_g])
        best = int(np.nanargmax(np.nanmean(m[is_idx], axis=0)))
        oos = np.nanmean(m[oos_idx], axis=0)
        rank = (np.sum(oos < oos[best]) + 0.5 * (np.sum(oos == oos[best]) - 1) + 1) / (N + 1)   # (0,1)
        logits.append(math.log(rank / (1 - rank)))
    lg = np.array(logits)
    return {"pbo": round(float((lg <= 0).mean()), 4), "n_combos": len(lg), "median_logit": round(float(np.median(lg)), 4)}
