"""Mô phỏng lệnh PAPER cho tín hiệu Sell đã kích hoạt — thuần Python, tất định, KHÔNG có đường tới lệnh thật.

Quy tắc (bảo thủ, ghi trong docs/PATTERNS_SELL.md §Live):
- Vào lệnh: giá đóng nến kích hoạt (= levels.entry) tại thời điểm nến đóng; chi phí khứ hồi `cost_bps` trừ vào kết quả (đơn vị R).
- 3 phần bằng nhau, chốt ở TP 1R/2R/3R (levels tp_1r/tp_2r/tp_3r), chung SL (levels.sl). Không dời SL.
- Chỉ xét nến ĐÃ ĐÓNG cùng khung, bắt đầu từ nến SAU nến kích hoạt. Trong 1 nến chạm cả SL và TP -> coi SL trước (bảo thủ).
  Mở cửa nhảy qua SL -> khớp ở giá mở (xấu hơn); mở cửa đã dưới TP -> khớp ở giá mở.
- Hết hạn `max_hold_bars` nến -> đóng phần còn lại ở giá đóng cửa nến đó.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def cost_bps_for(symbol: str, table: dict) -> float:
    if symbol in table:
        return float(table[symbol])
    for k, v in table.items():
        if k.endswith(":") and symbol.startswith(k):
            return float(v)
    return float(table.get("default", 2.0))


def open_trade(payload: dict, cost_bps: float, replay: bool) -> dict | None:
    lv = payload.get("levels") or {}
    try:
        entry, sl = float(lv["entry"]), float(lv["sl"])
    except (KeyError, TypeError, ValueError):
        return None
    r = sl - entry
    if not (r > 0):
        return None
    tps = [float(lv.get(f"tp_{m}r", entry - m * r)) for m in (1, 2, 3)]
    cost = entry * cost_bps / 1e4
    return {
        "setup_id": payload["setup_id"], "pattern": payload["pattern"], "symbol": payload["symbol"], "tf": payload["tf"], "side": "sell",
        "opened_at": payload["ts"], "entry": entry, "sl": sl, "r": r, "tp": tps, "status": "open", "closed_at": None,
        "legs": [{"tp": tp, "status": "open", "exit": None, "exit_ts": None, "r": None} for tp in tps],
        "cost_r": round(cost / r, 4), "result_r": None, "mfe_r": 0.0, "mae_r": 0.0, "bars_held": 0, "last_bar_ts": payload["bar_ts"],
        "replay": bool(replay),
    }


def step(t: dict, bar: dict, close_ts: str, max_hold_bars: int) -> bool:
    """Áp 1 nến đã đóng (bar: ts_open ISO, o,h,l,c). Trả True nếu lệnh vừa đóng hoàn toàn."""
    if t["status"] != "open":
        return False
    e, sl, r = t["entry"], t["sl"], t["r"]
    o, h, lo, c = float(bar["o"]), float(bar["h"]), float(bar["l"]), float(bar["c"])
    t["bars_held"] += 1
    t["last_bar_ts"] = bar["ts"]
    t["mfe_r"] = round(max(t["mfe_r"], (e - lo) / r), 4)
    t["mae_r"] = round(max(t["mae_r"], (h - e) / r), 4)
    for lg in t["legs"]:
        if lg["status"] != "open":
            continue
        if h >= sl:                                  # SL trước (bảo thủ)
            px = max(sl, o)
            lg.update(status="sl", exit=px, exit_ts=close_ts, r=round((e - px) / r, 4))
        elif lo <= lg["tp"]:
            px = min(lg["tp"], o)
            lg.update(status="tp", exit=px, exit_ts=close_ts, r=round((e - px) / r, 4))
    if t["bars_held"] >= max_hold_bars:
        for lg in t["legs"]:
            if lg["status"] == "open":
                lg.update(status="timeout", exit=c, exit_ts=close_ts, r=round((e - c) / r, 4))
    if all(lg["status"] != "open" for lg in t["legs"]):
        t["status"] = "closed"
        t["closed_at"] = close_ts
        t["result_r"] = round(sum(lg["r"] for lg in t["legs"]) / len(t["legs"]) - t["cost_r"], 4)
        return True
    return False


# ------------------------------------------------------------------ sổ cái hash-chain (append-only)
GENESIS = "0" * 64


def canon(obj: Any) -> str:
    def d(v):
        return v.isoformat() if isinstance(v, datetime) else v
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=d)


def chain_hash(prev: str, kind: str, ref: str, content: dict) -> str:
    return hashlib.sha256(f"{prev}|{kind}|{ref}|{canon(content)}".encode()).hexdigest()


def verify(rows: list[dict], anchor: dict | None = None) -> dict:
    """rows theo seq tăng dần: {seq, kind, ref, content, prev_hash, hash}. Phát hiện SỬA nội dung, XOÁ/CHÈN giữa chuỗi (đứt prev_hash).
    `anchor` = {"n": số bản ghi, "hash": hash bản ghi thứ n} lưu NGOÀI DB: phát hiện cắt đuôi / viết lại lịch sử (hash tại n khác)."""
    prev = GENESIS
    for i, r in enumerate(rows):
        content = r["content"] if isinstance(r["content"], dict) else json.loads(r["content"])
        if r["seq"] != i + 1 or r["prev_hash"] != prev or chain_hash(prev, r["kind"], r["ref"], content) != r["hash"]:
            return {"ok": False, "n": len(rows), "broken_at": r["seq"], "head": prev, "reason": "hash/seq không khớp (sửa hoặc xoá)"}
        prev = r["hash"]
    out = {"ok": True, "n": len(rows), "head": prev}
    if anchor and anchor.get("n"):
        n = int(anchor["n"])
        if n > len(rows):
            return {"ok": False, "n": len(rows), "head": prev, "broken_at": len(rows) + 1, "reason": f"chuỗi ngắn hơn neo ({len(rows)} < {n}): bị cắt đuôi"}
        if rows[n - 1]["hash"] != anchor.get("hash"):
            return {"ok": False, "n": len(rows), "head": prev, "broken_at": n, "reason": "hash tại vị trí neo khác: lịch sử bị viết lại"}
        out["anchored"] = True
    return out


# ------------------------------------------------------------------ thống kê (đơn vị R)
def _agg(ts: list[dict]) -> dict:
    closed = [t for t in ts if t["status"] == "closed" and t.get("result_r") is not None]
    rs = [float(t["result_r"]) for t in closed]
    wins, losses = [x for x in rs if x > 0], [x for x in rs if x <= 0]
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in rs:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n_closed": len(closed), "n_open": sum(1 for t in ts if t["status"] == "open"), "wins": len(wins), "losses": len(losses),
            "winrate": round(len(wins) / len(rs), 4) if rs else None, "avg_r": round(sum(rs) / len(rs), 4) if rs else None,
            "sum_r": round(sum(rs), 4), "pf": round(sum(wins) / -sum(losses), 3) if losses and sum(losses) < 0 else None,
            "max_dd_r": round(dd, 4)}


def stats(trades: list[dict], include_replay: bool = False) -> dict:
    ts = [t for t in trades if include_replay or not t.get("replay")]
    ts.sort(key=lambda t: str(t.get("closed_at") or t.get("opened_at")))
    out = {"overall": _agg(ts)}
    for key, name in (("pattern", "by_pattern"), ("tf", "by_tf"), ("symbol", "by_symbol")):
        groups: dict[str, list] = {}
        for t in ts:
            groups.setdefault(t[key], []).append(t)
        out[name] = [{key: k, **_agg(v)} for k, v in sorted(groups.items())]
    eq, cum = [], 0.0
    for t in ts:
        if t["status"] == "closed" and t.get("result_r") is not None:
            cum += float(t["result_r"])
            eq.append({"t": str(t["closed_at"]), "cum_r": round(cum, 4)})
    out["equity"] = eq
    n = out["overall"]["n_closed"]
    out["note"] = ("Mẫu nhỏ (n<30): chưa có ý nghĩa thống kê." if n < 30 else "Kết quả mô phỏng (paper), quá khứ không đảm bảo tương lai.") + \
        " Đơn vị R = khoảng cách Entry->SL; đã trừ chi phí giả định. Không gồm lệnh replay."
    return out
