"""Test xếp hạng option học được: ưu tiên hàng thiếu, chi phí, bandit học từ bấm, giải thích, mô phỏng cải thiện tỉ lệ chấp nhận."""
import random

from ai_trading.classroom import option_rank as R
from ai_trading.classroom.store import ClassStore

from .test_class_api import E1, env  # noqa: F401


def mk(tmp_path):
    return ClassStore(str(tmp_path / "c"))


OPTS = [
    {"id": "q_sl", "kind": "question", "label": "SL đặt ở đâu", "row_key": "sl"},
    {"id": "q_ctx", "kind": "question", "label": "Bối cảnh xu hướng", "row_key": "context"},
    {"id": "t1", "kind": "test", "label": "Chạy backtest", "heavy": True},
    {"id": "v1", "kind": "variant", "label": "Biến thể khung H4"},
]
CTX = {"rows": {"sl": "trống", "context": "cao"}, "confirmed": ["context"], "text": "SL"}


def test_info_cost_and_explain():
    r = R.rank(OPTS, CTX, None, mode="mean", top=None)
    assert r[0]["id"] == "q_sl"                      # hàng trống ưu tiên
    assert r[-1]["id"] == "t1" or r[-1]["parts"]["cost"] == 1.0 or r[-1]["id"] in ("t1", "q_ctx")
    assert next(x for x in r if x["id"] == "t1")["rank"] > next(x for x in r if x["id"] == "q_sl")["rank"]
    e = R.explain(r[0])
    assert any("trống" in w for w in e["why"]) and e["why_en"] and set(e["parts"]) == {"info", "ctx", "bandit", "cost"}
    assert len(R.rank(OPTS, CTX, None, top=2)) == 2
    assert len(R.rank(OPTS + [{"id": "q_sl"}, {"label": "x"}, "bad"], CTX, None, top=None)) == 4   # trùng/ hỏng bị bỏ


def test_feedback_store_and_bandit_learns(tmp_path):
    s = mk(tmp_path)
    for _ in range(8):
        R.record_feedback(s, "r", "u1", "v1", "variant", "clicked")
        R.record_feedback(s, "r", "u1", "q_ctx", "question", "not_this")
    st = R.load_stats(s, "u1")
    assert st["expert"]["variant"]["clicked"] == 8 and st["class"]["question"]["not_this"] == 8
    assert R.load_stats(s, "u2")["expert"] == {} and R.load_stats(s, "u2")["class"]["variant"]["clicked"] == 8
    a, b, _ = R.posterior("variant", st)
    a2, b2, _ = R.posterior("question", st)
    assert a / (a + b) > a2 / (a2 + b2)
    r = R.rank([OPTS[3], {"id": "q_x", "kind": "question", "label": "Hỏi gì đó"}], {}, st, mode="mean")
    assert r[0]["id"] == "v1"
    try:
        R.record_feedback(s, "r", "u", "o", "k", "bogus")
        assert False
    except ValueError:
        pass
    sm = R.summary(s, "u1")
    assert sm["total"] == 16


def test_simulated_acceptance_improves(tmp_path):
    """Chuyên gia mô phỏng: thích 'variant'(0.8) và 'compare'(0.5), ít khi bấm 'question'(0.15), 'scan'(0.05). Tỉ lệ bấm top-2 phải tăng so với đầu."""
    s = mk(tmp_path)
    truth = {"variant": 0.8, "compare": 0.5, "question": 0.15, "scan": 0.05}
    rng = random.Random(7)
    rates = []
    for rnd in range(6):
        clicks = shown = 0
        for t in range(60):
            opts = [{"id": f"{k}{t}", "kind": k, "label": k} for k in truth]
            top = R.rank(opts, {}, R.load_stats(s, "u"), top=2, mode="thompson", seed=rng.randrange(10**9))
            for o in top:
                ok = rng.random() < truth[o["kind"]]
                clicks += ok
                shown += 1
                R.record_feedback(s, "r", "u", o["id"], o["kind"], "clicked" if ok else "ignored")
        rates.append(clicks / shown)
    base = sum(truth.values()) / len(truth) * 1.0      # xếp ngẫu nhiên chọn trúng ~0,375 (top-2 trên 4 loại)
    assert rates[-1] > rates[0] and sum(rates[-2:]) / 2 > base + 0.25, (rates, base)


def test_stats_route(env):
    c, app, _ = env
    R.record_feedback(app.state.class_store, "r", "exp1", "o", "variant", "clicked")
    j = c.get("/class/options/stats", headers=E1).json()
    assert j["mine"]["total"] == 1 and j["class"]["kinds"][0]["kind"] == "variant"
    assert c.get("/class/options/stats").status_code == 403
