"""Mock API cho phát triển UI: chạy CHÍNH api-gateway (create_app) với InMemoryRepo + fakeredis, nên định dạng
JSON trùng bản thật. Phục vụ luôn bản build tĩnh (app/dist) ở "/" và gateway ở "/api" (giống nginx).

Chạy (từ gốc repo, dùng venv của repo):
  .venv\\Scripts\\python services\\web-ui\\dev\\mock_server.py [--port 8590] [--empty] [--fail news,calendar]
  --empty   : mọi bảng rỗng (thử trạng thái empty)
  --fail X  : các đường dẫn /v1/X trả 503 (thử trạng thái error)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fakeredis.aioredis as fr
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from tscommon import make_event

from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc).replace(microsecond=0)
rnd = random.Random(42)

BASE = {"EURUSD": 1.0852, "GBPUSD": 1.2961, "USDJPY": 150.214, "XAUUSD": 2652.4, "VN:VNM": 68500.0, "VN:FPT": 124300.0,
        "VN:VCB": 93800.0, "US:AAPL": 231.2}
VOL = {"EURUSD": 0.00035, "GBPUSD": 0.00045, "USDJPY": 0.06, "XAUUSD": 1.6, "VN:VNM": 35.0, "VN:FPT": 80.0, "VN:VCB": 55.0,
       "US:AAPL": 0.25}
TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}
TF_N = {"M1": 600, "M5": 500, "M15": 500, "H1": 500, "H4": 400, "D1": 300}
LIVE: dict[str, float] = {}


def make_bars() -> list[dict]:
    rows = []
    for sym, base in BASE.items():
        for tf, n in TF_N.items():
            if sym.startswith("VN:") and tf in ("M1", "M5"):
                continue  # vnstock chỉ cung cấp khung lớn: thử trường hợp symbol thiếu khung
            step = TF_MIN[tf]
            vol = VOL[sym] * math.sqrt(step) * 0.9
            px = base * (1 + rnd.uniform(-0.01, 0.01))
            series = []
            for i in range(n):
                o = px
                c = o + rnd.gauss(0, vol) + (base - o) * 0.01
                h = max(o, c) + abs(rnd.gauss(0, vol * 0.5))
                l = min(o, c) - abs(rnd.gauss(0, vol * 0.5))
                series.append((o, h, l, c))
                px = c
            # kéo nến cuối về giá hiện tại
            shift = base - series[-1][3]
            for i, (o, h, l, c) in enumerate(series):
                ts = (NOW - timedelta(minutes=step * (n - 1 - i))).replace(second=0)
                if step >= 60:
                    ts = ts.replace(minute=0)
                if step >= 1440:
                    ts = ts.replace(hour=0)
                rows.append({"symbol": sym, "tf": tf, "ts_open": ts, "o": o + shift, "h": h + shift, "l": l + shift,
                             "c": c + shift, "v": float(rnd.randint(80, 2400)), "source": "dukascopy" if not sym.startswith("VN:") else "vnstock"})
            LIVE.setdefault(sym, base)
    return rows


def make_quotes() -> list[dict]:
    out = []
    for sym, base in BASE.items():
        spread = {"EURUSD": 0.00012, "GBPUSD": 0.00016, "USDJPY": 0.012, "XAUUSD": 0.35}.get(sym, base * 0.0003)
        mid = base
        out.append({"symbol": sym, "ts": NOW - timedelta(seconds=rnd.randint(1, 20)), "bid": mid - spread / 2, "ask": mid + spread / 2,
                    "source": "dukascopy" if not sym.startswith("VN:") else "vnstock"})
    return out


NEWS_T = [
    ("USD mạnh lên khi dữ liệu việc làm Mỹ vượt dự báo", ["EURUSD", "USDJPY", "XAUUSD"], "reuters-rss", "vi", 0.35),
    ("Fed giữ nguyên lãi suất, Chủ tịch nhấn mạnh phụ thuộc vào dữ liệu", ["EURUSD", "XAUUSD"], "reuters-rss", "vi", -0.1),
    ("Vàng lập đỉnh mới khi nhu cầu trú ẩn tăng", ["XAUUSD"], "gdelt", "vi", 0.5),
    ("ECB cho biết chưa vội cắt giảm lãi suất thêm", ["EURUSD"], "ecb-rss", "vi", 0.05),
    ("BoJ phát tín hiệu thận trọng, yên Nhật dao động mạnh", ["USDJPY"], "reuters-rss", "vi", -0.2),
    ("VN-Index vượt 1.300 điểm nhờ nhóm ngân hàng", ["VN:VCB"], "cafef-rss", "vi", 0.6),
    ("Vinamilk công bố doanh thu quý 3 tăng 6%", ["VN:VNM"], "vnexpress-rss", "vi", 0.4),
    ("FPT ký hợp đồng chuyển đổi số lớn tại Nhật Bản", ["VN:FPT"], "cafef-rss", "vi", 0.55),
    ("Apple ra mắt dòng sản phẩm mới, cổ phiếu biến động nhẹ", ["US:AAPL"], "reuters-rss", "en", 0.1),
    ("UK inflation cools more than expected, pound slips", ["GBPUSD"], "reuters-rss", "en", -0.3),
    ("Oil climbs as OPEC+ signals output restraint", ["XAUUSD", "USDJPY"], "gdelt", "en", 0.0),
    ("Dollar index steadies ahead of CPI release", ["EURUSD", "GBPUSD", "USDJPY"], "gdelt", "en", 0.0),
]


def make_news() -> list[dict]:
    rows = []
    for i in range(48):
        t, syms, src, lang, sent = NEWS_T[i % len(NEWS_T)]
        rows.append({"url": f"https://example.com/news/{i}", "title": t if i < len(NEWS_T) else f"{t} (cập nhật {i // len(NEWS_T)})",
                     "summary": "Tóm tắt ngắn của bài viết: thị trường phản ứng với số liệu mới và kỳ vọng chính sách tiền tệ trong các phiên tới."
                     if i % 3 else None, "published_at": NOW - timedelta(minutes=17 * i + rnd.randint(0, 9)), "source": src, "lang": lang,
                     "symbols": syms, "sentiment": sent if i % 4 else None, "ingested_at": NOW})
    return rows


def make_calendar() -> list[dict]:
    ev = [("US", "Bảng lương phi nông nghiệp (NFP)", "high", "185K", "175K"), ("US", "CPI hằng năm", "high", "3.1%", "3.2%"),
          ("US", "Quyết định lãi suất FOMC", "high", "5.50%", "5.50%"), ("EU", "Quyết định lãi suất ECB", "high", "4.25%", "4.25%"),
          ("GB", "GDP hàng quý", "med", "0.2%", "0.1%"), ("JP", "Quyết định lãi suất BoJ", "high", "0.10%", "0.10%"),
          ("US", "Doanh số bán lẻ", "med", "0.3%", "0.1%"), ("CN", "PMI sản xuất", "med", "50.2", "50.1"),
          ("EU", "Chỉ số niềm tin ZEW", "low", "12.5", "11.3"), ("VN", "CPI Việt Nam (so với cùng kỳ)", "med", "3.6%", "3.4%"),
          ("US", "Đơn xin trợ cấp thất nghiệp", "med", "232K", "229K"), ("GB", "Chỉ số PMI dịch vụ", "low", "52.1", "52.5"),
          ("US", "Tồn kho dầu thô EIA", "low", "-1.2M", "-0.4M"), ("JP", "Cán cân thương mại", "low", "¥-0.3T", "¥-0.5T")]
    rows = []
    n = 0
    for day in range(-2, 8):
        base = (NOW + timedelta(hours=7)).replace(hour=0, minute=0, second=0) + timedelta(days=day) - timedelta(hours=7)
        for k in range(5 + (day % 3)):
            c, title, imp, fc, pv = ev[(n * 5 + k) % len(ev)]
            ts = base + timedelta(hours=1 + 3 * k + (n % 2), minutes=30 if k % 2 else 0)
            past = ts < NOW
            rows.append({"event_id": f"ff-{n}", "source": "faireconomy", "country": c, "title": title, "impact": imp, "ts": ts,
                         "forecast": fc, "previous": pv, "actual": (fc if k % 2 else pv) if past else None})
            n += 1
    # đảm bảo luôn có 1 sự kiện HIGH trong ~40 phút để thử đếm ngược
    rows.append({"event_id": "ff-soon", "source": "faireconomy", "country": "US", "title": "Phát biểu của Chủ tịch Fed", "impact": "high",
                 "ts": NOW + timedelta(minutes=41, seconds=12), "forecast": None, "previous": None, "actual": None})
    return rows


EXPERTS = [
    ("myfxbook:alpha-gold", "myfxbook", "Alpha Gold Desk", {"gain_pct": 142.5, "max_drawdown_pct": 12.4, "months_active": 38, "followers": 1840, "score": 86, "qualified": True}),
    ("myfxbook:euro-swing", "myfxbook", "Euro Swing", {"gain_pct": 78.2, "max_drawdown_pct": 18.9, "months_active": 26, "followers": 620, "score": 72, "qualified": True}),
    ("zulutrade:yen-carry", "zulutrade", "Yen Carry Lab", {"gain_pct": 54.0, "max_drawdown_pct": 24.0, "months_active": 14, "followers": 310, "score": 58, "qualified": True}),
    ("myfxbook:grid-master", "myfxbook", "Grid Master", {"gain_pct": 310.0, "max_drawdown_pct": 61.0, "months_active": 9, "followers": 4200, "score": 22, "qualified": False, "grid": True, "martingale": True}),
    ("cftc:cot", "cftc-cot", "CFTC Commitments of Traders", {"score": 80, "qualified": True, "months_active": 120}),
    ("sec:berkshire", "sec-13f", "Berkshire Hathaway (13F)", {"score": 90, "qualified": True, "months_active": 480, "followers": 0}),
]


def make_experts() -> dict:
    ex = [{"expert_id": i, "source": s, "display_name": n, "url": f"https://example.com/{i.split(':')[1]}", "reputation": r, "tracked": r.get("qualified", False)}
          for i, s, n, r in EXPERTS]
    sig = []
    combos = [("myfxbook:alpha-gold", "XAUUSD", "buy", 2641.5, 2625.0, 2680.0), ("myfxbook:alpha-gold", "XAUUSD", "buy", 2650.0, 2630.0, 2700.0),
              ("myfxbook:euro-swing", "EURUSD", "sell", 1.0890, 1.0940, 1.0790), ("myfxbook:euro-swing", "GBPUSD", "buy", 1.2920, 1.2860, 1.3040),
              ("zulutrade:yen-carry", "USDJPY", "buy", 149.8, 148.9, 152.0), ("myfxbook:grid-master", "EURUSD", "buy", 1.0870, None, None),
              ("zulutrade:yen-carry", "EURUSD", "sell", 1.0900, 1.0950, 1.0800)]
    for i, (e, s, side, en, sl, tp) in enumerate(combos):
        sig.append({"expert_id": e, "source": e.split(":")[0], "symbol": s, "side": side, "opened_at": NOW - timedelta(hours=2 * i + 1),
                    "entry": en, "sl": sl, "tp": tp, "status": "open", "url": "https://example.com/signal"})
    sig.append({"expert_id": "myfxbook:euro-swing", "source": "myfxbook", "symbol": "USDJPY", "side": "sell", "opened_at": NOW - timedelta(days=3),
                "entry": 151.2, "sl": 152.0, "tp": 149.0, "status": "closed", "url": None})
    pos = []
    for k, (e, s, v, a) in enumerate([("cftc:cot", "EURUSD", 41250, None), ("cftc:cot", "GBPUSD", -12480, None), ("cftc:cot", "USDJPY", 68210, None),
                                      ("cftc:cot", "XAUUSD", 189400, None), ("sec:berkshire", "US:AAPL", -10000000, 187.4), ("myfxbook:alpha-gold", "XAUUSD", 3.5, 2645.0)]):
        pos.append({"expert_id": e, "source": next(x[1] for x in EXPERTS if x[0] == e), "symbol": s, "as_of": NOW - timedelta(days=k % 3, hours=k),
                    "net_volume": float(v), "avg_price": a})
    return {"experts": ex, "expert_signals": sig, "expert_positions": pos}


def make_accounts() -> list[dict]:
    out = []
    for acc, plat, bal, drift in (("DEMO-MT5-01", "mt5", 10000.0, 4.0), ("DEMO-MT4-01", "mt4", 5000.0, 1.3)):
        eq = bal
        n = 7 * 24 * 6
        for i in range(n):
            ts = NOW - timedelta(minutes=10 * (n - 1 - i))
            eq += rnd.gauss(drift * 0.12, drift)
            last = i == n - 1
            pos = []
            if last:
                pos = [{"position_id": "9001", "symbol": "XAUUSD", "broker_symbol": "XAUUSD.m", "side": "buy", "volume": 0.10, "price_open": 2641.5,
                        "price_current": 2652.4, "sl": 2625.0, "tp": 2680.0, "profit": 109.0, "swap": -0.8, "time_open": (NOW - timedelta(hours=5)).isoformat()},
                       {"position_id": "9002", "symbol": "EURUSD", "broker_symbol": "EURUSD.m", "side": "sell", "volume": 0.30, "price_open": 1.0890,
                        "price_current": 1.0852, "sl": 1.0940, "tp": 1.0790, "profit": 114.0, "swap": -1.2, "time_open": (NOW - timedelta(hours=9)).isoformat()},
                       {"position_id": "9003", "symbol": "USDJPY", "broker_symbol": "USDJPY.m", "side": "buy", "volume": 0.20, "price_open": 150.50,
                        "price_current": 150.214, "sl": 149.0, "tp": 0.0, "profit": -38.1, "swap": 0.4, "time_open": (NOW - timedelta(hours=2)).isoformat()}]
            out.append({"account_id": acc, "platform": plat, "ts": ts, "balance": round(bal + (i // 40) * drift, 2), "equity": round(eq, 2),
                        "margin": round(210 + 30 * math.sin(i / 20), 2) if plat == "mt5" else 140.0, "positions": pos})
    return out


def make_alerts() -> list[dict]:
    t = [("crit", "mt-bridge mất kết nối tài khoản DEMO-MT4-01", "Không nhận snapshot trong 5 phút.", ["mt-bridge", "mt4"]),
         ("warn", "market-collector: Dukascopy trả 503", "Thử lại sau 60s (backoff).", ["market-collector"]),
         ("info", "Sự kiện HIGH sắp diễn ra: NFP (US) sau 30 phút", None, ["calendar", "high"]),
         ("warn", "Margin level DEMO-MT5-01 dưới 300%", "Equity/Margin = 280%.", ["account", "margin"]),
         ("info", "Chuyên gia mới đạt chuẩn: Euro Swing", None, ["expert"]),
         ("crit", "storage-writer: lag consumer > 10 phút", "Stream md.quotes tồn 12.400 tin.", ["storage-writer"]),
         ("info", "Backfill XAUUSD H1 hoàn tất", None, ["market-collector"])]
    return [{"id": i + 1, "ts": NOW - timedelta(minutes=37 * i + 4), "level": t[i % len(t)][0], "title": t[i % len(t)][1], "body": t[i % len(t)][2],
             "tags": t[i % len(t)][3], "dedupe_key": f"k{i}", "delivered": i % 5 != 0} for i in range(24)]


class LiveRedis(fr.FakeRedis):
    """fakeredis + xread giả lập: phát tick ngẫu nhiên (fakeredis treo khi BLOCK)."""

    async def xread(self, streams, count=None, block=None):  # noqa: D401
        await asyncio.sleep(0.4)
        out = []
        if "md.quotes" in streams and LIVE:
            evs = []
            for sym in rnd.sample(list(LIVE), k=3):
                spread = {"EURUSD": 0.00012, "GBPUSD": 0.00016, "USDJPY": 0.012, "XAUUSD": 0.35}.get(sym, BASE[sym] * 0.0003)
                LIVE[sym] += rnd.gauss(0, VOL[sym] * 0.12)
                ev = make_event("quote", "market-collector", {"symbol": sym, "bid": LIVE[sym] - spread / 2, "ask": LIVE[sym] + spread / 2,
                                                              "ts": datetime.now(timezone.utc).isoformat(), "source": "dukascopy"})
                evs.append((f"{int(datetime.now().timestamp() * 1000)}-{rnd.randint(0, 99999)}", {"e": ev.model_dump_json()}))
            out.append(("md.quotes", evs))
        return out


def make_analytics(bars: list[dict]) -> list[dict]:
    """Chạy CHÍNH engine của service analytics (TA-Lib) trên nến giả => snapshot đúng định dạng bảng analytics_snapshots."""
    from analytics.config import load_yaml
    from analytics.repo import MemoryBarSource, MemoryStore
    from analytics.runner import Runner

    data: dict[tuple[str, str], list[dict]] = {}
    for b in bars:
        data.setdefault((b["symbol"], b["tf"]), []).append(b)
    store = MemoryStore()
    cfg = load_yaml(None)
    asyncio.run(Runner(cfg, MemoryBarSource(data), store, None).run_cycle())
    return store.as_gateway_rows()


def build(empty: bool, fail: set[str], no_csp: bool = False) -> FastAPI:
    _bars = [] if empty else make_bars()
    tables = {} if empty else {"analytics_snapshots": make_analytics(_bars), "bars": _bars, "quotes": make_quotes(), "news_items": make_news(), "calendar_events": make_calendar(),
                               **make_experts(), "account_snapshots": make_accounts(), "alerts": make_alerts()}
    redis = LiveRedis(decode_responses=True)
    gw = create_app(GatewaySettings(api_tokens=("dev",), auth_disabled=True, cors_origins=(), max_page_size=1000, ws_max_connections=50),
                    InMemoryRepo(**tables), redis)

    async def seed():
        for st, src in (("md.quotes", "market-collector"), ("md.bars", "market-collector"), ("news.items", "news-collector"),
                        ("calendar.events", "news-collector"), ("account.snapshots", "mt-bridge"), ("alerts.out", "alert-service")):
            if empty:
                continue
            ev = make_event("x", src, {"symbol": "EURUSD"})
            await redis.xadd(st, {"e": ev.model_dump_json()})

    import contextlib

    @contextlib.asynccontextmanager
    async def lifespan(_):
        await seed()
        yield

    root = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @root.middleware("http")
    async def chaos(request: Request, call_next):
        p = request.url.path
        if any(p.startswith(f"/api/v1/{f}") for f in fail):
            return JSONResponse({"detail": "mock failure"}, status_code=503)
        resp = await call_next(request)
        if not p.startswith("/api") and not no_csp:  # cùng CSP với nginx để bắt lỗi CSP khi dev
            for ln in (ROOT / "nginx" / "security-headers.conf").read_text(encoding="utf-8").splitlines():
                if ln.startswith("add_header Content-Security-Policy"):
                    resp.headers["Content-Security-Policy"] = ln.split('"')[1]
        return resp

    root.mount("/api", gw)
    dist = ROOT / "app" / "dist"
    if dist.exists():
        root.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return root


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8590)
    ap.add_argument("--empty", action="store_true")
    ap.add_argument("--fail", default="")
    ap.add_argument("--no-csp", action="store_true")
    a = ap.parse_args()
    print(f"Mock UI: http://127.0.0.1:{a.port}/  (dist={'ok' if (ROOT / 'app' / 'dist').exists() else 'NOT BUILT: cd app && npm run build'})", file=sys.stderr)
    uvicorn.run(build(a.empty, {x for x in a.fail.split(",") if x}, a.no_csp), host="127.0.0.1", port=a.port, log_level="warning")
