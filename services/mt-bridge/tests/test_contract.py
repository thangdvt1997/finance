"""Contract test: cung 1 kich ban qua (a) FakeMT5 adapter, (b) EA gia gui HTTP (mt4 & mt5) -> ket qua chuan hoa phai khop."""
import pytest
from scenario import T0, make_cfg, post, to_ea_batch, to_fake_mt5

from mtbridge.adapters.mt5 import MT5Gateway

DROP = {"account_id", "platform", "source"}


def norm(obj):
    d = obj.model_dump(mode="json")
    return {k: v for k, v in d.items() if k not in DROP}


def snapshot(gw, tf="H1"):
    return {
        "account": norm(gw.get_account()),
        "positions": [norm(p) for p in gw.get_positions()],
        "orders": [norm(o) for o in gw.get_orders()],
        "quotes": [norm(q) for q in gw.get_quotes(["EURUSD", "XAUUSD"])],
        "bars": {s: [norm(b) for b in gw.get_rates(s, tf, 10)] for s in ("EURUSD", "XAUUSD")},
    }


@pytest.fixture
def mt5_snapshot():
    fake = to_fake_mt5()
    gw = MT5Gateway(make_cfg("m5d", "mt5", transport="mt5_direct"), fake, password="investor", clock=lambda: T0)
    gw.connect()
    snap = snapshot(gw)
    assert set(fake.calls) <= {"initialize", "account_info", "positions_get", "orders_get", "symbol_select", "symbol_info_tick", "copy_rates_from_pos", "copy_rates_range", "copy_ticks_from", "shutdown"}
    return snap


@pytest.mark.parametrize("acc,platform", [("a4", "mt4"), ("a5", "mt5")])
def test_ea_path_matches_mt5_adapter(env, mt5_snapshot, acc, platform):
    svc, client, pub, _ = env
    r = post(client, f"secret-token-{acc}-xxxxxxxx", to_ea_batch(acc, platform))
    assert r.status_code == 200, r.text
    got = snapshot(svc.gateways[acc])
    exp = mt5_snapshot
    if platform == "mt4":
        assert got["account"].pop("margin_mode") == "hedging"  # MT4 luon hedging
        exp = {**exp, "account": {k: v for k, v in exp["account"].items() if k != "margin_mode"}}
    assert got == exp
    # bar dang chay khong bao gio xuat hien
    assert [b["ts_open"] for b in got["bars"]["EURUSD"]] == ["2026-10-11T09:00:00Z", "2026-10-11T10:00:00Z", "2026-10-11T11:00:00Z"]


def test_normalization_details(mt5_snapshot):
    pos = {p["position_id"]: p for p in mt5_snapshot["positions"]}
    assert pos["1001"]["symbol"] == "EURUSD" and pos["1001"]["broker_symbol"] == "EURUSD.m" and pos["1001"]["side"] == "buy"
    assert pos["1002"]["side"] == "sell" and pos["1002"]["volume"] == 0.05
    assert pos["1001"]["time_open"].startswith("2026-10-11T09:00:00")  # server UTC+3 da quy ve UTC
    assert mt5_snapshot["orders"][0]["kind"] == "buy_limit"
