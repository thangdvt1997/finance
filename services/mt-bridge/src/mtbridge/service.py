"""Service: ingest (EA) + poller (MT5 truc tiep) -> publish account.snapshots / md.quotes / md.bars / alerts.out."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram
from pydantic import ValidationError
from tscommon import STREAMS, Event, assets, make_app, make_event

from .accounts import AccountConfig, BridgeConfig, load_config
from .adapters.agent import AgentGateway, IngestResult
from .adapters.mt5 import MT5Gateway
from .alerts import AlertEngine, alert
from .feed import CanonFeed, FeedSettings, load_symbols
from .gateway import BrokerGateway
from .models import Account, Bar, Deal, Position, Quote
from .protocol import ACCOUNT_ID_RE, MAX_BODY_BYTES, AuthError, Batch, NonceCache, RegisterIn, verify_sig, verify_token, verify_token_hash
from .ratelimit import RateLimiter
from .registry import AccountRecord, AccountRegistry, CompositeRegistry, HttpRegistry, StaticRegistry

log = logging.getLogger("mtbridge")
SOURCE = "mt-bridge"
STATUS_STREAM = "mt.account_status"  # online|offline|degraded theo tai khoan (docs/CONTRACTS.md); chi khi doi trang thai
MAX_REGISTER_BYTES = 8192
_ACC_RE = re.compile(ACCOUNT_ID_RE)

INGEST = Counter("mtbridge_ingest_total", "Batch ingest theo ket qua", ["account", "result"])
PUBLISHED = Counter("mtbridge_published_total", "Event da publish", ["stream"])
ALERTS = Counter("mtbridge_alerts_total", "Alert da phat", ["level"])
LAST_SEEN = Gauge("mtbridge_account_last_seen_timestamp", "Epoch lan cuoi thay du lieu", ["account"])
DEALS = Counter("mtbridge_deals_total", "Deal lich su da publish (account.deals)", ["account"])
UP = Gauge("mtbridge_account_connected", "1 neu dang ket noi", ["account"])
REGISTERED = Counter("mtbridge_register_total", "Yeu cau /ingest/v1/register theo ket qua", ["result"])
_LAT_B = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
# EA->bridge = now - batch.ts (thoi gian EA ghi tren dong ho EA => GOM CA lech dong ho EA; lech rieng xem skew_s trong /health)
EA_TO_BRIDGE = Histogram("mtbridge_ea_to_bridge_seconds", "Tre EA->bridge: now - batch.ts (gom lech dong ho EA)", buckets=_LAT_B)
INGEST_SECONDS = Histogram("mtbridge_ingest_seconds", "Tong thoi gian handle_ingest (xac thuc->publish xong)", buckets=_LAT_B)
PUBLISH_SECONDS = Histogram("mtbridge_publish_seconds", "Thoi gian XADD len bus", ["stream"], buckets=_LAT_B)
EA_STATUS = Gauge("mtbridge_ea_online_accounts", "So tai khoan EA theo trang thai", ["status"])
FEED_BARS = Counter("mtbridge_feed_canon_bars_total", "Nen canon (feed EA uu tien) da phat", ["tf"])
FEED_LAST_M1 = Gauge("mtbridge_feed_canon_last_m1_timestamp", "Epoch ts_open nen M1 canon moi nhat", ["symbol"])
# Feed toan thi truong (EA market-feed, docs/handoff/FEED_ALL_contract.md): metric theo hop dong, chi cho tai khoan feed (nhan class fx|metal|index).
_FB = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
FEEDALL_TICKS = Counter("mtbridge_feed_ticks_total", "Quote hop le tu EA feed", ["class"])
FEEDALL_LAST_Q = Gauge("mtbridge_feed_symbol_last_quote_timestamp", "Epoch UTC quote cuoi cua symbol (EA feed)", ["symbol", "class"])
FEEDALL_EXPECTED = Gauge("mtbridge_feed_symbols_expected", "So symbol feed ky vong theo nhom", ["class"])
FEEDALL_LAT = Histogram("mtbridge_feed_latency_seconds", "now(bridge) - quote.ts(UTC)", ["class"], buckets=_FB)
FEEDALL_BATCHES = Counter("mtbridge_feed_batches_total", "Batch ingest cua EA feed", ["result"])
FEEDALL_RECONNECT = Counter("mtbridge_feed_reconnect_total", "EA feed ket noi lai (im > 3 chu ky heartbeat roi co batch)", ["account"])
_FEED_CLASS = {"forex": "fx", "metal": "metal", "index": "index"}
RAW_BARS_DROPPED = Counter("mtbridge_raw_bars_dropped_total", "Nen EA tho bi bo theo MT_BAR_TFS (H4/D1 theo gio server)", ["tf"])


class Publisher(Protocol):
    async def publish(self, stream: str, event: Event) -> Any: ...


@dataclass
class Settings:
    config_path: str = field(default_factory=lambda: os.getenv("BRIDGE_CONFIG", "config/accounts.yaml"))
    admin_token: str = field(default_factory=lambda: os.getenv("BRIDGE_ADMIN_TOKEN", ""))
    # Chi che do dev ro rang (BRIDGE_ADMIN_INSECURE_DEV=1) moi cho /accounts khong token.
    admin_insecure_dev: bool = field(default_factory=lambda: os.getenv("BRIDGE_ADMIN_INSECURE_DEV", "") == "1")
    skew_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_SKEW_S", "120")))
    mt5_poll_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_MT5_POLL_S", "5")))
    monitor_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_MONITOR_S", "10")))
    # MT_REQUIRE_HMAC=1: tai khoan transport=agent KHONG co hmac_secret_env bi tu choi (fail-closed). Bat sau khi moi EA da ky X-MT-Sig.
    require_hmac: bool = field(default_factory=lambda: os.getenv("MT_REQUIRE_HMAC", "0") == "1")
    nonce_ttl_s: int = field(default_factory=lambda: int(os.getenv("BRIDGE_NONCE_TTL_S", "600")))
    # --- nguon tai khoan dong (service auth): de trong = chi dung accounts.yaml ---
    auth_url: str = field(default_factory=lambda: os.getenv("BRIDGE_AUTH_URL", ""))
    auth_token: str = field(default_factory=lambda: os.getenv("BRIDGE_AUTH_TOKEN", ""))  # token dich vu 2 chieu (bridge->auth va auth->bridge /internal/invalidate)
    auth_ttl_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_AUTH_TTL_S", "15")))
    auth_max_stale_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_AUTH_MAX_STALE_S", "600")))
    # --- gioi han toc do / suc khoe ---
    rate_per_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_RATE_PER_S", "5")))  # request/giay/tai khoan (EA gui ~1 req/3s)
    rate_burst: float = field(default_factory=lambda: float(os.getenv("BRIDGE_RATE_BURST", "20")))
    fail_per_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_FAIL_PER_S", "0.5")))  # xac thuc sai / IP (chong do token)
    fail_burst: float = field(default_factory=lambda: float(os.getenv("BRIDGE_FAIL_BURST", "30")))
    degraded_rtt_ms: int = field(default_factory=lambda: int(os.getenv("BRIDGE_DEGRADED_RTT_MS", "2500")))
    seen_flush_s: float = field(default_factory=lambda: float(os.getenv("BRIDGE_SEEN_FLUSH_S", "30")))
    trust_proxy: bool = field(default_factory=lambda: os.getenv("BRIDGE_TRUST_PROXY", "") == "1")  # lay IP tu X-Forwarded-For (chi khi sau reverse proxy tin cay)
    # Khung nen EA THO duoc phat len md.bars. H4/D1 cua EA cat theo gio SERVER broker (vd EET: D1 mo 21:00 UTC) -> lech hop dong
    # md.bars (UTC) va xen ke nen nguon khac trong cung chuoi => mac dinh bo; H4/D1 lay tu chuoi canon (feed.py). Rollback: them H4,D1.
    raw_bar_tfs: tuple[str, ...] = field(default_factory=lambda: tuple(x.strip().upper() for x in os.getenv("MT_BAR_TFS", "M1,M5,M15,H1").split(",") if x.strip()))


@dataclass
class EAHealth:
    """Suc khoe EA theo tai khoan (RAM): hien thi tren master + phat mt.account_status khi doi trang thai."""
    account_id: str
    platform: str
    status: str = "offline"            # online | degraded | offline
    reason: str = ""
    last_seen: Optional[datetime] = None
    rtt_ms: int = 0
    skew_s: float = 0.0
    ea_version: str = ""
    build: int = 0
    broker: str = ""
    server: str = ""
    remote_addr: str = ""
    fails: int = 0
    dirty: bool = False
    flushed_at: Optional[datetime] = None
    pending: bool = False              # tai khoan o trang thai pending (chua nhan du lieu)


class BridgeService:
    def __init__(
        self,
        cfg: BridgeConfig,
        publisher: Publisher,
        *,
        settings: Optional[Settings] = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        gateways: Optional[dict[str, BrokerGateway]] = None,
        registry: Optional[AccountRegistry] = None,
    ):
        self.cfg, self.pub = cfg, publisher
        self.settings = settings or Settings()
        self.clock = clock
        self.registry: AccountRegistry = registry or StaticRegistry(cfg)
        self.health: dict[str, EAHealth] = {}
        _ts = lambda: self.clock().timestamp()  # noqa: E731
        self.rl_account = RateLimiter(self.settings.rate_per_s, self.settings.rate_burst, clock=_ts)
        self.rl_fail = RateLimiter(self.settings.fail_per_s, self.settings.fail_burst, clock=_ts)
        self.rl_register = RateLimiter(2.0, 60, clock=_ts)  # theo IP (nhieu EA cung NAT/proxy co the ghep cap cung luc)
        self.rl_register_login = RateLimiter(1 / 60, 6, clock=_ts)
        self._audit_at: dict[tuple[str, str], float] = {}
        self._last_refresh = 0.0
        self._ta_warned: set[str] = set()   # tai khoan da canh bao trade_allowed (chi bao khi chuyen trang thai)
        self.accounts: dict[str, AccountConfig] = cfg.by_id()
        self.engine = AlertEngine()
        self.nonce_redis = getattr(publisher, "r", None)  # Redis (Bus.r): nonce dung chung/ben qua restart (SET NX EX); None -> chi cache RAM
        self.nonces = NonceCache(window_s=max(300.0, self.settings.skew_s * 2), clock=lambda: self.clock().timestamp())
        self.gateways: dict[str, BrokerGateway] = gateways if gateways is not None else {}
        for a in cfg.accounts:
            if a.account_id not in self.gateways:
                self.gateways[a.account_id] = AgentGateway(a, clock) if a.transport == "agent" else MT5Gateway(a, clock=clock)
        self._last_quote: dict[tuple[str, str], tuple[float, float]] = {}
        self._last_bar_pub: dict[tuple[str, str, str], datetime] = {}
        self._tasks: list[asyncio.Task] = []
        self.feed = CanonFeed(FeedSettings())
        self.feed_all = self._make_feed_all(self.feed.st)
        self.feed_fb = self._make_feed_fb(self.feed.st, self.feed_all.st)
        self._feed_last_batch: Optional[float] = None
        self._init_feed_metrics()

    @staticmethod
    def _make_feed_all(main: FeedSettings) -> CanonFeed:
        """Chuoi canon thu 2 cho EA market-feed (tai khoan rieng `FEED_ALL_ACCOUNT`, mac dinh mt5:100000001-feed); KHONG dung ma da thuoc chuoi cu."""
        en = os.getenv("FEED_ALL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        syms = tuple(x for x in load_symbols(os.getenv("FEED_ALL_SYMBOLS", "@/config/feed_symbols.txt")) if x not in set(main.symbols))
        acc = os.getenv("FEED_ALL_ACCOUNT", "mt5:100000001-feed").strip()
        return CanonFeed(FeedSettings(enabled=en and bool(syms), account=acc, symbols=syms, prefix=main.prefix))

    @staticmethod
    def _make_feed_fb(main: FeedSettings, fa: FeedSettings) -> CanonFeed:
        """Du phong cho 7 ma chuoi cu (EURUSD..USTEC): khi EA lab cu (`main.account`) im > stale_s, nen M1 cua EA feed
        (cung tai khoan/nguon voi feed_all) thay the; EA cu song lai -> tu nhuong (nguon canon cu xep truoc theo ten)."""
        en = os.getenv("FEED_FALLBACK_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        return CanonFeed(FeedSettings(enabled=en and fa.enabled, account=fa.account, symbols=tuple(main.symbols), prefix=fa.prefix,
                                      stale_s=fa.stale_s, fill_max_min=fa.fill_max_min, grace_s=fa.grace_s))

    def _legacy_stale(self, now: datetime) -> bool:
        hb = self.feed.last_hb
        return hb is None or (now - hb).total_seconds() > self.feed.st.stale_s

    def is_feed_all(self, account_id: str) -> bool:
        return bool(self.feed_all.st.account) and account_id == self.feed_all.st.account

    def _init_feed_metrics(self) -> None:
        cnt: dict[str, int] = {}
        for sym in self.feed_all.st.symbols:
            c = _FEED_CLASS.get(assets.classify(sym))
            if c:
                cnt[c] = cnt.get(c, 0) + 1
        for c in ("fx", "metal", "index"):
            FEEDALL_EXPECTED.labels(c).set(cnt.get(c, 0))

    def _feed_all_note(self, quotes: list[Quote]) -> None:
        now = self.clock().timestamp()
        for q in quotes:
            c = _FEED_CLASS.get(assets.classify(q.symbol))
            if c is None:
                continue
            FEEDALL_TICKS.labels(c).inc()
            FEEDALL_LAST_Q.labels(q.symbol, c).set(q.ts.timestamp())
            FEEDALL_LAT.labels(c).observe(max(0.0, now - q.ts.timestamp()))

    # ---------- publish ----------
    async def _pub(self, key: str, type_: str, payload: dict) -> None:
        _t = time.perf_counter()
        await self.pub.publish(STREAMS[key], make_event(type_, SOURCE, payload))
        PUBLISH_SECONDS.labels(STREAMS[key]).observe(time.perf_counter() - _t)
        PUBLISHED.labels(STREAMS[key]).inc()

    async def publish_alerts(self, alerts: list[dict]) -> None:
        for a in alerts:
            await self._pub("alerts", "alert", a)
            ALERTS.labels(a["level"]).inc()

    async def publish_account(self, account: Account, positions: list[Position], orders: list) -> None:
        payload = account.model_dump(mode="json")
        payload["positions"] = [p.model_dump(mode="json") for p in positions]
        payload["orders"] = [o.model_dump(mode="json") for o in orders]
        await self._pub("account", "account_snapshot", payload)

    async def publish_quotes(self, quotes: list[Quote]) -> None:
        for q in quotes:
            k = (q.source, q.symbol)
            if self._last_quote.get(k) == (q.bid, q.ask):
                continue
            self._last_quote[k] = (q.bid, q.ask)
            await self._pub("quotes", "quote", q.model_dump(mode="json", include={"symbol", "bid", "ask", "ts", "source"}))

    async def publish_bars(self, bars: list[Bar]) -> None:
        for b in bars:
            await self._pub("bars", "bar", b.model_dump(mode="json", include={"symbol", "tf", "ts_open", "o", "h", "l", "c", "v", "source"}))

    def _raw_bars(self, bars: list[Bar]) -> list[Bar]:
        keep = []
        for b in bars:
            if b.tf in self.settings.raw_bar_tfs:
                keep.append(b)
            else:
                RAW_BARS_DROPPED.labels(b.tf).inc()
        return keep

    async def _feed_publish(self, bars: list[Bar]) -> None:
        if not bars:
            return
        await self.publish_bars(bars)
        for b in bars:
            FEED_BARS.labels(b.tf).inc()
            if b.tf == "M1":
                FEED_LAST_M1.labels(b.symbol).set(b.ts_open.timestamp())

    async def publish_deals(self, account_id: str, platform: str, deals: list[Deal]) -> None:
        """Lich su da dong -> account.deals (1 event/lo, idempotent o storage-writer theo (account_id, ticket)). READ-ONLY."""
        if not deals:
            return
        payload = {"account_id": account_id, "platform": platform, "deals": [d.model_dump(mode="json") for d in deals]}
        await self._pub("deals", "account_deals", payload)
        DEALS.labels(account_id).inc(len(deals))

    async def _after_data(self, cfg: AccountConfig, gw: BrokerGateway, account: Optional[Account], positions: Optional[list[Position]], orders: Optional[list]) -> None:
        extra = self.engine.on_alive(cfg.account_id, cfg.platform)
        if account is not None:
            await self.publish_account(account, gw.get_positions(), gw.get_orders())
            extra += self.engine.on_snapshot(account, positions, cfg.rules)
        await self.publish_alerts(extra)
        h = gw.health()
        if h.last_seen:
            LAST_SEEN.labels(cfg.account_id).set(h.last_seen.timestamp())
        UP.labels(cfg.account_id).set(1 if h.connected else 0)

    # ---------- ingest (EA) ----------
    def _gateway(self, rec: AccountRecord) -> AgentGateway:
        """Gateway theo tai khoan (tao lan dau khi tai khoan dong xuat hien; cau hinh theo ban ghi moi nhat)."""
        aid = rec.account_id
        gw = self.gateways.get(aid)
        if not isinstance(gw, AgentGateway):
            gw = self.gateways[aid] = AgentGateway(rec.cfg, self.clock)
        gw.cfg = rec.cfg
        self.accounts[aid] = rec.cfg
        return gw

    def authenticate(self, headers: dict[str, str], raw: bytes, model: type = Batch) -> tuple[AccountRecord, Any]:
        if len(raw) > MAX_BODY_BYTES:
            raise AuthError(413, "body too large")
        acc_id = headers.get("x-mt-account", "")
        rec = self.registry.get(acc_id)
        auth = headers.get("authorization", "")
        presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if rec is None or not verify_token_hash(rec.token_hash, presented):
            if rec is None and not self.registry.healthy:
                raise AuthError(503, "account registry unavailable")  # khong de EA tuong token sai khi auth tam down
            raise AuthError(401, "unauthorized")  # dong nhat: khong lo tai khoan co ton tai hay khong
        if rec.status == "suspended":
            raise AuthError(403, "suspended")  # da chung minh so huu token -> bao ro ly do (va audit)
        ok, retry = self.rl_account.allow(rec.account_id)
        if not ok:
            raise AuthError(429, "rate limited", retry)
        try:
            batch = model.model_validate_json(raw)
        except ValidationError as e:
            raise AuthError(422, f"schema: {e.errors(include_url=False, include_context=False, include_input=False)[:3]}")
        secret = rec.hmac_secret
        need = rec.require_hmac if rec.require_hmac is not None else (self.settings.require_hmac or bool(secret))
        sig = headers.get("x-mt-sig", "")
        if need:
            if not (secret and verify_sig(secret, batch.ts, batch.nonce, raw, sig)):
                raise AuthError(401, "unauthorized")  # fail-closed: tai khoan bat HMAC ma thieu secret/chu ky sai
        elif secret and sig and not verify_sig(secret, batch.ts, batch.nonce, raw, sig):
            raise AuthError(401, "unauthorized")
        if (batch.account_id and batch.account_id != rec.account_id) or batch.platform != rec.platform:
            raise AuthError(400, "account/platform mismatch")
        if abs(self.clock().timestamp() - batch.ts) > self.settings.skew_s:
            raise AuthError(401, "timestamp out of range")
        if not self.nonces.check_and_add(rec.account_id, batch.nonce):
            raise AuthError(409, "replay")
        return rec, batch

    async def _claim_nonce_redis(self, account_id: str, nonce: str) -> None:
        """Nonce luu Redis co TTL (SET NX EX): chong replay xuyen restart/nhieu replica. Redis loi -> 503 (fail-closed)."""
        if self.nonce_redis is None:
            return
        try:
            ok = await self.nonce_redis.set(f"mtb:nonce:{account_id}:{nonce}", "1", nx=True, ex=self.settings.nonce_ttl_s)
        except Exception as e:  # noqa: BLE001
            raise AuthError(503, f"nonce store unavailable: {type(e).__name__}") from e
        if not ok:
            raise AuthError(409, "replay")

    def _audit_throttled(self, aid: str, action: str, every: float = 300.0) -> bool:
        now = self.clock().timestamp()
        k = (aid, action)
        if now - self._audit_at.get(k, 0.0) < every:
            return False
        if len(self._audit_at) > 10_000:
            self._audit_at = {kk: t for kk, t in self._audit_at.items() if now - t < every}
        self._audit_at[k] = now
        return True

    def _remote(self, headers: dict[str, str]) -> str:
        if self.settings.trust_proxy and headers.get("x-forwarded-for"):
            return headers["x-forwarded-for"].split(",")[0].strip()[:64]
        return headers.get("x-remote-addr", "")[:64]

    async def handle_ingest(self, headers: dict[str, str], raw: bytes) -> dict:
        _t0 = time.perf_counter()
        acc = headers.get("x-mt-account", "")
        ip = self._remote(headers) or "?"
        # Gioi han xac thuc SAI theo (IP, tai khoan) - KHONG chi theo IP: sau reverse proxy/NAT nhieu EA chung IP, 1 EA sai cau hinh
        # khong duoc khoa ca nhom. Tai khoan la (khong ton tai) dung chung 1 xo theo IP ("?") de chan do quet.
        if self.registry.get(acc) is None and _ACC_RE.fullmatch(acc or ""):
            await self.registry.ensure(acc)  # tai khoan moi do master vua tao -> hien ngay (khong doi TTL)
        fk = f"{ip}|{acc if self.registry.get(acc) is not None else '?'}"
        if not self.rl_fail.has(fk):
            INGEST.labels("?", "429").inc()
            raise AuthError(429, "too many failures", 10.0)
        try:
            rec, batch = self.authenticate(headers, raw)
            await self._claim_nonce_redis(rec.account_id, batch.nonce)
        except AuthError as e:
            known = self.registry.get(acc) is not None
            INGEST.labels(acc if known else "?", str(e.code)).inc()
            if known and self.is_feed_all(acc):
                FEEDALL_BATCHES.labels("rate_limited" if e.code == 429 else "rejected").inc()
            if e.code in (401, 422, 400):
                self.rl_fail.allow(f"{ip}|{acc if known else '?'}")
            if e.code == 403 and known and self._audit_throttled(acc, "ea_rejected_suspended"):
                await self.registry.audit(acc, "ea_rejected_suspended", {"ip": ip})
            raise
        cfg = rec.cfg
        EA_TO_BRIDGE.observe(max(0.0, self.clock().timestamp() - batch.ts))
        if rec.status == "pending":  # da xac thuc nhung CHUA duoc master duyet: khong nhan du lieu; van ghi suc khoe de master thay EA da ket noi
            await self._note_health(rec, batch, headers)
            INGEST.labels(rec.account_id, "202").inc()
            return {"ok": False, "status": "pending", "message": "cho master duyet tai khoan"}
        gw = self._gateway(rec)
        res: IngestResult = gw.ingest(batch)
        extra: list[dict] = []
        if not res.trade_allowed_warning:
            self._ta_warned.discard(cfg.account_id)
        elif cfg.account_id not in self._ta_warned:
            self._ta_warned.add(cfg.account_id)
            extra.append(alert("warn", f"[{cfg.account_id}] Tai khoan cho phep giao dich", "Nen dung INVESTOR password; bridge chi doc nhung rui ro bi lo mat khau chinh.", [f"account:{cfg.account_id}", "security"], f"trade_allowed:{cfg.account_id}"))
        await self.publish_quotes(res.quotes)
        feed_all = self.is_feed_all(cfg.account_id)
        if not feed_all:   # EA feed chi gui M1 cho chuoi canon: khong phat them nen tho (tranh nhan doi luu tru)
            await self.publish_bars(self._raw_bars(res.bars))
        if feed_all:
            try:
                now = self.clock()
                nt = now.timestamp()
                if self._feed_last_batch is not None and nt - self._feed_last_batch > 45:
                    FEEDALL_RECONNECT.labels(cfg.account_id).inc()
                self._feed_last_batch = nt
                self._feed_all_note(res.quotes)
                if self.feed_all.active_for(cfg.account_id):
                    self.feed_all.heartbeat(now)
                    await self._feed_publish(self.feed_all.on_bars(res.bars, now))
                if self.feed_fb.active_for(cfg.account_id) and self._legacy_stale(now):
                    self.feed_fb.heartbeat(now)
                    await self._feed_publish(self.feed_fb.on_bars(res.bars, now))
                FEEDALL_BATCHES.labels("ok").inc()
            except Exception:  # noqa: BLE001
                FEEDALL_BATCHES.labels("error").inc()
                log.exception("feed-all loi (bo qua, ingest van OK)")
        if self.feed.active_for(cfg.account_id):   # chuoi canon (feed EA uu tien, feed.py); loi o day khong duoc lam hong ingest
            try:
                now = self.clock()
                self.feed.heartbeat(now)
                await self._feed_publish(self.feed.on_bars(res.bars, now))
            except Exception:  # noqa: BLE001
                log.exception("feed canon loi (bo qua, ingest van OK)")
        await self.publish_deals(cfg.account_id, cfg.platform, res.deals)
        await self._after_data(cfg, gw, res.account, res.positions, res.orders)
        await self.publish_alerts(extra)
        await self._note_health(rec, batch, headers)
        INGEST.labels(cfg.account_id, "200").inc()
        INGEST_SECONDS.observe(time.perf_counter() - _t0)
        return {"ok": True, "status": rec.status, "quotes": len(res.quotes), "bars": len(res.bars), "snapshot": res.account is not None, "deals": len(res.deals)}

    # ---------- suc khoe EA + su kien mt.account_status ----------
    def _eval_status(self, h: EAHealth) -> tuple[str, str]:
        st = self.settings
        if st.degraded_rtt_ms and h.rtt_ms > st.degraded_rtt_ms:
            return "degraded", f"do tre {h.rtt_ms}ms"
        if abs(h.skew_s) > st.skew_s * 0.5:
            return "degraded", f"lech dong ho {h.skew_s:.0f}s"
        if h.fails >= 3:
            return "degraded", f"{h.fails} lan gui loi lien tiep"
        return "online", ""

    async def _set_status(self, h: EAHealth, status: str, reason: str) -> None:
        h.reason = reason
        if h.status == status:
            return
        h.status, h.dirty, h.flushed_at = status, True, None  # doi trang thai -> bao auth/master ngay
        payload = {
            "account_id": h.account_id, "platform": h.platform, "status": status, "reason": reason,
            "pending": h.pending, "ts": self.clock().isoformat(), "last_seen_at": h.last_seen.isoformat() if h.last_seen else None,
            "latency_ms": h.rtt_ms, "ea_version": h.ea_version, "build": h.build, "broker": h.broker, "server": h.server,
        }
        try:
            await self.pub.publish(STATUS_STREAM, make_event("mt_account_status", SOURCE, payload))
            PUBLISHED.labels(STATUS_STREAM).inc()
        except Exception:  # noqa: BLE001 - su kien trang thai khong duoc lam hong duong ingest
            log.exception("publish %s that bai", STATUS_STREAM)

    async def _note_health(self, rec: AccountRecord, msg: Any, headers: dict[str, str]) -> None:
        now = self.clock()
        h = self.health.get(rec.account_id)
        if h is None:
            h = self.health[rec.account_id] = EAHealth(rec.account_id, rec.platform)
        ag = getattr(msg, "agent", None)
        if ag is not None:
            h.rtt_ms, h.ea_version, h.build, h.fails = ag.rtt_ms, ag.ea or h.ea_version, ag.build or h.build, ag.fail
            h.broker = ag.company or h.broker
        elif hasattr(msg, "company"):  # RegisterIn
            h.ea_version, h.build, h.broker, h.server = msg.ea or h.ea_version, msg.build or h.build, msg.company or h.broker, msg.server or h.server
        acc = getattr(msg, "account", None)
        if acc is not None and acc.server:
            h.server = acc.server
        h.skew_s = round(now.timestamp() - msg.ts, 1)
        h.remote_addr = self._remote(headers) or h.remote_addr
        h.last_seen, h.dirty, h.pending = now, True, rec.status == "pending"
        await self._set_status(h, *self._eval_status(h))

    def _health_item(self, h: EAHealth) -> dict:
        return {
            "account_id": h.account_id, "status": h.status, "reason": h.reason, "pending": h.pending,
            "last_seen_at": h.last_seen.isoformat() if h.last_seen else None, "latency_ms": h.rtt_ms, "skew_s": h.skew_s,
            "ea_version": h.ea_version, "build": h.build, "broker": h.broker, "server": h.server, "remote_addr": h.remote_addr,
        }

    async def _health_tick(self) -> None:
        """Dinh ky: offline khi mat nhip, don tai khoan da bi go, day last_seen/suc khoe len auth (gop lo), lam moi registry."""
        now = self.clock()
        static_ids = {a.account_id for a in self.cfg.accounts}
        for aid, h in list(self.health.items()):
            c = self.accounts.get(aid)
            timeout = c.rules.heartbeat_timeout_s if c else 90.0
            if h.status != "offline" and h.last_seen and (now - h.last_seen).total_seconds() > timeout:
                await self._set_status(h, "offline", "mat nhip EA")
            if aid not in static_ids and self.registry.get(aid) is None and self.registry.healthy:  # tai khoan da xoa o master
                self.health.pop(aid, None)
                self.accounts.pop(aid, None)
                self.gateways.pop(aid, None)
        counts = {"online": 0, "degraded": 0, "offline": 0}
        for h in self.health.values():
            counts[h.status] = counts.get(h.status, 0) + 1
        for k, v in counts.items():
            EA_STATUS.labels(k).set(v)
        due = [h for h in self.health.values() if h.dirty and (h.flushed_at is None or (now - h.flushed_at).total_seconds() >= self.settings.seen_flush_s)]
        if due:
            items = [self._health_item(h) for h in due[:500]]
            for h in due[:500]:
                h.dirty, h.flushed_at = False, now
            await self.registry.report_seen(items)
        if now.timestamp() - self._last_refresh >= max(2.0, self.settings.auth_ttl_s / 2):
            self._last_refresh = now.timestamp()
            await self.registry.refresh()

    # ---------- dang ky / ghep cap (EA lan dau) ----------
    async def handle_register(self, headers: dict[str, str], raw: bytes) -> dict:
        """POST /ingest/v1/register. (a) co Bearer+X-MT-Account hop le: EA bao thong tin/lay trang thai;
        (b) khong co token: ghep cap bang PairCode qua auth -> auth tra credential 1 lan (bridge KHONG luu, KHONG log)."""
        ip = self._remote(headers) or "?"
        if len(raw) > MAX_REGISTER_BYTES:
            raise AuthError(413, "body too large")
        if not self.rl_fail.has(f"{ip}|reg"):
            raise AuthError(429, "too many failures", 10.0)
        ok, retry = self.rl_register.allow(ip)
        if not ok:
            raise AuthError(429, "rate limited", retry)
        try:
            info = RegisterIn.model_validate_json(raw)
        except ValidationError:
            self.rl_fail.allow(f"{ip}|reg")
            raise AuthError(422, "schema")
        if headers.get("authorization", "").lower().startswith("bearer ") and headers.get("x-mt-account"):
            acc = headers["x-mt-account"]
            if self.registry.get(acc) is None and _ACC_RE.fullmatch(acc):
                await self.registry.ensure(acc)
            try:
                rec, _ = self.authenticate(headers, raw, RegisterIn)
                await self._claim_nonce_redis(rec.account_id, info.nonce)
            except AuthError as e:
                if e.code in (401, 422, 400):
                    self.rl_fail.allow(f"{ip}|{acc}")
                raise
            await self._note_health(rec, info, headers)
            REGISTERED.labels("token").inc()
            return {"ok": rec.status in ("pending", "active"), "status": rec.status, "account_id": rec.account_id}
        ok, retry = self.rl_register_login.allow(f"{info.platform}:{info.login}")
        if not ok:
            raise AuthError(429, "rate limited", retry)
        res = await self.registry.register({
            "platform": info.platform, "login": info.login, "server": info.server, "company": info.company, "build": info.build,
            "ea": info.ea, "pair_code": info.pair_code, "account_id": info.account_id, "remote_addr": ip,
        })
        REGISTERED.labels(res.status).inc()
        if res.status in ("rejected", "unknown"):
            self.rl_fail.allow(f"{ip}|reg")
        return res.public()

    async def invalidate(self, account_id: str) -> None:
        """auth goi khi master xoay token/HMAC, dinh chi, kich hoat, xoa: bo cache + nap lai NGAY (hieu luc o request ke tiep)."""
        self.registry.invalidate(account_id)
        if _ACC_RE.fullmatch(account_id or ""):
            await self.registry.ensure(account_id)

    # ---------- MT5 truc tiep ----------
    async def poll_mt5_once(self, gw: MT5Gateway) -> None:
        cfg = gw.cfg
        try:
            account = await asyncio.to_thread(gw.get_account)
            positions = await asyncio.to_thread(gw.get_positions)
            orders = await asyncio.to_thread(gw.get_orders)
            quotes = await asyncio.to_thread(gw.get_quotes)
            new_bars: list[Bar] = []
            for s in cfg.watch_symbols:
                for tf in cfg.timeframes:
                    bars = await asyncio.to_thread(gw.get_rates, s, tf, 3)
                    for b in bars:
                        k = (b.symbol, b.tf, b.source)
                        if k not in self._last_bar_pub or b.ts_open > self._last_bar_pub[k]:
                            self._last_bar_pub[k] = b.ts_open
                            new_bars.append(b)
        except Exception as e:  # mat ket noi: de heartbeat monitor canh bao
            log.warning("poll %s loi: %s", cfg.account_id, e)
            return
        await self.publish_quotes(quotes)
        await self.publish_bars(self._raw_bars(new_bars))
        await self._after_data(cfg, gw, account, positions, orders)

    async def monitor_once(self) -> None:
        now = self.clock()
        for fd in (self.feed, self.feed_all, self.feed_fb):
            if not fd.st.enabled:
                continue
            try:
                await self._feed_publish(fd.flush_due(now))
            except Exception:  # noqa: BLE001
                log.exception("feed canon flush loi")
        for aid, cfg in list(self.accounts.items()):
            if aid not in self.gateways:
                continue
            h = self.gateways[aid].health()
            await self.publish_alerts(self.engine.check_heartbeat(aid, h.last_seen, now, cfg.rules, cfg.platform))
            UP.labels(aid).set(1 if h.connected and h.last_seen and (now - h.last_seen).total_seconds() <= cfg.rules.heartbeat_timeout_s else 0)
        await self._health_tick()

    # ---------- vong doi ----------
    async def start(self) -> None:
        for gw in self.gateways.values():
            if isinstance(gw, MT5Gateway):
                try:
                    await asyncio.to_thread(gw.connect)
                except Exception as e:
                    log.error("MT5 %s ket noi that bai: %s", gw.account_id, e)
        await self.registry.refresh()  # nap danh sach tai khoan dong truoc khi nhan ingest
        self._tasks = [asyncio.create_task(self._loop(self.monitor_once, self.settings.monitor_s))]
        for gw in self.gateways.values():
            if isinstance(gw, MT5Gateway):
                self._tasks.append(asyncio.create_task(self._loop(lambda g=gw: self.poll_mt5_once(g), self.settings.mt5_poll_s)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for gw in self.gateways.values():
            if isinstance(gw, MT5Gateway):
                gw.close()

    @staticmethod
    async def _loop(fn, every: float) -> None:
        while True:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("loop error")
            await asyncio.sleep(every)

    # ---------- view ----------
    def accounts_view(self) -> list[dict]:
        now = self.clock()
        out = []
        for aid, cfg in list(self.accounts.items()):
            gw = self.gateways.get(aid)
            if gw is None:
                continue
            h = gw.health()
            row: dict[str, Any] = {"account_id": aid, "platform": cfg.platform, "transport": cfg.transport, "connected": h.connected, "last_seen": h.last_seen.isoformat() if h.last_seen else None, "age_s": (now - h.last_seen).total_seconds() if h.last_seen else None, "detail": h.detail}
            eh = self.health.get(aid)
            rec = self.registry.get(aid)
            row["account_state"] = rec.status if rec else "active"
            if eh is not None:
                row.update(ea_status=eh.status, ea_reason=eh.reason, latency_ms=eh.rtt_ms, skew_s=eh.skew_s, ea_version=eh.ea_version, build=eh.build, broker=eh.broker, server=eh.server, remote_addr=eh.remote_addr)
            try:
                a = gw.get_account()
                row.update(balance=a.balance, equity=a.equity, margin_level=a.margin_level, margin_mode=a.margin_mode, currency=a.currency, positions=len(gw.get_positions()))
            except Exception:
                pass
            out.append(row)
        for aid, eh in list(self.health.items()):  # tai khoan pending: EA da lien lac nhung chua nhan du lieu
            if aid not in self.accounts:
                rec = self.registry.get(aid)
                out.append({"account_id": aid, "platform": eh.platform, "transport": "agent", "connected": eh.status != "offline", "last_seen": eh.last_seen.isoformat() if eh.last_seen else None,
                            "age_s": (now - eh.last_seen).total_seconds() if eh.last_seen else None, "detail": "pending", "account_state": rec.status if rec else "pending", **{k: v for k, v in self._health_item(eh).items() if k in ("latency_ms", "skew_s", "ea_version", "build", "broker", "server", "remote_addr")}, "ea_status": eh.status, "ea_reason": eh.reason})
        return out


def create_app(service: BridgeService, *, background: bool = False):
    @asynccontextmanager
    async def lifespan(_app):
        if background:
            await service.start()
        yield
        if background:
            await service.stop()

    app = make_app("mt-bridge")
    app.router.lifespan_context = lifespan

    def _headers(request: Request) -> dict[str, str]:
        h = {k.lower(): v for k, v in request.headers.items()}
        h["x-remote-addr"] = request.client.host if request.client else ""  # khong tin header khach tu dat
        return h

    def _err(e: AuthError) -> JSONResponse:
        hdr = {"Retry-After": str(max(1, int(e.retry_after + 0.999)))} if e.retry_after else None
        return JSONResponse({"ok": False, "error": e.msg}, status_code=e.code, headers=hdr)

    @app.post("/ingest/v1")
    async def ingest(request: Request):
        raw = await request.body()
        try:
            res = await service.handle_ingest(_headers(request), raw)
        except AuthError as e:
            return _err(e)
        return JSONResponse(res, status_code=202 if res.get("status") == "pending" else 200)

    @app.post("/ingest/v1/register")
    async def register(request: Request):
        raw = await request.body()
        try:
            res = await service.handle_register(_headers(request), raw)
        except AuthError as e:
            return _err(e)
        code = {"ok": 200, "rejected": 403, "suspended": 403, "unknown": 404, "rate_limited": 429, "error": 502}.get(res["status"] if not res.get("ok") else "ok", 200)
        return JSONResponse(res, status_code=code, headers={"Cache-Control": "no-store"})

    @app.post("/internal/invalidate")
    async def invalidate(request: Request):
        tok = service.settings.auth_token
        if not tok:
            return JSONResponse({"error": "service token not configured"}, status_code=503)
        if not verify_token(tok, request.headers.get("authorization", "").removeprefix("Bearer ").strip()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
            aid = str(body.get("account_id", ""))
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "bad request"}, status_code=400)
        await service.invalidate(aid)
        return {"ok": True}

    @app.get("/accounts")
    async def accounts(request: Request):
        tok = service.settings.admin_token
        if not tok:
            # fail-closed: chua cau hinh token -> tu choi (tru dev mode ro rang)
            if not service.settings.admin_insecure_dev:
                return JSONResponse({"error": "admin token not configured"}, status_code=503)
        elif not verify_token(tok, request.headers.get("authorization", "").removeprefix("Bearer ").strip()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return service.accounts_view()

    return app


def create_default_app():  # uvicorn mtbridge.service:create_default_app --factory
    from tscommon import Bus, get_settings

    st = Settings()
    cfg = load_config(st.config_path) if (os.path.exists(st.config_path) or not st.auth_url) else BridgeConfig(accounts=[])
    bus = Bus.from_url(get_settings().redis_url)
    registry: AccountRegistry = StaticRegistry(cfg)
    if st.auth_url:  # tai khoan dong tu service auth (uu tien) + accounts.yaml (tuong thich/du phong)
        registry = CompositeRegistry(HttpRegistry(st.auth_url, st.auth_token, ttl_s=st.auth_ttl_s, max_stale_s=st.auth_max_stale_s), registry)
    return create_app(BridgeService(cfg, bus, settings=st, registry=registry), background=True)
