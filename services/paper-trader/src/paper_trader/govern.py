"""Cấu hình bất biến theo phiên bản: băm cấu hình hiệu lực của từng tài khoản. Đổi bất kỳ tham số/rủi ro/chi phí giả định nào
-> hash khác -> phiên bản MỚI (bảng paper_config_versions, append-only) + sự kiện `config_version` trong journal (có hash-chain).
Nhờ đó mọi kết quả forward test luôn gắn với đúng bộ tham số đã chạy; không thể 'sửa tham số cho đẹp' mà không để lại dấu vết."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from . import chain


def effective_config(cfg: dict, acfg: dict, rt: Any) -> dict:
    """Cấu hình hiệu lực (CHỈ phần tất định ảnh hưởng kết quả; không gồm đường dẫn, token, cửa sổ tin tĩnh)."""
    eng = rt.engine
    return {
        "account_id": acfg["id"], "strategy": acfg["strategy"], "base_ccy": acfg.get("base_ccy", "USD"),
        "initial_capital": float(acfg["initial_capital"]), "benchmark": acfg.get("benchmark"), "rebalance": acfg.get("rebalance", "monthly"),
        "universe": list(acfg["universe"]), "start_at": acfg.get("start_at"), "deprecated": bool(acfg.get("deprecated", False)),
        "tf": cfg.get("tf", "D1"), "periods_per_year": int(cfg.get("periods_per_year", 252)),
        "max_pending_steps": int(cfg.get("max_pending_steps", 5)),
        "params": eng.strategy.params, "risk": dict(eng.risk.cfg),
        "assumptions": {s: asdict(i) for s, i in sorted(eng.instruments.items())},    # spread/trượt giá/phí/swap giả định theo symbol
    }


def hashes(eff: dict) -> dict:
    return {"config_hash": chain.hash_obj(eff), "params_hash": chain.hash_obj({"strategy": eff["strategy"], "params": eff["params"]})}
