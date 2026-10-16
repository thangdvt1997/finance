"""Đồng bộ mẫu luật đội tài khoản (FLEET_MGMT mục 3-4): lấy assignments từ auth -> đánh giá -> gửi kết quả + điều kiện sự cố.
Phát alerts.out khi TRẠNG THÁI luật đổi; push chung cho khách đã opt-in. READ-ONLY. Thiếu FLEET_INTERNAL_TOKEN = tắt (endpoint cũ không ảnh hưởng)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from prometheus_client import Counter, Gauge, Histogram
from tscommon.events import make_event

from . import rules_engine as re_

log = logging.getLogger("risk-monitor.fleet")

STATE_HASH = "risk:rule_state"
RANK = {"green": 0, "yellow": 1, "red": 2}
BATCH = 500
G_RULE = Gauge("risk_rule_status", "Số kết quả luật theo trạng thái", ["status"])
H_EVAL = Histogram("risk_rules_eval_seconds", "Thời gian một chu kỳ đánh giá luật", buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60))
C_SYNC = Counter("risk_rules_sync_total", "Đồng bộ luật từ auth", ["result"])
C_POST = Counter("risk_rules_post_total", "Gửi kết quả luật tới auth", ["result"])
C_PUSH = Counter("risk_rules_push_total", "Yêu cầu push cho khách", ["result"])

SEV = {"ok": "ok", "warn": "warning", "crit": "critical"}


class FleetConfig:
    def __init__(self, auth_url: str, token: str, alert_rules_url: str, history_days: int = 45, series_ttl: float = 300.0,
                 cache_max_age: float = 600.0):
        self.auth_url, self.token, self.alert_rules_url = auth_url.rstrip("/"), token, alert_rules_url.rstrip("/")
        self.history_days, self.series_ttl, self.cache_max_age = history_days, series_ttl, cache_max_age

    @classmethod
    def from_env(cls, cfg: dict | None = None) -> "FleetConfig":
        c = (cfg or {}).get("fleet", {}) or {}
        return cls(os.getenv("FLEET_AUTH_URL", "http://auth:8000"), os.getenv("FLEET_INTERNAL_TOKEN", "").strip(),
                   os.getenv("ALERT_RULES_URL", "http://alert-rules:8000"), history_days=max(45, int(c.get("history_days", 45))))


async def urllib_http(method: str, url: str, token: str, body: dict | None = None, timeout: float = 10.0) -> tuple[int, dict | None]:
    """(status, json|None); status 0 = lỗi mạng. Token chỉ nằm trong header, không log."""
    def _do() -> tuple[int, dict | None]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL từ cấu hình nội bộ)
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, None
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return 0, None
    return await asyncio.to_thread(_do)


def budget_conditions(account_id: str, items: list[dict]) -> list[dict]:
    """Điều kiện sự cố từ ngân sách rủi ro hiện có (kind 'budget') để hộp sự cố gom theo nguyên nhân."""
    out = []
    for it in items:
        sev = SEV.get(it.get("status"))
        if sev is None:
            continue
        v, unit = it.get("value"), it.get("unit", "")
        detail = f"{it['label']}: {v:.2f}{unit} / hạn mức {it['limit']:g}{unit}" if v is not None else it["label"]
        out.append({"key": f"budget:{account_id}:{it['key']}", "account_id": account_id, "severity": sev, "kind": "budget",
                    "title": f"{it['label']}: {'vượt' if sev == 'critical' else 'gần'} hạn mức", "detail": detail, "cause_key": f"budget:{it['key']}"})
    return out


def _eval_jobs(jobs: list[tuple], now: datetime) -> list[tuple]:
    return [(aid, asg, re_.evaluate(kind, params, series=series, snapshot=snap, deal_times=deals, now=now))
            for aid, asg, kind, params, series, snap, deals in jobs]


class FleetEngine:
    def __init__(self, cfg: FleetConfig, redis, bus, http=urllib_http, clock=lambda: datetime.now(timezone.utc)):
        self.cfg, self.r, self.bus, self.http, self.clock = cfg, redis, bus, http, clock
        self.rules: dict = {"assignments": [], "client_push": {}}
        self.rules_mono: float | None = None
        self._series: dict[str, tuple[float, list]] = {}
        self._warned = False
        self.st: dict = {"last_sync_at": None, "last_sync_ok": None, "last_error": None, "last_eval_at": None, "eval_seconds": None,
                         "counts": {}, "alerts": 0, "pushes": 0, "post": None}
        self.results: list[dict] = []

    @property
    def enabled(self) -> bool:
        if not self.cfg.token:
            if not self._warned:
                log.info("FLEET_INTERNAL_TOKEN chưa đặt: engine luật đội tài khoản TẮT")
                self._warned = True
            return False
        return True

    # ---- đồng bộ luật ----
    async def sync_rules(self) -> bool:
        status, data = await self.http("GET", f"{self.cfg.auth_url}/internal/fleet/rules", self.cfg.token)
        now = time.monotonic()
        self.st["last_sync_at"] = self.clock().isoformat()
        if status == 200 and isinstance(data, dict) and isinstance(data.get("assignments"), list):
            self.rules = {"assignments": data["assignments"], "client_push": data.get("client_push") or {}, "rev": data.get("rev")}
            self.rules_mono = now
            self.st.update(last_sync_ok=True, last_error=None)
            C_SYNC.labels("ok").inc()
            return True
        err = f"auth trả {status}" if status else "không kết nối được auth"
        C_SYNC.labels("error").inc()
        if self.st.get("last_error") != err:
            log.warning("đồng bộ luật lỗi: %s (giữ bản cũ tối đa %ds)", err, int(self.cfg.cache_max_age))
        self.st.update(last_sync_ok=False, last_error=err)
        if self.rules_mono is None or now - self.rules_mono > self.cfg.cache_max_age:
            self.rules = {"assignments": [], "client_push": {}}          # bản cũ quá 10 phút: không đánh giá bằng dữ liệu cũ
        return False

    # ---- dữ liệu ----
    async def _get_series(self, src, account_id: str, snap: dict | None) -> list:
        hit = self._series.get(account_id)
        if hit and time.monotonic() - hit[0] < self.cfg.series_ttl:
            ser = hit[1]
        else:
            try:
                ser = list(await src.mt_equity(account_id, self.cfg.history_days))
            except Exception:  # noqa: BLE001
                log.exception("đọc chuỗi equity %s lỗi", account_id)
                ser = hit[1] if hit else []
            self._series[account_id] = (time.monotonic(), ser)
        ts, eq = (snap or {}).get("ts"), (snap or {}).get("equity")
        if ts is not None and eq is not None and (not ser or ts > ser[-1][0]):
            ser = ser + [(ts, float(eq))]
        return ser

    async def run(self, src, conditions: list[dict] | None = None) -> dict:
        """Một chu kỳ: sync -> đánh giá -> chuyển trạng thái (alerts/push) -> gửi results + conditions. Không ném lỗi ra ngoài."""
        if not self.enabled:
            return {}
        t0 = time.monotonic()
        now = self.clock()
        await self.sync_rules()
        asgs = [a for a in self.rules["assignments"] if isinstance(a, dict) and a.get("assignment_id")]
        results, names = [], {}
        if asgs:
            try:
                snaps = {r["account_id"]: r for r in await src.mt_accounts()}
            except Exception:  # noqa: BLE001
                log.exception("đọc snapshot lỗi")
                snaps = {}
            deals = None
            if any(a.get("kind") == "max_trades_day" for a in asgs) and hasattr(src, "deal_times"):
                try:
                    deals = await src.deal_times(2)
                except Exception:  # noqa: BLE001
                    log.exception("đọc deal lỗi")
            series = {}
            for aid in {x for a in asgs for x in a.get("accounts", [])}:
                series[aid] = await self._get_series(src, aid, snaps.get(aid))
            jobs = []
            for a in asgs:
                names[a["assignment_id"]] = a
                for aid in a.get("accounts", []):
                    jobs.append((aid, a["assignment_id"], a.get("kind"), a.get("params") or {}, series.get(aid, []), snaps.get(aid),
                                 None if deals is None else deals.get(aid, [])))
            for aid, asg, res in await asyncio.to_thread(_eval_jobs, jobs, now):
                snap_ts = (snaps.get(aid) or {}).get("ts")
                if snap_ts is not None and res["status"] != "na" and (now - snap_ts).total_seconds() > 900:
                    res["detail"] += f" [snapshot cũ {int((now - snap_ts).total_seconds() // 60)} phút]"
                results.append({"account_id": aid, "assignment_id": asg, **res, "evaluated_at": now.isoformat()})
        n_alerts, n_push = await self._transitions(results, names)
        post = await self._post(results, conditions or [])
        counts = {k: sum(1 for r in results if r["status"] == k) for k in ("green", "yellow", "red", "na")}
        for k, v in counts.items():
            G_RULE.labels(k).set(v)
        dt = time.monotonic() - t0
        H_EVAL.observe(dt)
        self.results = results
        self.st.update(last_eval_at=now.isoformat(), eval_seconds=round(dt, 3), counts=counts, alerts=n_alerts, pushes=n_push, post=post)
        return {"results": len(results), "alerts": n_alerts, "pushes": n_push, "post": post}

    # ---- chuyển trạng thái ----
    async def _transitions(self, results: list[dict], asgs: dict) -> tuple[int, int]:
        try:
            raw = await self.r.hgetall(STATE_HASH)
        except Exception:  # noqa: BLE001
            log.exception("đọc state luật lỗi")
            return 0, 0
        prev = {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in raw.items()}
        push_map = self.rules.get("client_push") or {}
        n_alerts = n_push = 0
        newstate: dict[str, str] = {}
        for res in results:
            if res["status"] not in RANK:
                continue
            key = f"{res['assignment_id']}:{res['account_id']}"
            was, cur = prev.get(key, "green"), res["status"]
            if cur == was:
                continue
            a = asgs.get(res["assignment_id"], {})
            ev = self._alert(res, a, was, cur)
            try:
                await self.bus.publish("alerts.out", make_event("alert", "risk-monitor", ev))
            except Exception:  # noqa: BLE001
                log.exception("phát cảnh báo luật lỗi")
                continue                                                  # không lưu state -> thử lại chu kỳ sau
            newstate[key] = cur
            n_alerts += 1
            if RANK[cur] > RANK[was] and a.get("notify_client") and res["account_id"] in push_map:
                n_push += await self._push(push_map[res["account_id"]])
        if newstate:
            await self.r.hset(STATE_HASH, mapping=newstate)
        live = {f"{r['assignment_id']}:{r['account_id']}" for r in results}
        gone = [k for k in prev if k not in live and k.split(":", 1)[0] not in asgs]
        if gone and asgs:
            await self.r.hdel(STATE_HASH, *gone)
        return n_alerts, n_push

    @staticmethod
    def _alert(res: dict, a: dict, was: str, cur: str) -> dict:
        aid, name = res["account_id"], a.get("name") or "luật"
        up = RANK[cur] > RANK[was]
        if cur == "green":
            lvl, title = "info", f"[{aid}] Đã về trong hạn mức luật: {name}"
        elif up:
            lvl = "crit" if cur == "red" else "warn"
            title = f"[{aid}] Luật {'VI PHẠM' if cur == 'red' else 'sát hạn mức'}: {name}"
        else:
            lvl, title = "info", f"[{aid}] Luật hạ xuống mức cảnh báo: {name}"
        return {"level": lvl, "title": title, "body": f"{res['detail']}. Chỉ cảnh báo (READ-ONLY), không tự động hành động.",
                "tags": ["risk-monitor", f"account:{aid}", f"rule:{res['assignment_id']}"],
                "dedupe_key": f"fleet-rule:{res['assignment_id']}:{aid}:{cur}"}

    async def _push(self, user_id: str) -> int:
        status, data = await self.http("POST", f"{self.cfg.alert_rules_url}/internal/notify", self.cfg.token, {"owner": user_id, "kind": "rule"})
        ok = status == 200
        C_PUSH.labels("ok" if ok else "error").inc()
        if not ok:
            log.warning("push khách lỗi (status=%s)", status)
        return int((data or {}).get("sent", 0)) if ok else 0

    # ---- gửi kết quả ----
    async def _post(self, results: list[dict], conds: list[dict]) -> dict:
        total = max(len(results), len(conds))
        out = {"batches": 0, "accepted": 0, "errors": 0, "last_status": None}
        for i in range(0, total, BATCH):
            status, data = await self.http("POST", f"{self.cfg.auth_url}/internal/fleet/results", self.cfg.token,
                                           {"results": results[i:i + BATCH], "conditions": conds[i:i + BATCH]})
            out["batches"] += 1
            out["last_status"] = status
            if status == 200:
                C_POST.labels("ok").inc()
                out["accepted"] += int((data or {}).get("accepted", 0))
            else:
                C_POST.labels("error").inc()
                out["errors"] += 1
                if status in (404, 503, 0):
                    break                                                  # auth chưa sẵn sàng: bỏ phần còn lại, thử lại chu kỳ sau
        return out

    def status(self, limit: int = 500) -> dict:
        a = self.rules.get("assignments", [])
        return {"read_only": True, "engine": "on" if self.cfg.token else "off", "assignments": len(a),
                "accounts": len({x for s in a for x in s.get("accounts", [])}), "rev": self.rules.get("rev"),
                "client_push_accounts": len(self.rules.get("client_push") or {}), **self.st, "results": self.results[:limit]}
