"""Mot kich ban trung tinh -> render thanh FakeMT5 va thanh batch EA (de contract test)."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timedelta, timezone

from mtbridge.accounts import AccountConfig
from mtbridge.adapters.fake_mt5 import AccountInfo, FakeMT5, Tick, TradeOrder, TradePosition
from mtbridge.protocol import sign

T0 = datetime(2026, 10, 11, 12, 30, 0, tzinfo=timezone.utc)
OFF = 3 * 3600  # server = UTC+3


def srv(dt: datetime) -> int:
    return int(dt.timestamp()) + OFF


H = lambda h, m=0: datetime(2026, 10, 11, h, m, tzinfo=timezone.utc)  # noqa: E731

ACCOUNT = dict(login=555, server="Demo-Srv", currency="USD", leverage=100, balance=10000.0, equity=9950.5, margin=200.0, free_margin=9750.5, margin_level=4975.25)
POSITIONS = [
    dict(ticket=1002, symbol="XAUUSD.m", type=1, lots=0.05, open_price=2400.5, price=2399.0, sl=2410.0, tp=2380.0, profit=7.5, swap=-0.2, magic=0, comment="manual", open_time=srv(H(8, 15))),
    dict(ticket=1001, symbol="EURUSD.m", type=0, lots=0.10, open_price=1.08, price=1.085, sl=0.0, tp=0.0, profit=50.0, swap=0.0, magic=7, comment="bot", open_time=srv(H(9, 0))),
]
ORDERS = [dict(ticket=2001, symbol="EURUSD.m", type=2, lots=0.2, price=1.07, sl=0.0, tp=0.0, magic=7, comment="", setup_time=srv(H(10, 0)))]
QUOTES = [dict(symbol="EURUSD.m", bid=1.0850, ask=1.0852, time=srv(H(12, 29, ))), dict(symbol="XAUUSD.m", bid=2399.0, ask=2399.4, time=srv(H(12, 29)))]
# H1: 09,10,11 da dong; 12:00 dang chay (EA khong gui, FakeMT5 co tra -> adapter phai bo)
BARS_H1 = [(H(9), 1.0, 1.2, 0.9, 1.1, 100.0), (H(10), 1.1, 1.3, 1.0, 1.2, 110.0), (H(11), 1.2, 1.25, 1.15, 1.18, 90.0)]
FORMING = (H(12), 1.18, 1.19, 1.17, 1.185, 20.0)


def make_cfg(account_id: str, platform: str, transport: str = "agent", **kw) -> AccountConfig:
    return AccountConfig(
        account_id=account_id, platform=platform, transport=transport, token_env=f"TOK_{account_id}",
        symbol_suffix=".m", server_utc_offset_hours=3, watch_symbols=["EURUSD", "XAUUSD"], timeframes=["H1"],
        login=555, server="Demo-Srv", **kw,
    )


def to_fake_mt5() -> FakeMT5:
    a = ACCOUNT
    m = FakeMT5(account=AccountInfo(login=a["login"], trade_mode=0, leverage=100, trade_allowed=False, margin_mode=2, balance=a["balance"], credit=0.0, profit=57.5, equity=a["equity"], margin=a["margin"], margin_free=a["free_margin"], margin_level=a["margin_level"], currency="USD", server="Demo-Srv", name="x"))
    m.positions = [TradePosition(ticket=p["ticket"], time=p["open_time"], type=p["type"], magic=p["magic"], identifier=p["ticket"], volume=p["lots"], price_open=p["open_price"], sl=p["sl"], tp=p["tp"], price_current=p["price"], swap=p["swap"], profit=p["profit"], symbol=p["symbol"], comment=p["comment"]) for p in POSITIONS]
    m.orders = [TradeOrder(ticket=o["ticket"], time_setup=o["setup_time"], type=o["type"], state=1, magic=o["magic"], volume_initial=o["lots"], volume_current=o["lots"], price_open=o["price"], sl=o["sl"], tp=o["tp"], price_current=1.085, symbol=o["symbol"], comment=o["comment"]) for o in ORDERS]
    for q in QUOTES:
        m.ticks[q["symbol"]] = Tick(time=q["time"], bid=q["bid"], ask=q["ask"], last=0.0, volume=0, time_msc=q["time"] * 1000)
    rows = [dict(time=srv(t), open=o, high=h, low=l, close=c, tick_volume=v, spread=1, real_volume=0) for (t, o, h, l, c, v) in BARS_H1 + [FORMING]]
    m.rates[("EURUSD.m", m.TIMEFRAME_H1)] = rows
    m.rates[("XAUUSD.m", m.TIMEFRAME_H1)] = rows
    m.initialized = True
    return m


def to_ea_batch(account_id: str, platform: str, *, ts: datetime = T0, nonce: str | None = None, with_snapshot=True, margin_mode="hedging") -> dict:
    b = {"v": 1, "account_id": account_id, "platform": platform, "ts": int(ts.timestamp()), "server_time": int(ts.timestamp()) + OFF, "nonce": nonce or uuid.uuid4().hex, "seq": 1, "quotes": copy.deepcopy(QUOTES), "bars": []}
    for s in ("EURUSD.m", "XAUUSD.m"):
        for (t, o, h, l, c, v) in BARS_H1:
            b["bars"].append(dict(symbol=s, tf="H1", time=srv(t), o=o, h=h, l=l, c=c, v=v))
    if with_snapshot:
        b["account"] = dict(ACCOUNT, margin_mode=margin_mode, trade_allowed=False)
        b["positions"] = copy.deepcopy(POSITIONS)
        b["orders"] = copy.deepcopy(ORDERS)
    return b


def post(client, token: str, batch: dict, *, account: str | None = None, secret: str | None = None, headers: dict | None = None):
    raw = json.dumps(batch).encode()
    h = {"Authorization": f"Bearer {token}", "X-MT-Account": account or batch["account_id"], "Content-Type": "application/json"}
    if secret:
        h["X-MT-Sig"] = sign(secret, batch["ts"], batch["nonce"], raw)
    h.update(headers or {})
    return client.post("/ingest/v1", content=raw, headers=h)
