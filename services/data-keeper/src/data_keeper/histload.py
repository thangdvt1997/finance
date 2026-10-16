"""K4 - Nạp LỊCH SỬ chọn lọc từ kho nghiên cứu MT5 (data/research/patterns/mt5, parquet/bin) vào bảng `bars` production.

CLI (chạy từ host VPS, user thuộc nhóm docker; KHÔNG cần deploy service):
  python3 services/data-keeper/src/data_keeper/histload.py plan   [--symbols A,B] [--retention M1=60,M5=365,...]
  python3 .../histload.py load    --symbols EURUSD,AUDCAD [--dry-run] [--no-guard]
  python3 .../histload.py load    --all                         # nạp toàn bộ 162 mã, 1 luồng, nice, dừng khi p95>0,5 s
  python3 .../histload.py reconcile --all                       # đối chiếu số nến kho vs DB
  python3 .../histload.py size                                  # dung lượng bảng bars + nén
  python3 .../histload.py report                                # ghi docs/handoff/DK_coverage_final.md
(đọc parquet chạy trong container tạm tradingsys-analytics, --cpus giới hạn; SQL qua docker exec psql.)

Quy tắc:
- Nguồn ghi = chuỗi canon CỦA CHÍNH MÃ ĐÓ: 7 mã cũ -> 'canon:mt5:100000001', 155 mã còn lại -> 'canon:mt5:100000001-feed'
  (cùng chuỗi với nến live của feed => KHÔNG thêm nguồn thứ ba, không trộn nguồn). Idempotent: INSERT .. ON CONFLICT DO NOTHING
  (nến live đã có luôn thắng, chạy lại không đổi gì).
- M1/M5/M15/M30/H1 lấy native (ts_open đã UTC). H4/D1/W1/MN1 KHÔNG lấy native (native cắt theo giờ server EET) mà gộp từ H1 theo mốc UTC
  (H4 00,04,..; D1 00:00 UTC; W1 thứ Hai 00:00 UTC; MN1 mùng 1) giống feed; chỉ giữ bucket đã đủ (kết thúc <= hết nến H1 cuối của kho).
- Retention: M1 chỉ N ngày gần nhất, khung lớn hơn sâu hơn (RETENTION_DAYS). Mốc "gần nhất" = nến cuối của kho (không phải đồng hồ).
- 3 mã không có M1 (NZDMXN, USDARS, USDGEL): đọc thẳng raw/*.bin M5 trở lên (quy tắc giờ 'eu' như importer), khung thấp nhất = M5, ghi cờ.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC_OLD = "canon:mt5:100000001"
SRC_FEED = "canon:mt5:100000001-feed"
OLD7 = frozenset({"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30", "USTEC"})
NO_M1 = ("NZDMXN", "USDARS", "USDGEL")

TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800, "MN1": 2592000}
NATIVE_TFS = ("M1", "M5", "M15", "M30", "H1")
DERIVED_TFS = ("H4", "D1", "W1", "MN1")
ALL_TFS = NATIVE_TFS + DERIVED_TFS
# Độ sâu (ngày) tính ngược từ nến cuối của kho; None = toàn bộ lịch sử.
RETENTION_DAYS: dict[str, int | None] = {"M1": 60, "M5": 365, "M15": 730, "M30": 1095, "H1": 3650, "H4": None, "D1": None, "W1": None, "MN1": None}
# Ước lượng byte/nến sau nén timescale (cập nhật từ số đo thật bằng `size`/trial).
EST_BYTES_PER_ROW = 20.0

_P = Path(__file__).resolve().parents
ROOT = Path(os.environ.get("TS_ROOT", "/root/trading-system"))
if len(_P) > 4 and (_P[4] / "infra").exists():
    ROOT = _P[4]
STORE = ROOT / "data/research/patterns"
PG = "tradingsys-timescaledb-1"
IMAGE = "tradingsys-analytics:latest"
P95_MAX = 0.5
LAT_SCRIPT = ROOT / "infra/ops/feed_latency.py"
STATE = ROOT / "data/dk/histload_state.json"


def source_for(symbol: str) -> str:
    return SRC_OLD if symbol.upper() in OLD7 else SRC_FEED


def parse_retention(s: str | None) -> dict[str, int | None]:
    r = dict(RETENTION_DAYS)
    for part in (s or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().upper()
            if k not in TF_SEC:
                raise ValueError(f"khung lạ: {k}")
            r[k] = None if v.strip().lower() in ("all", "none", "") else int(v)
    return r


def window_start(last: datetime, days: int | None) -> datetime | None:
    return None if days is None else last - timedelta(days=days)


def lowest_tf(symbol: str, available: set[str]) -> str:
    """Khung thấp nhất có dữ liệu native (M1, hoặc M5 cho 3 mã không có M1)."""
    for tf in ("M1", "M2", "M3", "M4", "M5", "M15", "M30", "H1"):
        if tf in available:
            return tf
    return "H1"


# ---------------------------------------------------------------- đọc kho (chạy trong container có pandas/pyarrow) ----------
def _read_raw(p: Path):
    import numpy as np
    import pandas as pd

    dt = np.dtype([("time", "<i8"), ("o", "<f8"), ("h", "<f8"), ("l", "<f8"), ("c", "<f8"), ("tv", "<i8"), ("spread", "<i4"), ("rv", "<i8")])
    df = pd.DataFrame(np.fromfile(p, dtype=dt)).drop_duplicates("time").sort_values("time")
    ok = (df.o > 0) & (df.h >= df.l) & (df.h >= df.o) & (df.h >= df.c) & (df.l <= df.o) & (df.l <= df.c)
    df = df[ok].reset_index(drop=True)
    w = pd.to_datetime(df["time"], unit="s")  # giờ server (EET Europe/Athens) -> UTC
    ts = w.dt.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    out = pd.DataFrame({"ts_open": ts, "o": df.o, "h": df.h, "l": df.l, "c": df.c, "v": df.tv.astype("float64")})
    return out.dropna(subset=["ts_open"]).reset_index(drop=True)


def read_native(store: Path, sym: str, tf: str):
    """DataFrame ts_open(UTC),o,h,l,c,v từ parquet; thiếu parquet -> raw .bin; không có -> None."""
    import pandas as pd

    p = store / "mt5/bars" / f"{sym}_{tf}.parquet"
    if p.exists():
        d = pd.read_parquet(p, columns=["ts_open", "o", "h", "l", "c", "v"])
        d["ts_open"] = pd.to_datetime(d["ts_open"], utc=True)
    else:
        r = store / "mt5/raw" / f"{sym}_{tf}.bin"
        if not r.exists() or r.stat().st_size < 60:
            return None
        d = _read_raw(r)
    return d.drop_duplicates("ts_open").sort_values("ts_open").reset_index(drop=True)


def resample_utc(h1, tf: str):
    """H1 (ts_open UTC) -> H4/D1/W1/MN1 theo mốc UTC. Tra DataFrame ts_open,o,h,l,c,v; bucket cuối chưa đủ bị bỏ."""
    import pandas as pd

    if h1 is None or h1.empty:
        return h1
    ts = h1["ts_open"]
    if tf == "MN1":
        key = ts.dt.tz_localize(None).dt.to_period("M").dt.start_time.dt.tz_localize("UTC")
    elif tf == "W1":
        d = ts.dt.floor("D")
        key = d - pd.to_timedelta(d.dt.weekday, unit="D")
    else:
        sec = TF_SEC[tf]
        epoch = (ts - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
        key = pd.to_datetime(epoch // sec * sec, unit="s", utc=True)
    g = h1.assign(k=key.values).groupby("k", sort=True)
    out = g.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum")).reset_index().rename(columns={"k": "ts_open"})
    out["ts_open"] = pd.to_datetime(out["ts_open"], utc=True)
    last_end = h1["ts_open"].iloc[-1] + pd.Timedelta(hours=1)
    if tf == "MN1":
        ends = out["ts_open"] + pd.offsets.MonthBegin(1)
    else:
        ends = out["ts_open"] + pd.Timedelta(seconds=TF_SEC[tf])
    return out[ends <= last_end].reset_index(drop=True)


def frames_for(store: Path, sym: str, retention: dict, tfs=ALL_TFS) -> dict:
    """tf -> DataFrame đã cắt theo retention (mốc = nến cuối của kho)."""
    import pandas as pd

    res: dict = {}
    h1 = read_native(store, sym, "H1")
    for tf in tfs:
        d = read_native(store, sym, tf) if tf in NATIVE_TFS else resample_utc(h1, tf)
        if d is None or d.empty:
            continue
        if tf in NATIVE_TFS and len(d) > 1:
            d = d.iloc[:-1]  # nến native cuối có thể chưa đóng -> bỏ (rẻ, an toàn)
        st = window_start(d["ts_open"].iloc[-1], retention.get(tf))
        if st is not None:
            d = d[d["ts_open"] >= pd.Timestamp(st)]
        res[tf] = d.reset_index(drop=True)
    return res


def export_symbols(store: Path, symbols: list[str], retention: dict, out_csv: str | None, count_only: bool = False) -> dict:
    """Chạy trong container: ghi CSV (symbol,tf,ts_open,o,h,l,c,v,source) hoặc chỉ đếm. Trả {sym:{tf:{rows,from,to}}}."""
    stats: dict = {}
    fh = open(out_csv, "w", newline="") if out_csv and not count_only else None
    w = csv.writer(fh) if fh else None
    try:
        for sym in symbols:
            fr = frames_for(store, sym, retention)
            src = source_for(sym)
            stats[sym] = {}
            for tf, d in fr.items():
                stats[sym][tf] = {"rows": int(len(d)), "from": d["ts_open"].iloc[0].isoformat() if len(d) else None,
                                  "to": d["ts_open"].iloc[-1].isoformat() if len(d) else None}
                if w is not None:
                    for t, o, h, l, c, v in d[["ts_open", "o", "h", "l", "c", "v"]].itertuples(index=False):
                        w.writerow([sym, tf, t.strftime("%Y-%m-%dT%H:%M:%S+00:00"), repr(float(o)), repr(float(h)), repr(float(l)), repr(float(c)), repr(float(v)), src])
    finally:
        if fh:
            fh.close()
    return stats


# ---------------------------------------------------------------- hạ tầng (host) -------------------------------------------
def psql(sql: str, stdin: str | None = None, timeout: int = 3600) -> str:
    cmd = ["docker", "exec", "-i", PG, "sh", "-c", 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d ts -At']
    r = subprocess.run(cmd, input=(stdin if stdin is not None else sql), capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"psql lỗi: {r.stderr.strip()[:600]}")
    return r.stdout


def run_export(symbols: list[str], retention: dict, out_dir: str, count_only: bool = False) -> dict:
    """Chạy phần đọc kho trong container tạm (cpus=1, cpu-shares thấp, nice)."""
    script = Path(__file__).resolve()
    ret = ",".join(f"{k}={'all' if v is None else v}" for k, v in retention.items())
    cmd = ["nice", "-n", "15", "docker", "run", "--rm", "--user", "root", "--cpus", "1", "--cpu-shares", "128", "-m", "6g",
           "-v", f"{STORE}:/out:ro", "-v", f"{script}:/hl/histload.py:ro", "-v", f"{out_dir}:/w",
           "-e", "PYTHONPATH=/out/.pylib", "--entrypoint", "python", IMAGE, "/hl/histload.py", "_export",
           "--symbols", ",".join(symbols), "--retention", ret, "--store", "/out", "--out", "/w/bars.csv"]
    if count_only:
        cmd.append("--count-only")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"export lỗi: {r.stderr.strip()[-600:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def p95_now(window: int = 8) -> float | None:
    """p95 trễ giá (fx) qua infra/ops/feed_latency.py (chỉ đọc). None nếu không đo được."""
    try:
        r = subprocess.run([sys.executable, str(LAT_SCRIPT), str(window)], capture_output=True, text=True, timeout=window + 30)
        m = re.search(r"fx: n=(\d+) p50=\S+ p95=([0-9.]+)s", r.stdout)
        return float(m.group(2)) if m else None
    except Exception:  # noqa: BLE001
        return None


class Guard:
    """Tạm dừng khi p95 > 0,5 s. Đo lại tối đa mỗi `every` giây; khi xấu: ngủ rồi đo lại cho tới khi ổn."""

    def __init__(self, enabled=True, every=45.0, p95_max=P95_MAX, measure=p95_now, sleep=time.sleep):
        self.enabled, self.every, self.p95_max, self.measure, self.sleep = enabled, every, p95_max, measure, sleep
        self._t = 0.0
        self.pauses = 0
        self.last = None

    def wait_ok(self) -> None:
        if not self.enabled or time.time() - self._t < self.every:
            return
        while True:
            self.last = self.measure()
            self._t = time.time()
            if self.last is None or self.last <= self.p95_max:
                return
            self.pauses += 1
            print(f"[guard] p95={self.last:.3f}s > {self.p95_max}s -> tạm dừng 60 s", flush=True)
            self.sleep(60)


INSERT_SQL = """BEGIN;
CREATE TEMP TABLE _h(symbol text, tf text, ts_open timestamptz, o float8, h float8, l float8, c float8, v float8, source text) ON COMMIT DROP;
COPY _h FROM STDIN WITH (FORMAT csv);
{data}\\.
{tail}
"""


def load_csv(data: str, dry: bool) -> list[tuple[str, str, int, int]]:
    """Nạp CSV vào bars; trả [(source, tf, staged, inserted)]."""
    tail = ("WITH ins AS (INSERT INTO bars(symbol,tf,ts_open,o,h,l,c,v,source) SELECT symbol,tf,ts_open,o,h,l,c,v,source FROM _h "
            "ON CONFLICT (symbol,tf,ts_open,source) DO NOTHING RETURNING 1), n AS (SELECT count(*) k FROM ins) "
            "SELECT 'ins', (SELECT count(*) FROM _h), (SELECT k FROM n);\nCOMMIT;") if not dry else \
        ("SELECT 'dry', (SELECT count(*) FROM _h), (SELECT count(*) FROM _h h WHERE NOT EXISTS (SELECT 1 FROM bars b WHERE b.symbol=h.symbol AND b.tf=h.tf AND b.ts_open=h.ts_open AND b.source=h.source));\nROLLBACK;")
    out = psql(INSERT_SQL.format(data=data, tail=tail))
    for ln in out.splitlines():
        p = ln.split("|")
        if p[0] in ("ins", "dry"):
            return [("*", "*", int(p[1]), int(p[2]))]
    raise RuntimeError("không đọc được kết quả nạp: " + out[-300:])


# ---------------------------------------------------------------- lệnh CLI ---------------------------------------------------
def all_symbols() -> list[str]:
    f = ROOT / "infra/mt-bridge/feed_symbols.txt"
    return [l.strip().upper() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]


def pick_symbols(a) -> list[str]:
    if a.all:
        return all_symbols()
    return [s.strip().upper() for s in (a.symbols or "").split(",") if s.strip()]


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"symbols": {}}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, sort_keys=True))


def cmd_plan(a) -> None:
    ret = parse_retention(a.retention)
    syms = pick_symbols(a) or all_symbols()
    with tempfile.TemporaryDirectory(dir=str(ROOT / "data")) as td:
        os.chmod(td, 0o755)
        stats = run_export(syms, ret, td, count_only=True)
    tot: dict = {}
    for s, d in stats.items():
        for tf, x in d.items():
            tot[tf] = tot.get(tf, 0) + x["rows"]
    n = sum(tot.values())
    print("Retention (ngày):", {k: v for k, v in ret.items()})
    print(f"{'khung':6}{'số nến':>14}{'~MB nén':>10}")
    for tf in ALL_TFS:
        print(f"{tf:6}{tot.get(tf, 0):>14,}{tot.get(tf, 0) * EST_BYTES_PER_ROW / 1e6:>10.0f}")
    print(f"{'TỔNG':6}{n:>14,}{n * EST_BYTES_PER_ROW / 1e6:>10.0f}  (ước {EST_BYTES_PER_ROW:.0f} B/nến sau nén; thô ~110 B/nến trước nén)")
    st = load_state()
    st["plan"] = {"retention": ret, "rows_by_tf": tot, "rows_total": n, "est_bytes_per_row": EST_BYTES_PER_ROW, "symbols": len(stats)}
    save_state(st)


def cmd_load(a) -> None:
    ret = parse_retention(a.retention)
    syms = pick_symbols(a)
    if not syms:
        raise SystemExit("cần --symbols hoặc --all")
    guard = Guard(enabled=not a.no_guard)
    st = load_state()
    batch = max(1, a.batch)
    todo = [s for s in syms if not (a.resume and st["symbols"].get(s, {}).get("done"))]
    t0 = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        guard.wait_ok()
        with tempfile.TemporaryDirectory(dir=str(ROOT / "data")) as td:
            os.chmod(td, 0o755)
            stats = run_export(chunk, ret, td)
            data = (Path(td) / "bars.csv").read_text()
        guard.wait_ok()
        (_, _, staged, ins), = load_csv(data, a.dry_run)
        for s in chunk:
            d = stats.get(s, {})
            have = set(d)
            lt = lowest_tf(s, have)
            st["symbols"][s] = {"done": not a.dry_run, "source": source_for(s), "rows": {tf: x["rows"] for tf, x in d.items()},
                                "lowest_tf": lt, "no_m1": "M1" not in have, "at": datetime.now(timezone.utc).isoformat()}
        save_state(st)
        print(f"[{i + len(chunk)}/{len(todo)}] {','.join(chunk)} staged={staged} {'sẽ chèn' if a.dry_run else 'đã chèn'}={ins} "
              f"(+{time.time() - t0:.0f}s, p95={guard.last}, pauses={guard.pauses})", flush=True)
        if a.sleep:
            time.sleep(a.sleep)


def cmd_reconcile(a) -> dict:
    ret = parse_retention(a.retention)
    syms = pick_symbols(a) or all_symbols()
    with tempfile.TemporaryDirectory(dir=str(ROOT / "data")) as td:
        os.chmod(td, 0o755)
        stats = run_export(syms, ret, td, count_only=True)
    res = {}
    bad = 0
    for s in syms:
        src = source_for(s)
        for tf, x in stats.get(s, {}).items():
            if not x["rows"]:
                continue
            hi = datetime.fromisoformat(x["to"])
            q = (f"SELECT count(*) FROM bars WHERE symbol='{s}' AND tf='{tf}' AND source='{src}' AND ts_open>='{x['from']}' AND ts_open<='{hi.isoformat()}'")
            db = int(psql(q).strip() or 0)
            res.setdefault(s, {})[tf] = {"store": x["rows"], "db": db, "diff": db - x["rows"]}
            if db < x["rows"]:
                bad += 1
    tot_store = sum(v["store"] for d in res.values() for v in d.values())
    tot_db = sum(v["db"] for d in res.values() for v in d.values())
    print(f"đối chiếu {len(res)} mã: kho={tot_store:,} db={tot_db:,} (db>=kho vì có thêm nến live); cặp (mã,khung) thiếu nến: {bad}")
    for s, d in res.items():
        for tf, v in d.items():
            if v["diff"] < 0:
                print(f"  THIẾU {s} {tf}: kho={v['store']} db={v['db']}")
    st = load_state()
    st["reconcile"] = {"at": datetime.now(timezone.utc).isoformat(), "kho": tot_store, "db": tot_db, "pairs_short": bad}
    save_state(st)
    return res


def cmd_size(a) -> None:
    print(psql("SELECT 'bars', pg_size_pretty(hypertable_size('bars')), (SELECT count(*) FROM bars), "
               "(SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name='bars'), "
               "(SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name='bars' AND NOT is_compressed);"
               "SELECT 'db', pg_size_pretty(pg_database_size('ts'));"
               "SELECT 'src', source, count(*) FROM bars GROUP BY 2 ORDER BY 3 DESC;"))
    print(psql("SELECT pg_size_pretty(before_compression_total_bytes), pg_size_pretty(after_compression_total_bytes) FROM hypertable_compression_stats('bars')"))


def cmd_compress(a) -> None:
    """(Tái)nén chunk chưa nén hoặc 'partial' (sau khi nạp vào chunk đã nén), 1 chunk/lần, lock_timeout 3 s để không chặn đọc
    của UI/giá (bỏ qua chunk bận, chạy lại sau), nghỉ giữa các chunk, tôn trọng guard p95."""
    rows = psql("SELECT format('%I.%I', c.chunk_schema, c.chunk_name) FROM timescaledb_information.chunks c "
                "JOIN _timescaledb_catalog.chunk k ON k.relid = format('%I.%I', c.chunk_schema, c.chunk_name)::regclass "
                "WHERE c.hypertable_name='bars' AND (k.status&8=8 OR (NOT c.is_compressed AND c.range_end < now() - interval '30 days')) "
                "ORDER BY c.range_start").split()
    guard = Guard(enabled=not a.no_guard)
    done = busy = 0
    for i, c in enumerate(rows, 1):
        guard.wait_ok()
        try:
            psql(f"SET lock_timeout='60s'; SELECT compress_chunk('{c}', true)", timeout=900)
            done += 1
        except RuntimeError as e:
            busy += 1
            print(f"bỏ qua {c}: {str(e)[:100]}", flush=True)
        if i % 100 == 0:
            print(f"đã xử lý {i}/{len(rows)} (nén {done}, bận {busy})", flush=True)
        time.sleep(a.sleep)
    print(f"xong: {done} nén, {busy} bận/bỏ qua trên {len(rows)} chunk")


def cmd_reindex(a) -> None:
    """Sau khi nén, chỉ mục PK/ts của chunk đã nén vẫn phình (heap đã rỗng nhưng trang chỉ mục còn): REINDEX chỉ các chunk đã nén,
    không partial, chỉ mục > 1 MB. lock_timeout 20 s, guard p95, nghỉ giữa các chunk."""
    rows = psql("SELECT i.indexrelid::regclass::text FROM _timescaledb_catalog.chunk k JOIN pg_index i ON i.indrelid=k.relid "
                "WHERE k.hypertable_id=(SELECT id FROM _timescaledb_catalog.hypertable WHERE table_name='bars') AND k.status&1=1 AND k.status&8=0 "
                "AND pg_relation_size(i.indexrelid) > 1048576 ORDER BY pg_relation_size(i.indexrelid) DESC").split()
    guard = Guard(enabled=not a.no_guard)
    done = busy = 0
    for i, ix in enumerate(rows, 1):
        guard.wait_ok()
        try:
            psql(f"SET lock_timeout='20s'; REINDEX INDEX {ix}", timeout=900)
            done += 1
        except RuntimeError as e:
            busy += 1
            print(f"bỏ qua {ix}: {str(e)[:80]}", flush=True)
        if i % 100 == 0:
            print(f"reindex {i}/{len(rows)} (xong {done}, bận {busy})", flush=True)
        time.sleep(a.sleep)
    print(f"xong reindex: {done} ok, {busy} bận trên {len(rows)} chỉ mục")


def _main_export(a) -> None:
    stats = export_symbols(Path(a.store), [s for s in a.symbols.split(",") if s], parse_retention(a.retention), a.out, a.count_only)
    print(json.dumps(stats))


def cmd_report(a) -> None:
    st = load_state()
    ret = st.get("plan", {}).get("retention", RETENTION_DAYS)
    syms = all_symbols()
    man = json.loads((STORE / "mt5/manifest.json").read_text())["files"]
    have: dict = {}
    for f in man:
        have.setdefault(f["symbol"], {})[f["tf"]] = f["bars"]
    db: dict = {}
    for ln in psql("SELECT symbol, tf, count(*), min(ts_open)::date FROM bars WHERE source LIKE 'canon:mt5:100000001%' GROUP BY 1,2").splitlines():
        sy, tf, n, d0 = ln.split("|")
        db.setdefault(sy, {})[tf] = (int(n), d0)
    cols = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    L = ["# DK coverage final (K4 histload)", "",
         f"Sinh bởi `histload.py report` lúc {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Retention nạp (ngày, tính ngược từ nến cuối kho): `{json.dumps(ret)}`.",
         "Số nến = số nến trong bảng `bars` theo chuỗi canon của mã (gồm cả nến live). `Từ` = ngày nến sớm nhất khung thấp nhất đã nạp.", ""]
    miss = [s for s in syms if s not in have]
    L += ["## Mã không có trong manifest kho trước khi xử lý", ""]
    L += [f"- Khi bắt đầu: kho có 159/162 mã (đủ 21 khung). 7 mã từng ghi là \"còn thiếu\" đã được importer nhập xong trong lúc đó (manifest 159 mã, mỗi mã 21 khung) -> không còn mã thiếu ngoài 3 mã dưới.",
          "- 3 mã không có M1 trên broker (NZDMXN, USDARS, USDGEL): importer bỏ qua vì M1.bin rỗng (không sinh parquet). histload đọc thẳng `raw/*.bin` (quy tắc giờ EET) từ M5 trở lên; khung thấp nhất = M5 (cờ `no_m1` trong `data/dk/histload_state.json`). USDGEL gần như không giao dịch (khoảng 230 nến/khung, dừng 2018).", ""]
    L += ["## Bảng phủ", "", "| Mã | Chuỗi | Khung thấp nhất | " + " | ".join(cols) + " | Từ | Ghi chú |", "|---|---|---|" + "---|" * len(cols) + "---|---|"]
    for sy in syms:
        h = have.get(sy, {})
        d = db.get(sy, {})
        low = lowest_tf(sy, set(h))
        frm = d.get(low, (0, "-"))[1]
        note = []
        if sy in NO_M1:
            note.append("không có M1 -> M5")
        if sy not in have:
            note.append("không có trong kho")
        if not d:
            note.append("chưa nạp")
        L.append(f"| {sy} | {'cũ' if sy in OLD7 else 'feed'} | {low} | " + " | ".join(f"{d[t][0]:,}" if t in d else "-" for t in cols) + f" | {frm} | {'; '.join(note)} |")
    rec = st.get("reconcile")
    if rec:
        L += ["", f"Đối chiếu ({rec['at'][:16]} UTC): kho={rec['kho']:,} nến, DB={rec['db']:,}; cặp (mã,khung) thiếu nến: {rec['pairs_short']}."]
    out = ROOT / "docs/handoff/DK_coverage_final.md"
    out.write_text("\n".join(L) + "\n")
    print("ghi", out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "load", "reconcile", "size", "report", "compress", "reindex", "_export"):
        p = sp.add_parser(name)
        p.add_argument("--symbols")
        p.add_argument("--all", action="store_true")
        p.add_argument("--retention")
        if name == "load":
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--no-guard", action="store_true")
            p.add_argument("--resume", action="store_true")
            p.add_argument("--batch", type=int, default=1)
            p.add_argument("--sleep", type=float, default=0.5)
        if name in ("compress", "reindex"):
            p.add_argument("--no-guard", action="store_true")
            p.add_argument("--sleep", type=float, default=0.5)
        if name == "_export":
            p.add_argument("--store")
            p.add_argument("--out")
            p.add_argument("--count-only", action="store_true")
    a = ap.parse_args(argv)
    {"plan": cmd_plan, "load": cmd_load, "reconcile": cmd_reconcile, "size": cmd_size, "report": cmd_report,
     "compress": cmd_compress, "reindex": cmd_reindex, "_export": _main_export}[a.cmd](a)


if __name__ == "__main__":
    main()
