"""Nguon 'actual' cho lich kinh te: so lieu goc tu co quan thong ke (API cong khai) ngay khi duoc cong bo.

Khong tu phat su kien; Source nay chi doc `ctx.book` (CalendarBook), tham do provider theo lich thua dan sau gio cong bo
(config `poll_schedule_min`), roi `book.set_actual(...)`; Runner phat lai hang lich da co actual (upsert theo event_id+source).

Provider (deu da kiem tra that tu VPS 2026-10-11, fixture `tests/fixtures/real_act_*.json`):
- bls      Hoa Ky, BLS Public API v1 (KHONG key: 25 req/ngay, <=10 series/req, toi da 10 nam). Co BLS_API_KEY -> v2 (500 req/ngay).
- statcan  Canada, Statistics Canada WDS (khong key).
- ons      Anh, ONS time-series JSON (khong key).
- abs      Uc, ABS Data API SDMX-JSON (khong key).
- eurostat Khu vuc dong Euro, Eurostat JSON-stat (khong key). Dataset hien tai dung o 2025-12 -> ky tham chieu giu khong cho nhan so cu.
- fred     FRED API (CAN key mien phi FRED_API_KEY; khong co key -> bo qua cac chi so fred). CHUA kiem chung voi key that.
- boj      Nhat, BoJ Time-Series Data Search API (khong key, JSON; kiem tra that 2026-10-14, fixture real_act_boj_*.json).

Ghi chu 2026-10-14: Eurostat thay bo HICP cu (prc_hicp_manr dong bang 2026-02) bang prc_hicp_minr (dimension coicop18,
unit RCH_A/RCH_M); khu vuc dong euro = EA21 o cac dataset lao dong/kinh doanh (EA cho HICP).
Nguon da xet nhung KHONG dung: lich Fair Economy khong co truong actual; api.nasdaq.com (robots.txt Disallow: /);
api.census.gov (nay bat buoc key); Investing/ForexFactory HTML (ToS cam scrape).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..calendar_book import expected_period, indicator_value
from ..models import Emit
from .base import Context, Source

log = logging.getLogger("news_collector.actuals")

BLS_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_V2 = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
STATCAN = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"
ONS = "https://www.ons.gov.uk/{path}/timeseries/{id}/{dataset}/data"
ABS = "https://data.api.abs.gov.au/rest/data/ABS,{flow},1.0.0/{key}"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
FRED = "https://api.stlouisfed.org/fred/series/observations"
BOJ = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
_MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


# ---- Phan tich phan hoi (ham thuan) -----------------------------------------------------------------
def parse_bls(body: bytes) -> dict[str, dict[str, float]]:
    d = json.loads(body)
    if d.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS: {d.get('status')} {' '.join(d.get('message') or [])[:200]}")
    out: dict[str, dict[str, float]] = {}
    for s in d["Results"]["series"]:
        pts = {}
        for r in s["data"]:
            if r["period"].startswith("M") and r["period"] != "M13":  # M13 = trung binh nam
                try:
                    pts[f"{r['year']}-{r['period'][1:]}"] = float(r["value"])
                except ValueError:
                    pass  # '-' = khong co du lieu
        out[s["seriesID"]] = pts
    return out


def parse_statcan(body: bytes) -> dict[str, dict[str, float]]:
    out = {}
    for r in json.loads(body):
        if r.get("status") != "SUCCESS":
            continue
        o = r["object"]
        out[str(o["vectorId"])] = {p["refPer"][:7]: float(p["value"]) for p in o["vectorDataPoint"] if p.get("value") is not None}
    return out


def parse_ons(body: bytes) -> dict[str, float]:
    out = {}
    for m in json.loads(body).get("months", []):
        y, mon = m["date"].split()
        try:
            out[f"{y}-{_MON[mon.upper()]:02d}"] = float(m["value"])
        except (KeyError, ValueError):
            pass
    return out


def parse_abs(body: bytes) -> dict[str, float]:
    d = json.loads(body)
    st = d["data"].get("structures") or [d["data"]["structure"]]
    times = [v["id"] for v in st[0]["dimensions"]["observation"][0]["values"]]
    out = {}
    for s in d["data"]["dataSets"][0]["series"].values():
        for i, o in s["observations"].items():
            if o and o[0] is not None:
                out[times[int(i)][:7]] = float(o[0])
    return out


def parse_eurostat(body: bytes) -> dict[str, float]:
    d = json.loads(body)
    idx = d["dimension"]["time"]["category"]["index"]
    return {t: float(d["value"][str(i)]) for t, i in idx.items() if str(i) in (d.get("value") or {}) and d["value"][str(i)] is not None}


def parse_fred(body: bytes) -> dict[str, float]:
    out = {}
    for o in json.loads(body).get("observations", []):
        try:
            out[o["date"][:7]] = float(o["value"])
        except ValueError:
            pass  # '.' = thieu
    return out


def parse_boj(body: bytes) -> dict[str, dict[str, float]]:
    """BoJ getDataCode JSON -> {ma chuoi: {YYYY-MM: gia tri}} (chi tan suat thang)."""
    d = json.loads(body)
    if d.get("STATUS") != 200:
        raise ValueError(f"BoJ: {d.get('STATUS')} {d.get('MESSAGEID')} {str(d.get('MESSAGE'))[:200]}")
    out: dict[str, dict[str, float]] = {}
    for s in d.get("RESULTSET") or []:
        v = s.get("VALUES") or {}
        pts = {}
        for t, x in zip(v.get("SURVEY_DATES") or [], v.get("VALUES") or []):
            t = str(t)
            try:
                if len(t) == 6 and x not in (None, ""):
                    pts[f"{t[:4]}-{t[4:]}"] = float(x)
            except (TypeError, ValueError):
                pass  # o trong / ky hieu thieu so lieu
        out[s["SERIES_CODE"]] = pts
    return out


# ---- Provider (I/O qua ctx.client) ------------------------------------------------------------------
class Provider:
    name = ""

    def __init__(self, daily_cap: int):
        self.daily_cap, self.calls, self.day = daily_cap, 0, ""

    def budget_ok(self, now: datetime, need: int = 1) -> bool:
        d = now.strftime("%Y%m%d")
        if d != self.day:
            self.day, self.calls = d, 0
        return self.calls + need <= self.daily_cap

    async def fetch(self, ctx: Context, series: list[str], now: datetime) -> dict[str, dict[str, float]]:  # pragma: no cover
        raise NotImplementedError


class BlsProvider(Provider):
    name = "bls"

    def __init__(self, daily_cap: int, api_key: str = ""):
        super().__init__(daily_cap)
        self.api_key = api_key

    async def fetch(self, ctx, series, now):
        out: dict[str, dict[str, float]] = {}
        step = 50 if self.api_key else 10
        for i in range(0, len(series), step):
            chunk = series[i:i + step]
            body = {"seriesid": chunk, "startyear": str(now.year - (2 if not self.api_key else 3)), "endyear": str(now.year)}
            if self.api_key:
                body["registrationkey"] = self.api_key
            self.calls += 1
            try:
                raw = await ctx.client.post_json(BLS_V2 if self.api_key else BLS_V1, body)
            except Exception as ex:  # khong de key lot vao log
                raise RuntimeError(f"BLS loi {type(ex).__name__}: {str(ex).replace(self.api_key or '\0', '***')[:200]}") from None
            out.update(parse_bls(raw))
        return out


class StatCanProvider(Provider):
    name = "statcan"

    async def fetch(self, ctx, series, now):
        self.calls += 1
        raw = await ctx.client.post_json(STATCAN, [{"vectorId": int(v), "latestN": 16} for v in series])
        return parse_statcan(raw)


class OnsProvider(Provider):
    name = "ons"

    async def fetch(self, ctx, series, now):
        out = {}
        for s in series:  # "muc/duong/dan|id|dataset"
            path, sid, ds = s.split("|")
            self.calls += 1
            body, _ = await ctx.client.get(ONS.format(path=path, id=sid, dataset=ds), use_cache=False)
            out[s] = parse_ons(body)
        return out


class AbsProvider(Provider):
    name = "abs"

    async def fetch(self, ctx, series, now):
        out = {}
        for s in series:  # "FLOW|key"
            flow, key = s.split("|")
            self.calls += 1
            body, _ = await ctx.client.get(ABS.format(flow=flow, key=key), params={"lastNObservations": 18},
                                           headers={"Accept": "application/vnd.sdmx.data+json"}, use_cache=False)
            out[s] = parse_abs(body)
        return out


class EurostatProvider(Provider):
    name = "eurostat"

    async def fetch(self, ctx, series, now):
        out = {}
        for s in series:  # "dataset|k=v&k=v"
            ds, q = s.split("|")
            params = dict(kv.split("=") for kv in q.split("&"))
            params.update({"format": "JSON", "sinceTimePeriod": f"{now.year - 2}-01"})
            self.calls += 1
            body, _ = await ctx.client.get(EUROSTAT.format(dataset=ds), params=params, use_cache=False)
            out[s] = parse_eurostat(body)
        return out


class FredProvider(Provider):
    name = "fred"

    def __init__(self, daily_cap: int, api_key: str):
        super().__init__(daily_cap)
        self.api_key = api_key

    async def fetch(self, ctx, series, now):
        out = {}
        for s in series:
            self.calls += 1
            try:
                body, _ = await ctx.client.get(FRED, params={"series_id": s, "api_key": self.api_key, "file_type": "json",
                                                             "observation_start": f"{now.year - 2}-01-01"}, use_cache=False)
            except Exception as ex:
                raise RuntimeError(f"FRED loi {type(ex).__name__}: {str(ex).replace(self.api_key, '***')[:200]}") from None
            out[s] = parse_fred(body)
        return out


class BojProvider(Provider):
    name = "boj"

    async def fetch(self, ctx, series, now):
        out = {}
        for s in series:  # "DB|MA_CHUOI"
            db, code = s.split("|")
            self.calls += 1
            body, _ = await ctx.client.get(BOJ, params={"format": "json", "lang": "en", "db": db, "code": code,
                                                        "startDate": f"{now.year - 2}01"}, use_cache=False)
            out[s] = parse_boj(body).get(code, {})
        return out


def build_providers(cfg: dict, bls_key: str = "", fred_key: str = "") -> dict[str, Provider]:
    caps = cfg.get("providers", {})
    bls_cap = caps.get("bls", {}).get("daily_cap_with_key" if bls_key else "daily_cap", 22)
    prov: dict[str, Provider] = {
        "bls": BlsProvider(bls_cap, bls_key), "statcan": StatCanProvider(caps.get("statcan", {}).get("daily_cap", 200)),
        "ons": OnsProvider(caps.get("ons", {}).get("daily_cap", 200)), "abs": AbsProvider(caps.get("abs", {}).get("daily_cap", 100)),
        "eurostat": EurostatProvider(caps.get("eurostat", {}).get("daily_cap", 100)),
        "boj": BojProvider(caps.get("boj", {}).get("daily_cap", 100))}
    if fred_key:
        prov["fred"] = FredProvider(caps.get("fred", {}).get("daily_cap", 500), fred_key)
    return prov


class ActualsSource(Source):
    """Tham do 'actual' cho su kien lich da toi gio. Moi vong chi goi mang khi co su kien den luot (xem CalendarBook.pending)."""
    name = "cal_actuals"

    def __init__(self, providers: dict[str, Provider], interval: float = 30):
        self.providers, self.interval = providers, interval
        self.last: dict = {"filled": 0, "last_error": None}

    async def fetch(self, ctx: Context) -> list[Emit]:
        book, now = ctx.book, ctx.now()
        if book is None:
            return []
        due = book.pending(now)
        by: dict[str, list] = {}
        for key, p, ind in due:
            by.setdefault(ind["provider"], []).append((key, p, ind))
        for prov_name, items in by.items():
            prov = self.providers.get(prov_name)
            if prov is None:  # vd fred khong co key
                continue
            series = sorted({i["series"] for _, _, i in items})
            step = 50 if (prov_name == "bls" and getattr(prov, "api_key", "")) else 10
            need = -(-len(series) // step) if prov_name == "bls" else len(series)
            if not prov.budget_ok(now, need):
                log.warning("provider %s het ngan sach request hom nay (%d)", prov_name, prov.daily_cap)
                continue
            for key, _, _ in items:
                book.mark_attempt(key)
            try:
                data = await prov.fetch(ctx, series, now)
            except Exception as ex:  # noqa: BLE001 - loi mot provider khong chan provider khac
                self.last["last_error"] = f"{prov_name}: {type(ex).__name__}: {ex}"
                log.warning("actuals %s loi: %s", prov_name, ex)
                continue
            for key, p, ind in items:
                pts = data.get(ind["series"])
                if not pts:
                    continue
                per = expected_period(datetime.fromisoformat(p["ts"]), ind.get("lag_months", 1))
                val, prev = indicator_value(pts, per, ind)
                if val is None:
                    continue  # chua cong bo ky nay (hoac dataset cu) -> de thu lai theo lich
                book.set_actual(key, val, prev, ind, per, now)
                self.last["filled"] += 1
                log.info("actual %s %s = %.4g (ky %s, %s)", p["country"], p["title"], val, per, prov_name)
        return []
