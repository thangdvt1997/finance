"""D1: arena (thống kê trung thực, trạng thái rỗng), guardrail/kill-switch, xác minh hash-chain có neo; không đường đặt lệnh."""
import json
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from .regs import REG
from ai_trading import arena
from ai_trading.app import create_app
from ai_trading.config import Settings

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT.parents[1] / "docs" / "research" / "pattern_sell"
H = "a" * 64


def mk(fetch, redis=None):
    return TestClient(create_app(Settings(registry_dir=REG, research_dir=str(RES)),
                                 redis=redis or fakeredis.aioredis.FakeRedis(decode_responses=True), fetch=fetch))


async def empty_fetch(path):
    if path.startswith("/scan/trades/r"):
        return {"items": []}
    if path.startswith("/paper/overview"):
        return {"items": []}
    return None


def test_arena_empty_state_explains():
    c = mk(empty_fetch)
    a = c.get("/ai/arena").json()
    assert a["total_trades"] == 0 and a["ranked"] == 0 and "Chưa có lệnh paper" in a["note"]
    ids = {r["id"] for r in a["items"]}
    assert {"KB-1", "KB-2", "KB-3", "KB-4"} <= ids
    assert all(r["trades"] == 0 and r["label"] == "chưa đủ mẫu" and r["rank"] is None and r["expectancy_r"] is None for r in a["items"])
    assert c.get("/ai/overview").json()["arena_meta"]["total_trades"] == 0


def test_arena_unavailable_flag():
    async def none(path):
        return None
    a = mk(none).get("/ai/arena").json()
    assert a["available"] is False and a["items"]


def test_row_stats_and_rank_threshold():
    rs = [1.0, -1.0, 2.0, -0.5] * 10                        # n=40 >= 30
    st = arena.row_stats(rs)
    assert st["trades"] == 40 and st["expectancy_r"] == pytest.approx(0.375) and st["ci95"][0] < 0.375 < st["ci95"][1]
    assert st["max_dd_r"] == 1.0 and 0 < st["p_vs_random"] < 0.5
    closed = [{"pattern": "KB-1", "closed_at": f"2026-10-01T{i % 24:02d}:00:00", "opened_at": "2026-09-30", "result_r": r} for i, r in enumerate(rs)]
    closed += [{"pattern": "KB-2", "closed_at": "2026-10-02", "opened_at": "2026-10-01", "result_r": 5.0}] * 3
    out = arena.build(closed, {"KB-1": "a", "KB-2": "b", "KB-3": "c"})
    by = {r["id"]: r for r in out["items"]}
    assert by["KB-1"]["rank"] == 1 and by["KB-1"]["enough_sample"] and by["KB-1"]["label"] is None
    assert by["KB-2"]["rank"] is None and by["KB-2"]["label"] == "chưa đủ mẫu" and by["KB-3"]["trades"] == 0   # KB-2 lãi to nhưng mẫu nhỏ -> không xếp hạng


def test_sign_flip_p_exact_small():
    assert arena.sign_flip_p([1.0]) is None
    assert arena.sign_flip_p([1.0, 1.0, 1.0]) == 0.125          # 1/8 tổ hợp dấu cho tổng >= 3
    assert arena.sign_flip_p([-1.0, -1.0, -1.0]) == 1.0


GUARD = {"enabled": True, "kill_switch": {"on": False}, "daily_loss_r": 0.0, "counts": {}, "recent_blocks": [], "degraded": [], "limits": {}, "sizing_table": []}


async def guard_fetch(path):
    if path.startswith("/scan/guardrail"):
        return dict(GUARD)
    if path.startswith("/scan/ledger/verify"):
        return {"ok": True, "n": 3, "head": H}
    return await empty_fetch(path)


def test_guardrail_state_and_killswitch_roundtrip():
    c = mk(guard_fetch)
    g = c.get("/ai/guardrail").json()
    assert g["available"] and g["kill_switch"]["on"] is False and g["ledger"]["ok"] is True
    r = c.post("/ai/guardrail/killswitch", json={"on": True, "reason": "thử"}).json()
    assert r["kill_switch"]["on"] and r["kill_switch"]["by"] == "master"
    assert c.get("/ai/guardrail").json()["kill_switch"]["on"] is True
    assert c.post("/ai/guardrail/killswitch", json={"on": False}).json()["kill_switch"]["on"] is False


@pytest.mark.parametrize("body", [{}, {"on": "yes"}, {"on": True, "x": 1}, {"on": 1}])
def test_killswitch_rejects_bad_body(body):
    assert mk(guard_fetch).post("/ai/guardrail/killswitch", json=body).status_code == 422


def test_killswitch_rejects_source_names():
    assert mk(guard_fetch).post("/ai/guardrail/killswitch", json={"on": True, "reason": "do Binance lỗi"}).status_code == 422


def test_ledger_anchor_detects_truncation():
    state = {"n": 5, "ok": True}
    seen = []

    async def f(path):
        if path.startswith("/scan/ledger/verify"):
            seen.append(path)
            if "anchor_n=5" in path and state["n"] < 5:
                return {"ok": False, "n": state["n"], "head": H, "reason": "cắt đuôi"}
            return {"ok": True, "n": state["n"], "head": H if state["n"] == 5 else "b" * 64}
        return await empty_fetch(path)
    c = mk(f)
    assert c.get("/ai/ledger/verify").json()["ok"] is True
    state["n"] = 3                                             # đuôi bị cắt: chuỗi ngắn vẫn tự nhất quán
    v = c.get("/ai/ledger/verify").json()
    assert "anchor_n=5" in seen[-1] and v["ok"] is False
    v = c.get("/ai/ledger/verify").json()
    assert v["ok"] is False                                    # neo KHÔNG bị hạ xuống sau khi vỡ


def test_ledger_verify_unavailable():
    async def none(path):
        return None
    assert mk(none).get("/ai/ledger/verify").json() == {"available": False, "ok": None, "reason": "Chưa đọc được sổ lệnh paper."}


def test_kill_key_pair_matches_pattern_scan():
    from ai_trading.d1 import KILL_KEY
    src = (ROOT.parents[0] / "pattern-scan" / "src" / "pattern_scan" / "guardrail.py")
    if src.exists():                                           # trong image ai-trading không có mã pattern-scan
        assert f'KILL_KEY = "{KILL_KEY}"' in src.read_text(encoding="utf-8")
