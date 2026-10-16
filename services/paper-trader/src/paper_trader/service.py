"""Lớp dịch vụ chất lượng/quản trị cho paper: gom perfx + tca + drift + card + hash-chain thành báo cáo theo tài khoản, và Monitor định kỳ
(xác minh chuỗi, giám sát suy giảm -> alerts.out + journal). CHỈ ĐỌC/tính toán trên journal; ghi duy nhất sự kiện cảnh báo vào paper_events (mô phỏng)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from prometheus_client import Gauge
from tscommon import make_event

from . import SIMULATION_LABEL, card as cardmod, chain, drift as driftmod, perfx, tca as tcamod
from .models import parse_ts
from .perf import daily_returns, equity_series

log = logging.getLogger("paper")

CHAIN_OK = Gauge("paper_chain_ok", "1 = hash-chain nguyên vẹn, 0 = đứt/bị sửa", ["account"])
DRIFT_STATUS = Gauge("paper_drift_status", "-1 chưa đủ mẫu, 0 xanh, 1 vàng, 2 đỏ", ["account"])
CONFIG_VERSION = Gauge("paper_config_version", "Phiên bản cấu hình hiện hành của tài khoản", ["account"])
DRIFT_NUM = {"insufficient": -1, "n/a": -1, "green": 0, "yellow": 1, "red": 2}
BENCH_DEFAULT = ("bh_6040", "bh_fx")
TTL = 120.0


def _j(x: Any) -> Any:
    return json.loads(x) if isinstance(x, str) else (x or {})


class Anchors:
    """Neo `seq:hash` đầu chuỗi ở NƠI KHÁC DB (Redis; lỗi -> bộ nhớ) để phát hiện viết lại lịch sử kể cả khi chuỗi bị tính lại."""
    def __init__(self, redis=None):
        self.r, self.mem = redis, {}

    async def get(self, aid: str) -> dict | None:
        if self.r is not None:
            try:
                v = await self.r.get(f"paper:chain_anchor:{aid}")
                if v:
                    seq, _, h = (v.decode() if isinstance(v, bytes) else v).partition(":")
                    return {"seq": int(seq), "hash": h}
            except Exception:  # noqa: BLE001
                pass
        return self.mem.get(aid)

    async def set(self, aid: str, seq: int, h: str) -> None:
        self.mem[aid] = {"seq": seq, "hash": h}
        if self.r is not None:
            try:
                await self.r.set(f"paper:chain_anchor:{aid}", f"{seq}:{h}")
            except Exception:  # noqa: BLE001
                pass


class QualityService:
    def __init__(self, store, cards: dict[str, dict], anchors: Anchors | None = None):
        self.store, self.cards, self.anchors = store, cards, anchors or Anchors()
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self.verify_state: dict[str, dict] = {}

    # ------------------------------------------------------------------ tiện ích
    async def _acct(self, aid: str) -> dict | None:
        return await self.store.get_account(aid)

    async def _cached(self, kind: str, aid: str, fn, fresh: bool = False):
        k = (kind, aid)
        hit = self._cache.get(k)
        if hit and not fresh and time.time() - hit[0] < TTL:
            return hit[1]
        v = await fn()
        self._cache[k] = (time.time(), v)
        return v

    def _card(self, row: dict) -> dict | None:
        return cardmod.card_for(self.cards, row["strategy"])

    def _expectation(self, row: dict) -> dict | None:
        return cardmod.expectation_for(self._card(row), row["account_id"])

    # ------------------------------------------------------------------ hiệu suất
    async def performance(self, aid: str, fresh: bool = False) -> dict | None:
        async def run():
            r = await self._acct(aid)
            if not r:
                return None
            cfg, st = _j(r.get("config")), _j(r.get("state"))
            eq = await self.store.equity(aid, 20000)
            benches: dict[str, list[dict]] = {}
            for b in dict.fromkeys([r.get("benchmark_id"), *BENCH_DEFAULT]):
                if b and b != aid:
                    rows = await self.store.equity(b, 20000)
                    if rows:
                        benches[b] = rows
            fills = await self.store.all_fills(aid)
            pos = await self.store.positions(aid)
            exp = self._expectation(r)
            rep = await asyncio.to_thread(perfx.report, eq, benches, float(r["initial_capital"]), int(cfg.get("periods_per_year") or 252), fills, pos,
                                          float((st.get("costs") or {}).get("swap", 0.0)), r["base_ccy"], exp)
            rep["account_id"] = aid
            rep["benchmark_id"] = r.get("benchmark_id")
            rep["config"] = self._cfg_info(r, await self.store.config_versions(aid))
            return rep
        return await self._cached("perf", aid, run, fresh)

    @staticmethod
    def _cfg_info(r: dict, versions: list[dict]) -> dict:
        cfg = _j(r.get("config"))
        return {"config_hash": cfg.get("config_hash"), "params_hash": cfg.get("params_hash"), "version": cfg.get("config_version"),
                "versions": [{"version": v["version"], "config_hash": v["config_hash"], "created_at": v["created_at"].isoformat()
                              if hasattr(v["created_at"], "isoformat") else v["created_at"]} for v in versions]}

    # ------------------------------------------------------------------ TCA
    async def tca(self, aid: str, fresh: bool = False) -> dict | None:
        async def run():
            r = await self._acct(aid)
            if not r:
                return None
            cfg, st = _j(r.get("config")), _j(r.get("state"))
            eq = await self.store.equity(aid, 20000)
            fills = await self.store.all_fills(aid)
            exp = self._expectation(r)
            rep = await asyncio.to_thread(tcamod.report, fills, cfg.get("assumptions") or {}, st.get("costs") or {}, float(st.get("traded_notional") or 0.0),
                                          eq, float(r["initial_capital"]), int(cfg.get("periods_per_year") or 252), exp)
            rep["account_id"] = aid
            if not cfg.get("assumptions"):
                rep["warning"] = "chưa có `assumptions` trong cấu hình lưu (chờ chu kỳ khởi động sau khi nâng cấp)"
            return rep
        return await self._cached("tca", aid, run, fresh)

    # ------------------------------------------------------------------ suy giảm
    @staticmethod
    def daily_cost_ratio(eq_rows: list[dict], fills: list[dict], initial: float) -> pd.Series:
        """Chi phí ngày (spread+trượt giá+phí+thuế+swap) / equity phiên trước -> cộng ngược vào lợi suất để có lợi suất GỘP."""
        eq = equity_series(eq_rows)
        if eq.empty:
            return pd.Series(dtype=float)
        d = eq.resample("1D").last().dropna()
        prev = d.shift(1)
        prev.iloc[0] = initial
        cost = pd.Series(0.0, index=d.index)
        for f in fills:                               # fill tại open bar T -> đóng ở T+1 ngày (D1)
            k = (pd.Timestamp(f["ts"]) + pd.Timedelta(days=1)).floor("D")
            if k in cost.index:
                cost[k] += float(f.get("spread_cost") or 0) + float(f.get("slippage_cost") or 0) + float(f.get("commission") or 0) + float(f.get("tax") or 0)
        for e in eq_rows:
            k = pd.Timestamp(e["ts"]).floor("D")
            if k in cost.index:
                cost[k] += float(e.get("swap_cost") or 0)
        return (cost / prev).fillna(0.0)

    async def drift(self, aid: str, fresh: bool = False) -> dict | None:
        async def run():
            r = await self._acct(aid)
            if not r:
                return None
            cfg = _j(r.get("config"))
            ppy = int(cfg.get("periods_per_year") or 252)
            eq = await self.store.equity(aid, 20000)
            fills = await self.store.all_fills(aid)
            tc = await self.tca(aid, fresh)
            ratio = ((tc or {}).get("overall") or {}).get("ratio")
            rn = daily_returns(equity_series(eq), float(r["initial_capital"]))
            cost = self.daily_cost_ratio(eq, fills, float(r["initial_capital"]))
            rep = await asyncio.to_thread(driftmod.report, rn, cost, self._expectation(r), ppy, ratio, len(fills))
            rep["account_id"] = aid
            return rep
        return await self._cached("drift", aid, run, fresh)

    # ------------------------------------------------------------------ hash-chain
    async def verify(self, aid: str, fresh: bool = True) -> dict | None:
        async def run():
            r = await self._acct(aid)
            if not r:
                return None
            entries = await self.store.chain_entries(aid)
            live, status = await self.store.chain_live(aid)
            rep = await asyncio.to_thread(chain.verify, aid, entries, live, status, await self.anchors.get(aid))
            rep["checked_at"] = datetime.now(timezone.utc).isoformat()
            rep["chain_enabled"] = bool(entries)
            if not entries:
                rep["ok"] = None
                rep["note"] = "chuỗi trống (chưa áp migration 004 hoặc tài khoản mới)"
            rep["tamper_evident"] = "Phát hiện sửa/xoá/chèn bản ghi; KHÔNG chống được kẻ có quyền superuser tính lại cả chuỗi (neo `anchor` ngoài DB giảm rủi ro này)."
            self.verify_state[aid] = rep
            return rep
        return await self._cached("verify", aid, run, fresh)

    # ------------------------------------------------------------------ strategy card
    async def card(self, aid: str, fresh: bool = False) -> dict | None:
        r = await self._acct(aid)
        if not r:
            return None
        cd = self._card(r)
        cfg, st = _j(r.get("config")), _j(r.get("state"))
        versions = await self.store.config_versions(aid)
        perf = await self.performance(aid, fresh)
        dr = await self.drift(aid, fresh)
        tc = await self.tca(aid, fresh)
        vs = self.verify_state.get(aid) or await self.verify(aid)
        evs = await self.store.events(aid, 1000)
        n_reb = sum(1 for e in evs if e["type"] == "rebalance")
        incep = st.get("inception_ts")
        acct = {"account_id": aid, "replay": bool(cfg.get("start_at")), "meaningful": bool(r.get("meaningful", True)), "deprecated": bool(cfg.get("deprecated")),
                "status": r.get("status", "active"), "inception": parse_ts(incep)}
        ev = cardmod.evaluate(cd, acct, perf, dr, tc, (vs or {}).get("ok"), versions, int(st.get("n_fills") or 0), n_reb, datetime.now(timezone.utc), cfg.get("params_hash"))
        pub = None
        if cd:
            pub = {k: v for k, v in cd.items() if not k.startswith("_")}
        return {"account_id": aid, "name": r["name"], "strategy": r["strategy"], "card": pub, "expectation": self._expectation(r), "evaluation": ev,
                "config": self._cfg_info(r, versions), "inception": incep}

    async def warm_governance(self, stop: asyncio.Event, every: float = 25.0) -> None:
        """Vòng nền làm nóng cache governance (kể cả ngay sau restart) -> request người dùng luôn trúng cache."""
        while not stop.is_set():
            try:
                self._gov_cache = (time.monotonic(), await self._governance_compute())
            except Exception:  # noqa: BLE001
                log.exception("warm governance lỗi")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=every)

    async def governance(self) -> dict:
        """Tổng quan cho UI: mọi tài khoản không bị đóng băng — giai đoạn, drift, chain, phiên bản cấu hình.
        Cache 60 s (được vòng warm_governance làm nóng mỗi 25 s) (tính card+drift cho mọi tài khoản ~1,2 s > ngân sách p95 500 ms; QA API 2026-10-15)."""
        c = getattr(self, "_gov_cache", None)
        if c and time.monotonic() - c[0] < 60:
            return c[1]
        out = await self._governance_compute()
        self._gov_cache = (time.monotonic(), out)
        return out

    async def _governance_compute(self) -> dict:
        items = []
        for r in await self.store.list_accounts():
            cfg = _j(r.get("config"))
            if cfg.get("deprecated"):
                continue
            c = await self.card(r["account_id"])
            dr = await self.drift(r["account_id"])
            vs = self.verify_state.get(r["account_id"]) or await self.verify(r["account_id"])
            items.append({"account_id": r["account_id"], "name": r["name"], "strategy": r["strategy"], "meaningful": bool(r.get("meaningful", True)),
                          "stage": c["evaluation"]["stage"], "stage_label": c["evaluation"]["stage_label"], "progress": c["evaluation"].get("progress"),
                          "failing": c["evaluation"].get("failing"), "drift": (dr or {}).get("status"), "diagnosis": (dr or {}).get("diagnosis"),
                          "chain_ok": (vs or {}).get("ok"), "chain_entries": (vs or {}).get("entries"), "config_version": c["config"].get("version"),
                          "config_hash": c["config"].get("config_hash")})
        return {"items": items, "cards": [{"id": k, "name": v.get("name"), "version": v.get("version"), "declared_stage": v.get("declared_stage")} for k, v in self.cards.items()]}


class Monitor:
    """Định kỳ: xác minh hash-chain, giám sát suy giảm; cảnh báo khi đổi trạng thái (alerts.out) + ghi sự kiện vào journal."""
    def __init__(self, runner, service: QualityService, interval: float = 3600.0):
        self.runner, self.svc, self.interval = runner, service, interval
        self.last = 0.0
        self.prev_chain: dict[str, bool | None] = {}
        self.prev_drift: dict[str, str] = {}

    async def tick(self, now: datetime, force: bool = False) -> dict:
        if not force and time.time() - self.last < self.interval:
            return {"skipped": True}
        self.last = time.time()
        out: dict[str, Any] = {}
        for aid, rt in self.runner.accounts.items():
            try:
                v = await self.svc.verify(aid, fresh=True)
                ok = (v or {}).get("ok")
                CHAIN_OK.labels(aid).set(1 if ok is not False else 0)
                cv = (await self.runner.store.get_account(aid) or {}).get("config")
                if cv:
                    CONFIG_VERSION.labels(aid).set(float(_j(cv).get("config_version") or 0))
                if ok is False and self.prev_chain.get(aid) is not False:
                    await self._alert(rt, now, "crit", f"[MÔ PHỎNG] {aid}: HASH-CHAIN ĐỨT/BỊ SỬA ({v['problem_counts']})",
                                      f"Journal paper của {aid} không còn khớp chuỗi băm: {v['problem_counts']}. Rà soát ngay (/v1/paper/accounts/{aid}/verify).",
                                      f"chain_break:{v['entries']}", "chain_break")
                if ok:
                    h = v["head"]
                    await self.svc.anchors.set(aid, h["seq"], h["hash"])
                self.prev_chain[aid] = ok
                out[aid] = {"chain_ok": ok}
                if rt.deprecated or rt.replay or not rt.engine.strategy.meaningful:
                    continue
                d = await self.svc.drift(aid, fresh=True)
                stt = (d or {}).get("status", "insufficient")
                DRIFT_STATUS.labels(aid).set(DRIFT_NUM.get(stt, -1))
                out[aid]["drift"] = stt
                prev = self.prev_drift.get(aid)
                if stt == "red" and prev != "red":                     # vàng chỉ hiển thị trên UI (quan sát liên tục -> báo động giả nhiều)
                    await self._alert(rt, now, "crit", f"[MÔ PHỎNG] {aid}: giám sát suy giảm {stt.upper()} — {d.get('diagnosis_text', '')}",
                                      f"{d.get('diagnosis_text', '')}. n={d.get('n_days')} ngày. Chẩn đoán: {d.get('diagnosis')}. Đây là tín hiệu để RÀ SOÁT, không phải kết luận.\n{SIMULATION_LABEL}",
                                      f"drift:{stt}:{now.date().isoformat()}", "drift_alert")
                self.prev_drift[aid] = stt
            except Exception:  # noqa: BLE001
                log.exception("monitor: lỗi tài khoản %s", aid)
        return out

    async def _alert(self, rt, now: datetime, level: str, title: str, body: str, key: str, etype: str) -> None:
        ev = {"key": f"{key}:{now.date().isoformat()}" if etype == "chain_break" else key, "type": etype, "severity": "crit" if level == "crit" else "warn",
              "ts": now, "message": title, "data": {"kind": etype}}
        try:
            await self.runner.store.save_manual(rt.id, rt.engine.state, [ev])
        except Exception:  # noqa: BLE001
            log.exception("monitor: không ghi được sự kiện %s", etype)
        bus = self.runner.bus
        if bus is None or not self.runner.cfg.get("alerts_enabled", True):
            return
        try:
            await bus.publish("alerts.out", make_event("alert", "paper-trader", {"level": level, "title": title[:140], "body": body,
                                                                                  "tags": ["paper", etype, rt.id], "dedupe_key": f"paper:{rt.id}:{key}"}))
        except Exception:  # noqa: BLE001
            log.exception("monitor: không phát được alert")
