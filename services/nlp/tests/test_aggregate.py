from nlp.aggregate import SymbolAggregator

H = 3600.0
NOW = 1_800_000_000.0


def seeded():
    a = SymbolAggregator(min_delta=0.5, min_n_1h=3, min_n_24h=6, cooldown_s=6 * H, fresh_s=2 * H)
    for i in range(8):                       # nền dương trong 3-17h trước
        a.add("XAUUSD", NOW - (3 + i * 2) * H, 0.6)
    for i in range(3):                       # giờ gần nhất âm
        a.add("XAUUSD", NOW - 600 * (i + 1), -0.7)
    return a


def test_windows():
    w1, w24 = seeded().windows("XAUUSD", NOW)
    assert w1.n == 3 and w1.mean < -0.6 and w24.n == 11 and w24.mean > 0


def test_reversal_detected_once_with_cooldown_and_key():
    a = seeded()
    r = a.check_reversal("XAUUSD", NOW, NOW - 600)
    assert r and r.direction == "down" and r.current < 0 < r.baseline
    assert r.dedupe_key.startswith("nlp:flip:XAUUSD:down:")
    assert a.check_reversal("XAUUSD", NOW + 60, NOW) is None          # cooldown


def test_no_alert_when_not_enough_samples_or_no_flip_or_stale():
    a = SymbolAggregator()
    for i in range(2):
        a.add("EURUSD", NOW - 300 * (i + 1), -0.9)
    for i in range(8):
        a.add("EURUSD", NOW - (3 + i) * H, 0.7)
    assert a.check_reversal("EURUSD", NOW, NOW - 300) is None          # chỉ 2 tin trong 1h
    assert seeded().check_reversal("XAUUSD", NOW + 5 * H, NOW - 600) is None   # tin cũ (backfill)
    c = SymbolAggregator()
    for i in range(10):
        c.add("USOIL", NOW - (i + 1) * 600, 0.5)
    assert c.check_reversal("USOIL", NOW, NOW - 600) is None            # cùng dấu


def test_prune_and_snapshot():
    a = seeded()
    a.add("OLD", NOW - 30 * H, 0.1)
    a.prune(NOW)
    assert "OLD" not in a.data and "XAUUSD" in a.snapshot(NOW)
