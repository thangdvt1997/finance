"""Strategy card + tiêu chí chuyển giai đoạn (paper -> xét duyệt). Thẻ là YAML trong repo (cards/*.yaml, bất biến theo phiên bản qua git);
giai đoạn của TỪNG tài khoản được TÍNH TỰ ĐỘNG từ số liệu thật (số tuần forward, số lệnh, Sharpe, drawdown, drift, TCA, hash-chain, cấu hình).
Hệ thống KHÔNG tự 'duyệt' lên bước tiền thật: tối đa tới 'đủ điều kiện xét duyệt' — quyết định cuối là của người + cổng pháp lý G1-G3."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

STAGES = {
    "pipeline_test": "Kiểm thử đường ống (không có ý nghĩa thống kê)",
    "retired": "Đã thay thế (đóng băng)",
    "paper_early": "Paper — đang tích luỹ mẫu",
    "paper_hold": "Paper — đủ thời gian nhưng CHƯA đạt tiêu chí",
    "review_ready": "Đủ điều kiện XÉT DUYỆT (cần người duyệt; chưa phải tiền thật)",
    "suspended": "Đình chỉ — cần rà soát ngay",
    "no_card": "Chưa có strategy card",
}


def load_cards(card_dir: str | None) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    if not card_dir or not Path(card_dir).is_dir():
        return cards
    for p in sorted(Path(card_dir).glob("*.y*ml")):
        try:
            c = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        if c.get("id"):
            c["_file"] = p.name
            cards[c["id"]] = c
    return cards


def card_for(cards: dict[str, dict], strategy: str) -> dict | None:
    for c in cards.values():
        if c.get("strategy") == strategy:
            return c
    return None


def expectation_for(card: dict | None, account_id: str) -> dict | None:
    """Kỳ vọng backtest áp dụng cho tài khoản (cùng universe/tham số). Tài khoản không nằm trong `applies_to.accounts` -> None."""
    if not card or account_id not in ((card.get("applies_to") or {}).get("accounts") or []):
        return None
    bt, ex = card.get("backtest") or {}, card.get("expectation") or {}
    return {"sharpe": bt.get("sharpe"), "sharpe_ci95": bt.get("sharpe_ci95"), "vol_ann": bt.get("vol"), "cagr": bt.get("cagr_total"),
            "max_dd": bt.get("max_dd"), "turnover_yr": bt.get("turnover_yr"), "cost_drag_yr": bt.get("cost_drag_yr"),
            "sharpe_forward": ex.get("sharpe_forward"), "source": bt.get("source")}


def _crit(cid: str, label: str, required: Any, actual: Any, ok: bool | None, hard: bool = False, unit: str = "") -> dict:
    return {"id": cid, "label": label, "required": required, "actual": actual, "ok": ok, "hard": hard, "unit": unit}


def weeks_between(a: datetime | None, b: datetime) -> float:
    if not a:
        return 0.0
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    return max(0.0, (b - a).total_seconds() / 604800.0)


def evaluate(card: dict | None, acct: dict, perf: dict | None, drift: dict | None, tca: dict | None, chain_ok: bool | None,
             versions: list[dict], n_fills: int, n_rebalances: int, now: datetime, params_hash: str | None) -> dict:
    """acct: {account_id, replay, meaningful, deprecated, status, inception}. perf: perfx.report. Trả {stage, label, criteria, progress,...}."""
    out: dict[str, Any] = {"account_id": acct["account_id"], "card_id": card.get("id") if card else None}
    if acct.get("deprecated"):
        return {**out, "stage": "retired", "stage_label": STAGES["retired"], "criteria": [], "progress": None}
    if acct.get("replay") or not acct.get("meaningful", True):
        return {**out, "stage": "pipeline_test", "stage_label": STAGES["pipeline_test"], "criteria": [], "progress": None}
    if not card:
        return {**out, "stage": "no_card", "stage_label": STAGES["no_card"], "criteria": [], "progress": None}
    g = (card.get("gates") or {}).get("paper_to_review") or {}
    last_v = versions[-1] if versions else None
    v_start = last_v["created_at"] if last_v else None
    incep = acct.get("inception")
    # đồng hồ chỉ tính từ khi cấu hình hiện hành có hiệu lực (đổi tham số = bắt đầu lại phiên bản mới); phiên bản đầu = từ inception
    clock_from = incep if (not last_v or last_v["version"] == 1) else max(x for x in (incep, v_start) if x)
    weeks = weeks_between(clock_from, now)
    days = int((perf or {}).get("days") or 0)
    m = (perf or {}).get("metrics") or {}
    sharpe = (m.get("sharpe") or {}).get("value")
    sh_ci = (m.get("sharpe") or {}).get("ci95")
    max_dd = (m.get("max_dd") or {}).get("value")
    crit: list[dict] = [
        _crit("weeks", "Số tuần forward với cấu hình hiện hành", g.get("min_weeks"), round(weeks, 2), weeks >= g["min_weeks"] if g.get("min_weeks") else None, unit="tuần"),
        _crit("days", "Số ngày giao dịch có lợi suất", g.get("min_trading_days"), days, days >= g["min_trading_days"] if g.get("min_trading_days") else None, unit="ngày"),
        _crit("fills", "Số lệnh khớp (mô phỏng)", g.get("min_fills"), n_fills, n_fills >= g["min_fills"] if g.get("min_fills") else None),
        _crit("rebalances", "Số kỳ tái cân bằng đã chạy", g.get("min_rebalances"), n_rebalances, n_rebalances >= g["min_rebalances"] if g.get("min_rebalances") else None),
    ]
    if g.get("min_sharpe") is not None:
        crit.append(_crit("sharpe", "Sharpe (điểm) ≥ ngưỡng — CI95 chỉ để tham khảo", g["min_sharpe"], None if sharpe is None else round(sharpe, 3),
                          None if sharpe is None or days < (g.get("min_trading_days") or 0) else sharpe >= g["min_sharpe"]))
    if g.get("max_drawdown") is not None:
        crit.append(_crit("max_dd", "Max drawdown không vượt ngưỡng", -g["max_drawdown"], None if max_dd is None else round(max_dd, 4),
                          None if max_dd is None else max_dd >= -g["max_drawdown"], hard=True))
    dstat = (drift or {}).get("status")
    if g.get("require_no_drift_red", True):
        crit.append(_crit("drift", "Không có cảnh báo suy giảm ĐỎ", "≠ red", dstat or "n/a", None if dstat in (None, "n/a", "insufficient") else dstat != "red", hard=True))
    ratio = ((tca or {}).get("overall") or {}).get("ratio")
    if g.get("max_exec_cost_ratio") is not None:
        crit.append(_crit("exec_cost", "Chi phí thực / giả định ≤ ngưỡng", g["max_exec_cost_ratio"], None if ratio is None else round(ratio, 3),
                          None if ratio is None or n_fills < 10 else ratio <= g["max_exec_cost_ratio"]))
    if g.get("require_chain_ok", True):
        crit.append(_crit("chain", "Hash-chain journal nguyên vẹn", True, chain_ok, chain_ok, hard=True))
    if g.get("require_never_locked", True):
        crit.append(_crit("kill", "Kill-switch không ở trạng thái khoá cứng", "≠ locked", acct.get("status"), acct.get("status") != "locked", hard=True))
    if g.get("require_config_stable", True):
        crit.append(_crit("config", "Cấu hình không đổi trong toàn bộ cửa sổ đánh giá", "phiên bản hiện hành bắt đầu từ inception",
                          f"v{last_v['version']}" if last_v else "?", (last_v["version"] == 1) if last_v else None))
    if card.get("locked_params_hash", {}).get(acct["account_id"]) and params_hash:
        crit.append(_crit("params_lock", "Tham số khớp hash đã khoá trong thẻ", card["locked_params_hash"][acct["account_id"]][:12], params_hash[:12],
                          params_hash == card["locked_params_hash"][acct["account_id"]], hard=True))
    hard_fail = [c for c in crit if c["hard"] and c["ok"] is False]
    soft_fail = [c for c in crit if not c["hard"] and c["ok"] is False]
    unknown = [c for c in crit if c["ok"] is None]
    min_w = g.get("min_weeks") or 0
    if hard_fail:
        stage = "suspended"
    elif weeks < min_w or days < (g.get("min_trading_days") or 0):
        stage = "paper_early"
    elif soft_fail:
        stage = "paper_hold"
    elif unknown:
        stage = "paper_hold"
    else:
        stage = "review_ready"
    return {**out, "stage": stage, "stage_label": STAGES[stage],
            "progress": {"weeks": round(weeks, 2), "weeks_required": min_w, "pct": round(min(1.0, weeks / min_w), 3) if min_w else None,
                         "days": days, "days_required": g.get("min_trading_days"), "clock_from": clock_from.isoformat() if clock_from else None},
            "criteria": crit, "failing": [c["id"] for c in hard_fail + soft_fail], "unknown": [c["id"] for c in unknown],
            "sharpe_ci95": sh_ci,
            "note": "Không có bước tự động nào dẫn tới tiền thật: 'review_ready' chỉ là điều kiện cần, còn phải qua duyệt tay + cổng pháp lý G1-G3 (PLAN.md)."}
