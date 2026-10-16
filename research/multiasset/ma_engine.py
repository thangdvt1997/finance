"""Engine backtest da tai san (vector hoa, minh bach). Tai su dung engine.py (metrics, bootstrap, deflated Sharpe) va strategies.py (Donchian state loop).
Quy uoc: loi suat tai san la 'excess' (vuot tien mat USD, nhu hop dong tuong lai). Tin hieu tinh tu chi so tich luy I = cumprod(1+r_excess).
Thoi gian: tin hieu o close t -> vao lenh o close t+1 -> huong loi suat cua phien t+2 (lag=2, bao thu cho lech mui gio/dong cua cac san)."""
import numpy as np, pandas as pd
from ma_common import *
import strategies as ST
from engine import metrics, block_bootstrap_sharpe, deflated_sharpe, psr0

ANN = 252


class Ctx:
    def __init__(self, R, rf_ann, cols):
        self.cols = list(cols); self.R = R[self.cols]; idx = self.R.index
        self.idx = idx
        self.acc = pd.Series(pd.Series(idx, index=idx).diff().dt.days.fillna(1).values / 365.0, index=idx)
        self.rfd = (rf_ann.reindex(idx) * self.acc)
        self.cls = np.array([ASSETS[c][0] for c in self.cols])
        self.cost = np.array([ASSETS[c][1] for c in self.cols]) / 1e4
        started = self.R.notna().cummax()
        self.I = (1 + self.R.fillna(0)).cumprod().where(started)
        self.sig = self.R.ewm(span=60, min_periods=60).std() * np.sqrt(ANN)
        self._c = {}
        self.Rz = self.R.fillna(0.0)

    def cov(self, d):
        if d in self._c: return self._c[d]
        i = self.idx.get_loc(d); lo = max(0, i - 500); X = self.R.iloc[lo:i + 1].values
        m = ~np.isnan(X); Xz = np.where(m, X, 0.0); n = len(X)
        w = 0.5 ** (np.arange(n)[::-1] / 60.0); sw = np.sqrt(w)[:, None]
        A = Xz * sw; M = m * sw
        num = A.T @ A; den = M.T @ M
        cv = np.divide(num, den, out=np.zeros_like(num), where=den > 1e-9) * ANN
        cv = 0.8 * cv + 0.2 * np.diag(np.diag(cv))
        self._c[d] = cv
        return cv


# ---------------- tin hieu (DataFrame trong [-1,1], NaN = chua du lich su) ----------------
def sig_tsmom(I, lb=252, skip=21):
    return np.sign(I.shift(skip) / I.shift(lb) - 1).where(I.shift(lb).notna())


def sig_multi(I, lbs=(21, 63, 252)):
    ss = [np.sign(I / I.shift(l) - 1).where(I.shift(l).notna()) for l in lbs]
    return sum(ss) / len(ss)


def sig_ma(I, slow=200):
    m = I.rolling(slow).mean(); return np.sign(I - m).where(m.notna())


def sig_macross(I, fast=100, slow=200):
    m = I.rolling(slow).mean(); return np.sign(I.rolling(fast).mean() - m).where(m.notna())


def sig_donch(I, n_in=200, n_out=100):
    return ST.donchian(I, n_in, n_out)


def sig_ens(I):
    parts = [sig_tsmom(I, 252, 21), sig_multi(I), sig_ma(I, 200), sig_donch(I, 200, 100)]
    return sum(parts) / len(parts)


def rebal_dates(idx, freq, start):
    s = pd.Series(idx, index=idx)
    if freq == "W": m = (s.dt.isocalendar().week.values != s.shift(-1).dt.isocalendar().week.values)
    else: m = (s.dt.to_period("M") != s.shift(-1).dt.to_period("M")).values
    d = idx[m]
    return d[d >= pd.Timestamp(start)]


def weights(ctx, S, reb, scheme="rp", target=0.10, lmax=3.0, gross_cap=8.0, asset_cap=3.0):
    N = len(ctx.cols); out = np.zeros((len(reb), N))
    Sr = S.reindex(reb).values; sg = ctx.sig.reindex(reb).values
    clsu = [np.where(ctx.cls == c)[0] for c in CLASSES + ["crypto"]]
    for k, d in enumerate(reb):
        s = Sr[k]; g = sg[k]
        live = ~np.isnan(s) & ~np.isnan(g)
        if live.sum() < 3: continue
        b = np.zeros(N)
        if scheme == "rp":
            pres = [ix[live[ix]] for ix in clsu if live[ix].any()]
            K = len(pres)
            for ix in pres: b[ix] = 1.0 / K / len(ix)
        else:
            b[live] = 1.0 / live.sum()
        raw = np.where(live, np.nan_to_num(s), 0.0) * b * target / np.maximum(np.nan_to_num(g, nan=1.0), 0.01)
        if not np.any(raw): continue
        cv = ctx.cov(d)
        pv = np.sqrt(max(raw @ cv @ raw, 1e-12))
        L = min(lmax, target / pv)
        w = np.clip(raw * L, -asset_cap, asset_cap)
        gr = np.abs(w).sum()
        if gr > gross_cap: w *= gross_cap / gr
        out[k] = w
    return pd.DataFrame(out, index=reb, columns=ctx.cols)


def run(ctx, S, freq="M", scheme="rp", target=0.10, lmax=3.0, gross_cap=8.0, asset_cap=3.0, cost_mult=1.0, fric=0.003,
        lag=2, start="1990-01-01", long_only=False):
    if long_only: S = S.clip(lower=0)
    reb = rebal_dates(ctx.idx, freq, start)
    Wr = weights(ctx, S, reb, scheme, target, lmax, gross_cap, asset_cap)
    W = Wr.reindex(ctx.idx).ffill().fillna(0.0)
    We = W.shift(lag).fillna(0.0)
    gross = We.abs().sum(axis=1)
    pnl = (We * ctx.Rz).sum(axis=1)
    mult = pd.Series(np.where(ctx.idx < pd.Timestamp("2010-01-01"), 1.5, 1.0), index=ctx.idx)
    dW = We.diff().abs().fillna(0.0)
    tc = (dW * ctx.cost).sum(axis=1) * mult * cost_mult
    fr = gross * fric * ctx.acc
    net = pnl - tc - fr
    live = gross > 0
    first = max(live.idxmax(), pd.Timestamp(start)) if live.any() else pd.Timestamp(start)
    sl = slice(first, None)
    contrib = (We * ctx.Rz).loc[sl]
    return dict(net=net.loc[sl], gross=gross.loc[sl], turnover=dW.sum(axis=1).loc[sl], cost=(tc + fr).loc[sl], W=We.loc[sl], contrib=contrib,
                gross_pnl=pnl.loc[sl])


def total_series(net, ctx):
    return net + ctx.rfd.reindex(net.index)


def summarize(net, ctx, label=""):
    n = net.dropna()
    if len(n) < 250 or n.std() == 0: return {}
    m = metrics(n); tot = total_series(n, ctx); eq = (1 + tot).cumprod(); yrs = (n.index[-1] - n.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    return dict(label=label, Sharpe=m["Sharpe"], Vol=m["Vol"], ExcessCAGR=m["CAGR"], TotalCAGR=cagr, MaxDD=dd, Calmar=cagr / abs(dd) if dd < 0 else np.nan,
                Skew=m["Skew"], Kurt=m["Kurt"], Sortino=m["Sortino"], PctLossYears=m["PctLossYears"], MaxUnderwaterY=m["MaxUnderwaterYears"], Years=yrs,
                start=str(n.index[0].date()), end=str(n.index[-1].date()))


def sharpe_d(r):
    r = r.dropna(); return r.mean() / r.std() * np.sqrt(ANN)
