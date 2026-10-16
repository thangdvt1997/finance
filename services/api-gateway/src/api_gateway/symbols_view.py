"""`GET /v1/symbols` (mo rong theo loai tai san) + `GET /v1/symbols/classes`.

Registry loai tai san: `tscommon.assets` (assets.yaml). Gia `last` va `change_pct` re: 1 truy van quotes moi nhat + 1 truy van 3 nen D1
gan nhat/ symbol (repo.price_snapshot). Quy tac: quote moi (<= 6 gio) -> last = mid, tham chieu = dong cua D1 cua ngay UTC TRUOC ngay cua quote
(crypto: dong cua 00:00 UTC; co phieu co quote: dong cua phien truoc); khong co quote moi -> last = dong cua D1 moi nhat, tham chieu = D1 truoc do.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from tscommon import assets

QUOTE_FRESH = timedelta(hours=6)


class SymbolItem(BaseModel):
    """Phan tu `GET /v1/symbols`. Truong cu (symbol,tfs,last_bar,last_quote) giu nguyen; cac truong con lai la BO SUNG."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    symbol: str
    tfs: list[str] = []
    last_bar: datetime | None = None
    last_quote: datetime | None = None
    class_: str = Field(alias="class", description="forex|crypto|metal|commodity|index|etf|stock_us|stock_vn|bond (|other: chua dang ky)")
    name: str
    name_en: str
    group: str | None = None
    quote_currency: str | None = None
    precision: int
    session: str = Field(description="crypto_24x7|fx_24x5|us_equity|vn_equity|eod_daily")
    session_open: bool | None = Field(None, description="Phien dang mo? (gio+thu, khong xet ngay le; null = so lieu cuoi ngay)")
    last: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    price_source: str | None = Field(None, description="quote|d1")
    price_ts: datetime | None = None
    registered: bool = True


class ClassItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    class_: str = Field(alias="class")
    name: str
    name_en: str
    order: int
    session: str | None = None
    precision: int | None = None
    quote_currency: str | None = None
    count: int = Field(description="So symbol dang co du lieu (bars/quotes)")
    groups: list[dict[str, Any]] = Field(default=[], description="[{group, count}]")


def _mid(q: dict) -> float | None:
    b, a = q.get("bid"), q.get("ask")
    vals = [x for x in (b, a) if x and x > 0]
    return sum(vals) / len(vals) if vals else None


def price_fields(quote: dict | None, d1: list[dict], now: datetime) -> dict:
    """quote: {ts,bid,ask}|None; d1: nen D1 moi nhat truoc ([{ts_open,c}], giam dan theo ts_open)."""
    d1 = sorted((x for x in d1 if x.get("c")), key=lambda x: x["ts_open"], reverse=True)
    last = ref = ts = src = None
    if quote and (m := _mid(quote)) and now - quote["ts"] <= QUOTE_FRESH:
        last, ts, src = m, quote["ts"], "quote"
        day = quote["ts"].astimezone(timezone.utc).date()
        prev = [x for x in d1 if x["ts_open"].astimezone(timezone.utc).date() < day]
        ref = prev[0]["c"] if prev else None
    elif d1:
        last, ts, src = d1[0]["c"], d1[0]["ts_open"], "d1"
        ref = d1[1]["c"] if len(d1) > 1 else None
    chg = (last / ref - 1) * 100 if last and ref else None
    return {"last": last, "prev_close": ref, "change_pct": round(chg, 3) if chg is not None else None,
            "price_source": src, "price_ts": ts}


def build_items(syms: list[dict], snap: dict, now: datetime, cls: str | None = None, prices: bool = True) -> list[dict]:
    out = []
    quotes, d1s = snap.get("quotes", {}), snap.get("d1", {})
    for r in syms:
        info = assets.asset_info(r["symbol"])
        if cls and info.cls != cls:
            continue
        item = {**r, **assets.as_public(info, now)}
        if prices:
            item.update(price_fields(quotes.get(r["symbol"]), d1s.get(r["symbol"], []), now))
        out.append(item)
    out.sort(key=lambda i: (assets.CLASSES.index(i["class"]) if i["class"] in assets.CLASSES else 99, i["group"] or "", i["symbol"]))
    return out


def build_classes(syms: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    groups: dict[str, dict[str, int]] = {}
    for r in syms:
        info = assets.asset_info(r["symbol"])
        counts[info.cls] = counts.get(info.cls, 0) + 1
        g = groups.setdefault(info.cls, {})
        g[info.group or ""] = g.get(info.group or "", 0) + 1
    out = []
    for c in assets.class_infos():
        n = counts.get(c["class"], 0)
        if c["class"] == assets.OTHER and n == 0:
            continue
        out.append({**c, "count": n, "groups": [{"group": k or None, "count": v} for k, v in sorted(groups.get(c["class"], {}).items())]})
    return out


def register_symbol_routes(api: APIRouter, get_repo: Callable) -> None:
    @api.get("/symbols", response_model=list[SymbolItem], response_model_by_alias=True,
             summary="Symbol co du lieu + loai tai san (class), ten, nhom, phien, gia/% thay doi")
    async def symbols(request: Request,
                      class_: Annotated[str | None, Query(alias="class", pattern=r"^[a-z_]{1,16}$",
                                                           description="Loc theo loai: forex|crypto|metal|commodity|index|etf|stock_us|stock_vn|bond")] = None,
                      prices: Annotated[bool, Query(description="Kem last/prev_close/change_pct (rẻ: 2 truy van)")] = True):
        repo = get_repo(request)
        now = datetime.now(timezone.utc)
        syms = await repo.symbols()
        snap = await repo.price_snapshot() if prices else {}
        return build_items(syms, snap, now, class_, prices)

    @api.get("/symbols/classes", response_model=list[ClassItem], response_model_by_alias=True,
             summary="Cac loai tai san + so symbol co du lieu moi loai (va nhom con)")
    async def symbol_classes(request: Request):
        return build_classes(await get_repo(request).symbols())
