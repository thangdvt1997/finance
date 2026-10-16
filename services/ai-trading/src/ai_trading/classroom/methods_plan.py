"""KẾ HOẠCH ÁP DỤNG phương pháp (pipeline 9 bước, tiêu chí đạt TẤT ĐỊNH) + xuất tài liệu md/PDF. Hợp đồng: docs/handoff/METHOD_API.md (mục 9).
Chỉ ĐỌC dữ liệu sẵn có (độ rõ/canvas, nhãn, kết quả backtest, test khoá); không sửa logic của chúng. TRUNG THỰC: thiếu số liệu = 'pending' (không bịa);
bước 4-6 trượt -> 'CHƯA đủ điều kiện áp dụng'; nhãn 'ready' chỉ khi đủ cả 9 bước. CHỈ nghiên cứu/paper — không có đường đặt lệnh."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .api import NOSTORE
from .methods import Methods, ROLES as SCEN_ROLES
from .safety import clean_text, looks_injected
from .store import now

THRESHOLDS = {
    "clarity_min": 80, "label_precision_min": 0.70, "label_coverage_min": 0.80, "label_n_min": 12, "golden_min": 3,
    "dev_trades_min": 100, "p_vs_random_max": 0.05, "dsr_min": 0.95, "pbo_max": 0.5, "stability_positive_share_min": 0.6, "stability_group_n_min": 10,
    "paper_trades_min": 30, "paper_weeks_min": 12, "risk_per_trade_max_pct": 2.0,
}
T = THRESHOLDS
REQUIRED_ROWS = ("symbol_tf", "formation", "trigger", "invalidation", "sl", "tp", "sizing")
RISK_ROWS = ("risk_per_trade", "hot_risk", "loss_limits", "stop_rules")
STEPS = (
    (1, "clarity", "Ý tưởng đủ rõ", "Idea is clear enough"),
    (2, "formalize", "Hình thức hoá thành luật máy + golden test", "Formalised as machine rules + golden tests"),
    (3, "scan_labels", "Quét lịch sử + nhãn chuyên gia", "History scan + expert labels"),
    (4, "backtest", "Backtest trung thực", "Honest backtest"),
    (5, "stability", "Ổn định theo regime/ mã/ khung", "Stability by regime/symbol/timeframe"),
    (6, "risk", "Rủi ro và guardrail của phương pháp", "Method risk & guardrails"),
    (7, "paper", "Paper-trade đủ lệnh", "Paper-trading, enough trades"),
    (8, "approval", "Rà soát và phê duyệt của master", "Master review & approval"),
    (9, "docs", "Tài liệu áp dụng", "Application document"),
)
MASTER_STEPS = (4, 7, 8)
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_NUM = re.compile(r"\d")
DISCLAIMER = "Chỉ nghiên cứu và mô phỏng (paper); hệ thống không đặt lệnh thật. Vốn thật cần cổng pháp lý G1-G3 và xác nhận của người dùng. Kết quả quá khứ không đảm bảo tương lai."


def crit(cid: str, label: str, required: str, actual: Any, ok: bool | None, scenario: str | None = None) -> dict:
    return {"id": cid, "label_vi": label, "required": required, "actual": "chưa có" if actual is None else str(actual), "pass": ok, "scenario": scenario}


def _f(x: Any, nd: int = 3) -> str | None:
    return None if x is None else f"{x:.{nd}f}".replace(".", ",")


def _status(cs: list[dict]) -> str:
    if any(c["pass"] is False for c in cs):
        return "failed"
    if not cs or any(c["pass"] is None for c in cs):
        return "pending"
    return "passed"


def _pct(text: str) -> float | None:
    m = _PCT.search(text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _dsr(dev: dict) -> float | None:
    d = dev.get("dsr") if dev.get("dsr") is not None else (dev.get("oos") or {}).get("dsr")
    if isinstance(d, dict):
        d = d.get("dsr")
    return d if isinstance(d, (int, float)) else None


def _share(groups: dict, nmin: int) -> tuple[int, float | None]:
    q = [g for g in (groups or {}).values() if isinstance(g, dict) and (g.get("n") or 0) >= nmin and g.get("exp_r") is not None]
    return len(q), (sum(1 for g in q if g["exp_r"] > 0) / len(q) if q else None)


SUGG = {
    "exp_pos": "Không có edge sau chi phí: làm rõ lại ý tưởng với ví dụ SAI/gần giống, đổi khung hoặc mã, thêm bộ lọc có lý do kinh tế, hoặc dừng kịch bản này.",
    "ci_low": "Khoảng tin cậy 95% còn chứa 0: chưa chứng minh có edge; cần thêm mẫu độc lập (thêm mã/khung hợp lý) chứ không chỉnh tham số theo kết quả.",
    "p_random": "Chưa vượt baseline ngẫu nhiên: luật chưa tốt hơn vào lệnh ngẫu nhiên cùng SL/TP; xem lại điều kiện kích hoạt.",
    "dsr": "DSR thấp: số lần thử/tham số quá nhiều so với bằng chứng; thu gọn lưới tham số, đăng ký giả thuyết trước.",
    "pbo": "PBO cao: nguy cơ quá khớp; bỏ bớt tham số tự do.",
    "trades": "Số lệnh ngoài mẫu quá ít: kết luận không đáng tin; nới điều kiện hợp lý hoặc thêm mã/khung.",
    "locked": "Test khoá không đạt: KHÔNG chỉnh rồi chạy lại cùng kịch bản (test khoá đã mở 1 lần); làm kịch bản mới với giả thuyết mới hoặc dừng.",
    "stab_series": "Không ổn định theo mã/khung: giới hạn phương pháp vào nhóm có bằng chứng hoặc thêm bộ lọc, rồi kiểm lại.",
    "stab_year": "Không ổn định theo năm: lợi thế có thể chỉ do một giai đoạn; giới hạn bối cảnh (regime) hoặc dừng.",
    "risk_pct": "Rủi ro mỗi lệnh vượt trần 2%: hạ xuống.",
    "hot_ge": "Rủi ro nóng phải lớn hơn hoặc bằng rủi ro mỗi lệnh.",
}


def compute_plan(M: Methods, mid: str) -> dict:
    s, sstore = M.s, M.sstore
    m = M.get(mid)
    ver = m["version"]
    scen = [x for x in M.scen_rows(mid) if x["role"] != "experimental"]
    traded = [x for x in scen if x["role"] in ("core", "support")]
    canvas = M.canvas(mid)
    rows = {r["key"]: r for r in canvas["rows"]}
    rels = M.relations(mid)
    ev: dict[int, list[dict]] = {n: [] for n in range(1, 10)}
    cr: dict[int, list[dict]] = {n: [] for n in range(1, 10)}
    sg: dict[int, list[str]] = {n: [] for n in range(1, 10)}
    act: dict[int, dict] = {}
    title = {x["room_id"]: (s.room(x["room_id"]) or {}).get("title", "?") for x in M.scen_rows(mid)}

    def sug(n: int, k: str) -> None:
        if SUGG.get(k) and SUGG[k] not in sg[n]:
            sg[n].append(SUGG[k])

    def room_act(n: int, rid: str | None, kind: str = "open_room", label: str = "Làm bước này") -> None:
        act.setdefault(n, {"kind": kind, "label_vi": label, "room_id": rid})

    # ---- 1. ý tưởng đủ rõ
    cr[1].append(crit("has_core", "Có ít nhất 1 kịch bản lõi", ">= 1", sum(1 for x in scen if x["role"] == "core"), True if any(x["role"] == "core" for x in scen) else None))
    if not scen:
        room_act(1, None, "open_canvas", "Gắn kịch bản vào phương pháp")
    for x in scen:
        rid = x["room_id"]
        rws, cl = M.room_canvas(rid)
        by = {r["key"]: r for r in rws}
        unconf = [k for k in REQUIRED_ROWS if not by[k]["confirmed"]]
        cr[1].append(crit("clarity", f"Độ rõ >= {T['clarity_min']} ({title[rid][:30]})", f">= {T['clarity_min']}", cl["score"], cl["score"] >= T["clarity_min"], rid))
        cr[1].append(crit("required_rows", f"Hàng bắt buộc đã xác nhận ({title[rid][:30]})", "7/7", f"{7 - len(unconf)}/7", True if not unconf else None, rid))
        ev[1].append({"kind": "room", "label": f"Hồ sơ kịch bản: {title[rid]}", "room_id": rid, "scenario_id": None, "value": f"độ rõ {cl['score']}"})
        if cl["score"] < T["clarity_min"] or unconf:
            room_act(1, rid, "open_room", "Làm rõ kịch bản này")

    # ---- 2. luật máy + golden
    for x in scen:
        rid = x["room_id"]
        sid = M.scenario_id_of(rid)
        res = (sstore.result(sid) or {}) if sid and sstore else {}
        reg = bool(sid and sstore and sstore.scenario(sid))
        det = res.get("detector") or {}
        cr[2].append(crit("registered", f"Luật máy đã đăng ký ({title[rid][:30]})", "có", "có" if reg else None, True if reg else None, rid))
        gt, gp = det.get("golden_total"), det.get("golden_pass")
        if det.get("status") == "done":
            cr[2].append(crit("golden", f"Golden test đạt toàn bộ, >= {T['golden_min']} ví dụ", f"{T['golden_min']}+ và 100%", f"{gp}/{gt}", (gt or 0) >= T["golden_min"] and gp == gt, rid))
            ev[2].append({"kind": "result", "label": "Kết quả detector + golden", "room_id": rid, "scenario_id": sid, "value": f"golden {gp}/{gt}"})
        else:
            cr[2].append(crit("golden", f"Golden test đạt toàn bộ ({title[rid][:30]})", "100%", None, None, rid))
        if reg:
            ev[2].append({"kind": "scenario", "label": "Kịch bản đã đăng ký", "room_id": rid, "scenario_id": sid, "value": sid})
        if not reg or det.get("status") != "done" or (gt or 0) < T["golden_min"] or gp != gt:
            room_act(2, rid, "open_room", "Hình thức hoá / chạy golden test")
    if not scen:
        cr[2].append(crit("registered", "Có kịch bản để hình thức hoá", ">= 1", 0, None))

    # ---- 3. quét + nhãn
    for x in traded:
        rid = x["room_id"]
        lb = M.label_summary(rid)
        n, prec, cov = lb["n_labeled"], lb["precision"], lb["coverage"]
        cr[3].append(crit("label_n", f"Số nhãn >= {T['label_n_min']} ({title[rid][:30]})", f">= {T['label_n_min']}", n, n >= T["label_n_min"] or None, rid))
        ok_p = None if n < T["label_n_min"] else prec >= T["label_precision_min"]
        ok_c = None if n < T["label_n_min"] or cov is None else cov >= T["label_coverage_min"]
        cr[3].append(crit("label_precision", "Độ chính xác nhãn", f">= {T['label_precision_min']}", _f(prec), ok_p, rid))
        cr[3].append(crit("label_coverage", "Độ phủ nhãn", f">= {T['label_coverage_min']}", _f(cov), ok_c, rid))
        ev[3].append({"kind": "room", "label": f"Nhãn: {title[rid]}", "room_id": rid, "scenario_id": None, "value": f"{n}/{lb['n_examples']} nhãn, chính xác {_f(prec)}"})
        if ok_p is not True or ok_c is not True:
            room_act(3, rid, "open_room", "Quét ví dụ và gắn nhãn")
    if not traded:
        cr[3].append(crit("label_n", "Có kịch bản lõi/bổ trợ để quét", ">= 1", 0, None))

    # ---- 4. backtest trung thực + 5. ổn định
    has_regime = any(r["kind"] == "regime" for r in rels)
    ci_lows: list[float] = []
    for x in traded:
        rid = x["room_id"]
        sid = M.scenario_id_of(rid)
        res = (sstore.result(sid) or {}) if sid and sstore else {}
        dev = res.get("dev") or {}
        done = dev.get("status") == "done"
        t = title[rid][:30]
        has_test_action = any(a["command"] == "test" and a.get("scenario_id") for a in s.actions(rid))
        cr[4].append(crit("hypothesis", f"Giả thuyết đã đăng ký trước khi chạy ({t})", "có", "có" if has_test_action else None, True if has_test_action else None, rid))
        if not done:
            cr[4].append(crit("dev_done", f"Backtest walk-forward đã chạy ({t})", "xong", None, None, rid))
            cr[5].append(crit("stab_data", f"Có số liệu theo nhóm ({t})", "có", None, None, rid))
            room_act(4, rid, "open_room", "Chạy backtest")
            continue
        oos = dev.get("oos") or {}
        pooled = oos.get("pooled") or {}
        n, exp, ci = pooled.get("n"), pooled.get("exp_r"), pooled.get("ci95") or [None, None]
        p, dsr, pbo = oos.get("p_vs_random"), _dsr(dev), (dev.get("pbo") or {}).get("pbo") if isinstance(dev.get("pbo"), dict) else dev.get("pbo")
        if ci[0] is not None:
            ci_lows.append(ci[0])
        cr[4] += [
            crit("trades", f"Số lệnh ngoài mẫu ({t})", f">= {T['dev_trades_min']}", n, None if n is None else n >= T["dev_trades_min"], rid),
            crit("exp_pos", "Kỳ vọng ròng sau chi phí > 0 (R)", "> 0", _f(exp), None if exp is None else exp > 0, rid),
            crit("ci_low", "Cận dưới CI95 > 0", "> 0", _f(ci[0]), None if ci[0] is None else ci[0] > 0, rid),
            crit("p_random", "p so với baseline ngẫu nhiên", f"< {T['p_vs_random_max']}", _f(p), None if p is None else p < T["p_vs_random_max"], rid),
            crit("dsr", "DSR", f">= {T['dsr_min']}", _f(dsr), None if dsr is None else dsr >= T["dsr_min"], rid),
            crit("pbo", "PBO", f"< {T['pbo_max']}", _f(pbo), None if pbo is None else pbo < T["pbo_max"], rid),
            crit("costs", "Đã tính chi phí thật (spread/trượt/phí)", "có", "có" if dev.get("costs") else None, True if dev.get("costs") else False, rid),
        ]
        for c in cr[4][-7:]:
            if c["pass"] is False:
                sug(4, c["id"])
        ev[4].append({"kind": "result", "label": f"Walk-forward: {title[rid]}", "room_id": rid, "scenario_id": sid, "value": f"n={n}, kỳ vọng {_f(exp)}R, CI95 [{_f(ci[0])}; {_f(ci[1])}]"})
        opened = bool(sstore.test_opened(sid))
        te = res.get("test") or {}
        if not opened:
            cr[4].append(crit("locked", f"Test khoá do master mở 1 lần ({t})", "đã mở và verdict edge", "chưa mở", None, rid))
            room_act(4, rid, "run_test", "Master mở test khoá")
        elif te.get("status") != "done":
            cr[4].append(crit("locked", f"Test khoá ({t})", "xong", te.get("status") or "đang chạy", None if te.get("status") in (None, "queued", "running") else False, rid))
        else:
            ok = res.get("verdict") == "edge"
            ts = te.get("summary") or {}
            cr[4].append(crit("locked", f"Test khoá đạt (verdict edge) ({t})", "edge", res.get("verdict"), ok, rid))
            ev[4].append({"kind": "result", "label": f"Test khoá: {title[rid]}", "room_id": rid, "scenario_id": sid, "value": f"n={ts.get('n')}, kỳ vọng {_f(ts.get('exp_r'))}R, verdict {res.get('verdict')}"})
            if not ok:
                sug(4, "locked")
        if any(c["pass"] is False for c in cr[4] if c["scenario"] == rid):
            room_act(4, rid, "open_room", "Xem kết quả và sửa hướng")
        # --- 5
        ns, sh = _share(oos.get("by_series"), T["stability_group_n_min"])
        ny, yh = _share(oos.get("by_year"), T["stability_group_n_min"])
        cr[5].append(crit("stab_series", f"Ổn định theo mã/khung ({t})", f">= {int(T['stability_positive_share_min'] * 100)}% nhóm dương (>= 2 nhóm)", f"{_f(sh, 2)} ({ns} nhóm)" if ns else None,
                          None if ns < 2 else sh >= T["stability_positive_share_min"], rid))
        cr[5].append(crit("stab_year", f"Ổn định theo năm ({t})", f">= {int(T['stability_positive_share_min'] * 100)}% năm dương (>= 3 năm)", f"{_f(yh, 2)} ({ny} năm)" if ny else None,
                          None if ny < 3 else yh >= T["stability_positive_share_min"], rid))
        if has_regime:
            nr, rh = _share(oos.get("by_regime"), T["stability_group_n_min"])
            cr[5].append(crit("stab_regime", f"Ổn định theo regime ({t})", f">= {int(T['stability_positive_share_min'] * 100)}% regime dương", f"{_f(rh, 2)} ({nr} regime)" if nr else None,
                              None if nr < 1 else rh >= T["stability_positive_share_min"], rid))
        for c in cr[5][-3:]:
            if c["pass"] is False:
                sug(5, c["id"])
        ev[5].append({"kind": "result", "label": f"Theo nhóm: {title[rid]}", "room_id": rid, "scenario_id": sid, "value": f"{ns} nhóm mã/khung, {ny} năm"})
        if any(c["pass"] is not True for c in cr[5] if c["scenario"] == rid):
            room_act(5, rid, "open_room", "Xem ổn định theo nhóm")
    if not traded:
        cr[4].append(crit("dev_done", "Có kịch bản lõi/bổ trợ để backtest", ">= 1", 0, None))
        cr[5].append(crit("stab_data", "Có số liệu theo nhóm", "có", None, None))

    # ---- 6. rủi ro + guardrail
    for k in RISK_ROWS:
        r = rows[k]
        ok = None if (r["confidence"] == "trống" or not r["confirmed"]) else (True if r["quantified"] else False)
        cr[6].append(crit("row_" + k, f"{r['title_vi']}: đã xác nhận + có số", "xác nhận + số", "trống" if r["confidence"] == "trống" else ("đã xác nhận" if r["confirmed"] else "chưa xác nhận"), ok))
        if ok is not True:
            act.setdefault(6, {"kind": "open_canvas", "label_vi": "Điền hồ sơ rủi ro phương pháp", "room_id": None})
    for k in ("symbols_tf", "correlation", "roles"):
        r = rows[k]
        cr[6].append(crit("row_" + k, f"{r['title_vi']}: đã xác nhận", "xác nhận", "đã xác nhận" if r["confirmed"] else ("chưa xác nhận" if r["text"] else "trống"), True if r["confirmed"] else None))
        if not r["confirmed"]:
            act.setdefault(6, {"kind": "open_canvas", "label_vi": "Điền hồ sơ rủi ro phương pháp", "room_id": None})
    rp, hp = _pct(rows["risk_per_trade"]["text"]), _pct(rows["hot_risk"]["text"])
    cr[6].append(crit("risk_pct", "Rủi ro mỗi lệnh trong trần", f"<= {T['risk_per_trade_max_pct']}%", None if rp is None else f"{_f(rp, 2)}%", None if rp is None else rp <= T["risk_per_trade_max_pct"]))
    if rp is not None and rp > T["risk_per_trade_max_pct"]:
        sug(6, "risk_pct")
    cr[6].append(crit("hot_ge", "Rủi ro nóng >= rủi ro mỗi lệnh", ">=", None if hp is None or rp is None else f"{_f(hp, 2)}% / {_f(rp, 2)}%", None if hp is None or rp is None else hp >= rp))
    if hp is not None and rp is not None and hp < rp:
        sug(6, "hot_ge")
    for x in scen:
        rid = x["room_id"]
        by = {r["key"]: r for r in M.room_canvas(rid)[0]}
        for k in ("sl", "invalidation"):
            cr[6].append(crit("scn_" + k, f"{by[k]['title_vi']} đã xác nhận ({title[rid][:30]})", "xác nhận", "đã xác nhận" if by[k]["confirmed"] else "chưa", True if by[k]["confirmed"] else None, rid))
    if len(scen) >= 2:
        has_pr = rows["priority"]["confirmed"] or any(r["kind"] in ("priority", "exclusive") for r in rels)
        cr[6].append(crit("priority", "Có thứ tự ưu tiên khi nhiều tín hiệu", "có", "có" if has_pr else None, True if has_pr else None))
    ev_rows = s.q("SELECT * FROM class_method_evidence WHERE method_id=? ORDER BY id DESC", (mid,))
    last_ev = {}
    for r in ev_rows:
        last_ev.setdefault(r["kind"], dict(r))
    st_ev = last_ev.get("stress")
    st_data = json.loads(st_ev["data"]) if st_ev else None
    cr[6].append(crit("stress", "Bằng chứng kiểm tra stress (master ghi)", "đạt", None if not st_data else ("đạt" if st_data.get("passed") else "không đạt"), None if not st_data else bool(st_data.get("passed"))))
    if st_ev:
        ev[6].append({"kind": "evidence", "label": "Kiểm tra stress", "room_id": None, "scenario_id": None, "value": ", ".join(st_data.get("scenarios") or [])[:120] or ("đạt" if st_data.get("passed") else "không đạt")})
    else:
        act.setdefault(6, {"kind": "attach_evidence", "label_vi": "Ghi bằng chứng stress (master)", "room_id": None})
    ev[6].append({"kind": "canvas", "label": "Hồ sơ phương pháp", "room_id": None, "scenario_id": None, "value": f"độ rõ {canvas['clarity']['score']}"})

    # ---- 7. paper
    pp_ev = last_ev.get("paper")
    pp = json.loads(pp_ev["data"]) if pp_ev else None
    floor = min(ci_lows) if ci_lows else None
    if pp:
        cr[7] += [crit("paper_trades", "Số lệnh paper", f">= {T['paper_trades_min']}", pp.get("trades"), pp.get("trades", 0) >= T["paper_trades_min"]),
                  crit("paper_weeks", "Số tuần paper", f">= {T['paper_weeks_min']}", pp.get("weeks"), pp.get("weeks", 0) >= T["paper_weeks_min"]),
                  crit("paper_chain", "Sổ lệnh hash-chain hợp lệ", "có", "có" if pp.get("hash_chain_ok") else "không", bool(pp.get("hash_chain_ok"))),
                  crit("paper_vs_bt", "Kỳ vọng paper không thấp hơn cận dưới CI backtest", ">= cận dưới", f"{_f(pp.get('expectancy_r'))} / {_f(floor)}",
                       None if floor is None or pp.get("expectancy_r") is None else pp["expectancy_r"] >= floor)]
        ev[7].append({"kind": "evidence", "label": "Paper forward-test", "room_id": None, "scenario_id": None, "value": f"{pp.get('trades')} lệnh, {pp.get('weeks')} tuần, kỳ vọng {_f(pp.get('expectancy_r'))}R"})
    else:
        cr[7].append(crit("paper_trades", "Có bằng chứng paper (master ghi)", "có", None, None))
        act[7] = {"kind": "attach_evidence", "label_vi": "Ghi bằng chứng paper (master)", "room_id": None}

    # ---- 8. phê duyệt master
    ap = s.q("SELECT * FROM class_method_approval WHERE method_id=?", (mid,))
    ap = dict(ap[0]) if ap else None
    if ap and ap["version"] == ver:
        cr[8].append(crit("approved", "Master đã phê duyệt đúng phiên bản hiện tại", "có", f"{'duyệt' if ap['approved'] else 'từ chối'} v{ap['version']}", bool(ap["approved"])))
        ev[8].append({"kind": "evidence", "label": "Phê duyệt master", "room_id": None, "scenario_id": None, "value": f"{'duyệt' if ap['approved'] else 'từ chối'} {ap['at'][:10]} {ap['note'] or ''}".strip()})
    else:
        cr[8].append(crit("approved", "Master đã phê duyệt đúng phiên bản hiện tại", "có", "hết hiệu lực (phương pháp đã đổi)" if ap else None, None))
        act[8] = {"kind": "approve", "label_vi": "Master xem xét và phê duyệt", "room_id": None}

    # ---- 9. tài liệu
    ex = s.q("SELECT * FROM class_method_export WHERE method_id=? AND version=? ORDER BY id DESC LIMIT 1", (mid, ver))
    cr[9].append(crit("exported", "Tài liệu áp dụng đã xuất đúng phiên bản (chỉ khi bước 1-8 đạt)", "có", f"{ex[0]['fmt']} {ex[0]['at'][:10]}" if ex else None, True if ex else None))
    if ex:
        ev[9].append({"kind": "export", "label": "Tài liệu áp dụng", "room_id": None, "scenario_id": None, "value": f"băm {ex[0]['sha']}"})
    else:
        act[9] = {"kind": "export", "label_vi": "Xuất tài liệu", "room_id": None}

    # ---- tổng hợp
    prev = {}
    r = s.q("SELECT snapshot FROM class_method_plan WHERE method_id=?", (mid,))
    if r:
        try:
            prev = {x["n"]: x for x in json.loads(r[0]["snapshot"])["steps"]}
        except (ValueError, KeyError):
            prev = {}
    t_now = now()
    steps: list[dict] = []
    for n, key, vi, en in STEPS:
        status = _status(cr[n])
        need = {4: (1, 2, 3), 5: (4,), 6: (4, 5), 7: (4, 5, 6), 8: (1, 2, 3, 4, 5, 6, 7), 9: tuple(range(1, 9))}.get(n, ())
        if status == "passed" and any(steps[i - 1]["status"] != "passed" for i in need):
            status = "blocked"
        old = prev.get(n)
        since = old["since"] if old and old["status"] == status else t_now
        steps.append({"n": n, "key": key, "title_vi": vi, "title_en": en, "status": status, "owner": "master" if n in MASTER_STEPS else m["owner_name"] or m["owner"], "since": since,
                      "criteria": cr[n], "evidence": ev[n], "action": act.get(n) or ({"kind": "open_canvas", "label_vi": "Xem lại", "room_id": None}), "suggestions": sg[n]})
        if status == "passed":
            steps[-1]["action"] = None
    st = {s_["n"]: s_["status"] for s_ in steps}
    passed = sum(1 for s_ in steps if s_["status"] == "passed")
    reasons = [f"Bước {s_['n']} ({s_['title_vi']}): " + ("; ".join(f"{c['label_vi']} = {c['actual']} (cần {c['required']})" for c in s_["criteria"] if c["pass"] is not True)[:400] or s_["status"])
               for s_ in steps[3:6] if s_["status"] != "passed"]
    if any(st[n] == "failed" for n in (4, 5, 6)):
        code, lvi, len_ = "not_eligible", "CHƯA đủ điều kiện áp dụng", "NOT yet eligible for application"
    elif not all(st[n] == "passed" for n in (4, 5, 6)):
        code, lvi, len_ = "incomplete", "CHƯA đủ điều kiện áp dụng (chưa đủ bằng chứng ở bước 4-6)", "NOT yet eligible (steps 4-6 lack evidence)"
    elif all(st[n] == "passed" for n in (7, 8, 9)):
        code, lvi, len_ = "ready", "Đủ điều kiện áp dụng ở chế độ nghiên cứu/paper", "Eligible for research/paper application"
    else:
        code, lvi, len_ = "eligible_review", "Đã qua bước 4-6; còn chờ paper, phê duyệt hoặc tài liệu (chưa phải 'sẵn sàng')", "Steps 4-6 passed; paper, approval or document pending (not 'ready')"
    return {"method_id": mid, "method_name": m["name"], "method_version": ver, "computed_at": t_now, "progress": {"passed": passed, "total": 9},
            "verdict": {"code": code, "label_vi": lvi, "label_en": len_, "reasons": reasons, "paper_only": True, "note_vi": "Chỉ nghiên cứu/paper; vốn thật cần cổng pháp lý G1-G3."},
            "steps": steps, "thresholds": THRESHOLDS, "disclaimer": DISCLAIMER}


# ---------------------------------------------------------------------- xuất tài liệu
def export_md(M: Methods, mid: str, plan: dict) -> str:
    m = M.get(mid)
    L = [f"# Kế hoạch áp dụng phương pháp {m['name']}", "", f"_Phiên bản phương pháp {m['version']}, tạo lúc {plan['computed_at']}. {DISCLAIMER}_", "",
         f"## Kết luận", "", f"**{plan['verdict']['label_vi']}** ({plan['progress']['passed']}/9 bước đạt).", ""]
    if plan["verdict"]["code"] != "ready":
        L += ["Lý do chưa đủ điều kiện:", ""] + [f"- {r}" for r in plan["verdict"]["reasons"]] + [""]
    L += ["Phương pháp này chỉ phục vụ nghiên cứu và paper-trade; không có đường đặt lệnh thật và tài liệu này không hứa lợi nhuận.", "", "## Các kịch bản", ""]
    sc = M.scen_rows(mid)
    if sc:
        L += ["| Kịch bản | Vai trò | Độ rõ | Nhãn (chính xác) | Kết quả test | Kỳ vọng R | Số lệnh |", "|---|---|---|---|---|---|---|"]
        for x in sc:
            v = M.scenario_view(x["room_id"], x["role"])
            t = v["test"]
            L.append(f"| {v['title']} | {x['role']} | {v['clarity']['score']} | {_f(v['labels']['precision']) or 'chưa có'} | {t['verdict'] if t['dev_done'] else 'chưa chạy'} | {_f(t['expectancy_r']) or 'chưa có'} | {t['trades'] if t['trades'] is not None else 'chưa có'} |")
    else:
        L.append("Chưa có kịch bản nào.")
    L += ["", "## Quy tắc kết hợp", ""]
    g = M.graph(mid)
    names = {n["id"]: n["title"] for n in g["graph"]["nodes"]}
    LBL = {"exclusive": "loại trừ nhau", "complementary": "bổ trợ nhau", "priority": "ưu tiên hơn", "mirror": "là bản đối xứng buy/sell của", "timeframe": "là khung chính, còn kia là khung xác nhận:", "regime": "chỉ chạy trong regime"}
    for r in g["relations"]:
        tail = f" {r['params'].get('regime')}" if r["kind"] == "regime" else f" {names.get(r['b'], '?')}"
        L.append(f"- {names.get(r['a'], '?')} {LBL[r['kind']]}{tail}" + (f" ({r['note']})" if r["note"] else ""))
    if not g["relations"]:
        L.append("Chưa khai báo quan hệ giữa các kịch bản.")
    if g["priority_order"] and len(g["priority_order"]) > 1:
        L.append("- Thứ tự xét tín hiệu: " + " > ".join(names[i] for i in g["priority_order"]))
    L += ["", "## Hồ sơ phương pháp (quản trị vốn, quy tắc dừng, bối cảnh)", ""]
    for r in M.canvas(mid)["rows"]:
        L.append(f"- **{r['title_vi']}** ({r['confidence']}{', đã xác nhận' if r['confirmed'] else ''}): {r['text'] or 'chưa khai báo'}")
    L += ["", "## Pipeline 9 bước", "", "| Bước | Trạng thái | Chịu trách nhiệm | Từ ngày |", "|---|---|---|---|"]
    for s_ in plan["steps"]:
        L.append(f"| {s_['n']}. {s_['title_vi']} | {s_['status']} | {s_['owner']} | {s_['since'][:10]} |")
    L += ["", "## Kết quả test (số thật)", ""]
    any_ev = False
    for s_ in plan["steps"]:
        for e in s_["evidence"]:
            if e["kind"] in ("result", "evidence"):
                any_ev = True
                L.append(f"- Bước {s_['n']} - {e['label']}: {e['value']}")
    if not any_ev:
        L.append("Chưa có kết quả test nào cho phương pháp này.")
    for x in M.scen_rows(mid):
        t = M.test_view(x["room_id"])
        if t["verdict"] == "no_edge":
            L.append(f"- Kịch bản {(M.s.room(x['room_id']) or {}).get('title', '?')}: KHÔNG có edge sau chi phí (kỳ vọng {_f(t['expectancy_r'])}R, {t['trades']} lệnh).")
        elif t["dev_done"] and t["verdict"] != "edge":
            L.append(f"- Kịch bản {(M.s.room(x['room_id']) or {}).get('title', '?')}: CHƯA chứng minh có edge (verdict {t['verdict']}).")
    L += ["", "## Rủi ro", ""]
    for s_ in plan["steps"][5:6]:
        for c in s_["criteria"]:
            L.append(f"- {c['label_vi']}: {c['actual']} (cần {c['required']}) - {'đạt' if c['pass'] else 'chưa đạt' if c['pass'] is False else 'chưa có dữ liệu'}")
    L += ["", "## Việc còn thiếu", ""]
    todo = [f"- Bước {s_['n']} ({s_['title_vi']}): " + "; ".join(f"{c['label_vi']}" for c in s_["criteria"] if c["pass"] is not True)[:300] for s_ in plan["steps"] if s_["status"] != "passed"]
    L += todo or ["Không còn việc thiếu."]
    sugg = [x for s_ in plan["steps"] for x in s_["suggestions"]]
    if sugg:
        L += ["", "## Gợi ý hướng sửa", ""] + [f"- {x}" for x in dict.fromkeys(sugg)]
    L += ["", "## Quyết định cần người dùng", ""]
    dec = []
    st = {s_["n"]: s_["status"] for s_ in plan["steps"]}
    if st[4] != "passed":
        dec.append("Cho phép master mở test khoá (một lần duy nhất) khi dev đã đạt; hoặc quyết định dừng/ làm lại kịch bản nếu dev trượt.")
    if st[7] != "passed":
        dec.append("Ghi bằng chứng paper-trade (>= 30 lệnh, >= 12 tuần) khi đã chạy.")
    if st[8] != "passed":
        dec.append("Master rà soát và phê duyệt (chỉ khi bước 1-7 đạt).")
    dec.append("Mọi giao dịch vốn thật nằm ngoài phạm vi: chỉ xem xét sau cổng pháp lý G1-G3 và xác nhận bằng văn bản của người dùng.")
    L += [f"- {d}" for d in dec]
    return "\n".join(L) + "\n"


def _ascii(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def export_pdf(md: str) -> bytes:
    """PDF gọn tự dựng (Helvetica, chữ không dấu vì phông chuẩn không có tiếng Việt); không cần công cụ ngoài."""
    lines: list[str] = []
    for ln in _ascii(md).splitlines():
        ln = re.sub(r"[*_`#]", "", ln).rstrip()
        while len(ln) > 95:
            cut = ln.rfind(" ", 0, 95)
            cut = cut if cut > 40 else 95
            lines.append(ln[:cut])
            ln = "  " + ln[cut:].lstrip()
        lines.append(ln)
    per = 58
    pages = [lines[i:i + per] for i in range(0, len(lines), per)] or [[""]]
    objs: list[bytes] = []
    n_pages = len(pages)
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(("<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages)) + f"] /Count {n_pages} >>").encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, pg in enumerate(pages):
        body = "BT /F1 9 Tf 12 TL 40 800 Td\n" + "\n".join("(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for ln in pg) + "\nET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(f"<< /Length {len(body.encode())} >>\nstream\n".encode() + body.encode() + b"\nendstream")
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


# ---------------------------------------------------------------------- route
def register(app: FastAPI, st: Any, store: Any, M: Methods, who, method_of, wr, j) -> None:
    def snapshot(mid: str, plan: dict, uid: str) -> None:
        store.x("INSERT OR REPLACE INTO class_method_plan(method_id,snapshot,computed_at,by_user) VALUES(?,?,?,?)",
                (mid, json.dumps({"steps": [{"n": s["n"], "status": s["status"], "since": s["since"]} for s in plan["steps"]], "verdict": plan["verdict"]["code"]}), plan["computed_at"], uid))

    @app.get("/class/methods/{mid}/plan", tags=["class-methods"])
    async def get_plan(request: Request, mid: str):
        method_of(mid, who(request))
        return j(compute_plan(M, mid))

    @app.post("/class/methods/{mid}/plan/recheck", tags=["class-methods"])
    async def recheck(request: Request, mid: str):
        w = who(request)
        method_of(mid, w)
        wr(w)
        p = compute_plan(M, mid)
        snapshot(mid, p, w.uid)
        M.log(mid, w.uid, "plan.recheck", p["verdict"]["code"])
        store.audit(w.uid, w.role, None, "method.plan.recheck", f"{mid}:{p['verdict']['code']}")
        return j(p)

    @app.post("/class/methods/{mid}/plan/evidence", tags=["class-methods"])
    async def evidence(request: Request, mid: str, body: dict):
        w = who(request)
        method_of(mid, w)
        if not w.master:
            raise HTTPException(403, "Chỉ master ghi bằng chứng kế hoạch")
        wr(w)
        kind, d = body.get("kind"), body.get("data")
        if kind not in ("paper", "stress") or not isinstance(d, dict):
            raise HTTPException(422, "kind: paper|stress và data là object")
        note = clean_text(body.get("note") or "", 300)
        if looks_injected(note):
            raise HTTPException(422, "note chứa chỉ thị")
        num = lambda v, lo, hi: isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi  # noqa: E731
        if kind == "paper":
            if not (num(d.get("trades"), 0, 1e6) and num(d.get("weeks"), 0, 520) and num(d.get("expectancy_r"), -100, 100) and isinstance(d.get("hash_chain_ok"), bool)):
                raise HTTPException(422, "paper cần trades, weeks, expectancy_r (số) và hash_chain_ok (boolean)")
            data = {k: d[k] for k in ("trades", "weeks", "expectancy_r", "hash_chain_ok")}
        else:
            if not isinstance(d.get("passed"), bool):
                raise HTTPException(422, "stress cần passed (boolean)")
            scs = d.get("scenarios") or []
            if not isinstance(scs, list) or len(scs) > 10 or any(not isinstance(x, str) or looks_injected(x) for x in scs):
                raise HTTPException(422, "scenarios: danh sách <= 10 chuỗi hợp lệ")
            data = {"passed": d["passed"], "scenarios": [clean_text(x, 60) for x in scs]}
        eid = store.x("INSERT INTO class_method_evidence(method_id,kind,data,note,by_user,at) VALUES(?,?,?,?,?,?)", (mid, kind, json.dumps(data), note, w.uid, now()))
        M.log(mid, w.uid, "evidence." + kind)
        store.audit(w.uid, w.role, None, "method.plan.evidence", f"{mid}:{kind}")
        return j({"ok": True, "id": eid})

    @app.post("/class/methods/{mid}/plan/approve", tags=["class-methods"])
    async def approve(request: Request, mid: str, body: dict):
        w = who(request)
        m = method_of(mid, w)
        if not w.master:
            raise HTTPException(403, "Chỉ master phê duyệt")
        wr(w)
        ok = body.get("approve", True)
        if not isinstance(ok, bool):
            raise HTTPException(422, "approve phải là boolean")
        note = clean_text(body.get("note") or "", 300)
        if looks_injected(note):
            raise HTTPException(422, "note chứa chỉ thị")
        if ok:
            p = compute_plan(M, mid)
            miss = [s["n"] for s in p["steps"][:7] if s["status"] != "passed"]
            if miss:
                raise HTTPException(409, "Chưa thể phê duyệt: bước chưa đạt " + ", ".join(map(str, miss)))
        store.x("INSERT OR REPLACE INTO class_method_approval(method_id,version,approved,note,by_user,at) VALUES(?,?,?,?,?,?)", (mid, m["version"], 1 if ok else 0, note, w.uid, now()))
        M.log(mid, w.uid, "plan.approve" if ok else "plan.reject")
        store.audit(w.uid, w.role, None, "method.plan.approve" if ok else "method.plan.reject", mid)
        return j({"ok": True, "approved": ok, "version": m["version"]})

    @app.get("/class/methods/{mid}/plan/export", tags=["class-methods"])
    async def export(request: Request, mid: str, format: str = "md"):
        w = who(request)
        m = method_of(mid, w)
        if format not in ("md", "pdf"):
            raise HTTPException(422, "format: md|pdf")
        p = compute_plan(M, mid)
        md = export_md(M, mid, p)
        sha = hashlib.sha256(md.encode()).hexdigest()[:16]
        if all(s["status"] == "passed" for s in p["steps"][:8]):
            store.x("INSERT INTO class_method_export(method_id,version,sha,fmt,by_user,at) VALUES(?,?,?,?,?,?)", (mid, m["version"], sha, format, w.uid, now()))
        M.log(mid, w.uid, "plan.export", format)
        store.audit(w.uid, w.role, None, "method.plan.export", f"{mid}:{format}")
        slug = re.sub(r"[^a-z0-9]+", "-", _ascii(m["name"]).lower()).strip("-")[:40] or "phuong-phap"
        hdr = {**NOSTORE, "Content-Disposition": f'attachment; filename="ke-hoach-ap-dung-{slug}.{format}"', "X-Plan-Verdict": p["verdict"]["code"]}
        if format == "pdf":
            return Response(export_pdf(md), media_type="application/pdf", headers=hdr)
        return Response(md, media_type="text/markdown; charset=utf-8", headers=hdr)
