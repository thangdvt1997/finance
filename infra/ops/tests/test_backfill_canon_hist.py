"""Chay: docker run --rm -v $PWD/infra/ops:/ops:ro --entrypoint python tradingsys-analytics:latest -m unittest discover -s /ops/tests"""
import sys, unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backfill_canon_hist import resample_utc  # noqa: E402


def h1(start, n, step=1.0):
    ts = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"ts_open": ts, "o": [100 + i * step for i in range(n)], "h": [101 + i * step for i in range(n)],
                         "l": [99 + i * step for i in range(n)], "c": [100.5 + i * step for i in range(n)], "v": [10.0] * n})


class T(unittest.TestCase):
    def test_h4_utc_alignment_and_ohlc(self):
        r = resample_utc(h1("2026-10-12 00:00", 8), "H4")
        self.assertEqual([t.hour for t in r.ts_open], [0, 4])
        a = r.iloc[0]
        self.assertEqual((a.o, a.h, a.l, a.c, a.v), (100, 104, 99, 103.5, 40))

    def test_h4_not_server_time(self):
        # H1 bat dau 01:00 UTC (lech): bucket 00:00 chi co 3 nen, van moc 00 (khong 01/21)
        r = resample_utc(h1("2026-10-12 01:00", 7), "H4")
        self.assertEqual([t.hour for t in r.ts_open], [0, 4])
        self.assertEqual(r.iloc[0].v, 30)

    def test_d1_midnight_utc(self):
        r = resample_utc(h1("2026-10-12 00:00", 48), "D1")
        self.assertEqual(len(r), 2)
        self.assertTrue(all(t.hour == 0 for t in r.ts_open))
        self.assertEqual(r.iloc[1].o, 124)

    def test_cutoff_only_closed_buckets(self):
        r = resample_utc(h1("2026-10-12 00:00", 12), "H4", cutoff=pd.Timestamp("2026-10-12 08:00", tz="UTC"))
        self.assertEqual([t.hour for t in r.ts_open], [0, 4])
        r = resample_utc(h1("2026-10-12 00:00", 12), "H4", cutoff=pd.Timestamp("2026-10-12 07:59", tz="UTC"))
        self.assertEqual([t.hour for t in r.ts_open], [0])

    def test_ms_precision_timestamps(self):
        d = h1("2026-10-12 00:00", 4)
        d["ts_open"] = d["ts_open"].astype("datetime64[ms, UTC]")
        r = resample_utc(d, "H4")
        self.assertEqual(len(r), 1)
        self.assertEqual(r.iloc[0].ts_open, pd.Timestamp("2026-10-12 00:00", tz="UTC"))


if __name__ == "__main__":
    unittest.main()
