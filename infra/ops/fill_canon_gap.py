#!/usr/bin/env python3
"""Lap khe nen canon (source='canon:mt5:100000001') bang job RANGE (MTAgentRange) chay o terminal PHU (mtlab-mt5-hist),
KHONG dong vao EA live (mtlab-mt5) va KHONG tron nguon (cung tai khoan/ may chu MT5, ghi dung source canon).

Quy trinh (xem docs/DATA_KEEPER.md, muc "Chay range an toan"):
  1. terminal phu: data/mtlab-hist/out/job-mt5.cfg = "MTAgentRange" / "MTAgentRange.set"; docker start mtlab-mt5-hist
  2. python3 infra/ops/fill_canon_gap.py --from 2026-10-15T00:00 [--to ...] [--dry-run]
  3. tra cfg cu + docker stop mtlab-mt5-hist (script nay lam giup voi --cleanup)
Khung: M1,M5,M15,H1 lay NATIVE; H4,D1 GOP tu H1 theo moc UTC (giong feed canon). Gio may chu MT5 -> UTC: tu dong do bang cach
doi chieu nen H1 da co trong canon (offset ung vien 0..4 gio), khong khop thi dung lai.
Idempotent: INSERT ON CONFLICT DO NOTHING; nen DANG DO (volume thap hon ban native, ts >= --fix-partial-from) duoc cap nhat lai.
READ-ONLY: chi CopyRates qua terminal phu, khong co duong dat lenh.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SOURCE = "canon:mt5:100000001"
PG = "tradingsys-timescaledb-1"
XCHG = "/wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/xchg"
TF_SEC = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
NATIVE = ("M1", "M5", "M15", "H1")
UTC = timezone.utc


def sh(cmd: list[str], inp: str | None = None, check=True) -> str:
    r = subprocess.run(cmd, input=inp, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"loi {cmd[:4]}: {r.stderr.strip()[:300]}")
    return r.stdout


def psql(sql: str) -> str:
    return sh(["docker", "exec", "-i", PG, "sh", "-c", 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d ts -At'], sql)


class Range:
    def __init__(self, container: str, timeout=90.0):
        self.c, self.timeout = container, timeout

    def _x(self, script: str, inp: str | None = None, check=True) -> str:
        return sh(["docker", "exec", "-i", self.c, "bash", "-c", script], inp, check)

    def fetch(self, sym: str, tf: str, f_srv: int, t_srv: int) -> list[tuple]:
        rid = f"{sym}_{tf}_{f_srv}_{t_srv}"
        self._x(f"mkdir -p '{XCHG}/req' '{XCHG}/res'; rm -f '{XCHG}/res/{rid}.'*; cat > '{XCHG}/req/{rid}.tmp' && mv '{XCHG}/req/{rid}.tmp' '{XCHG}/req/{rid}.json'",
                json.dumps({"symbol": sym, "tf": tf, "from": f_srv, "to": t_srv}))
        t0 = time.monotonic()
        while True:
            msg = self._x(f"cat '{XCHG}/res/{rid}.done' 2>/dev/null", check=False).strip()
            if msg:
                break
            if time.monotonic() - t0 > self.timeout:
                raise TimeoutError(f"terminal phu khong tra loi {rid} trong {self.timeout}s")
            time.sleep(1.0)
        if msg.startswith("err"):
            self._x(f"rm -f '{XCHG}/res/{rid}.'* '{XCHG}/req/{rid}.json'")
            if "no_data" in msg:
                return []
            raise RuntimeError(f"{rid}: {msg}")
        body = self._x(f"cat '{XCHG}/res/{rid}.csv'")
        self._x(f"rm -f '{XCHG}/res/{rid}.'* '{XCHG}/req/{rid}.json'")
        out = []
        for row in csv.reader(io.StringIO(body)):
            if row and row[0].isdigit():
                out.append((int(row[0]), *(float(x) for x in row[1:6])))
        return out


def ok_bar(o, h, l, c) -> bool:
    return min(o, h, l, c) > 0 and h >= max(o, c, l) and l <= min(o, c, h)


def resample(h1: list[tuple], sec: int, now: datetime) -> list[tuple]:
    """h1: (ts_utc_epoch,o,h,l,c,v) -> nen `sec` theo moc UTC; chi giu bucket da dong (end <= now)."""
    b: dict[int, list[tuple]] = {}
    for r in sorted(h1):
        b.setdefault(r[0] // sec * sec, []).append(r)
    out = []
    for k, rs in sorted(b.items()):
        if k + sec > now.timestamp():
            continue
        out.append((k, rs[0][1], max(x[2] for x in rs), min(x[3] for x in rs), rs[-1][4], sum(x[5] for x in rs)))
    return out


def detect_offset(rg: Range, sym: str, f: datetime) -> int:
    """Doi chieu H1 native voi canon da co (>= 3 nen) de tim offset may chu - UTC (giay)."""
    rows = psql(f"SELECT extract(epoch from ts_open)::bigint, o, h, l, c FROM bars WHERE source='{SOURCE}' AND symbol='{sym}' AND tf='H1' "
                f"AND ts_open >= '{f.isoformat()}' ORDER BY ts_open LIMIT 4 OFFSET 2")
    ref = {int(r.split("|")[0]): tuple(float(x) for x in r.split("|")[1:]) for r in rows.split() if r}
    if len(ref) < 2:
        raise SystemExit("khong du nen H1 canon de do offset gio may chu")
    lo, hi = min(ref), max(ref)
    for off in (3, 2, 0, 1, 4):
        got = rg.fetch(sym, "H1", lo + off * 3600, hi + off * 3600)
        m = {r[0] - off * 3600: r[1:5] for r in got}
        if m and all(k in m and all(abs(m[k][i] - ref[k][i]) < 1e-6 for i in range(4)) for k in ref):
            return off * 3600
    raise SystemExit("khong khop offset gio may chu voi canon (0..4 gio): dung, kiem tra tay")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default="mtlab-mt5-hist")
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,XAUUSD,US500,US30,USTEC")
    ap.add_argument("--from", dest="t0", default="2026-10-15T00:00", help="UTC, can ngay (de gop D1/H4 dung)")
    ap.add_argument("--to", dest="t1", default=None, help="UTC, mac dinh bay gio")
    ap.add_argument("--fix-partial-from", default="2026-10-15T04:00", help="UTC: nen canon DANG DO >= moc nay duoc cap nhat lai")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.t0).replace(tzinfo=UTC)
    now = datetime.now(UTC)
    t1 = datetime.fromisoformat(a.t1).replace(tzinfo=UTC) if a.t1 else now
    fixp = datetime.fromisoformat(a.fix_partial_from).replace(tzinfo=UTC)
    rg = Range(a.container)
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    rows: list[list] = []
    off = None
    for sym in syms:
        if off is None:
            off = detect_offset(rg, sym, t0)
            print(f"offset may chu - UTC = {off // 3600} gio (da doi chieu canon)", file=sys.stderr)
        h1utc: list[tuple] = []
        for tf in NATIVE:
            sec = TF_SEC[tf]
            got = rg.fetch(sym, tf, int(t0.timestamp()) + off, int(t1.timestamp()) + off)
            n_in = 0
            for ts, o, h, l, c, v in got:
                u = ts - off
                if u % sec or u + sec > now.timestamp() or not ok_bar(o, h, l, c):
                    continue
                rows.append([sym, tf, datetime.fromtimestamp(u, UTC).isoformat(), o, h, l, c, v])
                n_in += 1
                if tf == "H1":
                    h1utc.append((u, o, h, l, c, v))
            print(f"{sym} {tf}: native={len(got)} hop_le={n_in}", file=sys.stderr)
        for tf in ("H4", "D1"):
            for k, o, h, l, c, v in resample(h1utc, TF_SEC[tf], now):
                if k >= t0.timestamp():
                    rows.append([sym, tf, datetime.fromtimestamp(k, UTC).isoformat(), o, h, l, c, v])
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    sql = ("BEGIN;\nCREATE TEMP TABLE _g(symbol text, tf text, ts_open timestamptz, o float8, h float8, l float8, c float8, v float8) ON COMMIT DROP;\n"
           "COPY _g FROM STDIN WITH (FORMAT csv);\n" + buf.getvalue() + "\\.\n"
           f"SELECT 'staged', tf, count(*) FROM _g GROUP BY tf ORDER BY tf;\n"
           f"SELECT 'moi', g.tf, count(*) FROM _g g WHERE NOT EXISTS (SELECT 1 FROM bars b WHERE b.symbol=g.symbol AND b.tf=g.tf AND b.ts_open=g.ts_open AND b.source='{SOURCE}') GROUP BY g.tf ORDER BY g.tf;\n"
           f"SELECT 'dang_do_se_cap_nhat', g.tf, count(*) FROM _g g JOIN bars b ON b.symbol=g.symbol AND b.tf=g.tf AND b.ts_open=g.ts_open AND b.source='{SOURCE}' "
           f"WHERE g.ts_open >= '{fixp.isoformat()}' AND b.v < g.v GROUP BY g.tf ORDER BY g.tf;\n")
    if a.dry_run:
        print(psql(sql + "ROLLBACK;\n"))
        return
    sql += (f"UPDATE bars b SET o=g.o,h=g.h,l=g.l,c=g.c,v=g.v FROM _g g WHERE b.symbol=g.symbol AND b.tf=g.tf AND b.ts_open=g.ts_open AND b.source='{SOURCE}' "
            f"AND g.ts_open >= '{fixp.isoformat()}' AND b.v < g.v;\n"
            f"INSERT INTO bars(symbol,tf,ts_open,o,h,l,c,v,source) SELECT symbol,tf,ts_open,o,h,l,c,v,'{SOURCE}' FROM _g ON CONFLICT (symbol,tf,ts_open,source) DO NOTHING;\nCOMMIT;\n")
    print(psql(sql))


if __name__ == "__main__":
    main()
