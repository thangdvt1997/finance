"""Lich su deal da dong (EA -> bridge -> account.deals): schema, chuan hoa, idempotent, chong replay, extra=forbid."""
import copy

from scenario import H, post, srv, to_ea_batch

TOK = "secret-token-a4-xxxxxxxx"

DEALS = [
    dict(ticket=5001, position_id=5001, symbol="EURUSD.m", type=0, lots=0.10, open_price=1.0800, close_price=1.0850, sl=1.0770, tp=1.0900,
         open_time=srv(H(8, 0)), close_time=srv(H(9, 30)), profit=50.0, swap=-0.5, commission=-0.7, magic=7, comment="bot", reason="tp"),
    dict(ticket=5002, position_id=5002, symbol="XAUUSD.m", type=1, lots=0.05, open_price=2400.0, close_price=2405.0, sl=0.0, tp=0.0,
         open_time=srv(H(8, 5)), close_time=srv(H(10, 0)), profit=-25.0, swap=0.0, commission=-0.35, magic=0, comment="manual", reason="client"),
    dict(ticket=5003, position_id=0, symbol="", type=2, lots=0.0, open_price=0.0, close_price=0.0,
         open_time=srv(H(7, 0)), close_time=srv(H(7, 0)), profit=1000.0, comment="deposit"),
]


def batch(deals, **kw):
    b = to_ea_batch("a4", "mt4", **kw)
    b["deals"] = copy.deepcopy(deals)
    return b


def test_deals_published_normalized(env):
    _, client, pub, _ = env
    r = post(client, TOK, batch(DEALS))
    assert r.status_code == 200 and r.json()["deals"] == 3
    evs = pub.on("account.deals")
    assert len(evs) == 1 and evs[0].type == "account_deals"
    p = evs[0].payload
    assert p["account_id"] == "a4" and p["platform"] == "mt4" and len(p["deals"]) == 3
    d0 = p["deals"][0]
    assert d0["ticket"] == "5001" and d0["symbol"] == "EURUSD" and d0["broker_symbol"] == "EURUSD.m" and d0["side"] == "buy"
    assert d0["time_close"].startswith("2026-10-11T09:30") and d0["time_open"].startswith("2026-10-11T08:00")  # gio server UTC+3 -> UTC
    assert d0["source"] == "mt4:a4" and d0["reason"] == "tp" and d0["commission"] == -0.7
    assert p["deals"][1]["side"] == "sell" and p["deals"][2]["side"] == "balance" and p["deals"][2]["symbol"] == ""
    assert p["deals"][2]["position_id"] == "5003"  # position_id=0 -> ticket


def test_no_deals_key_publishes_nothing(env):
    _, client, pub, _ = env
    r = post(client, TOK, to_ea_batch("a4", "mt4"))
    assert r.status_code == 200 and r.json()["deals"] == 0 and pub.on("account.deals") == []
    b = to_ea_batch("a4", "mt4"); b["deals"] = []
    assert post(client, TOK, b).status_code == 200 and pub.on("account.deals") == []


def test_replayed_batch_rejected_and_resend_is_idempotent_key(env):
    _, client, pub, _ = env
    b = batch(DEALS)
    assert post(client, TOK, b).status_code == 200
    assert post(client, TOK, b).status_code == 409  # cung nonce = replay -> khong publish lai
    assert len(pub.on("account.deals")) == 1
    # EA gui lai cung deal voi nonce moi (mat ack): bridge van cho qua, ticket giong nhau -> DB upsert theo (account_id, ticket)
    assert post(client, TOK, batch(DEALS)).status_code == 200
    t1 = [d["ticket"] for d in pub.on("account.deals")[0].payload["deals"]]
    t2 = [d["ticket"] for d in pub.on("account.deals")[1].payload["deals"]]
    assert t1 == t2


def test_deal_schema_rejections(env):
    _, client, pub, _ = env
    bad = [
        {**DEALS[0], "extra_field": 1},                       # extra=forbid
        {**DEALS[0], "type": 3},                              # khong phai buy/sell/balance
        {**DEALS[0], "symbol": "EUR USD;DROP"},               # ky tu la
        {**DEALS[0], "profit": float("nan")},                 # NaN
        {**DEALS[0], "reason": "hack"},
        {**DEALS[0], "comment": "x" * 65},
        {**DEALS[0], "close_time": 0},
        {**DEALS[0], "ticket": -1},
    ]
    for d in bad:
        r = post(client, TOK, batch([d]))
        assert r.status_code == 422, d
    assert pub.on("account.deals") == []
    too_many = [dict(DEALS[0], ticket=i) for i in range(501)]
    assert post(client, TOK, batch(too_many)).status_code == 422


def test_deals_survive_cross_account_token(env):
    _, client, pub, _ = env
    b = batch(DEALS)
    assert post(client, "secret-token-a5-xxxxxxxx", b, account="a4").status_code == 401  # token tai khoan khac
    assert pub.on("account.deals") == []
