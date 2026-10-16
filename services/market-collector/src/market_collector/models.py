from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TF_SECONDS: dict[str, int] = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
TF_ORDER = list(TF_SECONDS)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(ts: datetime) -> datetime:
    """Naive -> coi la UTC; aware -> doi sang UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def floor_ts(ts: datetime, tf: str) -> datetime:
    """Lam tron xuong dau nen (moc epoch UTC; H4/D1 can theo 00:00 UTC)."""
    sec = TF_SECONDS[tf]
    e = int(ensure_utc(ts).timestamp())
    return datetime.fromtimestamp(e - e % sec, tz=timezone.utc)


def tf_delta(tf: str) -> timedelta:
    return timedelta(seconds=TF_SECONDS[tf])


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    tf: str
    ts_open: datetime  # UTC aware
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0
    source: str = ""

    def to_payload(self) -> dict:
        return {
            "symbol": self.symbol, "tf": self.tf, "ts_open": ensure_utc(self.ts_open).isoformat(),
            "o": self.o, "h": self.h, "l": self.l, "c": self.c, "v": self.v, "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    ts: datetime
    source: str

    def to_payload(self) -> dict:
        return {"symbol": self.symbol, "bid": self.bid, "ask": self.ask,
                "ts": ensure_utc(self.ts).isoformat(), "source": self.source}
