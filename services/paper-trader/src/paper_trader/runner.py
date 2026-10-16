"""Vòng lặp forward test: nạp nến đã đóng (ts_ro) -> engine từng bước -> ghi journal (ts_paper) -> phát bus/alert.
KHÔNG có đường thực thi thật: chỉ ghi các bảng paper_* và phát paper.events / alerts.out."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from prometheus_client import Counter, Gauge
from tscommon import make_event

from . import SIMULATION_LABEL
from . import govern
from .config import instrument_for
from .engine import Engine
from .market import MarketView, frame_from_rows, resample_h1
from .models import AccountState, TF_DELTA, parse_ts, utc
from .repo import BarSource, PaperStore
from .risk import RiskConfig, RiskEngine
from .strategy import build as build_strategy

log = logging.getLogger("paper")

CYCLES = Counter("paper_cycles_total", "Số chu kỳ", ["status"])
STEPS = Counter("paper_steps_total", "Số bước bar đã mô phỏng", ["account"])
FILLS = Counter("paper_fills_total", "Số fill mô phỏng", ["account"])
EQUITY = Gauge("paper_equity", "Equity mô phỏng (tiền tài khoản)", ["account"])
DRAWDOWN = Gauge("paper_drawdown", "Drawdown hiện tại (số âm)", ["account"])
STATUS = Gauge("paper_account_status", "0=active 1=halted 2=locked (kill-switch)", ["account"])
LAST_OK = Gauge("paper_last_success_timestamp", "Unix time chu kỳ thành công gần nhất")
SYM_MISSING = Counter("paper_data_missing_total", "Thiếu dữ liệu nến", ["symbol"])

EVENTS_STREAM = "paper.events"
ALERTS_STREAM = "alerts.out"
STATUS_NUM = {"active": 0, "halted": 1, "locked": 2}


class AccountRuntime:
    def __init__(self, acfg: dict, engine: Engine, replay: bool):
        self.cfg, self.engine, self.replay = acfg, engine, replay

    @property
    def id(self) -> str:
        return self.cfg["id"]

    @property
    def deprecated(self) -> bool:
        """Tài khoản đã được thay thế: GIỮ journal + vị thế cuối (bất biến), không chạy thêm bước nào."""
        return bool(self.cfg.get("deprecated"))


def load_params(acfg: dict) -> dict:
    p: dict = {}
    pf = acfg.get("params_file")
    if pf and Path(pf).is_file():
        p.update((yaml.safe_load(Path(pf).read_text(encoding="utf-8")) or {}).get("params", {}) or {})
    p.update(acfg.get("params") or {})
    return p


def build_runtime(cfg: dict, acfg: dict, state: AccountState | None = None) -> AccountRuntime:
    universe = list(acfg["universe"])
    instruments = {s: instrument_for(cfg, s) for s in universe}
    strat = build_strategy(acfg["strategy"], load_params(acfg))
    strat.meaningful = bool(acfg.get("meaningful", strat.meaningful))
    risk = RiskEngine(RiskConfig.build(acfg.get("risk")), int(cfg.get("periods_per_year", 252)))
    eng = Engine(acfg["id"], acfg.get("base_ccy", "USD"), instruments, universe, strat, risk, tf=cfg.get("tf", "D1"),
                 rebalance=acfg.get("rebalance", "monthly"), initial_capital=float(acfg["initial_capital"]),
                 max_pending_steps=int(cfg.get("max_pending_steps", 5)), state=state)
    return AccountRuntime(acfg, eng, replay=bool(acfg.get("start_at")))


class Runner:
    def __init__(self, cfg: dict, source: BarSource, store: PaperStore, bus=None, windows_fn=None):
        self.cfg, self.source, self.store, self.bus = cfg, source, store, bus
        self.windows_fn = windows_fn
        self.accounts: dict[str, AccountRuntime] = {}
        self.lock = asyncio.Lock()
        self.last: dict = {"status": "chưa chạy"}
        self.tf = cfg.get("tf", "D1")
        self.monitor = None                       # service.Monitor (xác minh hash-chain + giám sát suy giảm), gắn bởi app

    # ------------------------------------------------------------------ khởi tạo
    async def init(self) -> None:
        for acfg in self.cfg["accounts"]:
            rt = build_runtime(self.cfg, acfg)
            row = await self.store.get_account(acfg["id"])
            if row and row.get("state"):
                rt.engine.state = AccountState.from_dict(row["state"] if isinstance(row["state"], dict) else json.loads(row["state"]))
            eff = govern.effective_config(self.cfg, acfg, rt)               # cấu hình hiệu lực -> hash -> phiên bản bất biến
            hs = govern.hashes(eff)
            ver = await self.store.register_config(acfg["id"], hs["config_hash"], hs["params_hash"], eff)
            await self.store.ensure_account({
                "account_id": acfg["id"], "name": acfg.get("name", acfg["id"]), "strategy": acfg["strategy"],
                "base_ccy": acfg.get("base_ccy", "USD"), "initial_capital": float(acfg["initial_capital"]),
                "benchmark_id": acfg.get("benchmark"), "meaningful": bool(acfg.get("meaningful", rt.engine.strategy.meaningful)),
                "config": {k: v for k, v in acfg.items() if k != "params_file"} | {"params": rt.engine.strategy.params,
                                                                                    "risk_effective": dict(rt.engine.risk.cfg),
                                                                                    "assumptions": eff["assumptions"], "config_hash": hs["config_hash"],
                                                                                    "params_hash": hs["params_hash"], "config_version": ver.get("version")},
                "state": rt.engine.state.to_dict()})
            self.accounts[acfg["id"]] = rt
            await self.store.chain_bootstrap(acfg["id"])                    # chuỗi rỗng + đã có bản ghi cũ -> neo hiện trạng (genesis) TRƯỚC mọi bản ghi mới
            if ver.get("new"):
                await self._config_event(rt, ver, hs)

    async def _config_event(self, rt: "AccountRuntime", ver: dict, hs: dict) -> None:
        """Phiên bản cấu hình mới -> sự kiện bất biến trong journal (+ cảnh báo nếu là THAY ĐỔI so với phiên bản trước)."""
        now = datetime.now(timezone.utc)
        changed = ver.get("version", 1) > 1
        ev = {"key": f"config:{hs['config_hash'][:16]}", "type": "config_version", "severity": "warn" if changed else "info", "ts": now,
              "message": (f"[MÔ PHỎNG] cấu hình {rt.id} ĐỔI -> phiên bản v{ver['version']} (hash {hs['config_hash'][:12]}); đồng hồ đánh giá chuyển giai đoạn bắt đầu lại"
                          if changed else f"[MÔ PHỎNG] cấu hình {rt.id} v{ver['version']} khoá (hash {hs['config_hash'][:12]})"),
              "data": {"version": ver["version"], "config_hash": hs["config_hash"], "params_hash": hs["params_hash"], "previous": ver.get("previous")}}
        await self.store.save_manual(rt.id, rt.engine.state, [ev])
        if changed and self.bus is not None and not rt.deprecated and self.cfg.get("alerts_enabled", True):
            try:
                await self.bus.publish(ALERTS_STREAM, make_event("alert", "paper-trader", {
                    "level": "warn", "title": ev["message"][:140], "body": f"{ev['message']}\n{SIMULATION_LABEL}", "tags": ["paper", "config_version", rt.id],
                    "dedupe_key": f"paper:{rt.id}:{ev['key']}"}))
            except Exception:  # noqa: BLE001
                log.exception("không phát được alert cấu hình")

    # ------------------------------------------------------------------ dữ liệu
    async def _frames(self, symbols: list[str]) -> dict:
        out = {}
        n = int(self.cfg.get("history_bars", 520))
        for s in symbols:
            rows = await self.source.bars(s, self.tf, n)
            df = frame_from_rows(rows)
            if df.empty and self.tf in ("D1", "H4"):
                h1 = frame_from_rows(await self.source.bars(s, "H1", min(n * 24, 12000)))
                df = resample_h1(h1, self.tf) if not h1.empty else df
            if df.empty:
                SYM_MISSING.labels(s).inc()
            out[s] = df
        return out

    # ------------------------------------------------------------------ 1 chu kỳ
    async def run_cycle(self, now: datetime | None = None) -> dict:
        async with self.lock:
            now = utc(now or datetime.now(timezone.utc))
            t0 = time.monotonic()
            summary: dict[str, Any] = {}
            windows = await self.windows_fn(now) if self.windows_fn else []
            for aid, rt in self.accounts.items():
                if rt.deprecated:
                    summary[aid] = {"deprecated": True}
                    continue
                try:
                    summary[aid] = await self._run_account(rt, now, windows)
                except Exception:  # noqa: BLE001
                    log.exception("paper: lỗi tài khoản %s", aid)
                    await self._resync(rt)
                    summary[aid] = {"error": True}
            CYCLES.labels("ok").inc()
            LAST_OK.set(time.time())
            if self.monitor is not None:
                try:
                    await self.monitor.tick(now)
                except Exception:  # noqa: BLE001
                    log.exception("paper: monitor lỗi (không ảnh hưởng mô phỏng)")
            self.last = {"status": "ok", "generated_at": now.isoformat(), "seconds": round(time.monotonic() - t0, 2),
                         "accounts": summary, "label": SIMULATION_LABEL}
            return self.last

    async def _resync(self, rt: AccountRuntime) -> None:
        """Lỗi giữa chừng -> bỏ trạng thái trong bộ nhớ, nạp lại từ DB (nguồn chân lý)."""
        row = await self.store.get_account(rt.id)
        if row and row.get("state"):
            st = row["state"]
            rt.engine.state = AccountState.from_dict(st if isinstance(st, dict) else json.loads(st))

    async def _run_account(self, rt: AccountRuntime, now: datetime, windows: list[dict]) -> dict:
        eng, st = rt.engine, rt.engine.state
        syms = eng.required_symbols()
        view = MarketView(await self._frames(syms), self.tf, now)
        all_t = view.step_times(None, eng.universe)
        if not all_t:
            return {"steps": 0, "note": "chưa có nến đã đóng"}
        if st.last_close is None:
            start_at = parse_ts(rt.cfg.get("start_at"))
            if start_at:                                    # replay có chủ đích (nhãn rõ trong events)
                steps = view.step_times(start_at, eng.universe)
                st.inception_ts = start_at
                ev_note = f"REPLAY từ {start_at.isoformat()} (dữ liệu quá khứ, KHÔNG phải forward test thật)"
            else:                                           # forward thật: bắt đầu từ bar đã đóng gần nhất
                steps = [all_t[-1]]
                st.inception_ts = all_t[-1] + TF_DELTA[self.tf]
                ev_note = f"bắt đầu forward test tại {st.inception_ts.isoformat()}"
            first_event = {"key": "account_started", "type": "account_started", "severity": "info", "ts": st.inception_ts,
                           "message": f"[MÔ PHỎNG] tài khoản {rt.id} khởi tạo vốn {st.initial_capital:,.0f} {eng.base}; {ev_note}",
                           "data": {"initial_capital": st.initial_capital, "base_ccy": eng.base, "strategy": eng.strategy.name,
                                    "replay": bool(start_at), "universe": eng.universe}}
        else:
            steps = view.step_times(st.last_close, eng.universe)
            first_event = None
        if not steps:
            return {"steps": 0}
        analytics = None
        if not rt.replay:
            analytics = await self.source.analytics_summary(self.tf)
        n_fills = 0
        latest_t = all_t[-1]
        for i, T in enumerate(steps[:2000]):
            res = eng.step(T, view, analytics if T == latest_t else None, windows)
            if first_event and i == 0:
                res.events.insert(0, first_event)
            new_keys = await self.store.save_step(rt.id, res, eng.state)
            STEPS.labels(rt.id).inc()
            n_fills += len(res.fills)
            FILLS.labels(rt.id).inc(len(res.fills))
            await self._publish(rt, res, set(new_keys), live=(T == latest_t))
        EQUITY.labels(rt.id).set(eng.state.last_equity)
        DRAWDOWN.labels(rt.id).set(eng.state.last_equity / eng.state.hwm - 1.0 if eng.state.hwm else 0.0)
        STATUS.labels(rt.id).set(STATUS_NUM.get(eng.state.status, 0))
        return {"steps": len(steps), "fills": n_fills, "equity": round(eng.state.last_equity, 2), "status": eng.state.status}

    # ------------------------------------------------------------------ bus + alert
    async def _publish(self, rt: AccountRuntime, res, new_keys: set[str], live: bool) -> None:
        if self.bus is None:
            return
        evs = [e for e in res.events if e["key"] in new_keys]
        for e in evs:
            payload = {"account_id": rt.id, "simulation": True, "label": SIMULATION_LABEL, "severity": e["severity"], "message": e["message"],
                       "ts": e["ts"].isoformat(), **e["data"], "event_type": e["type"]}
            try:
                await self.bus.publish(EVENTS_STREAM, make_event(f"paper.{e['type']}", "paper-trader", payload))
            except Exception:  # noqa: BLE001
                log.exception("không phát được paper.events")
        if not self.cfg.get("alerts_enabled", True) or rt.replay:
            return                                          # replay: không spam Telegram
        fills = [e for e in evs if e["type"] == "fill"]
        alerts: list[dict] = []
        for e in evs:
            if e["type"] == "kill_switch":                       # quan trọng: luôn báo, kể cả khi đang bắt kịp nhiều bar
                alerts.append(self._alert("crit", e, f"paper:{rt.id}:{e['key']}"))
            elif not live:
                continue                                        # bước cũ (bắt kịp): không spam
            elif e["type"] in ("kill_switch_reset", "halt_released", "strategy_error"):
                alerts.append(self._alert("warn" if e["type"] != "halt_released" else "info", e, f"paper:{rt.id}:{e['key']}"))
            elif e["type"] == "rebalance" and e["data"].get("orders"):
                alerts.append(self._alert("info", e, f"paper:{rt.id}:{e['key']}"))
        if fills and live:
            body = "\n".join(f"{f['data']['side']} {f['data']['qty']:g} {f['data']['symbol']} @ {f['data']['price']:.6g}" for f in fills)
            alerts.append({"level": "info", "title": f"[MÔ PHỎNG] {rt.id}: khớp {len(fills)} lệnh mô phỏng",
                           "body": f"{body}\n{SIMULATION_LABEL}", "tags": ["paper", "fill", rt.id],
                           "dedupe_key": f"paper:{rt.id}:fills:{res.close_ts.isoformat()}"})
        for a in alerts:
            try:
                await self.bus.publish(ALERTS_STREAM, make_event("alert", "paper-trader", a))
            except Exception:  # noqa: BLE001
                log.exception("không phát được alert")

    @staticmethod
    def _alert(level: str, e: dict, key: str) -> dict:
        return {"level": level, "title": e["message"][:120], "body": f"{e['message']}\n{SIMULATION_LABEL}",
                "tags": ["paper", e["type"], e["data"].get("kind", "")][:3], "dedupe_key": key}

    # ------------------------------------------------------------------ lệnh quản trị (vẫn chỉ là mô phỏng)
    async def command(self, account_id: str, cmd: str, reason: str = "") -> dict:
        async with self.lock:
            rt = self.accounts.get(account_id)
            if rt is None:
                raise KeyError(account_id)
            ts = datetime.now(timezone.utc)
            if cmd == "reset":
                ev = rt.engine.manual_reset(ts)
            elif cmd == "halt":
                ev = rt.engine.manual_halt(ts, reason or "manual")
            else:
                raise ValueError(cmd)
            new = await self.store.save_manual(account_id, rt.engine.state, [ev])
            if self.bus is not None and new:
                await self.bus.publish(EVENTS_STREAM, make_event(f"paper.{ev['type']}", "paper-trader",
                                                                 {"account_id": account_id, "simulation": True, "message": ev["message"], **ev["data"]}))
                await self.bus.publish(ALERTS_STREAM, make_event("alert", "paper-trader", self._alert("crit" if cmd == "halt" else "warn", ev, f"paper:{account_id}:{ev['key']}")))
            STATUS.labels(account_id).set(STATUS_NUM.get(rt.engine.state.status, 0))
            return {"account_id": account_id, "status": rt.engine.state.status, "event": ev["message"]}


async def loop(runner: Runner, interval: int, stop: asyncio.Event) -> None:
    await asyncio.sleep(min(5, interval))
    while not stop.is_set():
        try:
            await runner.run_cycle()
        except Exception:  # noqa: BLE001
            CYCLES.labels("error").inc()
            runner.last = {"status": "lỗi", "generated_at": datetime.now(timezone.utc).isoformat()}
            log.exception("paper: chu kỳ lỗi")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def risk_windows_fn(cfg: dict):
    """Nguồn cửa sổ rủi ro tin: cấu hình tĩnh `news_windows` + (nếu có) endpoint /v1/risk-windows. Lỗi nguồn -> chỉ dùng tĩnh."""
    static = []
    for w in cfg.get("news_windows") or []:
        static.append({**w, "start": parse_ts(w["start"]), "end": parse_ts(w["end"])})
    url = cfg.get("risk_windows_url") or ""
    cache: dict[str, Any] = {"t": 0.0, "v": []}
    tok_env = cfg.get("risk_windows_token_env") or ""

    async def fn(now: datetime) -> list[dict]:
        out = list(static)
        if not url:
            return out
        if time.time() - cache["t"] > 300:
            try:
                import httpx
                hdr = {"X-API-Key": os.getenv(tok_env, "")} if tok_env else {}
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(url, headers=hdr)
                r.raise_for_status()
                data = r.json()
                parsed, seen = [], set()
                if isinstance(data, dict) and "symbols" in data:       # định dạng api-gateway /v1/risk-windows (cửa sổ đã gồm T-15..T+30)
                    for st in data["symbols"]:
                        for e in (st.get("current") or []) + (st.get("upcoming") or []):
                            k = (st["symbol"], e.get("source"), e.get("event_id"))
                            s_, e_ = parse_ts(e.get("window_start")), parse_ts(e.get("window_end"))
                            if k in seen or not (s_ and e_):
                                continue
                            seen.add(k)
                            parsed.append({"start": s_, "end": e_, "symbols": [st["symbol"]], "title": e.get("title") or "news", "padded": True})
                else:
                    items = data.get("items", data) if isinstance(data, dict) else data
                    for w in items:
                        s_, e_ = parse_ts(w.get("start") or w.get("ts_start")), parse_ts(w.get("end") or w.get("ts_end"))
                        if s_ and e_:
                            parsed.append({"start": s_, "end": e_, "currencies": w.get("currencies") or [], "symbols": w.get("symbols") or [],
                                           "title": w.get("title") or w.get("event") or "news"})
                cache["v"] = parsed
            except Exception as ex:  # noqa: BLE001
                log.warning("risk-windows không khả dụng (%s) — dùng cấu hình tĩnh", ex)
            cache["t"] = time.time()
        return out + cache["v"]
    return fn
