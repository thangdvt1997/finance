"""Tin hieu chien luoc. Tham so CO DINH theo van lieu. Moi ham tra DataFrame tin hieu (NaN = ngoai universe)."""
import numpy as np, pandas as pd
from engine import META


def month_end_mask(idx):
    s = pd.Series(idx, index=idx)
    return (s.dt.to_period("M") != s.shift(-1).dt.to_period("M")).values


def hold_monthly(sig):
    m = month_end_mask(sig.index)
    return sig.where(pd.Series(m, index=sig.index), np.nan).ffill()


def tsmom(P, lb=252):
    """Moskowitz-Ooi-Pedersen (2012): dau loi suat lb ngay, tai can bang cuoi thang, vol-target (trong engine)."""
    return hold_monthly(np.sign(P / P.shift(lb) - 1)).where(P.notna())


def ma_cross(P, fast=50, slow=200):
    m = P.rolling(slow).mean()
    return np.sign(P.rolling(fast).mean() - m).where(m.notna())


def _state_loop(long_in, long_out, short_in, short_out):
    T, N = long_in.shape; pos = np.zeros((T, N))
    for j in range(N):
        p = 0.0
        for t in range(T):
            if p == 0:
                if long_in[t, j]: p = 1.0
                elif short_in[t, j]: p = -1.0
            elif p > 0 and long_out[t, j]:
                p = -1.0 if short_in[t, j] else 0.0
            elif p < 0 and short_out[t, j]:
                p = 1.0 if long_in[t, j] else 0.0
            pos[t, j] = p
    return pos


def donchian(P, n_in=55, n_out=20):
    """Turtle (he 2): vao khi close vuot max/min close n_in ngay truoc; thoat khi close pha min/max n_out ngay. Dung close (khong co high/low)."""
    hi_in = P.rolling(n_in).max().shift(1); lo_in = P.rolling(n_in).min().shift(1)
    hi_out = P.rolling(n_out).max().shift(1); lo_out = P.rolling(n_out).min().shift(1)
    pos = _state_loop((P > hi_in).values, (P < lo_out).values, (P < lo_in).values, (P > hi_out).values)
    return pd.DataFrame(pos, index=P.index, columns=P.columns).where(hi_in.notna())


def rsi(P, n=2):
    d = P.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def rsi2_mr(P, lo=10, hi=90, trend_n=200, exit_n=5):
    """Connors RSI(2): long khi close>SMA200 va RSI2<lo, thoat khi close>SMA5; short doi xung."""
    R = rsi(P, 2); t = P.rolling(trend_n).mean(); x = P.rolling(exit_n).mean()
    pos = _state_loop(((P > t) & (R < lo)).values, (P > x).values, ((P < t) & (R > hi)).values, (P < x).values)
    return pd.DataFrame(pos, index=P.index, columns=P.columns).where(t.notna())


def bollinger_mr(P, n=20, k=2.0):
    m = P.rolling(n).mean(); sd = P.rolling(n).std(); z = (P - m) / sd
    pos = _state_loop((z < -k).values, (z >= 0).values, (z > k).values, (z <= 0).values)
    return pd.DataFrame(pos, index=P.index, columns=P.columns).where(sd.notna())


def carry(P, rates, k=3):
    """FX carry cat ngang: cuoi thang xep hang 8 dong tien (gom USD) theo lai 3M (tre 1 thang), long k cao nhat, short k thap nhat;
    chuyen thanh vi the cap so voi USD."""
    ccys = list(rates.columns); w = pd.DataFrame(0.0, index=P.index, columns=ccys)
    rk = rates.rank(axis=1, method="first", ascending=False)
    w[rk <= k] = 1.0; w[rk > len(ccys) - k] = -1.0
    w[rates.isna().any(axis=1)] = np.nan
    w = hold_monthly(w)
    sig = pd.DataFrame(np.nan, index=P.index, columns=P.columns)
    for c in P.columns:
        m = META[c]
        if m["kind"] != "fx": continue
        sig[c] = w[m["base"]] if m["quote"] == "USD" else -w[m["quote"]]
    return sig


def buy_hold(P):
    """Long dong ngoai te/kim loai so voi USD (EURUSD +1, USDJPY -1...)."""
    sig = pd.DataFrame(1.0, index=P.index, columns=P.columns)
    for c in P.columns:
        if META[c]["kind"] == "fx" and META[c]["base"] == "USD": sig[c] = -1.0
    return sig.where(P.notna())


def flip_rate(sig, mask):
    s = sig.where(sig != 0).ffill()
    f = (np.sign(s).diff().abs() > 0)
    n = f.loc[mask].sum().sum(); d = s.notna().loc[mask].sum().sum()
    return float(n / max(d, 1))


def shifted_signal(sig, seed, min_shift=252):
    """Kiem soat 'pha thoi gian': dich vong tron tin hieu cua tung instrument mot do lech ngau nhien >= 1 nam (trong doan co du lieu).
    Giu nguyen ty le long/short, so lan dao chieu, thoi gian dung ngoai thi truong; chi pha vi tri tin hieu so voi dien bien gia that."""
    rng = np.random.default_rng(seed); out = sig.copy()
    for c in sig.columns:
        v = sig[c]; ok = v.notna().values; idx = np.where(ok)[0]
        if len(idx) < 3 * min_shift: continue
        seg = v.values[idx]; k = int(rng.integers(min_shift, len(seg) - min_shift))
        arr = v.values.copy(); arr[idx] = np.roll(seg, k); out[c] = arr
    return out


def random_signal(P, flip_p, decision_mask, seed):
    """Dau ngau nhien, doi dau voi xac suat flip_p tai moi ngay quyet dinh (khop toc do doi chieu cua chien luoc that)."""
    rng = np.random.default_rng(seed); T, N = P.shape
    flips = (rng.random((T, N)) < flip_p) & decision_mask[:, None]
    sgn = np.where(flips, -1.0, 1.0); sgn[0, :] = rng.choice([-1.0, 1.0], size=N)
    return pd.DataFrame(np.cumprod(sgn, axis=0), index=P.index, columns=P.columns).where(P.notna())
