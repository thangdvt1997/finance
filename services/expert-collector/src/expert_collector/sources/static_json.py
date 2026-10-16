"""Nguon JSON do ban tu bien soan (chuyen gia VN, danh sach theo doi thu cong...). Khong dung mang.

Dinh dang:
{"experts":[{"expert_id":"vn:abc","display_name":"..","url":"..","reputation":{gain_pct,max_drawdown_pct,months_active,followers,trades},
 "positions":[{"symbol":"EURUSD","side":"buy","volume":0.1,"entry":1.08,"sl":..,"tp":..,"opened_at":"2026-10-01T00:00:00Z","ticket":"1"}],
 "signals":[{"symbol":"VN:VNM","side":"buy","entry":..,"tp":..,"opened_at":"..","url":".."}],
 "closed_trades":[{"volume":0.1,"profit":-5}]}]}"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import ExpertInfo, PositionInfo, SignalInfo, normalize_symbol
from .base import ExpertSource


def _dt(v: Any) -> datetime | None:
    if not v:
        return None
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_document(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in doc.get("experts", []):
        info = ExpertInfo(expert_id=e["expert_id"], source="static_json", display_name=e.get("display_name", ""),
                          url=e.get("url", ""), reputation=dict(e.get("reputation") or {}))
        pos = [PositionInfo(symbol=normalize_symbol(p["symbol"]), side=p["side"], volume=float(p.get("volume", 0)),
                            entry=p.get("entry"), sl=p.get("sl"), tp=p.get("tp"), opened_at=_dt(p.get("opened_at")),
                            ticket=p.get("ticket")) for p in e.get("positions", [])]
        sig = [SignalInfo(symbol=normalize_symbol(s["symbol"]), side=s["side"], entry=s.get("entry"), sl=s.get("sl"),
                          tp=s.get("tp"), opened_at=_dt(s.get("opened_at")), status=s.get("status", "open"),
                          url=s.get("url", ""), raw={"static": True}) for s in e.get("signals", [])]
        out[info.expert_id] = {"info": info, "positions": pos, "signals": sig, "trades": e.get("closed_trades", [])}
    return out


class StaticJsonSource(ExpertSource):
    name = "static_json"
    supports_positions = True
    tos_risk = "low"
    warning = "Du lieu do ban tu nhap; chiu trach nhiem ve nguon goc."

    def __init__(self, path: str):
        self.path = path

    def _load(self) -> dict[str, dict]:
        if not self.path or not Path(self.path).exists():
            return {}
        return parse_document(json.loads(Path(self.path).read_text(encoding="utf-8")))

    async def list_experts(self) -> list[ExpertInfo]:
        return [v["info"] for v in self._load().values()]

    async def fetch_signals(self, expert: ExpertInfo) -> list[SignalInfo]:
        return self._load().get(expert.expert_id, {}).get("signals", [])

    async def fetch_positions(self, expert: ExpertInfo) -> list[PositionInfo]:
        return self._load().get(expert.expert_id, {}).get("positions", [])

    async def fetch_trades(self, expert: ExpertInfo) -> list[dict]:
        return self._load().get(expert.expert_id, {}).get("trades", [])
