"""Chien luoc + benchmark cho backtest co phieu VN (build decide(i) cho vn_engine.simulate)."""
import numpy as np, pandas as pd
from vn_common import *
from vn_engine import Panel, Cfg, simulate, period_ends, regime
from engine import metrics

START = pd.Timestamp("2014-02-01")      # ngay dau tien co du 12 thang lich su (du lieu bat dau 2013-01-02)


def proxy_returns(P, top=100, power=1.0):
    """Loi suat ngay cua chi so proxy: top-N thanh khoan (theo hang TRUOC do), ty trong ~ GTGD TB60^power (xap xi von hoa; khong co so luong CP luu hanh)."""
    w = np.where(np.isfinite(P.tv60.values), P.tv60.values, 0.0) ** power * (np.nan_to_num(P.rank_tv, nan=1e9) <= top)
    w = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-9)
    r = np.nan_to_num(P.ret.values)
    return pd.Series(np.r_[0.0, (w[:-1] * r[1:]).sum(axis=1)], index=P.dates)


PROXY = dict(top=100, power=0.5)     # proxy thanh khoan khop VN-Index that tot nhat (xem proxy_test.py: corr ngay 0,92, dong y che do ~84%)


def build_vni(P, idx_raw, top=None, power=None, use_etf=True):
    """Chuoi 'VNI chain' (muc gia) noi bang loi suat: proxy thanh khoan (2013 -> khi E1VFVN30 niem yet 2014-10) -> E1VFVN30 (ETF VN30; -> 2017-08) -> VN-Index that (nguon, tu 2017-08-24).
    Tra (Series level theo P.dates, thong ke so khop tren giai doan 2017-08 -> nay)."""
    top = top or PROXY["top"]; power = power or PROXY["power"]
    real = idx_raw[idx_raw.code == "VNINDEX"].copy(); real["date"] = pd.to_datetime(real["date"])
    real = real.set_index("date")["close"].astype(float).sort_index(); real = real[~real.index.duplicated()]
    ri = real.reindex(P.dates); first = ri.first_valid_index(); pos = P.dates.get_loc(first); base = float(ri.loc[first])
    pr = proxy_returns(P, top, power)
    rret = pr.copy()
    j = P.cidx.get("E1VFVN30")
    if use_etf and j is not None:
        er = P.ACd.iloc[:, j].pct_change(fill_method=None)
        e0 = P.dates[P.first_idx[j] + 1]
        m = (P.dates >= e0) & (P.dates < first); rret[m] = er[m].fillna(pr[m])
    rr = 1.0 + rret.values
    arr = ri.ffill().values.copy(); arr[pos] = base
    for t in range(pos - 1, -1, -1): arr[t] = arr[t + 1] / rr[t + 1]
    lvl = pd.Series(arr, index=P.dates)
    both = pd.concat([ri.pct_change(), pr], axis=1).dropna(); both.columns = ["real", "proxy"]; both = both.loc[first:]
    yrs = (both.index[-1] - both.index[0]).days / 365.25
    out = dict(corr_daily=float(both.corr().iloc[0, 1]), corr_monthly=float(((1 + both).resample("ME").prod() - 1).corr().iloc[0, 1]), real_start=str(first.date()), n=len(both),
               proxy_cagr=float((1 + both.proxy).prod() ** (1 / yrs) - 1), real_cagr=float((1 + both.real).prod() ** (1 / yrs) - 1), top=top, power=power)
    sma_r = real.rolling(200).mean(); on_real = (real > sma_r)
    def agree(r_series):
        px = (1 + r_series).cumprod(); on = (px > px.rolling(200).mean()).reindex(on_real.index)
        ok = sma_r.notna(); return float((on_real[ok] == on[ok]).mean())
    out["regime_agree_proxy"] = agree(pr.reindex(real.index).fillna(0.0)) if False else agree(pr.loc[first:])
    if j is not None:
        er = P.ACd.iloc[:, j].pct_change(fill_method=None).loc[first:].fillna(0.0)
        out["regime_agree_etf"] = agree(er); out["corr_daily_etf"] = float(pd.concat([ri.pct_change(), er], axis=1).dropna().corr().iloc[0, 1])
        out["etf_start"] = str(P.dates[P.first_idx[j]].date())
    return lvl, out


def rebal_idx(P, freq="M"):
    return period_ends(P.dates, freq, START)


def universe_rank(P, allowed=None):
    """Hang theo thanh khoan (GTGD TB60) giua cac ma du dieu kien; allowed = mang bool theo cot de gioi han universe (survivors/VN100 hien tai)."""
    if allowed is None: return P.rank_tv
    ok = P.elig & np.asarray(allowed)[None, :]
    return P.tv60.where(pd.DataFrame(ok, index=P.dates, columns=P.codes)).rank(axis=1, ascending=False, method="first").values


def ew_universe(P, uni, rank=None):
    rk = P.rank_tv if rank is None else rank
    def decide(i):
        m = np.flatnonzero(rk[i] <= uni)
        return {int(j): 1.0 / len(m) for j in m} if len(m) >= 5 else {}
    return decide


def single(P, code):
    j = P.cidx[code]
    return lambda i: {j: 1.0}


def momentum(P, S, N=15, uni=100, weight="ew", reg=None, pos_only=False, sign=1.0, rng=None, rand=False, rank=None):
    """Top-N theo diem S trong universe theo thanh khoan (uni = 30 hoac 100). reg: mang bool (True = duoc giu co phieu).
    rand=True: chon N ngau nhien trong cung universe/dieu kien (placebo). sign=-1: dao chieu (losers)."""
    rk = P.rank_tv if rank is None else rank
    def decide(i):
        if reg is not None and not reg[i]: return {}
        cand = np.flatnonzero((rk[i] <= uni) & np.isfinite(S[i]))
        if pos_only: cand = cand[S[i, cand] > 0]
        if len(cand) < 5: return {}
        if rand:
            top = rng.choice(cand, size=min(N, len(cand)), replace=False)
        else:
            top = cand[np.argsort(-sign * S[i, cand])[:N]]
        if weight == "iv":
            iv = 1.0 / np.clip(P.vol60[i, top], 0.10, None); w = iv / iv.sum()
        else:
            w = np.full(len(top), 1.0 / len(top))
        return {int(j): float(x) for j, x in zip(top, w)}
    return decide


def triggers(P, freq, reg, mode, start=None):
    """Ngay quyet dinh: cuoi thang/quy (+ ngay doi che do neu mode == 'D')."""
    base = period_ends(P.dates, freq, start or START)
    if mode == "D" and reg is not None:
        fl = np.flatnonzero(reg[1:] != reg[:-1]) + 1
        fl = fl[P.dates[fl] >= (start or START)]
        base = np.unique(np.r_[base, fl])
    return base


def summarize(res, rf=RF, label=""):
    nav = res["nav"]; r = res["ret"]
    ex = r - rf / ANN
    m = metrics(ex)
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    dd = (nav / nav.cummax() - 1).min()
    return dict(label=label, Sharpe=m.get("Sharpe", np.nan), CAGR=cagr, Vol=r.std() * np.sqrt(ANN), MaxDD=dd,
                Calmar=cagr / abs(dd) if dd < 0 else np.nan, Skew=m.get("Skew", np.nan), PctLossYears=m.get("PctLossYears", np.nan),
                Expo=float(res["expo"].mean()), NHeld=float(res["nheld"].mean()), TurnoverYr=res.get("turnover_yr", np.nan),
                CostYr=res.get("cost_yr", np.nan), start=str(nav.index[0].date()), end=str(nav.index[-1].date()), Years=yrs)


def index_result(level, start, rf=RF):
    """Mua giu chi so (khong chi phi) tu `start` -> dict nhu simulate (de dung chung summarize)."""
    lv = level.loc[start:].dropna(); nav = lv / lv.iloc[0]
    return dict(nav=nav, ret=nav.pct_change().dropna(), expo=pd.Series(1.0, index=nav.index), nheld=pd.Series(1.0, index=nav.index),
                turnover_yr=0.0, cost_yr=0.0)
