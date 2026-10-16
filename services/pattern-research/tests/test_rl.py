import numpy as np
import pandas as pd

from pattern_research.rl import algos
from pattern_research.rl.env import TradingEnv, simulate, make_features


def _df(n=600, sym="EURUSD"):
    rg = np.random.default_rng(0)
    c = 1.1 * np.exp(np.cumsum(rg.normal(0, 1e-3, n)))
    d = pd.DataFrame({"c": c}, index=pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"))
    d.attrs["symbol"] = sym
    return d


def test_cost_and_flat():
    nxt = np.array([0.01, -0.01, 0.0]); cost = np.full(3, 0.001)
    assert np.allclose(simulate(np.zeros(3), nxt, cost), 0)
    r = simulate(np.array([1.0, -1.0, -1.0]), nxt, cost)
    assert np.allclose(r, [0.01 - 0.001, 0.01 - 0.002, 0.0])


def test_env_and_algos_deterministic():
    X, nxt, cost = make_features(_df())
    env = TradingEnv(X, nxt, cost); o, _ = env.reset()
    o, r, d, *_ = env.step(1); assert o.shape[0] == X.shape[1] + 1 and r <= nxt[0]
    a = algos.es_act(algos.es_fit(X, nxt, cost, 1, iters=3), X)
    b = algos.es_act(algos.es_fit(X, nxt, cost, 1, iters=3), X)
    assert (a == b).all()
    m = algos.q_fit(X[:200], nxt[:200], cost[:200], 1, epochs=1)
    assert len(algos.q_act(m, X[:50])) == 50


def test_no_test_split():
    from pattern_research.rl.env import load_dev
    assert (load_dev("EURUSD").split != "test").all()
