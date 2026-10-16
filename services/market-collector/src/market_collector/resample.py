from __future__ import annotations

from typing import Iterable

from .models import TF_SECONDS, Bar, ensure_utc, floor_ts


def dedupe_bars(bars: Iterable[Bar]) -> list[Bar]:
    """Bo trung theo (symbol, tf, ts_open, source) -- ban sau thang; tra ve da sort theo thoi gian."""
    seen: dict[tuple, Bar] = {}
    for b in bars:
        seen[(b.symbol, b.tf, ensure_utc(b.ts_open), b.source)] = b
    return sorted(seen.values(), key=lambda b: (b.symbol, b.source, b.tf, ensure_utc(b.ts_open)))


def resample(bars: Iterable[Bar], target_tf: str) -> list[Bar]:
    """Gop nen tf nho -> tf lon (ham thuan). Bucket can theo moc epoch UTC (H4: 00,04,..; D1: 00:00 UTC).

    Dau vao co the gom nhieu symbol/source nhung phai cung 1 tf nguon. Bucket cuoi co the chua tron --
    consumer upsert theo khoa tu nhien nen ban cap nhat sau se de len."""
    items = dedupe_bars(bars)
    if not items:
        return []
    src_tf = items[0].tf
    if any(b.tf != src_tf for b in items):
        raise ValueError("resample: dau vao lan nhieu tf")
    if target_tf not in TF_SECONDS or src_tf not in TF_SECONDS:
        raise ValueError(f"tf khong hop le: {src_tf}->{target_tf}")
    s, t = TF_SECONDS[src_tf], TF_SECONDS[target_tf]
    if t < s or t % s:
        raise ValueError(f"khong the resample {src_tf} -> {target_tf}")
    if t == s:
        return items

    out: list[Bar] = []
    cur_key: tuple | None = None
    acc: list[Bar] = []

    def flush() -> None:
        if acc:
            out.append(Bar(symbol=acc[0].symbol, tf=target_tf, ts_open=floor_ts(acc[0].ts_open, target_tf),
                           o=acc[0].o, h=max(b.h for b in acc), l=min(b.l for b in acc),
                           c=acc[-1].c, v=sum(b.v for b in acc), source=acc[0].source))

    for b in items:  # da sort theo (symbol, source, ts)
        key = (b.symbol, b.source, floor_ts(b.ts_open, target_tf))
        if key != cur_key:
            flush()
            acc, cur_key = [], key
        acc.append(b)
    flush()
    return out
