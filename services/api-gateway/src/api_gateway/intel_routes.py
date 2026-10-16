"""`GET /v1/intel/*` — thong tin thi truong tong hop (chi doc, tinh o may chu tu bang bars/quotes/news/calendar qua ts_ro, cache ngan).

  strength  suc manh 8 tien te (H1/H4/D1)         fx          bang cap x ky + ma tran ty gia cheo
  heatmap   ban do nhiet theo nhom tai san        movers      top tang/giam/bien dong/khoi luong/52w/gap
  stats     ATR%, do bien dong, beta               correlation tuong quan (+ rolling), distribution phan phoi loi suat
  pulse     nhip thi truong tong hop               news(+topics,related) tin tuc terminal
  calendar/indicators|history  lich su chi so      cot         vi the dau co lon (hang tuan)

Tat ca la THONG KE tren du lieu gia/tin da luu, khong phai khuyen nghi. Khong tra ten nguon (middleware hide_sources van scrub them).
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from statistics import fmean, median
from typing import Annotated, Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from tscommon import assets

from . import intel_calc as C
from . import intel_data as D

SYMBOL_RE = r"^[A-Za-z0-9:._\-]{1,32}$"
_SYM = re.compile(SYMBOL_RE)
SKIP_PREFIX = ("FRED:",)                      # chuoi lai suat/chi so vi mo: khong dua vao heatmap/movers theo % gia
SECTOR_GROUP = "ETF ngành Mỹ"
GROUPS: dict[str, Callable[[assets.AssetInfo], bool]] = {
    "all": lambda i: i.cls != assets.OTHER,
    "crypto": lambda i: i.cls == "crypto",
    "etf": lambda i: i.cls in ("etf", "index") and i.group != SECTOR_GROUP,
    "sector": lambda i: i.group == SECTOR_GROUP,
    "commodity": lambda i: i.cls in ("metal", "commodity"),
    "forex": lambda i: i.cls == "forex",
    "us_stock": lambda i: i.cls == "stock_us",
    "bond": lambda i: i.cls == "bond",
    "vn": lambda i: i.cls == "stock_vn",
}
GROUP_PATTERN = "^(" + "|".join(GROUPS) + ")$"
PERIODS = {"1d": "d1", "1w": "w1", "1m": "m1", "3m": "m3", "6m": "m6", "ytd": "ytd", "1y": "y1"}
PERIOD_PATTERN = "^(" + "|".join(PERIODS) + ")$"
INTRA = {"1h": ("H1", 1), "4h": ("H4", 1)}


COT_CONTRACTS = {  # symbol theo cap -> (ten hop dong ky han de hien thi, dao chieu so voi cap)
    "EURUSD": ("Euro", False), "GBPUSD": ("Bảng Anh", False), "AUDUSD": ("Đô la Úc", False), "NZDUSD": ("Đô la New Zealand", False),
    "USDJPY": ("Yên Nhật", True), "USDCAD": ("Đô la Canada", True), "USDCHF": ("Franc Thụy Sĩ", True),
    "XAUUSD": ("Vàng", False), "XAGUSD": ("Bạc", False), "USOIL": ("Dầu WTI", False), "US:SPX": ("S&P 500 E-mini", False), "DXY": ("Chỉ số Đô la Mỹ", False),
}


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def _symbols_arg(v: str | None, mx: int = 40) -> list[str]:
    syms = _csv(v)
    if len(syms) > mx:
        raise HTTPException(422, f"Tối đa {mx} mã")
    for s in syms:
        if not _SYM.match(s):
            raise HTTPException(422, f"Mã không hợp lệ: {s[:40]}")
    return syms


def _label(symbol: str) -> str:
    return symbol.split(":", 1)[1] if ":" in symbol else symbol


def _crypto_label(symbol: str) -> str:
    s = _label(symbol)
    return s[:-4] if symbol.startswith("CRYPTO:") and s.endswith("USDT") else s


def _meta(symbol: str) -> dict[str, Any]:
    i = assets.asset_info(symbol)
    return {"symbol": symbol, "label": _crypto_label(symbol), "name": i.name, "class": i.cls, "group": i.group}


async def _universe(repo, group: str) -> tuple[dict[str, list], dict[str, dict], datetime]:
    now = datetime.now(timezone.utc)
    ds, qs = await asyncio.gather(D.daily(repo, 400), D.quotes(repo))
    sel = {s: b for s, b in ds.items() if not s.startswith(SKIP_PREFIX) and GROUPS[group](assets.asset_info(s)) and len(b) >= 2}
    return sel, qs, now


def _metrics_for(universe: dict[str, list], qs: dict[str, dict], now: datetime) -> dict[str, dict]:
    out = {}
    for s, bs in universe.items():
        eff, px = D.with_quote(bs, qs.get(s), now)
        m = C.item_metrics(s, eff, px)
        if m:
            out[s] = m
    return out


def register_intel_routes(api: APIRouter, get_repo: Callable) -> None:
    # ------------------------------------------------------------------------------------------ suc manh tien te
    @api.get("/intel/strength", tags=["intel"], summary="Sức mạnh 8 tiền tệ chính (H1/H4/D1) tính từ các cặp quy về USD")
    async def intel_strength(request: Request, tf: Annotated[str, Query(pattern="^(H1|H4|D1)$")] = "D1",
                             window: Annotated[int | None, Query(ge=2, le=250, description="Số nến của cửa sổ so sánh")] = None):
        repo = get_repo(request)
        win = window or {"H1": 24, "H4": 30, "D1": 5}[tf]
        days = {"H1": 14, "H4": 40, "D1": 400}[tf]

        async def build():
            ser = await D.intraday(repo, tf, days, list(C.USD_PAIRS)) if tf != "D1" else await D.daily(repo, days, list(C.USD_PAIRS))
            r = C.strength(ser, win)
            return {"tf": tf, "window": win, "as_of": r["history_ts"][-1] if r["history_ts"] else None, **r,
                    "coverage": f"{len(r['currencies'])}/8", "disclaimer": "Thống kê biến động giá, không phải khuyến nghị."}
        return await D.cached(("strength", id(repo), tf, win), 20, build)

    @api.get("/intel/fx", tags=["intel"], summary="Heatmap cặp × khung (28 cặp) và ma trận tỷ giá chéo 8×8")
    async def intel_fx(request: Request):
        repo = get_repo(request)

        async def build():
            pairs = list(C.USD_PAIRS)
            d1, h1, h4, qs = await asyncio.gather(D.daily(repo, 60, pairs), D.intraday(repo, "H1", 10, pairs), D.intraday(repo, "H4", 30, pairs), D.quotes(repo))
            now = datetime.now(timezone.utc)
            rets = C.usd_returns(d1, h1, h4)
            last: dict[str, float] = {}
            asof: dict[str, str] = {}
            for p in pairs:
                bs = d1.get(p) or []
                if not bs:
                    continue
                eff, px = D.with_quote(bs, qs.get(p), now)
                last[p] = px or eff[-1][4]
                asof[p] = C._iso(qs[p]["ts"] if px else bs[-1][0])
            cov = {k: sorted(p for p in pairs if (src.get(p) or [])) for k, src in (("1h", h1), ("4h", h4), ("1d", d1))}
            return {"periods": ["1h", "4h", "1d", "1w", "1m"], "rows": C.fx_changes(rets), "cross": C.cross_rates(last), "asof": asof,
                    "coverage": cov, "as_of": max(asof.values()) if asof else None}
        out = await D.cached(("fx", id(repo)), 20, build)
        cross = {**out["cross"], "matrix": [[(round(x, 8) if x is not None else None) for x in row] for row in out["cross"]["matrix"]]}   # giữ độ chính xác cho quy đổi (JPY ~0.0064)
        return {**C.rnd_obj({k: v for k, v in out.items() if k != "cross"}, 5), "cross": cross}

    # ------------------------------------------------------------------------------------------ heatmap / movers
    @api.get("/intel/heatmap", tags=["intel"], summary="Bản đồ nhiệt theo nhóm tài sản: % thay đổi + kích thước theo giá trị giao dịch 20 phiên")
    async def intel_heatmap(request: Request, group: Annotated[str, Query(pattern=GROUP_PATTERN)] = "crypto",
                            period: Annotated[str, Query(pattern=PERIOD_PATTERN)] = "1d"):
        repo = get_repo(request)

        async def build():
            uni, qs, now = await _universe(repo, group)
            mets = _metrics_for(uni, qs, now)
            key = PERIODS[period]
            items = []
            for s, m in mets.items():
                items.append({**_meta(s), "change_pct": m.get(key), "d1": m["d1"], "last": m["last"], "turnover": m["turnover"], "volume": m["volume"],
                              "asof": m["asof"], "spark": m["spark"]})
            items = [i for i in items if i["change_pct"] is not None]
            items.sort(key=lambda i: -(i["turnover"] or 0))
            vals = [i["change_pct"] for i in items]
            return {"group": group, "period": period, "size_basis": "turnover_20d", "count": len(items), "items": items,
                    "summary": {"up": sum(1 for v in vals if v > 0), "down": sum(1 for v in vals if v < 0), "avg": fmean(vals) if vals else None,
                                "median": median(vals) if vals else None},
                    "as_of": max((i["asof"] for i in items), default=None)}
        return C.rnd_obj(await D.cached(("heat", id(repo), group, period), 30, build), 3)

    @api.get("/intel/movers", tags=["intel"], summary="Top tăng/giảm/biến động/khối lượng, gần đỉnh-đáy 52 tuần, gap")
    async def intel_movers(request: Request, group: Annotated[str, Query(pattern=GROUP_PATTERN)] = "all",
                           period: Annotated[str, Query(pattern="^(1h|4h|1d|1w|1m)$")] = "1d",
                           limit: Annotated[int, Query(ge=3, le=50)] = 10):
        repo = get_repo(request)

        async def build():
            uni, qs, now = await _universe(repo, group)
            mets = _metrics_for(uni, qs, now)
            rows = []
            covered = len(mets)
            if period in INTRA:
                tf, k = INTRA[period]
                ib = await D.intraday(repo, tf, 8 if tf == "H1" else 30, list(uni))
                chg = {}
                for s, bs in ib.items():
                    if len(bs) > k and bs[-1 - k][4]:
                        chg[s] = (bs[-1][4] / bs[-1 - k][4] - 1) * 100
                covered = len(chg)
                for s, v in chg.items():
                    m = mets.get(s)
                    rows.append({**_meta(s), "change_pct": v, "last": ib[s][-1][4], "volume": m["volume"] if m else None, "vol_ratio": m["vol_ratio"] if m else None,
                                 "atr_pct": m["atr_pct"] if m else None, "range_pct": m["range_pct"] if m else None, "z": None,
                                 "from_high": m["from_high"] if m else None, "from_low": m["from_low"] if m else None, "gap": None,
                                 "spark": m["spark"] if m else [], "asof": C._iso(ib[s][-1][0])})
            else:
                key = {"1d": "d1", "1w": "w1", "1m": "m1"}[period]
                for s, m in mets.items():
                    rows.append({**_meta(s), "change_pct": m[key], "last": m["last"], "volume": m["volume"], "vol_ratio": m["vol_ratio"], "atr_pct": m["atr_pct"],
                                 "range_pct": m["range_pct"], "z": m["z"], "from_high": m["from_high"], "from_low": m["from_low"], "gap": m["gap"],
                                 "spark": m["spark"], "asof": m["asof"]})
            have = [r for r in rows if r["change_pct"] is not None]

            def top(lst, key, rev=True, flt=None):
                src = [r for r in lst if r.get(key) is not None and (flt is None or flt(r))]
                return sorted(src, key=lambda r: r[key], reverse=rev)[:limit]
            daily_rows = [{**_meta(s), "change_pct": m["d1"], "last": m["last"], "vol_ratio": m["vol_ratio"],
                           "atr_pct": m["atr_pct"], "range_pct": m["range_pct"], "z": m["z"], "from_high": m["from_high"], "from_low": m["from_low"], "gap": m["gap"],
                           "spark": m["spark"], "asof": m["asof"]} for s, m in mets.items()]
            return {
                "group": group, "period": period, "count": len(have), "universe": len(mets), "covered": covered, "as_of": max((r["asof"] for r in have), default=None),
                "gainers": top(have, "change_pct", True, lambda r: r["change_pct"] > 0),
                "losers": top(have, "change_pct", False, lambda r: r["change_pct"] < 0),
                "volatile": sorted([r for r in daily_rows if r["z"] is not None], key=lambda r: -abs(r["z"]))[:limit],
                "range": top(daily_rows, "range_pct"),
                "volume": top(daily_rows, "vol_ratio", True, lambda r: r["vol_ratio"] and r["class"] not in ("forex", "bond")),
                "near_high": sorted([r for r in daily_rows if r["from_high"] is not None], key=lambda r: -r["from_high"])[:limit],
                "near_low": sorted([r for r in daily_rows if r["from_low"] is not None], key=lambda r: r["from_low"])[:limit],
                "gaps": sorted([r for r in daily_rows if r["gap"] is not None and abs(r["gap"]) >= 0.3 and r["class"] in ("etf", "index", "stock_us", "stock_vn", "metal", "commodity")],
                               key=lambda r: -abs(r["gap"]))[:limit],
                "new_high": sum(1 for m in mets.values() if m["from_high"] is not None and m["from_high"] >= -0.01),
                "new_low": sum(1 for m in mets.values() if m["from_low"] is not None and m["from_low"] <= 0.01),
                "note": "52 tuần = 252 phiên gần nhất có dữ liệu; gap = giá mở cửa so với đóng cửa phiên trước; z = biến động hôm nay chuẩn hoá theo độ lệch chuẩn 20 phiên.",
            }
        return C.rnd_obj(await D.cached(("movers", id(repo), group, period, limit), 30, build), 3)

    # ------------------------------------------------------------------------------------------ thong ke rui ro
    @api.get("/intel/stats", tags=["intel"], summary="ATR%, độ biến động thực hiện 20 phiên (+phân vị 1 năm), khoảng cách SMA, beta so với benchmark")
    async def intel_stats(request: Request, group: Annotated[str, Query(pattern=GROUP_PATTERN)] = "all",
                          benchmark: Annotated[str, Query(pattern=SYMBOL_RE)] = "US:SPY",
                          window: Annotated[int, Query(ge=20, le=250)] = 60):
        repo = get_repo(request)

        async def build():
            uni, qs, now = await _universe(repo, group)
            ds = await D.daily(repo, 400)
            bench = ds.get(benchmark)
            brets = C.log_returns(bench) if bench else []

            def calc() -> list[dict]:            # CPU thuần Python -> chạy ở thread, không chặn event loop (R3-11)
                items = []
                for s, bs in uni.items():
                    eff, _ = D.with_quote(bs, qs.get(s), now)
                    st = C.symbol_stats(s, eff)
                    if not st:
                        continue
                    b = C.beta(C.log_returns(eff), brets, window) if brets and s != benchmark else None
                    items.append({**_meta(s), **st, "beta": b["beta"] if b else None, "corr_bench": b["corr"] if b else None, "beta_n": b["n"] if b else None})
                return items
            items = await asyncio.to_thread(calc)
            return {"group": group, "benchmark": benchmark if bench else None, "window": window, "count": len(items), "items": items}
        return await D.cached(("stats", id(repo), group, benchmark, window), 60, build)

    @api.get("/intel/correlation", tags=["intel"], summary="Ma trận tương quan lợi suất log của danh sách mã được chọn")
    async def intel_correlation(request: Request, symbols: Annotated[str | None, Query(description="CSV mã; trống = rổ mặc định đa tài sản")] = None,
                                window: Annotated[int, Query(ge=10, le=500)] = 60,
                                method: Annotated[str, Query(pattern="^(pearson|spearman)$")] = "pearson"):
        repo = get_repo(request)
        syms = _symbols_arg(symbols, 40) or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US:SPY", "US:QQQ", "US:TLT", "US:GLD", "US:USO", "CRYPTO:BTCUSDT", "CRYPTO:ETHUSDT", "VN:FPT"]
        ds = await D.daily(repo, 700, syms)
        have = [s for s in syms if len(ds.get(s, [])) >= 12]
        rets = {s: C.log_returns(ds[s]) for s in have}
        r = C.correlation_matrix(rets, have, window, method)
        r["missing"] = [s for s in syms if s not in have]
        r["labels"] = {s: _crypto_label(s) for s in syms}
        return r

    @api.get("/intel/correlation/rolling", tags=["intel"], summary="Tương quan lăn giữa 2 mã")
    async def intel_rolling(request: Request, a: Annotated[str, Query(pattern=SYMBOL_RE)], b: Annotated[str, Query(pattern=SYMBOL_RE)],
                            window: Annotated[int, Query(ge=10, le=250)] = 30, span: Annotated[int, Query(ge=20, le=700)] = 250):
        repo = get_repo(request)
        ds = await D.daily(repo, 900, [a, b])
        if a not in ds or b not in ds:
            raise HTTPException(404, "Thiếu dữ liệu cho một trong hai mã")
        ser = C.rolling_correlation(C.log_returns(ds[a]), C.log_returns(ds[b]), window, span)
        vals = [x["corr"] for x in ser]
        return {"a": a, "b": b, "window": window, "series": ser, "latest": vals[-1] if vals else None,
                "avg": round(fmean(vals), 3) if vals else None, "min": min(vals) if vals else None, "max": max(vals) if vals else None}

    @api.get("/intel/distribution", tags=["intel"], summary="Phân phối lợi suất ngày của 1 mã (histogram, độ lệch, kurtosis, VaR/ES lịch sử)")
    async def intel_distribution(request: Request, symbol: Annotated[str, Query(pattern=SYMBOL_RE)],
                                 window: Annotated[int, Query(ge=30, le=1500)] = 250, bins: Annotated[int, Query(ge=11, le=81)] = 41):
        repo = get_repo(request)
        ds = await D.daily(repo, int(window * 1.6) + 30, [symbol])
        bs = ds.get(symbol)
        if not bs:
            raise HTTPException(404, "Không có dữ liệu cho mã này")
        rets = [r for _, r in C.log_returns(bs)][-window:]
        dist = C.distribution(rets, bins)
        if not dist:
            raise HTTPException(404, "Chưa đủ dữ liệu để dựng phân phối")
        return {"symbol": symbol, **_meta(symbol), "window": window, **dist, "disclaimer": "Thống kê lịch sử; không dự báo tương lai."}

    # ------------------------------------------------------------------------------------------ nhip thi truong
    @api.get("/intel/pulse", tags=["intel"], summary="Market Pulse: độ biến động, độ rộng, xu hướng theo lớp tài sản, tâm lý tin tức")
    async def intel_pulse(request: Request):
        repo = get_repo(request)

        async def build():
            now = datetime.now(timezone.utc)
            ds, qs = await asyncio.gather(D.daily(repo, 400), D.quotes(repo))
            per: dict[str, dict[str, Any]] = {}
            stats: dict[str, dict] = {}

            def calc() -> None:                  # CPU thuần Python -> thread (R3-11)
                for s, bs in ds.items():
                    if s.startswith(SKIP_PREFIX) or len(bs) < 25:
                        continue
                    cls = assets.asset_info(s).cls
                    if cls == assets.OTHER:
                        continue
                    eff, px = D.with_quote(bs, qs.get(s), now)
                    m = C.item_metrics(s, eff, px)
                    st = C.symbol_stats(s, eff)
                    if not m or not st:
                        continue
                    per.setdefault(cls, {})[s] = {**m, **st}
                    stats[s] = {**m, **st}
            await asyncio.to_thread(calc)
            classes = []
            cls_names = {c["class"]: c["name"] for c in assets.class_infos()}
            for cls, rows in per.items():
                vals = list(rows.values())
                n = len(vals)
                above = lambda k: round(100 * sum(1 for v in vals if v.get(k) is not None and v[k] > 0) / max(1, sum(1 for v in vals if v.get(k) is not None)), 1)  # noqa: E731
                classes.append({
                    "class": cls, "name": cls_names.get(cls, cls), "n": n,
                    "adv": sum(1 for v in vals if (v["d1"] or 0) > 0), "dec": sum(1 for v in vals if (v["d1"] or 0) < 0),
                    "above20": above("sma20_dist"), "above50": above("sma50_dist"), "above200": above("sma200_dist"),
                    "new_high": sum(1 for v in vals if v["from_high"] is not None and v["from_high"] >= -0.01),
                    "new_low": sum(1 for v in vals if v["from_low"] is not None and v["from_low"] <= 0.01),
                    "avg_d1": fmean([v["d1"] for v in vals if v["d1"] is not None]) if any(v["d1"] is not None for v in vals) else None,
                    "avg_w1": fmean([v["w1"] for v in vals if v["w1"] is not None]) if any(v["w1"] is not None for v in vals) else None,
                    "avg_m1": fmean([v["m1"] for v in vals if v["m1"] is not None]) if any(v["m1"] is not None for v in vals) else None,
                    "avg_vol_rank": round(fmean([v["vol_rank"] for v in vals if v["vol_rank"] is not None]), 1) if any(v["vol_rank"] is not None for v in vals) else None,
                })
            classes.sort(key=lambda c: assets.CLASSES.index(c["class"]) if c["class"] in assets.CLASSES else 99)
            # do bien dong kieu VIX: vol thuc hien 20 phien (annualized) cua benchmark + phan vi 1 nam
            bench_vol = []
            for s, lab in (("US:SPY", "S&P 500"), ("US:QQQ", "Nasdaq 100"), ("CRYPTO:BTCUSDT", "Bitcoin"), ("CRYPTO:ETHUSDT", "Ethereum"), ("EURUSD", "EUR/USD"),
                           ("USDJPY", "USD/JPY"), ("XAUUSD", "Vàng"), ("US:TLT", "Trái phiếu 20+ năm"), ("US:USO", "Dầu WTI")):
                st = stats.get(s)
                if st and st.get("vol20") is not None:
                    bench_vol.append({"symbol": s, "label": lab, "vol20": st["vol20"], "rank": st["vol_rank"], "atr_pct": st["atr_pct"]})
            vol_idx = C.pulse_score(b["rank"] for b in bench_vol)
            spy = stats.get("US:SPY")
            # tin tuc 24h
            rows = await D.news_rows(repo, now - timedelta(hours=48), None, None, [], 1500)
            cur = [r for r in rows if r["ts"] >= now - timedelta(hours=24)]
            prev = [r for r in rows if r["ts"] < now - timedelta(hours=24)]
            sent = lambda lst: (fmean([r["sentiment"] for r in lst if r.get("sentiment") is not None]) if any(r.get("sentiment") is not None for r in lst) else None)  # noqa: E731
            tcount: dict[str, int] = {}
            for r in cur:
                for t in C.classify_news(r["title"], r.get("summary"), r.get("symbols"), r.get("sentiment"), r.get("topics"), r.get("importance"))["topics"]:
                    tcount[t] = tcount.get(t, 0) + 1
            news = {"n_24h": len(cur), "n_prev": len(prev), "avg": round(sent(cur), 3) if sent(cur) is not None else None,
                    "avg_prev": round(sent(prev), 3) if sent(prev) is not None else None,
                    "pos": sum(1 for r in cur if (r.get("sentiment") or 0) > 0.15), "neg": sum(1 for r in cur if (r.get("sentiment") or 0) < -0.15),
                    "topics": [{"id": t, "name": C.TOPICS[t][0], "n": n} for t, n in sorted(tcount.items(), key=lambda x: -x[1])[:6]]}
            # chi so khau vi rui ro 0..100 (tham khao): do rong co phieu/ETF + crypto, tam ly tin, 1 - bien dong, xu huong thang cua S&P
            eq = [c for c in classes if c["class"] in ("stock_us", "etf", "index")]
            cr = next((c for c in classes if c["class"] == "crypto"), None)
            parts = {
                "breadth_equity": fmean([c["above50"] for c in eq]) if eq else None,
                "breadth_crypto": cr["above50"] if cr else None,
                "news": (news["avg"] + 1) * 50 if news["avg"] is not None else None,
                "calm": 100 - vol_idx if vol_idx is not None else None,
                "trend": max(0, min(100, ((spy["m1"] or 0) + 5) * 10)) if spy and spy.get("m1") is not None else None,
            }
            score = C.pulse_score(parts.values())
            return {"as_of": now.isoformat().replace("+00:00", "Z"), "classes": classes, "volatility": {"index": vol_idx, "items": bench_vol,
                    "label": C.label_level(vol_idx, ["Rất thấp", "Thấp", "Vừa", "Cao", "Rất cao"]), "spy_vol20": spy["vol20"] if spy else None},
                    "news": news, "appetite": {"score": score, "parts": {k: (round(v, 1) if v is not None else None) for k, v in parts.items()},
                    "label": C.label_level(score, ["Rất thận trọng", "Thận trọng", "Trung lập", "Lạc quan", "Rất lạc quan"])},
                    "disclaimer": "Chỉ số tổng hợp mang tính tham khảo, không phải khuyến nghị đầu tư."}
        return C.rnd_obj(await D.cached(("pulse", id(repo)), 60, build), 3)

    # ------------------------------------------------------------------------------------------ tin tuc
    def _news_item(r: dict, with_summary: bool = True) -> dict:
        cls = C.classify_news(r["title"], r.get("summary"), r.get("symbols"), r.get("sentiment"), r.get("topics"), r.get("importance"))
        out = {"id": C.news_id(r["url"]), "url": r["url"], "title": r["title"], "ts": r["ts"], "lang": r.get("lang"),
               "symbols": list(r.get("symbols") or []), "sentiment": r.get("sentiment"), "sentiment_label": r.get("sentiment_label"), **cls}
        if with_summary:
            out["summary"] = (r.get("summary") or "")[:1200] or None
        return out

    @api.get("/intel/news", tags=["intel"], summary="Terminal tin tức: tìm toàn văn, lọc mã/chủ đề/mức quan trọng/cảm xúc, phân trang theo thời gian")
    async def intel_news(request: Request, q: Annotated[str | None, Query(max_length=120)] = None,
                         symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None,
                         topic: Annotated[str | None, Query(description="CSV chủ đề")] = None,
                         min_importance: Annotated[int, Query(ge=0, le=3)] = 0,
                         sentiment: Annotated[str | None, Query(pattern="^(pos|neg|neu)$")] = None,
                         lang: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
                         hours: Annotated[int, Query(ge=1, le=24 * 365 * 15)] = 72,
                         before: datetime | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 60):
        repo = get_repo(request)
        now = datetime.now(timezone.utc)
        words = [w for w in re.split(r"\s+", (q or "").strip()) if w][:6]
        wanted = set(_csv(topic))
        if wanted - set(C.TOPICS):
            raise HTTPException(422, "Chủ đề không hợp lệ")
        rows = await D.news_rows(repo, now - timedelta(hours=hours), before, symbol, words, 800)
        out = []
        for r in rows:
            if lang and r.get("lang") != lang:
                continue
            s = r.get("sentiment")
            if sentiment == "pos" and not (s is not None and s > 0.15) or sentiment == "neg" and not (s is not None and s < -0.15) \
                    or sentiment == "neu" and not (s is not None and -0.15 <= s <= 0.15):
                continue
            it = _news_item(r)
            if it["importance"] < min_importance or (wanted and not wanted & set(it["topics"])):
                continue
            out.append(it)
            if len(out) >= limit:
                break
        nxt = out[-1]["ts"] if len(out) >= limit else None
        return {"items": out, "count": len(out), "next_before": nxt, "scanned": len(rows), "as_of": now}

    @api.get("/intel/news/topics", tags=["intel"], summary="Thống kê chủ đề tin trong N giờ gần nhất (số tin, cảm xúc trung bình)")
    async def intel_news_topics(request: Request, hours: Annotated[int, Query(ge=1, le=720)] = 24):
        repo = get_repo(request)
        now = datetime.now(timezone.utc)

        async def build():
            rows = await D.news_rows(repo, now - timedelta(hours=hours), None, None, [], 1500)
            agg: dict[str, list] = {t: [] for t in C.TOPICS}
            sym: dict[str, int] = {}
            for r in rows:
                it = _news_item(r, False)
                for t in it["topics"]:
                    agg[t].append(r.get("sentiment"))
                for s in it["symbols"]:
                    sym[s] = sym.get(s, 0) + 1
            topics = []
            for t, lst in agg.items():
                v = [x for x in lst if x is not None]
                if lst:
                    topics.append({"id": t, "name": C.TOPICS[t][0], "n": len(lst), "sentiment": round(fmean(v), 3) if v else None})
            topics.sort(key=lambda x: -x["n"])
            return {"hours": hours, "total": len(rows), "topics": topics,
                    "symbols": [{"symbol": s, "label": _crypto_label(s), "n": n} for s, n in sorted(sym.items(), key=lambda x: -x[1])[:20]]}
        return await D.cached(("ntopics", id(repo), hours), 30, build)

    @api.get("/intel/news/related", tags=["intel"], summary="Tin liên quan: cùng mã/chủ đề, tiêu đề tương tự")
    async def intel_news_related(request: Request, url: Annotated[str, Query(min_length=8, max_length=1000)], limit: Annotated[int, Query(ge=1, le=20)] = 8):
        repo = get_repo(request)
        base = await D.news_by_url(repo, url)
        if not base:
            raise HTTPException(404, "Không tìm thấy tin")
        now = datetime.now(timezone.utc)
        rows = await D.news_rows(repo, base["ts"] - timedelta(days=14), None, None, [], 1200)
        bt = C.tokens(base["title"])
        bsym = set(base.get("symbols") or [])
        btop = set(C.classify_news(base["title"], base.get("summary"), base.get("symbols"), base.get("sentiment"), base.get("topics"), base.get("importance"))["topics"])
        scored = []
        for r in rows:
            if r["url"] == url:
                continue
            it = _news_item(r, False)
            sc = 2.2 * C.jaccard(bt, C.tokens(r["title"])) + 0.6 * len(bsym & set(it["symbols"])) + 0.25 * len(btop & set(it["topics"]))
            sc -= min(1.0, abs((r["ts"] - base["ts"]).total_seconds()) / (14 * 86400)) * 0.15
            if sc >= 0.5:
                scored.append((sc, it))
        scored.sort(key=lambda x: -x[0])
        symbols = [{"symbol": s, "label": _crypto_label(s)} for s in sorted(bsym)]
        return {"base": _news_item(base), "related": [{**it, "score": round(sc, 2)} for sc, it in scored[:limit]], "symbols": symbols, "as_of": now}

    # ------------------------------------------------------------------------------------------ lich kinh te: lich su chi so
    @api.get("/intel/calendar/indicators", tags=["intel"], summary="Chỉ số kinh tế lặp lại (≥2 lần) để xem lịch sử thực tế/dự báo/kỳ trước")
    async def intel_cal_indicators(request: Request):
        repo = get_repo(request)
        rows = await D.cached(("calind", id(repo)), 120, lambda: D.calendar_indicators(repo))
        return {"items": [{**r, "key": f"{r.get('country') or ''}|{r['title']}"} for r in rows], "count": len(rows)}

    @api.get("/intel/calendar/history", tags=["intel"], summary="Lịch sử 1 chỉ số: thực tế / dự báo / kỳ trước theo thời gian")
    async def intel_cal_history(request: Request, title: Annotated[str, Query(min_length=2, max_length=200)],
                                country: Annotated[str | None, Query(max_length=8)] = None, limit: Annotated[int, Query(ge=2, le=120)] = 36):
        repo = get_repo(request)
        rows = await D.calendar_history(repo, title, country or None, limit)
        if not rows:
            raise HTTPException(404, "Không có lịch sử cho chỉ số này")
        rows = sorted(rows, key=lambda r: r["ts"])

        def num(s):
            if s is None:
                return None
            m = re.search(r"-?\d+(?:[.,]\d+)?", str(s).replace(",", "") if "," in str(s) and "." in str(s) else str(s).replace(",", "."))
            return float(m.group(0)) if m else None
        out = []
        for i, r in enumerate(rows):
            # "kỳ trước" của sự kiện kế tiếp chính là thực tế (đã hiệu chỉnh) của kỳ này -> dùng làm thực tế khi thiếu
            nxt_prev = num(rows[i + 1]["previous"]) if i + 1 < len(rows) else None
            act = num(r.get("actual"))
            out.append({"ts": r["ts"], "actual": act, "actual_text": r.get("actual"), "forecast": num(r.get("forecast")), "forecast_text": r.get("forecast"),
                        "previous": num(r.get("previous")), "previous_text": r.get("previous"), "actual_from_next": nxt_prev if act is None else None,
                        "surprise": (act - num(r.get("forecast"))) if act is not None and num(r.get("forecast")) is not None else None,
                        "impact": r.get("impact"), "period": (r.get("extra") or {}).get("actual_period") if isinstance(r.get("extra"), dict) else None})
        have = [o for o in out if o["surprise"] is not None]
        return {"title": title, "country": country, "count": len(out), "items": out,
                "stats": {"n_actual": sum(1 for o in out if o["actual"] is not None), "n_surprise": len(have),
                          "beat_pct": round(100 * sum(1 for o in have if o["surprise"] > 0) / len(have), 1) if have else None,
                          "avg_surprise": round(fmean([o["surprise"] for o in have]), 4) if have else None}}

    # ------------------------------------------------------------------------------------------ vi the dau co lon
    @api.get("/intel/cot", tags=["intel"], summary="Vị thế đầu cơ lớn hàng tuần theo mã: chuỗi net, phân vị, thay đổi tuần (tham khảo)")
    async def intel_cot(request: Request):
        repo = get_repo(request)

        async def build():
            rows = await D.positions_weekly(repo, "cftc")
            by: dict[str, dict[str, float]] = {}
            for r in rows:
                by.setdefault(r["symbol"], {})[r["as_of"].date().isoformat()] = float(r["net_volume"])
            items = []
            for sym, series in by.items():
                pts = sorted(series.items())
                vals = [v for _, v in pts]
                cur = vals[-1]
                prev = vals[-2] if len(vals) > 1 else None
                con = COT_CONTRACTS.get(sym, (sym, False))
                items.append({**_meta(sym), "contract": con[0], "inverted": con[1], "as_of": pts[-1][0], "net": cur, "prev": prev, "change": cur - prev if prev is not None else None,
                              "n": len(vals), "percentile": C.percentile_rank(vals, cur) if len(vals) >= 8 else None,
                              "min": min(vals), "max": max(vals), "series": [{"d": d, "net": v} for d, v in pts]})
            items.sort(key=lambda i: i["symbol"])
            return {"items": items, "count": len(items), "weeks_max": max((i["n"] for i in items), default=0),
                    "note": "Vị thế ròng của nhóm đầu cơ lớn theo báo cáo hàng tuần (công bố trễ, dữ liệu thứ Ba, đăng thứ Sáu); tham khảo, không phải tín hiệu."}
        return await D.cached(("cot", id(repo)), 120, build)
