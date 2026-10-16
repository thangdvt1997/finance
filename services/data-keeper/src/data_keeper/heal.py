"""K2 - tu chua an toan + canh bao thong minh (data-keeper).

Hop dong: `async heal_cycle(ctx, matrix) -> list[dict]` (matrix tu inventory.build_matrix).
An toan:
  * Hanh dong CHI nam trong ALLOWED_ACTIONS; LLM khong ra lenh ha tang. Docker chi dung cho container trong ALLOWED_CONTAINERS.
  * DK_HEAL_DRY_RUN (mac dinh bat = "1"): chi ghi ke hoach/ nhat ky, khong tac dong.
  * Restart: toi da DK_HEAL_MAX_RESTARTS_PER_HOUR lan/gio + cooldown DK_HEAL_RESTART_COOLDOWN_S; stop -t 40 roi start (terminal can thoi gian luu settings).
  * docker-socket-proxy hien tai la CHI DOC (POST=0): POST bi chan -> hanh dong ghi la "planned" (khong loi). De thuc thi that can
    mot proxy rieng cho phep POST tren containers, tro bang DK_DOCKER_RESTART_URL (lead quyet dinh).
  * Chuyen nguon du phong: chua co duong noi an toan -> chi danh dau mã vao dk.actions (kind=failover_plan) + ghi tep ke hoach.
  * Canh bao: chi cho ma BROKEN khi thi truong MO (CLOSED khong bao), dedupe + cooldown, nguong so ma/ thoi gian lien tuc.
Ctx (duck-typing, moi thu tuy chon): ctx.db (asyncpg-like: execute/fetch), ctx.http (httpx.AsyncClient), ctx.now() -> datetime UTC.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("data_keeper.heal")

ALLOWED_ACTIONS = frozenset({"resync_symbols", "check_allow_url", "check_container", "restart_feed", "failover_plan", "alert"})
ALLOWED_CONTAINERS = frozenset({"mtlab-mt5-feed"})
BAD = ("BROKEN", "SLOW")

DDL = """
CREATE TABLE IF NOT EXISTS dk.actions (
  id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(),
  kind text NOT NULL, target text, status text NOT NULL, detail jsonb NOT NULL DEFAULT '{}'::jsonb);
CREATE INDEX IF NOT EXISTS dk_actions_ts ON dk.actions (kind, ts DESC);
"""
SCHEMA_SQL = DDL   # main.load_modules chạy lúc khởi động -> bảng dk.actions luôn có (api đọc)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class HealConfig:
    dry_run: bool = True
    container: str = "mtlab-mt5-feed"
    docker_url: str = "http://docker-socket-proxy:2375"            # doc (inspect/top/logs)
    docker_restart_url: str = ""                                    # proxy cho phep POST (trong = khong co duong ghi)
    feed_list_path: str = "/out/feed_symbols.txt"                   # thu muc /out cua feed (rw), ban sao danh sach ma mong muon
    plan_path: str = "/out/dk_failover_plan.json"
    max_restarts_per_hour: int = 2
    restart_cooldown_s: float = 900.0
    broken_min_symbols: int = 3             # tu bay nhieu ma BROKEN (thi truong mo) moi coi la su co feed
    broken_min_age_s: float = 300.0         # phai hong lien tuc > 5 phut
    failover_after_s: float = 3600.0        # ma hong > 1 gio du da chua -> danh dau failover
    alert_cooldown_s: float = 3600.0
    ntfy_url: str = ""                      # vd http://ntfy:80/tradingsys-alerts
    alert_webhook: str = ""                 # alert-service /webhook/alertmanager
    alert_token: str = ""
    cpu_warn_pct: float = 150.0             # tran container 1.5 cpu
    mem_warn_pct: float = 90.0

    @classmethod
    def from_env(cls) -> "HealConfig":
        return cls(
            dry_run=_env("DK_HEAL_DRY_RUN", "1").strip().lower() not in ("0", "false", "no", "off"),
            container=_env("DK_FEED_CONTAINER", "mtlab-mt5-feed"),
            docker_url=_env("DK_DOCKER_URL", "http://docker-socket-proxy:2375"),
            docker_restart_url=_env("DK_DOCKER_RESTART_URL", ""),
            feed_list_path=_env("DK_FEED_LIST_PATH", "/out/feed_symbols.txt"),
            plan_path=_env("DK_FAILOVER_PLAN_PATH", "/out/dk_failover_plan.json"),
            max_restarts_per_hour=int(_env("DK_HEAL_MAX_RESTARTS_PER_HOUR", "2")),
            restart_cooldown_s=float(_env("DK_HEAL_RESTART_COOLDOWN_S", "900")),
            broken_min_symbols=int(_env("DK_HEAL_BROKEN_MIN_SYMBOLS", "3")),
            broken_min_age_s=float(_env("DK_HEAL_BROKEN_MIN_AGE_S", "300")),
            failover_after_s=float(_env("DK_HEAL_FAILOVER_AFTER_S", "3600")),
            alert_cooldown_s=float(_env("DK_ALERT_COOLDOWN_S", "3600")),
            ntfy_url=_env("DK_NTFY_URL", "http://ntfy:80/tradingsys-alerts"),
            alert_webhook=_env("DK_ALERT_WEBHOOK", "http://alert-service:8000/webhook/alertmanager"),
            alert_token=_env("DK_ALERT_TOKEN", ""),
        )


@dataclass
class HealState:
    """Trang thai trong bo nho (hydrate tu dk.actions khi khoi dong)."""
    broken_since: dict[str, float] = field(default_factory=dict)
    restarts: list[float] = field(default_factory=list)
    last_alert: dict[str, float] = field(default_factory=dict)
    last_resync_sig: str = ""
    failover_marked: set[str] = field(default_factory=set)


_STATE = HealState()


def symbol_state(tfs: dict[str, dict]) -> str:
    # su co FEED thi hien o M1; khung cao (D1...) thieu la viec backfill/nap lich su, khong phai restart feed
    rt = {k: v for k, v in tfs.items() if k == "M1"} or tfs
    sts = [v.get("status", "OK") for v in rt.values()] or ["OK"]
    if "BROKEN" in sts:
        return "BROKEN"
    if "SLOW" in sts:
        return "SLOW"
    if all(s == "CLOSED" for s in sts):
        return "CLOSED"
    return "OK"


def _tick_alive(tfs: dict, now: datetime, max_age_s: float = 300.0) -> bool:
    lt = next((v.get("last_tick") for v in tfs.values() if v.get("last_tick")), None)
    if isinstance(lt, str):
        try:
            lt = datetime.fromisoformat(lt)
        except ValueError:
            return False
    if lt is None:
        return False
    if lt.tzinfo is None:
        lt = lt.replace(tzinfo=timezone.utc)
    return (now - lt).total_seconds() <= max_age_s


def classify(matrix: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"OK": [], "CLOSED": [], "SLOW": [], "BROKEN": []}
    for sym, tfs in matrix.items():
        out[symbol_state(tfs)].append(sym)
    return out


def _now(ctx: Any) -> datetime:
    f = getattr(ctx, "now", None)
    return f() if callable(f) else datetime.now(timezone.utc)


# ---------------- nhat ky ----------------
async def log_action(ctx: Any, kind: str, target: str, status: str, detail: dict | None = None) -> dict:
    assert kind in ALLOWED_ACTIONS, kind
    rec = {"kind": kind, "target": target, "status": status, "detail": detail or {}, "ts": _now(ctx).isoformat()}
    log.info("dk.action %s %s -> %s %s", kind, target, status, json.dumps(rec["detail"], ensure_ascii=False)[:300])
    db = getattr(ctx, "db", None)
    if db is not None:
        try:
            await db.execute("INSERT INTO dk.actions(kind,target,status,detail) VALUES($1,$2,$3,$4::jsonb)",
                             kind, target, status, json.dumps(rec["detail"], ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            log.warning("ghi dk.actions loi: %s", e)
    return rec


async def hydrate_state(ctx: Any, st: HealState = _STATE) -> None:
    """Khoi phuc so lan restart/canh bao tu dk.actions (khong vuot gioi han sau khi container data-keeper khoi dong lai)."""
    db = getattr(ctx, "db", None)
    if db is None:
        return
    try:
        await db.execute(DDL)
        rows = await db.fetch("SELECT kind, target, extract(epoch from ts) AS e FROM dk.actions "
                              "WHERE ts > now() - interval '2 hours' AND status IN ('done','sent') AND kind IN ('restart_feed','alert')")
        now = time.time()
        for r in rows:
            e = float(r["e"])
            if r["kind"] == "restart_feed":
                st.restarts.append(e)
            elif now - e < 86400:
                st.last_alert[r["target"]] = max(st.last_alert.get(r["target"], 0.0), e)
    except Exception as e:  # noqa: BLE001
        log.warning("hydrate loi: %s", e)


# ---------------- docker ----------------
class DockerAPI:
    def __init__(self, cfg: HealConfig, http: Any):
        self.cfg, self.http = cfg, http

    def _guard(self, name: str) -> None:
        if name not in ALLOWED_CONTAINERS:
            raise PermissionError(f"container ngoai allow-list: {name}")

    async def _get(self, path: str, **kw: Any):
        return await self.http.get(f"{self.cfg.docker_url}{path}", timeout=8.0, **kw)

    async def inspect(self, name: str) -> dict:
        self._guard(name)
        r = await self._get(f"/containers/{name}/json")
        r.raise_for_status()
        return r.json()

    async def stats(self, name: str) -> dict:
        self._guard(name)
        r = await self._get(f"/containers/{name}/stats", params={"stream": "false", "one-shot": "true"})
        r.raise_for_status()
        return r.json()

    async def top(self, name: str) -> str:
        self._guard(name)
        r = await self._get(f"/containers/{name}/top")
        r.raise_for_status()
        return json.dumps(r.json())

    async def logs(self, name: str, tail: int = 400) -> str:
        self._guard(name)
        r = await self._get(f"/containers/{name}/logs", params={"stdout": "1", "stderr": "1", "tail": str(tail)})
        r.raise_for_status()
        return r.content.decode("utf-8", "replace")

    async def restart_soft(self, name: str) -> tuple[bool, str]:
        """stop -t 40 + start qua proxy cho phep POST. Tra (da_thuc_thi, ly_do)."""
        self._guard(name)
        base = self.cfg.docker_restart_url
        if not base:
            return False, "khong co DK_DOCKER_RESTART_URL (proxy chi doc)"
        r = await self.http.post(f"{base}/containers/{name}/stop", params={"t": "40"}, timeout=60.0)
        if r.status_code == 403:
            return False, "proxy chan POST"
        if r.status_code not in (204, 304):
            return False, f"stop http {r.status_code}"
        r = await self.http.post(f"{base}/containers/{name}/start", timeout=20.0)
        return (r.status_code in (204, 304)), f"start http {r.status_code}"


def container_health(ins: dict | None, st: dict | None, top: str, cfg: HealConfig) -> dict:
    """Thuan tuy: danh gia container tu so lieu docker (de test)."""
    res: dict[str, Any] = {"ok": True, "problems": []}
    state = (ins or {}).get("State", {})
    if ins is not None and not state.get("Running", False):
        res["ok"] = False
        res["problems"].append("container khong chay")
    if st:
        try:
            cpu = st["cpu_stats"]; pre = st["precpu_stats"]
            dcpu = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
            dsys = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
            ncpu = cpu.get("online_cpus") or 1
            if dsys > 0:
                res["cpu_pct"] = round(dcpu / dsys * ncpu * 100, 1)
                if res["cpu_pct"] > cfg.cpu_warn_pct:
                    res["problems"].append(f"CPU {res['cpu_pct']}%")
            m = st["memory_stats"]
            res["mem_pct"] = round(m["usage"] / m["limit"] * 100, 1)
            if res["mem_pct"] > cfg.mem_warn_pct:
                res["problems"].append(f"RAM {res['mem_pct']}%")
        except (KeyError, TypeError, ZeroDivisionError):
            pass
    if top and ins is not None and state.get("Running") and "terminal64" not in top.lower() and "wine" not in top.lower():
        res["problems"].append("khong thay tien trinh Wine/terminal")
    res["ok"] = not res["problems"]
    return res


def allow_url_ok(logs: str) -> bool | None:
    """True neu post-start (them URL WebRequest) da xong; None neu khong du du lieu."""
    if not logs:
        return None
    return "post-start done" in logs


# ---------------- canh bao ----------------
Notifier = Callable[[str, str, str], Awaitable[bool]]


async def default_notify(ctx: Any, cfg: HealConfig, key: str, level: str, text: str) -> bool:
    http = getattr(ctx, "http", None)
    if http is None:
        return False
    ok = False
    if cfg.alert_webhook:
        hdr = {"Authorization": f"Bearer {cfg.alert_token}"} if cfg.alert_token else {}
        try:
            from tscommon.internal_auth import internal_headers
            hdr.update(internal_headers())
        except Exception:  # noqa: BLE001 - tscommon cũ chưa có internal_auth
            pass
        body = {"status": "firing", "alerts": [{"status": "firing", "labels": {"alertname": f"DataKeeper_{key}", "severity": level},
                                                "annotations": {"summary": text, "description": text}}]}
        try:
            r = await http.post(cfg.alert_webhook, json=body, headers=hdr, timeout=8.0)
            ok = r.status_code < 300
        except Exception as e:  # noqa: BLE001
            log.warning("alert-service loi: %s", e)
    if not ok and cfg.ntfy_url:
        try:
            r = await http.post(cfg.ntfy_url, content=text.encode(), headers={"Title": "Du lieu thi truong", "Priority": "4" if level == "critical" else "3"}, timeout=8.0)
            ok = r.status_code < 300
        except Exception as e:  # noqa: BLE001
            log.warning("ntfy loi: %s", e)
    return ok


async def maybe_alert(ctx: Any, cfg: HealConfig, st: HealState, key: str, level: str, text: str, actions: list, notify: Notifier | None = None) -> None:
    """Dedupe theo key + cooldown. Dry-run: chi ghi nhat ky, khong gui."""
    now = time.time()
    if now - st.last_alert.get(key, 0.0) < cfg.alert_cooldown_s:
        return
    if cfg.dry_run:
        actions.append(await log_action(ctx, "alert", key, "dry_run", {"level": level, "text": text}))
        st.last_alert[key] = now
        return
    sent = await (notify(key, level, text) if notify else default_notify(ctx, cfg, key, level, text))
    if sent:
        st.last_alert[key] = now
    actions.append(await log_action(ctx, "alert", key, "sent" if sent else "failed", {"level": level, "text": text}))


# ---------------- hanh dong ----------------
def _restart_budget(cfg: HealConfig, st: HealState, now: float) -> tuple[bool, str]:
    st.restarts[:] = [t for t in st.restarts if now - t < 3600]
    if len(st.restarts) >= cfg.max_restarts_per_hour:
        return False, f"da {len(st.restarts)} lan restart/gio (tran {cfg.max_restarts_per_hour})"
    if st.restarts and now - max(st.restarts) < cfg.restart_cooldown_s:
        return False, f"cooldown {int(cfg.restart_cooldown_s - (now - max(st.restarts)))}s"
    return True, ""


def write_feed_list(cfg: HealConfig, symbols: list[str]) -> bool:
    """Ghi danh sach ma mong muon (EA doc feed_symbols.txt luc init; hieu luc sau restart nhe)."""
    p = Path(cfg.feed_list_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(sorted(set(symbols))) + "\n")
        os.replace(tmp, p)
        return True
    except OSError as e:
        log.warning("ghi %s loi: %s", p, e)
        return False


async def heal_cycle(ctx: Any, matrix: dict, cfg: HealConfig | None = None, st: HealState | None = None,
                     notify: Notifier | None = None) -> list[dict]:
    cfg = cfg or getattr(ctx, "heal_cfg", None) or HealConfig.from_env()
    st = st or _STATE
    actions: list[dict] = []
    now = time.time()
    cls = classify(matrix)
    broken, slow = cls["BROKEN"], cls["SLOW"]
    # theo doi thoi gian hong lien tuc; CLOSED/OK xoa dau
    for s in list(st.broken_since):
        if s not in broken:
            st.broken_since.pop(s, None)
            st.failover_marked.discard(s)
    for s in broken:
        st.broken_since.setdefault(s, now)
    persistent = [s for s in broken if now - st.broken_since[s] >= cfg.broken_min_age_s]
    # Ma con TICK tuoi nhung thieu nen M1 (nguon nen hong, vd EA lab cu): feed khoe -> KHONG resync/restart feed, canh bao rieng, khong bao "im lang" gia.
    now_dt = _now(ctx)
    ticking = [s for s in persistent if _tick_alive(matrix.get(s, {}), now_dt)]
    persistent = [s for s in persistent if s not in set(ticking)]
    if len(ticking) >= cfg.broken_min_symbols:
        await maybe_alert(ctx, cfg, st, "bars_missing", "warning",
                          f"{len(ticking)} ma van co gia nhung thieu nen M1 (nguon nen): {', '.join(sorted(ticking)[:8])}", actions, notify)
    if len(persistent) < cfg.broken_min_symbols:
        return actions                                    # khong co su co ben vung -> khong lam gi (CLOSED/nhat thoi)

    open_total = len(cls["OK"]) + len(broken) + len(slow)
    frac = len(persistent) / max(1, open_total)
    http = getattr(ctx, "http", None)
    docker = DockerAPI(cfg, http) if http is not None else None

    # 1. kiem container + allow URL (chi doc)
    ch: dict[str, Any] = {"ok": True, "problems": []}
    allow_ok: bool | None = None
    if docker is not None:
        try:
            ins = await docker.inspect(cfg.container)
            stt = None
            try:
                stt = await docker.stats(cfg.container)
            except Exception:  # noqa: BLE001
                pass
            top = ""
            try:
                top = await docker.top(cfg.container)
            except Exception:  # noqa: BLE001
                pass
            ch = container_health(ins, stt, top, cfg)
            started = ins.get("State", {}).get("StartedAt", "")
            allow_ok = allow_url_ok(await docker.logs(cfg.container))
            ch["started_at"] = started
        except Exception as e:  # noqa: BLE001
            ch = {"ok": None, "problems": [f"khong doc duoc docker: {type(e).__name__}"]}
    actions.append(await log_action(ctx, "check_container", cfg.container, "ok" if ch.get("ok") else "problem", ch))
    if allow_ok is False:
        actions.append(await log_action(ctx, "check_allow_url", cfg.container, "problem", {"note": "chua thay 'post-start done' (URL WebRequest co the chua duoc them)"}))

    # 2. dang ky lai symbol (ghi danh sach mong muon: toan bo ma co trong ma tran, dedupe theo chu ky)
    sig = ",".join(sorted(persistent))
    if sig != st.last_resync_sig:
        st.last_resync_sig = sig
        if cfg.dry_run:
            actions.append(await log_action(ctx, "resync_symbols", cfg.feed_list_path, "dry_run", {"symbols": persistent}))
        else:
            ok = write_feed_list(cfg, list(matrix))
            actions.append(await log_action(ctx, "resync_symbols", cfg.feed_list_path, "done" if ok else "failed", {"symbols": persistent}))

    # 3. restart nhe: chi khi su co dien rong (>= 25% ma dang mo) hoac container co van de, trong ngan sach
    sys_wide = frac >= 0.25 or ch.get("ok") is False
    if sys_wide:
        okb, why = _restart_budget(cfg, st, now)
        if not okb:
            actions.append(await log_action(ctx, "restart_feed", cfg.container, "skipped", {"reason": why}))
        elif cfg.dry_run:
            actions.append(await log_action(ctx, "restart_feed", cfg.container, "dry_run", {"broken": len(persistent)}))
        elif docker is None:
            actions.append(await log_action(ctx, "restart_feed", cfg.container, "planned", {"reason": "khong co http client"}))
        else:
            try:
                done, detail = await docker.restart_soft(cfg.container)
            except Exception as e:  # noqa: BLE001
                done, detail = False, f"loi {type(e).__name__}"
            if done:
                st.restarts.append(now)
            actions.append(await log_action(ctx, "restart_feed", cfg.container, "done" if done else "planned", {"detail": detail, "broken": len(persistent)}))

    # 4. failover: ma hong qua lau -> danh dau/ ghi ke hoach (chua co duong noi an toan)
    stale = [s for s in persistent if now - st.broken_since[s] >= cfg.failover_after_s and s not in st.failover_marked]
    if stale:
        st.failover_marked.update(stale)
        if not cfg.dry_run:
            try:
                Path(cfg.plan_path).write_text(json.dumps({"ts": _now(ctx).isoformat(), "symbols": sorted(stale), "note": "ke hoach chuyen nguon du phong (chua noi)"}))
            except OSError:
                pass
        actions.append(await log_action(ctx, "failover_plan", ",".join(sorted(stale))[:200], "dry_run" if cfg.dry_run else "planned", {"symbols": sorted(stale), "count": len(stale)}))

    # 5. canh bao: chi mã mo-cua hong ben vung; mot canh bao gop cho ca dot (dedupe theo muc)
    if frac >= 0.25:
        await maybe_alert(ctx, cfg, st, "feed_wide", "critical",
                          f"Luong gia gap su co: {len(persistent)}/{open_total} ma dang mo cua khong co du lieu moi. Dang tu xu ly.", actions, notify)
    elif len(persistent) >= cfg.broken_min_symbols:
        await maybe_alert(ctx, cfg, st, "feed_partial", "warning",
                          f"{len(persistent)} ma dang mo cua im lang: {', '.join(sorted(persistent)[:8])}", actions, notify)
    if stale:
        await maybe_alert(ctx, cfg, st, "feed_stale", "warning", f"{len(stale)} ma hong qua 1 gio, can can nhac nguon du phong.", actions, notify)
    return actions
