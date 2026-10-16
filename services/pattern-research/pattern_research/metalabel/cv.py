"""CV theo thoi gian: purge (loai lenh train chong lan khoang test) + embargo; walk-forward theo nam."""
from __future__ import annotations

import numpy as np
import pandas as pd


def purged_masks(entry: pd.Series, exit_: pd.Series, test_lo, test_hi, embargo: pd.Timedelta):
    """(train_mask, test_mask). test = lenh co entry trong [test_lo, test_hi). Train loai: lenh co khoang [entry, exit]
    chong lan [test_lo - embargo, test_hi + embargo) (purge) — kem lenh dang mo luc test bat dau / ket thuc sau test_lo."""
    te = (entry >= test_lo) & (entry < test_hi)
    overlap = (entry < test_hi + embargo) & (exit_ >= test_lo - embargo)
    return ~overlap, te


def kfold_blocks(entry: pd.Series, k: int):
    """k khoi lien tiep theo thoi gian co so lenh xap xi nhau -> [(lo, hi)]."""
    q = entry.sort_values().to_numpy()
    cuts = [q[int(len(q) * i / k)] for i in range(k)] + [q.max() + np.timedelta64(1, "s")]
    return [(pd.Timestamp(cuts[i]), pd.Timestamp(cuts[i + 1])) for i in range(k)]


def wf_chunks(first_year: int, val_start: pd.Timestamp, test_start: pd.Timestamp):
    """Cac khoi danh gia ngoai mau, giong walk-forward cu: nam first_year..2024, 2025H1, VAL (het truoc embargo cua TEST)."""
    f = [(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01"), str(y)) for y in range(first_year, 2025)]
    f.append((pd.Timestamp("2025-01-01"), val_start, "2025H1"))
    f.append((val_start, test_start - pd.Timedelta(days=5), "VAL"))
    return f
