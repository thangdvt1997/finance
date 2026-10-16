"""Vòng xử lý: pattern.signals -> lưu -> ảnh -> thông báo -> PAPER; theo dõi lệnh paper mở trên nến đã đóng."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from prometheus_client import Counter, Gauge

from . import annot, paper
from .guardrail import KILL_KEY, Guardrail
from .notify import Ntfy, close_text, signal_text
from .store import _dt

log = logging.getLogger("pattern-scan")
STREAM, GROUP = "pattern.signals", "pattern-scan"
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}

EVENTS = Counter("pattern_scan_events_total", "Sự kiện pattern.signal đã xử lý", ["state", "live"])
RENDER = Counter("pattern_scan_render_total", "Kết quả render ảnh", ["result"])
TRADES = Counter("pattern_scan_paper_trades_total", "Lệnh paper", ["action"])
OPEN = Gauge("pattern_scan_paper_open", "Số lệnh paper đang mở")
LAST_OK = Gauge("pattern_scan_last_success_timestamp", "Unix time vòng theo dõi thành công gần nhất")


def _tfsec(tf: str) -> int:
    return TF_SECONDS.get(tf, 900)


def _cand(rows: list[dict]) -> list[dict]:
    return [{"t": r["ts_open"].timestamp(), "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])} for r in rows]


class Scanner:
    def __init__(self, cfg: dict, store, notifier: Ntfy | None = None, clock=lambda: datetime.now(timezone.utc)):
        self.cfg, self.store, self.ntfy, self.clock = cfg, store, notifier, clock
        self.last: dict = {"status": "chưa chạy"}
        self.guard = Guardrail(cfg, events_reader=self._cal, trades_reader=lambda: self.store.trades(None, 20000))
        self.kill_get = None        # async () -> str|None; lifespan nối tới Redis (cờ do master bật qua ai-trading)
        self.guard.kill_reader = self._kill

    async def _kill(self):
        return await self.kill_get() if self.kill_get else None

    async def _cal(self, now: datetime) -> list[dict]:
        return await self.store.calendar_events(now - timedelta(hours=3), now + timedelta(hours=2))

    # ------------------------------------------------------------------ ảnh
    async def _prepare(self, p: dict):
        rc = self.cfg["render"]
        rows = await self.store.bars_until(p["symbol"], p["tf"], _dt(p["bar_ts"]), int(rc.get("max_bars", 260)) + 200)
        cs = _cand([r for r in rows if r["o"] and r["h"] and r["l"] and r["c"]])
        if len(cs) < 20:
            return None, None, []
        start = annot.window_start(p, [c["t"] for c in cs], int(rc.get("bars_before", 40)))
        cs = cs[max(start, len(cs) - int(rc.get("max_bars", 260))):]
        ann, marks = annot.build(p, cs, float(rc.get("tz_offset_h", 7)))
        return cs, ann, marks

    async def render_marks(self, p: dict) -> tuple[None, list[dict]]:
        """Điểm đánh dấu (pivot/kích hoạt) cho biểu đồ tương tác — cùng logic với ảnh."""
        _, _, marks = await self._prepare(p)
        return None, marks

    async def render(self, p: dict) -> tuple[bytes | None, list[dict]]:
        rc = self.cfg["render"]
        try:
            cs, ann, marks = await self._prepare(p)
        except Exception:  # noqa: BLE001 - lỗi đọc nến: lưu sự kiện không ảnh, repair() làm bù sau
            RENDER.labels("error").inc()
            log.exception("đọc nến lỗi %s", p.get("setup_id"))
            return None, []
        if cs is None:
            RENDER.labels("no_bars").inc()
            return None, []
        if not rc.get("enabled", True):
            return None, marks
        try:
            from pattern_render import render_png_bytes
            sz = rc.get("size", [1600, 800])
            png = await asyncio.to_thread(render_png_bytes, cs, ann, size=(int(sz[0]), int(sz[1])), max_kb=int(rc.get("max_kb", 180)))
            RENDER.labels("ok").inc()
            return png, marks
        except Exception:  # noqa: BLE001
            RENDER.labels("error").inc()
            log.exception("render lỗi %s", p.get("setup_id"))
            return None, marks

    # ------------------------------------------------------------------ 1 sự kiện
    async def handle(self, p: dict, received: datetime | None = None, allow_notify: bool = True) -> dict:
        received = received or self.clock()
        need = ("setup_id", "pattern", "symbol", "tf", "state", "bar_ts", "ts")
        if any(not p.get(k) for k in need):
            return {"skip": "thiếu trường"}
        en = self.cfg.get("patterns_enabled")
        if en is not None and p["pattern"] not in en:
            return {"skip": "kịch bản tắt"}
        live = (received - _dt(p["ts"])).total_seconds() <= int(self.cfg["fresh_bars"]) * _tfsec(p["tf"])
        eid = await self.store.insert_event(p, live)
        if eid is None:
            return {"skip": "trùng"}
        EVENTS.labels(p["state"], str(live).lower()).inc()
        png, _ = await self.render(p)
        if png:
            await self.store.put_media(eid, png)
        out = {"event_id": eid, "live": live, "image": bool(png)}
        pc = self.cfg["paper"]
        if p["state"] == "triggered" and pc.get("enabled", True):
            t = paper.open_trade(p, paper.cost_bps_for(p["symbol"], pc.get("cost_bps") or {}), replay=not live)
            if t is not None and live:      # guardrail chỉ áp cho tín hiệu live (replay/backfill lịch sử không bị chặn theo thời gian thực)
                dec = await self.guard.check(p, self.clock())
                if not dec["allow"]:
                    TRADES.labels("blocked_" + dec["kind"]).inc()
                    out["blocked"] = dec["reason"]
                    t = None
                elif dec.get("size"):
                    t["guard"] = dec["size"]
            if t is not None:
                tid = await self.store.insert_trade(t)
                out["trade_id"] = tid
                if tid:
                    TRADES.labels("open").inc()
        nc = self.cfg["notify"]
        if (allow_notify and live and self.ntfy is not None and nc.get("enabled", True) and p["state"] in (nc.get("states") or [])
                and float(p.get("score") or 0) >= float(nc.get("min_score", 0))):
            title, msg = signal_text(p)
            ok = await self.ntfy.send(title, msg, png, filename=f"{p['pattern']}_{p['symbol'].replace(':', '-')}_{p['tf']}.png",
                                      priority=4 if p["state"] == "triggered" else 3)
            if not ok and png:      # ntfy chưa bật đính kèm -> vẫn gửi chữ
                ok = await self.ntfy.send(title, msg)
            out["notified"] = ok
        return out

    # ------------------------------------------------------------------ theo dõi lệnh paper
    async def monitor(self) -> dict:
        now = self.clock()
        pc = self.cfg["paper"]
        opened = await self.store.trades("open", 1000)
        closed_n = 0
        for t in opened:
            dt = timedelta(seconds=_tfsec(t["tf"]))
            rows = await self.store.bars_after(t["symbol"], t["tf"], _dt(t["last_bar_ts"]), 500)
            changed = closed = False
            for r in rows:
                if r["ts_open"] + dt > now:        # chỉ nến ĐÃ ĐÓNG
                    break
                bar = {"ts": r["ts_open"].isoformat(), "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"]}
                changed = True
                if paper.step(t, bar, (r["ts_open"] + dt).isoformat(), int(pc.get("max_hold_bars", 192))):
                    closed = True
                    break
            if changed:
                await self.store.update_trade(t, closed)
            if closed:
                closed_n += 1
                TRADES.labels("close").inc()
                nc = self.cfg["notify"]
                if self.ntfy is not None and nc.get("enabled", True) and nc.get("on_close", True) and not t.get("replay"):
                    await self.ntfy.send(*close_text(t), tags="white_check_mark" if t["result_r"] > 0 else "x")
        OPEN.set(len(opened) - closed_n)
        LAST_OK.set(time.time())
        self.last = {"status": "ok", "at": now.isoformat(), "open": len(opened) - closed_n, "closed_now": closed_n}
        return self.last

    async def repair(self) -> int:
        """Sự kiện đã lưu nhưng thiếu ảnh (lỗi DB/render giữa chừng) hoặc triggered thiếu lệnh paper -> làm bù (idempotent)."""
        days = float(self.cfg["backfill"].get("days", 3))
        evs = await self.store.events(self.clock() - timedelta(days=days), 5000)
        keys = {(t["setup_id"], t["symbol"], t["tf"]) for t in await self.store.trades(None, 5000)}
        n = 0
        for e in evs:
            p = {**e, "bar_ts": e["bar_ts"].isoformat(), "ts": e["ts"].isoformat()}
            if not e.get("has_image"):
                png, _ = await self.render(p)
                if png:
                    await self.store.put_media(e["id"], png)
                    n += 1
            pc = self.cfg["paper"]
            if e["state"] == "triggered" and pc.get("enabled", True) and (e["setup_id"], e["symbol"], e["tf"]) not in keys:
                t = paper.open_trade(p, paper.cost_bps_for(e["symbol"], pc.get("cost_bps") or {}), replay=not e.get("live"))
                if t is not None and e.get("live"):     # bù lệnh cho tín hiệu live cũng phải qua guardrail (không lách bằng repair)
                    dec = await self.guard.check(p, self.clock())
                    if not dec["allow"]:
                        t = None
                    elif dec.get("size"):
                        t["guard"] = dec["size"]
                if t is not None and await self.store.insert_trade(t):
                    TRADES.labels("open").inc()
                    n += 1
        return n

    async def backfill(self) -> int:
        """Bù sự kiện lỡ (stream giữ 24h / service tắt): đọc pattern_signals gần đây; cũ -> replay, không thông báo."""
        days = float(self.cfg["backfill"].get("days", 3))
        rows = await self.store.signals_since(self.clock() - timedelta(days=days))
        n = 0
        for r in rows:
            p = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items()}
            res = await self.handle(p, allow_notify=True)
            n += 1 if "event_id" in res else 0
        await self.repair()
        return n


async def consume_loop(sc: Scanner, bus, consumer: str, stop: asyncio.Event) -> None:
    from tscommon import Event  # noqa: F401
    await bus.ensure_group(STREAM, GROUP)
    for mid, fields in await bus.pending_own(STREAM, GROUP, consumer):   # tin đã giao nhưng chưa ack (restart)
        try:
            from tscommon.events import Event as Ev
            ev = Ev.model_validate_json(fields["e"])
            if ev.type == "pattern.signal":
                await sc.handle(ev.payload)
            await bus.ack(STREAM, GROUP, mid)
        except Exception:  # noqa: BLE001
            log.exception("xử lý lại tin treo lỗi %s", mid)
    while not stop.is_set():
        try:
            async for mid, ev in bus.consume(STREAM, GROUP, consumer, block_ms=2000, count=20):
                try:
                    if ev.type == "pattern.signal":
                        await sc.handle(ev.payload)
                    await bus.ack(STREAM, GROUP, mid)
                except Exception:  # noqa: BLE001 - không ack: lần khởi động sau xử lý lại (idempotent)
                    log.exception("xử lý pattern.signal lỗi %s", mid)
                if stop.is_set():
                    break
        except Exception:  # noqa: BLE001
            log.exception("consume lỗi; thử lại sau 5s")
            await asyncio.sleep(5)


async def periodic(fn, interval: float, stop: asyncio.Event, first_delay: float = 5) -> None:
    await asyncio.sleep(first_delay)
    while not stop.is_set():
        try:
            await fn()
        except Exception:  # noqa: BLE001
            log.exception("tác vụ định kỳ lỗi: %s", getattr(fn, "__name__", fn))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
