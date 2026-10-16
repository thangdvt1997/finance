from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from tscommon import Bus, make_app

from . import __version__, annot, paper
from .config import Settings, load_cfg
from .notify import Ntfy
from .store import MemoryStore, _dt
from .guardrail import KILL_KEY
from .worker import TF_SECONDS, Scanner, consume_loop, periodic

log = logging.getLogger("pattern-scan")
DISCLAIMER = "Tín hiệu kỹ thuật chỉ để tham khảo/mô phỏng (paper), không phải khuyến nghị đầu tư; hệ thống không đặt lệnh."
CLIENT_STATES = ("armed", "triggered")
NAMES = {"KB-1": "Hồi - giảm nhẹ - 2 đỉnh giảm dần", "KB-2": "Nêm/tam giác sau hồi 50%", "KB-3": "Đi ngang + vai-đầu-vai",
         "KB-4": "Tiếp diễn sau phá hộp"}
SYM = r"^[A-Za-z0-9:._\-]{1,32}$"
TF = r"^(M1|M5|M15|M30|H1|H4|D1)$"
EX_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")
Aud = Annotated[str, Query(pattern=r"^(master|client)$")]


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _img(eid: int | None) -> str | None:
    return f"/v1/patterns/media/{eid}.png" if eid else None


def _trade_out(t: dict | None) -> dict | None:
    if not t:
        return None
    d = {k: _iso(v) for k, v in t.items() if k not in ("open_hash",)}
    d["hash"] = t.get("open_hash")
    return d


def group_setups(events: list[dict], trades: list[dict], now: datetime, cfg: dict, view: str, audience: str) -> list[dict]:
    by: dict[tuple, list[dict]] = {}
    for e in events:
        by.setdefault((e["setup_id"], e["symbol"], e["tf"]), []).append(e)
    tr = {(t["setup_id"], t["symbol"], t["tf"]): t for t in trades}
    rank = {"forming": 1, "armed": 2, "triggered": 3, "invalid": 3}
    out = []
    for key, evs in by.items():
        evs.sort(key=lambda e: (e["bar_ts"], rank.get(e["state"], 0), e["id"]))
        latest = evs[-1]
        if audience == "client":
            if latest["state"] == "invalid":
                continue
            evs = [e for e in evs if e["state"] in CLIENT_STATES]
            if not evs:
                continue
            latest = evs[-1]
        t = tr.get(key)
        st = latest["state"]
        age_bars = (now - latest["ts"]).total_seconds() / TF_SECONDS.get(latest["tf"], 900)
        active = (st in ("forming", "armed") and age_bars <= float(cfg["stale_bars"].get(st, 100))) or \
                 (st == "triggered" and t is not None and t["status"] == "open")
        if (view == "active" and not active) or (view == "history" and active):
            continue
        img_ev = next((e for e in reversed(evs) if e.get("has_image")), None)
        item = {"setup_id": latest["setup_id"], "pattern": latest["pattern"], "name": NAMES.get(latest["pattern"], latest["pattern"]),
                "symbol": latest["symbol"], "tf": latest["tf"], "side": "sell", "state": st, "score": float(latest["score"]),
                "first_ts": _iso(evs[0]["ts"]), "last_ts": _iso(latest["ts"]), "bar_ts": _iso(latest["bar_ts"]),
                "levels": latest["levels"], "steps": latest["steps"], "reason": latest.get("reason"), "stale": not active and st in ("forming", "armed"),
                "image": _img(img_ev["id"]) if img_ev else None,
                "events": [{"id": e["id"], "state": e["state"], "ts": _iso(e["ts"]), "bar_ts": _iso(e["bar_ts"]), "score": float(e["score"]),
                            "image": _img(e["id"]) if e.get("has_image") else None, "live": e.get("live")} for e in evs],
                "trade": _trade_out(t)}
        if audience == "client":
            item.pop("reason", None)
        out.append(item)
    order = {"triggered": 0, "armed": 1, "forming": 2, "invalid": 3}
    if view == "active":
        out.sort(key=lambda x: x["last_ts"], reverse=True)
        out.sort(key=lambda x: order.get(x["state"], 9))
    else:
        out.sort(key=lambda x: x["last_ts"], reverse=True)
    return out


def create_app(settings: Settings | None = None, scanner: Scanner | None = None) -> FastAPI:
    settings = settings or Settings()
    app = make_app("pattern-scan", __version__, internal_auth=True)  # X-Internal-Token (tscommon.internal_auth)
    app.state.scanner = scanner

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop, tasks, closers = asyncio.Event(), [], []
        if _app.state.scanner is None:
            cfg = load_cfg(settings.config_path)
            if settings.enabled and settings.read_url and settings.write_url:
                from .store import PgStore
                st = await PgStore.connect(settings.read_url, settings.write_url)
                closers.append(st.close)
            else:
                log.warning("thiếu DATABASE_URL/PSCAN_DB_RW_URL hoặc ENABLED=false: chạy RAM, không quét")
                st = MemoryStore()
            nt = Ntfy(settings.ntfy_url, settings.ntfy_topic, settings.ntfy_token, settings.click_url, int(cfg["notify"].get("max_per_min", 20)))
            _app.state.scanner = sc = Scanner(cfg, st, nt)
            if settings.enabled and not isinstance(st, MemoryStore):
                bus = Bus.from_url(settings.redis_url)
                closers.append(bus.r.aclose)
                sc.kill_get = lambda: bus.r.get(KILL_KEY)
                tasks.append(asyncio.create_task(consume_loop(sc, bus, settings.consumer, stop)))
                tasks.append(asyncio.create_task(periodic(sc.monitor, float(cfg["monitor_interval_s"]), stop, 15)))
                tasks.append(asyncio.create_task(periodic(sc.backfill, float(cfg["backfill"].get("interval_s", 600)), stop, 3)))
        try:
            yield
        finally:
            stop.set()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for c in closers:
                with contextlib.suppress(Exception):
                    await c()

    app.router.lifespan_context = lifespan

    def sc() -> Scanner:
        return app.state.scanner

    @app.get("/status", tags=["ops"])
    async def status():
        s = sc()
        return {"monitor": s.last, "notify_recent": len(s.ntfy.outbox) if s.ntfy else 0}

    @app.get("/scan/setups", tags=["scan"], summary="Setup kịch bản (gộp sự kiện) + ảnh + lệnh paper")
    async def setups(view: Annotated[str, Query(pattern=r"^(active|history|all)$")] = "active",
                     symbol: Annotated[str | None, Query(pattern=SYM)] = None, tf: Annotated[str | None, Query(pattern=TF)] = None,
                     pattern: Annotated[str | None, Query(pattern=r"^KB-[0-9]{1,2}$")] = None,
                     state: Annotated[str | None, Query(pattern=r"^(forming|armed|triggered|invalid)$")] = None,
                     days: Annotated[int, Query(ge=1, le=90)] = 14, limit: Annotated[int, Query(ge=1, le=200)] = 100,
                     audience: Aud = "master"):
        s = sc()
        now = s.clock()
        evs = await s.store.events(now - timedelta(days=days), 5000)
        evs = [e for e in evs if (not symbol or e["symbol"] == symbol) and (not tf or e["tf"] == tf) and (not pattern or e["pattern"] == pattern)]
        items = group_setups(evs, await s.store.trades(None, 2000), now, s.cfg, view, audience)
        if state:
            items = [i for i in items if i["state"] == state]
        return {"as_of": now.isoformat(), "view": view, "items": items[:limit], "disclaimer": DISCLAIMER}

    @app.get("/scan/setup", tags=["scan"], summary="Chi tiết 1 setup + điểm đánh dấu cho biểu đồ")
    async def setup(setup_id: Annotated[str, Query(min_length=4, max_length=80, pattern=r"^KB-[0-9A-Za-z:_\-]+$")],
                    symbol: Annotated[str, Query(pattern=SYM)], tf: Annotated[str, Query(pattern=TF)], audience: Aud = "master"):
        s = sc()
        now = s.clock()
        evs = [e for e in await s.store.events(now - timedelta(days=90), 20000)
               if e["setup_id"] == setup_id and e["symbol"] == symbol and e["tf"] == tf]
        items = group_setups(evs, await s.store.trades(None, 5000), now, s.cfg, "all", audience)
        if not items:
            raise HTTPException(404, "không tìm thấy")
        it = items[0]
        last_ev = max((e for e in evs if any(x["id"] == e["id"] for x in it["events"])), key=lambda e: (e["bar_ts"], e["id"]))
        p = {**last_ev, "bar_ts": _iso(last_ev["bar_ts"]), "ts": _iso(last_ev["ts"])}
        _, marks = await s.render_marks(p)
        dt = TF_SECONDS.get(tf, 900)
        anchors = [t for t in annot.anchor_times(setup_id)]
        frm = (min(anchors) if anchors else _dt(it["bar_ts"]) - timedelta(seconds=dt * 120)) - timedelta(seconds=dt * 40)
        to = _dt(it["bar_ts"])
        if it.get("trade") and it["trade"].get("closed_at"):
            to = _dt(it["trade"]["closed_at"])
        elif it.get("trade"):
            to = now
        return {"item": it, "marks": marks, "window": {"from": frm.isoformat(), "to": to.isoformat()}, "disclaimer": DISCLAIMER}

    @app.get("/scan/media/{eid}.png", tags=["scan"], summary="Ảnh PNG của 1 sự kiện")
    async def media(eid: int, audience: Aud = "master"):
        m = await sc().store.media(eid)
        if not m or (audience == "client" and m[1] not in CLIENT_STATES):
            raise HTTPException(404, "không có ảnh")
        return Response(m[0], media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/scan/trades", tags=["scan"], summary="Lệnh PAPER của tín hiệu đã kích hoạt")
    async def trades(status: Annotated[str, Query(pattern=r"^(open|closed|all)$")] = "all",
                     pattern: Annotated[str | None, Query(pattern=r"^KB-[0-9]{1,2}$")] = None,
                     symbol: Annotated[str | None, Query(pattern=SYM)] = None, limit: Annotated[int, Query(ge=1, le=500)] = 200,
                     include_replay: bool = True):
        rows = await sc().store.trades(None if status == "all" else status, 5000)
        rows = [r for r in rows if (not pattern or r["pattern"] == pattern) and (not symbol or r["symbol"] == symbol)
                and (include_replay or not r.get("replay"))]
        return {"items": [_trade_out(r) for r in rows[:limit]], "disclaimer": DISCLAIMER}

    @app.get("/scan/trades/r", tags=["scan"], summary="Chuỗi R của lệnh paper đã đóng (gọn, không replay) cho arena")
    async def trades_r():
        rows = await sc().store.trades("closed", 20000)
        out = [{"pattern": r["pattern"], "closed_at": _iso(r.get("closed_at")), "opened_at": _iso(r.get("opened_at")),
                "result_r": r.get("result_r")} for r in rows if not r.get("replay") and r.get("result_r") is not None]
        out.sort(key=lambda x: x["closed_at"])
        return {"items": out}

    @app.get("/scan/stats", tags=["scan"], summary="Thống kê paper theo R (mặc định bỏ lệnh replay)")
    async def stats(include_replay: bool = False):
        s = sc()
        rows = await s.store.trades(None, 20000)
        out = paper.stats(rows, include_replay)
        out["ledger"] = paper.verify(await s.store.ledger_rows())
        out["n_replay"] = sum(1 for r in rows if r.get("replay"))
        out["as_of"] = s.clock().isoformat()
        out["disclaimer"] = DISCLAIMER
        return out

    @app.get("/scan/ledger/verify", tags=["scan"], summary="Xác minh hash-chain sổ paper (+ neo ngoài DB để phát hiện cắt đuôi)")
    async def ledger_verify(anchor_n: Annotated[int, Query(ge=0, le=100000000)] = 0,
                            anchor_hash: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None):
        anc = {"n": anchor_n, "hash": anchor_hash} if anchor_n and anchor_hash else None
        return paper.verify(await sc().store.ledger_rows(), anc)

    @app.get("/scan/guardrail", tags=["scan"], summary="Trạng thái guardrail rủi ro của sổ paper (kill-switch, lỗ ngày, tin, cỡ vị thế)")
    async def guardrail_state():
        return await sc().guard.state(sc().clock())

    def _examples_fs() -> list[dict]:
        d = Path(settings.examples_dir)
        out = []
        if d.is_dir():
            for j in sorted(d.glob("*.json")):
                if not EX_ID.match(j.stem) or not (d / f"{j.stem}.png").is_file():
                    continue
                try:
                    meta = json.loads(j.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                out.append({"id": j.stem, "kind": str(meta.get("kind", "golden")), "pattern": meta.get("pattern"), "title": meta.get("title"),
                            "symbol": meta.get("symbol"), "tf": meta.get("tf"), "ts": meta.get("ts"), "note": meta.get("note"),
                            "image": f"/v1/patterns/examples/{j.stem}.png"})
        return out

    @app.get("/scan/examples", tags=["scan"], summary="Thư viện ví dụ: mẫu chuẩn + tín hiệu live đã kích hoạt")
    async def examples(limit: Annotated[int, Query(ge=1, le=200)] = 60):
        s = sc()
        items = _examples_fs()
        evs = [e for e in await s.store.events(s.clock() - timedelta(days=90), 5000) if e["state"] == "triggered" and e.get("has_image")]
        for e in evs[: max(0, limit - len(items))]:
            items.append({"id": f"live-{e['id']}", "kind": "live" if e.get("live") else "replay", "pattern": e["pattern"],
                          "title": f"{e['pattern']} {e['symbol']} {e['tf']}", "symbol": e["symbol"], "tf": e["tf"], "ts": _iso(e["ts"]),
                          "note": None, "image": _img(e["id"])})
        return {"items": items[:limit], "disclaimer": DISCLAIMER}

    @app.get("/scan/examples/{xid}.png", tags=["scan"])
    async def example_png(xid: str):
        if not EX_ID.match(xid):
            raise HTTPException(404, "không có")
        f = Path(settings.examples_dir) / f"{xid}.png"
        if not f.is_file():
            raise HTTPException(404, "không có")
        return Response(f.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    # ---- Hiện vật backtest (CHỈ ĐỌC, bản nhỏ docs/research/pattern_sell mount :ro). Danh sách trắng tên file, không đọc đường dẫn tuỳ ý. ----
    BT_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}$")
    BT_DL = {"ledger_summary.csv": ("ledger", "text/csv; charset=utf-8"), "ledger_test.csv.gz": ("ledger", "application/gzip")}

    def _bt_dir(sub: str) -> Path:
        return Path(settings.backtest_dir) / sub

    def _bt_list(sub: str) -> list[str]:
        d = _bt_dir(sub)
        return sorted(f.name for f in d.glob("*.png") if BT_FILE.match(f.name)) if d.is_dir() else []

    @app.get("/scan/backtest/summary", tags=["scan"], summary="Tóm tắt backtest (dev/val/test khoá) + danh sách biểu đồ/ví dụ/tệp tải")
    async def bt_summary():
        f = Path(settings.backtest_dir) / "summary.json"
        empty = {"rows": [], "charts": [], "examples": [], "downloads": [], "empty": True, "disclaimer": DISCLAIMER}   # chưa có hiện vật (backtest đang dừng): 200 rỗng hợp lệ
        if not f.is_file():
            return empty
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return empty
        data["charts"] = [{"name": n, "image": f"/v1/patterns/backtest/charts/{n}"} for n in _bt_list("charts")]
        data["examples"] = [{"name": n, "image": f"/v1/patterns/backtest/examples/{n}"} for n in _bt_list("examples")]
        data["downloads"] = [{"name": n, "url": f"/v1/patterns/backtest/download/{n}", "size": (_bt_dir(sub) / n).stat().st_size}
                             for n, (sub, _) in BT_DL.items() if (_bt_dir(sub) / n).is_file()]
        data["disclaimer"] = DISCLAIMER
        return data

    @app.get("/scan/backtest/{kind}/{name}", tags=["scan"], summary="Ảnh biểu đồ/ví dụ backtest hoặc tệp CSV tải về")
    async def bt_file(kind: str, name: str):
        if kind in ("charts", "examples"):
            if not BT_FILE.match(name) or not name.endswith(".png"):
                raise HTTPException(404, "không có")
            f, ctype, hdr = _bt_dir(kind) / name, "image/png", {}
        elif kind == "download" and name in BT_DL:
            sub, ctype = BT_DL[name]
            f, hdr = _bt_dir(sub) / name, {"Content-Disposition": f'attachment; filename="{name}"'}
        else:
            raise HTTPException(404, "không có")
        if not f.is_file():
            raise HTTPException(404, "không có")
        return Response(f.read_bytes(), media_type=ctype, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff", **hdr})

    return app
