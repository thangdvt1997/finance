"""BẢN SAO NGUYÊN VĂN (chỉ thêm tham số `classes`) phần tín hiệu + trọng số của research/multiasset/ma_engine.py và research/strategies.py.
Dùng làm "vàng" cho test hồi quy tính nhất quán plugin <-> backtest, không phụ thuộc scipy/pq của gói research.
Nếu backtest đổi, cập nhật file này RỒI chạy lại test (test_backtest_consistency.py::test_ref_matches_research_if_available so với mã gốc khi có thể import)."""
import numpy as np
import pandas as pd

ANN = 252
CLASSES = ["eq", "bond", "fx", "metal", "energy", "agri"]


def _state_loop(long_in, long_out, short_in, short_out):
    T, N = long_in.shape
    pos = np.zeros((T, N))
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
    hi_in = P.rolling(n_in).max().shift(1); lo_in = P.rolling(n_in).min().shift(1)
    hi_out = P.rolling(n_out).max().shift(1); lo_out = P.rolling(n_out).min().shift(1)
    pos = _state_loop((P > hi_in).values, (P < lo_out).values, (P < lo_in).values, (P > hi_out).values)
    return pd.DataFrame(pos, index=P.index, columns=P.columns).where(hi_in.notna())


def sig_tsmom(I, lb=252, skip=21):
    return np.sign(I.shift(skip) / I.shift(lb) - 1).where(I.shift(lb).notna())


def sig_multi(I, lbs=(21, 63, 252)):
    ss = [np.sign(I / I.shift(l) - 1).where(I.shift(l).notna()) for l in lbs]
    return sum(ss) / len(ss)


def sig_ma(I, slow=200):
    m = I.rolling(slow).mean(); return np.sign(I - m).where(m.notna())


def sig_donch(I, n_in=200, n_out=100):
    return donchian(I, n_in, n_out)


def sig_ens(I):
    parts = [sig_tsmom(I, 252, 21), sig_multi(I), sig_ma(I, 200), sig_donch(I, 200, 100)]
    return sum(parts) / len(parts)


class Ctx:
    """Như ma_engine.Ctx nhưng nhận danh sách lớp thay vì tra ASSETS."""
    def __init__(self, R, classes):
        self.cols = list(R.columns); self.R = R; self.idx = R.index
        self.cls = np.array(classes)
        started = self.R.notna().cummax()
        self.I = (1 + self.R.fillna(0)).cumprod().where(started)
        self.sig = self.R.ewm(span=60, min_periods=60).std() * np.sqrt(ANN)
        self._c = {}

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
