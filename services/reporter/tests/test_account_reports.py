"""Báo cáo THEO TÀI KHOẢN: kỳ, dựng/render, lưu trữ (path traversal), lịch, API, không lộ tên nguồn (HTML + PDF)."""
from __future__ import annotations

import asyncio
import io
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import NOW
from reporter import account_report as ar
from reporter.account_reports import build_router  # noqa: F401
from reporter.account_service import AccountReporter
from reporter.account_store import AccountStore, ScheduleStore, account_dir_name, clean_schedule, valid_account, valid_name
from reporter.app import create_app
from reporter.collect import Gateway
from reporter.config import Settings
from reporter.render import render_account_html, render_pdf

BANNED = ("dukascopy", "yahoo", "frankfurter", "twelvedata", "cafef", "vietstock", "reuters", "forexfactory", "myfxbook", "mql5", "oanda", "ccxt")
ACC = "mt5:99000123"
XSS = '<script>alert("x")</script>'


def _eq_series():
    base = datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc)
    pts = []
    for i in range(30):
        e = 10000 + 15 * i - (60 if 10 < i < 16 else 0)
        pts.append({"ts": (base + timedelta(minutes=30 * i)).isoformat(), "equity": float(e), "balance": 10000.0, "margin": 100.0})
    return pts


def _risk(name=None):
    return {"account": {"account_id": ACC, "kind": "mt", "platform": "mt5", "currency": "USD", "equity": 10435.0, "balance": 10000.0,
                        "name": name or "Khách A", "ts": "2026-10-12T00:00:00+00:00"},
            "margin": {"margin_level_pct": 850.5, "margin_used": 120.0, "free_margin": 10300.0, "status": "ok"},
            "exposure": {"leverage_gross": 1.8, "positions": 2, "max_ccy_conc_pct": 35.0,
                         "by_symbol": [{"symbol": "EURUSD", "net_lots": 0.3, "net_value": 3000.0, "pnl": 12.5}]},
            "drawdown": {"available": True, "day": {"pnl_pct": 0.4}, "dd_from_peak_pct": -0.5, "max_dd_pct": -1.2},
            "var": {"available": True, "hist": {"95": {"var_pct": -1.1}, "es": {"es_pct": -1.6}}},
            "budget": {"status": "warn", "items": [{"key": "lev", "label": "Đòn bẩy", "unit": "x", "value": 1.8, "limit": 2.0, "used_pct": 90.0, "status": "warn"}]},
            "warnings": ["Nguồn: dukascopy lệch giá", XSS]}


def _journal(n=12):
    if not n:
        return {"summary": {"n": 0}}
    return {"summary": {"n": n, "wins": 7, "losses": 5, "breakeven": 0, "win_rate": 0.58, "net": 210.5, "profit_factor": 1.8, "expectancy": 17.5,
                        "avg_win": 50.0, "avg_loss": -30.0, "best": 120.0, "worst": -60.0},
            "streaks": {"max_loss_streak": 3},
            "groups": {"symbol": [{"key": "EURUSD", "n": 8, "net": 150.0, "win_rate": 0.6, "profit_factor": 2.0},
                                  {"key": "XAUUSD", "n": 4, "net": -20.0, "win_rate": 0.25, "profit_factor": 0.7}]}}


def _compliance():
    return {"account_id": ACC, "rules": [
        {"rule_name": "Giới hạn lỗ ngày", "status": "yellow", "usage_pct": 82.0, "value": 2.4, "limit": 3.0, "unit": "%", "headroom": 0.6},
        {"rule_name": XSS + " tuân theo myfxbook", "status": "red", "usage_pct": 120.0, "value": 6, "limit": 5, "unit": "lệnh", "headroom": -1},
        {"rule_name": "Chưa đo", "status": "na"}]}


def make_gw(cfg, equity=True, risk=True, journal=12, risk_name=None):
    def h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == f"/v1/risk/accounts/{ACC}" and risk:
            return httpx.Response(200, json=_risk(risk_name))
        if p == "/v1/equity-history" and equity and req.url.params.get("account_id") == ACC:
            return httpx.Response(200, json=_eq_series())
        if p == f"/v1/journal/{ACC}/summary" and journal is not None:
            return httpx.Response(200, json=_journal(journal))
        return httpx.Response(404, json={"detail": "x"})
    return Gateway(cfg, httpx.AsyncClient(transport=httpx.MockTransport(h), base_url="http://gw"))


def make_auth(rules=True, scope=None, calls=None):
    def h(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((req.url.path, dict(req.url.params), req.headers.get("authorization")))
        if req.headers.get("authorization") != "Bearer tok":
            return httpx.Response(401, json={})
        if "/compliance" in req.url.path and rules:
            return httpx.Response(200, json=_compliance())
        if req.url.path == "/internal/fleet/scope-accounts" and scope is not None:
            return httpx.Response(200, json={"accounts": scope})
        return httpx.Response(503, json={})
    return ar.AuthClient("http://auth", "tok", httpx.AsyncClient(transport=httpx.MockTransport(h), base_url="http://auth", headers={"Authorization": "Bearer tok"}))


@pytest.fixture
def acfg(tmp_path):
    return Settings(data_dir=tmp_path, api_key="k", internal_token="tok", tick_seconds=0.01)


def fake_pdf(html: str) -> bytes:
    return b"%PDF-fake"


def mk(acfg, **kw):
    gw = kw.pop("gw", None) or make_gw(acfg)
    auth = kw.pop("auth", None)
    return AccountReporter(acfg, gateway=gw, auth=auth if auth is not None else make_auth(), pdf=kw.pop("pdf", fake_pdf), clock=lambda: NOW, **kw)


# ---------------- kỳ ----------------
def test_period_logic():
    tz = "Asia/Ho_Chi_Minh"   # NOW = Thứ hai 12/10/2026 07:00 VN
    assert ar.last_period("daily", NOW, tz).isoformat() == "2026-10-11"
    assert ar.last_period("weekly", NOW, tz).isoformat() == "2026-10-11"      # Chủ nhật vừa qua
    assert ar.last_period("monthly", NOW, tz).isoformat() == "2026-09-30"
    assert ar.due_period("daily", 6, NOW, tz) == "2026-10-11"                   # 06:00 đã qua
    assert ar.due_period("daily", 8, NOW, tz) == "2026-10-10"                   # chưa tới 08:00 -> kỳ trước
    assert ar.due_period("weekly", 9, NOW, tz) == "2026-10-04"
    assert ar.due_period("monthly", 7, NOW, tz) == "2026-09-30"
    sun = datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc)                       # Chủ nhật: kỳ tuần chưa kết thúc
    assert ar.last_period("weekly", sun, tz).isoformat() == "2026-10-11"
    s, e = ar.window("weekly", "2026-10-11", tz)
    assert (s.date().isoformat(), e.date().isoformat()) == ("2026-10-05", "2026-10-12")
    s, e = ar.window("monthly", "2026-09-30", tz)
    assert (s.date().isoformat(), e.date().isoformat()) == ("2026-09-01", "2026-10-01")
    s, e = ar.window("daily", "2026-10-11", tz)
    assert e - s == timedelta(days=1)


# ---------------- dựng / render ----------------
async def _html(acfg, kind="daily", **kw):
    raw = await ar.collect_account(acfg, kw.pop("gw", None) or make_gw(acfg), kw.pop("auth", None) or make_auth(), ACC, kind, "2026-10-11")
    ctx = ar.build_account(kind, "2026-10-11", ACC, "Khách A", raw, acfg, NOW)
    return ctx, render_account_html(ctx)


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
async def test_build_render_all_sections(acfg, kind):
    ctx, html = await _html(acfg, kind)
    assert ctx["ok"] == ar.ORDER and ctx["fail"] == []
    for s in ("Hiệu suất", "Rủi ro", "Nhật ký giao dịch", "Tuân thủ luật", "Đường equity", "Giới hạn lỗ ngày", "READ-ONLY"):
        assert s in html
    assert ACC in html and "<svg" in html
    assert ctx["kind_vi"] in html and ("Báo cáo " + {"daily": "ngày", "weekly": "tuần", "monthly": "tháng"}[kind]) in html
    p = ctx["sections"]["performance"]
    assert p["pnl_up"] and p["max_dd"] != "—"


async def test_html_escapes_xss_and_scrubs_sources(acfg):
    ctx, html = await _html(acfg)
    assert "<script>" not in html and "&lt;script&gt;" in html
    low = html.lower()
    text = re.sub(r"<[^>]+>", " ", low)
    for w in BANNED:
        assert w not in low and w not in text and w not in str(ctx).lower(), w


async def test_compliance_missing_is_polite_not_error(acfg):
    _, html = await _html(acfg, auth=make_auth(rules=False))
    assert "Chưa có dữ liệu" in html and "Giới hạn lỗ ngày" not in html
    raw = await ar.collect_account(acfg, make_gw(acfg), None, ACC, "daily", "2026-10-11")      # không có token/auth
    ctx = ar.build_account("daily", "2026-10-11", ACC, None, raw, acfg, NOW)
    assert not ctx["sections"]["compliance"]["ok"] and "compliance" not in ctx["fail"]         # tuỳ chọn: không làm 'degraded'
    assert ctx["sections"]["performance"]["ok"]


async def test_no_trades_and_failed_sections(acfg):
    ctx, html = await _html(acfg, gw=make_gw(acfg, journal=0, risk=False))
    assert ctx["sections"]["journal"]["empty"] and "Không có lệnh đã đóng" in html
    assert "risk" in ctx["fail"] and "Chưa có dữ liệu" in html


def test_pdf_has_no_source_names(acfg):
    pypdf = pytest.importorskip("pypdf")
    ctx, html = asyncio.run(_html(acfg))
    try:
        pdf = render_pdf(html)
    except OSError as e:
        pytest.skip(f"thiếu thư viện hệ thống cho WeasyPrint: {e}")
    txt = "".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf)).pages).lower()
    assert txt and "báo cáo" in txt
    for w in BANNED:
        assert w not in txt, w


# ---------------- lưu trữ / path traversal ----------------
@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b", "x" * 65, "a b", "a\x00b", "é", None, 5])
def test_invalid_account_ids(bad):
    assert not valid_account(bad)
    with pytest.raises(ValueError):
        account_dir_name(bad)


def test_dir_name_is_encoded_and_unique():
    d1, d2 = account_dir_name("mt5:1"), account_dir_name("mt5_1")
    assert d1 != d2 and d1.startswith("a_") and "/" not in d1 and ":" not in d1
    assert re.fullmatch(r"a_[A-Za-z0-9_\-]+_[0-9a-f]{10}", account_dir_name("..."))


def test_store_paths_stay_inside_root(tmp_path):
    st = AccountStore(tmp_path)
    p = st.path("..", "daily", "2026-10-11", "html")     # ".." hợp lệ theo regex nhưng bị mã hoá -> nằm trong root
    assert st.root.resolve() in p.resolve().parents
    for args in [("a", "daily", "2026-10-11", "exe"), ("a", "../daily", "2026-10-11", "html"), ("a", "daily", "../../etc", "html"),
                 ("a", "yearly", "2026-10-11", "html"), ("a/b", "daily", "2026-10-11", "html")]:
        assert not valid_name(*args)
        with pytest.raises(ValueError):
            st.path(*args)


def test_store_save_release_prune(tmp_path):
    st = AccountStore(tmp_path)
    e = st.save("A1", "daily", "2026-10-11", "<html>x</html>", b"%PDF", ["performance"], [], False)
    assert e["released"] is False and e["status"] == "ok" and st.exists("A1", "daily", "2026-10-11")
    assert st.items("A1", released_only=True) == []
    assert st.set_released("A1", "daily", "2026-10-11", True)["released"] is True
    assert len(st.items("A1", released_only=True)) == 1
    assert st.set_released("A1", "daily", "1999-01-01", True) is None
    assert st.items("B2") == []            # tài khoản khác không thấy
    for d in range(70):
        st.save("A1", "daily", (datetime(2026, 1, 1) + timedelta(days=d)).date().isoformat(), "h", None, [], ["pdf"], False)
    assert len([i for i in st.items("A1") if i["kind"] == "daily"]) == 60
    assert st.find("A1", "daily", "2026-01-01") is None and not st.path("A1", "daily", "2026-01-01", "html").exists()


# ---------------- sinh báo cáo ----------------
async def test_generate_default_unreleased_and_release_flag(acfg):
    rep = mk(acfg)
    e = await rep.generate(ACC, "daily")
    assert e["period"] == "2026-10-11" and e["released"] is False and e["status"] == "ok"
    e2 = await rep.generate(ACC, "weekly", release=True)
    assert e2["released"] is True and rep.store.path(ACC, "weekly", e2["period"], "html").is_file()
    again = await rep.generate(ACC, "daily", force=False)
    assert again["skipped"] == "exists"


async def test_generate_skips_account_without_data(acfg):
    rep = mk(acfg, gw=make_gw(acfg, equity=False, risk=False, journal=None))
    out = await rep.generate(ACC, "daily")
    assert out["skipped"] == "no_data" and rep.store.items(ACC) == []


async def test_generate_pdf_failure_is_degraded(acfg):
    def boom(_):
        raise RuntimeError("x")
    e = await mk(acfg, pdf=boom).generate(ACC, "daily")
    assert e["status"] == "degraded" and "pdf" in e["sections_fail"] and not e["has_pdf"]


async def test_no_duplicate_inflight_and_concurrency_limit(acfg):
    running, peak = 0, 0

    def slow_pdf(html):
        nonlocal running, peak
        import time
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1
        return b"%PDF"
    rep = mk(acfg, pdf=slow_pdf)
    same = await asyncio.gather(rep.generate(ACC, "daily"), rep.generate(ACC, "daily"))
    assert sorted(x.get("skipped", "") for x in same) == ["", "running"]
    peak = 0
    accs = [f"mt5:{i}" for i in range(8)]

    def gw_all(req):
        p = req.url.path
        if p.startswith("/v1/risk/accounts/"):
            return httpx.Response(200, json=_risk())
        return httpx.Response(404, json={})
    rep2 = AccountReporter(acfg, gateway=Gateway(acfg, httpx.AsyncClient(transport=httpx.MockTransport(gw_all), base_url="http://gw")),
                           auth=make_auth(), pdf=slow_pdf, clock=lambda: NOW)
    await asyncio.gather(*[rep2.generate(a, "daily") for a in accs])
    assert 1 <= peak <= 2


# ---------------- lịch ----------------
def test_schedule_validation():
    ok = clean_schedule({"scope": {"type": "group", "ref": "Nhóm VIP"}, "kind": "weekly", "hour": 7, "auto_release": True})
    assert ok["enabled"] is True and ok["auto_release"] is True and len(ok["schedule_id"]) == 16
    assert clean_schedule({"scope": {"type": "all", "ref": "zzz"}, "kind": "daily", "hour": 0})["scope"]["ref"] is None
    for bad in [{"scope": {"type": "x", "ref": "a"}, "kind": "daily", "hour": 1}, {"scope": {"type": "account", "ref": "../x"}, "kind": "daily", "hour": 1},
                {"scope": {"type": "tag", "ref": "<b>"}, "kind": "daily", "hour": 1}, {"scope": {"type": "all"}, "kind": "yearly", "hour": 1},
                {"scope": {"type": "all"}, "kind": "daily", "hour": 24}, {"scope": {"type": "all"}, "kind": "daily", "hour": True},
                {"scope": {"type": "all"}, "kind": "daily", "hour": 1, "schedule_id": "../../x"}, "str", None]:
        with pytest.raises(ValueError):
            clean_schedule(bad)


def test_schedule_store_roundtrip(tmp_path):
    ss = ScheduleStore(tmp_path)
    assert ss.list() == []
    out = ss.replace([{"scope": {"type": "all"}, "kind": "daily", "hour": 6}])
    sid = out[0]["schedule_id"]
    assert ss.list() == out
    ss.upsert({**out[0], "hour": 9})
    assert ss.list()[0]["hour"] == 9 and len(ss.list()) == 1
    with pytest.raises(ValueError):
        ss.replace([out[0], out[0]])
    assert ss.delete(sid) and not ss.delete(sid) and ss.list() == []


async def test_tick_generates_for_scope_accounts_once(acfg):
    calls: list = []
    scope = [{"account_id": ACC, "label": "Khách A", "groups": ["VIP"]}, {"account_id": "mt5:77", "label": "Không dữ liệu", "groups": ["VIP"]}]
    rep = mk(acfg, auth=make_auth(scope=scope, calls=calls))
    rep.schedules.replace([{"scope": {"type": "group", "ref": "VIP"}, "kind": "daily", "hour": 6, "auto_release": True},
                           {"scope": {"type": "all"}, "kind": "weekly", "hour": 6, "enabled": False}])
    assert await rep.tick(NOW) == 1
    got = rep.store.items(ACC)
    assert len(got) == 1 and got[0]["released"] is True and got[0]["kind"] == "daily" and got[0]["period"] == "2026-10-11"
    assert rep.store.items("mt5:77") == []                       # không có dữ liệu -> bỏ qua
    scope_calls = [c for c in calls if c[0] == "/internal/fleet/scope-accounts"]
    assert scope_calls and scope_calls[0][1] == {"type": "group", "ref": "VIP"} and scope_calls[0][2] == "Bearer tok"
    n_before = len(calls)
    assert await rep.tick(NOW + timedelta(minutes=1)) == 0       # không chạy lại trong cùng kỳ
    assert len(calls) == n_before
    assert not any("weekly" == i["kind"] for i in rep.store.items(ACC))   # lịch tắt không chạy


async def test_tick_without_auth_token_does_not_crash_and_account_scope_works(acfg):
    cfg2 = Settings(data_dir=acfg.data_dir, api_key="k", internal_token="")
    rep = AccountReporter(cfg2, gateway=make_gw(cfg2), pdf=fake_pdf, clock=lambda: NOW)
    rep.schedules.replace([{"scope": {"type": "group", "ref": "VIP"}, "kind": "daily", "hour": 6},
                           {"scope": {"type": "account", "ref": ACC}, "kind": "daily", "hour": 6}])
    await rep.tick(NOW)                                          # group không phân giải được (không token) nhưng không làm hỏng lịch kia
    assert len(rep.store.items(ACC)) == 1
    assert "compliance" not in rep.store.items(ACC)[0]["sections_fail"]


# ---------------- API ----------------
class _Dummy:
    pass


def client(acfg):
    app = create_app(acfg, reporter=_Dummy(), run_scheduler=False, account_reporter=mk(acfg))
    return TestClient(app)


def test_api_generate_release_get_and_released_only(acfg):
    with client(acfg) as c:
        r = c.post("/account-reports/generate", json={"account_id": ACC, "kind": "daily"})
        assert r.status_code == 200 and r.json()["released"] is False
        per = r.json()["period"]
        assert c.get("/account-reports", params={"account_id": ACC}).json()["items"][0]["period"] == per
        assert c.get("/account-reports", params={"account_id": ACC, "released_only": 1}).json()["items"] == []
        assert c.get(f"/account-reports/{ACC}/{per}/html", params={"released_only": 1}).status_code == 404
        h = c.get(f"/account-reports/{ACC}/{per}/html")
        assert h.status_code == 200 and "text/html" in h.headers["content-type"] and h.headers["x-content-type-options"] == "nosniff"
        assert c.get(f"/account-reports/{ACC}/{per}/pdf").headers["content-type"].startswith("application/pdf")
        rel = c.post("/account-reports/release", json={"account_id": ACC, "kind": "daily", "period": per, "released": True})
        assert rel.status_code == 200 and rel.json()["released"] is True
        assert c.get(f"/account-reports/{ACC}/{per}/html", params={"released_only": 1, "kind": "daily"}).status_code == 200
        assert c.get(f"/account-reports/{ACC}/{per}/html", params={"kind": "weekly"}).status_code == 404
        assert c.post("/account-reports/release", json={"account_id": ACC, "kind": "daily", "period": "2000-01-01", "released": True}).status_code == 404


def test_api_rejects_bad_input_and_traversal(acfg):
    with client(acfg) as c:
        assert c.post("/account-reports/generate", json={"account_id": "../x", "kind": "daily"}).status_code == 422
        assert c.post("/account-reports/generate", json={"account_id": ACC, "kind": "yearly"}).status_code == 422
        assert c.post("/account-reports/generate", json={"account_id": ACC, "kind": "daily", "period": "2026-13-45"}).status_code == 422
        assert c.get("/account-reports", params={"account_id": "../.."}).status_code == 422
        for path in ["/account-reports/..%2f..%2fetc/2026-10-11/html", "/account-reports/%2e%2e/2026-10-11/html", f"/account-reports/{ACC}/..%2f..%2f/html",
                     f"/account-reports/{ACC}/2026-10-11/exe", f"/account-reports/{ACC}/2026-10-11/html%00"]:
            assert c.get(path).status_code in (404, 422)
        assert c.post("/account-reports/generate", json={"account_id": "mt5:404", "kind": "daily"}).status_code == 409   # không có dữ liệu


def test_api_schedules_crud(acfg):
    with client(acfg) as c:
        assert c.get("/account-report-schedules").json() == {"schedules": []}
        r = c.put("/account-report-schedules", json={"schedules": [{"scope": {"type": "tag", "ref": "vip"}, "kind": "monthly", "hour": 8}]})
        assert r.status_code == 200
        sid = r.json()["schedules"][0]["schedule_id"]
        assert c.put("/account-report-schedules", json={"schedules": [{"scope": {"type": "x"}, "kind": "daily", "hour": 1}]}).status_code == 422
        assert c.post("/account-report-schedules", json={"schedule_id": sid, "scope": {"type": "all"}, "kind": "weekly", "hour": 5}).json()["kind"] == "weekly"
        assert c.delete(f"/account-report-schedules/{sid}").status_code == 200 and c.delete(f"/account-report-schedules/{sid}").status_code == 404


def test_api_purge_removes_only_that_account(acfg):
    with client(acfg) as c:
        rep = c.app.state.account_reporter
        rep.store.save("A9", "daily", "2026-10-11", "h", b"%PDF", [], [], True)
        rep.store.save("B9", "daily", "2026-10-11", "h", b"%PDF", [], [], True)
        assert c.delete("/account-reports/A9").json() == {"deleted": 1}
        assert rep.store.items("A9") == [] and not rep.store.adir("A9").exists() and len(rep.store.items("B9")) == 1
        assert c.delete("/account-reports/../x").status_code in (404, 422)
        assert c.delete("/account-reports/A9").json() == {"deleted": 0}
