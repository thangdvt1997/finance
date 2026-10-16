"""vn-market: API CHỈ-ĐỌC cho chứng khoán Việt Nam (cuối ngày). api-gateway proxy `/v1/vn/*` -> `/vn/*` của service này.
Không có route ghi, không có đường đặt lệnh. Dữ liệu: VNDirect finfo (công khai, không chính thức, cuối ngày) + seed vnstock/KBS (ngành, rổ chỉ số)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from tscommon import make_app

from . import __version__, analytics as an, news as newsmod, rules, universe
from .ingest import Ingestor
from .vndirect import VNDirectClient

log = logging.getLogger("vn_market")

SOURCE = {"name": "VNDirect finfo (API công khai, không chính thức)", "delay": "cuối ngày (~15:10 giờ VN), không realtime",
          "sector": "phân ngành KBS (vnstock) - không phải ICB chính thức", "license": "chỉ dùng cá nhân, không phân phối lại"}
MAIN_INDEXES = ["VNINDEX", "VN30", "VN100", "HNX", "HNX30", "UPCOM"]
CODE_RE = re.compile(r"^[A-Z0-9]{2,12}$")
UNAVAILABLE = {
    "proprietary": {"available": False, "reason": "Giao dịch tự doanh: không có nguồn miễn phí hợp lệ ổn định (HOSE/HNX công bố rời rạc, VNDirect không cung cấp). "
                                                  "Cần tài khoản SSI FastConnect/DNSE hoặc nguồn trả phí (FiinQuant/WiChart)."},
    "intraday": {"available": False, "reason": "Giá realtime/khớp lệnh trong phiên (bảng giá): SSI iBoard và TCBS chặn truy cập tự động (403); cần tài khoản "
                                                "SSI FastConnect hoặc DNSE (Lightspeed API). Hệ thống chỉ có dữ liệu cuối ngày."},
    "financials": {"available": False, "reason": "BCTC chi tiết (doanh thu, lợi nhuận, ROE công bố) chưa tích hợp: nguồn miễn phí ổn định chưa xác minh. "
                                                  "EPS/ROE hiển thị là ước tính suy ra từ P/E, P/B."},
}


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "date phải dạng YYYY-MM-DD") from None


def _uni(u: str) -> str:
    u = (u or "all").lower()
    if u not in an.UNIVERSES:
        raise HTTPException(400, f"universe phải thuộc {sorted(an.UNIVERSES)}")
    return u


def _code(c: str) -> str:
    c = (c or "").strip().upper()
    if c.startswith("VN:"):
        c = c[3:]
    if not CODE_RE.match(c):
        raise HTTPException(400, "mã không hợp lệ")
    return c


def create_app(store: Any = None, ingestor: Ingestor | None = None, *, run_ingest: bool | None = None) -> FastAPI:
    holder: dict[str, Any] = {"store": store, "ing": ingestor, "client": None}
    cache: dict[Any, tuple[float, Any]] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if holder["store"] is None:
            from .store import Store
            holder["store"] = await Store.connect(os.environ["VN_DB_URL"])
            holder["client"] = VNDirectClient(base_url=os.getenv("VN_SOURCE_URL", "https://api-finfo.vndirect.com.vn/v4"),
                                              min_interval=float(os.getenv("VN_MIN_INTERVAL", "0.8")),
                                              user_agent=os.getenv("USER_AGENT", "trading-system-vn-market/0.1 (personal research, read-only)"))
            holder["ing"] = Ingestor(holder["client"], holder["store"])
        do_ingest = run_ingest if run_ingest is not None else os.getenv("VN_INGEST", "true").lower() in ("1", "true", "yes")
        if do_ingest and holder["ing"] is not None:
            task = asyncio.create_task(holder["ing"].loop(), name="vn-ingest")
        yield
        if task:
            task.cancel()
        if holder["client"]:
            await holder["client"].aclose()
        if holder["store"] is not None and hasattr(holder["store"], "close"):
            await holder["store"].close()

    app = make_app("vn-market", __version__, internal_auth=True)
    app.router.lifespan_context = lifespan

    def S():
        if holder["store"] is None:
            raise HTTPException(503, "chưa kết nối CSDL")
        return holder["store"]

    async def cached(key: Any, ttl: float, fn):
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        v = await fn()
        cache[key] = (time.monotonic(), v)
        if len(cache) > 200:
            for k in sorted(cache, key=lambda k: cache[k][0])[:100]:
                cache.pop(k, None)
        return v

    async def resolve_date(d: str | None) -> date:
        want = _d(d)
        latest = await cached("latest", 30, S().latest_date)
        if latest is None:
            raise HTTPException(503, "chưa có dữ liệu (đang nạp lần đầu)")
        if want is None:
            return latest
        return min(want, latest)

    async def snap(d: date) -> list[dict]:
        return await cached(("snap", d), 60, lambda: S().snapshot(d))

    def meta(d: date | None) -> dict:
        return {"as_of": d.isoformat() if d else None, "source": SOURCE["name"], "delay": SOURCE["delay"]}

    # ---- trạng thái ------------------------------------------------------------------------------------------------------------
    @app.get("/vn/status")
    async def status():
        st = S()
        c = await st.counts()
        ing = holder["ing"].status if holder["ing"] else {}
        latest = await st.latest_date()
        today = datetime.now(rules.VN_TZ).date()
        expected = rules.last_session_date(datetime.now(timezone.utc))
        lag = (date.fromisoformat(expected) - latest).days if latest else None
        return {"version": __version__, "source": SOURCE, "counts": c, "latest": latest, "expected_latest": expected, "lag_days": lag,
                "stale": bool(lag and lag > 1), "ingest": ing, "universe_seed": universe.seed_meta(), "today_vn": today,
                "capabilities": {"eod_prices": True, "indices": True, "breadth": True, "heatmap": True, "screener_fundamental": True,
                                 "foreign_flow": True, "events": True, "news_by_symbol": True, **{k: v["available"] for k, v in UNAVAILABLE.items()}},
                "unavailable": UNAVAILABLE}

    @app.get("/vn/rules")
    async def get_rules():
        return rules.rules_summary()

    @app.get("/vn/session")
    async def session():
        now = datetime.now(timezone.utc)
        return {"sessions": {f: rules.session_status(now, f) for f in an.FLOORS}, "last_closed_session": rules.last_session_date(now),
                "note": "Không xét ngày lễ."}

    # ---- tổng quan --------------------------------------------------------------------------------------------------------------
    @app.get("/vn/overview")
    async def overview(date: str | None = None):
        st = S()
        d = await resolve_date(date)
        rows = await snap(d)
        idx = {r["code"]: r for r in await cached(("idx", d), 60, lambda: st.index_on(d))}
        out_idx = []
        for code in MAIN_INDEXES:
            r = idx.get(code)
            if not r:
                continue
            ser = await cached(("ser", code, d), 300, lambda code=code: st.index_series(code, 30))
            out_idx.append({**{k: r.get(k) for k in ("code", "close", "chg", "pct", "open", "high", "low", "volume", "value", "pt_value", "advances",
                                                     "declines", "no_change", "no_trade", "ceiling_n", "floor_n")},
                            "spark": [x["close"] for x in ser if x["d"] <= d]})
        liq = an.liquidity(await cached(("liq", d), 300, lambda: st.liquidity_series(25)))
        fsum = an.foreign_summary(rows, 10)
        now = datetime.now(timezone.utc)
        return {**meta(d), "indices": out_idx, "breadth": an.breadth(rows), "liquidity": {k: liq[k] for k in ("last", "avg_prev", "ratio", "label", "window")},
                "foreign": {"totals": fsum["totals"], "top_buy": fsum["top_buy"][:5], "top_sell": fsum["top_sell"][:5]},
                "limits": {k: v for k, v in an.limit_hits(rows).items() if k.endswith("_n")},
                "session": {f: rules.session_status(now, f) for f in an.FLOORS}, "sectors": an.sector_summary(rows)[:30]}

    @app.get("/vn/indices")
    async def indices(date: str | None = None):
        d = await resolve_date(date)
        return {**meta(d), "rows": await cached(("idx", d), 60, lambda: S().index_on(d))}

    @app.get("/vn/index/{code}")
    async def index_series(code: str, n: int = Query(250, ge=5, le=3000)):
        code = _code(code)
        rows = await S().index_series(code, n)
        if not rows:
            raise HTTPException(404, "không có chỉ số này")
        return {**meta(rows[-1]["d"]), "code": code, "rows": rows}

    # ---- heatmap / ngành / top / trần sàn / độ rộng / thanh khoản -------------------------------------------------------------
    @app.get("/vn/heatmap")
    async def heatmap(universe_: str = Query("vn100", alias="universe"), size: str = Query("marketcap", pattern="^(marketcap|value)$"),
                      date: str | None = None, per_sector: int = Query(25, ge=3, le=60)):
        d = await resolve_date(date)
        return {**meta(d), **an.heatmap(await snap(d), _uni(universe_), size, per_sector)}

    @app.get("/vn/sectors")
    async def sectors(universe_: str = Query("all", alias="universe"), date: str | None = None):
        d = await resolve_date(date)
        return {**meta(d), "rows": an.sector_summary(await snap(d), _uni(universe_))}

    @app.get("/vn/movers")
    async def movers(by: str = Query("gainers", pattern="^(gainers|losers|volume|value|foreign_buy|foreign_sell)$"),
                     universe_: str = Query("all", alias="universe"), n: int = Query(20, ge=1, le=100), date: str | None = None,
                     min_value: float = Query(1e9, ge=0)):
        d = await resolve_date(date)
        return {**meta(d), "by": by, "rows": an.movers(await snap(d), by, _uni(universe_), n, min_value)}

    @app.get("/vn/limits")
    async def limits(universe_: str = Query("all", alias="universe"), date: str | None = None):
        d = await resolve_date(date)
        return {**meta(d), **an.limit_hits(await snap(d), _uni(universe_)), "bands": rules.rules_summary()["bands"]}

    @app.get("/vn/breadth")
    async def breadth(date: str | None = None, n: int = Query(60, ge=5, le=500)):
        st = S()
        d = await resolve_date(date)
        series = {}
        for code in ("VNINDEX", "HNX", "UPCOM"):
            rs = await cached(("ser", code, n, d), 300, lambda code=code: st.index_series(code, n))
            series[code] = [{"d": r["d"], "advances": r["advances"], "declines": r["declines"], "no_change": r["no_change"], "ceiling": r["ceiling_n"],
                             "floor": r["floor_n"], "pct": r["pct"]} for r in rs if r["d"] <= d]
        return {**meta(d), "computed": an.breadth(await snap(d)), "published_series": series,
                "note": "computed = tự đếm từ giá từng mã (cổ phiếu, không ETF); published_series = số liệu sở/VNDirect gắn với chỉ số (khác nhau nhẹ do phạm vi rổ)."}

    @app.get("/vn/liquidity")
    async def liquidity(n: int = Query(60, ge=5, le=300)):
        data = an.liquidity(await cached(("liq-n", n), 300, lambda: S().liquidity_series(n)), window=min(20, n - 1))
        return {**meta(data["days"][-1]["d"] if data["days"] else None), **data}

    # ---- khối ngoại ---------------------------------------------------------------------------------------------------------------
    @app.get("/vn/foreign")
    async def foreign(universe_: str = Query("all", alias="universe"), n: int = Query(15, ge=3, le=50), date: str | None = None,
                      cum_days: int = Query(5, ge=0, le=60)):
        st = S()
        d = await resolve_date(date)
        rows = await snap(d)
        out = {**meta(d), **an.foreign_summary(rows, n, _uni(universe_)), "proprietary": UNAVAILABLE["proprietary"]}
        out["market_series"] = await cached(("fms", 30, d), 300, lambda: st.foreign_market_series(30))
        if cum_days:
            dates = await cached(("dates", 60, d), 300, lambda: st.trading_dates(60))
            dates = [x for x in dates if x <= d][:cum_days]
            if dates:
                cum = await st.foreign_cum(min(dates))
                names = {r["code"]: r for r in rows}
                uni = [c for c in cum if c["code"] in names and an.in_universe(names[c["code"]], _uni(universe_))]
                uni.sort(key=lambda c: c["net_val"] or 0)
                f = lambda c: {"code": c["code"], "name": names[c["code"]].get("short_name"), "net_val": c["net_val"], "days": c["days"]}  # noqa: E731
                out["cum"] = {"days": len(dates), "since": min(dates), "top_buy": [f(c) for c in reversed(uni[-n:]) if (c["net_val"] or 0) > 0],
                              "top_sell": [f(c) for c in uni[:n] if (c["net_val"] or 0) < 0]}
        return out

    # ---- screener -----------------------------------------------------------------------------------------------------------------
    @app.get("/vn/screener")
    async def screener(request: Request, universe_: str = Query("vn100", alias="universe"), industry: str | None = None,
                       sort: str = "marketcap", order: str = Query("desc", pattern="^(asc|desc)$"), limit: int = Query(50, ge=1, le=500),
                       date: str | None = None):
        st = S()
        d = await resolve_date(date)
        q = request.query_params
        filt: dict[str, tuple[float | None, float | None]] = {}
        for k in an.RANGE_KEYS:
            lo, hi = q.get(f"{k}_min"), q.get(f"{k}_max")
            try:
                lo_v = float(lo) if lo not in (None, "") else None
                hi_v = float(hi) if hi not in (None, "") else None
            except ValueError:
                raise HTTPException(400, f"{k}_min/{k}_max phải là số") from None
            if lo_v is not None or hi_v is not None:
                filt[k] = (lo_v, hi_v)
        rows = await snap(d)

        async def build():
            codes = [r["code"] for r in rows if r.get("focus")]
            since = d - timedelta(days=130)
            return an.technicals(await st.closes(codes, since))
        techs = await cached(("tech", d), 1800, build)
        res = an.screen(rows, techs, filt, universe=_uni(universe_), industry=industry, sort=sort, desc=(order == "desc"), limit=limit)
        return {**meta(d), **res, "filters": {k: list(v) for k, v in filt.items()},
                "caveats": ["EPS = giá / P/E và ROE = P/B / P/E là ƯỚC TÍNH (nguồn không cung cấp trực tiếp)",
                            "RSI/MA chỉ có cho rổ theo dõi (VN100+HNX30) từ giá điều chỉnh; mã khác bị loại khi lọc theo RSI",
                            "P/E, P/B, vốn hoá do VNDirect tính hằng ngày, không kiểm chứng độc lập"],
                "industries": sorted({r["industry_name"] for r in rows if r.get("industry_name") and r.get("kind") != "ETF"})}

    # ---- mã đơn lẻ ----------------------------------------------------------------------------------------------------------------
    @app.get("/vn/symbols")
    async def symbols(q: str | None = None, focus: bool = True, limit: int = Query(300, ge=1, le=2000)):
        rows = await cached(("syms", focus), 300, lambda: S().symbols(focus))
        if q:
            qq = q.strip().lower()
            rows = [r for r in rows if qq in r["code"].lower() or qq in (r.get("short_name") or "").lower() or qq in (r.get("name") or "").lower()]
        return {"rows": [{k: r.get(k) for k in ("code", "floor", "kind", "name", "short_name", "industry_name", "in_vn30", "in_vn100", "in_hnx30")}
                         for r in rows[:limit]], "total": len(rows)}

    @app.get("/vn/symbol/{code}")
    async def symbol(code: str, n: int = Query(250, ge=5, le=3000)):
        st = S()
        code = _code(code)
        info = await st.symbol_info(code)
        if not info:
            raise HTTPException(404, "mã không có trong danh mục")
        hist = await st.history(code, n)
        d = hist[-1]["d"] if hist else None
        snaprow = next((r for r in (await snap(d) if d else []) if r["code"] == code), None)
        fr = await st.foreign_series(code, 30)
        today = datetime.now(rules.VN_TZ).date()
        ev = await st.events(today - timedelta(days=30), today + timedelta(days=180), [code])
        row = an.screener_row(snaprow, None) if snaprow else None
        return {**meta(d), "info": info, "snapshot": an.brief(snaprow) if snaprow else None, "fundamentals": row, "history": hist, "foreign": fr, "events": ev,
                "notes": ["giá `close` là GIÁ THÔ; `ad_close` đã điều chỉnh cổ tức/thưởng/chia tách (dùng cho động lượng/RSI)",
                          "EPS/ROE là ước tính từ P/E, P/B"]}

    # ---- sự kiện doanh nghiệp + tin ----------------------------------------------------------------------------------------------
    @app.get("/vn/events")
    async def events(days: int = Query(60, ge=1, le=240), back: int = Query(7, ge=0, le=60), focus: bool = True,
                     etype: str | None = Query(None, pattern="^[A-Za-z]{3,20}$"), code: str | None = None):
        st = S()
        today = datetime.now(rules.VN_TZ).date()
        codes = [_code(code)] if code else None
        rows = await st.events(today - timedelta(days=back), today + timedelta(days=days), codes)
        if focus and not code:
            rows = [r for r in rows if r.get("in_vn100") or r.get("in_hnx30") or r.get("in_vn30")]
        if etype:
            rows = [r for r in rows if r["etype"].lower() == etype.lower()]
        return {"as_of": today, "source": SOURCE["name"], "rows": rows, "total": len(rows),
                "types": {"DIVIDEND": "Cổ tức tiền mặt", "STOCKDIV": "Cổ tức bằng cổ phiếu", "KINDDIV": "Cổ phiếu thưởng", "ISSUE": "Phát hành thêm",
                          "MEETING": "Họp ĐHCĐ", "meetingRight": "Chốt quyền ĐHCĐ", "POLL": "Lấy ý kiến cổ đông"},
                "note": "effective_date = ngày giao dịch không hưởng quyền / ngày họp tuỳ loại; lịch có thể thay đổi, đối chiếu thông báo của doanh nghiệp."}

    @app.get("/vn/news")
    async def vn_news(code: str | None = None, days: int = Query(7, ge=1, le=30), limit: int = Query(40, ge=1, le=200), vn30: bool = False):
        st = S()
        items = await cached(("news", days), 300, lambda: st.news_recent(days))
        syms = await cached(("syms-all",), 600, lambda: st.symbols(False))
        want = _code(code) if code else None
        codes = [s["code"] for s in syms if (want and s["code"] == want) or (not want and (s["focus"] or s["in_vn30"]))]
        tagged = newsmod.tag_news(items, codes if not vn30 else [s["code"] for s in syms if s["in_vn30"]])
        if want:
            tagged = [t for t in tagged if want in t["codes"]]
        return {"rows": tagged[:limit], "total": len(tagged), "scanned": len(items), "source": "news_items (RSS tiếng Việt) + gắn mã tự động",
                "caveat": "Gắn mã bằng khớp từ khoá mã IN HOA: có thể sót hoặc nhầm; chỉ là gợi ý."}

    return app
