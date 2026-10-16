from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from prometheus_client import Counter, Gauge
from tscommon import Bus, make_event
from tscommon.bus import STREAMS

from . import DISCLAIMER
from .config import ECConfig
from .consensus import compute_consensus, compute_weighted_consensus
from .diff import diff_net, net_positions
from .models import ExpertInfo, OpinionInfo, SignalInfo, normalize_symbol
from .reputation import detect_grid, detect_history_wipe, detect_martingale, opinion_score, reputation_score
from .sources.base import ExpertSource
from .trackweights import TrackWeights, lookup, weight_of

log = logging.getLogger(__name__)
SERVICE = "expert-collector"
WIPE_FLAG_DAYS = 90

SIGNALS = Counter("ec_signals_published_total", "expert_signal events", ["source"])
PROFILES = Counter("ec_profiles_published_total", "expert_profile events", ["source"])
COT_STANCES = Gauge("ec_cot_stances", "so hop dong COT tham gia dong thuan", ["side"])
EXPERT_WEIGHT = Gauge("ec_cot_expert_weight", "trong so track-record cua hop dong COT trong dong thuan", ["expert_id"])
OPINIONS = Counter("ec_opinions_published_total", "expert opinion news items", ["source", "group"])
POSITIONS = Counter("ec_positions_published_total", "expert_position events", ["source"])
ALERTS = Counter("ec_alerts_published_total", "alerts", ["kind"])
ERRORS = Counter("ec_source_errors_total", "source errors", ["source"])
EXPERTS_TRACKED = Gauge("ec_experts_tracked", "qualified experts", ["source"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Collector:
    def __init__(self, sources: list[ExpertSource], bus: Bus, cfg: ECConfig, now: Callable[[], datetime] = _now):
        self.sources, self.bus, self.cfg, self.now = sources, bus, cfg, now
        self.r = bus.r
        self.tw = TrackWeights(self.r, max_age_hours=cfg.track_max_age_hours, enabled=cfg.track_weights_enabled)

    # ---------- publish helpers ----------
    async def _emit(self, stream_key: str, type_: str, payload: dict) -> None:
        await self.bus.publish(STREAMS[stream_key], make_event(type_, SERVICE, payload))

    async def _once(self, key: str) -> bool:
        """True neu day la lan dau thay key (dedupe)."""
        return bool(await self.r.set(f"ec:seen:{key}", "1", nx=True, ex=self.cfg.dedupe_ttl_seconds))

    async def _alert(self, kind: str, level: str, title: str, body: str, tags: list[str], dedupe_key: str) -> None:
        if not await self._once("alert:" + dedupe_key):
            return
        await self._emit("alerts", "alert", {"level": level, "title": title, "body": f"{body}\n{DISCLAIMER}",
                                             "tags": ["expert", *tags], "dedupe_key": dedupe_key})
        ALERTS.labels(kind).inc()

    # ---------- main loop ----------
    async def poll_once(self) -> None:
        for src in self.sources:
            try:
                experts = await src.list_experts()
            except Exception:  # noqa: BLE001 - mot nguon loi khong duoc lam sap nguon khac
                ERRORS.labels(src.name).inc()
                log.exception("list_experts failed: %s", src.name)
                continue
            tracked = 0
            for info in experts:
                try:
                    tracked += await self._process_expert(src, info)
                except Exception:  # noqa: BLE001
                    ERRORS.labels(src.name).inc()
                    log.exception("expert %s failed", info.expert_id)
            EXPERTS_TRACKED.labels(src.name).set(tracked)
        await self._check_consensus()

    async def run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:  # noqa: BLE001
                log.exception("poll_once failed")
            await asyncio.sleep(self.cfg.poll_seconds)

    # ---------- per expert ----------
    async def _process_expert(self, src: ExpertSource, info: ExpertInfo) -> int:
        eid, now = info.expert_id, self.now()
        rep = dict(info.reputation)
        if rep.get("kind") == "opinion":
            return await self._process_opinion_expert(src, info, rep)
        trades = await self._safe(src.fetch_trades(info), [])
        positions = await self._safe(src.fetch_positions(info), []) if src.supports_positions else []

        martingale = detect_martingale(trades)
        grid = detect_grid([{"symbol": normalize_symbol(p.symbol), "side": p.side, "entry": p.entry} for p in positions])

        hist_raw = await self.r.lrange(f"ec:rep:{eid}", 0, 199)
        history = [json.loads(x) for x in hist_raw]
        prior = await self._load_expert(eid)
        wiped_at = prior.get("wiped_at") if prior else None
        if detect_history_wipe(history, rep):
            wiped_at = now.isoformat()
        wiped = bool(wiped_at) and now - datetime.fromisoformat(wiped_at) < timedelta(days=WIPE_FLAG_DAYS)

        res = reputation_score(rep, self.cfg.thresholds, martingale=martingale, grid=grid, history_wiped=wiped)

        today = now.date().isoformat()
        if not history or history[0].get("_day") != today:
            await self.r.lpush(f"ec:rep:{eid}", json.dumps({**rep, "_day": today}))
            await self.r.ltrim(f"ec:rep:{eid}", 0, 199)

        record = {"expert_id": eid, "source": info.source, "display_name": info.display_name, "url": info.url,
                  "reputation": rep, "score": res.score, "qualified": res.qualified, "tracked": res.qualified,
                  "reasons": res.reasons, "martingale": martingale, "grid": grid, "history_wiped": wiped,
                  "wiped_at": wiped_at, "last_seen": now.isoformat()}
        await self.r.hset("ec:experts", eid, json.dumps(record))
        await self._publish_profile(info, record, rep, track=lookup(await self.tw.snapshot(), eid, info.source))
        if not res.qualified:
            return 0

        for sig in await self._safe(src.fetch_signals(info), []):
            await self._publish_signal(info, sig, record)
        if src.supports_positions:
            await self._process_positions(info, positions, record)
        return 1

    # ---------- y kien chuyen gia (kind='opinion') ----------
    async def _process_opinion_expert(self, src: ExpertSource, info: ExpertInfo, rep: dict) -> int:
        eid, now = info.expert_id, self.now()
        res = opinion_score(rep, self.cfg.opinion_min_credibility)
        record = {"expert_id": eid, "source": info.source, "display_name": info.display_name, "url": info.url, "reputation": rep,
                  "score": res.score, "qualified": res.qualified, "tracked": res.qualified, "reasons": res.reasons,
                  "martingale": False, "grid": False, "history_wiped": False, "wiped_at": None, "last_seen": now.isoformat()}
        await self.r.hset("ec:experts", eid, json.dumps(record))
        await self._publish_profile(info, record, rep)
        if not res.qualified:
            return 0
        for op in await self._safe(src.fetch_opinions(info), []):
            await self._publish_opinion(info, op, record)
        return 1

    async def _publish_opinion(self, info: ExpertInfo, op: OpinionInfo, record: dict) -> None:
        """Phat tin y kien qua `news.items` (nlp lam giau sentiment/symbols; storage ghi news_items + expert_opinions neu bat). Nhan: y kien tham khao."""
        if not await self._once("op:" + op.url):
            return
        rep = record["reputation"]
        published = (op.published_at or self.now()).isoformat()
        meta = {"expert_id": info.expert_id, "name": info.display_name, "group": rep.get("group"), "org_type": rep.get("org_type"),
                "credibility": record["score"], "stance": op.stance, "stance_score": op.stance_score, "topics": op.topics,
                "author": op.author or None, "label": "ý kiến tham khảo", "disclaimer": DISCLAIMER, "raw": op.raw}
        payload = {"url": op.url, "title": op.title, "summary": op.summary or None, "published_at": published,
                   "source": f"expert:{info.expert_id}", "lang": op.lang, "symbols": op.symbols, "sentiment": None, "expert": meta}
        await self._emit("news", "news", payload)
        OPINIONS.labels(info.source, str(rep.get("group"))).inc()
        item = {"ts": published, "expert_id": info.expert_id, "name": op.author or info.display_name, "org": info.display_name,
                "group": rep.get("group"), "title": op.title, "url": op.url, "stance": op.stance, "topics": op.topics, "symbols": op.symbols}
        await self.r.lpush("ec:opinions", json.dumps(item, ensure_ascii=False))
        await self.r.ltrim("ec:opinions", 0, 999)

    async def _publish_profile(self, info: ExpertInfo, record: dict, rep: dict, track: dict | None = None) -> None:
        """Phat `expert.profiles` (storage-writer upsert bang experts). Khong doi -> toi da 1 lan/ngay/chuyen gia."""
        payload = {"expert_id": info.expert_id, "source": info.source, "display_name": info.display_name,
                   "url": info.url,
                   "reputation": {**rep, "score": record["score"], "qualified": record["qualified"],
                                  "reasons": record["reasons"], "martingale": record["martingale"],
                                  "grid": record["grid"], "history_wiped": record["history_wiped"]},
                   "tracked": bool(record["tracked"])}
        trk, trk_changed = None, False
        if track:   # reputation.track = {score, n, status, hit, beats, weight}; chi them khi service track-record co du lieu
            trk = {"score": track.get("score"), "n": track.get("n"), "status": track.get("status"), "hit": track.get("hit"),
                   "beats": track.get("beats"), "weight": track.get("weight")}
            payload["reputation"]["track"] = trk
            trk_changed = await self._track_changed(info.expert_id, trk)
        # dedupe: phan `track` KHONG vao digest tru khi doi trang thai/beats hoac score lech >= 2 diem (tranh phat lai vo co)
        base = {**payload, "reputation": {k: v for k, v in payload["reputation"].items() if k != "track"}}
        digest = hashlib.md5(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()[:16]
        if trk_changed:
            digest = hashlib.md5((digest + f"|trk:{trk.get('status')}:{trk.get('beats')}:{trk.get('score')}").encode()).hexdigest()[:16]
        if await self._once(f"prof:{info.expert_id}:{self.now().date().isoformat()}:{digest}"):
            await self._emit("expert_profiles", "expert_profile", payload)
            PROFILES.labels(info.source).inc()
            if trk:
                await self.r.set(f"ec:trkprof:{info.expert_id}", json.dumps(trk))

    async def _track_changed(self, eid: str, trk: dict) -> bool:
        """So voi `track` da phat lan truoc: doi status/beats hoac |score| lech >= 2 diem (hoac chua tung phat) -> True."""
        raw = await self.r.get(f"ec:trkprof:{eid}")
        if not raw:
            return True
        try:
            old = json.loads(raw)
        except ValueError:
            return True
        if old.get("status") != trk.get("status") or old.get("beats") != trk.get("beats"):
            return True
        a, b = old.get("score"), trk.get("score")
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) >= 2

    async def _safe(self, coro, default):
        try:
            return await coro
        except Exception:  # noqa: BLE001
            log.exception("fetch failed")
            return default

    async def _load_expert(self, eid: str) -> dict | None:
        raw = await self.r.hget("ec:experts", eid)
        return json.loads(raw) if raw else None

    # ---------- signals (y tuong / khuyen nghi) ----------
    def _sig_payload(self, info: ExpertInfo, s: SignalInfo, record: dict, extra: dict | None = None) -> dict:
        return {"expert_id": info.expert_id, "source": info.source, "symbol": normalize_symbol(s.symbol), "side": s.side,
                "entry": s.entry, "sl": s.sl, "tp": s.tp,
                "opened_at": (s.opened_at or self.now()).isoformat(), "status": s.status, "url": s.url or info.url,
                "raw": {**s.raw, "reputation_score": record["score"], "disclaimer": DISCLAIMER, **(extra or {})}}

    async def _publish_signal(self, info: ExpertInfo, s: SignalInfo, record: dict) -> None:
        p = self._sig_payload(info, s, record)
        if not await self._once(f"sig:{info.expert_id}:{p['symbol']}:{p['side']}:{p['opened_at']}:{p['status']}"):
            return
        await self._emit("expert_signals", "expert_signal", p)
        SIGNALS.labels(info.source).inc()
        # stance cho dong thuan
        if s.side in ("buy", "sell") and s.status == "open":
            key = f"ec:stances:{info.expert_id}"
            old = await self.r.hget(key, p["symbol"])
            if not old or json.loads(old)["ts"] <= p["opened_at"]:
                await self.r.hset(key, p["symbol"], json.dumps({"side": s.side, "ts": p["opened_at"]}))
        await self._alert("signal", "info", f"Chuyen gia {info.display_name or info.expert_id}: {s.side.upper()} {p['symbol']}",
                          f"Nguon {info.source}, diem uy tin {record['score']}. {p['url']}",
                          [info.source, p["symbol"]], f"expert:{info.expert_id}:{p['symbol']}:{s.side}:{p['opened_at']}")

    # ---------- positions (mo/dong/dao chieu) ----------
    async def _process_positions(self, info: ExpertInfo, positions, record: dict) -> None:
        eid, now = info.expert_id, self.now()
        cur = net_positions(positions)
        key = f"ec:pos:{eid}"
        raw = await self.r.get(key)
        baseline = raw is None
        prev = json.loads(raw) if raw else {}
        changes = diff_net(prev, cur)

        for c in changes:
            if c.kind in ("close", "reverse"):
                await self._emit_pos_signal(info, c.symbol, c.old, "closed", now, record, baseline=False)
            if c.kind in ("open", "reverse"):
                await self._emit_pos_signal(info, c.symbol, c.new, "open", now, record, baseline=baseline)
            await self._emit("expert_positions", "expert_position", {
                "expert_id": eid, "source": info.source, "symbol": c.symbol,
                "net_volume": c.new["net_volume"] if c.new else 0.0, "avg_price": c.new["avg_price"] if c.new else None,
                "as_of": now.isoformat(), "raw": {"change": c.kind, "baseline": baseline, "disclaimer": DISCLAIMER}})
            POSITIONS.labels(info.source).inc()
            if not baseline:
                side = (c.new or c.old)["side"]
                label = {"open": "MO", "close": "DONG", "reverse": "DAO CHIEU"}[c.kind]
                stamp = (c.new or c.old).get("opened_at") or now.isoformat()
                await self._alert(f"position_{c.kind}", "warn" if c.kind == "reverse" else "info",
                                  f"Chuyen gia {info.display_name or eid}: {label} {c.symbol}",
                                  f"{c.kind} {side} {c.symbol} (diem uy tin {record['score']}).",
                                  [info.source, c.symbol, c.kind], f"expert:{eid}:{c.symbol}:{c.kind}:{stamp}")
        await self.r.set(key, json.dumps(cur))
        await self.r.delete(f"ec:stances:{eid}")
        if cur:
            await self.r.hset(f"ec:stances:{eid}", mapping={s: json.dumps({"side": v["side"], "ts": now.isoformat()}) for s, v in cur.items()})

    async def _emit_pos_signal(self, info, symbol, pos, status, now, record, baseline: bool) -> None:
        opened = pos.get("opened_at") or now.isoformat()
        s = SignalInfo(symbol=symbol, side=pos["side"], entry=pos.get("avg_price"), sl=pos.get("sl"), tp=pos.get("tp"),
                       opened_at=datetime.fromisoformat(opened), status=status, url=info.url,
                       raw={"net_volume": pos["net_volume"], "baseline": baseline})
        p = self._sig_payload(info, s, record)
        if status == "open" and not pos.get("opened_at"):
            p["opened_at"] = now.isoformat()
        if await self._once(f"sig:{info.expert_id}:{symbol}:{p['side']}:{p['opened_at']}:{status}"):
            await self._emit("expert_signals", "expert_signal", p)
            SIGNALS.labels(info.source).inc()

    # ---------- COT (news-collector -> expert.positions, expert_id 'CFTC:<ma>') tham gia dong thuan ----------
    COT_MAX_AGE = timedelta(days=10)   # bao cao tuan: vi the con hieu luc toi 10 ngay ke tu ngay du lieu (thu Ba)

    async def _ingest_cot(self) -> None:
        """Doc vi the COT moi nhat tu stream `expert.positions` (chi DOC) -> ec:experts (tracked) + ec:stances. Chieu theo cap:
        side = dau(net_volume x pair_direction) (pair_direction=-1 voi JPY/CAD/CHF: futures la ngoai te doi ung USD). Chi tham khao."""
        if not self.cfg.cot_consensus:
            return
        try:
            entries = await self.r.xrevrange(STREAMS["expert_positions"], count=5000)
        except Exception:  # noqa: BLE001
            log.exception("doc expert.positions loi")
            return
        latest: dict[str, dict] = {}
        for eid0, raw0 in (await self.r.hgetall("ec:cot:latest")).items():   # trang thai da thay (song sot khi stream bi cat theo thoi gian)
            try:
                latest[eid0] = json.loads(raw0)
            except ValueError:
                continue
        for _id, f in entries:
            try:
                p = json.loads(f["e"])["payload"]
            except (KeyError, ValueError, TypeError):
                continue
            eid = str(p.get("expert_id", ""))
            if not eid.startswith("CFTC:") or p.get("source") != "cftc" or p.get("net_volume") is None:
                continue
            cur = latest.get(eid)
            if cur is None or str(p.get("as_of", "")) > str(cur.get("as_of", "")):
                latest[eid] = p
                await self.r.hset("ec:cot:latest", eid, json.dumps(p))
        now = self.now()
        counts = {"buy": 0, "sell": 0}
        for eid, p in latest.items():
            try:
                as_of = datetime.fromisoformat(str(p["as_of"]).replace("Z", "+00:00"))
                signed = float(p["net_volume"]) * float((p.get("raw") or {}).get("pair_direction", 1) or 1)
            except (KeyError, ValueError, TypeError):
                continue
            if now - as_of > self.COT_MAX_AGE or signed == 0:
                await self.r.delete(f"ec:stances:{eid}")
                continue
            side = "buy" if signed > 0 else "sell"
            symbol = normalize_symbol(p["symbol"])
            record = {"expert_id": eid, "source": "cftc", "display_name": f"Vi the dau co lon (COT) - {symbol}", "url": "",
                      "reputation": {"kind": "positioning", "group": "cot", "note": "Chi tham khao; net non-commercial, du lieu tuan"},
                      "score": 60.0, "qualified": True, "tracked": True, "reasons": [], "martingale": False, "grid": False,
                      "history_wiped": False, "wiped_at": None, "last_seen": now.isoformat()}
            await self.r.hset("ec:experts", eid, json.dumps(record))
            await self.r.delete(f"ec:stances:{eid}")
            await self.r.hset(f"ec:stances:{eid}", symbol, json.dumps({"side": side, "ts": now.isoformat(), "as_of": as_of.isoformat(), "kind": "cot"}))
            counts[side] += 1
        for k, v in counts.items():
            COT_STANCES.labels(k).set(v)

    # ---------- dong thuan ----------
    async def _check_consensus(self) -> None:
        await self._ingest_cot()
        tracked = []
        experts_raw = await self.r.hgetall("ec:experts")
        for eid, raw in experts_raw.items():
            if json.loads(raw).get("tracked"):
                tracked.append(eid)
        stances: dict[str, dict[str, dict]] = {}
        for eid in tracked:
            h = await self.r.hgetall(f"ec:stances:{eid}")
            if h:
                stances[eid] = {s: json.loads(v) for s, v in h.items()}
        now = self.now()
        snap = await self.tw.snapshot()
        weights = {}
        for eid in stances:   # trong so tu track-record (fail-open: thieu -> 1.0); tien nghiem cu = 1 cho moi chuyen gia
            src = (json.loads(experts_raw[eid]).get("source") if eid in experts_raw else None)
            weights[eid] = weight_of(snap, eid, src)
        cot_w = {e: w for e, w in weights.items() if e.startswith("CFTC:")}
        for e, w in cot_w.items():
            EXPERT_WEIGHT.labels(e).set(w)
        if cot_w:
            log.info("COT trong dong thuan: %d hop dong, trong so track-record: %s", len(cot_w), {k: round(v, 3) for k, v in sorted(cot_w.items())})
        for c in compute_weighted_consensus(stances, now, timedelta(hours=self.cfg.stance_window_hours), weights=weights,
                                            min_experts=self.cfg.consensus_min_experts, min_ratio=self.cfg.consensus_min_ratio,
                                            min_weight=self.cfg.consensus_min_weight or None,
                                            min_weight_ratio=self.cfg.consensus_min_weight_ratio or None):
            await self._alert("consensus", "warn", f"Dong thuan chuyen gia: {c.side.upper()} {c.symbol}",
                              f"{len(c.experts)}/{c.total} chuyen gia uy tin cung chieu {c.side}: {', '.join(c.experts)}. "
                              f"Trong so theo thanh tich: {c.weight:.2f}/{c.weight_total:.2f} ({c.weight_ratio:.0%}). Chi tham khao." + (" Gom vi the COT (da dao dau cho cap USD/xxx)." if any(e.startswith("CFTC:") for e in c.experts) else ""),
                              ["consensus", c.symbol], f"consensus:{c.symbol}:{c.side}:{now.date().isoformat()}")

    # ---------- API ----------
    async def list_opinions_api(self, group: str | None = None, limit: int = 100) -> list[dict]:
        items = [json.loads(x) for x in await self.r.lrange("ec:opinions", 0, 999)]
        if group:
            items = [i for i in items if i.get("group") == group]
        return items[: max(1, min(limit, 500))]

    async def list_experts_api(self, tracked_only: bool = False) -> list[dict]:
        items = [json.loads(v) for v in (await self.r.hgetall("ec:experts")).values()]
        if tracked_only:
            items = [i for i in items if i.get("tracked")]
        return sorted(items, key=lambda i: -i.get("score", 0))
