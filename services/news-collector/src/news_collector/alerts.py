"""Phat hien su kien lich HIGH impact sap toi -> alerts.out. Ham thuan, de test."""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import Emit


def upcoming_high(events: list[dict], now: datetime, window_min: float = 30) -> list[Emit]:
    out = []
    horizon = now + timedelta(minutes=window_min)
    for ev in events:
        if ev.get("impact") != "high":
            continue
        ts = datetime.fromisoformat(ev["ts"])
        if not (now <= ts <= horizon):
            continue
        mins = max(0, int((ts - now).total_seconds() // 60))
        key = f"cal:{ev['source']}:{ev['event_id']}:{ev['ts']}"
        country = ev.get("country") or ""
        payload = {
            "level": "warn",
            "title": f"Su kien HIGH sap toi: {country} {ev['title']}".replace("  ", " "),
            "body": (f"{ev['title']} ({country}) luc {ev['ts']} UTC, con ~{mins} phut. "
                     f"Forecast={ev.get('forecast')} Previous={ev.get('previous')}. Nguon: {ev['source']}."),
            "tags": ["calendar", "high-impact", country.lower()],
            "dedupe_key": key,
        }
        out.append(Emit("alerts", "alert", payload, f"alert:{key}"))
    return out
