import base64
import json
import tempfile
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from .regs import REG
from ai_trading import scenario_schema as sch
from ai_trading.app import create_app
from ai_trading.config import Settings

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT.parents[1] / "docs" / "research" / "pattern_sell"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
DEMO = (ROOT / "tests" / "fixtures" / "examples" / "SC-DEMO-1.yaml").read_text(encoding="utf-8")


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


@pytest.fixture()
def env():
    with tempfile.TemporaryDirectory() as td:
        app = create_app(Settings(registry_dir=REG, research_dir=str(RES), state_dir=td),
                         redis=fakeredis.aioredis.FakeRedis(decode_responses=True))
        yield TestClient(app), Path(td)


def post(c, y=DEMO, images=None):
    return c.post("/ai/scenarios", json={"yaml": y, "images": images or {}})


def test_demo_yaml_valid():
    sc = sch.validate(DEMO)
    assert sc["side"] == "sell" and len(sch.grid_of(sc)) == 4


def test_create_list_detail(env):
    c, td = env
    r = post(c)
    assert r.status_code == 201 and r.json()["id"] == "SC-DEMO-1"
    cards = c.get("/ai/strategies").json()
    me = next(s for s in cards if s["id"] == "SC-DEMO-1")
    assert me["origin"] == "user" and me["phase"] == "created" and me["verdict"] == "unproven" and me["status"] == "research"
    d = c.get("/ai/strategies/SC-DEMO-1").json()
    assert d["scenario"]["phase"] == "created" and d["scenario"]["rules"] and d["backtest"] is None
    assert "không có bằng chứng" in d["honesty_note"].lower() or "thử nghiệm" in d["honesty_note"]
    # client: không thấy kịch bản người dùng nạp
    assert all(s["id"] != "SC-DEMO-1" for s in c.get("/ai/strategies?audience=client").json())
    assert c.get("/ai/strategies/SC-DEMO-1?audience=client").status_code == 404
    assert all(s["id"] != "SC-DEMO-1" for s in c.get("/ai/overview?audience=client").json()["strategies"])


def test_duplicate_and_registry_collision(env):
    c, _ = env
    assert post(c).status_code == 201
    assert post(c).status_code == 422                       # id đã tồn tại
    assert post(c, DEMO.replace("SC-DEMO-1", "KB-1")).status_code in (409, 422)
    assert post(c, DEMO.replace("SC-DEMO-1", "kb-2")).status_code in (409, 422)


@pytest.mark.parametrize("bad", [
    "id: &a SC-X1\nname: x\n",                              # anchor
    "a: &a [1,2]\nb: *a\n",                                 # alias
    "- 1\n- 2\n",                                           # không phải map
    "x" * 20000,                                            # quá lớn
    "id: SC-X1\nname: abc\nside: buy\n",                    # buy chưa hỗ trợ
    "!!python/object/apply:os.system ['id']",               # tag nguy hiểm
])
def test_bad_yaml(env, bad):
    c, _ = env
    assert post(c, bad).status_code == 422


def test_rule_bounds(env):
    c, _ = env
    for old, new in (("min: 2.0", "min: 9999"), ("bars: 6, min", "bars: 0, min"), ("rule: bear_body", "rule: os_system"),
                     ("tp_r: [1.0, 2.0]", "tp_r: [0.1]"), ("symbols: [EURUSD, GBPUSD]", "symbols: [\"../etc\"]"),
                     ("tfs: [H1]", "tfs: [M1]")):
        assert old in DEMO
        assert post(c, DEMO.replace(old, new)).status_code == 422, new


def test_images(env):
    c, td = env
    y = DEMO + "images: [mau1.png]\n"
    assert post(c, y, {"mau1.png": b64(PNG)}).status_code == 201
    assert (td / "scenarios" / "SC-DEMO-1" / "images" / "mau1.png").is_file()
    r = c.get("/ai/scenarios/SC-DEMO-1/images/mau1.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/ai/scenarios/SC-DEMO-1/images/khac.png").status_code == 404
    assert "images" in c.get("/ai/strategies/SC-DEMO-1").json()["scenario"] and c.get("/ai/strategies/SC-DEMO-1").json()["scenario"]["images"][0]["url"].startswith("/v1/ai-trading/scenarios/")


@pytest.mark.parametrize("name,data,ok", [
    ("../x.png", PNG, False), ("a/b.png", PNG, False), ("x.svg", PNG, False), ("x.png", b"<svg onload=alert(1)>", False),
    ("x.png", b"\xff\xd8\xff" + b"0" * 10, False),            # JPEG nội dung nhưng đuôi png
    ("x.png", PNG + b"0" * (700 * 1024), False),              # quá lớn
    ("x.png", b"not base64!!", False),
])
def test_bad_images(env, name, data, ok):
    c, _ = env
    raw = data if isinstance(data, str) else b64(data) if name != "x.png" or data != b"not base64!!" else "###"
    y = DEMO + f"images: [\"{name}\"]\n" if "/" not in name and ".." not in name else DEMO
    r = c.post("/ai/scenarios", json={"yaml": y, "images": {name: raw}})
    assert r.status_code == 422


def test_too_many_images(env):
    c, _ = env
    names = [f"i{n}.png" for n in range(6)]
    r = c.post("/ai/scenarios", json={"yaml": DEMO + f"images: {json.dumps(names)}\n", "images": {n: b64(PNG) for n in names}})
    assert r.status_code == 422


def test_images_must_match_yaml(env):
    c, _ = env
    assert post(c, DEMO, {"a.png": b64(PNG)}).status_code == 422
    assert post(c, DEMO + "images: [a.png]\n", {}).status_code == 422


def test_jobs_rules(env):
    c, td = env
    assert c.post("/ai/scenarios/SC-NOPE/jobs", json={"type": "backtest"}).status_code == 404
    post(c)
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "meta_label"}).status_code == 422
    r = c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "detector_test"})
    assert r.status_code == 202 and r.json()["status"] == "queued"
    jid = r.json()["id"]
    assert c.get(f"/ai/jobs/{jid}").json()["status"] == "queued"
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "backtest"}).status_code == 409    # 1 job/kịch bản
    assert c.get("/ai/jobs/../../etc").status_code in (404, 405)
    assert c.get("/ai/jobs/" + "0" * 32).status_code == 404
    assert len(c.get("/ai/scenarios/SC-DEMO-1/jobs").json()["items"]) == 1


def test_queue_limit(env):
    c, _ = env
    for i in range(4):
        post(c, DEMO.replace("SC-DEMO-1", f"SC-Q{i}"))
    codes = [c.post(f"/ai/scenarios/SC-Q{i}/jobs", json={"type": "backtest"}).status_code for i in range(4)]
    assert codes == [202, 202, 202, 429]


def test_final_test_gating(env):
    c, td = env
    post(c)
    # chưa có dev -> 409
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test", "confirm": "SC-DEMO-1"}).status_code == 409
    sd = td / "scenarios" / "SC-DEMO-1"
    (sd / "result.json").write_text(json.dumps({"dev": {"status": "done", "final_params": {"tp_r": 1.0, "sl_param": 0.25}, "oos": {"pooled": {"n": 40, "exp_r": -0.1}}}}))
    # thiếu/ sai xác nhận
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test"}).status_code == 422
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test", "confirm": "yes"}).status_code == 422
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test", "confirm": True}).status_code == 422
    ok = c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test", "confirm": "SC-DEMO-1"})
    assert ok.status_code == 202
    # sau khi test đã mở: không mở lại, không chạy lại backtest dev
    (sd / "test_opened.json").write_text("{}")
    for j in (td / "jobs").glob("*.json"):
        d = json.loads(j.read_text()); d["status"] = "done"; j.write_text(json.dumps(d))
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "final_test", "confirm": "SC-DEMO-1"}).status_code == 409
    assert c.post("/ai/scenarios/SC-DEMO-1/jobs", json={"type": "backtest"}).status_code == 409


def test_card_from_result(env):
    c, td = env
    post(c)
    res = {"dev": {"status": "done", "oos": {"pooled": {"n": 80, "exp_r": -0.12, "ci95": [-0.3, 0.05], "maxdd_r": 9}, "p_vs_random": 0.7},
                   "dsr": {"dsr": 0.01}, "pbo": {"pbo": 0.6}}, "verdict": "no_edge"}
    (td / "scenarios" / "SC-DEMO-1" / "result.json").write_text(json.dumps(res))
    d = c.get("/ai/strategies/SC-DEMO-1").json()
    assert d["phase"] == "dev_done" and d["verdict"] == "no_edge" and d["backtest"]["expectancy_r"] == -0.12
    assert d["backtest"]["splits"]["test"] is None and "chưa đủ" in d["warning"].lower() or "không có edge" in d["warning"].lower()
    (td / "scenarios" / "SC-DEMO-1" / "ledger_dev.csv").write_text("a,b\n1,2\n")
    assert c.get("/ai/ledger.csv?strategy=SC-DEMO-1&source=backtest_dev").status_code == 200
    assert c.get("/ai/ledger.csv?strategy=SC-DEMO-1&source=backtest_test").status_code == 404
    assert c.get("/ai/ledger.csv?strategy=SC-DEMO-1&source=paper").status_code == 404


def test_no_order_paths_in_new_code():
    import re
    for f in ("scenario_schema.py", "scenario_store.py", "app.py"):
        t = (ROOT / "src" / "ai_trading" / f).read_text(encoding="utf-8")
        assert not re.search(r"order_send|OrderSend|ccxt|create_order|MetaTrader5", t)
