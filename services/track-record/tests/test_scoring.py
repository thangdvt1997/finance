from __future__ import annotations

from datetime import timedelta

from conftest import T0, make_items
from track_record import config as C
from track_record import scoring


def run_family(specs: list[tuple[str, int, float, str]], seed0: int):
    ents, items = {}, {}
    for i, (eid, n, p, kind) in enumerate(specs):
        ents[eid] = {"entity_id": eid, "kind": kind, "lang": "en", "label": eid}
        items[eid] = {"1W": make_items(eid, n, p, seed0 * 1000 + i)}
    counts = {}
    for e, v in items.items():
        for sc in ("all", "forex", "sym:EURUSD"):
            counts[(e, sc)] = len(v["1W"])
    return scoring.compute_cards(items, ents, counts, {}, {})


def test_random_experts_not_beating_baseline_after_fdr():
    tot_tests = tot_beat = 0
    for seed in (1, 2, 3):
        cards, summ = run_family([(f"r{seed}-{i}", 80, 0.5, "analyst") for i in range(25)], seed)
        tot_tests += summ["tests"]
        tot_beat += summ["beating_baseline"]
    assert tot_tests >= 150
    assert tot_beat / tot_tests <= 0.10          # FDR: ti le duong tinh gia khong vuot q
    assert tot_beat <= 3


def test_skilled_expert_is_rated_and_beats_baseline():
    specs = [("skill", 200, 0.62, "analyst")] + [(f"r{i}", 200, 0.5, "analyst") for i in range(15)]
    cards, summ = run_family(specs, 7)
    c = cards[("skill", "all", "1W")]
    assert c["status"] == "rated" and c["n"] == 200
    assert c["beats_baseline"] and c["q_value"] < C.FDR_Q and c["ci_low"] > 0.5 and c["ret_ci_low"] > 0
    rows = scoring.assign_ranks([cards[(e, "all", "1W")] for e in {s[0] for s in specs}])
    assert [r for r in rows if r["rank"] == 1][0]["entity_id"] == "skill"
    assert c["weight"] > 1.3


def test_insufficient_below_min_n():
    cards, _ = run_family([("few", 29, 0.9, "analyst"), ("ok", 30, 0.5, "analyst")], 3)
    c = cards[("few", "all", "1W")]
    assert c["status"] == "insufficient" and c["weight"] == 1.0 and c["p_value"] is None and c["beats_baseline"] is False and c["n_needed"] == 1
    assert cards[("ok", "all", "1W")]["status"] == "rated"
    rows = scoring.assign_ranks([c, cards[("ok", "all", "1W")]])
    assert rows[0]["rank"] is None and rows[1]["rank"] == 1


def test_shrinkage_toward_half_and_tilt_bounded():
    post, m0 = scoring.shrink(3, 3, "analyst")
    assert 0.5 < post < 0.6 and m0 == 0.5            # 3/3 dung van chi ~0,57
    for k in C.PRIORS:
        assert abs(scoring.prior_of(k)[1]) <= 0.02
    assert scoring.weight_of(0.9, True) == 2.0 and scoring.weight_of(0.1, True) == 0.25 and scoring.weight_of(0.9, False) == 1.0


def test_independent_thinning_and_wilson():
    its = []
    for i in range(10):
        e = T0 + timedelta(days=i)
        its.append({"view_id": str(i), "entity_id": "x", "symbol": "A", "entry_ts": e, "exit_ts": e + timedelta(days=5)})
    assert len(scoring.independent(its)) == 2        # cac quan diem chong lan -> chi 2 cai doc lap
    lo, hi = scoring.wilson(60, 100)
    assert 0.50 < lo < 0.60 < hi < 0.70
    assert scoring.wilson(0, 0) == (None, None)


def test_bh_monotone_and_bounded():
    q = scoring.bh_qvalues([0.001, 0.04, 0.5, 0.9])
    assert q[0] <= q[1] <= q[2] <= q[3] <= 1.0 and abs(q[0] - 0.004) < 1e-9


def test_deterministic_with_fixed_seed():
    a, _ = run_family([("e", 60, 0.55, "analyst")], 5)
    b, _ = run_family([("e", 60, 0.55, "analyst")], 5)
    assert a[("e", "all", "1W")]["p_value"] == b[("e", "all", "1W")]["p_value"]
    assert a[("e", "all", "1W")]["ret_ci_low"] == b[("e", "all", "1W")]["ret_ci_low"]


def test_equity_band_structure():
    s = make_items("e", 120, 0.5, 11)
    eq = scoring.equity_band(s, "k")
    assert eq["points"] and set(eq["points"][0]) == {"t", "cum_ret_pct", "rand_p05", "rand_p50", "rand_p95"}
    p = eq["points"][-1]
    assert p["rand_p05"] <= p["rand_p50"] <= p["rand_p95"]
    r = scoring.rolling(s)
    assert r[-1]["n"] == 120
