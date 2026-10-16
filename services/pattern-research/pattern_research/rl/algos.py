"""Hai thuat toan nhe (khong torch): ES tuyen tinh va Q-learning bang. Deu deterministic theo seed."""
from __future__ import annotations

import numpy as np

from .env import POS, simulate


def _ctx(X):
    return np.column_stack([X, np.ones(len(X))])


# ---- ES (tien hoa chien luoc) chinh sach tuyen tinh 3 hanh dong (vi the chi phu thuoc dac trung) ----
def es_fit(X, nxt, cost, seed, iters=40, pop=24, sigma=0.3, lr=0.1, ann=1e4):
    rng = np.random.default_rng(seed)
    Z = _ctx(X); W = rng.normal(0, 0.05, (Z.shape[1], 3))
    def fit(W):
        pos = POS[(Z @ W).argmax(1)]
        return simulate(pos, nxt, cost).mean() * ann
    for _ in range(iters):
        E = rng.normal(0, 1, (pop, *W.shape))
        R = np.array([fit(W + sigma * e) for e in E])
        A = (R - R.mean()) / (R.std() + 1e-9)
        W = W + lr / (pop * sigma) * np.tensordot(A, E, 1) * sigma
    return W


def es_act(W, X, prev=0.0):
    return POS[(_ctx(X) @ W).argmax(1)]


# ---- Q-learning bang: trang thai roi rac (dau r1, tercile r6, r24, vi the) ----
def _disc(X, edges):
    s = np.zeros(len(X), int)
    for j, e in zip((0, 2, 4), edges):  # r1, r6, r24
        s = s * 3 + np.digitize(X[:, j], e)
    return s


def q_fit(X, nxt, cost, seed, epochs=12, alpha=0.1, gamma=0.5, eps0=0.5, ann=1e4):
    rng = np.random.default_rng(seed)
    edges = [np.quantile(X[:, j], [1 / 3, 2 / 3]) for j in (0, 2, 4)]
    S = _disc(X, edges); n = len(S)
    Q = np.zeros((27, 3, 3))  # [state, pos_idx, action]
    for ep in range(epochs):
        eps = eps0 * (1 - ep / epochs)
        pi = 0
        for t in range(n - 1):
            a = rng.integers(3) if rng.random() < eps else int(Q[S[t], pi].argmax())
            r = (POS[a] * nxt[t] - cost[t] * abs(POS[a] - POS[pi])) * ann
            Q[S[t], pi, a] += alpha * (r + gamma * Q[S[t + 1], a].max() - Q[S[t], pi, a])
            pi = a
    return Q, edges


def q_act(model, X, prev=0.0):
    Q, edges = model
    S = _disc(X, edges); pi = 0; out = np.zeros(len(S))
    for t in range(len(S)):
        a = int(Q[S[t], pi].argmax()); out[t] = POS[a]; pi = a
    return out
