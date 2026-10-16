from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient
from tscommon import Bus

from risk_monitor.alerts import AlertEmitter, transitions
from risk_monitor.app import create_app, cycle
from risk_monitor.config import Settings, load_config
from risk_monitor.service import RiskService

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self):
        rng = np.random.default_rng(3)
        idx = pd.date_range("2024-01-01", periods=900, freq="D")
        r = rng.normal(0, 0.006, (900, 3))
        self.df = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=["EURUSD", "GBPUSD", "US:SPY"])
        self.df["EURUSD"] = self.df["EURUSD"] / 100 * 1.1

    async def mt_accounts(self):
        pos = [{"symbol": "EURUSD", "side": "buy", "volume": 1.0, "price_current": 1.1, "profit": 5.0, "position_id": "1"},
               {"symbol": "GBPUSD", "side": "sell", "volume": 0.5, "price_current": 1.3, "profit": -2.0, "position_id": "2"}]
        import json
        return [{"account_id": "demo", "platform": "mt4", "ts": NOW - timedelta(seconds=30), "balance": 10_000.0,
                 "equity": 10_050.0, "margin": 3_000.0, "positions": json.dumps(pos)}]

    async def mt_equity(self, account_id, days):
        return [(NOW - timedelta(hours=h), 10_000.0 + 10 * (30 - h) % 120 - 40) for h in range(30, 0, -1)]

    async def paper_accounts(self):
        return [{"account_id": "p1", "name": "P1", "strategy": "x", "base_ccy": "USD", "initial_capital": 100_000.0, "meaningful": True,
                 "status": "active", "cash": 50_000.0, "equity": 100_500.0, "ts": NOW - timedelta(days=1)}]

    async def paper_positions(self, account_id):
        return [{"symbol": "US:SPY", "qty": -20, "mark_price": 500.0, "notional": 10_000.0, "unrealized_pnl": 12.0, "avg_price": 499}]

    async def paper_equity(self, account_id, days):
        return [(NOW - timedelta(days=d), 100_000.0 + 100 * (10 - d)) for d in range(10, 0, -1)]

    async def closes(self, symbols, start, end=None):
        df = self.df[[c for c in symbols if c in self.df.columns]]
        return df

    async def mt_meta(self, account_id):
        return {"currency": "USD", "leverage": 100, "margin_mode": "hedging"}

    async def close(self):
        pass


def make_svc():
    cfg = load_config(None)
    return RiskService(FakeSource(), cfg, clock=lambda: NOW)


async def test_report_mt_and_paper():
    svc = make_svc()
    rep = await svc.report("demo")
    assert rep["read_only"] and rep["account"]["kind"] == "mt"
    m = rep["margin"]
    assert m["margin_level_pct"] == pytest.approx(10_050 / 3_000 * 100)
    assert m["status"] == "ok"
    e = rep["exposure"]
    assert e["mode"] == "hedging" and e["positions"] == 2
    assert e["gross_notional"] == pytest.approx(110_000 + 0.5 * 100_000 * 1.3)  # GBP: base GBP -> USD qua GBPUSD(1.3)
    assert rep["var"]["available"] and rep["var"]["hist"]["95"]["var"] > 0
    assert rep["var"]["hist"]["es"]["es"] >= rep["var"]["hist"]["95"]["var"]
    assert rep["stress"] and rep["stress"] == sorted(rep["stress"], key=lambda r: r["pnl"])
    assert rep["budget"]["status"] in ("ok", "warn", "crit")
    p = await svc.report("p1")
    assert p["account"]["kind"] == "paper" and p["margin"] is None
    assert p["exposure"]["short_value"] == pytest.approx(-10_000.0)
    assert (await svc.report("nope")) is None
    s = await svc.summaries()
    assert {x["account_id"] for x in s} == {"demo", "p1"}


async def test_api_readonly_routes():
    app = create_app(Settings(enabled=False), service=make_svc())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/risk/accounts")
        assert r.status_code == 200 and r.json()["read_only"] and len(r.json()["accounts"]) == 2
        assert (await c.get("/risk/accounts/demo")).status_code == 200
        assert (await c.get("/risk/accounts/zzz")).status_code == 404
        assert (await c.get("/risk/accounts/a b")).status_code in (404, 422)
        assert (await c.get("/risk/config")).json()["scenarios"]
        for m in ("post", "put", "delete", "patch"):
            assert (await getattr(c, m)("/risk/accounts/demo")).status_code == 405


def test_alert_transitions():
    it = lambda st, v: [{"key": "dd_pct", "label": "Drawdown", "unit": "%", "value": v, "limit": 10.0, "status": st}]  # noqa: E731
    a, st = transitions("x", it("warn", 8.5), {})
    assert len(a) == 1 and a[0]["level"] == "warn" and st == {"dd_pct": "warn"}
    a2, st2 = transitions("x", it("warn", 8.6), st)
    assert a2 == []                                                  # không lặp
    a3, st3 = transitions("x", it("crit", 10.5), st2)
    assert a3[0]["level"] == "crit"
    a4, _ = transitions("x", it("ok", 1.0), st3)
    assert a4[0]["level"] == "info"                                  # hồi phục


async def test_cycle_emits_once_to_alerts_out():
    svc = make_svc()
    svc.cfg["budget"]["mt"]["leverage_gross"] = 5.0                  # ép vượt: gross ~ 21.5x
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(r)
    em = AlertEmitter(r, bus, svc.cfg)
    out1 = await cycle(svc, em, svc.cfg)
    out2 = await cycle(svc, em, svc.cfg)
    assert out1["alerts"] >= 1 and out2["alerts"] == 0
    assert await r.xlen("alerts.out") == out1["alerts"]


@pytest.mark.asyncio
async def test_summaries_dung_cache_nong_cua_vong_nen():
    """/risk/accounts không tính lạnh: bản do vòng nền tính (cache_seconds đã hết hạn) vẫn dùng được trong 1,5 chu kỳ."""
    cfg = load_config(None)
    cfg["cache_seconds"] = 0          # TTL ngắn của /risk/accounts/{id}: luôn hết hạn
    cfg["interval_seconds"] = 60
    svc = RiskService(FakeSource(), cfg, clock=lambda: NOW)
    await svc.report("demo", use_cache=False)
    await svc.report("p1", use_cache=False)
    calls = []
    orig = svc._build
    async def spy(a):
        calls.append(a)
        return await orig(a)
    svc._build = spy
    out = await svc.summaries()
    assert len(out) == 2 and calls == []
