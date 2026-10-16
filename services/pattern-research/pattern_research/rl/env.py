"""Moi truong gym-like (gymnasium neu co, khong thi lop tuong thich) tren nen H1.
Hanh dong {0 flat, 1 long, 2 short}; thuong = vi the*loi suat nen ke tiep - chi phi*|doi vi the|.
Chi phi lay tu COSTS cua backtest (san spread + truot gia), nua spread moi chieu + truot gia."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..backtest import COSTS
from ..loader import load

try:  # gymnasium la tuy chon (pip cai duoc, khong can torch)
    import gymnasium as gym
    from gymnasium import spaces
    _Base = gym.Env
except Exception:  # pragma: no cover
    gym = spaces = None
    _Base = object

POS = np.array([0.0, 1.0, -1.0])
FEATS = ["r1", "r3", "r6", "r12", "r24", "vol", "z24", "hs", "hc", "dw"]
LAG_SPLITS = ("train", "val")  # tuyet doi khong nap test


def cost_frac(symbol: str, close: np.ndarray) -> np.ndarray:
    """Chi phi (ti le gia) cho moi don vi doi vi the = spread/2 + truot gia (don vi gia / close)."""
    c = COSTS[symbol]
    if "spread_floor" in c:
        return (c["spread_floor"] / 2 + c["slip"] + c["comm"]) / close
    return np.full(len(close), (c["spread_bps"] / 2 + c["slip_bps"] + c["comm_bps"] / 2) * 1e-4)


def load_dev(symbol: str) -> pd.DataFrame:
    parts = [load(symbol, "H1", split=s, min_fill=0.5) for s in LAG_SPLITS]
    df = pd.concat(parts).sort_index()
    assert (df.split != "test").all()
    return df[~df.index.duplicated()]


def make_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(X, nxt_ret, cost) - dac trung chi dung gia den het nen t; nxt_ret = c[t+1]/c[t]-1 (nen cuoi = 0)."""
    c = df["c"].to_numpy(float)
    lr = np.log(c)
    def ret(k):
        x = np.full(len(c), 0.0); x[k:] = lr[k:] - lr[:-k]; return x
    r1 = ret(1)
    vol = pd.Series(r1).rolling(48, min_periods=10).std().bfill().to_numpy() + 1e-8
    ma = pd.Series(c).rolling(24, min_periods=5).mean().bfill().to_numpy()
    h = df.index.hour.to_numpy()
    X = np.column_stack([r1 / vol, ret(3) / (vol * 3 ** .5), ret(6) / (vol * 6 ** .5), ret(12) / (vol * 12 ** .5),
                         ret(24) / (vol * 24 ** .5), vol * 100, (c - ma) / (c * vol * 5),
                         np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24), df.index.dayofweek.to_numpy() / 4.0])
    X = np.clip(X, -5, 5)
    nxt = np.zeros(len(c)); nxt[:-1] = c[1:] / c[:-1] - 1
    # khe cuoi tuan/ngay nghi: bo loi suat bat thuong (> 8 sigma) khoi thuong de khong nhieu
    return X, nxt, cost_frac(df.attrs.get("symbol", "EURUSD"), c)


def simulate(pos: np.ndarray, nxt: np.ndarray, cost: np.ndarray, prev: float = 0.0) -> np.ndarray:
    """Loi suat tung nen (gom chi phi) cua chuoi vi the; vi the dau tu 'prev'."""
    p_prev = np.concatenate([[prev], pos[:-1]])
    return pos * nxt - cost * np.abs(pos - p_prev)


class TradingEnv(_Base):
    """gym-like: obs = [dac trung, vi the hien tai]; step(a) -> (obs, reward, terminated, truncated, info)."""
    def __init__(self, X, nxt, cost):
        self.X, self.nxt, self.cost = X, nxt, cost
        self.n = len(nxt)
        if spaces:
            self.observation_space = spaces.Box(-5, 5, (X.shape[1] + 1,), np.float32)
            self.action_space = spaces.Discrete(3)
        self.t = 0; self.pos = 0.0

    def _obs(self):
        return np.append(self.X[self.t], self.pos).astype(np.float32)

    def reset(self, seed=None, options=None):
        self.t = 0; self.pos = 0.0
        return self._obs(), {}

    def step(self, a):
        newp = POS[int(a)]
        r = newp * self.nxt[self.t] - self.cost[self.t] * abs(newp - self.pos)
        self.pos = newp; self.t += 1
        done = self.t >= self.n - 1
        return self._obs(), float(r), done, False, {}
