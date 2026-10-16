"""track-record: do do UY TIN KHACH QUAN cua chuyen gia/nguon y kien bang thanh tich (khong sinh van ban, khong dat lenh).
API noi bo (chi api-gateway goi, chi GET): /track/leaderboard | /experts/{id}/track-record | /consensus | /feed | /methodology | /chain/verify.
Ghi: chi scheduler noi bo (bang tr_* + Redis tr:*)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Path, Query, Request
from prometheus_client import Gauge
from tscommon import make_app

from . import __version__, consensus, scoring
from . import config as C
from .engine import Engine, Snapshot

log = logging.getLogger("track-record")
SCOPE_RE = r"^(all|forex|metal|index|commodity|crypto|stock_us|stock_vn|etf|bond|sym:[A-Za-z0-9:._-]{1,32})$"
SYM_RE = r"^[A-Za-z0-9:._-]{1,32}$"
EID_RE = r"^ent:[0-9a-f]{8}$"
HZ_RE = r"^(1D|1W|1M)$"

G_VIEWS = Gauge("trackrec_views_total", "So quan diem trong so cai", ["basis"])
G_ENT = Gauge("trackrec_entities", "So entity theo trang thai (1W, scope all)", ["status"])
G_BEAT = Gauge("trackrec_rated_beating_baseline", "So the diem rated vuot baseline (sau BH-FDR)")
G_LAST = Gauge("trackrec_last_scoring_timestamp", "Epoch giay lan cham diem thanh cong gan nhat")
G_CHAIN = Gauge("trackrec_chain_verified", "1 neu hash-chain hop le")
G_SECS = Gauge("trackrec_scoring_seconds", "Thoi gian cham diem lan gan nhat")


def r4(x: Any, nd: int = 4) -> Any:
    return None if x is None else round(float(x), nd)


def base(snap: Snapshot) -> dict:
    return {"method_version": C.METHOD_VERSION, "as_of": snap.as_of.isoformat(), "disclaimer": C.DISCLAIMER}


def card_out(c: dict) -> dict:
    return {"n": c["n"], "n_total": c["n_total"], "hit_rate": r4(c["hit_rate"]), "ci_low": r4(c["ci_low"]), "ci_high": r4(c["ci_high"]), "mean_ret_pct": r4(c["mean_ret_pct"], 3),
            "ret_ci_low": r4(c["ret_ci_low"], 3), "ret_ci_high": r4(c["ret_ci_high"], 3), "p_value": r4(c["p_value"], 5), "q_value": r4(c["q_value"], 5),
            "beats_baseline": bool(c["beats_baseline"]), "score": r4(c["score"], 1), "prior_score": r4(c["prior_score"], 1), "weight": r4(c["weight"], 3),
            "status": c["status"], "n_needed": c["n_needed"], "last_view_at": c["last_view_at"], "symbols_n": c["symbols_n"]}


def empty_card(n_total: int, kind: str, last: Optional[str], syms: int) -> dict:
    post, m0 = scoring.shrink(0, 0, kind)
    return {"n": 0, "n_total": n_total, "hit_rate": None, "ci_low": None, "ci_high": None, "mean_ret_pct": None, "ret_ci_low": None, "ret_ci_high": None, "p_value": None,
            "q_value": None, "beats_baseline": False, "score": r4(100 * post, 1), "prior_score": r4(100 * m0, 1), "weight": 1.0, "status": "insufficient", "n_needed": C.MIN_N,
            "last_view_at": last, "symbols_n": syms}


def ent_out(e: dict) -> dict:
    return {"entity_id": e["entity_id"], "label": e["label"], "kind": e["kind"], "lang": e["lang"]}


def set_metrics(e: Engine) -> None:
    s = e.snap
    if s is None:
        return
    by_basis: dict[str, int] = {}
    for v in s.views:
        by_basis[v["basis"]] = by_basis.get(v["basis"], 0) + 1
    for b in ("news", "signal", "cot"):
        G_VIEWS.labels(b).set(by_basis.get(b, 0))
    cs = [s.cards.get((eid, "all", "1W")) for eid in s.entities]
    G_ENT.labels("rated").set(sum(1 for c in cs if c and c["status"] == "rated"))
    G_ENT.labels("insufficient").set(sum(1 for c in cs if not c or c["status"] != "rated"))
    G_BEAT.set(s.summary.get("beating_baseline", 0))
    G_LAST.set(s.as_of.timestamp())
    G_CHAIN.set(1 if s.chain.get("ok") else 0)
    G_SECS.set(e.last_run.get("seconds", 0))


def create_app(engine: Optional[Engine] = None, interval_s: Optional[float] = None) -> FastAPI:
    app = make_app("track-record", __version__, internal_auth=True)
    app.state.engine = engine
    app.state.warm = engine is not None and engine.snap is not None
    interval = interval_s if interval_s is not None else float(os.getenv("TRACKREC_INTERVAL_S", "900"))

    async def loop(e: Engine):
        while True:
            failed = False
            try:
                await e.run_once()
                set_metrics(e)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                failed = True
                log.exception("lan cham diem loi")
            # Chưa có snapshot (vừa khởi động + lần chấm đầu lỗi, vd statement timeout khi máy tải cao) -> thử lại sớm, không chờ cả chu kỳ 15 phút (API 503).
            await asyncio.sleep(min(interval, 60.0) if (failed and e.snap is None) else interval)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        own, task = [], None
        if _app.state.engine is None:
            from .data import PgData
            from .store import PgStore
            data = await PgData.connect(os.environ["DATABASE_URL"])
            store = await PgStore.connect(os.environ["TRACKREC_DB_RW_URL"])
            redis = None
            if os.getenv("REDIS_URL"):
                import redis.asyncio as aioredis
                redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
            _app.state.engine = Engine(data, store, redis)
            own = [data, store]
            task = asyncio.create_task(loop(_app.state.engine))
        elif interval > 0:
            task = asyncio.create_task(loop(_app.state.engine))
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
            for o in own:
                with contextlib.suppress(Exception):
                    await o.close()

    app.router.lifespan_context = lifespan

    def snap(request: Request) -> Snapshot:
        e: Optional[Engine] = request.app.state.engine
        if e is None or e.snap is None:
            raise HTTPException(503, "đang khởi tạo lần chấm đầu tiên")
        return e.snap

    @app.get("/status", tags=["ops"])
    async def status(request: Request):
        e = request.app.state.engine
        s = e.snap if e else None
        return {"ready": s is not None, "as_of": s.as_of.isoformat() if s else None, "counts": s.counts if s else None, "chain_ok": s.chain.get("ok") if s else None,
                "read_only": True, "last_run": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in (e.last_run if e else {}).items()}}

    @app.get("/track/leaderboard", tags=["track"])
    async def leaderboard(request: Request, horizon: str = Query("1W", pattern=HZ_RE), scope: str = Query("all", pattern=SCOPE_RE),
                          kind: Optional[str] = Query(None, pattern="^(analyst|central_bank|media|positioning|signal_provider|other)$"),
                          lang: Optional[str] = Query(None, pattern="^(vi|en|other)$"), min_n: int = Query(C.MIN_N, ge=10, le=1000),
                          include_insufficient: bool = True, limit: int = Query(100, ge=1, le=200)):
        s = snap(request)
        rows = []
        for eid, ent in s.entities.items():
            if (kind and ent["kind"] != kind) or (lang and ent["lang"] != lang):
                continue
            c = s.cards.get((eid, scope, horizon))
            if c is None:
                continue
            row = {**ent_out(ent), **card_out(c)}
            if row["status"] == "rated" and row["n"] < min_n:
                row.update(status="insufficient", n_needed=min_n - row["n"], weight=1.0, beats_baseline=False)
            rows.append(row)
        scoring.assign_ranks(rows)
        n_rated = sum(1 for r in rows if r["status"] == "rated")
        n_all, n_beat = len(rows), sum(1 for r in rows if r["beats_baseline"])
        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 0, -r["n"], r["entity_id"]))
        if not include_insufficient:
            rows = [r for r in rows if r["status"] == "rated"]
        sm = s.summary
        return {**base(s), "horizon": horizon, "scope": scope, "min_n": min_n, "baseline": {"hit_rate": 0.5, "note": "ngẫu nhiên (hướng ngẫu nhiên, hoán vị)"},
                "summary": {"entities": n_all, "rated": n_rated, "insufficient": n_all - n_rated, "beating_baseline": n_beat, "tests": sm.get("tests", 0),
                            "expected_false_positives": sm.get("expected_false_positives", 0), "fdr_q": C.FDR_Q,
                            "uncorrected_expected_false_positives": sm.get("uncorrected_expected_false_positives", 0)},
                "rows": rows[:limit]}

    @app.get("/track/experts/{entity_id}/track-record", tags=["track"])
    async def track_record(request: Request, entity_id: str = Path(..., pattern=EID_RE), horizon: str = Query("1W", pattern=HZ_RE), scope: str = Query("all", pattern=SCOPE_RE)):
        s = snap(request)
        ent = s.entities.get(entity_id)
        if ent is None:
            raise HTTPException(404, "không có chuyên gia/nguồn này")
        evs = [v for v in s.views if v["entity_id"] == entity_id]
        evs_scope = [v for v in evs if consensus.in_scope(v["symbol"], scope)]
        n_total = len(evs)
        first = min((v["published_at"] for v in evs), default=None)
        last = max((v["published_at"] for v in evs), default=None)
        syms = len({v["symbol"] for v in evs})

        def card_for(sc: str, hz: str) -> dict:
            c = s.cards.get((entity_id, sc, hz))
            return card_out(c) if c else empty_card(sum(1 for v in evs if consensus.in_scope(v["symbol"], sc)), ent["kind"], last.isoformat() if last else None, syms)

        sample = scoring.independent([it for it in s.items.get((entity_id, horizon), []) if consensus.in_scope(it["symbol"], scope)])
        key = (entity_id, scope, horizon)
        if key not in s.cache:
            s.cache[key] = {"equity": scoring.equity_band(sample, "|".join(key)), "rolling": scoring.rolling(sample), "regime": scoring.by_regime(sample)}
        extra = s.cache[key]
        by_scope = []
        for (eid, sc, hz), c in s.cards.items():
            if eid == entity_id and hz == horizon and sc != "all":
                by_scope.append({"scope": sc, "n": c["n"], "hit_rate": r4(c["hit_rate"]), "ci_low": r4(c["ci_low"]), "ci_high": r4(c["ci_high"]), "mean_ret_pct": r4(c["mean_ret_pct"], 3),
                                 "status": c["status"], "_sym": sc.startswith("sym:")})
        classes = sorted((x for x in by_scope if not x["_sym"]), key=lambda x: -x["n"])
        top_syms = sorted((x for x in by_scope if x["_sym"]), key=lambda x: -x["n"])[:10]
        by_scope = [{k: v for k, v in x.items() if k != "_sym"} for x in classes + top_syms]
        recent = []
        for v in evs_scope[:20]:
            out = {}
            for hz in C.HORIZONS:
                it = s.outcome_idx.get((v["view_id"], hz))
                if it:
                    d = 1.0 if v["direction"] == "bullish" else -1.0
                    out[hz] = {"ret_pct": r4(d * it["raw"] * 100, 3), "hit": bool(it["hit"])}
                else:
                    out[hz] = None
            recent.append({"view_id": v["view_id"], "symbol": v["symbol"], "direction": v["direction"], "published_at": v["published_at"].isoformat(), "invalidation": v["invalidation"],
                           "state": "resolved" if all(out[h] for h in C.HORIZONS) else "pending", "outcome": out})
        return {**base(s), "entity": {**ent_out(ent), "first_view_at": first.isoformat() if first else None, "last_view_at": last.isoformat() if last else None, "n_total": n_total},
                "card": card_for(scope, horizon), "horizons": {hz: {"card": card_for(scope, hz)} for hz in C.HORIZONS}, "by_scope": by_scope,
                "by_regime": [{**x, "hit_rate": r4(x["hit_rate"]), "ci_low": r4(x["ci_low"]), "ci_high": r4(x["ci_high"]), "mean_ret_pct": r4(x["mean_ret_pct"], 3)} for x in extra["regime"]],
                "rolling": [{**x, "hit_rate": r4(x["hit_rate"]), "ci_low": r4(x["ci_low"]), "ci_high": r4(x["ci_high"])} for x in extra["rolling"]],
                "equity": {"points": [{**p, **{k: r4(p[k], 3) for k in ("cum_ret_pct", "rand_p05", "rand_p50", "rand_p95")}} for p in extra["equity"]["points"]], "note": extra["equity"]["note"]},
                "recent": recent, "chain": {"head_hash": s.chain.get("head_hash"), "verified": bool(s.chain.get("ok"))}}

    @app.get("/track/consensus", tags=["track"])
    async def consensus_ep(request: Request, window_days: int = Query(14, ge=1, le=90), scope: str = Query("all", pattern=SCOPE_RE), min_experts: int = Query(1, ge=1, le=50)):
        s = snap(request)
        rows = consensus.build(s.views, s.entities, s.weights, s.as_of, window_days, scope, min_experts)
        return {**base(s), "window_days": window_days, "scope": scope, "min_experts": min_experts, "rows": rows[:300]}

    @app.get("/track/feed", tags=["track"])
    async def feed(request: Request, limit: int = Query(50, ge=1, le=200), symbol: Optional[str] = Query(None, pattern=SYM_RE),
                   direction: Optional[str] = Query(None, pattern="^(bullish|bearish)$"), entity_id: Optional[str] = Query(None, pattern=EID_RE), before: Optional[str] = Query(None, max_length=40)):
        s = snap(request)
        cut = None
        if before:
            try:
                cut = datetime.fromisoformat(before.replace("Z", "+00:00"))
                if cut.tzinfo is None:
                    cut = cut.replace(tzinfo=C.UTC)
            except ValueError:
                raise HTTPException(422, "before không hợp lệ") from None
        items, more = [], False
        for v in s.views:
            if (symbol and v["symbol"] != symbol) or (direction and v["direction"] != direction) or (entity_id and v["entity_id"] != entity_id) or (cut and v["published_at"] >= cut):
                continue
            if len(items) >= limit:
                more = True
                break
            e = s.entities.get(v["entity_id"], {})
            w = s.weights.get(v["entity_id"], {})
            items.append({"view_id": v["view_id"], "entity_id": v["entity_id"], "label": e.get("label", ""), "kind": e.get("kind"), "symbol": v["symbol"], "asset_class": C.asset_class(v["symbol"]),
                          "direction": v["direction"], "published_at": v["published_at"].isoformat(), "invalidation": v["invalidation"], "horizon_hint": v["horizon_hint"],
                          "status": w.get("status", "insufficient"), "weight": r4(w.get("w", 1.0), 3)})
        return {**base(s), "items": items, "next_before": items[-1]["published_at"] if more and items else None}

    @app.get("/track/methodology", tags=["track"])
    async def methodology(request: Request):
        s = snap(request)
        return {**base(s), **METHODOLOGY}

    @app.get("/track/chain/verify", tags=["track"])
    async def chain_verify(request: Request):
        e: Optional[Engine] = request.app.state.engine
        if e is None:
            raise HTTPException(503, "chưa sẵn sàng")
        res = await e.store.verify()
        G_CHAIN.set(1 if res["ok"] else 0)
        return {"method_version": C.METHOD_VERSION, "as_of": C.utcnow().isoformat(), "disclaimer": C.DISCLAIMER, **res}

    return app


METHODOLOGY = {
    "views": "Quan điểm có hướng được trích bằng QUY TẮC (không sinh văn bản): tin có sentiment |s|>=0,35 gắn tối đa 3 mã có giá; tín hiệu mua/bán của chuyên gia; vị thế đầu cơ COT (dấu net theo hướng cặp, công bố thứ Sáu 20:30 UTC). 1 quan điểm/entity/mã/ngày; mâu thuẫn trong ngày thì bỏ ngày đó.",
    "no_lookahead": "Vào lệnh giả định = giá MỞ nến D1 đầu tiên bắt đầu SAU thời điểm quan sát (max(công bố, ghi nhận)); thoát = giá ĐÓNG nến thứ 1/5/21 kể từ nến vào. Chế độ thị trường chỉ dùng nến D1 đã đóng trước thời điểm quan sát.",
    "independence": "Chỉ đếm quan điểm độc lập: với mỗi (entity, mã), quan điểm mới chỉ tính khi nến vào không sớm hơn nến thoát của quan điểm đã tính trước đó (cửa sổ không chồng lấn).",
    "metrics": "hit = hướng đúng (lợi suất log theo hướng > 0). KTC Wilson 95% cho hit-rate; stationary block bootstrap (1000 lần, khối TB ~ n^(1/3)) cho lợi suất TB theo hướng; kiểm định hoán vị nhãn hướng (>=2000 lần, seed cố định) cho p-value một phía của lợi suất TB theo hướng so với hướng ngẫu nhiên cùng tỉ lệ mua/bán.",
    "multiple_testing": "Benjamini–Hochberg trên TOÀN họ kiểm định (mọi entity × phạm vi × kỳ hạn có n>=30), q=0,10. beats_baseline = rated & q<0,10 & cận dưới Wilson>0,5 & cận dưới bootstrap lợi suất>0.",
    "min_n": C.MIN_N,
    "shrinkage": "score = 100 × trung bình hậu nghiệm Beta (tiên nghiệm tâm 0,5 + tilt theo loại, độ mạnh k theo loại) nên co về 50 khi ít bằng chứng.",
    "priors": {k: {"k": v[0], "tilt": v[1]} for k, v in C.PRIORS.items()},
    "prior_tilt_note": "Tilt tiên nghiệm theo loại tổ chức giới hạn ±0,02; hiện chỉ đặt âm nhẹ (-0,01) cho tin tức thô và nhà cung cấp tín hiệu (thiên lệch sống sót), các loại khác = 0, theo docs/research/INFO_SIGNALS_STUDY.md.",
    "weight": "weight = 1 khi chưa đủ mẫu; khi rated = clamp(1 + 6·(post_mean − 0,5), 0,25, 2,0).",
    "ledger": "Sổ cái quan điểm append-only, hash-chain sha256(prev_hash|canonical_json); trigger DB chặn UPDATE/DELETE/TRUNCATE; /track/chain/verify kiểm toàn chuỗi.",
    "proxies": "Mã không có giá D1 trực tiếp dùng đại diện: SPX→SPY, NDX→QQQ, XAGUSD→SLV, USOIL→USO, BTCUSD/ETHUSD→cặp USDT. DXY chưa có giá D1 nên chưa chấm được.",
    "limitations": ["Dữ liệu còn mỏng; đa số entity chưa đủ mẫu nên KHÔNG xếp hạng.", "Sentiment của bài tin không phải quan điểm về cặp/mã.", "Kỳ hạn 1W/1M có thể chồng lấn giữa các mã (chỉ độc lập trong từng mã).",
                    "Không tính phí/spread/trượt giá.", "Thiên lệch sống sót: chỉ theo dõi các nguồn đang được thu thập.", "Chế độ thị trường là nhãn quy tắc từ D1, không phải mô hình trạng thái thật sự."],
}
