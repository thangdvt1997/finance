from pattern_scan import paper


def _t(**kw):
    p = {"setup_id": "KB-1:x", "pattern": "KB-1", "symbol": "EURUSD", "tf": "M15", "ts": "2026-10-01T10:15:00+00:00",
         "bar_ts": "2026-10-01T10:00:00+00:00", "levels": {"entry": 100.0, "sl": 110.0, "tp_1r": 90.0, "tp_2r": 80.0, "tp_3r": 70.0}}
    p.update(kw)
    return paper.open_trade(p, cost_bps=0.0, replay=False)


def bar(o, h, l, c, k=0):
    return {"ts": f"2026-10-01T1{k % 10}:00:00+00:00", "o": o, "h": h, "l": l, "c": c}


def test_open_rejects_bad_levels():
    assert _t(levels={"entry": 100.0, "sl": 95.0}) is None       # SL dưới entry cho lệnh Sell = vô lý
    assert _t(levels={"entry": 100.0}) is None


def test_tp_ladder_then_sl():
    t = _t()
    assert not paper.step(t, bar(100, 101, 89, 90), "c1", 100)        # TP1
    assert [lg["status"] for lg in t["legs"]] == ["tp", "open", "open"]
    assert paper.step(t, bar(90, 111, 89, 105), "c2", 100)            # chạm SL -> 2 phần còn lại SL
    assert [lg["status"] for lg in t["legs"]] == ["tp", "sl", "sl"]
    assert t["result_r"] == round((1 - 1 - 1) / 3, 4)


def test_same_bar_sl_and_tp_is_sl_first():
    t = _t()
    assert paper.step(t, bar(100, 112, 60, 95), "c1", 100)
    assert all(lg["status"] == "sl" for lg in t["legs"]) and t["result_r"] == -1.0


def test_gap_over_sl_fills_at_open_and_gap_below_tp():
    t = _t()
    paper.step(t, bar(115, 116, 114, 115), "c1", 100)
    assert t["legs"][0]["exit"] == 115 and t["legs"][0]["r"] == -1.5
    t = _t()
    paper.step(t, bar(65, 66, 60, 62), "c1", 100)
    assert all(lg["status"] == "tp" and lg["exit"] == 65 for lg in t["legs"])


def test_timeout_and_cost():
    t = paper.open_trade({"setup_id": "s", "pattern": "KB-3", "symbol": "XAUUSD", "tf": "H1", "ts": "2026-10-01T10:00:00+00:00",
                          "bar_ts": "2026-10-01T09:00:00+00:00", "levels": {"entry": 2000.0, "sl": 2010.0}}, cost_bps=5.0, replay=True)
    assert t["tp"] == [1990.0, 1980.0, 1970.0] and t["cost_r"] == 0.1 and t["replay"]
    assert not paper.step(t, bar(2000, 2001, 1995, 1996), "c1", 2)
    assert paper.step(t, bar(1996, 1998, 1994, 1995), "c2", 2)
    assert all(lg["status"] == "timeout" for lg in t["legs"]) and t["result_r"] == round(0.5 - 0.1, 4)
    assert t["mfe_r"] == 0.6 and t["mae_r"] == 0.1


def test_cost_bps_lookup():
    tb = {"default": 2.0, "XAUUSD": 3.0, "CRYPTO:": 10.0}
    assert paper.cost_bps_for("XAUUSD", tb) == 3.0 and paper.cost_bps_for("CRYPTO:BTCUSDT", tb) == 10.0 and paper.cost_bps_for("EURUSD", tb) == 2.0


def test_ledger_verify_detects_tamper():
    rows, prev = [], paper.GENESIS
    for k in range(3):
        c = {"id": k, "x": k * 1.5}
        h = paper.chain_hash(prev, "open", str(k), c)
        rows.append({"seq": k + 1, "kind": "open", "ref": str(k), "content": c, "prev_hash": prev, "hash": h})
        prev = h
    assert paper.verify(rows)["ok"]
    rows[1]["content"] = {"id": 1, "x": 99}
    v = paper.verify(rows)
    assert not v["ok"] and v["broken_at"] == 2


def test_stats_excludes_replay():
    a, b = _t(), _t(setup_id="b")
    paper.step(a, bar(100, 101, 69, 70), "2026-10-02T00:00:00+00:00", 10)
    paper.step(b, bar(100, 111, 99, 105), "2026-10-03T00:00:00+00:00", 10)
    b["replay"] = True
    s = paper.stats([a, b])
    assert s["overall"]["n_closed"] == 1 and s["overall"]["sum_r"] == 2.0 and "Mẫu nhỏ" in s["note"]
    s2 = paper.stats([a, b], include_replay=True)
    assert s2["overall"]["n_closed"] == 2 and s2["overall"]["sum_r"] == 1.0 and s2["overall"]["max_dd_r"] == -1.0
