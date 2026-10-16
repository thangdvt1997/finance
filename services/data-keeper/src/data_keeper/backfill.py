"""K3 backfill: phat hien gap -> hang doi uu tien -> lap bang lich su goc -> ghi idempotent.

- Gap tinh tren CHUOI DUY NHAT source=canon:<account> (khong tron nguon), tru khoang thi truong dong (sessions.py).
- Hang doi dk.backfill_queue (uu tien: ma chinh truoc, khung nho truoc, gap moi truoc).
- Lay du lieu qua `Fetcher` (mac dinh FileExchangeFetcher: EA export theo khoang [tu,den] trao doi qua thu muc).
- Ghi truc tiep bars bang INSERT ... ON CONFLICT DO NOTHING (symbol,tf,ts_open,source) -> idempotent, khong ghi de nen song.
- Song song <= 2, dung khi do tre gia xau (ctx.latency_p95() > nguong), nhat ky dk.backfill_log.
READ-ONLY/PAPER: khong co duong dat lenh.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol

from prometheus_client import Counter, Gauge

log = logging.getLogger("data_keeper.backfill")

TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
MAJORS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAGUSD", "EURJPY", "GBPJPY", "BTCUSD")
MAX_CHUNK_BARS = 2000  # = tran batch bars cua mt-bridge /ingest/v1
MAX_PARALLEL = 2
LATENCY_LIMIT_S = 0.5
DEFAULT_ACCOUNT = "mt5:100000001-feed"
MAX_SPAN_BARS = {"M1": 20000, "M5": 20000, "M15": 20000, "M30": 20000, "H1": 20000, "H4": 20000, "D1": 20000}

G_JOB_AGE = Gauge("dk_range_job_cfg_age_seconds", "Tuoi file job-mt5.cfg (terminal live chay SCRIPT thay EA); -1 = khong co")
C_JOB_RM = Counter("dk_range_job_cfg_removed_total", "So lan tu xoa job-mt5.cfg bi bo quen qua han")
JOB_CFG_TTL_S = float(os.environ.get("DK_JOB_CFG_TTL_S", "1800"))  # 30 phut


def guard_job_cfg(xchg: str | Path | None = None, ttl_s: float | None = None, now: float | None = None) -> dict:
    """job-mt5.cfg bi bo quen => terminal mtlab-mt5 chay script thay EA live (su co 2026-10-15: canon M1 khuyet ~21h).
    /root/mtlab/out/job-mt5.cfg la SYMLINK -> xchg/job-mt5.cfg nen data-keeper thay duoc file. Qua han ttl_s: XOA + canh bao
    (terminal doc cfg luc khoi dong, nen EA tro lai o lan khoi dong ke tiep). Chua qua han: chi canh bao. Tra {state, age_s}."""
    base = Path(xchg or os.environ.get("DK_BACKFILL_XCHG", "/data/backfill-xchg"))
    ttl = JOB_CFG_TTL_S if ttl_s is None else ttl_s
    f = base / "job-mt5.cfg"
    try:
        age = (now if now is not None else time.time()) - f.stat().st_mtime
    except FileNotFoundError:
        G_JOB_AGE.set(-1)
        return {"state": "none", "age_s": None}
    except OSError as e:  # noqa: BLE001
        log.warning("khong doc duoc %s: %s", f, e)
        return {"state": "error", "age_s": None}
    G_JOB_AGE.set(age)
    if age <= ttl:
        log.warning("job-mt5.cfg dang ton tai (%.0fs): terminal live chay SCRIPT, khong phai EA. Se tu xoa sau %.0fs", age, ttl)
        return {"state": "active", "age_s": age}
    try:
        f.unlink()
        C_JOB_RM.inc()
        log.error("CANH BAO: job-mt5.cfg bi bo quen %.0fs (> %.0fs) -> DA XOA. Terminal live van chay script cho den lan khoi dong ke tiep: "
                  "can `docker restart mtlab-mt5` (sau khi chac chan LiveUpdate khong thay terminal64.exe)", age, ttl)
        return {"state": "removed", "age_s": age}
    except OSError as e:  # noqa: BLE001
        log.error("CANH BAO: job-mt5.cfg bo quen %.0fs nhung KHONG xoa duoc: %s", age, e)
        return {"state": "stale", "age_s": age}


DDL = """
CREATE TABLE IF NOT EXISTS dk.backfill_queue (
  id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, tf TEXT NOT NULL,
  t0 TIMESTAMPTZ NOT NULL, t1 TIMESTAMPTZ NOT NULL, source TEXT NOT NULL,
  priority INT NOT NULL DEFAULT 100, status TEXT NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_error TEXT,
  UNIQUE (symbol, tf, t0, t1, source));
CREATE INDEX IF NOT EXISTS dk_bq_status_prio ON dk.backfill_queue (status, priority, t0 DESC);
CREATE TABLE IF NOT EXISTS dk.backfill_log (
  id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), symbol TEXT NOT NULL, tf TEXT NOT NULL,
  t0 TIMESTAMPTZ NOT NULL, t1 TIMESTAMPTZ NOT NULL, source TEXT NOT NULL, fetcher TEXT,
  fetched INT NOT NULL DEFAULT 0, inserted INT NOT NULL DEFAULT 0, result TEXT NOT NULL,
  elapsed_ms INT, detail TEXT);
"""


@dataclass(frozen=True)
class Gap:
    symbol: str
    tf: str
    t0: datetime  # ts_open dau tien thieu
    t1: datetime  # ts_open cuoi cung thieu (bao gom)

    @property
    def missing_bars(self) -> int:
        return int((self.t1 - self.t0).total_seconds() // TF_SEC[self.tf]) + 1


Bar = tuple  # (ts_open datetime UTC, o, h, l, c, v)


class Fetcher(Protocol):
    name: str

    async def fetch(self, symbol: str, tf: str, t0: datetime, t1: datetime) -> list[Bar]: ...


def _utc(ts: Any) -> datetime:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, timezone.utc)
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def priority_of(symbol: str, tf: str, t1: datetime, now: datetime | None = None) -> int:
    """So nho = uu tien cao: ma chinh -> 0, khung nho -> truoc, gap gan day -> truoc."""
    now = now or datetime.now(timezone.utc)
    p = 0 if symbol in MAJORS else 100
    p += list(TF_SEC).index(tf) * 5 if tf in TF_SEC else 40
    age_days = max(0, (now - t1).days)
    return p + min(age_days, 60) // 6


# ---------------- phat hien gap ----------------
def _session_expected(symbol: str, tf: str, t0: datetime, t1: datetime) -> list[tuple[datetime, datetime]]:
    """Khoang thi truong dong du kien [a,b). Dung sessions.py (A1); thieu -> quy tac cuoi tuan FX."""
    try:
        from . import sessions  # type: ignore
        return [(_utc(a), _utc(b)) for a, b in sessions.session_gaps_expected(symbol, tf, t0, t1)]
    except Exception as e:  # noqa: BLE001
        log.debug("sessions.py chua san sang (%s): dung quy tac cuoi tuan", e)
    out, d = [], (t0 - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    while d <= t1:
        fri = d + timedelta(days=(4 - d.weekday()) % 7, hours=22)
        sun = fri + timedelta(days=2)
        out.append((fri, sun))
        d += timedelta(days=7)
    return out


def subtract_closed(gap: Gap, closed: Iterable[tuple[datetime, datetime]]) -> list[Gap]:
    """Cat khoang dong cua ra khoi gap; tra ve cac gap con thuc su phai lap."""
    step = timedelta(seconds=TF_SEC[gap.tf])
    segs = [(gap.t0, gap.t1 + step)]  # nua mo [a,b)
    for a, b in sorted(closed):
        nxt = []
        for s, e in segs:
            if b <= s or a >= e:
                nxt.append((s, e))
                continue
            if a > s:
                nxt.append((s, a))
            if b < e:
                nxt.append((b, e))
        segs = nxt
    out = []
    for s, e in segs:
        # can ve luoi nen
        k0 = -(-int(s.timestamp()) // TF_SEC[gap.tf]) * TF_SEC[gap.tf]
        k1 = (int(e.timestamp()) - 1) // TF_SEC[gap.tf] * TF_SEC[gap.tf]
        if k1 >= k0:
            out.append(Gap(gap.symbol, gap.tf, _utc(k0), _utc(k1)))
    return out


GAP_SQL = """
SELECT prev, ts_open FROM (
  SELECT ts_open, lag(ts_open) OVER (ORDER BY ts_open) AS prev
  FROM bars WHERE symbol=$1 AND tf=$2 AND source=$3 AND ts_open >= $4) q
WHERE prev IS NOT NULL AND ts_open - prev > make_interval(secs => $5) ORDER BY ts_open DESC LIMIT 200
"""


async def detect_gaps(db: Any, symbol: str, tf: str, source: str, since: datetime) -> list[Gap]:
    """Gap giua cac nen lien tiep trong chuoi canon (khong tinh duoi: nen moi nhat do feed lo)."""
    sec = TF_SEC[tf]
    rows = await db.fetch(GAP_SQL, symbol, tf, source, since, float(sec) * 1.5)
    out: list[Gap] = []
    for r in rows:
        prev, nxt = _utc(r["prev"]), _utc(r["ts_open"])
        g = Gap(symbol, tf, prev + timedelta(seconds=sec), nxt - timedelta(seconds=sec))
        out.extend(subtract_closed(g, _session_expected(symbol, tf, g.t0, g.t1)))
    return out


def gaps_from_matrix(matrix: dict, source: str) -> list[Gap]:
    """Doc gap da biet tu ma tran inventory: matrix[sym][tf]['gaps'] = [(t0,t1)|{'t0','t1'}|Gap] (da tru phien dong)."""
    out: list[Gap] = []
    for sym, tfs in (matrix or {}).items():
        for tf, cell in (tfs or {}).items():
            if tf not in TF_SEC or not isinstance(cell, dict) or cell.get("status") in ("CLOSED",):
                continue
            g = cell.get("gaps")
            if not isinstance(g, (list, tuple)):
                continue
            for it in g:
                try:
                    if isinstance(it, Gap):
                        out.append(it)
                    elif isinstance(it, dict):
                        out.append(Gap(sym, tf, _utc(it["t0"]), _utc(it["t1"])))
                    else:
                        out.append(Gap(sym, tf, _utc(it[0]), _utc(it[1])))
                except (KeyError, IndexError, TypeError, ValueError):
                    log.warning("gap khong hop le bo qua: %r", it)
    return out


# ---------------- hang doi ----------------
async def ensure_schema(db: Any) -> None:
    for stmt in [s.strip() for s in DDL.split(";") if s.strip()]:
        await db.execute(stmt)


async def enqueue(db: Any, gaps: Iterable[Gap], source: str, max_bars: int = MAX_CHUNK_BARS, now: datetime | None = None) -> int:
    """Dua gap vao hang doi (chia nho <= max_bars/yeu cau). Trung (symbol,tf,t0,t1,source) bi bo qua."""
    n = 0
    for g in gaps:
        step = timedelta(seconds=TF_SEC[g.tf])
        a = g.t0
        while a <= g.t1:
            b = min(g.t1, a + step * (max_bars - 1))
            res = await db.execute(
                "INSERT INTO dk.backfill_queue(symbol,tf,t0,t1,source,priority) VALUES($1,$2,$3,$4,$5,$6) "
                "ON CONFLICT (symbol,tf,t0,t1,source) DO NOTHING",
                g.symbol, g.tf, a, b, source, priority_of(g.symbol, g.tf, b, now))
            n += 1 if str(res).endswith(" 1") else 0
            a = b + step
    return n


async def claim(db: Any, limit: int) -> list[dict]:
    rows = await db.fetch(
        "UPDATE dk.backfill_queue SET status='running', attempts=attempts+1, updated_at=now() WHERE id IN ("
        " SELECT id FROM dk.backfill_queue WHERE (status='pending' OR (status='failed' AND attempts<3 AND updated_at<now()-interval '10 minutes'))"
        " ORDER BY priority, t0 DESC LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING *", limit)
    return [dict(r) for r in rows]


# ---------------- ghi ----------------
INSERT_SQL = ("INSERT INTO bars(symbol,tf,ts_open,o,h,l,c,v,source) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) "
              "ON CONFLICT (symbol,tf,ts_open,source) DO NOTHING")


def valid_bars(bars: Iterable[Bar], tf: str, t0: datetime, t1: datetime) -> list[Bar]:
    """Giu nen trong [t0,t1], tren luoi khung, OHLC hop le, bo trung ts."""
    sec, seen, out = TF_SEC[tf], set(), []
    for b in bars:
        ts = _utc(b[0])
        if not (t0 <= ts <= t1) or int(ts.timestamp()) % sec or ts in seen or ts + timedelta(seconds=sec) > datetime.now(timezone.utc):
            # bo nen dang mo (chua dong): ON CONFLICT DO NOTHING se giu ban dang do mai mai
            continue
        o, h, l, c = (float(x) for x in b[1:5])
        if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
            continue
        seen.add(ts)
        out.append((ts, o, h, l, c, float(b[5]) if len(b) > 5 and b[5] is not None else 0.0))
    return sorted(out)


async def write_bars(db: Any, symbol: str, tf: str, source: str, bars: list[Bar]) -> int:
    """Upsert idempotent; tra ve so nen THUC SU them (nen da co: bo qua)."""
    if not source.startswith("canon:"):
        raise ValueError("backfill chi ghi source canon:<account>")
    if not bars:
        return 0
    before = await db.fetchval("SELECT count(*) FROM bars WHERE symbol=$1 AND tf=$2 AND source=$3 AND ts_open BETWEEN $4 AND $5",
                               symbol, tf, source, bars[0][0], bars[-1][0])
    await db.executemany(INSERT_SQL, [(symbol, tf, b[0], b[1], b[2], b[3], b[4], b[5], source) for b in bars])
    after = await db.fetchval("SELECT count(*) FROM bars WHERE symbol=$1 AND tf=$2 AND source=$3 AND ts_open BETWEEN $4 AND $5",
                              symbol, tf, source, bars[0][0], bars[-1][0])
    return int(after) - int(before)


# ---------------- fetcher mac dinh ----------------
class FileExchangeFetcher:
    """Yeu cau/tra loi qua thu muc chia se voi EA export theo khoang.
    Ghi <dir>/req/<id>.json {symbol,tf,from,to} (epoch UTC); EA ghi <dir>/res/<id>.csv (ts_open_epoch_utc,o,h,l,c,v) roi <id>.done.
    EA phia terminal (MTAgentExport mode=range) can bo sung; xem docs/handoff/DK_notes_A3.md."""
    name = "hist-export"

    def __init__(self, base: str | Path | None = None, timeout_s: float = 120.0, poll_s: float = 1.0):
        self.base = Path(base or os.environ.get("DK_BACKFILL_XCHG", "/data/backfill-xchg"))
        self.timeout_s, self.poll_s = timeout_s, poll_s

    async def fetch(self, symbol: str, tf: str, t0: datetime, t1: datetime) -> list[Bar]:
        rid = f"{symbol}_{tf}_{int(t0.timestamp())}_{int(t1.timestamp())}"
        (self.base / "req").mkdir(parents=True, exist_ok=True)
        (self.base / "res").mkdir(parents=True, exist_ok=True)
        done, res = self.base / "res" / f"{rid}.done", self.base / "res" / f"{rid}.csv"
        if not done.exists():
            tmp = self.base / "req" / f"{rid}.tmp"
            tmp.write_text(json.dumps({"symbol": symbol, "tf": tf, "from": int(t0.timestamp()), "to": int(t1.timestamp())}))
            tmp.rename(self.base / "req" / f"{rid}.json")
        deadline = time.monotonic() + self.timeout_s
        while not done.exists():
            if time.monotonic() > deadline:
                raise TimeoutError(f"EA khong tra loi {rid} trong {self.timeout_s}s")
            await asyncio.sleep(self.poll_s)
        out: list[Bar] = []
        msg = done.read_text(errors="ignore").strip()
        if msg.startswith("err"):  # EA bao loi (vd no_data = nguon khong co nen trong khoang) -> khong co file csv
            for p in (done, res, self.base / "req" / f"{rid}.json"):
                p.unlink(missing_ok=True)
            if "no_data" in msg:
                return []
            raise RuntimeError(f"EA {rid}: {msg}")
        with res.open() as fh:
            for row in csv.reader(fh):
                if row and row[0].isdigit():
                    out.append((_utc(int(row[0])), *row[1:6]))
        for p in (done, res, self.base / "req" / f"{rid}.json"):
            p.unlink(missing_ok=True)
        return out


# ---------------- chu trinh ----------------
async def _latency_ok(ctx: Any) -> bool:
    fn = getattr(ctx, "latency_p95", None)
    if fn is None:
        return True
    try:
        v = fn()
        v = await v if asyncio.iscoroutine(v) else v
        return v is None or float(v) <= float(getattr(ctx, "latency_limit", LATENCY_LIMIT_S))
    except Exception as e:  # noqa: BLE001 - khong do duoc -> than trong: tam dung
        log.warning("khong do duoc do tre gia (%s): tam dung backfill", e)
        return False


async def _log(db: Any, it: dict, fetcher: str, fetched: int, inserted: int, result: str, t_start: float, detail: str = "") -> None:
    await db.execute("INSERT INTO dk.backfill_log(symbol,tf,t0,t1,source,fetcher,fetched,inserted,result,elapsed_ms,detail) "
                     "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)", it["symbol"], it["tf"], it["t0"], it["t1"], it["source"],
                     fetcher, fetched, inserted, result, int((time.monotonic() - t_start) * 1000), detail[:500])


async def run_item(db: Any, fetcher: Fetcher, it: dict) -> dict:
    t_start = time.monotonic()
    t0, t1 = _utc(it["t0"]), _utc(it["t1"])
    try:
        raw = await fetcher.fetch(it["symbol"], it["tf"], t0, t1)
        bars = valid_bars(raw, it["tf"], t0, t1)
        ins = await write_bars(db, it["symbol"], it["tf"], it["source"], bars)
        status = "done" if bars else "empty"  # khoang rong thuc su (le/dong cua) -> khong thu lai mai
        await db.execute("UPDATE dk.backfill_queue SET status=$2, updated_at=now(), last_error=NULL WHERE id=$1", it["id"], status)
        await _log(db, it, fetcher.name, len(raw), ins, status, t_start)
        return {"id": it["id"], "symbol": it["symbol"], "tf": it["tf"], "fetched": len(raw), "inserted": ins, "status": status}
    except Exception as e:  # noqa: BLE001
        await db.execute("UPDATE dk.backfill_queue SET status='failed', updated_at=now(), last_error=$2 WHERE id=$1", it["id"], str(e)[:300])
        await _log(db, it, getattr(fetcher, "name", "?"), 0, 0, "failed", t_start, repr(e))
        return {"id": it["id"], "symbol": it["symbol"], "tf": it["tf"], "status": "failed", "error": str(e)[:200]}


async def backfill_cycle(ctx: Any, matrix: dict | None = None) -> list[dict]:
    """1 chu ky: (1) lay gap tu ma tran hoac tu DB, (2) xep hang doi, (3) lap toi da `batch` muc, song song <=2.
    ctx: .db (asyncpg pool/conn), tuy chon .fetcher, .account, .latency_p95(), .backfill_enabled, .backfill_batch, .since_days."""
    guard_job_cfg()
    if getattr(ctx, "backfill_enabled", True) is False:
        return []
    db = ctx.db
    account = getattr(ctx, "account", None) or os.environ.get("DK_CANON_ACCOUNT", DEFAULT_ACCOUNT)
    source = account if account.startswith("canon:") else f"canon:{account}"
    await ensure_schema(db)
    gaps = gaps_from_matrix(matrix or {}, source)
    if not gaps and getattr(ctx, "scan_db_gaps", False):
        since = datetime.now(timezone.utc) - timedelta(days=getattr(ctx, "since_days", 7))
        for sym, tfs in (matrix or {}).items():
            for tf in tfs:
                if tf in TF_SEC:
                    gaps += await detect_gaps(db, sym, tf, source, since)
    queued = await enqueue(db, gaps, source)
    fetcher = getattr(ctx, "fetcher", None) or FileExchangeFetcher()
    results: list[dict] = []
    budget = int(getattr(ctx, "backfill_batch", 4))
    par = max(1, min(MAX_PARALLEL, int(getattr(ctx, "backfill_parallel", 1))))
    while budget > 0:
        if not await _latency_ok(ctx):
            log.info("do tre gia xau: dung backfill (da lap %d muc)", len(results))
            results.append({"status": "paused_latency"})
            break
        items = await claim(db, min(par, budget))
        if not items:
            break
        budget -= len(items)
        results += await asyncio.gather(*(run_item(db, fetcher, it) for it in items))
    log.info("backfill: gap=%d xep_moi=%d xu_ly=%d", len(gaps), queued, len(results))
    return results
