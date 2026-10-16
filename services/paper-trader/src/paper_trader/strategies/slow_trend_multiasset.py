"""Trend chậm đa tài sản — CÀI ĐẶT ĐÚNG NHƯ BACKTEST (research/multiasset/ma_engine.py, docs/research/MULTI_ASSET_BACKTEST.md).

Các bước (mỗi lần engine gọi `targets`, tức mỗi kỳ rebalance — mặc định cuối/đầu tháng):
  1. Chuỗi chỉ số I = cumprod(1 + r_excess). Bar D1 của ETF/FX là GIÁ THÔ => r_excess xấp xỉ = r_giá + (cổ tức/coupon − lãi tiền mặt)·dt
     (xem `_net_carry`; FX: chỉ giá spot, KHÔNG có carry — giới hạn đã biết).
  2. Tín hiệu mỗi tài sản = TRUNG BÌNH 4 bộ (tham số cố định theo văn liệu, KHÔNG tối ưu):
        tsmom_12_1  : sign(I[t-21]/I[t-252]-1)
        tsmom_multi : mean(sign(I[t]/I[t-L]-1), L in 21,63,252)
        ma200       : sign(I[t]-SMA200(I))
        donchian    : vào dài > max 200 ngày trước / vào ngắn < min 200; thoát khi cắt min/max 100 ngày (trạng thái giữ)
     Tài sản thiếu lịch sử cho BẤT KỲ bộ nào (≈ 254 phiên) bị bỏ qua (không có tín hiệu). long_short: clip [-1,1]; allow_short=false: clip [0,1].
  3. Ngân sách rủi ro 'class_balanced': 6 lớp (eq, bond, fx, metal, energy, agri) ngang rủi ro, trong lớp chia đều; lớp chưa có dữ liệu bị bỏ.
  4. raw_i = signal_i · budget_i · target_vol / sigma_i  (sigma: EWMA std span 60, sàn 1%, năm hoá 252).
  5. Vol-target danh mục: L = min(lmax, target_vol / sqrt(w'Σw)), Σ = EWMA halflife 60 trên 501 phiên, shrink 20% về đường chéo.
  6. Trần: |w_i| <= asset_cap, gross <= gross_cap (backtest: 3.0 / 8.0). Hai trần BỔ SUNG (mặc định TẮT = giống backtest, tài khoản v2 bật
     để mô phỏng khả thi với vốn nhỏ): class_gross_cap (tổng |w| mỗi lớp) và short_class_cap (tổng vị thế BÁN mỗi lớp, vd bond).
Trả về Targets(kind='weight'): tỷ trọng danh nghĩa/vốn — risk engine ở chế độ passthrough chỉ còn cổng an toàn (max_weight, max_leverage).

Các hàm module-level là THUẦN (numpy/pandas) để test hồi quy so với bản sao mã backtest (tests/ref_backtest.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import Targets
from ..strategy import Strategy, StrategyContext, register

ANN = 252
CLASSES = ["eq", "bond", "fx", "metal", "energy", "agri"]

# symbol paper -> (lớp, loại carry, q%/năm). carry: 'div' = cổ tức (q) trừ tiền mặt; 'bond' = coupon≈tiền mặt (net 0);
# 'fx' = không có carry trong dữ liệu spot (net 0); 'cmd' = hàng hoá: chỉ trừ tiền mặt (collateral). q lấy từ research/multiasset/ma_common.py
# (EWG/FEZ... là ETF giá thô nên dùng lợi suất cổ tức của ETF thay cho chỉ số hiệu suất của backtest).
ASSET_MAP: dict[str, tuple[str, str, float]] = {
    "US:SPY": ("eq", "div", 2.0), "US:QQQ": ("eq", "div", 0.9), "US:IWM": ("eq", "div", 1.3), "US:EWG": ("eq", "div", 2.5),
    "US:FEZ": ("eq", "div", 3.3), "US:EWQ": ("eq", "div", 3.0), "US:EWU": ("eq", "div", 3.8), "US:EWJ": ("eq", "div", 1.8),
    "US:EWH": ("eq", "div", 3.2), "US:EWA": ("eq", "div", 4.0), "US:EWY": ("eq", "div", 1.5), "US:INDA": ("eq", "div", 1.3),
    "US:EWZ": ("eq", "div", 4.0), "US:VNM": ("eq", "div", 1.0),
    "US:SHY": ("bond", "bond", 0.0), "US:IEI": ("bond", "bond", 0.0), "US:IEF": ("bond", "bond", 0.0), "US:TLT": ("bond", "bond", 0.0),
    "EURUSD": ("fx", "fx", 0.0), "GBPUSD": ("fx", "fx", 0.0), "USDJPY": ("fx", "fx", 0.0), "AUDUSD": ("fx", "fx", 0.0),
    "USDCAD": ("fx", "fx", 0.0), "USDCHF": ("fx", "fx", 0.0), "NZDUSD": ("fx", "fx", 0.0),
    "XAUUSD": ("metal", "cmd", 0.0), "US:GLD": ("metal", "cmd", 0.0), "US:SLV": ("metal", "cmd", 0.0), "US:CPER": ("metal", "cmd", 0.0),
    "US:USO": ("energy", "cmd", 0.0), "US:BNO": ("energy", "cmd", 0.0), "US:UNG": ("energy", "cmd", 0.0),
    "US:CORN": ("agri", "cmd", 0.0), "US:WEAT": ("agri", "cmd", 0.0), "US:SOYB": ("agri", "cmd", 0.0), "US:CANE": ("agri", "cmd", 0.0),
}
# tên tài sản trong backtest (để đối chiếu / báo cáo)
BACKTEST_NAME = {"US:SPY": "SPX", "US:QQQ": "NDX", "US:IWM": "RUT", "US:EWG": "DAX", "US:FEZ": "SX5E", "US:EWQ": "CAC", "US:EWU": "FTSE",
                 "US:EWJ": "N225", "US:EWH": "HSI", "US:EWA": "ASX", "US:EWY": "KOSPI", "US:INDA": "SENSEX", "US:EWZ": "BVSP",
                 "US:VNM": "VNM", "US:SHY": "UST2", "US:IEI": "UST5", "US:IEF": "UST10", "US:TLT": "UST30", "US:GLD": "GOLD",
                 "US:SLV": "SILVER", "US:CPER": "COPPER", "US:USO": "WTI", "US:BNO": "BRENT", "US:UNG": "NATGAS", "US:CORN": "CORN",
                 "US:WEAT": "WHEAT", "US:SOYB": "SOY", "US:CANE": "SUGAR", "XAUUSD": "GOLD"}


def asset_info(sym: str) -> tuple[str, str, float]:
    if sym in ASSET_MAP:
        return ASSET_MAP[sym]
    if sym.startswith("VN:"):
        return ("eq", "none", 0.0)              # cổ phiếu VN: giá thô VND, không điều chỉnh (xem README)
    if sym.startswith("US:"):
        return ("eq", "div", 0.0)
    if sym[:3] in {"XAU", "XAG", "XPT", "XPD"}:
        return ("metal", "cmd", 0.0)
    return ("fx", "fx", 0.0)


def _net_carry(sym: str, cash_rate: float, overrides: dict | None) -> float:
    """Phần dịch chuyển/năm cộng vào lợi suất giá thô để xấp xỉ lợi suất excess (vượt tiền mặt)."""
    if overrides and sym in overrides:
        return float(overrides[sym])
    _, kind, q = asset_info(sym)
    if kind == "div":
        return q / 100.0 - cash_rate
    if kind == "cmd":
        return -cash_rate
    return 0.0


# ---------------------------------------------------------------------------------------------- dữ liệu -> lợi suất excess
def build_returns(history: dict[str, pd.DataFrame], symbols, cash_rate: float = 0.04, carry_overrides: dict | None = None,
                  max_stale_days: int = 10, adjust_carry: bool = True) -> tuple[pd.DataFrame, dict]:
    """DataFrame R (index = lịch hợp nhất, cột = symbol): lợi suất excess/phiên; NaN trước khi tài sản có dữ liệu; ngày nghỉ riêng -> 0
    (giống backtest: fillna(0) trong [first,last]). Symbol có nến cuối cũ hơn max_stale_days so với lịch chung bị loại (meta.stale)."""
    ser: dict[str, pd.Series] = {}
    for s in symbols:
        df = history.get(s)
        if df is None or len(df) < 3:
            continue
        c = df["c"].astype(float)
        idx = pd.DatetimeIndex(c.index)
        c.index = (idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx).normalize()
        c = c[~c.index.duplicated(keep="last")].sort_index()
        c = c[c > 0]
        if len(c) >= 3:
            ser[s] = c
    meta: dict = {"stale": [], "missing": [s for s in symbols if s not in ser]}
    if not ser:
        return pd.DataFrame(), meta
    end = max(s.index[-1] for s in ser.values())
    for s in list(ser):
        if (end - ser[s].index[-1]).days > max_stale_days:
            meta["stale"].append(s)
            del ser[s]
    cal = pd.DatetimeIndex(sorted(set().union(*[set(s.index) for s in ser.values()])))
    cols = {}
    for s, c in ser.items():
        c = c.reindex(cal)
        first = c.first_valid_index()
        c = c.loc[first:].ffill()
        if adjust_carry:
            d = _net_carry(s, cash_rate, carry_overrides)
            if d:
                days = (c.index - c.index[0]).days.values / 365.0
                c = c * np.exp(d * days)
        cols[s] = c.reindex(cal).pct_change()            # NaN trước first (và tại first)
    R = pd.DataFrame(cols, index=cal)[[s for s in symbols if s in cols]]
    return R, meta


# ---------------------------------------------------------------------------------------------- tín hiệu (bản sao backtest)
def index_from_returns(R: pd.DataFrame) -> pd.DataFrame:
    return (1 + R.fillna(0)).cumprod().where(R.notna().cummax())


def sig_tsmom(I, lb=252, skip=21):
    return np.sign(I.shift(skip) / I.shift(lb) - 1).where(I.shift(lb).notna())


def sig_multi(I, lbs=(21, 63, 252)):
    ss = [np.sign(I / I.shift(l) - 1).where(I.shift(l).notna()) for l in lbs]
    return sum(ss) / len(ss)


def sig_ma(I, slow=200):
    m = I.rolling(slow).mean()
    return np.sign(I - m).where(m.notna())


def _state_loop(long_in, long_out, short_in, short_out):
    T, N = long_in.shape
    pos = np.zeros((T, N))
    for j in range(N):
        p = 0.0
        for t in range(T):
            if p == 0:
                if long_in[t, j]:
                    p = 1.0
                elif short_in[t, j]:
                    p = -1.0
            elif p > 0 and long_out[t, j]:
                p = -1.0 if short_in[t, j] else 0.0
            elif p < 0 and short_out[t, j]:
                p = 1.0 if long_in[t, j] else 0.0
            pos[t, j] = p
    return pos


def sig_donch(P, n_in=200, n_out=100):
    hi_in = P.rolling(n_in).max().shift(1)
    lo_in = P.rolling(n_in).min().shift(1)
    hi_out = P.rolling(n_out).max().shift(1)
    lo_out = P.rolling(n_out).min().shift(1)
    pos = _state_loop((P > hi_in).values, (P < lo_out).values, (P < lo_in).values, (P > hi_out).values)
    return pd.DataFrame(pos, index=P.index, columns=P.columns).where(hi_in.notna())


def sig_ens(I: pd.DataFrame) -> pd.DataFrame:
    parts = [sig_tsmom(I, 252, 21), sig_multi(I), sig_ma(I, 200), sig_donch(I, 200, 100)]
    return sum(parts) / len(parts)


# ---------------------------------------------------------------------------------------------- phương sai / trọng số (bản sao backtest)
def ewma_sigma(R: pd.DataFrame) -> pd.DataFrame:
    return R.ewm(span=60, min_periods=60).std() * np.sqrt(ANN)


def cov_last(R: pd.DataFrame) -> np.ndarray:
    """Cov EWMA halflife 60 trên 501 phiên cuối (cặp, bỏ NaN), shrink 20% về đường chéo — như Ctx.cov của backtest."""
    n_all = len(R)
    lo = max(0, n_all - 1 - 500)
    X = R.iloc[lo:n_all].values
    m = ~np.isnan(X)
    Xz = np.where(m, X, 0.0)
    n = len(X)
    w = 0.5 ** (np.arange(n)[::-1] / 60.0)
    sw = np.sqrt(w)[:, None]
    A = Xz * sw
    M = m * sw
    num = A.T @ A
    den = M.T @ M
    cv = np.divide(num, den, out=np.zeros_like(num), where=den > 1e-9) * ANN
    return 0.8 * cv + 0.2 * np.diag(np.diag(cv))


def target_weights(R: pd.DataFrame, S_last: np.ndarray, sig_last: np.ndarray, classes: list[str], *, target: float = 0.10,
                   lmax: float = 3.0, asset_cap: float = 3.0, gross_cap: float = 8.0, class_gross_cap: dict | float | None = None,
                   short_class_cap: dict | float | None = None, min_live: int = 3) -> tuple[np.ndarray, dict]:
    """Trọng số tại ngày cuối của R. Phần lõi (budget/raw/L/clip/gross) = ma_engine.weights(scheme='rp'); hai trần lớp là phần bổ sung."""
    N = R.shape[1]
    cls = np.array(classes)
    s, g = S_last, sig_last
    live = ~np.isnan(s) & ~np.isnan(g)
    info: dict = {"n_live": int(live.sum())}
    if live.sum() < min_live:
        return np.zeros(N), info
    b = np.zeros(N)
    pres = [ix for ix in (np.where(cls == c)[0] for c in CLASSES) if live[ix].any()]
    pres = [ix[live[ix]] for ix in pres]
    K = len(pres)
    for ix in pres:
        b[ix] = 1.0 / K / len(ix)
    raw = np.where(live, np.nan_to_num(s), 0.0) * b * target / np.maximum(np.nan_to_num(g, nan=1.0), 0.01)
    if not np.any(raw):
        return np.zeros(N), info
    cv = cov_last(R)
    pv = float(np.sqrt(max(raw @ cv @ raw, 1e-12)))
    L = min(lmax, target / pv)
    w = np.clip(raw * L, -asset_cap, asset_cap)
    info.update({"L": round(L, 4), "raw_vol": round(pv, 5), "classes_live": K})
    # trần bổ sung theo lớp (mặc định tắt)
    for c in CLASSES:
        ix = np.where(cls == c)[0]
        if not len(ix):
            continue
        cap = class_gross_cap.get(c) if isinstance(class_gross_cap, dict) else class_gross_cap
        if cap is not None:
            gsum = np.abs(w[ix]).sum()
            if gsum > cap:
                w[ix] *= cap / gsum
                info.setdefault("class_capped", []).append(c)
        scap = short_class_cap.get(c) if isinstance(short_class_cap, dict) else short_class_cap
        if scap is not None:
            neg = ix[w[ix] < 0]
            ns = -w[neg].sum()
            if ns > scap:
                w[neg] *= scap / ns
                info.setdefault("short_capped", []).append(c)
    gr = np.abs(w).sum()
    if gr > gross_cap:
        w *= gross_cap / gr
        info["gross_capped"] = True
    info["exante_vol"] = round(float(np.sqrt(max(w @ cv @ w, 0.0))), 5)
    return w, info


@register("slow_trend_multiasset")
class SlowTrendMultiAsset(Strategy):
    """Trend chậm đa tài sản: ensemble 4 tín hiệu + ngân sách rủi ro theo lớp + vol-target danh mục (khớp backtest MULTI_ASSET_BACKTEST).
    params: target_vol=0.10, lmax=3.0, asset_cap=3.0, gross_cap=8.0 (mặc định = backtest), class_gross_cap/short_class_cap (None=tắt),
    allow_short=true, cash_rate=0.04, carry_overrides={}, adjust_carry=true, min_live=3, max_stale_days=10, history_required=300."""

    @property
    def required_history(self) -> int:
        return int(self.params.get("history_required", 300))

    def targets(self, ctx: StrategyContext) -> Targets:
        p = self.params
        syms = list(ctx.universe)
        R, rmeta = build_returns(ctx.history, syms, cash_rate=float(p.get("cash_rate", 0.04)), carry_overrides=p.get("carry_overrides"),
                                 max_stale_days=int(p.get("max_stale_days", 10)), adjust_carry=bool(p.get("adjust_carry", True)))
        if R.empty or len(R) < 260:
            return Targets(status="warming_up", meta={"need_bars": 260, "have_bars": 0 if R.empty else len(R), **rmeta})
        I = index_from_returns(R)
        S = sig_ens(I)
        if not bool(p.get("allow_short", True)):
            S = S.clip(lower=0)
        s_last = S.iloc[-1].to_numpy(dtype=float)
        g_last = ewma_sigma(R).iloc[-1].to_numpy(dtype=float)
        cols = list(R.columns)
        classes = [asset_info(c)[0] for c in cols]
        w, info = target_weights(R, s_last, g_last, classes, target=float(p.get("target_vol", 0.10)), lmax=float(p.get("lmax", 3.0)),
                                 asset_cap=float(p.get("asset_cap", 3.0)), gross_cap=float(p.get("gross_cap", 8.0)),
                                 class_gross_cap=p.get("class_gross_cap"), short_class_cap=p.get("short_class_cap"),
                                 min_live=int(p.get("min_live", 3)))
        if not np.any(w) and info.get("n_live", 0) < int(p.get("min_live", 3)):
            return Targets(status="warming_up", meta={"need": "tín hiệu cho >= min_live tài sản", **info, **rmeta})
        wt = {c: float(w[i]) for i, c in enumerate(cols)}
        for s in syms:
            wt.setdefault(s, 0.0)
        cg = {c: round(float(sum(abs(wt[s]) for s in cols if asset_info(s)[0] == c)), 4) for c in CLASSES}
        cn = {c: round(float(sum(wt[s] for s in cols if asset_info(s)[0] == c)), 4) for c in CLASSES}
        meta = {**info, **rmeta, "as_of": str(R.index[-1].date()), "gross": round(float(np.abs(w).sum()), 4), "net": round(float(w.sum()), 4),
                "class_gross": cg, "class_net": cn,
                "signals": {c: (None if np.isnan(s_last[i]) else round(float(s_last[i]), 3)) for i, c in enumerate(cols)}}
        return Targets(weights=wt, kind="weight", meta=meta)
