"""Giai đoạn D1: guardrail rủi ro (kill-switch do master bật/tắt) + xác minh hash-chain sổ paper. READ-ONLY/PAPER: không đường đặt lệnh.
Cờ kill-switch nằm ở Redis `aitrading:killswitch` (JSON {on,by,at,reason}); pattern-scan ĐỌC cờ này trước khi mở lệnh paper (mặc định: không có cờ = không chặn,
guardrail áp dụng mặc định cho sổ paper). Chỉ master ghi được (kiểm ở api-gateway: master + Origin + CSRF)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, HTTPException
from tscommon.sources import scrub_sources

log = logging.getLogger("ai-trading.d1")
KILL_KEY = "aitrading:killswitch"        # phải trùng pattern_scan.guardrail.KILL_KEY (test khoá cặp này)
ANCHOR_KEY = "aitrading:ledger_anchor"


def register(app: FastAPI, scan: Callable, redis_getter: Callable) -> None:
    async def kill_state() -> dict:
        rc = await redis_getter()
        if rc is None:
            return {"on": False, "known": False}
        try:
            raw = await rc.get(KILL_KEY)
        except Exception as e:  # noqa: BLE001
            log.warning("kill-switch đọc lỗi: %s", type(e).__name__)
            return {"on": False, "known": False}
        if not raw:
            return {"on": False, "known": True}
        try:
            d = json.loads(raw)
            return {"on": bool(d.get("on")), "known": True, "by": d.get("by"), "at": d.get("at"), "reason": d.get("reason")}
        except ValueError:
            return {"on": True, "known": True, "reason": "cờ không đọc được -> coi như BẬT"}

    @app.get("/ai/guardrail", tags=["ai-trading"])
    async def guardrail():
        g = await scan("/scan/guardrail")
        ks = await kill_state()
        if g is None:
            return {"available": False, "kill_switch": ks, "reason": "Dịch vụ quét chưa sẵn sàng; chưa đọc được trạng thái guardrail."}
        g["kill_switch"] = ks                      # cờ Redis là nguồn sự thật (pattern-scan đọc đúng cờ này)
        g["available"] = True
        g["ledger"] = await _verify()
        g["notes"] = ["Guardrail ÁP DỤNG mặc định cho sổ paper; chỉ chặn tín hiệu live mới (không đụng lệnh đã mở).",
                      "Nguồn phụ lỗi (cờ/lịch tin) -> vẫn cho qua nhưng hiện ở mục 'suy giảm' (đây là paper, không phải tiền thật)."]
        return g

    @app.post("/ai/guardrail/killswitch", tags=["ai-trading"])
    async def killswitch(body: dict):
        if not isinstance(body, dict) or set(body) - {"on", "reason"} or not isinstance(body.get("on"), bool):
            raise HTTPException(422, "cần {on: true|false, reason?: chuỗi}")
        reason = str(body.get("reason") or "")[:200]
        if reason and scrub_sources(reason) != reason:
            raise HTTPException(422, "lý do chứa tên nguồn dữ liệu")
        rc = await redis_getter()
        if rc is None:
            raise HTTPException(503, "Redis chưa sẵn sàng")
        rec = {"on": body["on"], "by": "master", "at": datetime.now(timezone.utc).isoformat(), "reason": reason}
        await rc.set(KILL_KEY, json.dumps(rec, ensure_ascii=False))
        log.warning("kill-switch paper -> %s", "BẬT" if rec["on"] else "TẮT")
        return {"kill_switch": {"on": rec["on"], "known": True, "by": rec["by"], "at": rec["at"], "reason": reason}}

    async def _verify() -> dict:
        """Hash-chain sổ paper + neo ngoài DB (Redis): neo chỉ tiến lên khi chuỗi hợp lệ; chuỗi ngắn đi/đổi hash tại neo -> ok=false."""
        rc = await redis_getter()
        anc = None
        if rc is not None:
            try:
                raw = await rc.get(ANCHOR_KEY)
                anc = json.loads(raw) if raw else None
            except Exception:  # noqa: BLE001
                anc = None
        q = f"?anchor_n={int(anc['n'])}&anchor_hash={anc['hash']}" if anc and anc.get("n") and anc.get("hash") else ""
        v = await scan("/scan/ledger/verify" + q)
        if v is None:
            return {"available": False, "ok": None, "reason": "Chưa đọc được sổ lệnh paper."}
        v["available"] = True
        if v.get("ok") and rc is not None and v.get("n") and (anc is None or int(v["n"]) >= int(anc.get("n") or 0)):
            try:
                await rc.set(ANCHOR_KEY, json.dumps({"n": v["n"], "hash": v["head"], "at": datetime.now(timezone.utc).isoformat()}))
            except Exception:  # noqa: BLE001
                pass
        v["anchored"] = bool(anc) and bool(v.get("ok"))
        return v

    @app.get("/ai/ledger/verify", tags=["ai-trading"])
    async def ledger_verify():
        return await _verify()
