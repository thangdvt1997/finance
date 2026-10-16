from data_keeper import main
from data_keeper.guard import p95_from


def test_load_modules_lenient():
    m = main.load_modules(["inventory", "khong_ton_tai"])
    assert "inventory" in m and "khong_ton_tai" not in m


def test_p95():
    prev = {0.1: 0, 0.25: 0, 0.5: 0, float("inf"): 0}
    cur = {0.1: 50, 0.25: 95, 0.5: 100, float("inf"): 100}
    assert 0.1 < p95_from(prev, cur) <= 0.25
    assert p95_from(prev, {0.1: 1, float("inf"): 1}) is None
