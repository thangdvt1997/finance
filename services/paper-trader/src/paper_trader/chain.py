"""Hash-chain cho journal mô phỏng (tamper-evident): mỗi bản ghi chứa hash(bản ghi trước + nội dung).
Phạm vi: lệnh (bất biến), trạng thái lệnh, fill, sự kiện, equity — theo TỪNG tài khoản, bảng phụ `paper_chain` (append-only).
Mục tiêu: PHÁT HIỆN sửa/xoá/chèn sau này; KHÔNG chống được kẻ có quyền superuser tính lại toàn bộ chuỗi — vì thế có `anchor`
(neo `seq:row_hash` lưu ngoài DB, vd Redis) để phát hiện viết lại lịch sử.

Quy ước chuẩn hoá (BẮT BUỘC giống nhau lúc ghi và lúc xác minh): thời gian -> ISO UTC; số thực nguyên -> int; NaN/Inf -> chuỗi; JSON khoá sắp xếp."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Iterable

from .models import iso, parse_ts

KINDS = ("order", "order_status", "fill", "event", "equity")
_RANK = {k: i for i, k in enumerate(KINDS)}


def norm(x: Any) -> Any:
    """Chuẩn hoá giá trị về dạng JSON ổn định (giống nhau cho dữ liệu vừa tạo và dữ liệu đọc lại từ PostgreSQL)."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, datetime):
        return iso(x)
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        if math.isinf(x):
            return "Infinity" if x > 0 else "-Infinity"
        return int(x) if x.is_integer() else x
    if isinstance(x, dict):
        return {str(k): norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    return str(x)


def canonical(o: Any) -> str:
    return json.dumps(norm(o), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def hash_obj(o: Any) -> str:
    return sha(canonical(o))


def genesis(account_id: str) -> str:
    return sha(f"genesis:{account_id}")


def row_hash(prev_hash: str, seq: int, kind: str, ref: str, content_hash: str) -> str:
    return sha(f"{prev_hash}|{seq}|{kind}|{ref}|{content_hash}")


def _ts(v: Any) -> str | None:
    return iso(parse_ts(v)) if v not in (None, "") else None


def _f(v: Any) -> Any:
    return None if v is None else float(v)


# ------------------------------------------------------------------ nội dung chuẩn theo loại (nhận dict hoặc đối tượng)
def _g(o: Any, k: str, default: Any = None) -> Any:
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def c_order(account_id: str, o: Any) -> dict:
    return {"client_order_id": _g(o, "client_order_id"), "account_id": account_id, "symbol": _g(o, "symbol"), "side": _g(o, "side"),
            "qty": _f(_g(o, "qty")), "kind": _g(o, "kind"), "target_weight": _f(_g(o, "target_weight")), "ref_price": _f(_g(o, "ref_price")),
            "decision_ts": _ts(_g(o, "decision_ts")), "eligible_from": _ts(_g(o, "eligible_from"))}


def c_order_status(o: Any) -> dict:
    return {"client_order_id": _g(o, "client_order_id"), "status": _g(o, "status"), "reason": _g(o, "reason") or ""}


def c_fill(account_id: str, f: Any) -> dict:
    return {"client_order_id": _g(f, "client_order_id"), "account_id": account_id, "symbol": _g(f, "symbol"), "side": _g(f, "side"),
            "qty": _f(_g(f, "qty")), "ts": _ts(_g(f, "ts")), "ref_price": _f(_g(f, "ref_price")), "price": _f(_g(f, "price")),
            "spread_cost": _f(_g(f, "spread_cost")), "slippage_cost": _f(_g(f, "slippage_cost")), "commission": _f(_g(f, "commission")),
            "tax": _f(_g(f, "tax")), "realized_pnl": _f(_g(f, "realized_pnl")), "q2b": _f(_g(f, "q2b"))}


def c_event(account_id: str, e: Any) -> dict:
    data = _g(e, "data") or {}
    if isinstance(data, str):
        data = json.loads(data)
    key = _g(e, "event_key") if _g(e, "event_key") is not None else _g(e, "key")
    # qua json một vòng: giống những gì jsonb trả về (tuple->list, datetime->str)
    data = json.loads(json.dumps(data, default=str, allow_nan=False))
    return {"account_id": account_id, "ts": _ts(_g(e, "ts")), "type": _g(e, "type"), "severity": _g(e, "severity"),
            "message": _g(e, "message"), "data": data, "event_key": key}


def c_equity(account_id: str, e: Any) -> dict:
    return {"account_id": account_id, "ts": _ts(_g(e, "ts")), "equity": _f(_g(e, "equity")), "cash": _f(_g(e, "cash")),
            "gross_exposure": _f(_g(e, "gross_exposure")), "net_exposure": _f(_g(e, "net_exposure")),
            "drawdown": _f(_g(e, "drawdown")), "swap_cost": _f(_g(e, "swap_cost"))}


def item(kind: str, ref: str, content: dict, ts: Any) -> dict:
    return {"kind": kind, "ref": ref, "content_hash": hash_obj(content), "ts": parse_ts(ts)}


def items_from_step(account_id: str, res: Any) -> list[dict]:
    """Các mục chuỗi phát sinh từ một StepResult (thứ tự cố định: lệnh mới, cập nhật lệnh, fill, equity). Sự kiện: items_from_events."""
    out: list[dict] = []
    for o in res.new_orders:
        out.append(item("order", o.client_order_id, c_order(account_id, o), o.decision_ts))
        out.append(item("order_status", f"{o.client_order_id}#{o.status}", c_order_status(o), o.decision_ts))
    for o in res.order_updates:
        out.append(item("order_status", f"{o.client_order_id}#{o.status}", c_order_status(o), res.close_ts))
    for f in res.fills:
        out.append(item("fill", f.client_order_id, c_fill(account_id, f), f.ts))
    out.append(item("equity", iso(res.close_ts), c_equity(account_id, {"ts": res.close_ts, "equity": res.equity, "cash": res.cash,
                                                                       "gross_exposure": res.gross, "net_exposure": res.net,
                                                                       "drawdown": res.drawdown, "swap_cost": res.swap_step}), res.close_ts))
    return out


def items_from_events(account_id: str, events: Iterable[dict]) -> list[dict]:
    return [item("event", e["key"], c_event(account_id, e), e["ts"]) for e in events]


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: (i["ts"], _RANK[i["kind"]], i["ref"]))


def link(account_id: str, tail_seq: int, tail_hash: str | None, items: list[dict]) -> list[dict]:
    """Gắn seq/prev_hash/row_hash cho `items` (đã lọc trùng) nối tiếp sau (tail_seq, tail_hash)."""
    prev = tail_hash or genesis(account_id)
    out = []
    seq = tail_seq
    for it in items:
        seq += 1
        h = row_hash(prev, seq, it["kind"], it["ref"], it["content_hash"])
        out.append({"account_id": account_id, "seq": seq, "kind": it["kind"], "ref": it["ref"], "ts": it["ts"],
                    "content_hash": it["content_hash"], "prev_hash": prev, "row_hash": h})
        prev = h
    return out


# ------------------------------------------------------------------ xác minh
def verify(account_id: str, entries: list[dict], live: dict[str, dict[str, str]], live_status: dict[str, str],
           anchor: dict | None = None, max_problems: int = 50) -> dict:
    """entries: các dòng paper_chain. live: {kind: {ref: content_hash}} tính LẠI từ bảng hiện tại (không gồm order_status).
    live_status: {client_order_id: status hiện tại}. anchor: {seq, hash} đã neo ở nơi khác (hoặc None).
    Trả báo cáo: ok + các vấn đề theo loại (link_break, bad_hash, seq_gap, modified, deleted, unchained, status_mismatch, anchor_mismatch)."""
    problems: list[dict] = []

    def add(t: str, **kw: Any) -> None:
        problems.append({"type": t, **kw})

    ents = sorted(entries, key=lambda e: e["seq"])
    prev = genesis(account_id)
    expect_seq = 1
    chained: dict[str, set[str]] = {k: set() for k in KINDS}
    last_status: dict[str, str] = {}
    by_seq: dict[int, str] = {}
    for e in ents:
        if e["seq"] != expect_seq:
            add("seq_gap", seq=e["seq"], expected=expect_seq)
            expect_seq = e["seq"]
        if e["prev_hash"] != prev:
            add("link_break", seq=e["seq"])
        if row_hash(e["prev_hash"], e["seq"], e["kind"], e["ref"], e["content_hash"]) != e["row_hash"]:
            add("bad_hash", seq=e["seq"], kind=e["kind"], ref=e["ref"])
        prev = e["row_hash"]
        expect_seq += 1
        by_seq[e["seq"]] = e["row_hash"]
        kind, ref = e["kind"], e["ref"]
        chained.setdefault(kind, set()).add(ref)
        if kind == "order_status":
            coid, _, st = ref.rpartition("#")
            last_status[coid] = st
        else:
            cur = live.get(kind, {}).get(ref)
            if cur is None:
                add("deleted", seq=e["seq"], kind=kind, ref=ref)
            elif cur != e["content_hash"]:
                add("modified", seq=e["seq"], kind=kind, ref=ref)
    for kind in ("order", "fill", "event", "equity"):
        for ref in live.get(kind, {}):
            if ref not in chained.get(kind, set()):
                add("unchained", kind=kind, ref=ref)
    for coid, st in live_status.items():
        if last_status.get(coid) is None:
            add("unchained", kind="order_status", ref=coid)
        elif last_status[coid] != st:
            add("status_mismatch", ref=coid, chained=last_status[coid], current=st)
    anchor_ok = None
    if anchor and anchor.get("seq") is not None:
        h = by_seq.get(int(anchor["seq"]))
        anchor_ok = h == anchor.get("hash")
        if not anchor_ok:
            add("anchor_mismatch", seq=int(anchor["seq"]), expected=anchor.get("hash"), actual=h)
    counts: dict[str, int] = {}
    for p in problems:
        counts[p["type"]] = counts.get(p["type"], 0) + 1
    head = ents[-1] if ents else None
    return {"account_id": account_id, "ok": not problems, "entries": len(ents),
            "head": {"seq": head["seq"], "hash": head["row_hash"]} if head else None,
            "genesis": ents[0]["row_hash"] if ents else None, "anchor_ok": anchor_ok,
            "problem_counts": counts, "problems": problems[:max_problems], "problems_truncated": len(problems) > max_problems,
            "scope": {k: len(chained.get(k, ())) for k in KINDS}}
