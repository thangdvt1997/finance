from datetime import timedelta

from scenario import T0, post, to_ea_batch

TOK = "secret-token-a4-xxxxxxxx"


def test_ok_and_publishes_contract_streams(env):
    svc, client, pub, _ = env
    r = post(client, TOK, to_ea_batch("a4", "mt4"))
    assert r.status_code == 200 and r.json()["snapshot"] is True
    snap = pub.on("account.snapshots")[0]
    assert snap.type == "account_snapshot" and snap.source == "mt-bridge"
    p = snap.payload
    for k in ("account_id", "platform", "balance", "equity", "margin", "positions", "ts"):
        assert k in p
    assert p["platform"] == "mt4" and len(p["positions"]) == 2
    q = pub.on("md.quotes")[0].payload
    assert set(q) == {"symbol", "bid", "ask", "ts", "source"} and q["symbol"] in ("EURUSD", "XAUUSD")
    b = pub.on("md.bars")[0].payload
    assert set(b) == {"symbol", "tf", "ts_open", "o", "h", "l", "c", "v", "source"}
    assert len(pub.on("md.bars")) == 6
    # gui lai nen y het (nonce moi) -> khong publish lai bar; quote khong doi cung bi bo
    n_bars, n_q = len(pub.on("md.bars")), len(pub.on("md.quotes"))
    post(client, TOK, to_ea_batch("a4", "mt4"))
    assert len(pub.on("md.bars")) == n_bars and len(pub.on("md.quotes")) == n_q


def test_bad_or_missing_token(env):
    _, client, pub, _ = env
    assert post(client, "wrong-token-value-1234", to_ea_batch("a4", "mt4")).status_code == 401
    assert post(client, "", to_ea_batch("a4", "mt4")).status_code == 401
    assert post(client, TOK, to_ea_batch("zzz", "mt4"), account="zzz").status_code == 401  # tai khoan la
    assert client.post("/ingest/v1", content=b"{}").status_code == 401
    assert pub.events == []


def test_token_of_other_account_rejected(env):
    _, client, _, _ = env
    assert post(client, "secret-token-a5-xxxxxxxx", to_ea_batch("a4", "mt4")).status_code == 401


def test_replay_nonce(env):
    _, client, _, _ = env
    b = to_ea_batch("a4", "mt4", nonce="nonce-0001-abcdef")
    assert post(client, TOK, b).status_code == 200
    r = post(client, TOK, b)
    assert r.status_code == 409 and r.json()["error"] == "replay"


def test_timestamp_skew(env):
    _, client, _, clock = env
    old = to_ea_batch("a4", "mt4", ts=T0 - timedelta(seconds=600))
    assert post(client, TOK, old).status_code == 401
    fut = to_ea_batch("a4", "mt4", ts=T0 + timedelta(seconds=600))
    assert post(client, TOK, fut).status_code == 401
    # sau khi tien dong ho bridge, batch cu van sai; batch moi hop le
    clock.t = T0 + timedelta(seconds=30)
    assert post(client, TOK, to_ea_batch("a4", "mt4", ts=clock.t)).status_code == 200


def test_schema_rejections(env):
    _, client, _, _ = env
    b = to_ea_batch("a4", "mt4")
    b["positions"][0]["type"] = 9
    assert post(client, TOK, b).status_code == 422
    b = to_ea_batch("a4", "mt4")
    b["unknown_field"] = 1
    assert post(client, TOK, b).status_code == 422
    b = to_ea_batch("a4", "mt4")
    b["quotes"][0]["bid"] = float("nan")
    assert post(client, TOK, b).status_code == 422
    b = to_ea_batch("a4", "mt4")
    b["bars"][0]["tf"] = "W1"
    assert post(client, TOK, b).status_code == 422
    b = to_ea_batch("a4", "mt4")
    b["quotes"][0]["symbol"] = "EUR USD;drop"
    assert post(client, TOK, b).status_code == 422


def test_account_platform_mismatch(env):
    _, client, _, _ = env
    assert post(client, TOK, to_ea_batch("a5", "mt5"), account="a4").status_code == 400
    assert post(client, TOK, to_ea_batch("a4", "mt5")).status_code == 400


def test_body_too_large(env):
    _, client, _, _ = env
    r = client.post("/ingest/v1", content=b"x" * 1_100_000, headers={"Authorization": f"Bearer {TOK}", "X-MT-Account": "a4"})
    assert r.status_code == 413 or r.status_code == 401


def test_hmac_required_when_configured(env):
    _, client, _, _ = env
    tok, sec = "secret-token-h1-xxxxxxxx", "hmac-secret-h1"
    assert post(client, tok, to_ea_batch("h1", "mt4")).status_code == 401  # thieu chu ky
    assert post(client, tok, to_ea_batch("h1", "mt4"), headers={"X-MT-Sig": "00"}).status_code == 401
    assert post(client, tok, to_ea_batch("h1", "mt4"), secret=sec).status_code == 200


def test_accounts_endpoint_and_health(env):
    svc, client, _, _ = env
    assert client.get("/healthz").status_code == 200
    assert "mtbridge_ingest_total" in client.get("/metrics").text
    assert client.get("/accounts").status_code == 401
    post(client, TOK, to_ea_batch("a4", "mt4"))
    rows = {r["account_id"]: r for r in client.get("/accounts", headers={"Authorization": "Bearer adm"}).json()}
    assert rows["a4"]["connected"] is True and rows["a4"]["positions"] == 2 and rows["a4"]["equity"] == 9950.5
    assert rows["a5"]["connected"] is False


def test_trade_allowed_alert_only_on_transition(env):
    """Phat hien khi chay MT4 that: canh bao trade_allowed bi phat lai moi batch (spam)."""
    _, client, pub, _ = env

    def batch(allowed):
        b = to_ea_batch("a4", "mt4")
        b["account"]["trade_allowed"] = allowed
        return b

    def n():
        return len([e for e in pub.on("alerts.out") if "trade_allowed" in str(e.payload.get("dedupe_key", ""))])

    for _ in range(3):
        assert post(client, TOK, batch(True)).status_code == 200
    assert n() == 1                       # 3 batch lien tiep -> chi 1 canh bao
    assert post(client, TOK, batch(False)).status_code == 200
    assert post(client, TOK, batch(True)).status_code == 200
    assert n() == 2                       # false -> true: canh bao lai


def test_accounts_fail_closed_without_admin_token():
    from fastapi.testclient import TestClient
    from mtbridge.accounts import BridgeConfig
    from mtbridge.service import BridgeService, Settings, create_app

    class P:
        async def publish(self, s, e): ...

    svc = BridgeService(BridgeConfig(accounts=[]), P(), settings=Settings(admin_token="", admin_insecure_dev=False))
    c = TestClient(create_app(svc))
    assert c.get("/accounts").status_code == 503
    assert c.get("/accounts", headers={"Authorization": "Bearer x"}).status_code == 503
    svc2 = BridgeService(BridgeConfig(accounts=[]), P(), settings=Settings(admin_token="", admin_insecure_dev=True))
    assert TestClient(create_app(svc2)).get("/accounts").status_code == 200
