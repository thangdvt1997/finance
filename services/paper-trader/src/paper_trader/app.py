"""HTTP API (chỉ đọc, trừ 2 lệnh quản trị kill-switch cần PAPER_ADMIN_TOKEN). Mọi phản hồi gắn nhãn MÔ PHỎNG."""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from tscommon import Bus, make_app

from . import SIMULATION_LABEL, __version__, perf
from .card import load_cards
from .config import Settings, load_yaml
from .runner import Runner, loop, risk_windows_fn
from .service import Anchors, Monitor, QualityService
from .strategy import load_plugins, registry

log = logging.getLogger("paper")

DISCLAIMER = "Đây là kết quả MÔ PHỎNG (forward test), KHÔNG phải tiền thật và không phải khuyến nghị đầu tư. Hiệu suất quá khứ/mô phỏng không đảm bảo kết quả tương lai."


def _clean(x):
    """NaN/Inf -> null (JSON hợp lệ); numpy scalar -> số Python."""
    if isinstance(x, float):
        return x if x == x and x not in (float("inf"), float("-inf")) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            return _clean(x.item())
        except Exception:  # noqa: BLE001
            return x
    return x


def _wrap(data: dict) -> dict:
    return _clean({"simulation": True, "label": SIMULATION_LABEL, "disclaimer": DISCLAIMER, "generated_at": datetime.now(timezone.utc).isoformat(), **data})


def _state(row: dict) -> dict:
    st = row.get("state") or {}
    return json.loads(st) if isinstance(st, str) else st


def _cfg(row: dict) -> dict:
    c = row.get("config") or {}
    return json.loads(c) if isinstance(c, str) else c


def _summary(row: dict) -> dict:
    st, cfg = _state(row), _cfg(row)
    init = float(row["initial_capital"])
    eq = row.get("equity")
    return {"account_id": row["account_id"], "name": row["name"], "strategy": row["strategy"], "base_ccy": row["base_ccy"],
            "initial_capital": init, "benchmark_id": row.get("benchmark_id"), "meaningful": bool(row.get("meaningful", True)),
            "status": row.get("status", "active"), "halt_reason": row.get("halt_reason") or "", "halt_until": row.get("halt_until"),
            "equity": eq, "total_return": (eq / init - 1.0) if eq is not None and init else None, "drawdown": row.get("drawdown"),
            "gross_exposure": row.get("gross_exposure"), "net_exposure": row.get("net_exposure"), "as_of": row.get("equity_ts"),
            "inception": st.get("inception_ts"), "replay": bool(cfg.get("start_at")), "rebalance": cfg.get("rebalance"),
            "universe": cfg.get("universe", [])}


def _kill_switch(row: dict) -> dict:
    st, cfg = _state(row), _cfg(row)
    lim = cfg.get("risk_effective") or {}
    eq, hwm = float(st.get("last_equity") or row["initial_capital"]), float(st.get("hwm") or row["initial_capital"])
    day0, wk0 = float(st.get("day_start_equity") or eq), float(st.get("week_start_equity") or eq)
    cur = {"daily": eq / day0 - 1.0 if day0 else 0.0, "weekly": eq / wk0 - 1.0 if wk0 else 0.0, "drawdown": eq / hwm - 1.0 if hwm else 0.0}
    limits = {"daily": -float(lim.get("max_daily_loss", 0)), "weekly": -float(lim.get("max_weekly_loss", 0)), "drawdown": -float(lim.get("max_drawdown", 0))}
    return {"status": row.get("status", "active"), "reason": row.get("halt_reason") or "", "halt_until": row.get("halt_until"),
            "hard_lock": row.get("status") == "locked", "limits": limits, "current": cur,
            "headroom": {k: cur[k] - limits[k] for k in cur},   # >0 = còn dư địa trước khi chạm giới hạn
            "rules": {"max_leverage": lim.get("max_leverage"), "max_weight": lim.get("max_weight"),
                      "max_orders_per_minute": lim.get("max_orders_per_minute"), "whitelist": lim.get("whitelist"),
                      "sizing": lim.get("sizing"), "flatten_on_halt": lim.get("flatten_on_halt")}}


def create_app(settings: Settings | None = None, runner: Runner | None = None, store=None) -> FastAPI:
    settings = settings or Settings()
    app = make_app("paper-trader", __version__, internal_auth=True)
    app.title = "Paper trader (MÔ PHỎNG)"
    app.description = f"{SIMULATION_LABEL}. Forward test phương pháp giao dịch; không broker, không tiền thật."
    app.state.runner, app.state.store = runner, store if store is not None else (runner.store if runner else None)
    app.state.service = None

    def wire(_app: FastAPI) -> None:
        """Gắn QualityService (hiệu suất CI/TCA/drift/card/hash-chain) + Monitor định kỳ vào runner."""
        if _app.state.store is None or _app.state.service is not None:
            return
        bus = getattr(_app.state.runner, "bus", None)
        anchors = Anchors(getattr(bus, "r", None))
        _app.state.service = QualityService(_app.state.store, load_cards(settings.card_dir), anchors)
        if _app.state.runner is not None:
            _app.state.runner.monitor = Monitor(_app.state.runner, _app.state.service, settings.monitor_interval)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()
        task, warm, closers = None, None, []
        if _app.state.runner is None and settings.enabled:
            from .repo import PgBarSource, PgPaperStore
            if not settings.write_url:
                raise RuntimeError("PAPER_DB_RW_URL trống: paper-trader cần role ts_paper (chạy infra/db/create_paper_role.sh)")
            cfg = load_yaml(settings.config_path)
            load_plugins(settings.strategy_dir)
            source = await PgBarSource.connect(settings.read_url)
            pstore = await PgPaperStore.connect(settings.write_url)
            closers += [source.close, pstore.close]
            bus = Bus.from_url(settings.redis_url)
            closers.append(bus.r.aclose)
            _app.state.runner = Runner(cfg, source, pstore, bus, await risk_windows_fn(cfg))
            _app.state.store = pstore
            await _app.state.runner.init()
        wire(_app)
        if _app.state.runner is not None and settings.enabled:
            task = asyncio.create_task(loop(_app.state.runner, int(_app.state.runner.cfg["interval_seconds"]), stop))
            if _app.state.service is not None:
                warm = asyncio.create_task(_app.state.service.warm_governance(stop))
        try:
            yield
        finally:
            stop.set()
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if warm:
                warm.cancel()
                await asyncio.gather(warm, return_exceptions=True)
            for c in closers:
                with contextlib.suppress(Exception):
                    await c()

    app.router.lifespan_context = lifespan
    wire(app)

    def st():
        s = app.state.store
        if s is None:
            raise HTTPException(503, "store chưa sẵn sàng (ENABLED=false?)")
        return s

    async def acct(account_id: str) -> dict:
        if "\x00" in account_id or len(account_id) > 64:   # NUL làm Postgres ném lỗi -> 500; id hợp lệ ngắn
            raise HTTPException(404, "không có tài khoản mô phỏng")
        row = await st().get_account(account_id)
        if not row:
            raise HTTPException(404, f"không có tài khoản mô phỏng '{account_id}'")
        return row

    def admin(x_admin_token: Annotated[str | None, Header()] = None):
        tok = settings.admin_token
        if not tok:
            raise HTTPException(503, "PAPER_ADMIN_TOKEN chưa đặt: lệnh quản trị bị tắt")
        if not x_admin_token or not hmac.compare_digest(x_admin_token, tok):
            raise HTTPException(401, "sai X-Admin-Token")

    @app.get("/status", tags=["ops"], summary="Kết quả chu kỳ gần nhất")
    async def status():
        r = app.state.runner
        return _wrap(r.last if r else {"status": "tắt (ENABLED=false)"})

    @app.get("/paper/strategies", tags=["paper"], summary="Plugin chiến lược đã đăng ký")
    async def strategies():
        out = []
        for name, cls in sorted(registry().items()):
            try:
                out.append(cls({}).describe())
            except Exception:  # noqa: BLE001
                out.append({"name": name})
        return _wrap({"items": out})

    @app.get("/paper/accounts", tags=["paper"], summary="Danh sách tài khoản mô phỏng")
    async def accounts():
        return _wrap({"items": [_summary(r) for r in await st().list_accounts()]})

    @app.get("/paper/overview", tags=["paper"], summary="Tổng quan cho UI: tài khoản + sparkline + thống kê chính")
    async def overview(points: Annotated[int, Query(ge=2, le=500)] = 90):
        rows = await st().list_accounts()
        items = []
        for r in rows:
            eq = await st().equity(r["account_id"], points)
            s = _summary(r)
            s["spark"] = [{"ts": e["ts"], "index": 100.0 * float(e["equity"]) / float(eq[0]["equity"])} for e in eq] if eq else []
            s["kill_switch"] = _kill_switch(r)
            items.append(s)
        return _wrap({"items": items, "strategies": sorted(registry()),
                      "cycle": app.state.runner.last if app.state.runner else None})

    @app.get("/paper/accounts/{account_id}", tags=["paper"], summary="Chi tiết tài khoản")
    async def account(account_id: str):
        r = await acct(account_id)
        rows = {x["account_id"]: x for x in await st().list_accounts()}
        s = _summary(rows.get(account_id, r))
        cfg = _cfg(r)
        s["config"] = {k: cfg.get(k) for k in ("rebalance", "universe", "params", "risk_effective", "start_at")}
        return _wrap(s)

    @app.get("/paper/accounts/{account_id}/equity", tags=["paper"], summary="Đường equity (+ benchmark chuẩn hoá về 100)")
    async def equity(account_id: str, limit: Annotated[int, Query(ge=1, le=20000)] = 3000, benchmark: bool = True):
        r = await acct(account_id)
        eq = await st().equity(account_id, limit)
        bm = []
        if benchmark and r.get("benchmark_id"):
            bm = await st().equity(r["benchmark_id"], limit)
        init = float(r["initial_capital"])
        return _wrap({"account_id": account_id, "benchmark_id": r.get("benchmark_id"), "base_ccy": r["base_ccy"], "initial_capital": init,
                      "series": perf.normalized(eq, init), "benchmark": perf.normalized(bm, float(bm[0]["equity"]) if bm else None),
                      "drawdown": [{"ts": e["ts"], "dd": e["drawdown"]} for e in eq]})

    @app.get("/paper/accounts/{account_id}/positions", tags=["paper"], summary="Vị thế mô phỏng hiện tại")
    async def positions(account_id: str):
        await acct(account_id)
        return _wrap({"items": await st().positions(account_id)})

    @app.get("/paper/accounts/{account_id}/orders", tags=["paper"], summary="Lệnh mô phỏng gần nhất")
    async def orders(account_id: str, limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        await acct(account_id)
        return _wrap({"items": await st().orders(account_id, limit)})

    @app.get("/paper/accounts/{account_id}/fills", tags=["paper"], summary="Fill mô phỏng gần nhất")
    async def fills(account_id: str, limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        await acct(account_id)
        return _wrap({"items": await st().fills(account_id, limit)})

    @app.get("/paper/accounts/{account_id}/events", tags=["paper"], summary="Journal sự kiện (bất biến)")
    async def events(account_id: str, limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        await acct(account_id)
        return _wrap({"items": await st().events(account_id, limit)})

    @app.get("/paper/events", tags=["paper"], summary="Journal sự kiện mọi tài khoản")
    async def all_events(limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        return _wrap({"items": await st().events(None, limit)})

    @app.get("/paper/accounts/{account_id}/kill-switch", tags=["paper"], summary="Trạng thái kill-switch + giới hạn rủi ro")
    async def kill_switch(account_id: str):
        return _wrap(_kill_switch(await acct(account_id)))

    @app.get("/paper/accounts/{account_id}/stats", tags=["paper"], summary="Thống kê hiệu suất/rủi ro (empyrical)")
    async def stats(account_id: str):
        r = await acct(account_id)
        eq = await st().equity(account_id, 20000)
        bm = await st().equity(r["benchmark_id"], 20000) if r.get("benchmark_id") else None
        ppy = int((_cfg(r).get("periods_per_year")) or 252)
        s = await asyncio.to_thread(perf.stats, eq, bm, float(r["initial_capital"]), ppy)
        state = _state(r)
        fl = await st().fills(account_id, 5000)
        closed = [f for f in fl if f.get("realized_pnl")]
        avg_eq = sum(float(e["equity"]) for e in eq) / len(eq) if eq else float(r["initial_capital"])
        s["trading"] = {"orders": state.get("n_orders", 0), "fills": state.get("n_fills", 0),
                        "turnover_x_equity": (state.get("traded_notional", 0.0) / avg_eq) if avg_eq else None,
                        "costs": state.get("costs", {}), "win_rate_closed": (sum(1 for f in closed if f["realized_pnl"] > 0) / len(closed)) if closed else None,
                        "realized_pnl": sum(f.get("realized_pnl") or 0.0 for f in fl)}
        s["note"] = ("Mẫu quá ngắn: Sharpe/CAGR chưa có ý nghĩa thống kê (cần >= 60 ngày, khuyến nghị 8-12 tuần theo STRATEGY_OPTIONS)." if not s.get("reliable") else "")
        return _wrap(s)

    def sv() -> QualityService:
        if app.state.service is None:
            raise HTTPException(503, "dịch vụ chất lượng chưa sẵn sàng")
        return app.state.service

    @app.get("/paper/accounts/{account_id}/performance", tags=["paper"], summary="Hiệu suất + khoảng tin cậy (bootstrap), rolling, benchmark, đóng góp lớp tài sản, đòn bẩy")
    async def performance(account_id: str, fresh: bool = False):
        await acct(account_id)
        return _wrap(await sv().performance(account_id, fresh))

    @app.get("/paper/accounts/{account_id}/tca", tags=["paper"], summary="TCA: chi phí/slippage mô phỏng vs giả định, chi phí luỹ kế, vòng quay")
    async def tca_(account_id: str, fresh: bool = False):
        await acct(account_id)
        return _wrap(await sv().tca(account_id, fresh))

    @app.get("/paper/accounts/{account_id}/drift", tags=["paper"], summary="Giám sát suy giảm: CUSUM/kiểm định so với kỳ vọng backtest; tách tín hiệu vs thực thi")
    async def drift_(account_id: str, fresh: bool = False):
        await acct(account_id)
        return _wrap(await sv().drift(account_id, fresh))

    @app.get("/paper/accounts/{account_id}/card", tags=["paper"], summary="Strategy card + giai đoạn tính tự động + tiêu chí chuyển giai đoạn")
    async def card_(account_id: str, fresh: bool = False):
        await acct(account_id)
        return _wrap(await sv().card(account_id, fresh))

    @app.get("/paper/accounts/{account_id}/verify", tags=["paper"], summary="Xác minh hash-chain journal của tài khoản")
    async def verify_one(account_id: str):
        await acct(account_id)
        return _wrap(await sv().verify(account_id))

    @app.get("/paper/verify", tags=["paper"], summary="Xác minh hash-chain journal mọi tài khoản (ok=false -> đứt/bị sửa)")
    async def verify_all():
        res = [await sv().verify(r["account_id"]) for r in await st().list_accounts()]
        return _wrap({"ok": all(x.get("ok") is not False for x in res if x), "items": [x for x in res if x]})

    @app.get("/paper/accounts/{account_id}/config-versions", tags=["paper"], summary="Lịch sử phiên bản cấu hình bất biến (hash)")
    async def config_versions(account_id: str):
        r = await acct(account_id)
        vs = await st().config_versions(account_id)
        cfg = _cfg(r)
        return _wrap({"account_id": account_id, "current": {"config_hash": cfg.get("config_hash"), "params_hash": cfg.get("params_hash"), "version": cfg.get("config_version")},
                      "items": [{"version": v["version"], "config_hash": v["config_hash"], "params_hash": v["params_hash"], "created_at": v["created_at"]} for v in vs]})

    @app.get("/paper/governance", tags=["paper"], summary="Tổng quan quản trị: giai đoạn chiến lược, drift, hash-chain, phiên bản cấu hình")
    async def governance():
        return _wrap(await sv().governance())

    @app.post("/paper/accounts/{account_id}/kill-switch/reset", tags=["admin"], summary="Reset kill-switch (cần X-Admin-Token)", dependencies=[Depends(admin)])
    async def ks_reset(account_id: str):
        r = app.state.runner
        if r is None:
            raise HTTPException(503, "runner chưa chạy")
        try:
            return _wrap(await r.command(account_id, "reset"))
        except KeyError:
            raise HTTPException(404, "không có tài khoản") from None

    @app.post("/paper/accounts/{account_id}/kill-switch/halt", tags=["admin"], summary="Khoá chiến lược thủ công (cần X-Admin-Token)", dependencies=[Depends(admin)])
    async def ks_halt(account_id: str, reason: str = "manual"):
        r = app.state.runner
        if r is None:
            raise HTTPException(503, "runner chưa chạy")
        try:
            return _wrap(await r.command(account_id, "halt", reason))
        except KeyError:
            raise HTTPException(404, "không có tài khoản") from None

    return app
