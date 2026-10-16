"""Bo sung D1 SAU tu bang bars san co (yahoo_daily): US500_SPY (ETF, 1993+) va XAUUSD_GC (futures GC=F, 2000+).
Doc CSV do psql xuat (COPY) -> Parquet cung schema/split. Chay sau build:  python -m pattern_research.export_db_d1 /out/db_d1"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from .build import OUT, label_split, sha

EXTRA = {"US500_SPY": "US:SPY", "XAUUSD_GC": "XAUUSD"}


def main(src: Path):
    sp = json.loads((OUT / "splits.json").read_text())
    man = json.loads((OUT / "manifest.json").read_text())
    man["files"] = [f for f in man["files"] if f["symbol"] not in EXTRA]
    for name in EXTRA:
        df = pd.read_csv(src / f"{name}.csv", names=["ts_open", "o", "h", "l", "c", "v"], header=None)
        df["ts_open"] = pd.to_datetime(df["ts_open"], utc=True)
        df = df.drop_duplicates("ts_open").sort_values("ts_open")
        df = df[(df.h >= df[["o", "c", "l"]].max(axis=1)) & (df.l <= df[["o", "c", "h"]].min(axis=1)) & (df.l > 0)]
        df["n_m1"] = 1440
        df["n_m1"] = df["n_m1"].astype("int16")
        df["split"] = label_split(df["ts_open"], sp)
        p = OUT / "bars" / f"{name}_D1.parquet"
        df.to_parquet(p, index=False)
        man["files"].append({"symbol": name, "tf": "D1", "source": "db_yahoo_daily", "from": df.ts_open.iloc[0].isoformat(),
                             "to": df.ts_open.iloc[-1].isoformat(), "bars": len(df), "partial_bar_pct": 0.0,
                             "missing_m1_pct": None, "session": "exchange daily",
                             "split_bars": {k: int(v) for k, v in df.split.value_counts().items()}, "sha": sha(p)})
        print(name, len(df), flush=True)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
