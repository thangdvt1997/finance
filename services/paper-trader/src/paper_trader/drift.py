"""Giám sát suy giảm (live-paper vs kỳ vọng backtest CÙNG tham số): CUSUM một phía + kiểm định trung bình + kiểm định tỷ lệ ngày lãi,
và tách 'suy giảm TÍN HIỆU' (lợi suất gộp trước chi phí kém kỳ vọng) khỏi 'suy giảm THỰC THI' (chi phí thực > giả định).

Thiết kế CUSUM (chuẩn hoá theo độ biến động live để so cùng rủi ro): x_t = (r_t - mu0)/sigma, mu0 = SR_kỳ_vọng * sigma/sqrt(ppy).
Phát hiện dịch chuyển từ SR kỳ vọng xuống SR_xấu (mặc định -0,5): k = (SR0 - SR1)/(2*sqrt(ppy)); ngưỡng h chọn để ARL0 (số ngày trung bình
giữa 2 báo động giả khi KHÔNG suy giảm) = arl0 (mặc định 1260 ngày = 5 năm) theo xấp xỉ Siegmund. Hạn chế thật: với Sharpe ~0,5 trên dữ liệu ngày,
độ trễ phát hiện tính bằng NĂM — CUSUM chỉ bắt được suy giảm nặng; mẫu ngắn thì chỉ có tác dụng cảnh báo sớm kiểu 'đừng tin vội'."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

MIN_DAYS = 20
WARN_ARL0 = 300.0          # ngưỡng vàng: ARL0 ngắn hơn (đỏ dùng arl0 ~ 1260 ngày)


def siegmund_arl0(k: float, h: float) -> float:
    """ARL0 xấp xỉ của CUSUM một phía với tham chiếu k, ngưỡng h, dữ liệu chuẩn hoá N(trung bình -k, 1) khi trong kiểm soát."""
    b = h + 1.166
    z = 2.0 * k * b
    return (math.exp(z) - z - 1.0) / (2.0 * k * k)


def solve_h(k: float, arl0: float) -> float:
    lo, hi = 0.0, 1.0
    while siegmund_arl0(k, hi) < arl0 and hi < 1e4:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        (lo, hi) = (mid, hi) if siegmund_arl0(k, mid) < arl0 else (lo, mid)
    return (lo + hi) / 2.0


def cusum_down(r: np.ndarray, mu0: float, sigma: float, k: float, h: float) -> dict:
    """S_t = max(0, S_{t-1} + (mu0 - r_t)/sigma - k). Báo động khi S_t >= h."""
    s, path, first = 0.0, [], None
    for i, x in enumerate(r):
        s = max(0.0, s + (mu0 - float(x)) / sigma - k)
        path.append(s)
        if first is None and s >= h:
            first = i
    return {"S": s, "S_max": max(path) if path else 0.0, "h": h, "k": k, "ratio": s / h if h > 0 else None,
            "breached": first is not None, "first_breach_index": first, "path": path}


def _worse(a: str, b: str) -> str:
    order = {"insufficient": -1, "green": 0, "yellow": 1, "red": 2}
    return a if order[a] >= order[b] else b


def report(r_net: pd.Series, daily_cost: pd.Series | None, exp: dict | None, ppy: int = 252, exec_ratio: float | None = None,
           n_fills: int = 0, alt_sharpe: float = -0.5, arl0: float = 1260.0, min_days: int = MIN_DAYS) -> dict:
    """r_net: lợi suất ngày ròng. daily_cost: chi phí ngày / equity trước đó (tỷ lệ) để suy ra lợi suất gộp. exp: {sharpe, vol_ann?} hoặc None."""
    n = len(r_net)
    out: dict[str, Any] = {"n_days": n, "min_days": min_days, "applicable": bool(exp), "status": "insufficient", "diagnosis": "insufficient",
                           "expectation": exp, "multiple_testing_note": "Nhiều kiểm định chạy song song -> báo động là tín hiệu để RÀ SOÁT, không phải bằng chứng."}
    if not exp:
        out["status"] = "n/a"
        out["diagnosis"] = "n/a"
        out["note"] = "Tài khoản không có kỳ vọng backtest cùng tham số (khác universe/cấu hình) -> không giám sát suy giảm kiểu này."
        return out
    sr0 = float(exp["sharpe"])
    out["alt_sharpe"], out["arl0_days"] = alt_sharpe, arl0
    if n < min_days:
        out["note"] = f"Cần ≥ {min_days} ngày lợi suất ({n} hiện có) để giám sát suy giảm."
        return out
    r = r_net.to_numpy(float)
    sigma = float(r.std(ddof=1))
    if sigma < 1e-9:
        out["note"] = "Chưa có biến động (chưa vào vị thế?) -> chưa đánh giá được."
        return out
    mu0 = sr0 * sigma / math.sqrt(ppy)
    k = (sr0 - alt_sharpe) / (2.0 * math.sqrt(ppy))
    h = solve_h(k, arl0)
    h_warn = solve_h(k, WARN_ARL0)
    cu = cusum_down(r, mu0, sigma, k, h)
    cu["h_warn"] = h_warn
    from scipy import stats
    mean_r = float(r.mean())
    t = (mean_r - mu0) / (sigma / math.sqrt(n))
    p_mean = float(stats.t.cdf(t, n - 1))                           # phía dưới: live kém kỳ vọng
    nz = r[np.abs(r) > 1e-12]
    m, wins = len(nz), int((nz > 0).sum())
    p0 = float(stats.norm.cdf(sr0 / math.sqrt(ppy)))                 # tỷ lệ ngày lãi kỳ vọng theo mô hình chuẩn
    p_hit = float(stats.binomtest(wins, m, p0, alternative="less").pvalue) if m >= min_days else None
    out["signal"] = {
        "live_vol_ann": sigma * math.sqrt(ppy), "live_sharpe": mean_r / sigma * math.sqrt(ppy), "expected_sharpe": sr0,
        "mean_daily": mean_r, "expected_mean_daily": mu0, "t_stat": t, "p_below_expected": p_mean,
        "cusum": {k_: v for k_, v in cu.items() if k_ not in ("path", "first_breach_index")},
        "cusum_path": [round(x, 4) for x in cu["path"]][-400:],
        "cusum_breach_date": (r_net.index[cu["first_breach_index"]].isoformat() if cu["first_breach_index"] is not None else None),
        "hit_rate": {"active_days": m, "wins": wins, "observed": wins / m if m else None, "expected": p0, "p_below_expected": p_hit},
    }
    if exp.get("vol_ann"):
        out["signal"]["vol_ratio_vs_backtest"] = sigma * math.sqrt(ppy) / float(exp["vol_ann"])
    # Quan sát liên tục hàng ngày làm tăng báo động giả của mọi kiểm định -> ngưỡng ĐỎ rất chặt (p<0,001 hoặc CUSUM ARL0 ~5 năm);
    # VÀNG chỉ để xem (CUSUM ARL0 ~300 ngày, p<0,02), không phát cảnh báo ra ngoài.
    sig = "green"
    if cu["breached"] or (p_mean < 0.001 and n >= 60):
        sig = "red"
    elif cu["S"] >= h_warn or (p_mean < 0.02 and n >= 40) or (p_hit is not None and p_hit < 0.02):
        sig = "yellow"
    if daily_cost is not None and len(daily_cost):
        cost = daily_cost.reindex(r_net.index).fillna(0.0).to_numpy(float)
        gross = r + cost
        gm = float(gross.mean())
        out["decomposition"] = {
            "mean_net_ann": mean_r * ppy, "mean_gross_ann": gm * ppy, "cost_drag_ann": float(cost.mean()) * ppy, "expected_mean_ann": mu0 * ppy,
            "shortfall_net_ann": (mu0 - mean_r) * ppy, "shortfall_gross_ann": (mu0 - gm) * ppy,
            "share_of_shortfall_due_to_cost": (float(cost.mean()) / (mu0 - mean_r)) if (mu0 - mean_r) > 1e-12 else None,
            "gross_sharpe": gm / float(gross.std(ddof=1)) * math.sqrt(ppy) if float(gross.std(ddof=1)) > 1e-12 else None}
    ex = "green"
    if exec_ratio is not None and n_fills >= 10:
        ex = "red" if exec_ratio > 2.0 else "yellow" if exec_ratio > 1.5 else "green"
    elif exec_ratio is None or n_fills < 10:
        ex = "insufficient"
    out["execution"] = {"status": ex, "cost_ratio_vs_assumed": exec_ratio, "fills": n_fills,
                        "rule": "vàng > 1,5x, đỏ > 2x chi phí toàn phần giả định (backtest nhạy chi phí: x2 -> Sharpe 0,44, x3 -> 0,33)"}
    out["signal_status"] = sig
    out["status"] = _worse(sig, ex if ex != "insufficient" else "green")
    s_bad, e_bad = sig in ("yellow", "red"), ex in ("yellow", "red")
    out["diagnosis"] = "both" if s_bad and e_bad else "signal" if s_bad else "execution" if e_bad else "none"
    out["diagnosis_text"] = {"both": "Suy giảm cả TÍN HIỆU lẫn THỰC THI", "signal": "Suy giảm TÍN HIỆU (lợi suất gộp kém kỳ vọng); chi phí trong dải",
                             "execution": "Suy giảm THỰC THI (chi phí thực > giả định); tín hiệu chưa lệch bất thường",
                             "none": "Chưa thấy lệch bất thường so với kỳ vọng backtest (mẫu còn ngắn — không có nghĩa là đã đạt)"}[out["diagnosis"]]
    return out
