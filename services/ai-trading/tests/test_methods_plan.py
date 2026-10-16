"""Test Kế hoạch áp dụng phương pháp (L3): tiêu chí tất định, trung thực, quyền, IDOR, xuất tài liệu, hook bộ nhớ."""
import json

from .test_class_api import E1, E2, M, env, mkroom  # noqa: F401
from .test_methods import add, mk, put
from ai_trading.classroom import persist
from ai_trading.classroom.methods_plan import THRESHOLDS, compute_plan

TXT = {
    "context": "Thị trường đi ngang sau nhịp giảm, xu hướng lớn H4 giảm hoặc trung tính, tránh phiên tin lớn",
    "symbol_tf": "EURUSD khung H1, lọc bằng H4",
    "formation": "Vùng đi ngang tối thiểu 20 nến, biên độ dưới 1,5 ATR, 3 đỉnh giảm dần cách nhau 4-10 nến, nến nén thân dưới 30% biên độ",
    "trigger": "Nến đóng cửa dưới đáy nến nén ít nhất 0,2 ATR, vào ở mở nến kế tiếp",
    "invalidation": "Giá đóng cửa trên đỉnh thứ nhất của chuỗi trong vòng 3 nến thì huỷ",
    "sl": "SL trên đỉnh 6 nến + 0,25 ATR, TP 2R, giữ tối đa 24 nến",
    "sizing": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh, tối đa 1 lệnh mở",
    "filters": "Chỉ phiên London và New York 07:00-20:00 UTC, spread dưới 1,5 pip",
    "examples": "Ví dụ đúng: 3 đỉnh giảm đều rồi nến nén nhỏ. Ví dụ sai gần giống: đỉnh thứ 3 cao hơn đỉnh thứ 2 thì không vào",
    "failure": "Thất bại khi có tin mạnh hoặc thanh khoản thấp ở phiên Á",
    "symmetry": "Bản Buy: 3 đáy tăng dần rồi nến nén, vào khi phá đỉnh nến nén",
    "rationale": "Bên mua yếu dần, bên bán bán ra sớm hơn ở mỗi nhịp hồi",
}
MROWS = {
    "context": "Dùng khi thị trường đi ngang sau nhịp giảm, không dùng khi có tin lớn hoặc xu hướng mạnh",
    "priority": "Kịch bản lõi luôn được ưu tiên hơn kịch bản phụ; hai tín hiệu ngược chiều thì bỏ cả hai",
    "risk_per_trade": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh", "hot_risk": "Tổng rủi ro nóng tối đa 2% và tối đa 3 lệnh mở",
    "loss_limits": "Lỗ ngày tối đa 1,5% và lỗ tuần tối đa 4% thì dừng đến hết kỳ",
    "correlation": "Không mở 2 lệnh cùng chiều trên các cặp có tương quan trên 0,8",
    "stop_rules": "Dừng 30 phút quanh tin mạnh, spread trên 2 pip thì bỏ qua, không vào lệnh giờ rollover",
    "symbols_tf": "EURUSD khung H1 lọc bằng H4, chỉ một mã", "roles": "Kịch bản Sell là lõi duy nhất của phương pháp thử nghiệm này",
}
EDIT = ["context", "symbol_tf", "formation", "trigger", "invalidation", "sl", "sizing", "filters", "ex_ok", "failure", "symmetry", "rationale"]


def teach(c, rid, h=E1):
    for k in EDIT:
        src = {"ex_ok": "examples"}.get(k, k)
        r = c.post(f"/class/rooms/{rid}/canvas/{k}/edit", json={"text": TXT[src]}, headers=h)
        assert r.status_code == 200, (k, r.text)
    c.post(f"/class/rooms/{rid}/canvas/tp/edit", json={"text": TXT["sl"]}, headers=h)


def finish_clarity(c, app, rid, h=E1):
    """Điền thêm giả định/câu hỏi mở (không sửa trực tiếp được) rồi xác nhận mọi hàng có chữ."""
    st = app.state.class_store
    m = persist.load(st.get_state(rid), rid, None)
    m.profile.assumptions = [{"text": "Dữ liệu nến đủ sạch", "status": "open"}]
    m.profile.open_questions = ["Có áp dụng cho khung M15 không"]
    st.put_state(rid, persist.dump(m))
    for r in c.get(f"/class/rooms/{rid}/canvas", headers=h).json()["rows"]:
        if r["text"]:
            c.post(f"/class/rooms/{rid}/canvas/{r['key']}/confirm", json={}, headers=h)
    return c.get(f"/class/rooms/{rid}/canvas", headers=h).json()["clarity"]["score"]


def fabricate(app, tmp, rid, sid, *, dev=None, det=None, test=None, opened=False, labels=(12, 1.0)):
    st = app.state.class_store
    d = tmp / "state" / "scenarios" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "scenario.yaml").write_text(f"id: {sid}\nname: x\n")
    res = {}
    if det is not None:
        res["detector"] = det
    if dev is not None:
        res["dev"] = dev
    if test is not None:
        res["test"] = test
    res["verdict"] = (dev or {}).get("_verdict", "unproven")
    (d / "result.json").write_text(json.dumps(res))
    if opened:
        (d / "test_opened.json").write_text("{}")
    st.add_action(rid, "test", "done", {}, "exp1", scenario_id=sid)
    n, prec = labels
    for i in range(n):
        eid = st.add_example(rid, 1, None, {"symbol": "EURUSD", "tf": "H1", "ts": f"2024-01-{i + 1:02d}"})
        st.add_label(rid, eid, "dung" if i < round(n * prec) else "sai", "lý do", "exp1", 1)


def good_dev():
    return {"status": "done", "dsr": {"dsr": 0.97}, "costs": "spread + trượt + phí", "n_trials": 6, "pbo": {"pbo": 0.2},
            "oos": {"pooled": {"n": 240, "exp_r": 0.12, "ci95": [0.03, 0.21]}, "p_vs_random": 0.01,
                    "by_series": {"EURUSD|H1": {"n": 120, "exp_r": 0.1}, "GBPUSD|H1": {"n": 120, "exp_r": 0.14}},
                    "by_year": {"2021": {"n": 60, "exp_r": 0.1}, "2022": {"n": 60, "exp_r": 0.2}, "2023": {"n": 60, "exp_r": 0.05}, "2024": {"n": 60, "exp_r": 0.13}}},
            "_verdict": "unproven"}


GOOD_DET = {"status": "done", "golden_pass": 3, "golden_total": 3}


def fill_method(c, mid, h=E1):
    for k, t in MROWS.items():
        assert c.post(f"/class/methods/{mid}/canvas/{k}/edit", json={"text": t}, headers=h).status_code == 200
        assert c.post(f"/class/methods/{mid}/canvas/{k}/confirm", json={}, headers=h).status_code == 200


def plan(c, mid, h=E1):
    r = c.get(f"/class/methods/{mid}/plan", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def stat(p):
    return {s["n"]: s["status"] for s in p["steps"]}


def setup_good(env, *, dev=None, opened=True, test=None, verdict="edge"):
    c, app, tmp = env
    mid = mk(c)
    rid = c.post(f"/class/methods/{mid}/scenarios", json={"new": {"title": "Sell 3 đỉnh giảm dần"}}, headers=E1).json()["scenario"]["room_id"]
    teach(c, rid)
    sc = finish_clarity(c, app, rid)
    d = dev or good_dev()
    d["_verdict"] = verdict
    fabricate(app, tmp, rid, "scn_good", dev=d, det=GOOD_DET, test=test, opened=opened)
    fill_method(c, mid)
    return c, app, mid, rid, sc


def test_empty_plan_is_honest(env):
    c, *_ = env
    mid = mk(c)
    p = plan(c, mid)
    assert [s["n"] for s in p["steps"]] == list(range(1, 10)) and p["progress"] == {"passed": 0, "total": 9}
    assert p["verdict"]["code"] == "incomplete" and "CHƯA" in p["verdict"]["label_vi"] and p["verdict"]["paper_only"]
    assert all(s["status"] in ("pending", "failed", "blocked") for s in p["steps"])
    assert p["thresholds"]["clarity_min"] == 80
    assert c.get(f"/class/methods/{mid}/plan", headers=E2).status_code == 404       # IDOR
    assert c.get(f"/class/methods/{mid}/plan").status_code == 403
    assert c.post(f"/class/methods/{mid}/plan/recheck", headers=E2).status_code == 404
    assert c.get(f"/class/methods/{mid}/plan/export", headers=E2).status_code == 404


def test_full_pipeline_ready_only_after_all(env):
    c, app, mid, rid, sc = setup_good(env, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    assert sc >= THRESHOLDS["clarity_min"], sc
    # hồ sơ rủi ro: chưa có stress -> bước 6 pending
    p = plan(c, mid)
    s = stat(p)
    assert s[1] == s[2] == s[3] == s[4] == s[5] == "passed", p["steps"]
    assert s[6] == "pending" and p["verdict"]["code"] == "incomplete" and "CHƯA" in p["verdict"]["label_vi"]
    # chuyên gia không được ghi bằng chứng/ duyệt
    ev = {"kind": "stress", "data": {"passed": True, "scenarios": ["spread x3"]}}
    assert c.post(f"/class/methods/{mid}/plan/evidence", json=ev, headers=E1).status_code == 403
    assert c.post(f"/class/methods/{mid}/plan/approve", json={}, headers=E1).status_code == 403
    assert c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "stress", "data": {}}, headers=M).status_code == 422
    assert c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "paper", "data": {"trades": "x"}}, headers=M).status_code == 422
    assert c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "bad", "data": {}}, headers=M).status_code == 422
    assert c.post(f"/class/methods/{mid}/plan/evidence", json=ev, headers=M).status_code == 200
    p = plan(c, mid)
    assert stat(p)[6] == "passed", [x for x in p["steps"][5]["criteria"] if x["pass"] is not True]
    assert p["verdict"]["code"] == "eligible_review" and p["verdict"]["code"] != "ready"
    # duyệt khi chưa có paper -> 409
    assert c.post(f"/class/methods/{mid}/plan/approve", json={}, headers=M).status_code == 409
    # paper không đủ -> thất bại bước 7
    c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "paper", "data": {"trades": 10, "weeks": 3, "expectancy_r": 0.1, "hash_chain_ok": True}}, headers=M)
    assert stat(plan(c, mid))[7] == "failed"
    c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "paper", "data": {"trades": 45, "weeks": 13, "expectancy_r": 0.08, "hash_chain_ok": True}}, headers=M)
    p = plan(c, mid)
    assert stat(p)[7] == "passed" and p["verdict"]["code"] == "eligible_review"
    assert c.post(f"/class/methods/{mid}/plan/approve", json={"note": "ok"}, headers=M).status_code == 200
    p = plan(c, mid)
    assert stat(p)[8] == "passed" and stat(p)[9] == "pending" and p["verdict"]["code"] == "eligible_review"     # chưa xuất tài liệu: chưa 'ready'
    r = c.get(f"/class/methods/{mid}/plan/export?format=md", headers=E1)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown") and "attachment" in r.headers["content-disposition"]
    assert "Kế hoạch áp dụng phương pháp" in r.text and "Quyết định cần người dùng" in r.text
    p = plan(c, mid)
    assert p["progress"]["passed"] == 9 and p["verdict"]["code"] == "ready"
    # sửa phương pháp -> phê duyệt/ tài liệu hết hiệu lực
    c.patch(f"/class/methods/{mid}", json={"description": "đã đổi"}, headers=E1)
    p = plan(c, mid)
    assert stat(p)[8] == "pending" and stat(p)[9] == "pending" and p["verdict"]["code"] != "ready"


def test_fail_no_edge_not_eligible(env):
    bad = good_dev()
    bad["oos"]["pooled"] = {"n": 268, "exp_r": -0.088, "ci95": [-0.2, 0.02]}
    bad["oos"]["p_vs_random"] = 0.6
    c, app, mid, rid, _ = setup_good(env, dev=bad, opened=False, verdict="no_edge")
    p = plan(c, mid)
    assert stat(p)[4] == "failed" and p["verdict"]["code"] == "not_eligible" and "CHƯA" in p["verdict"]["label_vi"]
    assert any("edge" in x for x in p["steps"][3]["suggestions"]) and p["verdict"]["reasons"]
    assert all(s["status"] != "passed" for s in p["steps"][6:])
    assert c.post(f"/class/methods/{mid}/plan/approve", json={}, headers=M).status_code == 409
    md = c.get(f"/class/methods/{mid}/plan/export", headers=M).text
    assert "KHÔNG có edge" in md and "-0,088" in md and "CHƯA đủ điều kiện" in md
    assert "sẵn sàng" not in md.lower().replace("chưa phải 'sẵn sàng'", "")


def test_locked_test_pending_then_failed(env):
    c, app, mid, rid, _ = setup_good(env, opened=False)
    p = plan(c, mid)
    assert stat(p)[4] == "pending" and p["verdict"]["code"] == "incomplete"          # dev đạt nhưng test khoá chưa mở -> không thể 'passed'
    assert stat(p)[5] in ("blocked", "pending") or stat(p)[5] == "passed"
    assert p["steps"][3]["action"]["kind"] == "run_test"
    # mở test khoá nhưng không đạt
    c2, app2, tmp = env
    sid_dir = tmp / "state" / "scenarios" / "scn_good"
    (sid_dir / "test_opened.json").write_text("{}")
    r = json.loads((sid_dir / "result.json").read_text())
    r["test"] = {"status": "done", "summary": {"n": 40, "exp_r": -0.2}}
    r["verdict"] = "no_edge"
    (sid_dir / "result.json").write_text(json.dumps(r))
    p = plan(c, mid)
    assert stat(p)[4] == "failed" and p["verdict"]["code"] == "not_eligible"


def test_step5_needs_groups_and_regime(env):
    thin = good_dev()
    thin["oos"]["by_series"] = {"EURUSD|H1": {"n": 200, "exp_r": 0.1}}
    c, app, mid, rid, _ = setup_good(env, dev=thin, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    assert stat(plan(c, mid))[5] == "pending"                                           # 1 nhóm: chưa đủ để kết luận ổn định
    neg = good_dev()
    neg["oos"]["by_year"] = {str(y): {"n": 50, "exp_r": -0.1 if y < 2024 else 0.5} for y in range(2021, 2025)}
    fabricate(app, env[2], rid, "scn_good2", dev=neg, det=GOOD_DET, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}}, opened=True)
    assert stat(plan(c, mid))[5] == "failed"
    # phương pháp có quan hệ regime nhưng chưa có số liệu theo regime -> không thể đạt
    c3, app3, mid3, rid3, _ = setup_good(env, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    rid_b = c3.post(f"/class/methods/{mid3}/scenarios", json={"new": {"title": "Phụ"}, "role": "filter"}, headers=E1).json()["scenario"]["room_id"]
    put(c3, mid3, [{"kind": "regime", "a": rid3, "params": {"regime": "range"}}, {"kind": "complementary", "a": rid3, "b": rid_b}])
    assert stat(plan(c3, mid3))[5] == "pending"


def test_step6_risk_limits(env):
    c, app, mid, rid, _ = setup_good(env, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "stress", "data": {"passed": True}}, headers=M)
    assert stat(plan(c, mid))[6] == "passed"
    c.post(f"/class/methods/{mid}/canvas/risk_per_trade/edit", json={"text": "Rủi ro 5% vốn mô phỏng mỗi lệnh"}, headers=E1)
    c.post(f"/class/methods/{mid}/canvas/risk_per_trade/confirm", json={}, headers=E1)
    p = plan(c, mid)
    assert stat(p)[6] == "failed" and p["verdict"]["code"] == "not_eligible" and any("2%" in x for x in p["steps"][5]["suggestions"])
    c.post(f"/class/methods/{mid}/canvas/risk_per_trade/edit", json={"text": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh"}, headers=E1)
    c.post(f"/class/methods/{mid}/canvas/risk_per_trade/confirm", json={}, headers=E1)
    c.post(f"/class/methods/{mid}/plan/evidence", json={"kind": "stress", "data": {"passed": False}}, headers=M)
    assert stat(plan(c, mid))[6] == "failed"                                              # stress không đạt


def test_experimental_excluded_and_blocked(env):
    c, app, mid, rid, _ = setup_good(env, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    ex = c.post(f"/class/methods/{mid}/scenarios", json={"new": {"title": "Thử nghiệm"}, "role": "experimental"}, headers=E1).json()["scenario"]["room_id"]
    assert ex
    assert stat(plan(c, mid))[1] == "passed"                                              # kịch bản experimental không chặn
    # kịch bản core thứ hai chưa dạy -> bước 1 không đạt và các bước sau 'blocked' nếu từng đạt
    c.post(f"/class/methods/{mid}/scenarios", json={"new": {"title": "Core hai"}, "role": "core"}, headers=E1)
    p = plan(c, mid)
    assert stat(p)[1] == "pending" or stat(p)[1] == "failed"
    assert stat(p)[8] != "passed" and stat(p)[9] != "passed"


def test_recheck_snapshot_since_and_pdf(env):
    c, app, mid, rid, _ = setup_good(env, test={"status": "done", "summary": {"n": 40, "exp_r": 0.1}})
    r1 = c.post(f"/class/methods/{mid}/plan/recheck", headers=E1).json()
    r2 = plan(c, mid)
    assert {s["n"]: s["since"] for s in r1["steps"]} == {s["n"]: s["since"] for s in r2["steps"]}      # mốc ngày giữ nguyên khi trạng thái không đổi
    pdf = c.get(f"/class/methods/{mid}/plan/export?format=pdf", headers=E1)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-1.4") and pdf.content.rstrip().endswith(b"%%EOF")
    assert c.get(f"/class/methods/{mid}/plan/export?format=docx", headers=E1).status_code == 422
    lst = c.get("/class/methods", headers=E1).json()["items"][0]
    assert lst["plan"]["total"] == 9 and lst["scenario_count"] == 1


def test_memory_hook_soft(env):
    c, app, *_ = env
    mid = mk(c)
    c.post(f"/class/methods/{mid}/canvas/risk_per_trade/edit", json={"text": "Rủi ro 0,5% vốn mô phỏng mỗi lệnh"}, headers=E1)
    n = app.state.class_store.q("SELECT COUNT(*) c FROM class_memory WHERE src_kind='method'")[0]["c"]
    assert n == 1
    assert compute_plan(app.state.methods, mid)["method_id"] == mid
