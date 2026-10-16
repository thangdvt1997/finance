"""Vòng đánh giá quy tắc người dùng: tick định kỳ + phản ứng theo md.quotes; kích hoạt -> ghi lịch sử + phát alerts.out."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge
from tscommon import Bus, make_event

from .evaluator import Evaluator, combine
from .notifications import LEVEL_SEVERITY, Notifier
from .store import rule_out, status_of

log = logging.getLogger("alert_rules.runner")

FIRED = Counter("alert_rules_fired_total", "Số lần quy tắc người dùng kích hoạt", ["level"])
EVAL_ERRORS = Counter("alert_rules_eval_errors_total", "Lỗi khi đánh giá quy tắc")
ACTIVE = Gauge("alert_rules_active", "Số quy tắc đang hoạt động")
TICK_LAST = Gauge("alert_rules_last_tick_timestamp", "Thời điểm tick gần nhất (epoch)")

CHANNEL_TAG = {"ntfy": "ch:ntfy", "log": "ch:log", "telegram": "ch:telegram"}
QUOTE_EVAL_MIN_GAP_S = 1.0


class Runner:
    def __init__(self, store, evaluator: Evaluator, bus: Bus | None, clock=time.time, push=None, notifier: Notifier | None = None):
        self.store, self.ev, self.bus, self.clock, self.push = store, evaluator, bus, clock, push
        self.notifier = notifier or Notifier(store, push, clock)
        self._ver: dict[str, object] = {}
        self._rules: list[dict] = []
        self._rules_at = 0.0
        self._last_q_eval: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def _load(self, force: bool = False) -> list[dict]:
        if force or self.clock() - self._rules_at > 5:
            self._rules = [r for r in await self.store.list_rules() if r["enabled"]]
            self._rules_at = self.clock()
            ACTIVE.set(sum(1 for r in self._rules if status_of(r) == "active"))
        return self._rules

    def invalidate(self) -> None:
        self._rules_at = 0.0

    async def on_quote(self, symbol: str, bid, ask, ts: float, source) -> None:
        self.ev.state.on_quote(symbol, bid, ask, ts, source)
        now = self.clock()
        if now - self._last_q_eval.get(symbol, 0) < QUOTE_EVAL_MIN_GAP_S:
            return
        self._last_q_eval[symbol] = now
        rules = [r for r in await self._load() if any(c.get("type") == "price" and c.get("symbol") == symbol
                                                      for c in r["spec"]["conditions"])]
        for r in rules:
            await self._run_rule(r)

    async def tick(self) -> int:
        rules = await self._load(force=True)
        TICK_LAST.set(self.clock())
        n = 0
        for r in rules:
            n += await self._run_rule(r)
        return n

    async def _run_rule(self, r: dict) -> int:
        rid = str(r["id"])
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        if status_of(r, now) != "active":
            return 0
        if self._ver.get(rid) != r["updated_at"]:   # quy tắc vừa sửa: xoá trạng thái cũ
            self._ver[rid] = r["updated_at"]
            self.ev.forget(rid)
        spec = r["spec"]
        if r.get("owner_user_id") and any(c.get("type") == "account" and not c.get("account_id") for c in spec["conditions"]):
            return 0   # quy tắc của client PHẢI gắn tài khoản cụ thể: thiếu -> không đánh giá (không bao giờ nhìn thấy tài khoản khác)
        last = r.get("last_fired_at")
        if spec["mode"] == "repeat" and last and (now - last).total_seconds() < spec.get("cooldown_min", 60) * 60:
            return 0   # đang trong thời gian chờ: bỏ qua đánh giá
        async with self._lock:
            try:
                ok, res = await self.ev.evaluate_rule(rid, r["spec"], commit=True)
            except Exception:  # noqa: BLE001
                EVAL_ERRORS.inc()
                log.exception("đánh giá quy tắc %s lỗi", rid)
                return 0
            if ok is None:
                return 0
            if not ok:
                return 0
            return 1 if await self._fire(r, r["spec"], res, now) else 0

    async def _fire(self, r: dict, spec: dict, res, now: datetime) -> bool:
        rid = str(r["id"])
        once = spec["mode"] == "once"
        count = await self.store.claim_fire(rid, now, spec.get("cooldown_min", 60), once)
        if count is None:
            return False
        texts = [x.text for x in res if x.ok or spec["logic"] == "and"]
        title = f"Cảnh báo của bạn: {r['name']}"
        body = "\n".join(f"- {t}" for t in texts) + (f"\nGhi chú: {spec['note']}" if spec.get("note") else "")
        snapshot = {"logic": spec["logic"], "conditions": [{**c, **x.as_dict()} for c, x in zip(spec["conditions"], res, strict=True)]}
        syms = sorted({c["symbol"] for c in spec["conditions"] if c.get("symbol")})
        chans = spec.get("channels") or ["log"]
        owner = r.get("owner_user_id")
        if owner:
            # Quy tắc CÁ NHÂN: chỉ ghi sự kiện theo chủ sở hữu (app đọc /user/rule-events) + Web Push CHUNG tới thiết bị của họ.
            # KHÔNG phát alerts.out (kênh toàn cục: ntfy/telegram của người vận hành) -> không lộ cho người khác.
            ev = make_event("alert", "alert-rules", {"level": spec["level"], "title": title, "body": body})
            await self.store.add_event(rid, r["name"], spec["level"], title, body, snapshot, [c for c in chans if c in ("app", "push")] or ["app"],
                                       ev.id, now, owner)
            FIRED.labels(spec["level"]).inc()
            log.info("quy tắc cá nhân %s kích hoạt lần %s", rid, count)
            # Trung tâm thông báo: 1 thông báo kind `rule` cho mỗi sự kiện (dedupe theo id sự kiện) + Web Push chung nếu quy tắc bật kênh push và người dùng không tắt.
            await self.notifier.send(owner, "rule", LEVEL_SEVERITY.get(spec["level"], "info"), title, body, r.get("account_id"),
                                     dedupe_key=f"rule-event:{ev.id}", push="push" in chans)
            self.invalidate()
            return True
        payload = {"level": spec["level"], "title": title, "body": body,
                   "tags": ["user-rule", f"rule:{rid}", *[CHANNEL_TAG[c] for c in chans if c in CHANNEL_TAG], *syms],
                   "dedupe_key": f"user-rule:{rid}:{count}"}
        ev = make_event("alert", "alert-rules", payload)
        await self.store.add_event(rid, r["name"], spec["level"], title, body, snapshot, chans, ev.id, now)
        FIRED.labels(spec["level"]).inc()
        log.info("quy tắc %s (%s) kích hoạt lần %s", r["name"], rid, count)
        if self.bus:
            await self.bus.publish("alerts.out", ev)
        self.invalidate()
        return True

    async def preview(self, rid: str | None, spec: dict) -> dict:
        ok, res = await self.ev.evaluate_rule(rid or "preview", spec, commit=False)
        return {"result": ok, "conditions": [x.as_dict() for x in res]}


__all__ = ["Runner", "rule_out", "combine"]
