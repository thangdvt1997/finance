"""Engine vector hoa don gian, minh bach (khong dung vectorbt: license Commons Clause + can kiem soat chi phi/carry).
Quy uoc thoi gian: tin hieu tinh bang du lieu toi close t -> vi the nam tu close t sang close t+1 (shift(1)); khong look-ahead.
Loi suat la 'excess return' (tien ky quy khong sinh lai); carry/swap cong rieng; chi phi tru rieng."""
import numpy as np, pandas as pd, pathlib
import pq
from scipy.stats import norm, skew as _skew, kurtosis as _kurt

R = pathlib.Path(__file__).parent; D = R / "data"
ANN = 252
FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
# base/quote cho carry; half-spread: FX tinh bang pip (spread retail ECN dien hinh 1-2 pip -> half = 0.5-1.2), kim loai/ETF bang bps
META = {
    "EURUSD": dict(kind="fx", base="EUR", quote="USD", half_pips=0.6, pip=1e-4),
    "GBPUSD": dict(kind="fx", base="GBP", quote="USD", half_pips=0.9, pip=1e-4),
    "USDJPY": dict(kind="fx", base="USD", quote="JPY", half_pips=0.7, pip=1e-2),
    "AUDUSD": dict(kind="fx", base="AUD", quote="USD", half_pips=0.9, pip=1e-4),
    "USDCAD": dict(kind="fx", base="USD", quote="CAD", half_pips=1.1, pip=1e-4),
    "USDCHF": dict(kind="fx", base="USD", quote="CHF", half_pips=1.1, pip=1e-4),
    "NZDUSD": dict(kind="fx", base="NZD", quote="USD", half_pips=1.2, pip=1e-4),
    "XAUUSD": dict(kind="metal", half_bps=2.5),   # spread CFD ~0.4-0.6 USD tren ~2000 USD => nua spread ~2-3 bps
    "XAGUSD": dict(kind="metal", half_bps=6.0),
    "SPY": dict(kind="eq", half_bps=1.0),
}
PRE2010_COST_MULT = 1.5   # spread retail truoc 2010 rong hon
CCY = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]


def load_prices(names):
    """FX lay tu ECB (Yahoo FX loi: tuong quan ngay voi ECB chi ~0.45, bad print 17%); kim loai/SPY tu Yahoo (GC=F, SI=F, SPY)."""
    fx = pq.load(D / "ecb_close.parquet")
    y = pq.load(D / "yahoo_close.parquet")
    y = y[y.index.dayofweek < 5]
    cols = {n: (fx[n] if n in fx.columns else y[n]) for n in names}
    df = pd.DataFrame(cols).sort_index()
    df = df.ffill(limit=5)  # ngay le kim loai/ETF: giu gia (loi suat 0)
    anchor = [c for c in names if c in fx.columns]
    return df[df[anchor[0]].notna()] if anchor else df.dropna(how="all")


def load_rates(index):
    """Lai suat lien ngan hang 3M (FRED/OECD, thang). Tre 1 thang (cong bo), ffill. JPY<2002-04 va CHF<1999-07 la xap xi."""
    r = pq.load(D / "rates_3m.parquet")[CCY]
    r["JPY"] = r["JPY"].fillna(0.1)   # BoJ ~0-0.5% giai doan 1999-2002 (xap xi)
    r["CHF"] = r["CHF"].bfill()
    last = r.apply(lambda s: s.dropna().index.max())
    r = r.shift(1) / 100.0
    d = r.reindex(r.index.union(index)).sort_index().ffill().reindex(index)
    valid_end = (last.min() + pd.DateOffset(months=2)).normalize()
    return d, valid_end


def carry_rate_diff(cols, rates):
    """Lai/nam nhan duoc khi LONG 1 don vi moi instrument."""
    out = pd.DataFrame(index=rates.index, columns=cols, dtype=float)
    for c in cols:
        m = META[c]
        out[c] = (rates[m["base"]] - rates[m["quote"]]) if m["kind"] == "fx" else -rates["USD"]  # CFD kim loai/ETF: long tra lai USD
    return out


def half_cost(prices):
    """Chi phi 1 chieu theo phan tram gia (nua spread)."""
    c = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for n in prices.columns:
        m = META[n]
        c[n] = m["half_pips"] * m["pip"] / prices[n] if m["kind"] == "fx" else m["half_bps"] * 1e-4
    mult = pd.Series(np.where(prices.index < "2010-01-01", PRE2010_COST_MULT, 1.0), index=prices.index)
    return c.mul(mult, axis=0)


def ewm_vol(ret, span=60):
    return ret.ewm(span=span, min_periods=30).std() * np.sqrt(ANN)


def run(prices, signal, rates, cost_mult=1.0, markup=0.005, target=0.10, inst_cap=4.0, lev_cap=6.0, vol_target=True):
    """signal: DataFrame (NaN = instrument ngoai universe; so = huong).
    1) moi instrument chuan hoa rui ro bang 1/vol (EWMA60), chia 1/N; 2) scale cap chien luoc ve vol muc tieu (ex-ante, tre 1 ngay);
    3) tru chi phi nua-spread theo |dvi the|, cong carry/swap, tru markup swap."""
    P = prices.reindex(columns=signal.columns)
    r = P.pct_change().fillna(0.0)
    vol = ewm_vol(P.pct_change()).clip(lower=0.02)
    live = signal.notna() & P.notna() & vol.notna()
    S = signal.where(live, 0.0)
    n = live.sum(axis=1).replace(0, np.nan)
    u = S * (1.0 / vol).clip(upper=inst_cap / target).fillna(0.0)
    u = u.div(n, axis=0).fillna(0.0) * target
    q = u.shift(1).fillna(0.0)
    gross0 = (q * r).sum(axis=1)
    if vol_target:
        sv = gross0.ewm(span=60, min_periods=60).std().shift(1) * np.sqrt(ANN)
        s = (target / sv.clip(lower=0.01)).clip(upper=lev_cap)
        s[sv.isna()] = 0.0
    else:
        s = pd.Series(1.0, index=P.index)
    qf = q.mul(s, axis=0)
    spot = (qf * r).sum(axis=1)
    cost = (qf.diff().abs().fillna(0.0) * half_cost(P).shift(1).bfill() * cost_mult).sum(axis=1)
    dt = pd.Series(P.index.to_series().diff().dt.days.fillna(1).values, index=P.index).clip(lower=1)
    rd = carry_rate_diff(list(P.columns), rates).fillna(0.0)
    carry = ((qf * rd.shift(1).bfill()).sum(axis=1) - qf.abs().sum(axis=1) * markup) * dt / 365.0
    net = spot + carry - cost
    act = qf.abs().sum(axis=1) > 0
    first = act.idxmax() if act.any() else P.index[0]
    return dict(net=net[first:], spot=spot[first:], carry=carry[first:], cost=cost[first:], pos=qf[first:],
                lev=qf.abs().sum(axis=1)[first:], turnover=qf.diff().abs().sum(axis=1)[first:])


def years(idx):
    return (idx[-1] - idx[0]).days / 365.25


def metrics(r):
    r = r.dropna()
    if len(r) < 50 or r.std() == 0:
        return {}
    eq = (1 + r).cumprod(); yrs = years(r.index)
    cagr = eq.iloc[-1] ** (1 / yrs) - 1; vol = r.std() * np.sqrt(ANN)
    sharpe = r.mean() / r.std() * np.sqrt(ANN)
    dd = eq / eq.cummax() - 1; mdd = dd.min()
    dn = np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(ANN)
    yr = (1 + r).groupby(r.index.year).prod() - 1
    full = yr.iloc[1:-1] if len(yr) > 3 else yr
    under = dd < -1e-9
    run_len = under.groupby((~under).cumsum()).cumsum().max()
    return dict(CAGR=cagr, Vol=vol, Sharpe=sharpe, Sortino=r.mean() * ANN / dn if dn > 0 else np.nan, MaxDD=mdd,
                Calmar=cagr / abs(mdd) if mdd < 0 else np.nan, PctLossYears=(full < 0).mean(), Skew=r.skew(),
                Kurt=r.kurt(), MaxUnderwaterYears=run_len / ANN, Years=yrs)


def block_bootstrap_sharpe(r, B=2000, block=21, seed=7):
    r = r.dropna().values; T = len(r); rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block)); starts = rng.integers(0, T, size=(B, nb))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % T).reshape(B, -1)[:, :T]
    x = r[idx]; sh = x.mean(1) / x.std(1, ddof=1) * np.sqrt(ANN)
    return np.percentile(sh, [2.5, 97.5]), float((sh <= 0).mean())


def deflated_sharpe(r, trial_sharpes_daily, n_trials):
    """Bailey & Lopez de Prado (2014). Tra (DSR=P[SR that>0 sau hieu chinh], SR0 nam hoa = nguong ky vong cua max-trong-N-lan-thu)."""
    r = r.dropna().values; T = len(r); sr = r.mean() / r.std(ddof=1)
    g = 0.5772156649; v = np.std(trial_sharpes_daily, ddof=1)
    sr0 = v * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * np.e)))
    sk = _skew(r); ku = _kurt(r, fisher=False)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / den)), float(sr0 * np.sqrt(ANN))


def psr0(r):
    r = r.dropna().values; T = len(r); sr = r.mean() / r.std(ddof=1); sk = _skew(r); ku = _kurt(r, fisher=False)
    return float(norm.cdf(sr * np.sqrt(T - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)))
