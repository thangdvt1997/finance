"""Tinh toan thuan (khong I/O) cho /v1/intel/*: suc manh tien te, heatmap, movers, tuong quan, beta, phan phoi, nhip thi truong, chu de tin.

Moi con so la THONG KE tu du lieu gia da luu (nen D1/H1/H4), KHONG phai khuyen nghi dau tu. Chuoi nen: list[Bar] tang dan theo thoi gian,
Bar = (ts: datetime, o, h, l, c, v). Khong dung numpy (gateway khong cai) -> toan bo bang Python thuan; kich thuoc nho (<= vai tram ma x ~400 nen).
"""
from __future__ import annotations

import hashlib
import math
import re
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Any, Iterable, Sequence

Bar = tuple[datetime, float, float, float, float, float]  # ts, o, h, l, c, v

# ----------------------------------------------------------------------------------------------- tien te
CCYS = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
# cap quy ve USD: ten cap -> (tien te, dau: +1 neu tien te la BASE (EURUSD), -1 neu la QUOTE (USDJPY))
USD_PAIRS: dict[str, tuple[str, int]] = {
    "EURUSD": ("EUR", 1), "GBPUSD": ("GBP", 1), "AUDUSD": ("AUD", 1), "NZDUSD": ("NZD", 1),
    "USDJPY": ("JPY", -1), "USDCHF": ("CHF", -1), "USDCAD": ("CAD", -1),
}
PERIOD_D1_BARS = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}


def _ln(a: float, b: float) -> float | None:
    return math.log(a / b) if a and b and a > 0 and b > 0 else None


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def strength(series: dict[str, Sequence[Bar]], window: int) -> dict[str, Any]:
    """Suc manh 8 tien te tu cac cap quy ve USD. `series`: cap -> nen (cung tf).

    u_X(t) = dau * ln(P_t / P_0) * 100 (USD = 0); diem = (n*u_X - sum(u)) / (n-1) = trung binh phan tram vuot troi so voi cac tien te con lai.
    Truc thoi gian = hop cac ts_open cua cac cap, lay `window+1` moc cuoi; cap thieu gia tai moc dau bi loai (khong dien khong).
    """
    pairs = {p: list(b) for p, b in series.items() if p in USD_PAIRS and len(b) >= 2}
    if not pairs:
        return {"currencies": [], "pairs": [], "missing": sorted(USD_PAIRS), "points": 0, "history_ts": []}
    axis = sorted({b[0] for bars in pairs.values() for b in bars})[-(window + 1):]
    if len(axis) < 2:
        return {"currencies": [], "pairs": [], "missing": sorted(USD_PAIRS), "points": 0, "history_ts": []}
    px: dict[str, list[float | None]] = {}
    for p, bars in pairs.items():
        ts = [b[0] for b in bars]
        vals: list[float | None] = []
        for t in axis:
            i = bisect_right(ts, t) - 1
            vals.append(bars[i][4] if i >= 0 else None)
        if vals[0] is None:        # khong co gia tai moc dau cua cua so -> khong so sanh duoc
            continue
        px[p] = vals
    if not px:
        return {"currencies": [], "pairs": [], "missing": sorted(USD_PAIRS), "points": 0, "history_ts": []}
    ccys = ["USD"] + [USD_PAIRS[p][0] for p in px]
    n = len(ccys)
    hist: dict[str, list[float]] = {c: [] for c in ccys}
    for k in range(len(axis)):
        u = {"USD": 0.0}
        for p, vals in px.items():
            c, sgn = USD_PAIRS[p]
            r = _ln(vals[k], vals[0]) if vals[k] is not None else None
            u[c] = (sgn * r * 100) if r is not None else 0.0
        tot = sum(u.values())
        for c in ccys:
            hist[c].append(round((n * u[c] - tot) / (n - 1), 4) if n > 1 else 0.0)
    out = [{"ccy": c, "score": hist[c][-1], "history": hist[c]} for c in ccys]
    out.sort(key=lambda x: -x["score"])
    for i, x in enumerate(out):
        x["rank"] = i + 1
    ideas = []
    if len(out) >= 2:
        for hi, lo in ((out[0], out[-1]), (out[0], out[-2]), (out[1], out[-1])):
            ideas.append({"strong": hi["ccy"], "weak": lo["ccy"], "gap": round(hi["score"] - lo["score"], 4)})
    return {"currencies": out, "pairs": sorted(px), "missing": sorted(set(USD_PAIRS) - set(px)), "points": len(axis),
            "history_ts": [_iso(t) for t in axis], "ideas": ideas}


def usd_returns(d1: dict[str, Sequence[Bar]], h1: dict[str, Sequence[Bar]], h4: dict[str, Sequence[Bar]]) -> dict[str, dict[str, float | None]]:
    """Ccy -> {ky: ln-return so voi USD (da dao dau)} cho 1h/4h/1d/1w/1m. Thieu du lieu -> None."""
    res: dict[str, dict[str, float | None]] = {"USD": {k: 0.0 for k in ("1h", "4h", "1d", "1w", "1m")}}
    for p, (c, sgn) in USD_PAIRS.items():
        r: dict[str, float | None] = {}
        for key, src, k in (("1h", h1, 1), ("4h", h4, 1), ("1d", d1, 1), ("1w", d1, 5), ("1m", d1, 21)):
            bars = src.get(p) or []
            v = _ln(bars[-1][4], bars[-1 - k][4]) if len(bars) > k else None
            r[key] = sgn * v if v is not None else None
        res[c] = r
    return res


PAIRS28 = ("EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCHF USDCAD EURGBP EURJPY EURCHF EURCAD EURAUD EURNZD GBPJPY GBPCHF GBPCAD GBPAUD GBPNZD "
           "AUDJPY AUDCHF AUDCAD AUDNZD NZDJPY NZDCHF NZDCAD CADJPY CADCHF CHFJPY").split()


def fx_changes(rets: dict[str, dict[str, float | None]]) -> list[dict[str, Any]]:
    """Bang cap x ky (%): 7 cap quy USD + 21 cap cheo suy ra (BASE/QUOTE = exp(u_BASE - u_QUOTE) - 1) theo quy uoc ten cap thi truong."""
    out = []
    for pair in PAIRS28:
        base, quote = pair[:3], pair[3:]
        row: dict[str, Any] = {"pair": pair, "base": base, "quote": quote}
        for key in ("1h", "4h", "1d", "1w", "1m"):
            ra, rb = rets.get(base, {}).get(key), rets.get(quote, {}).get(key)
            row[key] = round((math.exp(ra - rb) - 1) * 100, 4) if ra is not None and rb is not None else None
        out.append(row)
    return out


def cross_rates(last_usd: dict[str, float]) -> dict[str, Any]:
    """Ma tran 8x8 ty gia: hang = tien te CO SO, cot = tien te YET GIA (gia 1 don vi hang tinh bang cot). last_usd: cap USD -> gia."""
    usd_val: dict[str, float] = {"USD": 1.0}
    for p, (c, sgn) in USD_PAIRS.items():
        px = last_usd.get(p)
        if px and px > 0:
            usd_val[c] = px if sgn > 0 else 1.0 / px      # gia 1 don vi tien te tinh bang USD
    mat: list[list[float | None]] = []
    for a in CCYS:
        row = []
        for b in CCYS:
            row.append(None if a == b or a not in usd_val or b not in usd_val else usd_val[a] / usd_val[b])
        mat.append(row)
    return {"ccys": CCYS, "matrix": mat}


# ----------------------------------------------------------------------------------------------- thong ke co ban
def closes(bars: Sequence[Bar]) -> list[float]:
    return [b[4] for b in bars]


def pct_change(bars: Sequence[Bar], k: int, last: float | None = None) -> float | None:
    """% thay doi so voi dong cua k nen truoc (last = gia hien tai neu co, mac dinh dong cua nen cuoi)."""
    if len(bars) <= k:
        return None
    ref = bars[-1 - k][4]
    cur = last if last is not None else bars[-1][4]
    return (cur / ref - 1) * 100 if ref and cur else None


def atr(bars: Sequence[Bar], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        h, lo, pc = bars[i][2], bars[i][3], bars[i - 1][4]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return fmean(trs)


def log_returns(bars: Sequence[Bar]) -> list[tuple[datetime, float]]:
    out = []
    for i in range(1, len(bars)):
        r = _ln(bars[i][4], bars[i - 1][4])
        if r is not None:
            out.append((bars[i][0], r))
    return out


def sma(vals: Sequence[float], n: int) -> float | None:
    return fmean(vals[-n:]) if len(vals) >= n else None


def percentile_rank(sample: Sequence[float], x: float) -> float | None:
    if not sample:
        return None
    return round(100 * sum(1 for s in sample if s <= x) / len(sample), 1)


def ann_factor(symbol: str) -> float:
    return math.sqrt(365 if symbol.startswith("CRYPTO:") else 252)


def pstdev(xs: Sequence[float]) -> float:
    """Do lech chuan tong the bang float 2-pass (R3-11: statistics.pstdev dung Fraction chinh xac -> cham ~100x, chan event loop gateway)."""
    n = len(xs)
    if n < 1:
        raise ValueError("pstdev can it nhat 1 phan tu")
    mu = math.fsum(xs) / n
    return math.sqrt(max(0.0, math.fsum((x - mu) * (x - mu) for x in xs) / n))


def vol_series(rets: Sequence[float], n: int, last: int | None = None) -> list[float]:
    """Do lech chuan truot (n) cua loi suat -> chuoi (khong annualized). `last`: chi tinh `last` cua so cuoi (nguoi goi chi dung phan duoi)."""
    if len(rets) < n:
        return []
    start = n if last is None else max(n, len(rets) + 1 - last)
    return [pstdev(rets[i - n:i]) for i in range(start, len(rets) + 1)]


def spark(bars: Sequence[Bar], n: int = 30) -> list[float]:
    return [round(b[4], 6) for b in bars[-n:]]


def symbol_stats(symbol: str, bars: Sequence[Bar]) -> dict[str, Any] | None:
    """ATR%, do bien dong thuc hien 20 nen (annualized) + phan vi trong 1 nam, xu huong SMA."""
    if len(bars) < 25:
        return None
    c = closes(bars)
    trs = [max(bars[i][2] - bars[i][3], abs(bars[i][2] - bars[i - 1][4]), abs(bars[i][3] - bars[i - 1][4])) for i in range(1, len(bars))]
    atr_hist = []                       # ATR14/gia (%) tai tung nen cua ~1 nam gan nhat (cua so truot O(n))
    run = sum(trs[:13])
    for i in range(13, len(trs)):
        run += trs[i]
        if i >= 14:
            run -= trs[i - 14]
        px = c[i + 1]
        if px:
            atr_hist.append(run / 14 / px * 100)
    atr_hist = atr_hist[-252:]
    atr_pct = atr_hist[-1] if atr_hist else None
    rets = [r for _, r in log_returns(bars)]
    vs = vol_series(rets, 20, last=252)        # chi can 252 cua so cuoi (hist_vol + v20)
    af = ann_factor(symbol)
    v20 = vs[-1] * af * 100 if vs else None
    hist_vol = [x * af * 100 for x in vs[-252:]]
    s20, s50, s200 = sma(c, 20), sma(c, 50), sma(c, 200)
    return {
        "atr_pct": round(atr_pct, 3) if atr_pct is not None else None,
        "atr_rank": percentile_rank(atr_hist, atr_pct) if atr_pct is not None else None,
        "vol20": round(v20, 2) if v20 is not None else None,
        "vol_rank": percentile_rank(hist_vol, v20) if v20 is not None else None,
        "sma20_dist": round((c[-1] / s20 - 1) * 100, 2) if s20 else None,
        "sma50_dist": round((c[-1] / s50 - 1) * 100, 2) if s50 else None,
        "sma200_dist": round((c[-1] / s200 - 1) * 100, 2) if s200 else None,
        "bars": len(bars),
    }


# ----------------------------------------------------------------------------------------------- heatmap / movers
def item_metrics(symbol: str, bars: Sequence[Bar], last: float | None = None) -> dict[str, Any] | None:
    if len(bars) < 2:
        return None
    c = closes(bars)
    cur = last if last else c[-1]
    year = bars[-252:]
    hi = max(b[2] for b in year)
    lo = min(b[3] for b in year)
    ytd_ref = None
    y0 = datetime(bars[-1][0].year, 1, 1, tzinfo=timezone.utc)
    for b in bars:
        if b[0] >= y0:
            break
        ytd_ref = b[4]
    atr_v = atr(bars, 14)
    rets = [r for _, r in log_returns(bars[-21:])]
    sd = pstdev(rets) if len(rets) > 5 else None
    d1 = pct_change(bars, 1, cur)
    last_bar = bars[-1]
    turn = [b[4] * b[5] for b in bars[-20:] if b[5]]
    vols = [b[5] for b in bars[-21:-1] if b[5]]
    rng = (last_bar[2] - last_bar[3]) / last_bar[4] * 100 if last_bar[4] else None
    return {
        "last": cur, "prev": c[-2], "d1": d1, "w1": pct_change(bars, 5, cur), "m1": pct_change(bars, 21, cur),
        "m3": pct_change(bars, 63, cur), "m6": pct_change(bars, 126, cur), "y1": pct_change(bars, 252, cur),
        "ytd": (cur / ytd_ref - 1) * 100 if ytd_ref else None,
        "turnover": fmean(turn) if turn else None,
        "volume": last_bar[5] or None,
        "vol_ratio": (last_bar[5] / fmean(vols)) if vols and last_bar[5] and fmean(vols) else None,
        "atr_pct": atr_v / cur * 100 if atr_v and cur else None,
        "range_pct": rng,
        "z": (math.log(cur / c[-2]) / sd) if sd and c[-2] and cur > 0 else None,
        "high52": hi, "low52": lo,
        "from_high": (cur / hi - 1) * 100 if hi else None,
        "from_low": (cur / lo - 1) * 100 if lo else None,
        "gap": (last_bar[1] / c[-2] - 1) * 100 if c[-2] and last_bar[1] else None,
        "asof": _iso(last_bar[0]),
        "spark": spark(bars, 30),
    }


def rnd(x: Any, d: int = 3) -> Any:
    return round(x, d) if isinstance(x, float) and math.isfinite(x) else (None if isinstance(x, float) else x)


def rnd_obj(o: Any, d: int = 3) -> Any:
    if isinstance(o, dict):
        return {k: (v if k == "spark" else rnd_obj(v, d)) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd_obj(v, d) for v in o]
    return rnd(o, d)


# ----------------------------------------------------------------------------------------------- tuong quan / beta / phan phoi
def _align(a: Sequence[tuple[datetime, float]], b: Sequence[tuple[datetime, float]]) -> tuple[list[float], list[float]]:
    db = {t: v for t, v in b}
    xs, ys = [], []
    for t, v in a:
        w = db.get(t)
        if w is not None:
            xs.append(v)
            ys.append(w)
    return xs, ys


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n < 5:
        return None
    mx, my = fmean(x), fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def _rank(v: Sequence[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def correlation_matrix(rets: dict[str, list[tuple[datetime, float]]], symbols: Sequence[str], window: int, method: str = "pearson") -> dict[str, Any]:
    """Ma tran tuong quan loi suat log tren `window` quan sat CHUNG gan nhat cua tung cap (crypto 7 ngay/tuan, co phieu 5 -> giao nhau theo ngay)."""
    n = len(symbols)
    m: list[list[float | None]] = [[None] * n for _ in range(n)]
    cnt: list[list[int]] = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            if i == j:
                m[i][j], cnt[i][j] = 1.0, len(rets.get(symbols[i], [])[-window:])
                continue
            xs, ys = _align(rets.get(symbols[i], []), rets.get(symbols[j], []))
            xs, ys = xs[-window:], ys[-window:]
            if method == "spearman" and len(xs) >= 5:
                xs, ys = _rank(xs), _rank(ys)
            c = pearson(xs, ys)
            m[i][j] = m[j][i] = round(c, 4) if c is not None else None
            cnt[i][j] = cnt[j][i] = len(xs)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if m[i][j] is not None:
                pairs.append({"a": symbols[i], "b": symbols[j], "corr": m[i][j], "n": cnt[i][j]})
    pairs.sort(key=lambda p: -abs(p["corr"]))
    return {"symbols": list(symbols), "matrix": m, "n_obs": cnt, "top_pairs": pairs[:12], "method": method, "window": window}


def rolling_correlation(a: Sequence[tuple[datetime, float]], b: Sequence[tuple[datetime, float]], window: int, span: int) -> list[dict[str, Any]]:
    db = {t: v for t, v in b}
    common = [(t, v, db[t]) for t, v in a if t in db]
    out = []
    for i in range(max(window, len(common) - span), len(common) + 1):
        seg = common[i - window:i]
        if len(seg) < window:
            continue
        c = pearson([s[1] for s in seg], [s[2] for s in seg])
        if c is not None:
            out.append({"t": _iso(seg[-1][0]), "corr": round(c, 4)})
    return out


def beta(asset: Sequence[tuple[datetime, float]], bench: Sequence[tuple[datetime, float]], window: int) -> dict[str, Any] | None:
    xs, ys = _align(bench, asset)                       # x = benchmark, y = tai san
    xs, ys = xs[-window:], ys[-window:]
    if len(xs) < 20:
        return None
    mx, my = fmean(xs), fmean(ys)
    vx = sum((a - mx) ** 2 for a in xs)
    if vx <= 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    b = cov / vx
    alpha = my - b * mx
    c = pearson(xs, ys)
    return {"beta": round(b, 3), "alpha_daily_pct": round(alpha * 100, 4), "corr": round(c, 3) if c is not None else None,
            "r2": round(c * c, 3) if c is not None else None, "n": len(xs)}


def distribution(rets: Sequence[float], bins: int = 41) -> dict[str, Any] | None:
    n = len(rets)
    if n < 20:
        return None
    mu, sd = fmean(rets), pstdev(rets)
    if sd <= 0:
        return None
    skew = sum(((r - mu) / sd) ** 3 for r in rets) / n
    kurt = sum(((r - mu) / sd) ** 4 for r in rets) / n - 3
    lo, hi = max(min(rets), mu - 5 * sd), min(max(rets), mu + 5 * sd)
    w = (hi - lo) / bins or 1e-9
    h = [0] * bins
    for r in rets:
        k = int((min(max(r, lo), hi - 1e-12) - lo) / w)
        h[min(max(k, 0), bins - 1)] += 1
    srt = sorted(rets)
    q = lambda p: srt[max(0, min(n - 1, int(p * n)))]  # noqa: E731
    tail = [r for r in srt if r <= q(0.05)]
    out_bins = []
    for k in range(bins):
        x0 = lo + k * w
        mid = x0 + w / 2
        normal = n * w * math.exp(-((mid - mu) ** 2) / (2 * sd * sd)) / (sd * math.sqrt(2 * math.pi))
        out_bins.append({"x0": round(x0 * 100, 4), "x1": round((x0 + w) * 100, 4), "n": h[k], "normal": round(normal, 3)})
    return {"n": n, "mean_pct": round(mu * 100, 4), "std_pct": round(sd * 100, 4), "skew": round(skew, 3), "kurtosis": round(kurt, 3),
            "min_pct": round(srt[0] * 100, 3), "max_pct": round(srt[-1] * 100, 3), "p05_pct": round(q(0.05) * 100, 3), "p95_pct": round(q(0.95) * 100, 3),
            "var95_pct": round(-q(0.05) * 100, 3), "es95_pct": round(-fmean(tail) * 100, 3) if tail else None,
            "positive_pct": round(100 * sum(1 for r in rets if r > 0) / n, 1), "bins": out_bins}


# ----------------------------------------------------------------------------------------------- tin tuc: chu de / quan trong
# Tu vung chu de = cua service nlp (services/nlp/config/topics.yaml): DB luu topics/importance da gan san; tu khoa duoi day CHI la du phong
# cho tin chua duoc nlp gan (hoac test). id: (nhan tieng Viet, tu khoa du phong, trong so quan trong 0..2)
TOPICS: dict[str, tuple[str, list[str], int]] = {
    "monetary_policy": ("Chính sách tiền tệ", ["fed ", "fomc", "powell", "lãi suất", "lai suat", "interest rate", "rate cut", "rate hike", "ecb", "boj", "boe", "ngân hàng trung ương", "central bank", "nhnn"], 2),
    "inflation": ("Lạm phát", ["cpi", "pce", "ppi", "lạm phát", "lam phat", "inflation", "giá tiêu dùng"], 2),
    "jobs": ("Việc làm", ["nonfarm", "payroll", "unemployment", "thất nghiệp", "việc làm", "jobless"], 2),
    "growth": ("Tăng trưởng", ["gdp", "tăng trưởng", "pmi", "bán lẻ", "retail sales", "recession", "suy thoái"], 1),
    "geopolitics": ("Địa chính trị", ["chiến sự", "war", "trừng phạt", "sanction", "trung đông", "ukraine", "israel", "iran", "nga "], 2),
    "trade_tariffs": ("Thương mại & thuế quan", ["tariff", "thuế quan", "trade war", "xuất khẩu", "nhập khẩu"], 1),
    "energy": ("Năng lượng", ["dầu", "oil", "opec", "brent", "wti", "khí đốt", "natural gas", "xăng"], 1),
    "precious_metals": ("Kim loại quý", ["vàng", "gold", "bạc ", "silver", "xau"], 1),
    "corporate": ("Doanh nghiệp", ["lợi nhuận", "earnings", "doanh thu", "revenue", "m&a", "cổ tức", "dividend"], 0),
    "banking_credit": ("Ngân hàng & tín dụng", ["ngân hàng", "tín dụng", "nợ xấu", "bank", "trái phiếu", "bond", "cho vay"], 0),
    "sovereign_rating": ("Xếp hạng tín nhiệm", ["xếp hạng tín nhiệm", "credit rating", "moody", "fitch", "s&p global"], 1),
    "fx_markets": ("Ngoại hối", ["tỷ giá", "usd", "dollar", "đô la", "yên", "euro", "forex", "ngoại hối", "dxy"], 1),
    "equities": ("Cổ phiếu & chỉ số", ["wall street", "dow jones", "nasdaq", "s&p 500", "vn-index", "vnindex", "chứng khoán", "cổ phiếu", "khối ngoại"], 1),
    "crypto": ("Tiền ảo", ["bitcoin", "btc", "ethereum", "crypto", "tiền ảo", "tiền số", "stablecoin", "altcoin"], 1),
    "real_estate": ("Bất động sản", ["bất động sản", "nhà đất", "real estate", "housing", "căn hộ"], 0),
    "regulation_policy": ("Chính sách & quy định", ["quy định", "nghị định", "thông tư", "luật", "regulation", "chính phủ", "bộ tài chính"], 0),
    "tech_ai": ("Công nghệ & AI", ["trí tuệ nhân tạo", "chip", "bán dẫn", "semiconductor", "công nghệ", "openai", " ai "], 0),
}
IMPORTANCE_LEVEL = {"low": 1, "med": 2, "high": 3}


def _norm(s: str) -> str:
    return (s or "").lower()


def classify_news(title: str, summary: str | None, symbols: Sequence[str] | None, sentiment: float | None,
                  topics: Sequence[str] | None = None, importance: str | None = None) -> dict[str, Any]:
    """topics/importance tu nlp neu co (importance low|med|high -> 1..3); thieu -> du phong tu khoa + heuristic. importance: 0 = khong ro."""
    text = " " + _norm(title) + " " + _norm(summary or "")[:600] + " "
    tps = [t for t in (topics or []) if t in TOPICS]
    if not tps and not topics:
        tps = [tid for tid, (_, kws, _) in TOPICS.items() if any(k in text for k in kws)][:3]
    lvl = IMPORTANCE_LEVEL.get(importance or "")
    if lvl is None:
        score = max([TOPICS[t][2] for t in tps], default=0)
        if sentiment is not None and abs(sentiment) >= 0.75:
            score += 1
        if symbols and len(symbols) >= 2:
            score += 1
        if re.search(r"khẩn|breaking|nóng|flash|bất ngờ|surprise|sụp|crash|đỉnh lịch sử|record high|plunge|soar", text):
            score += 1
        lvl = 3 if score >= 4 else 2 if score >= 3 else 1 if score >= 1 else 0
    return {"topics": tps, "importance": lvl}


def news_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:16]


_WORD = re.compile(r"[\w]+", re.UNICODE)
_STOP = set("và của là các cho với trong một những được này khi đã sẽ không có người từ cũng như the of to in for on and a is at by with from as that this its it be are was".split())


def tokens(s: str) -> set[str]:
    return {w for w in _WORD.findall(_norm(s)) if len(w) > 2 and w not in _STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ----------------------------------------------------------------------------------------------- nhip thi truong
def pulse_score(parts: Iterable[float | None]) -> float | None:
    v = [p for p in parts if p is not None]
    return round(fmean(v), 1) if v else None


def label_level(x: float | None, labels: Sequence[str]) -> str | None:
    if x is None:
        return None
    return labels[min(len(labels) - 1, int(x / (100 / len(labels))))]
