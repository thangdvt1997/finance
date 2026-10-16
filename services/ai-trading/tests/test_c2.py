"""C2: regime (hiện vật thật), đồng thuận (track-record giả), ngữ cảnh analyst; không tên nguồn; client rút gọn."""
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
REGIME = REPO / "docs" / "research" / "regime"

CONS = {"as_of": "2026-10-15T00:00:00+00:00", "window_days": 14, "rows": [
    {"symbol": "EURUSD", "n_experts": 16, "bullish": {"n": 9, "weight": 9.0}, "bearish": {"n": 7, "weight": 6.0}, "net_weighted": 0.2, "agreement": 0.56, "level": "weak",
     "latest_at": "2026-10-14T19:00:00+00:00", "top": [{"label": "Vị thế đầu cơ — EUR", "direction": "bullish", "status": "rated", "weight": 1.2},
                                                          {"label": "Reuters tổng hợp", "direction": "bearish", "status": "insufficient", "weight": 1.0}]}]}
LB = {"summary": {"entities": 122, "rated": 10, "insufficient": 112, "beating_baseline": 0},
      "rows": [{"label": "Vị thế đầu cơ — XAU", "kind": "positioning", "n": 157, "hit_rate": 0.58, "q_value": 1.0, "beats_baseline": False, "status": "rated"},
               {"label": "Bloomberg desk", "kind": "media", "n": 40, "hit_rate": 0.5, "q_value": 1.0, "beats_baseline": False, "status": "rated"}]}


async def fake_fetch(path):
    if path.startswith("/scan/setups"):
        return {"items": [{"pattern": "KB-1", "name": "Hồi - giảm nhẹ", "tf": "M15", "side": "sell", "state": "forming", "bar_ts": "2026-10-15T04:30:00+00:00",
                           "steps": [{"id": 1, "ok": True, "label": "(1) Sóng giảm dẫn hướng mạnh", "detail": "sóng dẫn 15.3 ATR"},
                                     {"id": 4, "ok": False, "label": "(4) Hồi vượt đỉnh (2)", "detail": "chưa vượt"}]}]}
    return {"by_pattern": [], "items": []}


def tr_get(path):
    return LB if path.startswith("/track/leaderboard") else CONS


@pytest.fixture()
def c():
    app = create_app(Settings(registry_dir=REG, research_dir=str(RES), regime_dir=str(REGIME)),
                     redis=fakeredis.aioredis.FakeRedis(decode_responses=True), fetch=fake_fetch)
    app.state.c2._get = tr_get
    return TestClient(app)


def test_regime_real_artifact_master_vs_client(c):
    m = c.get("/ai/regime?audience=master").json()
    assert m["available"] and len(m["symbols"]) >= 8
    syms = {s["symbol"] for s in m["symbols"]}
    assert {"EURUSD", "XAUUSD", "US500"} <= syms
    assert "eval" in m["symbols"][0] and "direction_cells_abs_t_gt_2" in m["verdict"] and "HƯỚNG" in m["verdict"]["summary"]
    cl = c.get("/ai/regime?audience=client").json()
    assert "eval" not in cl["symbols"][0] and "states_fit" not in cl["symbols"][0] and "direction_cells" not in cl["verdict"]
    assert "KHÔNG phải dự báo hướng" in cl["note"]
    one = c.get("/ai/regime?symbol=eurusd&audience=client").json()
    assert one["symbol"] == "EURUSD" and one["current"]["label"] and abs(sum(one["current"]["prob"]) - 1) < 0.01
    assert c.get("/ai/regime?symbol=ZZZ").status_code == 404
    assert c.get("/ai/regime?symbol=../x").status_code == 422


def test_regime_honest_numbers_match_artifact(c):
    d = json.loads((REGIME / "summary.json").read_text())
    assert d["verdict"]["direction_cells_abs_t_gt_2"] == 0 and "test" in d["locks"]
    # mọi số trong tập đánh giá nằm trong khoảng hợp lệ
    for s in d["symbols"]:
        for e in s["eval"].values():
            assert 0 <= e["hmm"]["vol_p_vs_shifted"] <= 1 and e["hmm"]["mean_dwell_days"] >= 1


def test_consensus_reduced_and_source_names_filtered(c):
    m = c.get("/ai/consensus?symbol=EURUSD&audience=master").json()
    assert m["symbol"]["level"] == "weak" and m["symbol"]["confidence"] == "vừa" and len(m["symbol"]["feature_vector"]) == 4
    assert m["reliability"]["tier"] == "chưa chứng minh" and m["reliability"]["rated"] == 10
    assert [t["label"] for t in m["symbol"]["top"]] == ["Vị thế đầu cơ — EUR"]            # nhãn có tên nguồn bị loại
    allrows = c.get("/ai/consensus?audience=master").json()
    assert [x["label"] for x in allrows["rated_experts"]] == ["Vị thế đầu cơ — XAU"]
    cl = c.get("/ai/consensus?symbol=EURUSD&audience=client").json()
    assert "top" not in cl["symbol"] and "rated_experts" not in cl
    assert c.get("/ai/consensus?symbol=NOPE").json()["symbol"] is None


def test_consensus_503_when_track_down(c):
    c.app.state.c2._get = lambda p: None
    c.app.state.c2._cache.clear()
    assert c.get("/ai/consensus").status_code == 503


def test_analyst_context_and_no_source_names(c):
    d = c.get("/ai/analyst-context?symbol=EURUSD").json()
    assert d["symbol"] == "EURUSD" and d["regime"]["current"]["label"] and d["consensus"]["n_experts"] == 16
    assert d["scenarios"][0]["steps"][0]["ok"] is True
    assert "top" not in d["consensus"]
    blob = json.dumps(c.get("/ai/regime?audience=master").json()) + json.dumps(c.get("/ai/consensus?audience=master").json()) + json.dumps(d)
    assert not re.search(r"binance|yahoo|metaquotes|twelve|mt5|metatrader|reuters|bloomberg", blob, re.I)
