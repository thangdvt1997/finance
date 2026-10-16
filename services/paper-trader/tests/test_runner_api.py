"""Runner end-to-end (bộ nhớ), idempotency qua restart, API, hiệu suất (empyrical), bus/alert."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from paper_trader import perf
from paper_trader.app import create_app
from paper_trader.config import Settings, load_yaml
from paper_trader.repo import MemoryBarSource, MemoryPaperStore
from paper_trader.runner import Runner, risk_windows_fn

from .conftest import DAY, START, rows_from_closes


class FakeBus:
    def __init__(self):
        self.sent: list[tuple[str, object]] = []

    async def publish(self, stream, event):
        self.sent.append((stream, event))


def cfg(**acct):
    c = load_yaml(None)
    base = {"id": "bh", "name": "BH", "strategy": "buy_and_hold", "base_ccy": "USD", "initial_capital": 10_000, "universe": ["EURUSD", "USDJPY"],
            "rebalance": "first_only", "risk": {"max_leverage": 1.0, "max_weight": 0.5, "min_trade_weight": 0.0, "max_drawdown": 0.9,
                                                "max_daily_loss": 0.9, "max_weekly_loss": 0.9}}
    base.update(acct)
    c["accounts"] = [base]
    c["instruments"] = {"EURUSD": {"lot": 1, "spread_bps": 2.0, "slippage_bps": 1.0, "slip_range_frac": 0, "commission_bps": 0.5, "swap_long_bps": 0},
                        "USDJPY": {"lot": 1, "spread_bps": 2.0, "slippage_bps": 1.0, "slip_range_frac": 0, "commission_bps": 0.5, "swap_long_bps": 0}}
    return c


def data(n=12, eur_step=0.002, jpy_step=0.2):
    return {("EURUSD", "D1"): rows_from_closes([1.10 + eur_step * i for i in range(n)]),
            ("USDJPY", "D1"): rows_from_closes([150 + jpy_step * i for i in range(n)])}


async def make_runner(store=None, bus=None, now_bars=6, **acct):
    store = store or MemoryPaperStore()
    d = data()
    src = MemoryBarSource(d)
    r = Runner(cfg(**acct), src, store, bus, None)
    await r.init()
    return r, store, src


async def test_forward_start_then_fills_then_idempotent():
    bus = FakeBus()
    r, store, _ = await make_runner(bus=bus)
    now1 = START + DAY * 6                                          # bar 0..5 đã đóng
    s = await r.run_cycle(now1)
    assert s["accounts"]["bh"]["steps"] == 1                        # forward: chỉ bắt đầu từ bar đóng gần nhất, KHÔNG replay quá khứ
    acc = await store.get_account("bh")
    assert acc["state"]["inception_ts"] == (START + DAY * 6).isoformat()
    assert len(store.orders_) == 2 and not store.fills_
    s = await r.run_cycle(now1)                                     # chạy lại cùng thời điểm: không bước mới
    assert s["accounts"]["bh"]["steps"] == 0 and len(store.orders_) == 2
    s = await r.run_cycle(START + DAY * 8)                          # thêm 2 bar
    assert s["accounts"]["bh"]["steps"] == 2 and len(store.fills_) == 2
    f = store.fills_["bh:%s:EURUSD" % (START + DAY * 6).strftime("%Y%m%dT%H%M%S")]
    assert f["ts"] == START + DAY * 6                               # khớp ở bar 6 (bar sau bar tín hiệu 5)
    assert f["price"] == pytest.approx(f["ref_price"] * (1 + 2e-4))   # nửa spread 1bp + trượt 1bp
    assert [e["ts"] for e in await store.equity("bh", 10)] == [START + DAY * k for k in (6, 7, 8)]
    # restart: runner mới nạp trạng thái từ store -> không trùng lặp
    r2 = Runner(cfg(), MemoryBarSource(data()), store, bus, None)
    await r2.init()
    s = await r2.run_cycle(START + DAY * 8)
    assert s["accounts"]["bh"]["steps"] == 0 and len(store.orders_) == 2 and len(store.fills_) == 2
    s = await r2.run_cycle(START + DAY * 10)
    assert s["accounts"]["bh"]["steps"] == 2 and len(store.fills_) == 2          # buy&hold không giao dịch thêm
    # bus: paper.events + alert có nhãn MÔ PHỎNG
    streams = [st for st, _ in bus.sent]
    assert "paper.events" in streams and "alerts.out" in streams
    alerts = [e.payload for st, e in bus.sent if st == "alerts.out"]
    assert alerts and all("MÔ PHỎNG" in a["title"] + a["body"] for a in alerts)
    evs = [e.payload for st, e in bus.sent if st == "paper.events"]
    assert all(p["simulation"] is True and p["account_id"] == "bh" for p in evs)


async def test_save_step_twice_is_idempotent():
    from paper_trader.engine import Engine  # noqa: F401
    r, store, _ = await make_runner()
    await r.run_cycle(START + DAY * 6)
    rt = r.accounts["bh"]
    n_ev, n_ord = len(store.events_), len(store.orders_)
    # tái ghi cùng kết quả bước (giả lập crash giữa chừng rồi ghi lại)
    from paper_trader.market import MarketView, frame_from_rows
    ev = list(store.events_.values())[0]
    new = await store.save_manual("bh", rt.engine.state, [{"key": ev["event_key"], "type": ev["type"], "severity": "info", "message": "x", "data": {}, "ts": ev["ts"]}])
    assert new == [] and len(store.events_) == n_ev and len(store.orders_) == n_ord


async def test_usd_account_with_jpy_pair_converts_pnl():
    r, store, _ = await make_runner(universe=["USDJPY"], risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0, "max_drawdown": 0.9,
                                                                 "max_daily_loss": 0.9, "max_weekly_loss": 0.9})
    await r.run_cycle(START + DAY * 6)
    await r.run_cycle(START + DAY * 12)
    eq = await store.equity("bh", 100)
    fill = list(store.fills_.values())[0]
    pos = r.accounts["bh"].engine.state.positions["USDJPY"]
    # USDJPY: qty tính bằng USD; PnL USD ≈ qty * (giá_cuối - giá_khớp)/giá_cuối
    last = 150 + 0.2 * 11
    expected = pos.qty * (last - fill["price"]) / last - fill["commission"]
    assert eq[-1]["equity"] - 10_000 == pytest.approx(expected, rel=1e-6)
    assert pos.qty == pytest.approx(10_000, abs=1)                                                 # ≈ 10.000 USD danh nghĩa


async def test_kill_switch_alert_and_admin_commands():
    bus = FakeBus()
    closes = [1.1] * 4 + [0.9] * 8
    d = {("EURUSD", "D1"): rows_from_closes(closes, opens=[1.1] * 4 + [1.1] + [0.9] * 7)}
    c = cfg(universe=["EURUSD"], risk={"max_leverage": 1.0, "max_weight": 1.0, "min_trade_weight": 0.0, "max_drawdown": 0.10,
                                        "max_daily_loss": 0.9, "max_weekly_loss": 0.9})
    store = MemoryPaperStore()
    r = Runner(c, MemoryBarSource(d), store, bus, None)
    await r.init()
    await r.run_cycle(START + DAY * 2)                  # bắt đầu tại bar 1; mua ở bar 2
    await r.run_cycle(START + DAY * 12)
    assert r.accounts["bh"].engine.state.status == "locked"
    crit = [e.payload for st, e in bus.sent if st == "alerts.out" and e.payload["level"] == "crit"]
    assert crit and "KILL-SWITCH" in crit[0]["title"] and "MÔ PHỎNG" in crit[0]["body"]
    app = create_app(Settings(admin_token="s3cret"), runner=r, store=store)
    with TestClient(app) as cl:
        assert cl.post("/paper/accounts/bh/kill-switch/reset").status_code == 401
        assert cl.post("/paper/accounts/bh/kill-switch/reset", headers={"X-Admin-Token": "bad"}).status_code == 401
        ks = cl.get("/paper/accounts/bh/kill-switch").json()
        assert ks["status"] == "locked" and ks["hard_lock"] and ks["limits"]["drawdown"] == pytest.approx(-0.10) and ks["simulation"] is True
        ok = cl.post("/paper/accounts/bh/kill-switch/reset", headers={"X-Admin-Token": "s3cret"})
        assert ok.status_code == 200 and ok.json()["status"] == "active"
        assert cl.post("/paper/accounts/nope/kill-switch/reset", headers={"X-Admin-Token": "s3cret"}).status_code == 404


async def test_api_endpoints_shape_and_labels():
    r, store, _ = await make_runner(benchmark=None)
    await r.run_cycle(START + DAY * 6)
    await r.run_cycle(START + DAY * 11)
    app = create_app(Settings(), runner=r, store=store)
    with TestClient(app) as cl:
        for path in ("/paper/accounts", "/paper/overview", "/paper/accounts/bh", "/paper/accounts/bh/equity", "/paper/accounts/bh/positions",
                     "/paper/accounts/bh/orders", "/paper/accounts/bh/fills", "/paper/accounts/bh/events", "/paper/accounts/bh/kill-switch",
                     "/paper/accounts/bh/stats", "/paper/strategies", "/paper/events", "/status"):
            j = cl.get(path)
            assert j.status_code == 200, path
            body = j.json()
            assert body["simulation"] is True and "MÔ PHỎNG" in body["label"] and "KHÔNG phải tiền thật" in body["disclaimer"], path
        assert cl.get("/paper/accounts/zzz").status_code == 404
        assert cl.get("/paper/accounts/%00").status_code == 404          # NUL trong id: 404, không 500 (QA API 2026-10-15)
        assert cl.get("/paper/accounts/" + "A" * 300).status_code == 404
        eq = cl.get("/paper/accounts/bh/equity").json()
        assert eq["series"][0]["index"] == pytest.approx(100.0) and len(eq["series"]) == 6
        pos = cl.get("/paper/accounts/bh/positions").json()["items"]
        assert {p["symbol"] for p in pos} == {"EURUSD", "USDJPY"}
        st = cl.get("/paper/accounts/bh/stats").json()
        assert st["reliable"] is False and "Mẫu quá ngắn" in st["note"] and st["trading"]["fills"] == 2
        assert {s["name"] for s in cl.get("/paper/strategies").json()["items"]} >= {"buy_and_hold", "slow_trend_multiasset"}
        assert cl.get("/metrics").status_code == 200 and cl.get("/healthz").json()["status"] == "ok"
        assert cl.post("/paper/accounts/bh/kill-switch/halt").status_code == 503     # chưa đặt PAPER_ADMIN_TOKEN -> tắt lệnh quản trị


async def test_replay_account_uses_start_at():
    r, store, _ = await make_runner(start_at=(START + DAY * 2).isoformat())
    s = await r.run_cycle(START + DAY * 8)
    assert s["accounts"]["bh"]["steps"] == 6                                         # bar 2..7 đã đóng
    ev = store.events_[("bh", "account_started")]
    assert "REPLAY" in ev["message"] and ev["data"]["replay"] is True


async def test_risk_windows_static_blocks_entry():
    c = cfg()
    c["news_windows"] = [{"start": (START + DAY * 6 - timedelta(minutes=10)).isoformat(), "end": (START + DAY * 6 + timedelta(minutes=5)).isoformat(),
                          "currencies": ["USD"], "title": "NFP"}]
    store = MemoryPaperStore()
    r = Runner(c, MemoryBarSource(data()), store, None, await risk_windows_fn(c))
    await r.init()
    await r.run_cycle(START + DAY * 6)
    assert all(o["status"] == "rejected" and o["reason"] == "risk_window:NFP" for o in store.orders_.values()) and store.orders_
    assert not any(e["type"] == "fill" for e in [v for v in store.events_.values()])


# ------------------------------------------------------------------ hiệu suất
def _rows(vals, start=START):
    return [{"ts": start + DAY * i, "equity": v} for i, v in enumerate(vals)]


def test_perf_hand_values():
    s = perf.stats(_rows([100, 120, 90, 110]), initial=100)
    assert s["total_return"] == pytest.approx(0.10)
    assert s["max_drawdown"] == pytest.approx(-0.25)                       # 90/120 - 1
    assert s["current_drawdown"] == pytest.approx(110 / 120 - 1)
    assert s["reliable"] is False and s["cagr"] is None                    # < 30 ngày: không công bố CAGR
    assert s["days"] == 4


def test_perf_long_series_reliable_and_benchmark():
    import numpy as np
    n = 120
    a = [10_000 * (1.001 ** i) for i in range(n)]
    rng = np.random.default_rng(1)
    b = [10_000 * float(np.prod(1 + rng.normal(0.0004, 0.01, i))) for i in range(n)]
    s = perf.stats(_rows(a), _rows(b), initial=10_000)
    assert s["reliable"] is True and s["cagr"] == pytest.approx((1.001 ** 252) - 1, rel=0.02)
    assert s["max_drawdown"] == pytest.approx(0.0, abs=1e-12) and s["annual_volatility"] < 0.01
    assert "excess_total_return" in s and "tracking_error" in s and "beta" in s
