"""Test meta-labeling (khong can du lieu that)."""
import numpy as np
import pandas as pd

from pattern_research.metalabel.cv import kfold_blocks, purged_masks
from pattern_research.metalabel.features import bar_features
from pattern_research.metalabel.run import select


def mkbars(n=300, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({"o": c, "h": c + 1, "l": c - 1, "c": c, "v": rng.integers(1, 100, n).astype(float)})


def test_features_no_lookahead():
    df = mkbars()
    a = bar_features(df, "H1")
    df2 = df.copy()
    df2.loc[200:, ["o", "h", "l", "c", "v"]] *= 3          # doi tuong lai (>=200)
    b = bar_features(df2, "H1")
    pd.testing.assert_frame_equal(a.iloc[:200], b.iloc[:200])


def test_purge_removes_overlap_and_embargo():
    ts = pd.date_range("2020-01-01", periods=100, freq="D")
    entry, exit_ = pd.Series(ts), pd.Series(ts + pd.Timedelta(days=10))
    lo, hi = ts[50], ts[60]
    trm, tem = purged_masks(entry, exit_, lo, hi, pd.Timedelta(days=5))
    assert tem.sum() == 10
    assert not (trm & tem).any()
    assert not trm[36] and not trm[64] and trm[30] and trm[70]   # lenh mo chong test / trong embargo bi loai


def test_kfold_and_select_topq():
    e = pd.Series(pd.date_range("2020-01-01", periods=80, freq="D"))
    bl = kfold_blocks(e, 4)
    assert len(bl) == 4 and bl[0][0] == e.min()
    score = np.arange(20.0)
    sel = select(score, np.zeros(20, int), 0.25)
    assert sel.sum() == 5 and sel[15:].all()
