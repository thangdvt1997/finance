"""Thu thập dữ liệu CHỈ-ĐỌC qua api-gateway nội bộ (HTTP GET + X-API-Key). Mỗi nguồn lỗi độc lập: trả (None, lỗi), không làm hỏng báo cáo."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("reporter.collect")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Raw:
    """Kết quả thu thập: data[tên] = JSON hoặc None; errors[tên] = chuỗi lỗi ngắn."""
    data: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def get(self, name: str, default=None):
        v = self.data.get(name)
        return default if v is None else v

    def ok(self, name: str) -> bool:
        return self.data.get(name) is not None


class Gateway:
    def __init__(self, cfg: Settings, client: httpx.AsyncClient | None = None):
        self.cfg = cfg
        self._own = client is None
        self.client = client or httpx.AsyncClient(base_url=cfg.gateway_url, headers={"X-API-Key": cfg.api_key, "Accept": "application/json"},
                                                  timeout=cfg.http_timeout)

    async def aclose(self):
        if self._own:
            await self.client.aclose()

    async def get(self, path: str, params: dict | None = None):
        r = await self.client.get("/v1" + path, params=params)
        r.raise_for_status()
        return r.json()


async def collect(cfg: Settings, kind: str, now: datetime, gw: Gateway | None = None) -> Raw:
    gw = gw or Gateway(cfg)
    raw = Raw()
    weekly = kind == "weekly"
    back = timedelta(days=7 if weekly else 1)
    ahead = timedelta(days=7 if weekly else 1)
    sem = asyncio.Semaphore(6)

    async def fetch(name: str, path: str, params: dict | None = None):
        async with sem:
            try:
                raw.data[name] = await gw.get(path, params)
            except Exception as e:  # noqa: BLE001  (một nguồn lỗi không được làm hỏng cả báo cáo)
                raw.data[name] = None
                code = getattr(getattr(e, "response", None), "status_code", None)
                raw.errors[name] = f"HTTP {code}" if code else type(e).__name__
                log.warning("nguồn %s lỗi: %s", name, raw.errors[name])

    jobs = [
        fetch("quotes", "/quotes/latest"),
        fetch("news", "/news", {"since": iso(now - back), "limit": 500}),
        fetch("calendar", "/calendar", {"from": iso(now), "to": iso(now + ahead + timedelta(hours=1)), "impact": "high,med", "order": "asc", "limit": 300}),
        fetch("signals", "/expert-signals", {"status": "open", "limit": 500}),
        fetch("accounts", "/accounts"),
        fetch("risk", "/risk/accounts"),
        fetch("analytics", "/analytics/overview"),
        fetch("system", "/system"),
        fetch("datasources", "/data-sources"),
        fetch("alerts", "/alerts", {"limit": 500}),
        fetch("paper_overview", "/paper/overview"),
    ]
    if not weekly:  # bản tin AI (service briefing) cho báo cáo ngày
        jobs.append(fetch("briefing", "/briefing/latest"))
    for _, sym, _ in cfg.instruments:
        jobs.append(fetch(f"bars:{sym}", "/bars", {"symbol": sym, "tf": "D1", "limit": 150, "order": "desc"}))
    # paper: danh sách tài khoản rồi stats + equity từng tài khoản
    pa_task = fetch("paper_accounts", "/paper/accounts")
    await asyncio.gather(*jobs, pa_task)
    items = (raw.data.get("paper_accounts") or {}).get("items") or []
    dep = {k for k, v in ((raw.data.get("paper_overview") or {}).get("cycle") or {}).get("accounts", {}).items()
           if isinstance(v, dict) and v.get("deprecated")}
    ids = [i["account_id"] for i in items if i.get("account_id") and i["account_id"] not in dep and not i.get("replay")]
    sub = []
    for aid in ids:
        sub.append(fetch(f"stats:{aid}", f"/paper/accounts/{aid}/stats"))
        sub.append(fetch(f"equity:{aid}", f"/paper/accounts/{aid}/equity", {"limit": 400}))
    await asyncio.gather(*sub)
    raw.data["_paper_ids"] = ids
    if weekly:  # nhat ky giao dich (journal): review tuan cho tai khoan co lenh DA DONG; bo qua tai khoan mo phong/fixture
        await fetch("journal_accounts", "/journal/accounts")
        wk = journal_week(now, cfg.tz)
        jids = [a["account_id"] for a in (raw.data.get("journal_accounts") or {}).get("items") or []
                if a.get("account_id") and (a.get("n_trades") or 0) > 0 and not str(a.get("source") or "").startswith("sim:")]
        raw.data["_journal_ids"] = jids[:12]
        raw.data["_journal_week"] = wk
        await asyncio.gather(*[fetch(f"journal:{i}", f"/journal/{i}/review", {"week": wk, "tz": cfg.tz}) for i in raw.data["_journal_ids"]])
    return raw


def journal_week(now: datetime, tz: str) -> str:
    """Nhan tuan ISO (YYYY-Www) cua tuan vua ket thuc/dang chay: lui 12 gio de bao cao chay sang sang Thu hai van lay tuan truoc."""
    from zoneinfo import ZoneInfo
    y, w, _ = (now.astimezone(ZoneInfo(tz)) - timedelta(hours=12)).isocalendar()
    return f"{y}-W{w:02d}"
