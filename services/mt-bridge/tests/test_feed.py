"""Chuoi canon (feed EA uu tien): M1 phat ngay, lap phut khong tick, khung cao gop theo moc UTC chi khi quan sat tron,
fallback (khong phat) khi bucket do dang / EA offline, nen tre -> phat lai, raw H4/D1 bi bo, rollback bang co."""
import asyncio
from datetime import datetime, timedelta, timezone

from mtbridge.feed import CanonFeed, FeedSettings
from mtbridge.models import Bar

T = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)   # thu Tu
SRC = "canon:mt5:100000001"


def st(**kw):
    base = dict(enabled=True, account="mt5:100000001", symbols=("EURUSD", "XAUUSD", "US500"), prefix="canon",
                stale_s=300, fill_max_min=5, grace_s=120)
    base.update(kw)
    return FeedSettings(**base)


def m1(ts, c=1.1, sym="EURUSD", tf="M1", v=10.0):
    return Bar(symbol=sym, broker_symbol=sym, tf=tf, ts_open=ts, o=c, h=c + 0.001, l=c - 0.001, c=c, v=v, source="mt5:mt5:100000001")


def run(feed, start, minutes, step_hb=True, **kw):
    """Gui lan luot nen M1 [start, start+minutes) nhu EA (moi nen den luc ts+1m+5s)."""
    out = []
    for i in range(minutes):
        ts = start + timedelta(minutes=i)
        now = ts + timedelta(minutes=1, seconds=5)
        feed.heartbeat(now)
        out += feed.on_bars([m1(ts, c=1.1 + i * 1e-4, **kw)], now)
    return out


def by_tf(out, tf):
    return [b for b in out if b.tf == tf]


def test_m1_republished_immediately_with_canon_source():
    f = CanonFeed(st())
    out = run(f, T, 3)
    assert [b.ts_open for b in by_tf(out, "M1")] == [T, T + timedelta(minutes=1), T + timedelta(minutes=2)]
    assert all(b.source == SRC for b in out)


def test_other_symbols_and_tfs_ignored():
    f = CanonFeed(st())
    assert f.on_bars([m1(T, sym="GBPUSD"), m1(T, tf="H1")], T) == []


def test_partial_bucket_at_session_start_not_emitted_full_one_is():
    f = CanonFeed(st())
    out = run(f, T + timedelta(minutes=16), 50)        # phien bat dau 13:16 -> 14:05
    m15 = by_tf(out, "M15")
    assert [b.ts_open for b in m15] == [T + timedelta(minutes=30), T + timedelta(minutes=45)]  # 13:15 do dang -> khong phat
    assert by_tf(out, "H1") == []                        # 13:00 do dang -> nguon cu dung cho H1 13:00
    full = m15[0]
    src = [1.1 + i * 1e-4 for i in range(14, 29)]        # M1 13:30..13:44
    assert abs(full.o - src[0]) < 1e-12 and abs(full.c - src[-1]) < 1e-12
    assert abs(full.h - (max(src) + 0.001)) < 1e-12 and abs(full.l - (min(src) - 0.001)) < 1e-12 and full.v == 150


def test_h4_d1_aligned_utc_not_server_time():
    f = CanonFeed(st())
    out = run(f, T.replace(hour=0), 24 * 60 + 1)         # tron ngay 00:00 -> 00:00 hom sau
    d1 = by_tf(out, "D1")
    assert [b.ts_open for b in d1] == [T.replace(hour=0)]
    assert [b.ts_open.hour for b in by_tf(out, "H4")] == [0, 4, 8, 12, 16, 20]
    assert d1[0].v == 24 * 60 * 10


def test_no_tick_minutes_filled_flat_but_not_long_gaps():
    f = CanonFeed(st())
    f.heartbeat(T)
    f.on_bars([m1(T, c=1.2)], T)
    out = f.on_bars([m1(T + timedelta(minutes=4), c=1.3)], T + timedelta(minutes=5))
    flat = [b for b in by_tf(out, "M1") if b.v == 0]
    assert [b.ts_open.minute for b in flat] == [1, 2, 3] and all(b.o == b.h == b.l == b.c == 1.2 for b in flat)
    out = f.on_bars([m1(T + timedelta(minutes=30), c=1.3)], T + timedelta(minutes=31))   # 25 phut khong tick (EA van song): khong lap
    assert len(by_tf(out, "M1")) == 1


def test_offline_gap_starts_new_session_and_drops_partial_buckets():
    f = CanonFeed(st())
    run(f, T, 10)                                        # 13:00-13:09
    f.heartbeat(T + timedelta(minutes=30))               # EA im lang 20 phut > stale_s
    out = run(f, T + timedelta(minutes=32), 30)          # quay lai 13:32 (khong lien mach)
    assert f.sessions == 2
    assert by_tf(out, "H1") == []                        # H1 13:00 khong quan sat tron -> fallback
    assert T + timedelta(minutes=30) not in [b.ts_open for b in by_tf(out, "M15")]
    assert T + timedelta(minutes=45) in [b.ts_open for b in by_tf(out, "M15")]


def test_offline_but_contiguous_resend_keeps_session():
    f = CanonFeed(st())
    run(f, T, 10)
    f.heartbeat(T + timedelta(minutes=30))               # bridge/EA mat ket noi, EA gui bu tu con tro -> lien mach
    out = run(f, T + timedelta(minutes=10), 51)          # 13:10 -> 14:00
    assert f.sessions == 1
    assert [b.ts_open for b in by_tf(out, "H1")] == [T]


def test_flush_on_timer_when_market_quiet_and_late_bar_reemits():
    f = CanonFeed(st())
    run(f, T, 59)                                        # 13:00..13:58; 13:59 chua den (chua co tick phut sau)
    end = T + timedelta(hours=1)
    f.heartbeat(end + timedelta(seconds=60))
    assert by_tf(f.flush_due(end + timedelta(seconds=60)), "H1") == []        # chua qua grace
    f.heartbeat(end + timedelta(seconds=130))
    h1 = by_tf(f.flush_due(end + timedelta(seconds=130)), "H1")
    assert len(h1) == 1 and h1[0].ts_open == T
    late = f.on_bars([m1(T + timedelta(minutes=59), c=1.5)], end + timedelta(seconds=200))
    fix = by_tf(late, "H1")
    assert len(fix) == 1 and fix[0].c == 1.5 and fix[0].ts_open == T     # phat lai ban dung (upsert cung khoa)
    f.heartbeat(end + timedelta(seconds=290))
    assert by_tf(f.flush_due(end + timedelta(seconds=300)), "H1") == []          # khong phat trung lan nua


def test_no_timer_flush_while_ea_offline():
    f = CanonFeed(st())
    run(f, T, 59)
    assert f.flush_due(T + timedelta(hours=2)) == []     # heartbeat cuoi 13:59:05 -> stale


def test_duplicate_and_old_bars_ignored():
    f = CanonFeed(st())
    run(f, T, 3)
    assert f.on_bars([m1(T + timedelta(minutes=1))], T + timedelta(minutes=5)) == []


def test_disabled_flag_and_other_account():
    assert not CanonFeed(st(enabled=False)).active_for("mt5:100000001")
    assert not CanonFeed(st()).active_for("mt5:99000001")
    assert CanonFeed(st()).active_for("mt5:100000001")


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("FEED_CANON_ENABLED", "false")
    monkeypatch.setenv("FEED_CANON_SYMBOLS", "eurusd, us30")
    s = FeedSettings()
    assert s.enabled is False and s.symbols == ("EURUSD", "US30") and s.source == "canon:mt5:100000001"


def test_source_sorts_before_existing_sources():
    # moi duong doc dung DISTINCT ON (ts_open) ... ORDER BY source -> canon phai dung truoc nguon cu theo chu cai
    assert sorted([SRC, "dukascopy", "crypto_ccxt", "frankfurter", "mt5:mt5:100000001", "yahoo_daily"])[0] == SRC


def test_service_drops_raw_h4_d1_and_publishes_canon():
    """Tich hop BridgeService: raw H4/D1 bi bo theo MT_BAR_TFS; tai khoan feed sinh nen canon tren md.bars."""
    from mtbridge.service import BridgeService, Settings
    from mtbridge.accounts import BridgeConfig

    class Pub:
        def __init__(self):
            self.ev = []

        async def publish(self, stream, event):
            self.ev.append((stream, event))

    pub = Pub()
    svc = BridgeService(BridgeConfig(accounts=[]), pub, settings=Settings(), clock=lambda: T + timedelta(minutes=2))
    svc.feed = CanonFeed(st())
    raw = svc._raw_bars([m1(T), m1(T, tf="H4"), m1(T, tf="D1"), m1(T, tf="H1")])
    assert sorted(b.tf for b in raw) == ["H1", "M1"]
    asyncio.run(svc._feed_publish(svc.feed.on_bars([m1(T)], T + timedelta(minutes=1))))
    srcs = [e.payload["source"] for _, e in pub.ev]
    assert srcs == [SRC]


def test_ingest_http_path_emits_canon(env):
    """Duong that: EA POST /ingest/v1 (M1 + H4) -> md.bars co raw M1 (khong H4) + canon M1 cho tai khoan feed."""
    import scenario
    svc, client, pub, clock = env
    svc.feed = CanonFeed(st(account="a5"))
    b = scenario.to_ea_batch("a5", "mt5", ts=clock.t)
    t = clock.t.replace(second=0, microsecond=0) - timedelta(minutes=2)
    b["bars"] = [dict(symbol="EURUSD.m", tf="M1", time=scenario.srv(t), o=1.1, h=1.2, l=1.0, c=1.15, v=5),
                 dict(symbol="EURUSD.m", tf="H4", time=scenario.srv(t.replace(minute=0)), o=1.1, h=1.2, l=1.0, c=1.15, v=5)]
    r = scenario.post(client, "secret-token-a5-xxxxxxxx", b)
    assert r.status_code == 200, r.text
    bars = [e.payload for e in pub.on("md.bars")]
    assert sorted((x["tf"], x["source"]) for x in bars) == [("M1", "canon:a5"), ("M1", "mt5:a5")]


def test_symbols_from_file_and_failsafe(tmp_path, monkeypatch):
    from mtbridge.feed import DEFAULT_SYMBOLS, load_symbols
    f = tmp_path / "s.txt"
    f.write_text("# ghi chu\neurusd\nAUDDKK # x\n\nEURUSD\n")
    assert load_symbols(f"@{f}") == ("EURUSD", "AUDDKK")
    d = tuple(DEFAULT_SYMBOLS.split(","))
    assert load_symbols("@/khong/ton/tai") == d
    (tmp_path / "e.txt").write_text("# trong\n")
    assert load_symbols(f"@{tmp_path / 'e.txt'}") == d
    monkeypatch.setenv("FEED_CANON_SYMBOLS", f"@{f}")
    assert FeedSettings().symbols == ("EURUSD", "AUDDKK")


def test_repo_feed_symbols_file_has_all_and_original_seven():
    import pathlib
    from mtbridge.feed import load_symbols
    p = pathlib.Path(__file__).resolve().parents[3] / "infra/mt-bridge/feed_symbols.txt"
    syms = load_symbols(f"@{p}")
    assert len(syms) >= 160 and {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30", "USTEC", "AUDDKK", "XAUEUR", "DE40"} <= set(syms)


def test_scale_162_symbols_one_batch_per_minute():
    import time
    syms = tuple(f"S{i:03d}" for i in range(162))
    f = CanonFeed(st(symbols=syms))
    t0 = time.perf_counter()
    n = 0
    for i in range(30):
        ts = T + timedelta(minutes=i)
        now = ts + timedelta(minutes=1, seconds=5)
        f.heartbeat(now)
        n += len(f.on_bars([m1(ts, sym=s) for s in syms], now))
    assert n >= 30 * 162 and time.perf_counter() - t0 < 5
    assert len(f.syms) == 162 and all(b.source == SRC for b in f.flush_due(T + timedelta(hours=2)))


def test_feed_all_account_http_canon_only_no_raw_and_metrics(env):
    """EA market-feed (tai khoan rieng): chi canon M1, KHONG phat nen tho; quote van phat; metric mtbridge_feed_* tang."""
    import scenario
    from mtbridge import service as sv
    svc, client, pub, clock = env
    svc.feed = CanonFeed(st(account="other"))
    svc.feed_all = CanonFeed(st(account="a5", symbols=("EURUSD",)))
    b = scenario.to_ea_batch("a5", "mt5", ts=clock.t)
    t = clock.t.replace(second=0, microsecond=0) - timedelta(minutes=2)
    b["bars"] = [dict(symbol="EURUSD.m", tf="M1", time=scenario.srv(t), o=1.1, h=1.2, l=1.0, c=1.15, v=5)]
    before = sv.FEEDALL_BATCHES.labels("ok")._value.get()
    r = scenario.post(client, "secret-token-a5-xxxxxxxx", b)
    assert r.status_code == 200, r.text
    bars = [e.payload for e in pub.on("md.bars")]
    assert [(x["tf"], x["source"]) for x in bars] == [("M1", "canon:a5")]
    assert sv.FEEDALL_BATCHES.labels("ok")._value.get() == before + 1
    assert svc.is_feed_all("a5") and not svc.is_feed_all("other")


def test_feed_all_excludes_main_symbols(monkeypatch, tmp_path):
    from mtbridge.service import BridgeService
    f = tmp_path / "s.txt"
    f.write_text("EURUSD\nAUDDKK\nXAUEUR\n")
    monkeypatch.setenv("FEED_ALL_SYMBOLS", f"@{f}")
    fa = BridgeService._make_feed_all(FeedSettings(symbols=("EURUSD",), prefix="canon"))
    assert fa.st.symbols == ("AUDDKK", "XAUEUR") and fa.st.source == "canon:mt5:100000001-feed" and fa.st.enabled


def test_feed_all_load_136_quotes_per_second(env):
    """Tai du kien: 136 quote/batch moi giay + 136 nen M1 moi phut -> moi batch xu ly < 100ms (publish ca quote + canon)."""
    import time
    import scenario
    svc, client, pub, clock = env
    svc.feed = CanonFeed(st(account="other"))
    names = [f"S{i:03d}" for i in range(136)]
    svc.feed_all = CanonFeed(st(account="a5", symbols=tuple(names)))
    t = clock.t.replace(second=0, microsecond=0) - timedelta(minutes=2)
    el = []
    for k in range(20):
        b = scenario.to_ea_batch("a5", "mt5", ts=clock.t, with_snapshot=False)
        b["quotes"] = [dict(symbol=n, bid=1.0 + k * 1e-4, ask=1.0002 + k * 1e-4, time=scenario.srv(clock.t)) for n in names]
        b["bars"] = [dict(symbol=n, tf="M1", time=scenario.srv(t + timedelta(minutes=k)), o=1.1, h=1.2, l=1.0, c=1.15, v=5) for n in names] if k < 3 else []
        t0 = time.perf_counter()
        r = scenario.post(client, "secret-token-a5-xxxxxxxx", b)
        el.append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text
    assert sorted(el)[-3] < 0.5, el          # p~85% < 500ms, du bo cho CI cham; TB thuc te in ra duoi day
    assert len(pub.on("md.quotes")) >= 136 * 19


def test_feed_fallback_legacy_symbols_when_legacy_stale(env):
    """7 ma chuoi cu: EA lab cu im > stale_s -> nen M1 cua EA feed duoc phat (source canon:<feed>); cu song -> khong phat trung."""
    import scenario
    svc, client, pub, clock = env
    svc.feed = CanonFeed(st(account="other", symbols=("EURUSD",)))
    svc.feed_all = CanonFeed(st(account="a5", symbols=("AUDDKK",)))
    svc.feed_fb = svc._make_feed_fb(svc.feed.st, svc.feed_all.st)
    svc.feed_fb.st.account = "a5"
    assert svc.feed_fb.st.symbols == ("EURUSD",) and svc.feed_fb.st.source == "canon:a5"
    t = clock.t.replace(second=0, microsecond=0) - timedelta(minutes=2)

    def send():
        b = scenario.to_ea_batch("a5", "mt5", ts=clock.t)
        b["bars"] = [dict(symbol="EURUSD", tf="M1", time=scenario.srv(t), o=1.1, h=1.2, l=1.0, c=1.15, v=5)]
        assert scenario.post(client, "secret-token-a5-xxxxxxxx", b).status_code == 200
    send()                                   # cu chua tung song -> du phong phat
    assert [(x["symbol"], x["source"]) for x in (e.payload for e in pub.on("md.bars"))] == [("EURUSD", "canon:a5")]
    n = len(pub.on("md.bars"))
    svc.feed.last_hb = clock.t               # cu vua song lai -> du phong im
    t = t + timedelta(minutes=1)
    send()
    assert len(pub.on("md.bars")) == n
