"""GET /v1/data-sources: trang thai nguon du lieu mien phi (active | needs_key | disabled) + ket qua doi chieu nguon gia.
Tong hop CHI-DOC tu market-collector (/providers, /reconcile) va news-collector (/providers); moi nguon loi -> {"error": ...}
(khong lam hong ca endpoint). Khong tra gia tri khoa/token - collector chi bao ten bien env con thieu."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter
from tscommon.sources import scrub_obj

from .config import GatewaySettings


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 (URL tu cau hinh noi bo, chi GET)
        return json.loads(r.read())


async def _safe(url: str) -> dict:
    try:
        return await asyncio.to_thread(_get, url)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}"}


_KEEP = ("kind", "state", "last_ok", "last_cycle", "enabled", "free", "risky")


def anonymize_providers(items: list, label: str) -> list:
    """Trang thai tong hop khong ten: moi luong ->{provider: '<label> N', kind, state, last_ok...}. Bo needs_env/ten bien."""
    out = []
    for n, it in enumerate(items or [], 1):
        row = {"provider": f"{label} {n}"}
        if isinstance(it, dict):
            row.update({k: it[k] for k in _KEEP if k in it})
            if row.get("kind") and scrub_obj({"x": row["kind"]}).get("x") != row["kind"]:
                row.pop("kind")
        out.append(row)
    return out


def register_datasource_routes(api: APIRouter, hide: bool | None = None) -> None:
    @api.get("/data-sources", tags=["system"],
             summary="Trang thai luong du lieu (HIDE_SOURCES: an danh) + doi chieu gia")
    async def data_sources():
        mc = os.getenv("MARKET_COLLECTOR_URL", "http://market-collector:8000").rstrip("/")
        nc = os.getenv("NEWS_COLLECTOR_URL", "http://news-collector:8000").rstrip("/")
        mp, rec, npv = await asyncio.gather(_safe(f"{mc}/providers"), _safe(f"{mc}/reconcile"), _safe(f"{nc}/providers"))
        hide_now = GatewaySettings().hide_sources if hide is None else hide
        if hide_now:
            return {"generated_at": datetime.now(timezone.utc).isoformat(),
                    "market": anonymize_providers(mp.get("providers", []), "Luồng giá"), "market_error": mp.get("error"),
                    "news": anonymize_providers(npv.get("providers", []), "Luồng tin"), "news_error": npv.get("error"),
                    "reconcile": None if "error" in rec else scrub_obj(rec, drop_keys=False, neutral="luồng giá"),
                    "reconcile_error": rec.get("error")}
        return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "market": mp.get("providers", []), "market_error": mp.get("error"),
                "news": npv.get("providers", []), "news_error": npv.get("error"),
                "reconcile": None if "error" in rec else rec, "reconcile_error": rec.get("error")}
