
import asyncio
import contextlib
import json
import re
from collections import OrderedDict
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Path, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.websockets import WebSocketDisconnect
from prometheus_client import Counter, Gauge, Histogram
from tscommon import STREAMS, make_app
from tscommon.sources import scrub_obj, scrub_sources

from . import __version__, analytics_view as av
from .auth import token_ok
from .authz import WS_CLIENT_STREAMS, event_visible, filter_rows, get_principal, make_authorize, principal_from_headers
from .config import GatewaySettings
from .models import (AccountOrder, AccountSnapshot, AlertRow, Bar, CalendarEvent, EquityPoint, Expert, ExpertOpinion, ExpertPosition, ExpertSignal,
                     NewsItem, Overview, Page, Quote, SystemStatus)
from .repo import Repo
from .loopmon import LoopMonitor, enabled as loopmon_enabled
from .calendar_view import hide_superseded
from .journal_routes import register_journal_routes
from .track_routes import register_track_routes
from .briefing_routes import register_briefing_routes
from .datakeeper_routes import register_datakeeper_routes
from .intel_routes import register_intel_routes
from .datasources_routes import register_datasource_routes
from .paper_routes import register_paper_routes
from .account_reports_routes import register_account_reports_routes
from .ai_trading_routes import register_ai_trading_routes
from .reports_routes import register_reports_routes
from .risk_windows import register_risk_routes
from .symbols_view import register_symbol_routes
from .riskmon_routes import register_riskmon_routes
from .pattern_scan_routes import register_pattern_scan_routes
from .patterns_routes import register_patterns_routes
from .user_routes import register_user_routes
from .vn_routes import register_vn_routes
from .cache import CacheMiddleware, ResponseCache
from .realtime import _origin_ok as _ws_origin_ok, _reap, register_realtime

log = logging.getLogger("gateway")


class _DeadPeerSendFilter(logging.Filter):
    """RS-11: asyncio ghi 'socket.send() raised exception.' (không ném lỗi) khi peer WS đã reset; uvicorn dọn kết nối ngay sau đó.
    Lọc đúng thông điệp này (nhiễu ~5 dòng/kết nối chết), giữ mọi cảnh báo asyncio khác."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("socket.send() raised exception")


logging.getLogger("asyncio").addFilter(_DeadPeerSendFilter())

HTTP_REQS = Counter("gateway_http_requests_total", "Số request /v1", ["path", "status"])
HTTP_LAT = Histogram("gateway_http_request_seconds", "Độ trễ request /v1 (SLO p95)", ["path"],
                     buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
WS_CONNS = Gauge("gateway_ws_connections", "Số kết nối WebSocket đang mở")

SYMBOL_RE = r"^[A-Za-z0-9:._\-]{1,32}$"
TF_RE = r"^(M1|M5|M15|H1|H4|D1)$"
BARS_TF_RE = r"^(M1|M5|M15|M30|H1|H4|D1|W1|MN1)$"   # nến lịch sử có đủ khung MT5 (M30/W1/MN1 do data-keeper nạp); analytics vẫn chỉ TF_RE
ALLOWED_STREAMS = set(STREAMS.values()) | {"analytics.signals"}  # stream của service analytics (không có trong tscommon.STREAMS)
MAX_BARS = 5000
BAR_DUP_FACTOR = 3   # so nguon toi da cung 1 (symbol, tf, ts_open) thuong gap (canon, mt tho, dukascopy/frankfurter)

Symbol = Annotated[str, Query(pattern=SYMBOL_RE, description="Symbol chuẩn hoá, vd EURUSD, VN:VNM")]


def _csv(v: str | None) -> list[str] | None:
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


# 'canon' = chuoi feed EA uu tien (mt-bridge feed.py, source canon:<account>) - dung dau, khop quy tac ORDER BY source cua cac service khac.
BAR_SRC_PRI = ("canon", "dukascopy", "crypto_ccxt", "mt", "yahoo_daily", "frankfurter")


def _src_rank(src: str) -> int:
    s = src.lower()
    if s in BAR_SRC_PRI:
        return BAR_SRC_PRI.index(s)
    head = s.split(":", 1)[0]
    if head in ("mt4", "mt5"):
        head = "mt"
    return BAR_SRC_PRI.index(head) if head in BAR_SRC_PRI else len(BAR_SRC_PRI)


def _dedupe_bars(rows: list[dict]) -> list[dict]:
    """Moi (symbol, tf, ts_open) giu 1 nen: nguon uu tien cao nhat (BAR_SRC_PRI, so theo tien to truoc ':'), con lai theo thu tu goc."""
    def rank(r: dict) -> int:
        return _src_rank(str(r.get("source") or ""))

    best: dict[tuple, dict] = {}
    for r in rows:
        k = (r.get("symbol"), r.get("tf"), r.get("ts_open"))
        if k not in best or rank(r) < rank(best[k]):
            best[k] = r
    if len(best) == len(rows):
        return rows
    seen: set[tuple] = set()
    out = []
    for r in rows:
        k = (r.get("symbol"), r.get("tf"), r.get("ts_open"))
        if k in seen:
            continue
        seen.add(k)
        out.append(best[k])
    return out


# /v1/data-sources tu an danh o route (giu khoa provider -> nhan trung tinh); /v1/system la trang thai van hanh.
_SCRUB_SKIP_PATHS = ("/v1/data-sources",)


_SCRUB_THREAD_BYTES = int(os.getenv("SCRUB_THREAD_BYTES", "32768"))


_SCRUB_MEMO: dict = {}
_TS_LIKE = re.compile(r"[0-9TZ:.+\- ]*")


def _scrub_payload(p: dict) -> dict:
    """scrub_obj có memo cho payload phẳng kiểu quote: kết quả chỉ phụ thuộc tên khoá + giá trị chuỗi, còn số đi thẳng
    (khoá nguồn chỉ bị bỏ theo giá trị chuỗi/khoá strong, không theo số). Payload lồng nhau -> scrub_obj thường."""
    if any(isinstance(v, (dict, list, tuple)) for v in p.values()):
        return scrub_obj(p)
    num = (int, float, bool, type(None))
    # giá trị "hằng" (số, hoặc chuỗi chỉ gồm chữ số/ký tự giờ như ts ISO) không ảnh hưởng kết quả scrub -> không đưa vào chữ ký memo (ts mỗi tick khác nhau)
    const = lambda v: isinstance(v, num) or (isinstance(v, str) and _TS_LIKE.fullmatch(v) is not None)  # noqa: E731
    sig = tuple((k, None if const(v) else v) for k, v in p.items())
    tpl = _SCRUB_MEMO.get(sig)
    if tpl is None:
        tpl = scrub_obj({k: (0 if isinstance(v, num) else v) for k, v in p.items()})
        if len(_SCRUB_MEMO) > 4096:
            _SCRUB_MEMO.clear()
        _SCRUB_MEMO[sig] = tpl
    return {k: (p[k] if const(p[k]) else tv) for k, tv in tpl.items()}


def create_app(settings: GatewaySettings | None = None, repo: Repo | None = None, redis=None, cache: ResponseCache | None = None) -> FastAPI:
    settings = settings or GatewaySettings()
    app = make_app("api-gateway", __version__)
    app.title = "Trading System API Gateway"
    app.description = ("API chỉ-đọc cho dashboard: dữ liệu thị trường, tin tức, lịch kinh tế, tín hiệu chuyên gia, "
                       "tài khoản (READ-ONLY). Xác thực bằng header `X-API-Key`.")
    app.state.repo = repo
    app.state.redis = redis
    app.state.settings = settings
    app.state.ws_count = 0
    ev_txt: OrderedDict = OrderedDict()      # (stream, id) -> JSON đã scrub, dùng chung cho mọi kết nối /v1/stream

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET"],
                           allow_headers=["X-API-Key"])

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        own_repo = own_redis = False
        if _app.state.repo is None:
            from .pg_repo import PgRepo
            _app.state.repo = await PgRepo.connect(settings.database_url)
            own_repo = True
        if _app.state.redis is None:
            _app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            own_redis = True
        mon = LoopMonitor() if loopmon_enabled() else None   # R3-11: đo trễ event loop + chụp stack khi bị chặn
        if mon:
            mon.start()
        try:
            yield
        finally:
            if mon:
                await mon.stop()
            if own_repo:
                await _app.state.repo.close()
            if own_redis:
                await _app.state.redis.aclose()

    app.router.lifespan_context = lifespan

    def get_repo(request: Request) -> Repo:
        return request.app.state.repo

    async def require_key(x_api_key: Annotated[str | None, Header(description="API token")] = None) -> None:
        if not token_ok(x_api_key, settings.api_tokens, settings.auth_disabled):
            raise HTTPException(401, "API key không hợp lệ hoặc thiếu", headers={"WWW-Authenticate": "ApiKey"})

    def paging(limit: Annotated[int, Query(ge=1, description="Số bản ghi tối đa")] = 100,
               offset: Annotated[int, Query(ge=0, le=100_000)] = 0) -> tuple[int, int]:
        return min(limit, settings.max_page_size), offset

    Paging = Annotated[tuple[int, int], Depends(paging)]
    Repo_ = Annotated[Repo, Depends(get_repo)]

    authorize = make_authorize(lambda: settings.auth_trust_secret)   # phan quyen master/client (authz.py); API key van bat buoc
    api = APIRouter(prefix="/v1", dependencies=[Depends(require_key), Depends(authorize)])

    def page(rows: list[dict], lim: int, off: int) -> dict:
        return {"items": rows, "limit": lim, "offset": off, "count": len(rows)}

    @api.get("/bars", response_model=Page[Bar], summary="Nến OHLCV")
    async def bars(repo: Repo_, symbol: Symbol, tf: Annotated[str, Query(pattern=BARS_TF_RE)],
                   from_: Annotated[datetime | None, Query(alias="from")] = None,
                   to: datetime | None = None,
                   order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
                   limit: Annotated[int, Query(ge=1, le=MAX_BARS)] = 500,
                   offset: Annotated[int, Query(ge=0, le=100_000)] = 0):
        limit = min(limit, MAX_BARS)
        if settings.hide_sources:
            # nhieu nguon cung (symbol, tf, ts_open) (canon + EA tho + dukascopy: toi 3 hang/ts): lay du hang roi giu 1 nen theo uu tien
            # (UI khong thay nguon) -> tra dung `limit` nen thay vi limit hang
            rows = _dedupe_bars(await repo.bars(symbol, tf, from_, to, order, limit * BAR_DUP_FACTOR, offset))[:limit]
        else:
            rows = await repo.bars(symbol, tf, from_, to, order, limit, offset)
        return page(rows, limit, offset)

    @api.get("/quotes/latest", response_model=list[Quote], summary="Giá mới nhất mỗi symbol")
    async def quotes_latest(repo: Repo_, symbols: Annotated[str | None, Query(description="CSV symbol")] = None):
        syms = _csv(symbols)
        if syms and len(syms) > 100:
            raise HTTPException(422, "Tối đa 100 symbol")
        return await repo.quotes_latest(syms, 200)

    @api.get("/news", response_model=Page[NewsItem], summary="Tin tức (mới nhất trước)")
    async def news(repo: Repo_, pg: Paging, symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None,
                   since: datetime | None = None):
        return page(await repo.news(symbol, since, *pg), *pg)

    @api.get("/calendar", response_model=Page[CalendarEvent],
             summary="Lịch kinh tế (mặc định: từ hôm qua, sự kiện sắp tới trước)")
    async def calendar(repo: Repo_, pg: Paging,
                       from_: Annotated[datetime | None, Query(alias="from", description="Mặc định: bây giờ - 1 ngày")] = None,
                       to: Annotated[datetime | None, Query(description="Mặc định: không giới hạn")] = None,
                       impact: Annotated[str | None, Query(description="CSV: low,med,high")] = None,
                       order: Annotated[str, Query(pattern="^(upcoming|asc|desc)$",
                                                   description="upcoming: sắp tới tăng dần rồi quá khứ mới->cũ")] = "upcoming"):
        imp = _csv(impact)
        if imp and not set(imp) <= {"low", "med", "high"}:
            raise HTTPException(422, "impact phải thuộc low|med|high")
        now = datetime.now(timezone.utc)
        if from_ is None:
            from_ = now - timedelta(days=1)
        return page(hide_superseded(await repo.calendar(from_, to, imp, *pg, order=order, now=now)), *pg)

    @api.get("/experts", response_model=Page[Expert], summary="Danh sách chuyên gia theo dõi")
    async def experts(repo: Repo_, pg: Paging):
        return page(await repo.experts(*pg), *pg)

    @api.get("/expert-signals", response_model=Page[ExpertSignal], summary="Tín hiệu chuyên gia")
    async def expert_signals(repo: Repo_, pg: Paging, symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None,
                             status: Annotated[str | None, Query(pattern="^(open|closed)$")] = None,
                             expert_id: Annotated[str | None, Query(max_length=128)] = None):
        return page(await repo.expert_signals(symbol, status, expert_id, *pg), *pg)

    @api.get("/expert-opinions", response_model=Page[ExpertOpinion], summary="Ý kiến chuyên gia/tổ chức (tham khảo, không phải khuyến nghị)")
    async def expert_opinions(repo: Repo_, pg: Paging, group: Annotated[str | None, Query(max_length=32, pattern="^[a-z_]+$")] = None,
                              stance: Annotated[str | None, Query(pattern="^(hawkish|dovish|bullish|bearish|neutral)$")] = None,
                              symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None,
                              expert_id: Annotated[str | None, Query(max_length=128)] = None):
        return page(await repo.expert_opinions(group, stance, symbol, expert_id, *pg), *pg)

    @api.get("/expert-positions", response_model=Page[ExpertPosition], summary="Vị thế công khai của chuyên gia")
    async def expert_positions(repo: Repo_, pg: Paging, symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None,
                               expert_id: Annotated[str | None, Query(max_length=128)] = None):
        return page(await repo.expert_positions(symbol, expert_id, *pg), *pg)

    @api.get("/accounts", response_model=list[AccountSnapshot], summary="Snapshot tài khoản mới nhất (read-only)")
    async def accounts(request: Request, repo: Repo_):
        return filter_rows(get_principal(request), await repo.accounts_latest())   # client chi thay tai khoan cua minh

    @api.get("/accounts/{account_id}/orders", response_model=list[AccountOrder], summary="Lệnh chờ của 1 tài khoản (read-only; client chỉ tài khoản của mình)")
    async def account_orders(request: Request, repo: Repo_, account_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:\-]+$")],
                             status: Annotated[str, Query(pattern="^(open|removed|all)$")] = "open",
                             limit: Annotated[int, Query(ge=1, le=500)] = 200):
        if not get_principal(request).can(account_id):   # lớp 2 (lớp 1 = authorize theo URL): 403 đồng nhất, không oracle
            raise HTTPException(403, "Không có quyền truy cập")
        return await repo.account_orders(account_id, status, limit)

    @api.get("/me", summary="Vai trò + danh sách tài khoản MT hợp lệ của phiên hiện tại (do nginx/auth xác thực)")
    async def me(request: Request, repo: Repo_):
        p = get_principal(request)
        out = p.me()
        if p.is_master:
            out["accounts"] = sorted({a["account_id"] for a in await repo.accounts_latest()})
        return out

    @api.get("/alerts", response_model=Page[AlertRow], summary="Cảnh báo gần đây")
    async def alerts(repo: Repo_, pg: Paging, level: Annotated[str | None, Query(pattern="^(info|warn|crit)$")] = None):
        return page(await repo.alerts(level, *pg), *pg)

    @api.get("/overview", response_model=Overview, summary="Tổng hợp cho dashboard")
    async def overview(request: Request, repo: Repo_):
        now = datetime.now(timezone.utc)
        quotes, news_, events, sigs, accts = await asyncio.gather(
            repo.quotes_latest(None, 30),
            repo.news(None, now - timedelta(hours=24), 8, 0),
            repo.calendar(now, now + timedelta(hours=48), ["med", "high"], 10, 0),
            repo.expert_signals(None, "open", None, 10, 0),
            repo.accounts_latest())
        return {"generated_at": now, "quotes": quotes, "news": news_, "upcoming_events": hide_superseded(events),
                "expert_signals": sigs, "accounts": filter_rows(get_principal(request), accts)}

    # /v1/symbols (+ class/name/group/session/price) và /v1/symbols/classes: xem symbols_view.py (đăng ký bên dưới)

    @api.get("/equity-history", response_model=list[EquityPoint], summary="Lịch sử equity/balance/margin của 1 tài khoản")
    async def equity_history(repo: Repo_, account_id: Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[\w.:\-]+$")],
                             from_: Annotated[datetime | None, Query(alias="from", description="Mặc định: 30 ngày trước")] = None,
                             to: datetime | None = None,
                             limit: Annotated[int, Query(ge=1, le=5000)] = 1000):
        return await repo.equity_history(account_id, from_, to, limit)

    # ---------------- Phân tích kỹ thuật (service analytics ghi snapshot; gateway chỉ đọc/lọc) ----------------
    AnTf = Annotated[str, Query(pattern=TF_RE, description="Khung thời gian (H1|H4|D1...)")]

    @api.get("/analytics/overview", summary="Phân tích: trạng thái mọi symbol × khung + tổng hợp (heatmap)")
    async def analytics_overview(repo: Repo_):
        return av.overview(await repo.analytics("summary"))

    @api.get("/analytics/symbol/{symbol}", summary="Phân tích chi tiết 1 symbol: chỉ báo, trạng thái, chuỗi vẽ biểu đồ, phiên")
    async def analytics_symbol(repo: Repo_, symbol: Annotated[str, Path(pattern=SYMBOL_RE)], tf: AnTf | None = None):
        rows, sess = await asyncio.gather(repo.analytics("detail", symbol=symbol), repo.analytics("sessions", key=symbol))
        if tf:
            rows = [r for r in rows if r["payload"].get("tf") == tf]
        if not rows:  # mã ngoài danh sách analytics: 200 rỗng (có cờ available=false) thay vì 404 để không gây lỗi console ở UI
            return {"generated_at": datetime.now(timezone.utc), "symbol": symbol, "available": False, "tfs": {}, "sessions": None,
                    "disclaimer": av.DISCLAIMER}
        return {**av.symbol_detail(rows, sess), "available": True}

    @api.get("/analytics/screener", summary="Bộ lọc: lọc/sắp xếp symbol theo điều kiện chỉ báo (không phải tín hiệu mua/bán)")
    async def analytics_screener(
            repo: Repo_, tf: AnTf = "H1",
            trend: Annotated[str | None, Query(description="CSV: up,down,side")] = None,
            momentum: Annotated[str | None, Query(description="CSV: overbought,oversold,bullish,bearish,neutral")] = None,
            volatility: Annotated[str | None, Query(description="CSV: squeeze,high,normal,low")] = None,
            state: Annotated[str | None, Query(description="CSV mã trạng thái, phải thoả TẤT CẢ (vd above_ema200,squeeze)",
                                               pattern=r"^[a-z0-9_,]*$")] = None,
            rsi_min: float | None = None, rsi_max: float | None = None, adx_min: float | None = None,
            heat_min: float | None = None, bias_min: float | None = None, bias_max: float | None = None,
            atr_pctile_min: float | None = None, q: Annotated[str | None, Query(max_length=32)] = None,
            sort: Annotated[str, Query(pattern="^(" + "|".join(sorted(av.SORT_KEYS)) + ")$")] = "heat",
            order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
            limit: Annotated[int, Query(ge=1, le=500)] = 100):
        for name, val, allowed in (("trend", trend, av.TRENDS), ("momentum", momentum, av.MOMENTUMS), ("volatility", volatility, av.VOLS)):
            if val and not set(_csv(val)) <= allowed:
                raise HTTPException(422, f"{name} phải thuộc {sorted(allowed)}")
        return av.screener(await repo.analytics("summary"), tf=tf, trend=trend, momentum=momentum, volatility=volatility,
                           state=state, rsi_min=rsi_min, rsi_max=rsi_max, adx_min=adx_min, heat_min=heat_min, bias_min=bias_min,
                           bias_max=bias_max, atr_pctile_min=atr_pctile_min, q=q, sort=sort, order=order, limit=limit)

    @api.get("/analytics/correlation", summary="Ma trận tương quan lăn (log-return) + cặp mạnh nhất + cặp đổi chiều")
    async def analytics_correlation(repo: Repo_, tf: AnTf = "D1",
                                    min_delta: Annotated[float, Query(ge=0.1, le=2.0)] = 0.8):
        return av.correlation(await repo.analytics("correlation", key=tf), tf, min_delta)

    @api.get("/analytics/sessions", summary="Thống kê theo phiên Tokyo/London/NY và biên độ trung bình theo giờ (UTC)")
    async def analytics_sessions(repo: Repo_, symbol: Annotated[str | None, Query(pattern=SYMBOL_RE)] = None):
        return av.sessions(await repo.analytics("sessions", key=symbol))

    def _prom_up() -> list[dict] | None:
        url = settings.prometheus_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": 'up{job="services"}'})
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 (URL từ cấu hình, chỉ-đọc)
                data = json.loads(resp.read())
        except Exception:  # noqa: BLE001
            return None
        if data.get("status") != "success":
            return None
        out = []
        for r in data["data"]["result"]:
            ts, val = r["value"]
            out.append({"name": r["metric"].get("service") or r["metric"].get("instance", "?"), "up": val == "1",
                        "last_scrape": datetime.fromtimestamp(float(ts), timezone.utc), "detail": None})
        return sorted(out, key=lambda x: x["name"])

    _sys_cache: dict = {"t": 0.0, "v": None}

    @api.get("/system", response_model=SystemStatus, summary="Trạng thái hệ thống: service, stream, độ mới dữ liệu")
    async def system(request: Request, repo: Repo_):
        if _sys_cache["v"] is not None and time.monotonic() - _sys_cache["t"] < 5:
            return _sys_cache["v"]
        now = datetime.now(timezone.utc)
        r = request.app.state.redis

        async def stream_info(name: str) -> dict:
            info = {"stream": name, "length": None, "last_event_at": None, "lag_seconds": None, "_source": None}
            try:
                info["length"] = int(await r.xlen(name))
                last = await r.xrevrange(name, count=1)
                if last:
                    mid, fields = last[0]
                    t = datetime.fromtimestamp(int(mid.split("-")[0]) / 1000, timezone.utc)
                    info["last_event_at"] = t
                    info["lag_seconds"] = max(0.0, (now - t).total_seconds())
                    with contextlib.suppress(Exception):
                        info["_source"] = json.loads(fields["e"]).get("source")
            except Exception:  # noqa: BLE001
                pass
            return info

        streams, fresh = await asyncio.gather(asyncio.gather(*(stream_info(n) for n in sorted(ALLOWED_STREAMS))),
                                              repo.freshness())
        services, src = None, "none"
        if settings.prometheus_url:
            services = await asyncio.to_thread(_prom_up)
            src = "prometheus" if services is not None else "none"
        if services is None:  # fallback: suy ra từ sự kiện cuối của từng nguồn phát
            by: dict[str, datetime] = {}
            for st in streams:
                if st["_source"] and st["last_event_at"]:
                    by[st["_source"]] = max(by.get(st["_source"], st["last_event_at"]), st["last_event_at"])
            services = [{"name": n, "up": (now - t).total_seconds() < 900, "last_scrape": t,
                         "detail": "suy ra từ sự kiện cuối (không có Prometheus)"} for n, t in sorted(by.items())]
            src = "redis" if services else "none"
        sources = [{**f, "age_seconds": (now - f["last_ts"]).total_seconds() if f.get("last_ts") else None} for f in fresh]
        out = {"generated_at": now, "services_source": src, "services": services,
               "streams": [{k: v for k, v in st.items() if k != "_source"} for st in streams],
               "sources": sources, "ws_connections": app.state.ws_count, "version": __version__}
        _sys_cache.update(t=time.monotonic(), v=out)
        return out

    register_symbol_routes(api, get_repo)  # /v1/symbols, /v1/symbols/classes (registry loai tai san)
    register_risk_routes(api, get_repo)  # /v1/risk-windows, /v1/risk-windows/status (bo loc rui ro tin)
    register_paper_routes(api)  # /v1/paper/* : proxy GET chi-doc toi paper-trader (MO PHONG)
    register_reports_routes(api)  # /v1/reports : proxy GET chi-doc toi reporter (bao cao ngay/tuan HTML+PDF)
    register_vn_routes(api)  # /v1/vn/* : proxy GET chi-doc toi vn-market (chung khoan VN cuoi ngay)
    register_riskmon_routes(api)  # /v1/risk/* : proxy GET chi-doc toi risk-monitor (rui ro tai khoan, READ-ONLY)
    register_patterns_routes(api)  # /v1/patterns* : proxy GET chi-doc toi pattern-engine (kich ban Sell KB-1..4, CHI thong tin; client chi thay armed|triggered)
    register_ai_trading_routes(api, lambda: settings.api_tokens[0] if settings.api_tokens else _csrf_fallback)  # /v1/ai-trading/*: proxy toi ai-trading (client chi overview/strategies/arena rut gon)
    register_pattern_scan_routes(api)  # /v1/patterns/{live,setup,media,trades,stats,examples}: proxy GET toi pattern-scan (anh + paper; client bi ep audience=client)
    register_datasource_routes(api, settings.hide_sources)  # /v1/data-sources : trang thai nguon mien phi + doi chieu nguon gia
    _csrf_fallback = os.urandom(16).hex()
    register_user_routes(api, lambda: settings.api_tokens[0] if settings.api_tokens else _csrf_fallback)  # /v1/user/*: NHOM GHI DUY NHAT (canh bao + prefs, whitelist, CSRF)
    register_journal_routes(api, lambda: settings.api_tokens[0] if settings.api_tokens else _csrf_fallback)  # /v1/journal/*: doc nhat ky; ghi CHI tag/ghi chu (whitelist, CSRF)
    register_account_reports_routes(api, lambda: settings.api_tokens[0] if settings.api_tokens else _csrf_fallback)  # /v1/account-reports*: báo cáo theo tài khoản (docs/FLEET_MGMT.md §5)
    register_track_routes(api)  # /v1/experts/{leaderboard,consensus,feed,methodology,chain/verify,{id}/track-record}: proxy GET chi-doc toi track-record
    register_briefing_routes(api)  # /v1/briefing/*: bản tin AI (chỉ đọc, whitelist)
    register_datakeeper_routes(api, lambda: settings.api_tokens[0] if settings.api_tokens else _csrf_fallback)  # /v1/data/*: trang Dữ liệu (data-keeper), CHỈ master
    register_intel_routes(api, get_repo)  # /v1/intel/*: thông tin thị trường tổng hợp (sức mạnh tiền tệ, heatmap, movers, tương quan, nhịp thị trường, tin, lịch sử lịch)

    app.include_router(api)

    # RS-2/UX-S2-2: DB quá tải/statement timeout/mất kết nối -> 503 JSON + Retry-After (thay vì 500 thô "Internal Server Error")
    import asyncpg

    async def _db_busy(request: Request, exc: Exception):
        log.warning("db busy %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse({"detail": "Cơ sở dữ liệu đang bận, vui lòng thử lại", "code": "db_busy"}, status_code=503,
                            headers={"Retry-After": "3", "Cache-Control": "no-store"})

    for _exc in (asyncpg.QueryCanceledError, asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError,
                 asyncpg.InterfaceError, asyncio.TimeoutError):
        app.add_exception_handler(_exc, _db_busy)

    @app.middleware("http")
    async def hide_sources_mw(request: Request, call_next):
        """HIDE_SOURCES: go ten nguon khoi moi phan hoi /v1/* (JSON: khoa/gia tri; HTML bao cao: van ban). PDF giu nguyen."""
        resp = await call_next(request)
        path = request.url.path
        if not settings.hide_sources or not path.startswith("/v1/") or path.startswith(_SCRUB_SKIP_PATHS):
            return resp
        ctype = resp.headers.get("content-type", "").lower()
        is_json, is_html = "json" in ctype, "text/html" in ctype
        if not (is_json or is_html) or resp.status_code == 204:
            return resp
        body = b"".join([chunk async for chunk in resp.body_iterator])
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in {"content-length", "content-type"}}
        def _scrub(b: bytes) -> bytes:
            if is_json:
                return json.dumps(scrub_obj(json.loads(b)), ensure_ascii=False, separators=(",", ":")).encode()
            return scrub_sources(b.decode("utf-8")).encode()
        try:
            # R3-11: body lớn (vd /v1/bars 5000 nến) scrub mất hàng trăm ms CPU -> chạy ở thread để không chặn event loop (hub realtime)
            body = await asyncio.to_thread(_scrub, body) if len(body) > _SCRUB_THREAD_BYTES else _scrub(body)
        except Exception:  # noqa: BLE001  (khong the phan tich -> tra nguyen, khong lam hong endpoint)
            log.exception("hide_sources: khong xu ly duoc %s", path)
        return Response(content=body, status_code=resp.status_code, headers=headers, media_type=resp.media_type or ctype.split(";")[0])

    # Cache phản hồi (Redis, SWR, single-flight, vô hiệu hoá theo bus): NGOÀI hide_sources_mw (lưu bản đã gỡ tên nguồn), TRONG count_requests (SLO). docs/PERFORMANCE.md
    app.add_middleware(CacheMiddleware, cache=cache if cache is not None else ResponseCache.from_env(), settings=settings)

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        t0 = time.perf_counter()
        resp = await call_next(request)
        if request.url.path.startswith("/v1"):
            route = request.scope.get("route")
            rpath = getattr(route, "path", "other")
            HTTP_REQS.labels(rpath, str(resp.status_code)).inc()
            HTTP_LAT.labels(rpath).observe(time.perf_counter() - t0)
        return resp

    @app.get("/readyz", tags=["ops"], summary="Kiểm tra kết nối DB")
    async def readyz(request: Request):
        try:
            ok = await asyncio.wait_for(request.app.state.repo.ping(), 3)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            raise HTTPException(503, "db unavailable")
        return {"status": "ready"}

    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def ui():
        return HTMLResponse(resources.files("api_gateway").joinpath("ui/index.html").read_text(encoding="utf-8"))

    # ---------------- WebSocket ----------------
    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket, streams: str | None = None, symbols: str | None = None):
        """Đẩy realtime sự kiện từ Redis Streams (XREAD từ thời điểm kết nối).
        Auth: header `X-API-Key` hoặc tin nhắn đầu tiên `{"type":"auth","api_key":"..."}` (trình duyệt không đặt được header).
        Query: `streams` (CSV tên stream, mặc định tất cả), `symbols` (CSV lọc theo symbol)."""
        try:
            principal = principal_from_headers(ws.headers, settings.auth_trust_secret)   # nginx dat header sau auth_request; gia mao -> dong
        except HTTPException:
            await ws.close(code=1008, reason="forbidden")
            return
        if os.getenv("RT_CHECK_ORIGIN", "1").lower() not in {"0", "false", "no", "off"} and not _ws_origin_ok(
                ws.headers, {x.strip().lower() for x in os.getenv("RT_ALLOWED_ORIGINS", "").split(",") if x.strip()}):
            await ws.close(code=1008, reason="forbidden")       # chống CSWSH (trang cùng "site" khác origin dùng cookie SameSite=Strict); cùng chính sách /v1/rt
            return
        names = _csv(streams) or sorted(ALLOWED_STREAMS if principal.is_master else ALLOWED_STREAMS & WS_CLIENT_STREAMS)
        if not principal.is_master and not set(names) <= WS_CLIENT_STREAMS:
            await ws.close(code=1008, reason="stream không được phép")
            return
        if not set(names) <= ALLOWED_STREAMS:
            await ws.close(code=1008, reason="stream không hợp lệ")
            return
        wanted = set(_csv(symbols) or [])
        if app.state.ws_count >= settings.ws_max_connections:
            await ws.close(code=1013, reason="quá nhiều kết nối")
            return
        await ws.accept()
        authed = token_ok(ws.headers.get("x-api-key"), settings.api_tokens, settings.auth_disabled)
        if not authed:
            try:
                first = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
                authed = first.get("type") == "auth" and token_ok(first.get("api_key"), settings.api_tokens)
            except Exception:  # noqa: BLE001
                authed = False
        if not authed:
            await ws.close(code=1008, reason="unauthorized")
            return
        app.state.ws_count += 1
        WS_CONNS.inc()
        await ws.send_json({"type": "ready", "streams": names})
        r = app.state.redis
        last = {n: "$" for n in names}

        async def pump():
            while True:
                res = await r.xread(last, count=100, block=1000)
                for st, msgs in res or []:
                    for mid, fields in msgs:
                        last[st] = mid
                        try:
                            ev = json.loads(fields["e"])
                        except (KeyError, ValueError):
                            continue
                        if not event_visible(principal, ev, strict=st.startswith("account.")):
                            continue   # su kien cua tai khoan khac: khong gui cho client
                        if wanted:
                            p = ev.get("payload", {})
                            syms = {p.get("symbol"), *(p.get("symbols") or [])}
                            if not wanted & syms:
                                continue
                        # cùng một sự kiện gửi cho N kết nối: scrub + serialize MỘT lần (trước đây lặp N lần -> gateway 95% CPU, trễ bus->hub p95 ~1 s)
                        key = (st, mid)
                        txt = ev_txt.get(key)
                        if txt is None:
                            ev2 = ev
                            if settings.hide_sources and isinstance(ev.get("payload"), dict):
                                ev2 = {**ev, "payload": _scrub_payload(ev["payload"])}
                            txt = json.dumps({"type": "event", "stream": st, "id": mid, "event": ev2})
                            ev_txt[key] = txt
                            if len(ev_txt) > 512:
                                ev_txt.popitem(last=False)
                        try:
                            await ws.send_text(txt)
                        except (WebSocketDisconnect, RuntimeError, OSError, ConnectionError):
                            return   # RS-11: client đã đóng -> dừng pump, tránh uvicorn lặp cảnh báo socket.send()

        async def reader():  # phát hiện client đóng; bỏ qua nội dung
            while True:
                await ws.receive_text()

        tasks = [asyncio.create_task(pump()), asyncio.create_task(reader())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            # KHÔNG nuốt CancelledError và KHÔNG await gather(task con) ở đây: TestClient/anyio huỷ handler khi client ngắt, và gather bị huỷ giữa chừng
            # làm CancelledError rò ra phía gọi (test WS chập chờn ~1/300; tái hiện bằng starlette thuần). Task con chỉ cần cancel(), tự kết thúc.
            app.state.ws_count -= 1       # giảm bộ đếm TRƯỚC mọi await: handler bị huỷ khi dọn dẹp thì không rò rỉ slot kết nối
            WS_CONNS.dec()
            for t in tasks:
                t.cancel()
                t.add_done_callback(_reap)
            with contextlib.suppress(Exception):
                await ws.close()

    register_realtime(app, settings)   # /v1/rt (WS) + /v1/rt/sse: hub dùng chung, docs/REALTIME.md

    return app

