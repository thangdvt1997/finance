"""Chuoi nen "canon" tu EA cua MOT tai khoan nguon gia (feed) -> nguon uu tien cho FX/vang/chi so (docs/KIEN_TRUC.md muc Feed canon).

Vi sao: nen FX/vang M1 cua nguon lich su (dukascopy) tre cau truc 80-100 phut; EA MT5 demo gui nen M1 da dong tre ~1 phut.
Doc nen o moi service = `SELECT DISTINCT ON (ts_open) ... ORDER BY ts_open, source` (ten source dung truoc theo chu cai thang,
docs/DATA_SOURCE_PRIORITY.md). Vi vay chuoi canon mang source `canon:<account_id>` ('canon' < 'crypto_ccxt' < 'dukascopy')
-> o MOI (symbol, tf, ts_open) co nen canon thi canon thang; khong co thi tu roi ve nguon cu. KHONG tron 2 nguon trong 1 nen:
moi nen canon chi dung M1 cua EA.

Quy tac (thuan, khong I/O, dong ho tiem vao -> test duoc):
- M1: moi nen M1 da dong cua EA -> phat lai NGAY voi source canon. Phut khong co tick (khoang trong <= fill_max_min phut giua 2
  nen lien tiep) -> nen phang (o=h=l=c=close truoc, v=0) de nguon cu khong "lot" vao giua chuoi EA.
- M5/M15/H1/H4/D1: gop tu M1 canon theo moc UTC (H4 00,04,..; D1 00:00 UTC - cung hop dong md.bars, KHONG theo gio server EET).
  Chi phat bucket DA DONG va DUOC QUAN SAT TRON: bat dau phien (nen M1 dau tien nhan duoc) <= dau bucket. Bucket do dang luc
  bridge khoi dong / EA offline -> khong phat -> nguon cu dung cho dung bucket do (fallback theo khoang thoi gian).
- EA offline > stale_s (khong batch nao): khi co lai du lieu, neu nen M1 moi KHONG lien mach (khoang trong > fill_max_min) -> phien
  moi (bo cac bucket do dang). Lien mach (EA gui bu tu con tro) -> giu phien.
- Bucket dong khi: nen M1 cua bucket sau toi, hoac (EA con song) dong ho > cuoi bucket + grace_s. Nen M1 tre cua bucket vua phat
  (EA chi gui nen khi co tick o phut ke tiep) -> cap nhat va phat lai (upsert cung khoa, cung nguon).
Rollback: FEED_CANON_ENABLED=false (ngung phat) + `DELETE FROM bars WHERE source LIKE 'canon:%'` -> doc tro lai nhu cu.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import TF_SECONDS, Bar

AGG_TFS: tuple[str, ...] = ("M5", "M15", "H1", "H4", "D1")
_M1 = timedelta(minutes=1)


def _csv(v: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in v.split(",") if x.strip())


DEFAULT_SYMBOLS = "EURUSD,GBPUSD,USDJPY,XAUUSD,US500,US30,USTEC"


def load_symbols(spec: str) -> tuple[str, ...]:
    """'A,B,C' hoac '@/duong/dan/file.txt' (moi dong 1 ma, '#' = ghi chu; sinh boi infra/ops/gen_assets_mt5.py).
    Fail-safe: file thieu/rong/loi -> DEFAULT_SYMBOLS (7 ma canon goc), khong bao gio de rong ngoai y muon."""
    spec = (spec or "").strip()
    if spec.startswith("@"):
        try:
            with open(spec[1:], encoding="utf-8") as f:
                items = [ln.split("#", 1)[0].strip().upper() for ln in f]
            out = tuple(dict.fromkeys(x for x in items if x))
            if out:
                return out
        except OSError:
            pass
        return _csv(DEFAULT_SYMBOLS)
    return _csv(spec.upper())


def _floor(ts: datetime, tf: str) -> datetime:
    s = TF_SECONDS[tf]
    return datetime.fromtimestamp(int(ts.timestamp()) // s * s, tz=timezone.utc)


@dataclass
class FeedSettings:
    enabled: bool = field(default_factory=lambda: os.getenv("FEED_CANON_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
    account: str = field(default_factory=lambda: os.getenv("FEED_CANON_ACCOUNT", "mt5:100000001").strip())
    symbols: tuple[str, ...] = field(default_factory=lambda: load_symbols(os.getenv("FEED_CANON_SYMBOLS", DEFAULT_SYMBOLS)))
    prefix: str = field(default_factory=lambda: os.getenv("FEED_CANON_PREFIX", "canon").strip())
    stale_s: float = field(default_factory=lambda: float(os.getenv("FEED_STALE_S", "300")))
    fill_max_min: int = field(default_factory=lambda: int(os.getenv("FEED_FILL_MAX_MIN", "5")))
    grace_s: float = field(default_factory=lambda: float(os.getenv("FEED_GRACE_S", "120")))

    @property
    def source(self) -> str:
        return f"{self.prefix}:{self.account}"


@dataclass
class _Bucket:
    start: datetime
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float
    eligible: bool
    emitted: bool = False


@dataclass
class _Sym:
    session_start: Optional[datetime] = None
    last: Optional[Bar] = None           # nen M1 canon cuoi (that hoac phang)
    offline_mark: bool = False           # da co khoang EA offline > stale_s tu nen cuoi
    buckets: dict[str, _Bucket] = field(default_factory=dict)


class CanonFeed:
    def __init__(self, st: Optional[FeedSettings] = None):
        self.st = st or FeedSettings()
        self.syms: dict[str, _Sym] = {}
        self.last_hb: Optional[datetime] = None
        self._allow: Optional[frozenset] = None
        self._allow_src: Optional[tuple] = None
        self.sessions = 0                 # so phien da mo (metric/test)

    def active_for(self, account_id: str) -> bool:
        return self.st.enabled and bool(self.st.account) and account_id == self.st.account

    # ---- dau vao ----
    def heartbeat(self, now: datetime) -> None:
        """Moi batch hop le cua tai khoan feed (ke ca khong co nen)."""
        if self.last_hb is not None and (now - self.last_hb).total_seconds() > self.st.stale_s:
            for s in self.syms.values():
                s.offline_mark = True
        self.last_hb = now

    def on_bars(self, bars: list[Bar], now: datetime) -> list[Bar]:
        """Nen EA (moi tf) cua tai khoan feed -> danh sach nen canon can phat."""
        allow = self._allow
        if allow is None or self._allow_src is not self.st.symbols:   # tap tra cuu O(1) cho ~170 ma (st.symbols co the bi test doi)
            allow, self._allow, self._allow_src = frozenset(self.st.symbols), frozenset(self.st.symbols), self.st.symbols
        m1 = sorted((b for b in bars if b.tf == "M1" and b.symbol.upper() in allow), key=lambda b: (b.symbol, b.ts_open))
        out: list[Bar] = []
        for b in m1:
            out.extend(self._on_m1(b))
        return out

    def flush_due(self, now: datetime) -> list[Bar]:
        """Goi dinh ky: phat bucket da qua cuoi + grace khi EA con song (thi truong lang / cuoi tuan)."""
        if self.last_hb is None or (now - self.last_hb).total_seconds() > self.st.stale_s:
            return []
        out: list[Bar] = []
        for sym, s in self.syms.items():
            for tf, bk in s.buckets.items():
                if bk.eligible and not bk.emitted and now >= bk.start + timedelta(seconds=TF_SECONDS[tf] + self.st.grace_s):
                    bk.emitted = True
                    out.append(self._bar(sym, tf, bk))
        return out

    # ---- noi bo ----
    def _bar(self, sym: str, tf: str, bk: _Bucket) -> Bar:
        return Bar(symbol=sym, broker_symbol=sym, tf=tf, ts_open=bk.start, o=bk.o, h=bk.h, l=bk.l, c=bk.c, v=bk.v, source=self.st.source)

    def _on_m1(self, b: Bar) -> list[Bar]:
        sym = b.symbol.upper()
        s = self.syms.setdefault(sym, _Sym())
        ts = b.ts_open.astimezone(timezone.utc).replace(second=0, microsecond=0)
        if s.last is not None and ts <= s.last.ts_open:
            return []                     # cu/trung (EA gui lai) - M1 da dong khong doi
        out: list[Bar] = []
        gap_min = int((ts - s.last.ts_open).total_seconds() // 60) - 1 if s.last is not None else None
        if s.last is None or (s.offline_mark and gap_min > self.st.fill_max_min):
            s.session_start, s.buckets = ts, {}   # phien moi: bucket do dang khong duoc phat (fallback nguon cu)
            self.sessions += 1
        elif 0 < gap_min <= self.st.fill_max_min:
            p, t0 = s.last.c, s.last.ts_open   # _add doi s.last -> chot moc truoc vong lap
            for i in range(1, gap_min + 1):
                out.extend(self._add(sym, s, t0 + i * _M1, p, p, p, p, 0.0))
        s.offline_mark = False
        out.extend(self._add(sym, s, ts, b.o, b.h, b.l, b.c, b.v))
        return out

    def _add(self, sym: str, s: _Sym, ts: datetime, o: float, h: float, lo: float, c: float, v: float) -> list[Bar]:
        bar = Bar(symbol=sym, broker_symbol=sym, tf="M1", ts_open=ts, o=o, h=h, l=lo, c=c, v=v, source=self.st.source)
        s.last = bar
        out = [bar]
        for tf in AGG_TFS:
            start = _floor(ts, tf)
            bk = s.buckets.get(tf)
            if bk is not None and start == bk.start:
                bk.h, bk.l, bk.c, bk.v = max(bk.h, h), min(bk.l, lo), c, bk.v + v
                if bk.emitted:            # nen tre cua bucket da phat -> phat lai ban dung
                    out.append(self._bar(sym, tf, bk))
                continue
            if bk is not None and start > bk.start and bk.eligible and not bk.emitted:
                bk.emitted = True
                out.append(self._bar(sym, tf, bk))
            s.buckets[tf] = _Bucket(start, o, h, lo, c, v, eligible=s.session_start is not None and s.session_start <= start)
        return out
