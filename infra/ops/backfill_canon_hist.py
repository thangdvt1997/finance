#!/usr/bin/env python3
"""Nap LICH SU GAN cho chuoi canon (source='canon:mt5:100000001') tu parquet MT5 (data/research/patterns/mt5/bars).

Chay tren VPS (host, can docker; user nhom docker):
  python3 infra/ops/backfill_canon_hist.py --dry-run                 # chi bao cao, khong ghi DB
  python3 infra/ops/backfill_canon_hist.py                           # nap 3 chi so, 2 nam, M15/H1/H4/D1
  python3 infra/ops/backfill_canon_hist.py --symbols US500 --years 1 --tfs M15,H1

Quy tac:
- M15/H1: lay native parquet (ts_open da la UTC; lech server EET la so gio nguyen nen moc khop).
- H4/D1: KHONG dung parquet native (cat theo gio server EET) -> gop tu H1 theo moc UTC (H4 00,04,..; D1 00:00 UTC), giong feed.py.
- Chi ghi nen DA DONG truoc nen canon M1 som nhat hien co cua ma (M1 chi do feed song ghi; M15+ lich su khong lam doi moc -> idempotent) (ts_open + tf <= cutoff) -> khong chong len canon song.
- Idempotent: INSERT ... ON CONFLICT DO NOTHING (khong ghi de). Dong bo: ma khong du lieu/ khong canon -> bo qua, bao cao.
Phan doc parquet chay trong container tradingsys-analytics (--user root, file thuoc root); phan SQL qua docker exec psql.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = "canon:mt5:100000001"
TF_SEC = {"M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
NATIVE = ("M15", "H1")
_P = Path(__file__).resolve().parents
ROOT = _P[2] if len(_P) > 2 else Path('/root/trading-system')
PG = "tradingsys-timescaledb-1"


def resample_utc(h1, tf: str, cutoff=None):
    """H1 (DataFrame: ts_open UTC tz-aware, o,h,l,c,v) -> nen `tf` (H4/D1) theo moc UTC.
    Bucket chi giu khi co >=1 nen H1 va (cutoff None hoac bucket_end <= cutoff). Tra DataFrame ts_open,o,h,l,c,v."""
    import pandas as pd

    sec = TF_SEC[tf]
    d = h1.sort_values("ts_open").copy()
    ts = d["ts_open"]
    d["b"] = pd.to_datetime(_to_epoch_s(ts) // sec * sec, unit="s", utc=True)
    g = d.groupby("b", sort=True)
    out = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last(), "v": g["v"].sum()})
    out.index.name = "ts_open"
    out = out.reset_index()
    if cutoff is not None:
        out = out[out["ts_open"] + pd.Timedelta(seconds=sec) <= pd.Timestamp(cutoff)]
    return out.reset_index(drop=True)


def _to_epoch_s(ts):
    """Series datetime tz-aware (bat ky don vi) -> epoch giay (int64)."""
    import pandas as pd

    return (ts - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)


def export(args) -> None:
    """Chay trong container: doc parquet -> CSV (symbol,tf,ts_open_iso,o,h,l,c,v)."""
    import pandas as pd

    cut = {k: pd.Timestamp(v) for k, v in (x.split("=") for x in args.cutoffs.split(","))}
    rows = 0
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        for sym in args.symbols.split(","):
            c = cut[sym]
            start = c - pd.Timedelta(days=int(365.25 * args.years))
            frames = {}
            for tf in NATIVE:
                p = Path(args.bars) / f"{sym}_{tf}.parquet"
                d = pd.read_parquet(p, columns=["ts_open", "o", "h", "l", "c", "v"])
                d["ts_open"] = pd.to_datetime(d["ts_open"], utc=True)
                d = d.drop_duplicates("ts_open")
                frames[tf] = d[d["ts_open"] >= start - pd.Timedelta(days=2)]
            out = {}
            for tf in NATIVE:
                d = frames[tf]
                out[tf] = d[(d["ts_open"] >= start) & (d["ts_open"] + pd.Timedelta(seconds=TF_SEC[tf]) <= c)]
            for tf in ("H4", "D1"):
                r = resample_utc(frames["H1"], tf, c)
                out[tf] = r[r["ts_open"] >= start]
            for tf, d in out.items():
                if tf not in args.tfs.split(","):
                    continue
                for t, o, h, l, cl, v in d[["ts_open", "o", "h", "l", "c", "v"]].itertuples(index=False):
                    w.writerow([sym, tf, t.strftime("%Y-%m-%dT%H:%M:%S+00:00"), o, h, l, cl, v])
                    rows += 1
    print(f"export rows={rows}", file=sys.stderr)


def psql(sql: str, stdin: str | None = None) -> str:
    cmd = ["docker", "exec", "-i", PG, "sh", "-c", 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d ts -At']
    r = subprocess.run(cmd, input=(stdin if stdin is not None else sql), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"psql loi: {r.stderr.strip()[:500]}")
    return r.stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="US500,US30,USTEC")
    ap.add_argument("--tfs", default="M15,H1,H4,D1")
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bars", default="/out/mt5/bars", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--cutoffs", help=argparse.SUPPRESS)
    ap.add_argument("--export", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.export:
        return export(a)

    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    inl = ",".join(f"'{s}'" for s in syms)
    res = psql(f"SELECT symbol, to_char(min(ts_open) AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"') "
               f"FROM bars WHERE source='{SOURCE}' AND tf='M1' AND symbol IN ({inl}) GROUP BY symbol")
    cut = dict(l.split("|") for l in res.split() if "|" in l)
    for s in syms:
        if s not in cut:
            print(f"BO QUA {s}: chua co nen canon M1 song -> khong co moc cat")
    syms = [s for s in syms if s in cut]
    if not syms:
        raise SystemExit("khong co ma nao")
    with tempfile.TemporaryDirectory(dir=str(ROOT / "data")) as td:
        subprocess.run(["chmod", "755", td], check=True)
        cmd = ["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}/data/research/patterns:/out:ro",
               "-v", f"{ROOT}/infra/ops:/ops:ro", "-v", f"{td}:/w", "-e", "PYTHONPATH=/out/.pylib",
               "--entrypoint", "python", "tradingsys-analytics:latest", "/ops/backfill_canon_hist.py", "--export",
               "--symbols", ",".join(syms), "--tfs", a.tfs, "--years", str(a.years),
               "--cutoffs", ",".join(f"{s}={cut[s]}" for s in syms), "--out", "/w/bars.csv"]
        subprocess.run(cmd, check=True)
        data = (Path(td) / "bars.csv").read_text()
    sql = ("BEGIN;\nCREATE TEMP TABLE _h(symbol text, tf text, ts_open timestamptz, o float8, h float8, l float8, c float8, v float8) ON COMMIT DROP;\n"
           "COPY _h FROM STDIN WITH (FORMAT csv);\n" + data + "\\.\n"
           "SELECT 'staged', symbol, tf, count(*), min(ts_open), max(ts_open) FROM _h GROUP BY 2,3 ORDER BY 2,3;\n")
    if a.dry_run:
        sql += ("SELECT 'would_insert', h.symbol, h.tf, count(*) FROM _h h WHERE NOT EXISTS (SELECT 1 FROM bars b WHERE b.symbol=h.symbol AND b.tf=h.tf "
                f"AND b.ts_open=h.ts_open AND b.source='{SOURCE}') GROUP BY 2,3 ORDER BY 2,3;\nROLLBACK;\n")
    else:
        sql += (f"WITH i AS (INSERT INTO bars(symbol,tf,ts_open,o,h,l,c,v,source) SELECT symbol,tf,ts_open,o,h,l,c,v,'{SOURCE}' FROM _h "
                "ON CONFLICT DO NOTHING RETURNING symbol, tf) SELECT 'inserted', symbol, tf, count(*) FROM i GROUP BY 2,3 ORDER BY 2,3;\nCOMMIT;\n")
    print("cutoff:", cut)
    print(psql(sql))


if __name__ == "__main__":
    main()
