"""Arena (ham thuan) + Store kich ban: mau nho, traversal, trung id, thu muc do dang, trial_index."""
import tempfile

import pytest

from ai_trading import arena
from ai_trading.scenario_store import Store


def _tr(p, n):
    return [{"pattern": p, "closed_at": f"2026-01-{i % 28 + 1:02d}T0{i % 9}", "opened_at": "2026-01-01", "result_r": 1.0 if i % 3 else -1.0} for i in range(n)]


def test_arena_empty_and_threshold():
    e = arena.build([], {})
    assert e["items"] == [] and e["ranked"] == 0 and e["note"] == arena.NOTE_EMPTY
    d = {r["id"]: r for r in arena.build(_tr("a", 29) + _tr("b", 30), {"a": "A", "b": "B", "c": "C"})["items"]}
    assert d["a"]["label"] == "chưa đủ mẫu" and d["a"]["rank"] is None
    assert d["b"]["rank"] == 1 and d["b"]["label"] is None and d["b"]["ci95"]
    assert d["c"]["trades"] == 0 and d["c"]["expectancy_r"] is None
    assert arena.build(_tr("b", 40), {}) == arena.build(_tr("b", 40), {})
    assert arena.max_drawdown([1, -2, -1, 3]) == 3.0 and arena.sign_flip_p([1, 1, 1]) == 0.125


def test_store_basic_dup_traversal_trial():
    s = Store(tempfile.mkdtemp())
    s.create({"id": "QA_one", "family": "F", "name": "x"}, {"a.png": b"x"}, "qa")
    assert s.scenario("QA_one")["name"] == "x" and s.meta("QA_one")["trial_index"] == 1
    with pytest.raises(FileExistsError):
        s.create({"id": "QA_one", "family": "F", "name": "y"}, {}, "qa")
    assert s.scenario("QA_one")["name"] == "x"
    for bad in ("../etc", "..", "a/b", "", "ab", "a" * 40, None):
        assert s.path(bad) is None and s.scenario(bad) is None
    assert s.image("QA_one", "../scenario.yaml") is None and s.image("QA_one", "a.png")
    assert s.job("../x") is None
    j = s.enqueue("QA_one", "backtest", "qa")
    assert s.job(j["id"])["status"] == "queued"


def test_store_bad_image_name_leaves_no_dir():
    s = Store(tempfile.mkdtemp())
    with pytest.raises(ValueError):
        s.create({"id": "QA_two", "family": "F"}, {"../x.png": b"x"}, "qa")
    assert s.ids() == []
