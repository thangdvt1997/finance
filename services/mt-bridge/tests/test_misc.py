import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

import fakeredis.aioredis
from scenario import T0, make_cfg, to_ea_batch

from mtbridge.accounts import AccountConfig, BridgeConfig, load_config
from mtbridge.gateway import BrokerGateway
from mtbridge.models import Position, net_exposure
from mtbridge.service import BridgeService, Settings
from tscommon import Bus, STREAMS

ROOT = Path(__file__).resolve().parents[3]


def test_symbol_mapping_and_aliases():
    c = AccountConfig(account_id="x", platform="mt4", symbol_prefix="", symbol_suffix=".pro", symbol_aliases={"GOLD": "XAUUSD", "DE30": "GER40"})
    assert c.to_canonical("EURUSD.pro") == "EURUSD"
    assert c.to_canonical("GOLD") == "XAUUSD" and c.to_broker("XAUUSD") == "GOLD"
    assert c.to_broker("EURUSD") == "EURUSD.pro"


def test_server_time_dst_aware():
    c = AccountConfig(account_id="x", platform="mt4", server_tz="Europe/Athens")
    # server epoch dong goi nhu UTC: 12:00 gio server
    summer = datetime(2026, 7, 1, 12, tzinfo=timezone.utc).timestamp()
    winter = datetime(2026, 1, 1, 12, tzinfo=timezone.utc).timestamp()
    assert c.server_epoch_to_utc(summer).hour == 9  # UTC+3
    assert c.server_epoch_to_utc(winter).hour == 10  # UTC+2
    assert c.utc_to_server_epoch(c.server_epoch_to_utc(summer)) == summer


def test_offset_derived_from_ea_when_not_configured():
    from mtbridge.adapters.agent import AgentGateway
    from mtbridge.protocol import Batch
    cfg = AccountConfig(account_id="a4", platform="mt4", symbol_suffix=".m")
    gw = AgentGateway(cfg)
    gw.ingest(Batch.model_validate(to_ea_batch("a4", "mt4")))  # server_time = ts + 3h
    assert gw.get_positions()[0].time_open.hour == 9  # offset +3h suy ra tu server_time-ts


def test_net_exposure_hedging_and_netting():
    mk = lambda i, side, v: Position(position_id=i, symbol="EURUSD", broker_symbol="EURUSD", side=side, volume=v, price_open=1, price_current=1, time_open=T0)  # noqa: E731
    assert net_exposure([mk("1", "buy", 0.3), mk("2", "sell", 0.1)]) == {"EURUSD": 0.2}
    assert net_exposure([mk("9", "sell", 0.5)]) == {"EURUSD": -0.5}


def test_gateway_is_read_only():
    forbidden = {"place_order", "modify", "close", "order_send", "send_order", "close_position", "modify_order"}
    assert not forbidden & set(dir(BrokerGateway))
    abstract = set(BrokerGateway.__abstractmethods__)
    assert abstract == {"get_account", "get_positions", "get_orders", "get_rates", "get_quotes", "health"}


def test_no_trading_code_anywhere():
    """Phase doc-chi: khong co code dat/sua/dong lenh o bat ky dau (Python lan MQL). OrderCloseTime()/OrderClosePrice() la ham DOC lich su (MQL4), duoc phep."""
    pat = re.compile(r"order_send|order_check|OrderSend|OrderClose(?!Time|Price)|OrderModify|OrderDelete|CTrade|PositionClose|trade\.Buy|trade\.Sell|TRADE_ACTION", re.I)
    offenders = []
    for base in (ROOT / "services" / "mt-bridge" / "src", ROOT / "mt-agent"):
        for p in base.rglob("*"):
            if p.suffix in {".py", ".mq4", ".mq5", ".mqh"} and pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(p))
    assert offenders == []


def test_example_config_loads():
    cfg = load_config(str(ROOT / "services" / "mt-bridge" / "config" / "accounts.example.yaml"))
    assert len(cfg.accounts) >= 2
    assert not any(a.token_env == "" for a in cfg.accounts if a.transport == "agent")


def test_publish_through_real_bus_with_fakeredis():
    async def run():
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        bus = Bus(r)
        cfg = BridgeConfig(accounts=[make_cfg("a4", "mt4")])
        svc = BridgeService(cfg, bus, settings=Settings(), clock=lambda: T0)
        await svc.publish_alerts([{"level": "warn", "title": "t", "body": "", "tags": [], "dedupe_key": "k"}])
        from mtbridge.protocol import Batch
        res = svc.gateways["a4"].ingest(Batch.model_validate(to_ea_batch("a4", "mt4")))
        await svc.publish_quotes(res.quotes)
        await svc.publish_bars(res.bars)
        await svc.publish_account(res.account, res.positions, res.orders)
        for key in ("alerts", "quotes", "bars", "account"):
            assert await r.xlen(STREAMS[key]) >= 1, key
    asyncio.run(run())
