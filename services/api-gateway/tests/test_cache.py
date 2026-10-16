"""Cache phản hồi gateway (api_gateway/cache.py): khoá/TTL/stampede/fail-open + AN TOÀN DỮ LIỆU (IDOR, giả header, đầu độc cache). docs/PERFORMANCE.md."""
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

import fakeredis.aioredis as fr
import httpx
import pytest

from api_gateway import riskmon_routes
from api_gateway.app import create_app
from api_gateway.cache import STREAM_DOMAINS, ResponseCache, _cc, POLICIES
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

NOW = datetime.now(timezone.utc)
SECRET = "trust-secret-xyz"
KEY = {"X-API-Key": "tok1"}


def hdr(role, accounts="", uid="u1", secret=SECRET):
    h = {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": secret}
    if accounts:
        h["X-Accounts"] = accounts
    return h


CLIENT_A, CLIENT_B = hdr("client", "mt5:1", "ua"), hdr("client", "mt5:2", "ub")
MASTER = hdr("master", "*", "um")


class CRepo(InMemoryRepo):
    def __init__(self, **t):
        super().__init__(**t)
        self.n = Counter()
        self.delay = 0.0

    async def news(self, *a, **k):
        self.n["news"] += 1
        await asyncio.sleep(self.delay)
        return await super().news(*a, **k)

    async def accounts_latest(self, *a, **k):
        self.n["accounts"] += 1
        return await super().accounts_latest(*a, **k)


def repo():
    snap = lambda acc, bal: {"account_id": acc, "platform": "mt5", "ts": NOW, "balance": bal, "equity": bal, "margin": 0}  # noqa: E731
    return CRepo(account_snapshots=[snap("mt5:1", 100), snap("mt5:2", 200), snap("demo-mt4-01", 300)],
                 quotes=[{"symbol": "EURUSD", "ts": NOW, "bid": 1.1, "ask": 1.2, "source": "t"}],
                 news_items=[{"url": f"u{i}", "title": "n" * 40 + str(i), "published_at": NOW, "source": "rss", "symbols": ["EURUSD"]} for i in range(60)],
                 alerts=[{"id": 1, "ts": NOW, "level": "warn", "title": "w"}])


def settings(**kw):
    return GatewaySettings(**{"api_tokens": ("tok1",), "auth_disabled": False, "cors_origins": (), "max_page_size": 100, "ws_max_connections": 2,
                              "auth_trust_secret": SECRET, **kw})


@pytest.fixture
async def env():
    rds = fr.FakeRedis()                    # redis-cache (bytes)
    cache = ResponseCache(rds, warm=False, invalidate=False)
    r = repo()
    app = create_app(settings(), r, fr.FakeRedis(decode_responses=True), cache=cache)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, cache, r, rds


async def keys(rds):
    return sorted(k.decode() for k in await rds.keys("cache:r1:*"))


async def test_miss_hit_etag_304_headers(env):
    c, cache, r, rds = env
    a = await c.get("/v1/news?limit=5", headers=MASTER)
    b = await c.get("/v1/news?limit=5", headers=MASTER)
    assert (a.status_code, b.status_code) == (200, 200) and a.content == b.content
    assert (a.headers["x-gw-cache"], b.headers["x-gw-cache"]) == ("MISS", "HIT") and r.n["news"] == 1
    assert b.headers["cache-control"].startswith("private, max-age=") and "stale-while-revalidate" in b.headers["cache-control"]
    assert int(b.headers["x-accel-expires"]) >= 1
    c304 = await c.get("/v1/news?limit=5", headers={**MASTER, "If-None-Match": b.headers["etag"]})
    assert c304.status_code == 304 and c304.content == b""
    assert (await c.get("/v1/news?limit=5", headers={**MASTER, "If-None-Match": 'W/"x"'})).status_code == 200


async def test_query_is_normalized(env):
    c, cache, r, rds = env
    await c.get("/v1/news?limit=5&symbol=EURUSD", headers=MASTER)
    x = await c.get("/v1/news?symbol=EURUSD&limit=5", headers=MASTER)
    assert x.headers["x-gw-cache"] == "HIT" and r.n["news"] == 1
    y = await c.get("/v1/news?symbol=EURUSD&limit=6", headers=MASTER)
    assert y.headers["x-gw-cache"] == "MISS" and r.n["news"] == 2


async def test_only_200_json_is_cached(env):
    c, cache, r, rds = env
    assert (await c.get("/v1/bars?symbol=EURUSD&tf=BAD", headers=MASTER)).status_code == 422
    assert (await c.get("/v1/bars?symbol=EURUSD&tf=BAD", headers=MASTER)).status_code == 422
    assert await keys(rds) == []


async def test_swr_serves_stale_then_refreshes(env):
    c, cache, r, rds = env
    await c.get("/v1/news", headers=MASTER)
    (k,) = await keys(rds)
    raw = await rds.get(k)
    i = raw.index(b"\n")
    meta = json.loads(raw[:i])
    meta["s"] = int(datetime.now().timestamp() * 1000) - 1000          # hết hạn mềm, còn trong cửa sổ stale
    ttl = await rds.pttl(k)
    await rds.set(k, json.dumps(meta, separators=(",", ":")).encode() + raw[i:], px=max(ttl, 5000))
    s = await c.get("/v1/news", headers=MASTER)
    assert s.headers["x-gw-cache"] == "STALE"
    await asyncio.sleep(0.15)
    assert r.n["news"] == 2                                              # đã làm mới nền
    assert (await c.get("/v1/news", headers=MASTER)).headers["x-gw-cache"] == "HIT"


async def test_event_version_bump_invalidates(env):
    c, cache, r, rds = env
    await c.get("/v1/news", headers=MASTER)
    assert (await c.get("/v1/news", headers=MASTER)).headers["x-gw-cache"] == "HIT"
    await cache.bump(cache.event_vkeys("news.items", {"title": "x"}))
    s = await c.get("/v1/news", headers=MASTER)
    assert s.headers["x-gw-cache"] == "STALE"                                  # bị vô hiệu hoá: phục vụ bản cũ (SWR) + làm mới nền
    await asyncio.sleep(0.15)
    assert r.n["news"] == 2 and (await c.get("/v1/news", headers=MASTER)).headers["x-gw-cache"] == "HIT"
    assert cache.event_vkeys("md.bars", {"symbol": "EURUSD", "tf": "H1"}) == {"bars:EURUSD:H1"}
    assert cache.event_vkeys("md.bars", {}) == {"bars:all"} and cache.event_vkeys("md.bars", {"symbol": "EURUSD", "tf": "M1"}) == set()
    assert cache.event_vkeys("md.quotes", {"symbol": "EURUSD"}) == set() and set(STREAM_DOMAINS) >= {"md.bars", "news.items", "calendar.events"}


async def test_single_flight_no_stampede(env):
    c, cache, r, rds = env
    r.delay = 0.15
    res = await asyncio.gather(*[c.get("/v1/news?limit=7", headers=MASTER) for _ in range(40)])
    assert all(x.status_code == 200 for x in res) and r.n["news"] == 1
    assert len({x.content for x in res}) == 1


async def test_fail_open_when_redis_breaks():
    class Broken:
        async def mget(self, *a, **k):
            raise ConnectionError("down")

        async def set(self, *a, **k):
            raise ConnectionError("down")

        async def exists(self, *a, **k):
            raise ConnectionError("down")

    cache = ResponseCache(Broken(), warm=False, invalidate=False)
    r = repo()
    app = create_app(settings(), r, fr.FakeRedis(decode_responses=True), cache=cache)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        a = await c.get("/v1/news", headers=MASTER)
        for _ in range(5):                                   # 5 lỗi liên tiếp mở mạch 3s: các request sau đi thẳng app
            b = await c.get("/v1/news", headers=MASTER)
    assert a.status_code == b.status_code == 200 and a.headers.get("x-gw-cache") in (None, "BYPASS", "MISS") and r.n["news"] == 6 and not cache.active


async def test_kill_switch_key_bypasses_cache(env):
    c, cache, r, rds = env
    await c.get("/v1/news", headers=MASTER)
    await rds.set("cache:ctl:off", b"1")
    x = await c.get("/v1/news", headers=MASTER)
    assert x.status_code == 200 and "x-gw-cache" not in x.headers and r.n["news"] == 2
    await rds.delete("cache:ctl:off")
    assert (await c.get("/v1/news", headers=MASTER)).headers["x-gw-cache"] == "HIT"


async def test_disabled_cache_is_inert():
    cache = ResponseCache(None)
    app = create_app(settings(), repo(), fr.FakeRedis(decode_responses=True), cache=cache)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        x = await c.get("/v1/news", headers=MASTER)
    assert x.status_code == 200 and "x-gw-cache" not in x.headers


async def test_compression_roundtrip_large_body(env):
    c, cache, r, rds = env
    a = await c.get("/v1/news?limit=60", headers=MASTER)
    (k,) = await keys(rds)
    raw = await rds.get(k)
    meta = json.loads(raw[: raw.index(b"\n")])
    assert len(a.content) > 1024 and meta["z"] in (1, 2) and len(raw) < len(a.content)
    b = await c.get("/v1/news?limit=60", headers=MASTER)
    assert b.headers["x-gw-cache"] == "HIT" and b.content == a.content


# ------------------------------------------------------------------ AN TOÀN: IDOR / giả mạo / đầu độc cache
async def test_idor_account_scoped_routes_never_cross_clients(env):
    c, cache, r, rds = env
    ids = lambda resp: sorted(x["account_id"] for x in resp.json())  # noqa: E731
    for _ in range(2):                                   # lần 2 = HIT
        assert ids(await c.get("/v1/accounts", headers=CLIENT_A)) == ["mt5:1"]
        assert ids(await c.get("/v1/accounts", headers=CLIENT_B)) == ["mt5:2"]
        assert ids(await c.get("/v1/accounts", headers=MASTER)) == ["demo-mt4-01", "mt5:1", "mt5:2"]
    assert (await c.get("/v1/accounts", headers=CLIENT_A)).headers["x-gw-cache"] == "HIT"
    # client không có tài khoản nào: danh sách rỗng, không nhận bản của người khác
    assert (await c.get("/v1/accounts", headers=hdr("client", "", "uz"))).json() == []
    # 2 client CÙNG tập tài khoản khác user_id dùng chung bản (không chứa user_id) — nhưng khác tập thì khác khoá
    ks = await keys(rds)
    assert len({k.split(":")[2] for k in ks}) == 4      # m, c.<A>, c.<B>, c.<rỗng>
    assert not any("ua" in k.split(":")[2] or "ub" in k.split(":")[2] for k in ks)


async def test_overview_accounts_section_isolated(env):
    c, cache, r, rds = env
    for who, want in ((CLIENT_A, ["mt5:1"]), (CLIENT_B, ["mt5:2"]), (CLIENT_A, ["mt5:1"]), (MASTER, ["demo-mt4-01", "mt5:1", "mt5:2"])):
        j = (await c.get("/v1/overview", headers=who)).json()
        assert sorted(a["account_id"] for a in j["accounts"]) == want


async def test_equity_history_foreign_account_403_not_cached(env):
    c, cache, r, rds = env
    ok = await c.get("/v1/equity-history?account_id=mt5:1", headers=CLIENT_A)
    assert ok.status_code == 200
    for _ in range(2):
        assert (await c.get("/v1/equity-history?account_id=mt5:1", headers=CLIENT_B)).status_code == 403
        assert (await c.get("/v1/equity-history?account_id=mt5:2", headers=CLIENT_A)).status_code == 403
    assert (await c.get("/v1/equity-history?account_id=mt5:1&account_id=mt5:2", headers=CLIENT_A)).status_code == 403


async def test_forged_identity_headers_cannot_read_or_poison(env):
    c, cache, r, rds = env
    assert (await c.get("/v1/accounts", headers=MASTER)).status_code == 200            # master làm nóng cache
    assert (await c.get("/v1/accounts", headers=MASTER)).headers["x-gw-cache"] == "HIT"
    forged = {**KEY, "X-User-Id": "evil", "X-Role": "master", "X-Accounts": "*"}        # thiếu X-Auth-Secret
    assert (await c.get("/v1/accounts", headers=forged)).status_code == 403
    assert (await c.get("/v1/accounts", headers={**forged, "X-Auth-Secret": "wrong"})).status_code == 403
    assert (await c.get("/v1/accounts", headers={**KEY, "X-Role": "client", "X-Accounts": "mt5:1"})).status_code == 403
    assert (await c.get("/v1/news", headers={**forged})).status_code == 403
    assert (await c.get("/v1/accounts", headers={"X-User-Id": "x"})).status_code == 401  # thiếu API key
    assert (await c.get("/v1/news")).status_code == 401 and (await c.get("/v1/news", headers={"X-API-Key": "bad"})).status_code == 401
    # client giả X-Role=master KÈM secret hợp lệ là không thể (secret chỉ nginx biết); nhưng client thật dùng X-Accounts rộng hơn chính mình qua nginx bị đè -> phạm vi theo header đã xác thực
    only_a = await c.get("/v1/accounts", headers=hdr("client", "mt5:1", "ua"))
    assert [x["account_id"] for x in only_a.json()] == ["mt5:1"]


async def test_forbidden_route_for_client_never_served_from_master_cache(env):
    c, cache, r, rds = env
    assert (await c.get("/v1/alerts", headers=MASTER)).status_code == 200
    assert (await c.get("/v1/alerts", headers=CLIENT_A)).status_code == 403
    assert (await c.get("/v1/system", headers=CLIENT_A)).status_code == 403
    for p in ("/v1/me", "/v1/alerts", "/v1/user/prefs", "/v1/journal/accounts", "/v1/reports", "/v1/paper/x", "/v1/system", "/v1/data-sources"):
        assert not any(pol.rx.match(p) for pol in POLICIES), p                         # route nhạy cảm KHÔNG nằm trong bảng cache


async def test_me_not_cached_between_users(env):
    c, cache, r, rds = env
    assert (await c.get("/v1/me", headers=CLIENT_A)).json()["accounts"] == ["mt5:1"]
    assert (await c.get("/v1/me", headers=CLIENT_B)).json()["accounts"] == ["mt5:2"]
    assert await keys(rds) == []


async def test_shared_scope_separates_master_and_client(env):
    c, cache, r, rds = env
    await c.get("/v1/news", headers=MASTER)
    await c.get("/v1/news", headers=CLIENT_A)
    await c.get("/v1/news", headers=CLIENT_B)
    ks = await keys(rds)
    assert sorted(k.split(":")[2] for k in ks) == ["c", "m"] and r.n["news"] == 2        # client dùng chung phạm vi `c`, master tách riêng


async def test_risk_accounts_scoped_by_principal(env, monkeypatch):
    c, cache, r, rds = env
    body = {"accounts": [{"account_id": "mt5:1", "x": 1}, {"account_id": "mt5:2", "x": 2}]}
    monkeypatch.setattr(riskmon_routes, "_fetch", lambda url: (200, json.dumps(body).encode()))
    for _ in range(2):
        assert [a["account_id"] for a in (await c.get("/v1/risk/accounts", headers=CLIENT_A)).json()["accounts"]] == ["mt5:1"]
        assert [a["account_id"] for a in (await c.get("/v1/risk/accounts", headers=CLIENT_B)).json()["accounts"]] == ["mt5:2"]
        assert len((await c.get("/v1/risk/accounts", headers=MASTER)).json()["accounts"]) == 2


async def test_account_scope_headers_are_private_no_store(env):
    c, cache, r, rds = env
    await c.get("/v1/accounts", headers=CLIENT_A)
    h = (await c.get("/v1/accounts", headers=CLIENT_A)).headers
    assert h["cache-control"] == "private, no-store" and h["x-accel-expires"] == "0"
    pol = next(p for p in POLICIES if p.name == "accounts")
    assert _cc(pol, 2) == (b"private, no-store", b"0")


async def test_historic_bars_get_long_ttl():
    from api_gateway.cache import _bars_ttl
    assert _bars_ttl(None, {"tf": "M1"}) == 5 and _bars_ttl(None, {"tf": "D1"}) == 300
    assert _bars_ttl(None, {"tf": "H1", "to": "2020-01-01T00:00:00Z"}) == 3600
    assert _bars_ttl(None, {"tf": "H1", "to": "garbage"}) == 60


async def test_warm_refreshes_hot_keys_ahead_of_expiry(env):
    c, cache, r, rds = env
    cache.start = None                                   # không chạy vòng nền trong test; gọi warm_once thủ công
    cache.app_ref = c._transport.app
    await c.get("/v1/news?limit=3", headers=MASTER)
    await c.get("/v1/news?limit=3", headers=CLIENT_A)
    n0 = r.n["news"]
    (k,) = [k for k in await keys(rds) if ":m:" in k]
    raw = await rds.get(k)
    i = raw.index(b"\n")
    meta = json.loads(raw[:i])
    meta["s"] = int(datetime.now().timestamp() * 1000) + 100          # sắp hết hạn (<35% TTL)
    await rds.set(k, json.dumps(meta, separators=(",", ":")).encode() + raw[i:], px=60000)
    assert await cache.warm_once() >= 1
    assert r.n["news"] > n0
    assert (await c.get("/v1/news?limit=3", headers=MASTER)).headers["x-gw-cache"] == "HIT"
