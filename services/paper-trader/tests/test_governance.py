"""Quản trị + chất lượng paper: hash-chain (tính chất + phát hiện sửa), cấu hình bất biến, hiệu suất CI, TCA, drift/CUSUM, strategy card, API.
Giá trị kiểm bằng TAY khi có thể (ghi rõ trong từng test)."""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from paper_trader import card as cardmod, chain, drift, perfx, tca
from paper_trader.app import create_app
from paper_trader.config import Settings
from paper_trader.repo import MemoryBarSource, MemoryPaperStore
from paper_trader.runner import Runner
from paper_trader.service import Anchors, Monitor, QualityService

from .conftest import DAY, START
from .test_runner_api import FakeBus, cfg, data, make_runner

CARDS = str(Path(__file__).resolve().parents[1] / "cards")
PPY = 252


async def run_account(n_cycles=3, bus=None):
    r, store, src = await make_runner(bus=bus)
    for k in (6, 8, 11):
        await r.run_cycle(START + DAY * k)
    return r, store, src


async def verify(store, aid="bh", anchor=None):
    entries = await store.chain_entries(aid)
    live, status = await store.chain_live(aid)
    return chain.verify(aid, entries, live, status, anchor)


# =============================================================================================== HASH-CHAIN
async def test_chain_built_and_verifies_and_restart_idempotent():
    r, store, _ = await run_account()
    v = await verify(store)
    assert v["ok"] and v["entries"] > 10 and v["problems"] == []
    scope = v["scope"]
    assert scope["order"] == 2 and scope["fill"] == 2 and scope["equity"] == 6 and scope["event"] >= 3 and scope["order_status"] >= 4
    seqs = [e["seq"] for e in store.chain_["bh"]]
    assert seqs == list(range(1, len(seqs) + 1))                       # seq liên tục
    for a, b in zip(store.chain_["bh"], store.chain_["bh"][1:]):       # mỗi bản ghi chứa hash(bản ghi trước + nội dung)
        assert b["prev_hash"] == a["row_hash"]
        assert b["row_hash"] == chain.row_hash(a["row_hash"], b["seq"], b["kind"], b["ref"], b["content_hash"])
    assert store.chain_["bh"][0]["prev_hash"] == chain.genesis("bh")
    n = len(store.chain_["bh"])
    r2 = Runner(cfg(), MemoryBarSource(data()), store, None, None)       # restart: không trùng/đứt chuỗi
    await r2.init()
    await r2.run_cycle(START + DAY * 11)
    await r2.run_cycle(START + DAY * 11)
    assert len(store.chain_["bh"]) == n and (await verify(store))["ok"]


async def test_chain_detects_modified_fill_event_equity_order():
    r, store, _ = await run_account()
    base = await verify(store)
    assert base["ok"]
    # 1) sửa giá khớp
    k = next(iter(store.fills_))
    old = store.fills_[k]["price"]
    store.fills_[k]["price"] = old * 1.0001
    v = await verify(store)
    assert not v["ok"] and v["problem_counts"] == {"modified": 1} and v["problems"][0]["kind"] == "fill"
    store.fills_[k]["price"] = old
    assert (await verify(store))["ok"]                                  # sửa lại đúng -> hợp lệ trở lại (xác nhận kiểm tra theo nội dung)
    # 2) sửa nội dung sự kiện
    ek = next(iter(store.events_))
    msg = store.events_[ek]["message"]
    store.events_[ek]["message"] = msg + "!"
    assert (await verify(store))["problem_counts"] == {"modified": 1}
    store.events_[ek]["message"] = msg
    # 3) sửa equity
    qk = next(iter(store.equity_))
    e0 = store.equity_[qk]["equity"]
    store.equity_[qk]["equity"] = e0 + 1.0
    v = await verify(store)
    assert v["problems"][0]["kind"] == "equity" and not v["ok"]
    store.equity_[qk]["equity"] = e0
    # 4) sửa trường bất biến của lệnh
    ok_ = next(iter(store.orders_))
    q0 = store.orders_[ok_]["qty"]
    store.orders_[ok_]["qty"] = q0 + 1
    assert (await verify(store))["problems"][0]["kind"] == "order"
    store.orders_[ok_]["qty"] = q0
    assert (await verify(store))["ok"]


async def test_chain_detects_deleted_inserted_status_and_chain_tamper():
    r, store, _ = await run_account()
    # xoá fill
    k = next(iter(store.fills_))
    row = store.fills_.pop(k)
    v = await verify(store)
    assert v["problem_counts"].get("deleted") == 1
    store.fills_[k] = row
    # chèn fill không qua đường chính thức -> unchained
    store.fills_["bh:fake:EURUSD"] = {**row, "client_order_id": "bh:fake:EURUSD"}
    assert (await verify(store))["problem_counts"] == {"unchained": 1}
    del store.fills_["bh:fake:EURUSD"]
    # đổi trạng thái lệnh ngoài chuỗi
    ok_ = next(iter(store.orders_))
    st0 = store.orders_[ok_]["status"]
    store.orders_[ok_]["status"] = "cancelled" if st0 != "cancelled" else "pending"
    assert (await verify(store))["problem_counts"] == {"status_mismatch": 1}
    store.orders_[ok_]["status"] = st0
    # sửa bảng chuỗi: đổi content_hash một dòng -> bad_hash
    ents = store.chain_["bh"]
    mid = len(ents) // 2
    good = ents[mid]["content_hash"]
    ents[mid]["content_hash"] = "0" * 64
    v = await verify(store)
    assert v["problem_counts"].get("bad_hash") == 1 and not v["ok"]
    ents[mid]["content_hash"] = good
    # xoá một dòng giữa chuỗi -> seq_gap + link_break
    removed = ents.pop(mid)
    v = await verify(store)
    assert v["problem_counts"].get("seq_gap") and v["problem_counts"].get("link_break")
    ents.insert(mid, removed)
    assert (await verify(store))["ok"]


async def test_chain_anchor_detects_full_rewrite():
    """Kẻ sửa nội dung RỒI tính lại toàn bộ chuỗi vẫn bị bắt nhờ neo ngoài DB."""
    r, store, _ = await run_account()
    v = await verify(store)
    anchor = {"seq": v["head"]["seq"], "hash": v["head"]["hash"]}
    assert (await verify(store, anchor=anchor))["anchor_ok"] is True
    k = next(iter(store.fills_))
    store.fills_[k]["price"] *= 1.01
    ents = store.chain_["bh"]                                            # tính lại chuỗi sau khi sửa
    live, _ = await store.chain_live("bh")
    prev = chain.genesis("bh")
    for e in ents:
        if e["kind"] != "order_status":
            e["content_hash"] = live[e["kind"]][e["ref"]]
        e["prev_hash"] = prev
        e["row_hash"] = chain.row_hash(prev, e["seq"], e["kind"], e["ref"], e["content_hash"])
        prev = e["row_hash"]
    v2 = await verify(store, anchor=anchor)
    assert not v2["ok"] and v2["anchor_ok"] is False and v2["problem_counts"] == {"anchor_mismatch": 1}
    assert (await verify(store))["ok"]                                   # không có neo thì chuỗi tính lại trông hợp lệ (giới hạn đã nêu)


async def test_chain_bootstrap_on_legacy_rows():
    r, store, _ = await run_account()
    store.chain_.clear()                                                 # giả lập journal cũ trước khi có hash-chain
    assert (await verify(store))["problem_counts"]["unchained"] > 0
    assert await store.chain_bootstrap("bh") > 10
    assert (await verify(store))["ok"]
    assert await store.chain_bootstrap("bh") == 0                        # chỉ chạy khi chuỗi rỗng
    await r.run_cycle(START + DAY * 11)
    assert (await verify(store))["ok"]


async def test_legacy_journal_adopted_before_config_event():
    """Hồi quy: journal cũ (chưa có chuỗi/phiên bản cấu hình) -> init phải neo bản ghi cũ TRƯỚC khi ghi sự kiện cấu hình đầu tiên."""
    r, store, _ = await run_account()
    store.chain_.clear()
    store.versions_.clear()
    for k in [k for k, e in store.events_.items() if e["type"] == "config_version"]:
        del store.events_[k]
    r2 = Runner(cfg(), MemoryBarSource(data()), store, None, None)
    await r2.init()
    v = await verify(store)
    assert v["ok"] and v["scope"]["order"] == 2 and v["scope"]["equity"] == 6 and v["scope"]["event"] >= 3
    first = store.chain_["bh"][0]
    assert first["kind"] != "event" or first["ref"] != next(e["event_key"] for e in store.events_.values() if e["type"] == "config_version")


def test_canonical_hash_stable():
    a = {"b": 1.0, "a": [1, 2.5, None], "t": datetime(2026, 1, 1, tzinfo=timezone.utc), "n": float("nan")}
    b = {"t": "2026-01-01T00:00:00+00:00", "a": [1.0, 2.5, None], "n": "NaN", "b": 1}
    assert chain.hash_obj(a) == chain.hash_obj(b)
    assert chain.hash_obj({"x": 1}) != chain.hash_obj({"x": 1.0000001})
    # giá trị tay: sha256('genesis:bh')
    import hashlib
    assert chain.genesis("bh") == hashlib.sha256(b"genesis:bh").hexdigest()


# =============================================================================================== CẤU HÌNH BẤT BIẾN
async def test_config_versions_immutable_and_change_creates_new_version():
    bus = FakeBus()
    store = MemoryPaperStore()
    r = Runner(cfg(), MemoryBarSource(data()), store, bus, None)
    await r.init()
    acc = await store.get_account("bh")
    h1, v1 = acc["config"]["config_hash"], acc["config"]["config_version"]
    assert v1 == 1 and len(h1) == 64 and acc["config"]["assumptions"]["EURUSD"]["spread_bps"] == 2.0
    evs = [e for e in store.events_.values() if e["type"] == "config_version"]
    assert len(evs) == 1 and evs[0]["severity"] == "info"
    r2 = Runner(cfg(), MemoryBarSource(data()), store, bus, None)        # cùng cấu hình -> cùng hash, KHÔNG tạo phiên bản mới
    await r2.init()
    assert (await store.get_account("bh"))["config"]["config_hash"] == h1 and len(store.versions_["bh"]) == 1
    c3 = cfg()
    c3["instruments"]["EURUSD"]["spread_bps"] = 3.0                      # đổi giả định chi phí -> phiên bản mới
    r3 = Runner(c3, MemoryBarSource(data()), store, bus, None)
    await r3.init()
    acc = await store.get_account("bh")
    assert acc["config"]["config_version"] == 2 and acc["config"]["config_hash"] != h1
    assert [v["version"] for v in store.versions_["bh"]] == [1, 2] and store.versions_["bh"][0]["config_hash"] == h1   # bản cũ còn nguyên
    evs = [e for e in store.events_.values() if e["type"] == "config_version"]
    assert len(evs) == 2 and any(e["severity"] == "warn" for e in evs)
    assert any(s == "alerts.out" and "ĐỔI" in e.payload["title"] for s, e in bus.sent)
    c4 = cfg(params={"gross": 0.9})                                      # đổi tham số chiến lược -> hash tham số đổi
    r4 = Runner(c4, MemoryBarSource(data()), store, bus, None)
    await r4.init()
    assert store.versions_["bh"][-1]["params_hash"] != store.versions_["bh"][0]["params_hash"]
    assert (await verify(store))["ok"]                                   # sự kiện cấu hình cũng nằm trong chuỗi


# =============================================================================================== HIỆU SUẤT + CI
def test_metrics_hand_values_and_match_empyrical():
    import empyrical as ep
    r = np.array([0.01, 0.02, -0.01, 0.0])
    m = perfx.point_metrics(r, PPY)
    sd = math.sqrt(0.0005 / 3)                                           # tay: mean 0.005, phương sai mẫu 0.0005/3
    assert m["sharpe"] == pytest.approx(0.005 / sd * math.sqrt(252), rel=1e-12)
    assert m["vol"] == pytest.approx(sd * math.sqrt(252), rel=1e-12)
    assert m["hit_rate"] == 0.5
    dn = math.sqrt((0.01 ** 2) / 4)                                      # tay: chỉ -1% là âm -> sqrt(mean(min(r,0)^2))
    assert m["sortino"] == pytest.approx(0.005 / dn * math.sqrt(252), rel=1e-12)
    assert m["max_dd"] == pytest.approx(-0.01, abs=1e-12)                # đỉnh 1.0302 -> 1.0302*0.99 -> -1%
    assert m["cagr"] == pytest.approx((1.01 * 1.02 * 0.99 * 1.0) ** (252 / 4) - 1, rel=1e-10)
    rng = np.random.default_rng(3)
    x = rng.normal(0.0004, 0.01, 800)
    x[0] = 0.003                                                          # ngày đầu dương: định nghĩa MaxDD empyrical trùng
    mm = perfx.point_metrics(x, PPY)
    s = pd.Series(x)
    assert mm["sharpe"] == pytest.approx(ep.sharpe_ratio(s, annualization=PPY), rel=1e-9)
    assert mm["sortino"] == pytest.approx(ep.sortino_ratio(s, annualization=PPY), rel=1e-9)
    assert mm["vol"] == pytest.approx(ep.annual_volatility(s, annualization=PPY), rel=1e-9)
    assert mm["cagr"] == pytest.approx(ep.cagr(s, annualization=PPY), rel=1e-9)
    assert mm["max_dd"] == pytest.approx(ep.max_drawdown(s), rel=1e-9)
    assert mm["calmar"] == pytest.approx(ep.calmar_ratio(s, annualization=PPY), rel=1e-9)


def test_bootstrap_ci_properties():
    rng = np.random.default_rng(11)
    x = rng.normal(0.0006, 0.01, 1500)                                   # Sharpe thật ≈ 0.95
    ci = perfx.bootstrap_ci(x, PPY)
    pt = perfx.point_metrics(x, PPY)
    lo, hi = ci["sharpe"]
    assert lo < pt["sharpe"] < hi
    assert ci["sharpe"] == perfx.bootstrap_ci(x, PPY)["sharpe"]          # tất định (hạt giống cố định)
    years = len(x) / PPY
    analytic = 2 * 1.96 * math.sqrt((1 + 0.5 * pt["sharpe"] ** 2) / years)
    assert 0.6 * analytic < (hi - lo) < 1.6 * analytic                  # độ rộng cùng bậc công thức giải tích Lo (2002)
    assert perfx.bootstrap_ci(x[:400], PPY)["sharpe"][1] - perfx.bootstrap_ci(x[:400], PPY)["sharpe"][0] > hi - lo   # mẫu ngắn -> CI rộng hơn
    assert all(v is None for v in perfx.bootstrap_ci(x[:10], PPY).values())   # < 20 ngày -> không có CI
    cov = 0
    for seed in range(60):                                               # độ phủ ~95% (khoảng 80-100% cho 60 mô phỏng, mẫu 500 ngày)
        y = np.random.default_rng(100 + seed).normal(0.0004, 0.01, 500)
        a, b = perfx.bootstrap_ci(y, PPY, B=400, seed=seed)["sharpe"]
        true_sr = 0.0004 / 0.01 * math.sqrt(PPY)
        cov += a <= true_sr <= b
    assert 0.80 <= cov / 60 <= 1.0


def test_stationary_bootstrap_indices():
    rng = np.random.default_rng(1)
    idx = perfx.stationary_indices(100, 50, 5.0, rng)
    assert idx.shape == (50, 100) and idx.min() >= 0 and idx.max() < 100
    steps = np.diff(idx, axis=1) % 100
    cont = (steps == 1).mean()                                           # P(tiếp tục khối) ≈ 1 - 1/L = 0.8 (+ chút nhảy trúng)
    assert 0.75 < cont < 0.9


def test_rolling_benchmark_attribution_hand():
    r = pd.Series(np.random.default_rng(5).normal(0.0005, 0.01, 200), index=pd.date_range("2026-01-01", periods=200, freq="D", tz="UTC"))
    rt = perfx.rolling_table(r, PPY, (30, 90))
    assert rt["windows"] == [30, 90]
    last = rt["points"][-1]
    w = r.iloc[-30:]
    assert last["sharpe30"] == pytest.approx(w.mean() / w.std(ddof=1) * math.sqrt(252), rel=1e-9)
    assert last["sharpe30_lo"] < last["sharpe30"] < last["sharpe30_hi"]
    assert perfx.rolling_table(r.iloc[:50], PPY)["windows"] == [30]
    b = pd.Series(np.random.default_rng(6).normal(0.0003, 0.008, 200), index=r.index)
    s = 0.0001 + 1.5 * b                                                 # alpha ngày 0.0001, beta 1.5 chính xác
    c = perfx.compare_benchmark(s, b, PPY, 0.1, 0.05)
    assert c["beta"] == pytest.approx(1.5, abs=1e-9) and c["alpha_ann"] == pytest.approx(0.0001 * 252, rel=1e-6) and c["correlation"] == pytest.approx(1.0)
    assert c["excess_total_return"] == pytest.approx(0.05) and c["up_capture"] == pytest.approx(1.5, rel=0.05)
    assert "note" in perfx.compare_benchmark(s.iloc[:5], b.iloc[:5], PPY, 0, 0)


async def test_report_attribution_reconciles_with_ledger():
    r, store, _ = await run_account()
    st = await store.get_account("bh")
    eq = await store.equity("bh", 100)
    fills = await store.all_fills("bh")
    pos = await store.positions("bh")
    rep = perfx.report(eq, {}, 10_000.0, PPY, fills, pos, float(st["state"]["costs"]["swap"]), "USD")
    a = rep["attribution"]
    assert abs(a["unreconciled"]) < 1e-6                                 # sổ khớp: equity = vốn + chốt + chưa chốt − phí − swap
    assert rep["days"] == len(eq) - 0 or rep["days"] >= 1
    assert rep["reliable"] is False and rep["metrics"]["sharpe"]["ci95"] is None and "CHƯA" in (rep["ci_note"] or "")
    assert rep["leverage"]["current_gross"] > 0


# =============================================================================================== TCA
def test_tca_hand_values():
    fills = [{"symbol": "EURUSD", "side": "buy", "qty": 100.0, "ref_price": 100.0, "q2b": 1.0, "spread_cost": 1.0, "slippage_cost": 1.0,
              "commission": 0.3, "tax": 0.0, "ts": datetime(2026, 1, 6, tzinfo=timezone.utc)}]
    # notional 10000: slip thực = (1+1)/10000*1e4 = 2.0 bps; phí 0.3 bps. Giả định: nửa spread 1.0 + trượt 0.5 = 1.5 bps; phí 0.3
    assum = {"EURUSD": {"spread_bps": 2.0, "slippage_bps": 0.5, "commission_bps": 0.3, "sell_tax_bps": 0.0}}
    rep = tca.report(fills, assum, {"spread": 1.0, "slippage": 1.0, "commission": 0.3, "tax": 0.0, "swap": 0.2}, 10_000.0,
                     [{"equity": 10_000.0}, {"equity": 10_000.0}], 10_000.0)
    o = rep["overall"]
    assert o["realized_slip_bps"] == pytest.approx(2.0) and o["assumed_slip_bps"] == pytest.approx(1.5) and o["range_extra_bps"] == pytest.approx(0.5)
    assert o["all_in_bps"] == pytest.approx(2.3) and o["assumed_all_in_bps"] == pytest.approx(1.8) and o["ratio"] == pytest.approx(2.3 / 1.8)
    assert rep["costs_cum"]["total"] == pytest.approx(2.5) and rep["costs_cum"]["pct_of_initial"] == pytest.approx(2.5 / 10_000)
    assert rep["turnover"]["x_equity"] == pytest.approx(1.0) and rep["status"] == "insufficient"       # < 10 fill
    many = [dict(fills[0], ts=datetime(2026, 1, 6 + i, tzinfo=timezone.utc)) for i in range(12)]
    assert tca.report(many, assum, {}, 0.0, [], 10_000.0)["status"] == "green"
    bad = [dict(f, spread_cost=3.0, slippage_cost=3.0) for f in many]    # slip 6 bps -> toàn phần 6.3/1.8 = 3.5x
    assert tca.report(bad, assum, {}, 0.0, [], 10_000.0)["status"] == "red"
    assert tca.report([], assum, {}, 0.0, [], 10_000.0)["overall"] is None


# =============================================================================================== DRIFT / CUSUM
def test_cusum_hand_values_and_calibration():
    out = drift.cusum_down(np.array([-0.01, 0.02]), mu0=0.001, sigma=0.01, k=0.05, h=3.0)
    # tay: S1 = (0.001+0.01)/0.01 - 0.05 = 1.05 ; S2 = max(0, 1.05 + (0.001-0.02)/0.01 - 0.05) = max(0, -0.9) = 0
    assert out["path"][0] == pytest.approx(1.05) and out["path"][1] == 0.0 and not out["breached"]
    k = (0.553 + 0.5) / (2 * math.sqrt(252))
    h = drift.solve_h(k, 1260.0)
    assert drift.siegmund_arl0(k, h) == pytest.approx(1260.0, rel=1e-6)
    # hiệu chỉnh bằng mô phỏng: P(báo động giả trong ARL0 ngày) ≈ 1 - e^-1 = 0.63 (độ trễ xấp xỉ mũ)
    rng = np.random.default_rng(9)
    N, T = 4000, 1260
    s = np.zeros(N)
    hit = np.zeros(N, bool)
    for _ in range(T):
        s = np.maximum(0.0, s - rng.standard_normal(N) * 1.0 - k)       # trong kiểm soát: x ~ N(0,1) quanh kỳ vọng
        hit |= s >= h
    assert 0.5 < hit.mean() < 0.76


def _series(vals, start="2026-01-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="D", tz="UTC"))


def test_drift_statuses_and_signal_vs_execution_split():
    exp = {"sharpe": 0.55, "vol_ann": 0.095}
    rng = np.random.default_rng(2)
    sigma = 0.006
    z = np.tile([1.0, -1.0], 150)                                        # mẫu có ĐÚNG trung bình kỳ vọng, không có chuỗi xấu (S nhỏ)
    good = _series(0.55 * sigma / math.sqrt(252) + sigma * z)
    rep = drift.report(good, None, exp, PPY, exec_ratio=1.0, n_fills=40)
    assert rep["status"] == "green" and rep["diagnosis"] == "none"
    bad = _series(rng.normal(-1.0 * sigma / math.sqrt(252) * 6, sigma, 400))          # Sharpe live ≈ -6: tín hiệu chết
    rep = drift.report(bad, None, exp, PPY, exec_ratio=1.0, n_fills=40)
    assert rep["status"] == "red" and rep["diagnosis"] == "signal" and rep["signal"]["cusum"]["breached"] and rep["signal_status"] == "red"
    assert rep["signal"]["p_below_expected"] < 0.01 and rep["signal"]["hit_rate"]["observed"] < rep["signal"]["hit_rate"]["expected"]
    ex = drift.report(good, None, exp, PPY, exec_ratio=2.6, n_fills=40)               # tín hiệu ổn nhưng chi phí gấp 2,6 lần
    assert ex["execution"]["status"] == "red" and ex["diagnosis"] == "execution" and ex["signal_status"] == "green"
    cost = _series(np.full(300, 0.0003))                                             # chi phí/ngày 3 bps => lợi suất gộp cao hơn net
    d = drift.report(good, cost, exp, PPY, 1.0, 40)["decomposition"]
    assert d["cost_drag_ann"] == pytest.approx(0.0003 * 252) and d["mean_gross_ann"] == pytest.approx(d["mean_net_ann"] + 0.0003 * 252)
    assert drift.report(good.iloc[:10], None, exp, PPY)["status"] == "insufficient"
    assert drift.report(good, None, None, PPY)["status"] == "n/a"
    flat = drift.report(_series(np.zeros(50)), None, exp, PPY)
    assert flat["status"] == "insufficient" and "biến động" in flat["note"]


# =============================================================================================== STRATEGY CARD
def _perf(days=100, sharpe=0.4, dd=-0.05):
    return {"days": days, "metrics": {"sharpe": {"value": sharpe, "ci95": [-1.0, 1.8]}, "max_dd": {"value": dd}}}


def _acct(**kw):
    return {"account_id": "slow_trend_global_v2", "replay": False, "meaningful": True, "deprecated": False, "status": "active",
            "inception": datetime(2026, 10, 10, tzinfo=timezone.utc), **kw}


def test_card_loaded_and_stage_logic():
    cards = cardmod.load_cards(CARDS)
    cd = cardmod.card_for(cards, "slow_trend_multiasset")
    assert cd and cd["gates"]["paper_to_review"]["min_weeks"] == 12 and cd["backtest"]["sharpe_ci95"] == [0.21, 0.87]
    exp = cardmod.expectation_for(cd, "slow_trend_global_v2")
    assert exp["sharpe"] == 0.553 and cardmod.expectation_for(cd, "slow_trend_fx_v2") is None
    v1 = [{"version": 1, "created_at": datetime(2026, 10, 11, tzinfo=timezone.utc)}]
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    ev = cardmod.evaluate(cd, _acct(), _perf(2), {"status": "insufficient"}, None, True, v1, 0, 0, now, None)
    assert ev["stage"] == "paper_early" and ev["progress"]["pct"] == pytest.approx(2 / 7 / 12, abs=0.01)   # 2 ngày / 7 / 12 tuần
    late = datetime(2026, 10, 10, tzinfo=timezone.utc) + timedelta(weeks=13)
    ok = cardmod.evaluate(cd, _acct(), _perf(), {"status": "green"}, {"overall": {"ratio": 1.1}}, True, v1, 45, 4, late, None)
    assert ok["stage"] == "review_ready" and not ok["failing"] and "tiền thật" in ok["note"]
    low_sh = cardmod.evaluate(cd, _acct(), _perf(sharpe=-0.3), {"status": "green"}, {"overall": {"ratio": 1.0}}, True, v1, 45, 4, late, None)
    assert low_sh["stage"] == "paper_hold" and low_sh["failing"] == ["sharpe"]
    for kw, why in ((dict(chain_ok=False), "chain"), (dict(dd=-0.2), "max_dd")):
        e = cardmod.evaluate(cd, _acct(), _perf(dd=kw.get("dd", -0.05)), {"status": "green"}, None, kw.get("chain_ok", True), v1, 45, 4, late, None)
        assert e["stage"] == "suspended" and why in e["failing"]
    red = cardmod.evaluate(cd, _acct(), _perf(), {"status": "red"}, None, True, v1, 45, 4, late, None)
    assert red["stage"] == "suspended" and "drift" in red["failing"]
    v2 = v1 + [{"version": 2, "created_at": late - timedelta(days=3)}]                 # đổi tham số 3 ngày trước -> đồng hồ làm lại + tiêu chí cấu hình đỏ
    e = cardmod.evaluate(cd, _acct(), _perf(), {"status": "green"}, None, True, v2, 45, 4, late, None)
    assert e["stage"] == "paper_early" and e["progress"]["weeks"] < 1
    assert cardmod.evaluate(cd, _acct(replay=True), _perf(), None, None, True, v1, 0, 0, late, None)["stage"] == "pipeline_test"
    assert cardmod.evaluate(cd, _acct(deprecated=True), None, None, None, True, v1, 0, 0, late, None)["stage"] == "retired"
    assert cardmod.evaluate(None, _acct(), None, None, None, True, v1, 0, 0, late, None)["stage"] == "no_card"
    pl = {"slow_trend_global_v2": "a" * 64}
    cd2 = copy.deepcopy(cd)
    cd2["locked_params_hash"] = pl
    bad = cardmod.evaluate(cd2, _acct(), _perf(), {"status": "green"}, None, True, v1, 45, 4, late, "b" * 64)
    assert bad["stage"] == "suspended" and "params_lock" in bad["failing"]


# =============================================================================================== API + MONITOR
async def test_api_governance_endpoints_and_tamper_detection():
    bus = FakeBus()
    r, store, _ = await make_runner(bus=bus)
    await r.run_cycle(START + DAY * 6)
    await r.run_cycle(START + DAY * 11)
    app = create_app(Settings(card_dir=CARDS), runner=r, store=store)
    with TestClient(app) as cl:
        for p in ("performance", "tca", "drift", "card", "verify", "config-versions"):
            j = cl.get(f"/paper/accounts/bh/{p}")
            assert j.status_code == 200, p
            assert j.json()["simulation"] is True and "MÔ PHỎNG" in j.json()["label"], p
        assert cl.get("/paper/accounts/zzz/verify").status_code == 404
        perf = cl.get("/paper/accounts/bh/performance").json()
        assert perf["days"] >= 1 and perf["reliable"] is False and perf["attribution"]["classes"]
        assert cl.get("/paper/accounts/bh/tca").json()["overall"]["fills"] == 2
        card = cl.get("/paper/accounts/bh/card").json()
        assert card["evaluation"]["stage"] == "no_card" and card["config"]["version"] == 1       # buy_and_hold: không có strategy card
        gov = cl.get("/paper/governance").json()
        assert gov["items"][0]["chain_ok"] is True and gov["items"][0]["config_version"] == 1 and gov["cards"][0]["id"] == "slow_trend_multiasset"
        v = cl.get("/paper/verify").json()
        assert v["ok"] is True and v["items"][0]["entries"] > 10
        k = next(iter(store.fills_))                                    # SỬA journal -> endpoint phải báo đứt
        store.fills_[k]["price"] += 0.01
        v = cl.get("/paper/verify").json()
        assert v["ok"] is False and v["items"][0]["problem_counts"] == {"modified": 1}
        assert cl.get("/paper/accounts/bh/verify").json()["ok"] is False
    # Monitor: cảnh báo khi chuỗi đứt (alerts.out + sự kiện trong journal)
    svc = QualityService(store, cardmod.load_cards(CARDS), Anchors())
    mon = Monitor(r, svc, interval=0)
    bus.sent.clear()
    out = await mon.tick(datetime.now(timezone.utc), force=True)
    assert out["bh"]["chain_ok"] is False
    al = [e.payload for s, e in bus.sent if s == "alerts.out"]
    assert any("HASH-CHAIN" in a["title"] and a["level"] == "crit" for a in al)
    assert any(e["type"] == "chain_break" for e in store.events_.values())
    await mon.tick(datetime.now(timezone.utc), force=True)                # cùng trạng thái đứt: không cảnh báo lặp
    assert len([1 for s, e in bus.sent if s == "alerts.out"]) == len(al)


async def test_monitor_drift_alert_and_anchor_on_ok():
    """Tài khoản có kỳ vọng backtest: drift đỏ -> alert + sự kiện; chuỗi OK -> ghi neo."""
    bus = FakeBus()
    r, store, _ = await run_account(bus=bus)
    cards = cardmod.load_cards(CARDS)
    cards["slow_trend_multiasset"]["applies_to"]["accounts"].append("bh")
    cards["slow_trend_multiasset"]["strategy"] = "buy_and_hold"
    svc = QualityService(store, cards, Anchors())
    bad = _series(np.random.default_rng(1).normal(-0.003, 0.004, 80))
    r.accounts["bh"].engine.strategy.meaningful = True
    mon = Monitor(r, svc, interval=0)
    svc.drift = lambda aid, fresh=False: _async(drift.report(bad, None, {"sharpe": 0.55}, PPY, 1.0, 30))       # type: ignore[assignment]
    out = await mon.tick(datetime.now(timezone.utc), force=True)
    assert out["bh"]["chain_ok"] is True and out["bh"]["drift"] == "red"
    assert 0 < (await svc.anchors.get("bh"))["seq"] <= len(store.chain_["bh"])
    assert any(e["type"] == "drift_alert" for e in store.events_.values())
    assert any("suy giảm" in e.payload["title"] for s, e in bus.sent if s == "alerts.out")


async def _async(v):
    return v
