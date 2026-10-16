"""Provisioning dong: AccountRegistry (in-memory/HTTP/YAML), pending/suspended, thu hoi tuc thi, HMAC mac dinh, ghep cap, suc khoe EA, rate limit."""
import asyncio
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from scenario import T0, make_cfg, post, to_ea_batch

from mtbridge.accounts import BridgeConfig
from mtbridge.protocol import hash_token, sign
from mtbridge.registry import CompositeRegistry, HttpRegistry, InMemoryRegistry, StaticRegistry
from mtbridge.service import STATUS_STREAM, BridgeService, Settings, create_app


class FakePub:
    def __init__(self):
        self.events = []

    async def publish(self, stream, event):
        self.events.append((stream, event))

    def on(self, stream):
        return [e for s, e in self.events if s == stream]


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def make(static_cfgs=(), *, settings=None, registry=None):
    mem = InMemoryRegistry()
    clock, pub = Clock(T0), FakePub()
    cfg = BridgeConfig(accounts=list(static_cfgs))
    reg = registry or (CompositeRegistry(mem, StaticRegistry(cfg)) if static_cfgs else mem)
    svc = BridgeService(cfg, pub, settings=settings or Settings(admin_token="adm", auth_token="svc-token-123456"), clock=clock, registry=reg)
    return svc, TestClient(create_app(svc)), pub, clock, mem


def ea(aid, plat, **kw):
    return to_ea_batch(aid, plat, **kw)


def test_active_account_authenticates_and_publishes():
    svc, client, pub, _, mem = make()
    c = mem.create("mt5", 1001, status="active")
    r = post(client, c["token"], ea("mt5:1001", "mt5"), secret=c["hmac_secret"])
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert pub.on("account.snapshots")[0].payload["account_id"] == "mt5:1001"
    assert svc.accounts["mt5:1001"].platform == "mt5"


def test_pending_gets_202_and_no_data_published():
    svc, client, pub, _, mem = make()
    c = mem.create("mt4", 2002, status="pending")
    r = post(client, c["token"], ea("mt4:2002", "mt4"), secret=c["hmac_secret"])
    assert r.status_code == 202 and r.json()["status"] == "pending"
    assert not pub.on("account.snapshots") and not pub.on("md.quotes") and not pub.on("md.bars") and not pub.on("account.deals")
    # master duyet -> request ke tiep nhan du lieu ngay
    mem.set_status("mt4:2002", "active")
    assert post(client, c["token"], ea("mt4:2002", "mt4"), secret=c["hmac_secret"]).status_code == 200
    assert pub.on("account.snapshots")


def test_suspended_403_with_audit_but_wrong_token_is_401():
    svc, client, pub, _, mem = make()
    c = mem.create("mt5", 3003, status="active")
    assert post(client, c["token"], ea("mt5:3003", "mt5"), secret=c["hmac_secret"]).status_code == 200
    mem.set_status("mt5:3003", "suspended")
    n = len(pub.events)
    r = post(client, c["token"], ea("mt5:3003", "mt5"), secret=c["hmac_secret"])
    assert r.status_code == 403 and r.json()["error"] == "suspended"
    assert len(pub.events) == n  # khong publish du lieu
    assert [a[1] for a in mem.audits] == ["ea_rejected_suspended"]
    post(client, c["token"], ea("mt5:3003", "mt5"), secret=c["hmac_secret"])
    assert len(mem.audits) == 1  # audit gioi han tan suat (5 phut)
    assert post(client, "x" * 40, ea("mt5:3003", "mt5")).status_code == 401  # khong lo trang thai cho ke khong co token


def test_token_rotation_revokes_instantly():
    _, client, _, _, mem = make()
    c = mem.create("mt5", 4004, status="active")
    assert post(client, c["token"], ea("mt5:4004", "mt5"), secret=c["hmac_secret"]).status_code == 200
    new = mem.rotate_token("mt5:4004")
    assert post(client, c["token"], ea("mt5:4004", "mt5"), secret=c["hmac_secret"]).status_code == 401
    assert post(client, new, ea("mt5:4004", "mt5"), secret=c["hmac_secret"]).status_code == 200
    mem.rotate_hmac("mt5:4004")
    assert post(client, new, ea("mt5:4004", "mt5"), secret=c["hmac_secret"]).status_code == 401  # secret cu


def test_hmac_default_on_and_per_account_override():
    _, client, _, _, mem = make()
    a = mem.create("mt5", 5001, status="active")                       # mac dinh require_hmac=True
    assert post(client, a["token"], ea("mt5:5001", "mt5")).status_code == 401  # thieu chu ky
    assert post(client, a["token"], ea("mt5:5001", "mt5"), headers={"X-MT-Sig": "00" * 32}).status_code == 401
    assert post(client, a["token"], ea("mt5:5001", "mt5"), secret=a["hmac_secret"]).status_code == 200
    b = mem.create("mt5", 5002, status="active", require_hmac=False)  # tuong thich EA cu: khong ep, nhung co chu ky thi phai dung
    assert post(client, b["token"], ea("mt5:5002", "mt5")).status_code == 200
    assert post(client, b["token"], ea("mt5:5002", "mt5"), headers={"X-MT-Sig": "00" * 32}).status_code == 401


def test_hmac_signature_must_cover_body():
    _, client, _, _, mem = make()
    a = mem.create("mt4", 5101, status="active")
    b = ea("mt4:5101", "mt4")
    raw = json.dumps(b).encode()
    sig = sign(a["hmac_secret"], b["ts"], b["nonce"], raw)
    b2 = dict(b, seq=2)  # doi body sau khi ky
    r = client.post("/ingest/v1", content=json.dumps(b2).encode(), headers={"Authorization": f"Bearer {a['token']}", "X-MT-Account": "mt4:5101", "X-MT-Sig": sig})
    assert r.status_code == 401


def test_yaml_and_dynamic_coexist_and_yaml_hmac_flag(monkeypatch):
    monkeypatch.setenv("TOK_y1", "yaml-token-y1-xxxxxxxxxxxx")
    monkeypatch.setenv("TOK_y2", "yaml-token-y2-xxxxxxxxxxxx")
    monkeypatch.setenv("HM_y2", "yaml-hmac-y2")
    cfgs = [make_cfg("y1", "mt4"), make_cfg("y2", "mt5", hmac_secret_env="HM_y2"), make_cfg("y3", "mt4", require_hmac=True)]
    monkeypatch.setenv("TOK_y3", "yaml-token-y3-xxxxxxxxxxxx")
    _, client, _, _, mem = make(cfgs)
    d = mem.create("mt5", 6006, status="active")
    assert post(client, "yaml-token-y1-xxxxxxxxxxxx", ea("y1", "mt4")).status_code == 200
    assert post(client, "yaml-token-y2-xxxxxxxxxxxx", ea("y2", "mt5")).status_code == 401
    assert post(client, "yaml-token-y2-xxxxxxxxxxxx", ea("y2", "mt5"), secret="yaml-hmac-y2").status_code == 200
    assert post(client, "yaml-token-y3-xxxxxxxxxxxx", ea("y3", "mt4")).status_code == 401  # require_hmac=True nhung khong co secret: fail-closed
    assert post(client, d["token"], ea("mt5:6006", "mt5"), secret=d["hmac_secret"]).status_code == 200


def test_pairing_register_flow_returns_credentials_once():
    svc, client, pub, _, mem = make()
    c = mem.create("mt5", 7007, status="pending")
    body = {"v": 1, "platform": "mt5", "login": 7007, "server": "Demo-Srv", "company": "Broker X", "build": 6253, "ea": "1.1", "pair_code": c["pair_code"]}
    r = client.post("/ingest/v1/register", json=body)
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["status"] == "active" and j["account_id"] == "mt5:7007" and j["token"] and j["hmac_secret"]
    assert r.headers["cache-control"] == "no-store"
    # credential moi dung duoc ngay
    assert post(client, j["token"], ea("mt5:7007", "mt5"), secret=j["hmac_secret"]).status_code == 200
    # token cu (c["token"]) da bi vo hieu khi giao credential moi; ma ghep cap dung 1 lan
    assert post(client, c["token"], ea("mt5:7007", "mt5"), secret=c["hmac_secret"]).status_code == 401
    r2 = client.post("/ingest/v1/register", json=body)
    assert r2.status_code == 403 and "token" not in r2.json()


def test_register_rejects_bad_code_wrong_login_and_is_rate_limited():
    _, client, _, _, mem = make()
    c = mem.create("mt5", 7100, status="pending")
    base = {"v": 1, "platform": "mt5", "login": 7100, "pair_code": "ZZZZ-NOPE"}
    r = client.post("/ingest/v1/register", json=base)
    assert r.status_code == 403 and r.json()["status"] == "rejected"
    r = client.post("/ingest/v1/register", json=dict(base, login=9999, pair_code=c["pair_code"]))
    assert r.status_code == 403
    assert client.post("/ingest/v1/register", json=dict(base, bogus=1)).status_code == 422
    codes = [client.post("/ingest/v1/register", json=base).status_code for _ in range(12)]
    assert 429 in codes  # gioi han toc do theo IP/tai khoan


def test_register_with_token_reports_health_and_status():
    svc, client, pub, _, mem = make()
    c = mem.create("mt4", 7200, status="pending")
    b = {"v": 1, "platform": "mt4", "login": 7200, "server": "Srv-1", "company": "Acme Ltd", "build": 1492, "ea": "1.1", "account_id": "mt4:7200", "ts": int(T0.timestamp()), "nonce": "reg-nonce-0001"}
    raw = json.dumps(b).encode()
    r = client.post("/ingest/v1/register", content=raw, headers={"Authorization": f"Bearer {c['token']}", "X-MT-Account": "mt4:7200", "X-MT-Sig": sign(c["hmac_secret"], b["ts"], b["nonce"], raw)})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    h = svc.health["mt4:7200"]
    assert (h.broker, h.build, h.ea_version, h.server) == ("Acme Ltd", 1492, "1.1", "Srv-1")
    # khong co chu ky -> tu choi (HMAC mac dinh)
    b["nonce"] = "reg-nonce-0002"
    r = client.post("/ingest/v1/register", content=json.dumps(b).encode(), headers={"Authorization": f"Bearer {c['token']}", "X-MT-Account": "mt4:7200"})
    assert r.status_code == 401


def test_health_events_only_on_transitions_and_flush_to_registry():
    async def run():
        svc, client, pub, clock, mem = make()
        c = mem.create("mt5", 8008, status="active")

        def go(**agent):
            b = ea("mt5:8008", "mt5", ts=clock.t)
            b["agent"] = dict({"ea": "1.1", "build": 6253, "company": "Broker X", "rtt_ms": 120, "fail": 0}, **agent)
            return post(client, c["token"], b, secret=c["hmac_secret"])

        assert go().status_code == 200 and go().status_code == 200
        ev = pub.on(STATUS_STREAM)
        assert [e.payload["status"] for e in ev] == ["online"]  # lan dau; lan 2 khong doi -> khong phat lai
        assert ev[0].type == "mt_account_status" and ev[0].payload["ea_version"] == "1.1" and "remote_addr" not in ev[0].payload
        assert go(rtt_ms=9000).status_code == 200
        assert [e.payload["status"] for e in pub.on(STATUS_STREAM)] == ["online", "degraded"]
        assert "do tre" in pub.on(STATUS_STREAM)[-1].payload["reason"]
        assert go(rtt_ms=100).status_code == 200
        assert pub.on(STATUS_STREAM)[-1].payload["status"] == "online"
        await svc.monitor_once()
        assert mem.seen and mem.seen[-1]["account_id"] == "mt5:8008" and mem.seen[-1]["latency_ms"] == 100 and mem.seen[-1]["broker"] == "Broker X"
        assert "remote_addr" in mem.seen[-1]  # chi gui cho auth (master), khong len bus
        clock.t = T0 + timedelta(seconds=500)  # qua heartbeat_timeout_s
        await svc.monitor_once()
        assert pub.on(STATUS_STREAM)[-1].payload["status"] == "offline"
        n = len(pub.on(STATUS_STREAM))
        await svc.monitor_once()
        assert len(pub.on(STATUS_STREAM)) == n
        row = [r for r in svc.accounts_view() if r["account_id"] == "mt5:8008"][0]
        assert row["ea_status"] == "offline" and row["ea_version"] == "1.1" and row["broker"] == "Broker X" and row["account_state"] == "active"

    asyncio.run(run())


def test_rate_limit_per_account_isolated():
    _, client, _, _, mem = make(settings=Settings(admin_token="adm", rate_per_s=1.0, rate_burst=3.0))
    a, b = mem.create("mt5", 9001, status="active"), mem.create("mt5", 9002, status="active")
    codes = [post(client, a["token"], ea("mt5:9001", "mt5"), secret=a["hmac_secret"]).status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200] and 429 in codes
    r = post(client, a["token"], ea("mt5:9001", "mt5"), secret=a["hmac_secret"])
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert post(client, b["token"], ea("mt5:9002", "mt5"), secret=b["hmac_secret"]).status_code == 200  # tai khoan khac khong bi anh huong


def test_failed_auth_blocks_ip():
    _, client, _, _, mem = make(settings=Settings(admin_token="adm", fail_burst=5, fail_per_s=0.01))
    a = mem.create("mt5", 9101, status="active")
    codes = [post(client, "bad-token-%d-xxxxxxxxxxxxxxxx" % i, ea("mt5:9101", "mt5")).status_code for i in range(8)]
    assert codes[:5] == [401] * 5 and set(codes[5:]) == {429}
    assert post(client, a["token"], ea("mt5:9101", "mt5"), secret=a["hmac_secret"]).status_code == 429  # (IP, tai khoan) bi khoa tam thoi
    # EA khac cung IP (NAT/proxy) KHONG bi anh huong
    b = mem.create("mt5", 9102, status="active")
    assert post(client, b["token"], ea("mt5:9102", "mt5"), secret=b["hmac_secret"]).status_code == 200
    # do quet tai khoan la: dung chung 1 xo theo IP
    codes = [post(client, "scan-token-xxxxxxxxxxxxxxxxxxxx", ea("mt5:%d" % (500000 + i), "mt5"), account="mt5:%d" % (500000 + i)).status_code for i in range(8)]
    assert codes[:5] == [401] * 5 and set(codes[5:]) == {429}


def test_registry_unavailable_503_not_401_and_stale_if_error():
    async def run():
        svc, client, pub, clock, mem = make()
        c = mem.create("mt5", 9201, status="active")
        mem.available = False
        r = post(client, c["token"], ea("mt5:9201", "mt5"), secret=c["hmac_secret"])
        assert r.status_code == 503
        mem.available = True
        assert post(client, c["token"], ea("mt5:9201", "mt5"), secret=c["hmac_secret"]).status_code == 200

    asyncio.run(run())


def test_invalidate_endpoint_requires_service_token():
    svc, client, _, _, mem = make()
    assert client.post("/internal/invalidate", json={"account_id": "mt5:1"}).status_code == 401
    assert client.post("/internal/invalidate", headers={"Authorization": "Bearer nope"}, json={"account_id": "mt5:1"}).status_code == 401
    assert client.post("/internal/invalidate", headers={"Authorization": "Bearer svc-token-123456"}, json={"account_id": "mt5:1"}).json() == {"ok": True}
    svc2 = BridgeService(BridgeConfig(accounts=[]), FakePub(), settings=Settings(admin_token="adm", auth_token=""), clock=Clock(T0))
    assert TestClient(create_app(svc2)).post("/internal/invalidate", json={"account_id": "x"}).status_code == 503


# ------------------------------------------------------------------------------------------ HttpRegistry (fake auth)
class FakeAuth:
    """Gia lap service auth: lam nguon cho HttpRegistry qua `fetch` tiem vao."""

    def __init__(self):
        self.accounts = {}
        self.down = False
        self.calls = []
        self.registered = []
        self.seen = []

    def put(self, aid, platform, token, *, status="active", hmac="h-secret", **kw):
        self.accounts[aid] = dict(account_id=aid, platform=platform, status=status, ea_token_hash=hash_token(token), hmac_secret=hmac, require_hmac=True, rev=1, **kw)

    async def fetch(self, method, path, body):
        self.calls.append((method, path))
        if self.down:
            raise ConnectionError("auth down")
        if method == "GET" and path == "/internal/mt-accounts":
            return 200, {"rev": 1, "accounts": list(self.accounts.values())}
        if method == "GET" and path.startswith("/internal/mt-accounts/"):
            aid = path.rsplit("/", 1)[1].replace("%3A", ":")
            return (200, self.accounts[aid]) if aid in self.accounts else (404, None)
        if path.endswith("/seen"):
            self.seen.extend(body["items"])
            return 200, {"ok": True}
        if path.endswith("/register"):
            self.registered.append(body)
            return 200, {"status": "pending", "account_id": "mt5:1", "pairing_code": "AB12CD", "message": "cho duyet"}
        return 200, {}


def test_http_registry_refresh_ensure_negcache_invalidate_and_stale():
    async def run():
        t = [1000.0]
        fa = FakeAuth()
        fa.put("mt5:1", "mt5", "tok-one-xxxxxxxxxxxxxxxx")
        reg = HttpRegistry("http://auth:8000", "svc", ttl_s=15, max_stale_s=100, clock=lambda: t[0], fetch=fa.fetch)
        await reg.refresh()
        assert reg.get("mt5:1").status == "active" and reg.healthy
        # tai khoan moi do master tao: ensure() tra cuu le (khong cho refresh ke tiep)
        fa.put("mt5:2", "mt5", "tok-two-xxxxxxxxxxxxxxxx", status="pending")
        assert reg.get("mt5:2") is None
        await reg.ensure("mt5:2")
        assert reg.get("mt5:2").status == "pending"
        # id la: 404 -> negative cache (khong dap auth moi request)
        n = len(fa.calls)
        await reg.ensure("mt5:999")
        await reg.ensure("mt5:999")
        assert len(fa.calls) == n + 1 and reg.get("mt5:999") is None
        # thu hoi: master dinh chi -> invalidate + ensure nap ngay
        fa.accounts["mt5:1"]["status"] = "suspended"
        assert reg.get("mt5:1").status == "active"  # cache cu den khi TTL/invalidate
        reg.invalidate("mt5:1")
        await reg.ensure("mt5:1")
        assert reg.get("mt5:1").status == "suspended"
        # auth down: dung cache (stale-if-error) roi fail-closed khi qua max_stale
        fa.down = True
        t[0] += 50
        await reg.refresh()
        assert not reg.healthy and reg.get("mt5:1") is not None
        t[0] += 60
        assert reg.get("mt5:1") is None  # qua max_stale -> khong xac thuc nua
        fa.down = False
        await reg.refresh()
        assert reg.healthy and reg.get("mt5:1") is not None and reg.get("mt5:999") is None
        # tai khoan bi xoa o master -> mat khoi cache sau refresh
        del fa.accounts["mt5:2"]
        await reg.refresh()
        assert reg.get("mt5:2") is None
        # register/report_seen di qua auth
        res = await reg.register({"platform": "mt5", "login": 1, "pair_code": "AB12CD"})
        assert res.status == "pending" and res.pairing_code == "AB12CD" and fa.registered
        await reg.report_seen([{"account_id": "mt5:1"}])
        assert fa.seen == [{"account_id": "mt5:1"}]
        fa.down = True
        assert (await reg.register({})).status == "error"

    asyncio.run(run())


def test_end_to_end_with_http_registry_and_new_account_visible_immediately():
    async def run():
        fa = FakeAuth()
        reg = HttpRegistry("http://auth:8000", "svc", ttl_s=15, clock=lambda: T0.timestamp(), fetch=fa.fetch)
        svc = BridgeService(BridgeConfig(accounts=[]), FakePub(), settings=Settings(admin_token="adm", auth_token="svc-token-123456"), clock=Clock(T0), registry=reg)
        await reg.refresh()
        fa.put("mt4:42", "mt4", "tok-42-xxxxxxxxxxxxxxxxxxxx", hmac="s42")
        b = ea("mt4:42", "mt4")
        raw = json.dumps(b).encode()
        h = {"authorization": "Bearer tok-42-xxxxxxxxxxxxxxxxxxxx", "x-mt-account": "mt4:42", "x-mt-sig": sign("s42", b["ts"], b["nonce"], raw), "x-remote-addr": "203.0.113.9"}
        res = await svc.handle_ingest(h, raw)  # tai khoan vua tao: ensure() tra cuu le, khong cho refresh
        assert res["ok"] and res["status"] == "active"
        assert svc.health["mt4:42"].remote_addr == "203.0.113.9"
        await svc.monitor_once()
        assert fa.seen and fa.seen[-1]["account_id"] == "mt4:42" and fa.seen[-1]["remote_addr"] == "203.0.113.9"

    asyncio.run(run())


def test_nonce_memory_bounded_under_many_accounts():
    from mtbridge.protocol import NonceCache

    t = [0.0]
    nc = NonceCache(window_s=300, max_items=1000, clock=lambda: t[0])
    for i in range(5000):
        t[0] += 0.1
        assert nc.check_and_add(f"acc{i % 200}", f"n{i:08d}")
    assert len(nc._seen) <= 3100  # = ~window/khoang cach (cua so 300s x 10/s), khong tang vo han
    t[0] += 1000
    nc.check_and_add("x", "y" * 8)
    assert len(nc._seen) == 1


def test_pairing_flow_is_not_an_order_path():
    """Dam bao cac duong moi chi doc/khai bao: khong co route dat lenh."""
    svc, client, _, _, _ = make()
    paths = {r.path for r in client.app.routes}
    assert not any(any(w in p.lower() for w in ("order", "trade", "close", "modify")) for p in paths), paths


@pytest.mark.parametrize("bad", ["mt5:12 34", "mt5:1;2", "../x", "a" * 80])
def test_account_id_charset(bad):
    _, client, _, _, mem = make()
    c = mem.create("mt5", 1, status="active")
    b = ea("mt5:1", "mt5")
    b["account_id"] = bad
    assert post(client, c["token"], b, account="mt5:1", secret=c["hmac_secret"]).status_code == 422
