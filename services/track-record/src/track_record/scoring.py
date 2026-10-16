"""Cham diem KHACH QUAN: hit-rate + Wilson, loi suat theo huong + stationary block bootstrap, kiem dinh hoan vi nhan huong,
hieu chinh Benjamini-Hochberg tren TOAN HO kiem dinh, co Beta ve 0,5, trong so. Ham thuan (numpy), co dinh seed => tai lap duoc."""
from __future__ import annotations

import math
import zlib
from datetime import datetime
from typing import Any, Optional

import numpy as np

from . import config as C

Item = dict[str, Any]
Z95 = 1.959963984540054


def seed_of(*parts: str) -> int:
    return (C.SEED + zlib.crc32("|".join(parts).encode())) & 0x7FFFFFFF


# ---------- mau doc lap ----------
def independent(items: list[Item]) -> list[Item]:
    """Moi (entity, symbol): giu quan diem co entry_ts >= exit_ts cua quan diem da giu truoc do (cua so khong chong lan). Tra theo entry_ts."""
    last: dict[tuple, datetime] = {}
    out = []
    for it in sorted(items, key=lambda x: (x["entry_ts"], x["view_id"])):
        k = (it["entity_id"], it["symbol"])
        if k in last and it["entry_ts"] < last[k]:
            continue
        last[k] = it["exit_ts"]
        out.append(it)
    return out


# ---------- thong ke ----------
def wilson(k: int, n: int, z: float = Z95) -> tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def block_bootstrap_ci(x: np.ndarray, rng: np.random.Generator, B: int = C.N_BOOT, alpha: float = 0.05) -> tuple[float, float]:
    """Stationary bootstrap (Politis-Romano), do dai khoi TB ~ n^(1/3); CI percentile cho TRUNG BINH."""
    n = len(x)
    b = max(2.0, round(n ** (1 / 3)))
    idx = np.empty((B, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, B)
    for t in range(1, n):
        restart = rng.random(B) < 1.0 / b
        idx[:, t] = np.where(restart, rng.integers(0, n, B), (idx[:, t - 1] + 1) % n)
    means = x[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def perm_p(d: np.ndarray, r: np.ndarray, rng: np.random.Generator, P: int = C.N_PERM) -> float:
    """H0: nhan huong khong mang thong tin ve loi suat. Thong ke T = mean(d*r); hoan vi nhan huong (giu ti le mua/ban); p mot phia = (1+#{T*>=T})/(1+P)."""
    n = len(d)
    obs = float(np.mean(d * r))
    cnt, done, chunk = 0, 0, max(50, min(500, 4_000_000 // max(n, 1)))
    while done < P:
        c = min(chunk, P - done)
        m = np.tile(d, (c, 1))
        rng.permuted(m, axis=1, out=m)
        cnt += int(np.sum((m * r).mean(axis=1) >= obs - 1e-12))
        done += c
    return (cnt + 1) / (P + 1)


def bh_qvalues(p: list[float]) -> list[float]:
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    ps = np.asarray(p)[order]
    q = np.minimum.accumulate((ps * m / (np.arange(m) + 1))[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out.tolist()


def prior_of(kind: str) -> tuple[float, float]:
    k, tilt = C.PRIORS.get(kind, C.PRIORS["other"])
    return k, max(-0.02, min(0.02, tilt))


def shrink(hits: int, n: int, kind: str) -> tuple[float, float]:
    """(post_mean, prior_mean): Beta(k*m0, k*(1-m0)) + hits/n."""
    k, tilt = prior_of(kind)
    m0 = 0.5 + tilt
    return (hits + k * m0) / (n + k), m0


def weight_of(post_mean: float, rated: bool) -> float:
    return max(0.25, min(2.0, 1.0 + 6.0 * (post_mean - 0.5))) if rated else 1.0


# ---------- the cham ----------
def arrays(sample: list[Item]) -> tuple[np.ndarray, np.ndarray]:
    d = np.array([1.0 if it["direction"] == "bullish" else -1.0 for it in sample])
    r = np.array([it["raw"] for it in sample])
    return d, r


def basic_stats(sample: list[Item], seed_key: str, full: bool) -> dict[str, Any]:
    n = len(sample)
    d, r = arrays(sample) if n else (np.array([]), np.array([]))
    hits = int(np.sum(d * r > 0)) if n else 0
    lo, hi = wilson(hits, n)
    out: dict[str, Any] = {"n": n, "hits": hits, "hit_rate": (hits / n) if n else None, "ci_low": lo, "ci_high": hi,
                           "mean_ret_pct": float(np.mean(d * r) * 100) if n else None, "ret_ci_low": None, "ret_ci_high": None, "p_value": None}
    if full and n >= C.MIN_N:
        if n > C.MAX_PERM_N:                                   # lay MOI NHAT, tranh chi phi khong gioi han
            d, r = d[-C.MAX_PERM_N:], r[-C.MAX_PERM_N:]
        rng = np.random.default_rng(seed_of(seed_key))
        lo_r, hi_r = block_bootstrap_ci(d * r, rng)
        out["ret_ci_low"], out["ret_ci_high"] = lo_r * 100, hi_r * 100
        out["p_value"] = perm_p(d, r, rng)
    return out


def scopes_of(it: Item) -> list[str]:
    return ["all", it["asset_class"], "sym:" + it["symbol"]]


def compute_cards(items_by_entity: dict[str, dict[str, list[Item]]], entities: dict[str, dict], view_counts: dict[tuple, int],
                  last_view_at: dict[str, Optional[datetime]], symbols_n: dict[str, int]) -> tuple[dict[tuple, dict], dict]:
    """items_by_entity[entity_id][horizon] = list ITEM DA CHAM (chua loc doc lap); view_counts[(entity_id, scope)] = so quan diem (ke ca chua cham).
    Tra (cards[(eid,scope,hz)], summary)."""
    cards: dict[tuple, dict] = {}
    tests: list[tuple] = []
    for eid, ent in entities.items():
        kind = ent["kind"]
        for hz in C.HORIZONS:
            all_items = items_by_entity.get(eid, {}).get(hz, [])
            groups: dict[str, list[Item]] = {"all": all_items}
            for (e2, sc0), _n in view_counts.items():
                if e2 == eid:
                    groups.setdefault(sc0, [])
            for it in all_items:
                for sc in scopes_of(it)[1:]:
                    groups.setdefault(sc, []).append(it)
            for sc, its in groups.items():
                sample = independent(its)
                st = basic_stats(sample, f"{eid}|{sc}|{hz}", full=True)
                rated = st["n"] >= C.MIN_N
                post, m0 = shrink(st["hits"], st["n"], kind)
                st.update(entity_id=eid, scope=sc, horizon=hz, n_total=view_counts.get((eid, sc), 0), status="rated" if rated else "insufficient",
                          score=round(100 * post, 2), prior_score=round(100 * m0, 2), post_mean=post, weight=round(weight_of(post, rated), 4),
                          n_needed=max(0, C.MIN_N - st["n"]), q_value=None, beats_baseline=False, rank=None,
                          last_view_at=last_view_at.get(eid), symbols_n=symbols_n.get(eid, 0))
                cards[(eid, sc, hz)] = st
                if rated and st["p_value"] is not None:
                    tests.append((eid, sc, hz))
    qs = bh_qvalues([cards[t]["p_value"] for t in tests])
    for t, q in zip(tests, qs):
        c = cards[t]
        c["q_value"] = q
        c["beats_baseline"] = bool(q < C.FDR_Q and c["ci_low"] is not None and c["ci_low"] > 0.5 and c["ret_ci_low"] is not None and c["ret_ci_low"] > 0)
    beating = sum(1 for t in tests if cards[t]["beats_baseline"])
    summary = {"tests": len(tests), "beating_baseline": beating, "fdr_q": C.FDR_Q,
               "expected_false_positives": round(C.FDR_Q * beating, 3), "uncorrected_expected_false_positives": round(0.05 * len(tests), 2)}
    return cards, summary


def assign_ranks(rows: list[dict]) -> list[dict]:
    """Chi xep hang khi status=rated: theo score giam dan. Insufficient: rank None."""
    rated = sorted((r for r in rows if r["status"] == "rated"), key=lambda r: (-r["score"], -r["n"], r["entity_id"]))
    for i, r in enumerate(rated, 1):
        r["rank"] = i
    for r in rows:
        if r["status"] != "rated":
            r["rank"] = None
    return rows


# ---------- chi tiet 1 entity ----------
def downsample(seq: list, k: int) -> list:
    if len(seq) <= k:
        return seq
    idx = sorted({int(round(i * (len(seq) - 1) / (k - 1))) for i in range(k)})
    return [seq[i] for i in idx]


def equity_band(sample: list[Item], seed_key: str, points: int = 150) -> dict[str, Any]:
    n = len(sample)
    note = ("Tổng lợi suất log (%) nếu theo từng ý kiến (vào mở nến D1 kế tiếp, thoát theo kỳ hạn), CHƯA tính phí/spread/trượt giá. "
            "Dải xám = 5%-95% khi hướng bị hoán vị ngẫu nhiên (cùng tỉ lệ mua/bán).")
    if n == 0:
        return {"points": [], "note": note}
    s = sorted(sample, key=lambda x: (x["exit_ts"], x["view_id"]))
    d, r = arrays(s)
    cum = np.cumsum(d * r) * 100
    rng = np.random.default_rng(seed_of(seed_key, "band"))
    m = np.tile(d, (C.N_BAND, 1))
    rng.permuted(m, axis=1, out=m)
    sims = np.cumsum(m * r, axis=1) * 100
    p05, p50, p95 = np.quantile(sims, [0.05, 0.5, 0.95], axis=0)
    pts = [{"t": s[i]["exit_ts"].isoformat(), "cum_ret_pct": float(cum[i]), "rand_p05": float(p05[i]), "rand_p50": float(p50[i]), "rand_p95": float(p95[i])} for i in range(n)]
    return {"points": downsample(pts, points), "note": note}


def rolling(sample: list[Item], points: int = 60) -> list[dict]:
    s = sorted(sample, key=lambda x: (x["exit_ts"], x["view_id"]))
    out, hits = [], 0
    for i, it in enumerate(s, 1):
        hits += 1 if it["hit"] else 0
        lo, hi = wilson(hits, i)
        out.append({"t": it["exit_ts"].isoformat(), "n": i, "hit_rate": hits / i, "ci_low": lo, "ci_high": hi})
    return downsample(out, points)


def by_regime(sample: list[Item]) -> list[dict]:
    out = []
    for rg in C.REGIMES:
        sub = [it for it in sample if it.get("regime") == rg]
        if not sub:
            continue
        st = basic_stats(sub, "regime", full=False)
        out.append({"regime": rg, "n": st["n"], "hit_rate": st["hit_rate"], "ci_low": st["ci_low"], "ci_high": st["ci_high"], "mean_ret_pct": st["mean_ret_pct"]})
    return out
