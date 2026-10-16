"""Engine backtest co phieu VN, long-only, su kien theo ngay (minh bach, khong vectorbt).
Quy uoc thoi gian (KHONG look-ahead): tin hieu/tai trong tinh bang du lieu den close ngay t (ngay quyet dinh).
  - lenh BAN dat o phien t+1 (gia khop = VWAP phien do -+ truot gia), tien ve tai khoan sau T+2 (kha dung de MUA tu ngay t+3);
  - lenh MUA dat o phien t+3 (cho tien ban ve, gia khop = VWAP +- truot gia); co phieu mua o ngay d chi ban lai duoc tu d+2 (T+2).
Rang buoc: lo 100 cp; lock tran/san (khong mua duoc neu low>=tran, khong ban duoc neu high<=san); khoi luong ngay <= part_cap * KL TB 20 phien
(va <= 20% KL phien do); phi 0,15%/chieu + thue ban 0,1% + truot gia (nua buoc gia + co dinh + tac dong ~ sqrt(ty le thanh khoan));
tien mat sinh lai rf; ma het du lieu (huy niem yet): tat toan (tuy chon giam gia delist_haircut).
Gia: P&L tinh tren gia DIEU CHINH (adClose/adAverage: da gom co tuc/thuong/chia tach); gia tho dung cho lo, buoc gia, bien do.
"""
import numpy as np, pandas as pd
from dataclasses import dataclass
from vn_common import *


class Panel:
    def __init__(self, df, min_names=50):
        cnt = df.groupby("date").size()
        self.dates = cnt[cnt >= min_names].index
        df = df[df.date.isin(self.dates)]
        self.codes = sorted(df.code.unique())
        self.cidx = {c: i for i, c in enumerate(self.codes)}
        pv = lambda col: df.pivot(index="date", columns="code", values=col).reindex(index=self.dates, columns=self.codes)
        self.O, self.H, self.L, self.C = pv("open").values, pv("high").values, pv("low").values, pv("close").values
        self.AV = pv("average").values
        ac = pv("adClose")
        self.VOLd, self.VALd = pv("nmVolume"), pv("nmValue")
        self.VOL, self.VAL = self.VOLd.values, self.VALd.values
        self.CEIL, self.FLR = pv("ceilingPrice").values, pv("floorPrice").values
        self.floor = df.pivot(index="date", columns="code", values="floor").reindex(index=self.dates, columns=self.codes)
        typ = df.drop_duplicates("code").set_index("code")["type"].reindex(self.codes)
        self.is_etf = (typ.values == "ETF")
        self.T, self.N = len(self.dates), len(self.codes)
        self.has = ac.notna().values
        self.last_idx = np.array([np.where(self.has[:, j])[0].max() if self.has[:, j].any() else -1 for j in range(self.N)])
        self.first_idx = np.array([np.where(self.has[:, j])[0].min() if self.has[:, j].any() else self.T for j in range(self.N)])
        self.ACd = ac.ffill()
        self.ACf = self.ACd.values
        self.Cf = pd.DataFrame(self.C, index=self.dates, columns=self.codes).ffill().values
        self.F = self.ACf / self.Cf                                   # F = gia dieu chinh / gia tho; co phieu tho = hold_adj * F; hold_adj = co tho / F
        v = self.VOLd.fillna(0.0); val = self.VALd.fillna(0.0)
        traded = (v > 0)
        self.advv = v.rolling(20, min_periods=10).mean().values        # KL TB 20 phien (cp) den ngay t
        self.advval = val.rolling(20, min_periods=10).mean().values    # GTGD TB 20 phien (VND)
        self.tv60 = val.rolling(60, min_periods=40).mean()
        td60 = traded.rolling(60, min_periods=40).sum().values
        self.td120 = traded.rolling(120, min_periods=60).sum().values
        self.nobs = ac.notna().cumsum().values
        isstock = ~self.is_etf[None, :]
        hose = (self.floor == "HOSE").values
        self.elig = (td60 >= 40) & isstock & hose & self.has & (self.nobs >= 200)
        self.rank_tv = self.tv60.where(pd.DataFrame(self.elig, index=self.dates, columns=self.codes)).rank(axis=1, ascending=False, method="first").values
        self.ret = self.ACd.pct_change(fill_method=None).where(ac.notna())
        self.vol60 = self.ACd.pct_change(fill_method=None).rolling(60, min_periods=40).std().values * np.sqrt(ANN)
        self.last_date = {c: self.dates[self.last_idx[i]] for c, i in self.cidx.items() if self.last_idx[i] >= 0}

    def mom(self, lb, skip):
        """Momentum (lb - skip) phien: P(t-skip)/P(t-lb)-1 tren gia dieu chinh; NaN neu thieu lich su hoac it giao dich."""
        s = (self.ACd.shift(skip) / self.ACd.shift(lb) - 1).values
        ok = (self.nobs > lb + 1) & (self.td120 >= 80)
        return np.where(ok, s, np.nan)


def period_ends(dates, freq="M", start=None):
    """Chi so ngay giao dich CUOI moi thang/quy (bo ky cuoi vi chua dong)."""
    s = pd.Series(np.arange(len(dates)), index=dates)
    key = dates.to_period("M" if freq == "M" else "Q")
    last = s.groupby(key).max().values[:-1]
    return np.array([i for i in last if start is None or dates[i] >= pd.Timestamp(start)], dtype=int)


def regime(vni, ma=200):
    """vni: Series close khop P.dates. True khi close > SMA(ma) (False khi chua du ma phien)."""
    s = vni.rolling(ma, min_periods=ma).mean()
    return ((vni > s) & s.notna()).values


@dataclass
class Cfg:
    capital: float = 1e9
    invest: float = 0.98
    part_cap: float = 0.10       # toi da % KL TB 20 phien moi ngay
    day_vol_cap: float = 0.20    # toi da % KL phien khop
    cost_mult: float = 1.0       # nhan phi + thue + truot gia
    slip_base_bps: float = 5.0
    impact_bps: float = 10.0     # tai muc 1% GTGD TB20
    fill: str = "vwap"           # vwap | close | open
    sell_delay: int = 1
    buy_delay: int = 3
    t2_lock: int = 2             # chi ban lai tu d+2 sau khi mua
    pend_days: int = 5
    rf: float = RF
    delist_haircut: float = 0.0
    start: int = 0


def simulate(P, decide, trig, cfg=None, want_log=False):
    """decide(i) -> {j: trong so}; trig: cac chi so ngay quyet dinh. Tra dict(nav, ret, expo, nheld, turnover_yr, cost_yr, tot)."""
    cfg = cfg or Cfg()
    T, N = P.T, P.N
    cash = cfg.capital; recv = []
    hold = np.zeros(N); last_buy = np.full(N, -999)
    nav = np.full(T, np.nan); expo = np.zeros(T); nheld = np.zeros(T)
    pend = []
    trigset = set(int(x) for x in trig)
    tot = dict(comm=0.0, tax=0.0, slip=0.0, traded=0.0, blocked=0, partial=0)
    cm = cfg.cost_mult; daily_rf = cfg.rf / ANN
    log = []
    for d in range(cfg.start, T):
        if recv:
            keep = []
            for (da, amt) in recv:
                if da <= d: cash += amt
                else: keep.append((da, amt))
            recv = keep
        cash *= (1.0 + daily_rf)
        gone = np.where((hold > 0) & (P.last_idx + 5 < d))[0]       # het du lieu = huy niem yet/ngung: tat toan
        for j in gone:
            val = hold[j] * P.ACf[d, j]
            recv.append((d + 2, val * (1 - cfg.delist_haircut) * (1 - (COMMISSION + SELL_TAX) * cm)))
            hold[j] = 0.0
        if d in trigset:
            pend = []
            nv = cash + sum(a for _, a in recv) + float(np.nansum(hold * P.ACf[d]))
            tw = decide(d) or {}
            tgt = {}
            for j, w in tw.items():
                c = P.Cf[d, j]
                if np.isfinite(c) and c > 0: tgt[j] = float(np.floor(w * cfg.invest * nv / c / LOT) * LOT)
            cur = np.where(hold > 0)[0]
            for j in set(cur.tolist()) | set(tgt.keys()):
                held_raw = hold[j] * P.F[d, j] if hold[j] > 0 and np.isfinite(P.F[d, j]) else 0.0
                t_raw = tgt.get(j, 0.0)
                if held_raw > t_raw + 1e-9 and (held_raw - t_raw >= LOT or t_raw == 0):
                    pend.append((d + cfg.sell_delay, d + cfg.sell_delay + cfg.pend_days, j, -1, t_raw))
                elif t_raw - held_raw >= LOT:
                    pend.append((d + cfg.buy_delay, d + cfg.buy_delay + cfg.pend_days, j, +1, t_raw))
        if pend:
            todo = [o for o in pend if o[0] <= d]
            rest = [o for o in pend if o[0] > d]
            for (due, exp, j, side, t_raw) in sorted(todo, key=lambda o: o[3]):
                f = P.F[d, j]
                held_raw = hold[j] * f if hold[j] > 0 and np.isfinite(f) else 0.0
                need = (held_raw - t_raw) if side < 0 else (t_raw - held_raw)
                if need < (1.0 if (side < 0 and t_raw == 0) else LOT): continue          # da xong
                vol_d = P.VOL[d, j] if np.isfinite(P.VOL[d, j]) else 0.0
                bad = (vol_d <= 0) or (not np.isfinite(f))
                if side > 0 and not bad and np.isfinite(P.L[d, j]) and np.isfinite(P.CEIL[d, j]) and P.L[d, j] >= P.CEIL[d, j] - 1e-6: bad = True
                if side < 0 and not bad and np.isfinite(P.H[d, j]) and np.isfinite(P.FLR[d, j]) and P.H[d, j] <= P.FLR[d, j] + 1e-6: bad = True
                if side < 0 and d - last_buy[j] < cfg.t2_lock: bad = True
                if bad:
                    tot["blocked"] += 1
                    if d < exp: rest.append((due, exp, j, side, t_raw))
                    continue
                av = P.advv[d - 1, j] if d > 0 and np.isfinite(P.advv[d - 1, j]) else vol_d
                cap = min(cfg.part_cap * av, cfg.day_vol_cap * vol_d)
                px = {"vwap": P.AV[d, j], "close": P.C[d, j], "open": P.O[d, j]}[cfg.fill]
                if not (np.isfinite(px) and px > 0): px = P.C[d, j]
                q = min(need, cap)
                adval = P.advval[d - 1, j] if d > 0 and np.isfinite(P.advval[d - 1, j]) and P.advval[d - 1, j] > 0 else max(vol_d * px, 1.0)
                part = q * px / adval
                slip = ((0.5 * float(tick_size(px)) / px) + cfg.slip_base_bps / 1e4 + cfg.impact_bps / 1e4 * np.sqrt(max(part, 1e-9) / 0.01)) * cm
                if side > 0:
                    pe = px * (1 + slip)
                    if np.isfinite(P.CEIL[d, j]): pe = min(pe, P.CEIL[d, j])
                    q = min(q, cash / (pe * (1 + COMMISSION * cm)))
                    q = float(np.floor(q / LOT) * LOT)
                    if q < LOT:
                        tot["blocked"] += 1
                        if d < exp: rest.append((due, exp, j, side, t_raw))
                        continue
                    gross = q * pe; fee = gross * COMMISSION * cm
                    cash -= gross + fee; hold[j] += q / f; last_buy[j] = d
                    tot["comm"] += fee; tot["slip"] += q * (pe - px); tot["traded"] += gross
                else:
                    pe = px * (1 - slip)
                    if np.isfinite(P.FLR[d, j]): pe = max(pe, P.FLR[d, j])
                    if t_raw == 0 and need <= cap: q = held_raw
                    else: q = float(np.floor(min(need, cap) / LOT) * LOT)
                    if q <= 0:
                        tot["blocked"] += 1
                        if d < exp: rest.append((due, exp, j, side, t_raw))
                        continue
                    gross = q * pe; fee = gross * COMMISSION * cm; tax = gross * SELL_TAX * cm
                    recv.append((d + 2, gross - fee - tax)); hold[j] = max(hold[j] - q / f, 0.0)
                    if hold[j] * P.ACf[d, j] < 1.0: hold[j] = 0.0
                    tot["comm"] += fee; tot["tax"] += tax; tot["slip"] += q * (px - pe); tot["traded"] += gross
                if q < need - 1e-9:
                    tot["partial"] += 1
                    if d < exp: rest.append((due, exp, j, side, t_raw))
                if want_log: log.append((P.dates[d], P.codes[j], side, q, pe))
            pend = rest
        inv = float(np.nansum(hold * P.ACf[d])); nv = cash + sum(a for _, a in recv) + inv
        nav[d] = nv; expo[d] = inv / nv if nv > 0 else 0.0; nheld[d] = int((hold > 0).sum())
    nav = pd.Series(nav, index=P.dates).dropna()
    yrs = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    out = dict(nav=nav, ret=nav.pct_change().dropna(), expo=pd.Series(expo, index=P.dates).loc[nav.index],
               nheld=pd.Series(nheld, index=P.dates).loc[nav.index],
               turnover_yr=tot["traded"] / cfg.capital / yrs / 2.0,           # (mua + ban) / 2 / von / nam
               cost_yr=(tot["comm"] + tot["tax"] + tot["slip"]) / cfg.capital / yrs, tot=tot)
    if want_log: out["log"] = log
    return out
