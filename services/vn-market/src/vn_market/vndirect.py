"""Client + bộ phân tích cho API công khai VNDirect finfo (api-finfo.vndirect.com.vn/v4): nguồn dữ liệu cuối ngày CHÍNH của vn-market.

Đã kiểm tra thật từ VPS (2026-10-12): không cần key/đăng nhập, không bị chặn anti-bot (khác SSI iBoard 403 và TCBS Cloudflare 403 -> KHÔNG dùng).
Đây là API KHÔNG CHÍNH THỨC (web VNDirect dùng): có thể đổi/chặn bất cứ lúc nào; chỉ dùng cá nhân, tự giới hạn tốc độ (mặc định >= 0.8s/request),
User-Agent khai báo rõ, không cào trang HTML. Toàn bộ là dữ liệu CUỐI NGÀY (cập nhật ~15:10 giờ VN), KHÔNG realtime.

Đơn vị nguồn: giá theo NGHÌN đồng (57.7 = 57.700đ) -> nhân 1000 thành VND thật (hợp đồng CONTRACTS.md); khối lượng = cp; giá trị = VND;
chỉ số điểm giữ nguyên. Ratios: tỷ lệ phần trăm ở dạng phân số (0.049 = 4,9%).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from typing import Any

import httpx

log = logging.getLogger("vn_market.vndirect")

BASE_URL = "https://api-finfo.vndirect.com.vn/v4"
UA = "trading-system-vn-market/0.1 (personal research, read-only; contact: set USER_AGENT)"
PRICE_MULT = 1000.0

# mã ratio cần lấy -> cột vn_ratios
RATIO_CODES = {
    "MARKETCAP": "marketcap", "PRICE_TO_EARNINGS": "pe", "PRICE_TO_BOOK": "pb", "PRICE_TO_SALES": "ps",
    "DIVIDEND_YIELD": "div_yield", "BETA": "beta", "BVPS_CR": "bvps",
    "PRICE_CHG_PCT_CR_1M": "chg_1m", "PRICE_CHG_PCT_CR_3M": "chg_3m", "PRICE_CHG_PCT_CR_6M": "chg_6m", "PRICE_CHG_PCT_CR_1Y": "chg_1y",
    "PRICE_HIGHEST_CR_52W": "hi_52w", "PRICE_LOWEST_CR_52W": "lo_52w",
}
EVENT_TYPES = ("DIVIDEND", "STOCKDIV", "KINDDIV", "ISSUE", "MEETING", "meetingRight", "POLL")


class SourceError(Exception):
    pass


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _px(v: Any) -> float | None:
    x = _f(v)
    return None if x is None else round(x * PRICE_MULT, 4)


def _d(v: Any) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _i(v: Any) -> int | None:
    x = _f(v)
    return None if x is None else int(x)


class VNDirectClient:
    def __init__(self, http: httpx.AsyncClient | None = None, *, base_url: str = BASE_URL, min_interval: float = 0.8,
                 user_agent: str = UA, retries: int = 3):
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0), headers={"User-Agent": user_agent, "Accept": "application/json"},
                                               follow_redirects=False)
        self._own = http is None
        self.base = base_url.rstrip("/")
        self.min_interval = min_interval
        self.retries = retries
        self._last = 0.0
        self._lock = asyncio.Lock()
        self.requests = 0

    async def aclose(self) -> None:
        if self._own:
            await self._http.aclose()

    async def get(self, path: str, **params: Any) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        err: Exception | None = None
        for attempt in range(self.retries):
            async with self._lock:  # tự giới hạn tốc độ: tuần tự, cách nhau >= min_interval
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            self.requests += 1
            try:
                r = await self._http.get(f"{self.base}/{path.lstrip('/')}", params=params)
                if r.status_code == 429 or r.status_code >= 500:
                    raise SourceError(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    raise SourceError(f"HTTP {r.status_code} (không thử lại)") from None
                j = r.json()
                if not isinstance(j, dict):
                    raise SourceError("phản hồi không phải JSON object")
                return j
            except (httpx.HTTPError, ValueError, SourceError) as e:
                err = e
                if isinstance(e, SourceError) and "không thử lại" in str(e):
                    break
                await asyncio.sleep(min(2.0 * (attempt + 1), 8.0))
        raise SourceError(f"{path}: {err}")

    async def fetch_all(self, path: str, q: str, *, size: int = 3000, sort: str | None = None, fields: str | None = None, max_pages: int = 20) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            j = await self.get(path, q=q, size=size, page=page, sort=sort, fields=fields)
            data = j.get("data") or []
            out.extend(data)
            total = int(j.get("totalElements") or 0)
            if not data or len(out) >= total:
                break
        return out

    # ---- truy vấn mức cao -------------------------------------------------------------------------------------------------
    async def listed_symbols(self) -> list[dict]:
        return await self.fetch_all("stocks", "type:STOCK,ETF~status:listed", size=3000,
                                    fields="code,floor,type,companyName,shortName,listedDate,indexCode")

    async def latest_session(self) -> date | None:
        j = await self.get("vnmarket_prices", q="code:VNINDEX", size=1, sort="date")
        rows = j.get("data") or []
        return _d(rows[0].get("date")) if rows else None

    async def prices_on(self, floor: str, d: date) -> list[dict]:
        return await self.fetch_all("stock_prices", f"floor:{floor}~date:{d.isoformat()}", size=3000)

    async def price_history(self, code: str, start: date) -> list[dict]:
        return await self.fetch_all("stock_prices", f"code:{code}~date:gte:{start.isoformat()}", size=3000, sort="date")

    async def indices_on(self, d: date) -> list[dict]:
        return await self.fetch_all("vnmarket_prices", f"date:{d.isoformat()}", size=500)

    async def index_history(self, code: str, start: date) -> list[dict]:
        return await self.fetch_all("vnmarket_prices", f"code:{code}~date:gte:{start.isoformat()}", size=3000, sort="date")

    async def foreign_on(self, d: date) -> list[dict]:
        return await self.fetch_all("foreigns", f"tradingDate:{d.isoformat()}~type:STOCK,ETF", size=3000)

    async def foreign_history(self, code: str, start: date) -> list[dict]:
        return await self.fetch_all("foreigns", f"code:{code}~tradingDate:gte:{start.isoformat()}", size=3000, sort="tradingDate")

    async def ratio_on(self, ratio_code: str, d: date) -> list[dict]:
        return await self.fetch_all("ratios", f"reportDate:{d.isoformat()}~ratioCode:{ratio_code}", size=10000)

    async def events_between(self, start: date, end: date) -> list[dict]:
        q = f"locale:VN~group:investorRight~effectiveDate:gte:{start.isoformat()}~effectiveDate:lte:{end.isoformat()}"
        return await self.fetch_all("events", q, size=3000, sort="effectiveDate")


# ---- phân tích bản ghi (hàm thuần, test không cần mạng) -------------------------------------------------------------------
def parse_price(r: dict) -> dict | None:
    d = _d(r.get("date"))
    code = (r.get("code") or "").strip().upper()
    if not d or not code:
        return None
    close = _px(r.get("close"))
    basic = _px(r.get("basicPrice"))
    return {
        "code": code, "d": d, "floor": r.get("floor") or "", "basic": basic, "ceil": _px(r.get("ceilingPrice")), "flr": _px(r.get("floorPrice")),
        "open": _px(r.get("open")), "high": _px(r.get("high")), "low": _px(r.get("low")), "close": close, "ad_close": _px(r.get("adClose")),
        "avg_price": _px(r.get("average")), "volume": _f(r.get("nmVolume")) or 0.0, "value": _f(r.get("nmValue")) or 0.0,
        "pt_volume": _f(r.get("ptVolume")) or 0.0, "pt_value": _f(r.get("ptValue")) or 0.0, "pct": _f(r.get("pctChange")),
        "kind": r.get("type") or "STOCK",
    }


def parse_index(r: dict) -> dict | None:
    d = _d(r.get("date"))
    code = (r.get("code") or "").strip().upper()
    if not d or not code:
        return None
    return {
        "code": code, "d": d, "floor": r.get("floor"), "kind": r.get("type"), "open": _f(r.get("open")), "high": _f(r.get("high")),
        "low": _f(r.get("low")), "close": _f(r.get("close")), "chg": _f(r.get("change")), "pct": _f(r.get("pctChange")),
        "volume": _f(r.get("nmVolume")), "value": _f(r.get("nmValue")), "pt_value": _f(r.get("ptValue")),
        "advances": _i(r.get("advances")), "declines": _i(r.get("declines")), "no_change": _i(r.get("noChange")), "no_trade": _i(r.get("noTrade")),
        "ceiling_n": _i(r.get("ceilingStocks")), "floor_n": _i(r.get("floorStocks")),
    }


def parse_foreign(r: dict) -> dict | None:
    d = _d(r.get("tradingDate"))
    code = (r.get("code") or "").strip().upper()
    if not d or not code or r.get("type") not in (None, "STOCK", "ETF"):
        return None
    return {"code": code, "d": d, "floor": r.get("floor"), "buy_val": _f(r.get("buyVal")), "sell_val": _f(r.get("sellVal")),
            "net_val": _f(r.get("netVal")), "buy_vol": _f(r.get("buyVol")), "sell_vol": _f(r.get("sellVol")), "net_vol": _f(r.get("netVol")),
            "total_room": _f(r.get("totalRoom")), "current_room": _f(r.get("currentRoom"))}


def merge_ratios(rows_by_ratio: dict[str, list[dict]], as_of: date) -> list[dict]:
    """Gộp các bản ghi ratio (mỗi mã ratio một danh sách) thành 1 dòng/mã cổ phiếu."""
    out: dict[str, dict] = {}
    for rc, rows in rows_by_ratio.items():
        col = RATIO_CODES.get(rc)
        if not col:
            continue
        for r in rows:
            code = (r.get("code") or "").strip().upper()
            v = _f(r.get("value"))
            if not code or v is None:
                continue
            out.setdefault(code, {"code": code, "as_of": as_of})[col] = v
    for row in out.values():
        for c in RATIO_CODES.values():
            row.setdefault(c, None)
        # EPS/ROE là SUY RA (P/E, P/B) -> tính ở analytics, không lưu
    return list(out.values())


def parse_event(r: dict) -> dict | None:
    if r.get("locale") not in (None, "VN") or r.get("type") not in EVENT_TYPES:
        return None
    eid = r.get("id")
    code = (r.get("code") or "").strip().upper()
    if not eid or not code:
        return None
    return {"event_id": str(eid), "code": code, "etype": r["type"], "type_desc": r.get("typeDesc"), "note": r.get("note"),
            "dividend": _f(r.get("dividend")), "ratio": _f(r.get("ratio")), "disclosure_date": _d(r.get("disclosureDate")),
            "effective_date": _d(r.get("effectiveDate")), "expired_date": _d(r.get("expiredDate")), "actual_date": _d(r.get("actualDate"))}
