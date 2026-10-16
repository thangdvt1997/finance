import ast
import json
import re
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from .regs import REG
from ai_trading.app import create_app
from ai_trading.config import Settings

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RES = REPO / "docs" / "research" / "pattern_sell"
needs_pattern_data = pytest.mark.skipif(not (RES / "summary.json").exists(), reason="du lieu pattern_sell da luu tru (data/archive/scenarios_20261015c.tar.zst)")


async def fake_fetch(path):
    if path.startswith("/scan/trades/r"):
        return {"items": [{"pattern": "KB-2", "opened_at": "2026-10-01T00:00:00+00:00", "closed_at": f"2026-10-0{i + 2}T00:00:00+00:00", "result_r": r}
                          for i, r in enumerate((1.0, 0.5, 0.0))] + [{"pattern": "KB-1", "opened_at": "2026-10-02T00:00:00+00:00", "closed_at": "2026-10-05T00:00:00+00:00", "result_r": -0.5}]}
    if path.startswith("/paper/overview"):
        return {"items": []}
    return {"items": [{"pattern": "KB-2", "opened_at": "2026-10-01T00:00:00+00:00", "replay": False, "id": 1, "result_r": 1.0}]}


@pytest.fixture()
def c():
    app = create_app(Settings(registry_dir=REG, research_dir=str(RES)),
                     redis=fakeredis.aioredis.FakeRedis(decode_responses=True), fetch=fake_fetch)
    return TestClient(app)


def test_overview_contract(c):
    d = c.get("/ai/overview").json()
    assert set(d) >= {"strategies", "warnings", "arena", "updated_at"}
    ids = {s["id"] for s in d["strategies"]}
    assert {"KB-1", "KB-2", "KB-3", "KB-4", "meta-labeling", "regime", "llm-analyst", "consensus", "rl-sim", "risk-guardrail"} <= ids
    for s in d["strategies"]:
        assert set(s) == {"id", "name", "module", "status", "summary", "metrics", "verdict", "warning"}
        assert set(s["metrics"]) >= {"expectancy_r", "p_vs_random", "trades"}
    k2 = next(x for x in d["arena"] if x["id"] == "KB-2")
    assert k2["trades"] == 3 and k2["pnl_r"] == 1.5 and k2["since"] == "2026-10-01T00:00:00+00:00"
    assert k2["label"] == "chưa đủ mẫu" and k2["rank"] is None and d["arena_meta"]["ranked"] == 0
    assert any("-0,26" in w or "-0.262" in w or "-0,262" in w or "0.97" in w or "0,97" in w for w in d["warnings"]) or d["warnings"]


@needs_pattern_data
def test_real_numbers_and_no_edge(c):
    kb = c.get("/ai/strategies/KB-3").json()
    s = json.loads((RES / "summary.json").read_text())
    dv = next(r for r in s["by_kb"]["dev_val"] if r["label"] == "KB-3")
    te = next(r for r in s["by_kb"]["test"] if r["label"] == "KB-3")
    assert kb["verdict"] == "no_edge" and kb["backtest"]["expectancy_r"] == dv["exp_r"] < 0
    assert kb["backtest"]["splits"]["test"]["expectancy_r"] == te["exp_r"] < 0
    assert kb["backtest"]["aggregate_test"]["expectancy_r"] == -0.2625
    assert kb["backtest"]["p_vs_random"] == 0.9701
    assert kb["charts"] and kb["examples"] and kb["honesty_note"]
    assert all(u.startswith("/v1/ai-trading/media/") for u in kb["charts"])
    assert {e["result"] for e in kb["examples"]} <= {"win", "loss", "worst"}


@needs_pattern_data
def test_client_reduced(c):
    kb = c.get("/ai/strategies/KB-1?audience=client").json()
    assert "charts" not in kb and "examples" not in kb and kb["backtest"]["expectancy_r"] < 0


def test_placeholder_and_404(c):
    d = c.get("/ai/strategies/regime").json()
    assert d["backtest"] is None and d["forward_paper"] is None and d["verdict"] == "unproven"
    assert c.get("/ai/strategies/nope").status_code == 404
    assert c.get("/ai/strategies/..%2Fetc").status_code in (404, 422)


def test_lab(c):
    d = c.get("/ai/lab").json()
    assert len(d["backlog"]) >= 15 and d["experiments"]
    assert {b["status"] for b in d["backlog"]} <= {"idea", "planned", "running", "done", "dropped"}


@needs_pattern_data
def test_media_safe(c):
    name = c.get("/ai/strategies/KB-1").json()["charts"][0].rsplit("/", 1)[1]
    r = c.get(f"/ai/media/charts/{name}")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    for bad in ("../summary.json", "x.png", "..%2Fsummary.json", "summary.json"):
        assert c.get(f"/ai/media/charts/{bad}").status_code in (404, 422)
    assert c.get("/ai/media/ledger/x.png").status_code == 422


@needs_pattern_data
def test_ledger_csv(c):
    r = c.get("/ai/ledger.csv?strategy=KB-3")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert len(lines) - 1 == 320
    assert c.get("/ai/ledger.csv?strategy=regime").status_code == 404
    assert c.get("/ai/ledger.csv?strategy=KB-3&source=paper").status_code == 200
    assert c.get("/ai/ledger.csv?strategy=KB-3&source=../x").status_code == 422


def test_jobs_legacy_route(c):
    # giai đoạn B: job nền chỉ dành cho kịch bản người dùng nạp (xem test_scenarios.py); KB-1..4 có kết quả cố định
    assert c.post("/ai/jobs", json={"type": "backtest", "strategy_id": "KB-1"}).status_code == 404
    assert c.get("/ai/jobs/" + "0" * 32).status_code == 404
    assert c.get("/ai/jobs/zzz").status_code == 404
    assert c.post("/ai/jobs", json={"type": "rm -rf"}).status_code == 404
    assert c.post("/ai/jobs", json={"strategy_id": "nope"}).status_code == 404


def test_no_data_source_names_in_registry():
    bad = re.compile(r"binance|yahoo|metaquotes|twelve|mt5|metatrader|alphavantage|stooq", re.I)
    for f in (ROOT / "registry").glob("*.yaml"):
        assert not bad.search(f.read_text(encoding="utf-8")), f


def test_no_order_paths():
    banned = {"order_send", "OrderSend", "place_order", "create_order", "submit_order", "order_check"}
    for f in (ROOT / "src").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute):
                assert n.attr not in banned, f
            if isinstance(n, ast.Name):
                assert n.id not in banned, f
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
                assert not {m.split(".")[0] for m in mods} & {"MetaTrader5", "mt5", "ccxt", "ib_insync", "mt_bridge"}, f
    assert not re.search(r"order_send|OrderSend", "".join(f.read_text() for f in (ROOT / "registry").glob("*.yaml")))


def test_registry_sach_khong_the_kich_ban():
    """Sau dọn 2026-10-15: registry thật chỉ còn thẻ nền, không thẻ KB/R10/SC-DEMO; Lab không dựng thí nghiệm KB từ summary.json."""
    app = create_app(Settings(registry_dir=str(ROOT / "registry"), research_dir=str(RES)),
                     redis=fakeredis.aioredis.FakeRedis(decode_responses=True), fetch=fake_fetch)
    cl = TestClient(app)
    ids = {s["id"] for s in cl.get("/ai/overview").json()["strategies"]}
    assert ids == {"meta-labeling", "regime", "llm-analyst", "consensus", "rl-sim", "risk-guardrail"}
    assert not any(e["id"].startswith("pattern_sell:") for e in cl.get("/ai/lab").json()["experiments"])
