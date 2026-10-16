import asyncio
from datetime import timedelta

from scenario import ACCOUNT, POSITIONS, T0, make_cfg, post, to_ea_batch, to_fake_mt5

from mtbridge.accounts import AccountConfig, BridgeConfig
from mtbridge.adapters.mt5 import MT5Gateway
from mtbridge.service import BridgeService, Settings

TOK = "secret-token-a4-xxxxxxxx"


def alerts(pub):
    return [e.payload for e in pub.on("alerts.out")]


def send(client, clock, **mods):
    b = to_ea_batch("a4", "mt4", ts=clock.t)
    acc = dict(b["account"]); acc.update(mods.pop("account", {})); b["account"] = acc
    b.update(mods)
    assert post(client, TOK, b).status_code == 200


def test_drawdown_margin_and_new_position(env):
    svc, client, pub, clock = env
    send(client, clock)  # baseline: khong alert
    assert alerts(pub) == []
    clock.t += timedelta(seconds=10)
    send(client, clock, account={"equity": 8000.0, "margin_level": 150.0})  # dd ~19.6% > 10, margin<200
    a = alerts(pub)
    assert {x["dedupe_key"] for x in a} == {"dd:a4", "margin:a4:warn"}
    assert next(x for x in a if x["dedupe_key"] == "dd:a4")["level"] == "crit"
    for x in a:
        assert set(x) == {"level", "title", "body", "tags", "dedupe_key"}
    n = len(a)
    clock.t += timedelta(seconds=10)
    send(client, clock, account={"equity": 7900.0, "margin_level": 150.0})
    assert len(alerts(pub)) == n  # khong spam khi trang thai khong doi
    clock.t += timedelta(seconds=10)
    send(client, clock, account={"equity": 7900.0, "margin_level": 90.0})
    assert alerts(pub)[-1]["dedupe_key"] == "margin:a4:crit"
    # vi the moi ngoai du kien
    clock.t += timedelta(seconds=10)
    extra = dict(POSITIONS[1], ticket=9999, magic=12345, comment="intruder")
    send(client, clock, positions=POSITIONS + [extra])
    assert alerts(pub)[-1]["dedupe_key"] == "newpos:a4:9999"
    send_n = len(alerts(pub))
    clock.t += timedelta(seconds=10)
    send(client, clock, positions=POSITIONS + [extra])
    assert len(alerts(pub)) == send_n


def test_expected_magic_not_alerted():
    cfg = BridgeConfig(accounts=[make_cfg("a4", "mt4", rules={"expected_magics": [7]})])
    from conftest import Clock, FakePub
    pub, clock = FakePub(), Clock(T0)
    svc = BridgeService(cfg, pub, settings=Settings(), clock=clock)
    from mtbridge.protocol import Batch
    gw = svc.gateways["a4"]
    b = to_ea_batch("a4", "mt4", ts=T0)
    r = gw.ingest(Batch.model_validate(b))
    svc.engine.on_snapshot(r.account, r.positions, cfg.accounts[0].rules)
    b2 = to_ea_batch("a4", "mt4", ts=T0)
    b2["positions"] = POSITIONS + [dict(POSITIONS[0], ticket=777, magic=7)]
    r2 = gw.ingest(Batch.model_validate(b2))
    assert svc.engine.on_snapshot(r2.account, r2.positions, cfg.accounts[0].rules) == []


def test_heartbeat_lost_and_recovered(env):
    svc, client, pub, clock = env
    asyncio.run(svc.monitor_once())
    assert alerts(pub) == []  # chua tung ket noi: im lang
    send(client, clock)
    clock.t += timedelta(seconds=60)
    asyncio.run(svc.monitor_once())
    assert alerts(pub) == []
    clock.t += timedelta(seconds=60)  # 120s > 90s
    asyncio.run(svc.monitor_once())
    asyncio.run(svc.monitor_once())  # lap lai khong spam
    a = alerts(pub)
    assert len(a) == 1 and a[0]["dedupe_key"] == "hb:a4" and a[0]["level"] == "crit"
    # chi gui heartbeat (khong snapshot) cung phai bao 'ket noi lai'
    hb = to_ea_batch("a4", "mt4", ts=clock.t, with_snapshot=False)
    hb["quotes"], hb["bars"] = [], []
    assert post(client, TOK, hb).status_code == 200
    assert alerts(pub)[-1]["dedupe_key"] == "hb:a4:recovered"


def test_mt5_direct_poll_publishes_and_monitors():
    from conftest import Clock, FakePub
    cfg = make_cfg("m5d", "mt5", transport="mt5_direct")
    fake = to_fake_mt5()
    clock, pub = Clock(T0), FakePub()
    gw = MT5Gateway(cfg, fake, password="inv", clock=clock)
    gw.connect()
    svc = BridgeService(BridgeConfig(accounts=[cfg]), pub, settings=Settings(), clock=clock, gateways={"m5d": gw})
    asyncio.run(svc.poll_mt5_once(gw))
    assert len(pub.on("account.snapshots")) == 1 and len(pub.on("md.quotes")) == 2
    assert len(pub.on("md.bars")) == 2 * 3  # 3 nen dong moi symbol, khong co nen dang chay (3 nen cuoi, bo nen forming)
    asyncio.run(svc.poll_mt5_once(gw))
    assert len(pub.on("md.bars")) == 6  # idempotent
    fake.init_ok = False; fake.initialized = False  # terminal chet
    asyncio.run(svc.poll_mt5_once(gw))  # loi duoc nuot, khong publish them
    clock.t += timedelta(seconds=200)
    asyncio.run(svc.monitor_once())
    assert alerts(pub)[-1]["dedupe_key"] == "hb:m5d"


def test_mt5_refuses_trading_password():
    import pytest
    fake = to_fake_mt5()
    fake.account = fake.account._replace(trade_allowed=True)
    gw = MT5Gateway(make_cfg("m5d", "mt5", transport="mt5_direct"), fake, password="x", clock=lambda: T0)
    with pytest.raises(PermissionError):
        gw.connect()
    assert fake.initialized is False
