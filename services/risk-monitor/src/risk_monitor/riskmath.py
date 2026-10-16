"""Toán rủi ro danh mục: VaR/ES (lịch sử, tham số, EWMA), kiểm định Kupiec, đóng góp rủi ro, tương quan.
Quy ước: P&L (tiền) theo ngày; VaR/ES trả về SỐ DƯƠNG = mức lỗ. Mọi hàm thuần numpy, kiểm bằng số tay trong tests/."""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()


def hist_var_es(pnl: np.ndarray, alpha: float) -> tuple[float, float]:
    """VaR lịch sử = -phân vị (1-alpha) (nội suy tuyến tính, numpy mặc định); ES = -trung bình các P&L <= phân vị đó."""
    x = np.asarray(pnl, dtype=float)
    q = float(np.quantile(x, 1.0 - alpha))
    tail = x[x <= q]
    return -q, -float(tail.mean())


def param_var_es(sigma: float, alpha: float, mu: float = 0.0) -> tuple[float, float]:
    """Chuẩn: VaR = z·σ − μ ; ES = σ·φ(z)/(1−α) − μ  (z = Φ⁻¹(α))."""
    z = _N.inv_cdf(alpha)
    return z * sigma - mu, sigma * _N.pdf(z) / (1.0 - alpha) - mu


def ewma_sigma(x: np.ndarray, lam: float = 0.94, init_n: int = 30) -> float:
    """σ dự báo cho NGÀY KẾ TIẾP (RiskMetrics): s2 khởi tạo = trung bình bình phương init_n quan sát đầu (kỳ vọng 0);
    s2 ← λ·s2 + (1−λ)·x²  cho các quan sát còn lại."""
    x = np.asarray(x, dtype=float)
    k = max(1, min(init_n, len(x)))
    s2 = float(np.mean(x[:k] ** 2))
    for v in x[k:]:
        s2 = lam * s2 + (1.0 - lam) * float(v) ** 2
    return math.sqrt(s2)


def ewma_sigma_path(x: np.ndarray, lam: float = 0.94, init_n: int = 30) -> np.ndarray:
    """σ dự báo cho ngày t+1 tại mỗi t >= init_n-1 (độ dài len(x)-init_n+1)."""
    x = np.asarray(x, dtype=float)
    k = max(1, min(init_n, len(x)))
    s2 = float(np.mean(x[:k] ** 2))
    out = [math.sqrt(s2)]
    for v in x[k:]:
        s2 = lam * s2 + (1.0 - lam) * float(v) ** 2
        out.append(math.sqrt(s2))
    return np.array(out)


def kupiec_pof(n: int, x: int, p: float) -> tuple[float, float]:
    """Kupiec POF: n ngày, x lần vượt VaR, p = xác suất vượt kỳ vọng. Trả (LR, p-value) với chi² 1 bậc: p = erfc(sqrt(LR/2))."""
    if n <= 0:
        return 0.0, 1.0
    ph = x / n

    def ll(q: float) -> float:
        a = (n - x) * math.log(1 - q) if n - x > 0 else 0.0
        b = x * math.log(q) if x > 0 else 0.0
        return a + b

    lr = max(0.0, -2.0 * (ll(p) - ll(ph)))
    return lr, math.erfc(math.sqrt(lr / 2.0))


def risk_contributions(values: np.ndarray, cov: np.ndarray) -> dict:
    """values: exposure có dấu (tiền); cov: hiệp phương sai lợi suất NGÀY. Euler: rc_i = V_i (ΣV)_i / σ_p² (tổng = 1).
    diversification_ratio = Σ|V_i|σ_i / σ_p ; effective_bets = 1/Σ rc_i² (rc chuẩn hoá theo tổng |rc|)."""
    v = np.asarray(values, dtype=float)
    sv = cov @ v
    var_p = float(v @ sv)
    if var_p <= 0:
        return {"sigma_p": 0.0, "rc": [0.0] * len(v), "diversification_ratio": None, "effective_bets": None}
    sig_p = math.sqrt(var_p)
    rc = v * sv / var_p
    sig_i = np.sqrt(np.clip(np.diag(cov), 0, None))
    dr = float(np.sum(np.abs(v) * sig_i) / sig_p)
    w = np.abs(rc) / np.abs(rc).sum()
    return {"sigma_p": sig_p, "rc": [float(r) for r in rc], "diversification_ratio": dr,
            "effective_bets": float(1.0 / np.sum(w ** 2))}


def horizon_scale(x: float, days: int) -> float:
    """Quy tắc căn bậc hai theo thời gian (giả định i.i.d.; ĐÁNH GIÁ THẤP khi có tự tương quan/gap)."""
    return x * math.sqrt(days)
