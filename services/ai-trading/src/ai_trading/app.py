from __future__ import annotations

import asyncio
import base64
import binascii
import csv
import gzip
import io
import json
import logging
import re
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse, Response
from tscommon import make_app

from . import __version__
from . import arena as arena_mod
from .config import Settings
from . import scenario_schema as sch
from .registry import BACKLOG_STATUS, ID_RE, Registry
from .scenario_store import ACTIVE, JOB_TYPES as SC_JOB_TYPES, MAX_ACTIVE_JOBS, Store

log = logging.getLogger("ai-trading")
Aud = Annotated[str, Query(pattern=r"^(master|client)$")]
SID = Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,47}$")
JOB_TYPES = set(SC_JOB_TYPES)
LEDGER_SRC = ("backtest_test", "backtest_dev", "paper")
DISCLAIMER = "Chỉ nghiên cứu và mô phỏng (paper); hệ thống không đặt lệnh thật. Quá khứ không đảm bảo tương lai."


RESERVED_IDS = {"KB-1", "KB-2", "KB-3", "KB-4"}   # id dành riêng (kịch bản Sell cố định), cấm kể cả khi registry rỗng


def _csv_cell(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "@", "\t", "\r") or (s[:1] == "-" and not re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", s)) else s


def _get_json(url: str, headers: dict) -> dict | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json", **headers}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (URL nội bộ từ cấu hình, chỉ GET)
            return json.loads(r.read(4_000_000))
    except Exception as e:  # noqa: BLE001
        log.warning("pattern-scan không khả dụng: %s", type(e).__name__)
        return None


def _hdrs() -> dict:
    try:
        from tscommon.internal_auth import internal_headers
        return internal_headers()
    except Exception:  # noqa: BLE001
        return {}


def create_app(settings: Settings | None = None, redis=None, fetch=None, llm=None) -> FastAPI:
    """fetch(path) -> dict|None dùng cho test (thay lời gọi pattern-scan)."""
    st = settings or Settings()
    app = make_app("ai-trading", __version__, internal_auth=True)
    reg = Registry(st.registry_dir, st.research_dir, st.state_dir)
    store: Store = reg.store
    app.state.redis = redis
    app.state.reg = reg
    from . import c2 as _c2  # C2: regime + đồng thuận + ngữ cảnh analyst (chỉ đọc)
    _c2.register(app, st, lambda path: scan(path), _hdrs)
    from . import d1 as _d1  # D1: guardrail + kill-switch (master) + xác minh hash-chain sổ paper
    _d1.register(app, lambda path: scan(path), lambda: r())

    async def r():
        if app.state.redis is None and st.redis_url:
            import redis.asyncio as aioredis
            app.state.redis = aioredis.from_url(st.redis_url, decode_responses=True)
        return app.state.redis

    async def scan(path: str) -> dict | None:
        if fetch is not None:
            return await fetch(path)
        return await asyncio.to_thread(_get_json, f"{st.scan_url}{path}", _hdrs())

    async def paper_scan(path: str) -> dict | None:
        if fetch is not None:
            return await fetch(path)
        return await asyncio.to_thread(_get_json, f"{st.paper_url}{path}", _hdrs())

    async def arena_data() -> dict:
        rc = await r()
        if rc is not None:
            try:
                c = await rc.get("aitrading:arena")
                j = json.loads(c) if c else None
                if isinstance(j, dict):
                    return j
            except Exception as e:  # noqa: BLE001
                log.warning("cache arena: %s", type(e).__name__)
        trades = await scan("/scan/trades/r")
        pf = await paper_scan("/paper/overview")
        names = {sid: x.get("name", sid) for sid, x in reg.load()["strategies"].items() if x.get("module") == "pattern" and sid.startswith("KB-")}
        out = arena_mod.build((trades or {}).get("items", []), names,
                              [a for a in (pf or {}).get("items", []) if isinstance(a, dict) and a.get("account_id") and not a.get("replay")])
        out["available"] = trades is not None
        stats = trades
        if rc is not None and stats is not None:
            try:
                await rc.set("aitrading:arena", json.dumps(out), ex=st.arena_ttl_s)
            except Exception as e:  # noqa: BLE001
                log.warning("cache arena: %s", type(e).__name__)
        return out

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @app.get("/ai/overview", tags=["ai-trading"])
    async def overview(audience: Aud = "master"):
        d = reg.load()
        cards = [reg.card(s) for s in d["strategies"].values() if audience == "master" or s.get("origin") != "user"]
        return {"strategies": cards, "warnings": reg.warnings(), "arena": (ar := await arena_data())["items"], "arena_meta": {k: ar.get(k) for k in ("note", "min_n", "ranked", "total_trades", "available")}, "updated_at": now(), "disclaimer": DISCLAIMER}

    @app.get("/ai/strategies", tags=["ai-trading"])
    async def strategies(audience: Aud = "master"):
        return [reg.card(s) for s in reg.load()["strategies"].values() if audience == "master" or s.get("origin") != "user"]

    @app.get("/ai/strategies/{sid}", tags=["ai-trading"])
    async def strategy(sid: Annotated[str, SID], audience: Aud = "master"):
        s = reg.load()["strategies"].get(sid)
        if not s or (s.get("origin") == "user" and audience != "master"):
            raise HTTPException(404, "không tìm thấy")
        return reg.detail(s, audience)

    @app.get("/ai/lab", tags=["ai-trading"])
    async def lab():
        d = reg.load()
        backlog = [{"id": b["id"], "idea": b.get("idea", ""), "module": b.get("module"), "status": b.get("status", "idea") if b.get("status") in BACKLOG_STATUS else "idea",
                    "doc": b.get("doc")} for b in d["backlog"]]
        exps = [{"id": e.get("id"), "params": e.get("params"), "snapshot_sha": e.get("snapshot_sha"), "result": e.get("result"), "date": str(e.get("date", ""))}
                for e in d["lab"]]
        # thí nghiệm backtest KB đã chạy: dựng từ hiện vật thật
        s = d["summary"]
        has_kb = any((x.get("source") or {}).get("type") == "pattern_sell" for x in d["strategies"].values())
        if s and has_kb:   # chỉ khi còn thẻ kịch bản KB trong registry (đã dọn 2026-10-15 -> trạng thái rỗng)
            info = None
            try:
                info = json.loads((reg.res / "ledger" / "ledger_info.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            sha = (info or {}).get("snapshot_manifest_sha256")
            for row in s.get("rows", []):
                exps.append({"id": "pattern_sell:" + row["label"].split(" ")[0].lower(), "params": {"scope": row["label"], "n": row["n"]},
                             "snapshot_sha": sha, "result": {"expectancy_r": row["exp_r"], "ci95": [row["ci_lo"], row["ci_hi"]], "p_vs_random": row.get("p_random")},
                             "date": (info or {}).get("generated", "")[:10]})
        return {"experiments": exps, "backlog": backlog}

    @app.get("/ai/arena", tags=["ai-trading"])
    async def arena():
        return {**await arena_data(), "updated_at": now(), "disclaimer": DISCLAIMER}

    @app.get("/ai/media/{kind}/{name}", tags=["ai-trading"])
    async def media(kind: Annotated[str, Path(pattern=r"^(charts|examples)$")], name: str):
        p = reg.media_path(kind, name)
        if not p:
            raise HTTPException(404, "không có ảnh")
        return Response(p.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})

    @app.get("/ai/ledger.csv", tags=["ai-trading"])
    async def ledger(strategy: Annotated[str, Query(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,47}$")],
                     source: Annotated[str, Query(pattern=r"^(backtest_test|backtest_dev|paper)$")] = "backtest_test"):
        s = reg.load()["strategies"].get(strategy)
        if not s:
            raise HTTPException(404, "không tìm thấy")
        src = s.get("source") or {}
        if s.get("origin") == "user":
            f = store.path(strategy)
            f = f / ("ledger_dev.csv" if source == "backtest_dev" else "ledger_test.csv") if f else None
            if source == "paper" or not f or not f.is_file():
                raise HTTPException(404, "chưa có sổ lệnh")
            return Response(f.read_bytes(), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="ledger-{strategy}-{source}.csv"', "Cache-Control": "private, no-store",
                                     "X-Content-Type-Options": "nosniff"})
        kb = src.get("kb") if src.get("type") == "pattern_sell" else None
        if not kb:
            raise HTTPException(404, "chiến lược chưa có sổ lệnh")
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        if source == "paper":
            data = await scan(f"/scan/trades?status=all&limit=500&pattern={kb}&include_replay=false")
            items = (data or {}).get("items", [])
            cols = ["id", "setup_id", "pattern", "symbol", "tf", "status", "opened_at", "closed_at", "entry", "sl", "result_r", "hash"]
            w.writerow(cols)
            for t in items:
                w.writerow([_csv_cell(t.get(c)) for c in cols])
        else:
            f = reg.res / "ledger" / "ledger_test.csv.gz"
            if not f.is_file():
                raise HTTPException(404, "chưa có hiện vật")
            with gzip.open(f, "rt", encoding="utf-8", newline="") as fh:
                rd = csv.reader(fh)
                head = next(rd, [])
                w.writerow(head)
                i = head.index("kb") if "kb" in head else None
                for row in rd:
                    if i is not None and row[i] == kb:
                        w.writerow([_csv_cell(c) for c in row])
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="ledger-{strategy}-{source}.csv"', "Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff"})

    # ---- Kịch bản mới + job nền (giai đoạn B). Chỉ master (gateway chặn); không có đường tới lệnh thật. ----
    def _decode_images(imgs) -> dict[str, bytes]:
        if imgs is None:
            return {}
        if not isinstance(imgs, dict) or len(imgs) > sch.MAX_IMAGES:
            raise HTTPException(422, f"images: map tên->base64, tối đa {sch.MAX_IMAGES} ảnh")
        out: dict[str, bytes] = {}
        for n, b64 in imgs.items():
            if not isinstance(n, str) or not sch.IMG_NAME.match(n) or not isinstance(b64, str) or len(b64) > sch.MAX_IMG_BYTES * 4 // 3 + 16:
                raise HTTPException(422, "ảnh: tên/kích thước không hợp lệ (tối đa 700 KB, png/jpg/webp)")
            try:
                data = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                raise HTTPException(422, f"ảnh {n}: base64 không hợp lệ") from None
            kind = sch.image_kind(data)
            ext = n.rsplit(".", 1)[1].lower().replace("jpeg", "jpg")
            if len(data) > sch.MAX_IMG_BYTES or kind is None or kind != ext:
                raise HTTPException(422, f"ảnh {n}: nội dung không khớp đuôi tệp hoặc quá lớn")
            out[n] = data
        return out

    @app.post("/ai/scenarios", tags=["ai-trading"], status_code=201)
    async def create_scenario(body: dict):
        text = body.get("yaml")
        try:
            sc = sch.validate(text, taken_ids=set(store.ids()) | {k.lower() for k in reg.load()["strategies"]} | set(reg.load()["strategies"]))
        except sch.SchemaError as e:
            raise HTTPException(422, str(e)) from None
        if sc["id"].lower() in {k.lower() for k in reg.load()["strategies"]} or sc["id"].upper() in RESERVED_IDS:
            raise HTTPException(409, "id trùng với chiến lược có sẵn")
        imgs = _decode_images(body.get("images"))
        if set(imgs) != set(sc["images"]):
            raise HTTPException(422, "danh sách `images` trong YAML phải khớp đúng các ảnh tải lên")
        for g in sc["golden"]:
            if g["image"] and g["image"] not in imgs:
                raise HTTPException(422, "golden.image không có trong ảnh tải lên")
        try:
            store.create(sc, imgs, "master")
        except FileExistsError:
            raise HTTPException(409, "id đã tồn tại") from None
        reg._sig = None
        return {"id": sc["id"], "phase": "created", "family_trials": store.family_size(sc["family"]),
                "message": "Đã lưu kịch bản. Bước tiếp: chạy thử detector + golden test, rồi backtest nền."}

    @app.get("/ai/scenarios/{sid}/images/{name}", tags=["ai-trading"])
    async def scenario_image(sid: Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")],
                             name: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,58}\.(png|jpg|jpeg|webp)$")]):
        p = store.image(sid, name)
        if not p:
            raise HTTPException(404, "không có ảnh")
        data = p.read_bytes()
        kind = sch.image_kind(data)
        if kind is None:
            raise HTTPException(404, "không có ảnh")
        mt = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[kind]
        return Response(data, media_type=mt, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                                                      "Content-Security-Policy": "default-src 'none'; sandbox"})

    def _enqueue(sid: str, typ: str, confirm, params: dict | None = None) -> dict:
        if typ not in JOB_TYPES:
            raise HTTPException(422, "type không hợp lệ (detector_test|backtest|final_test|scan_examples)")
        if not store.path(sid) or not store.scenario(sid):
            raise HTTPException(404, "không tìm thấy kịch bản")
        jobs = store.jobs()
        act = [j for j in jobs if j.get("status") in ACTIVE]
        if any(j.get("scenario_id") == sid for j in act):
            raise HTTPException(409, "kịch bản đang có job chưa xong")
        if len(act) >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, "hàng đợi đầy (tối đa 3 job); thử lại sau")
        res = store.result(sid)
        if typ == "final_test":
            if store.test_opened(sid):
                raise HTTPException(409, "test khoá của kịch bản này đã mở (chỉ mở 1 lần, không lặp lại)")
            if (res.get("dev") or {}).get("status") != "done":
                raise HTTPException(409, "cần chạy backtest dev xong trước khi mở test khoá")
            if confirm != sid:
                raise HTTPException(422, "cần xác nhận rõ ràng: confirm phải đúng bằng id kịch bản")
        elif store.test_opened(sid) and typ == "backtest":
            raise HTTPException(409, "đã mở test khoá: không chạy lại backtest dev (tránh chỉnh theo kết quả test)")
        return store.enqueue(sid, typ, "master", params if typ == "scan_examples" else None)

    from .classroom import api as _class_api   # P2b: AI Training Class (/class/*) — phòng/tin/nhãn/hồ sơ bền (SQLite trên /classroom)
    _class_api.register(app, st, store, reg, _enqueue, llm)
    from .classroom import ux_api as _class_ux   # UX Lớp học: canvas/độ rõ/mẫu/demo (docs/handoff/UX_API.md)
    _class_ux.register(app, st, app.state.class_store, llm)
    from .classroom import memory_api as _class_memory   # Bộ nhớ của AI (docs/handoff/MEMORY_API.md)
    _class_memory.register(app, st, app.state.class_store, llm)
    from .classroom import methods_api as _class_methods   # Phương pháp + Kế hoạch áp dụng (docs/handoff/METHOD_API.md)
    _class_methods.register(app, st, app.state.class_store, store, llm)
    from .classroom import rooms_trash as _class_trash   # Thùng rác phòng (docs/handoff/ROOMS_TRASH_API.md)
    _class_trash.register(app, st, app.state.class_store, store)
    from .classroom import option_rank as _class_orank   # xếp hạng option học được (M3)
    _class_orank.register(app, app.state.class_store)
    from .classroom import intent_api as _class_intent   # Nhận ý định tự nhiên + option gợi ý (docs/handoff/INTENT_API.md)
    _class_intent.register(app, st, app.state.class_store, llm)

    @app.post("/ai/scenarios/{sid}/jobs", tags=["ai-trading"], status_code=202)
    async def create_scenario_job(sid: Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")], body: dict):
        return _enqueue(sid, str(body.get("type", "backtest")), body.get("confirm"))

    @app.get("/ai/scenarios/{sid}/jobs", tags=["ai-trading"])
    async def scenario_jobs(sid: Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")]):
        if not store.path(sid):
            raise HTTPException(404, "không tìm thấy")
        return {"items": store.jobs(sid)[-20:]}

    @app.post("/ai/jobs", tags=["ai-trading"], status_code=202)
    async def create_job(body: dict):
        sid = body.get("strategy_id")
        if not isinstance(sid, str) or not sch.SC_ID.match(sid):
            raise HTTPException(404, "chỉ kịch bản người dùng nạp mới chạy được job nền (KB-1..4 đã có kết quả cố định)")
        return _enqueue(sid, str(body.get("type", "backtest")), body.get("confirm"))

    @app.get("/ai/jobs/{jid}", tags=["ai-trading"])
    async def get_job(jid: str):
        j = store.job(jid)
        if not j:
            raise HTTPException(404, "không tìm thấy")
        return JSONResponse(j)

    return app
