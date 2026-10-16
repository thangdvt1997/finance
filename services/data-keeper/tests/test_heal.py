import asyncio
import time
from types import SimpleNamespace

from data_keeper import heal as H


def mx(broken=(), closed=(), ok=("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")):
    m = {s: {"M1": {"status": "OK"}} for s in ok}
    m.update({s: {"M1": {"status": "BROKEN"}} for s in broken})
    m.update({s: {"M1": {"status": "CLOSED"}} for s in closed})
    return m


def cfg(tmp, **kw):
    d = dict(dry_run=False, feed_list_path=str(tmp / "fs.txt"), plan_path=str(tmp / "plan.json"), broken_min_age_s=0, ntfy_url="", alert_webhook="")
    d.update(kw)
    return H.HealConfig(**d)


def run(c, m, conf, st, notify=None, http=None):
    ctx = SimpleNamespace(http=http)
    return asyncio.run(H.heal_cycle(ctx, m, conf, st, notify))


def test_closed_never_alerts(tmp_path):
    sent = []

    async def n(k, l, t):
        sent.append(k); return True
    acts = run(None, mx(closed=["DE40", "UK100", "FR40", "JP225"]), cfg(tmp_path), H.HealState(), n)
    assert acts == [] and not sent


def test_dry_run_no_side_effects(tmp_path):
    c = cfg(tmp_path, dry_run=True)
    acts = run(None, mx(broken=["A", "B", "C", "D"]), c, H.HealState())
    assert {a["kind"] for a in acts} >= {"resync_symbols", "restart_feed", "alert"}
    assert all(a["status"] in ("dry_run", "ok", "problem") for a in acts)
    assert not (tmp_path / "fs.txt").exists()


def test_resync_writes_list_and_alert_dedupe(tmp_path):
    sent = []

    async def n(k, l, t):
        sent.append(k); return True
    st, c, m = H.HealState(), cfg(tmp_path), mx(broken=["A", "B", "C", "D"])
    run(None, m, c, st, n); run(None, m, c, st, n)
    assert "A" in (tmp_path / "fs.txt").read_text().split()
    assert sent == ["feed_wide"]                      # cooldown dedupe


def test_restart_rate_limit(tmp_path):
    st, c = H.HealState(), cfg(tmp_path, restart_cooldown_s=0, max_restarts_per_hour=1)
    st.restarts.append(time.time())
    acts = run(None, mx(broken=["A", "B", "C", "D"]), c, st)
    r = [a for a in acts if a["kind"] == "restart_feed"][0]
    assert r["status"] == "skipped"


def test_below_threshold_no_action(tmp_path):
    assert run(None, mx(broken=["A"]), cfg(tmp_path), H.HealState()) == []


def test_container_guard():
    d = H.DockerAPI(H.HealConfig(), None)
    try:
        asyncio.run(d.inspect("fbauto"))
        assert False
    except PermissionError:
        pass


def test_restart_without_write_proxy_is_planned(tmp_path):
    class R:
        status_code = 200
        content = b""
        def json(self): return {"State": {"Running": True}}
        def raise_for_status(self): pass
    class Http:
        async def get(self, *a, **k): return R()
        async def post(self, *a, **k): raise AssertionError("khong duoc POST")
    acts = run(None, mx(broken=["A", "B", "C", "D"]), cfg(tmp_path), H.HealState(), http=Http())
    assert [a for a in acts if a["kind"] == "restart_feed"][0]["status"] == "planned"


def test_container_health_and_allow_url():
    c = H.HealConfig()
    assert not H.container_health({"State": {"Running": False}}, None, "", c)["ok"]
    assert H.allow_url_ok("x post-start done y") is True and H.allow_url_ok("abc") is False and H.allow_url_ok("") is None


def test_failover_marks_stale(tmp_path):
    st, c = H.HealState(), cfg(tmp_path, failover_after_s=0)
    acts = run(None, mx(broken=["A", "B", "C", "D"]), c, st)
    assert any(a["kind"] == "failover_plan" for a in acts) and (tmp_path / "plan.json").exists()


def test_ticking_without_bars_is_not_silent(tmp_path):
    """Ma con tick tuoi nhung thieu nen M1: canh bao 'bars_missing' rieng, KHONG resync/restart (feed khoe)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    m = mx()
    for s in ("US30", "US500", "USTEC"):
        m[s] = {"M1": {"status": "BROKEN", "last_tick": now}}
    sent = []

    async def n(k, l, t):
        sent.append((k, t)); return True
    acts = run(None, m, cfg(tmp_path), H.HealState(), n)
    assert not any(a["kind"] in ("resync_symbols", "restart_feed") for a in acts)
    assert sent and sent[0][0] == "bars_missing" and "im lang" not in sent[0][1]
