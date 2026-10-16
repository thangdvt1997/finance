"""Báo cáo theo tài khoản (account_reports_routes.py): client A không đọc báo cáo của B, client không thấy bản chưa phát hành,
client không ghi được; master/service ghi được (CSRF); staff theo phạm vi; 403 đồng nhất; không chuyển tiếp tham số lạ."""
import json
import urllib.parse

from api_gateway import account_reports_routes as ar
from test_authz import CLIENT_A, CLIENT_B, KEY, MASTER, hdr, make

SUP = hdr("support", "mt5:1", "us")
ANA = hdr("analyst", "mt5:1", "ua2")
AUD = hdr("auditor", "mt5:1", "uau")
CLIENT_NONE = hdr("client", "", "uc")

ITEMS = {
    "mt5:1": [{"account_id": "mt5:1", "kind": "daily", "period": "2026-10-11", "released": True},
              {"account_id": "mt5:1", "kind": "weekly", "period": "2026-10-11", "released": False}],
    "mt5:2": [{"account_id": "mt5:2", "kind": "daily", "period": "2026-10-11", "released": True}],
}


def fake_reporter(monkeypatch, calls):
    def _call(method, url, body=None, timeout=20):
        calls.append((method, url, body))
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = urllib.parse.unquote(u.path)
        if u.path == "/account-reports" and method == "GET":
            its = ITEMS.get(q.get("account_id"), [])
            if q.get("released_only") == "1":
                its = [i for i in its if i["released"]]
            return 200, json.dumps({"items": its}).encode(), {}
        if path.startswith("/account-reports/") and method == "GET":
            _, _, acc, period, ext = path.split("/")
            hit = [i for i in ITEMS.get(acc, []) if i["period"] == period and (not q.get("kind") or i["kind"] == q["kind"])
                   and (q.get("released_only") != "1" or i["released"])]
            if not hit:
                return 404, b'{"detail":"x"}', {}
            return 200, (b"<html>hello</html>" if ext == "html" else b"%PDF-1"), {"X-Report-Kind": hit[0]["kind"]}
        if u.path == "/account-reports/generate":
            return 200, json.dumps({"ok": True, "echo": json.loads(body)}).encode(), {}
        if u.path == "/account-reports/release":
            return 200, json.dumps({"ok": True, "echo": json.loads(body)}).encode(), {}
        if u.path == "/account-report-schedules":
            return 200, json.dumps({"schedules": [], "echo": json.loads(body) if body else None}).encode(), {}
        return 404, b"{}", {}
    monkeypatch.setattr(ar, "_call", _call)


def setup(monkeypatch):
    c, _ = make(monkeypatch)
    calls = []
    fake_reporter(monkeypatch, calls)
    return c, calls


def csrf(c, h):
    return {**h, "X-CSRF-Token": c.get("/v1/user/csrf", headers=h).json()["token"]}


def test_client_list_only_own_and_released(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        r = c.get("/v1/account-reports?account_id=mt5:1", headers=CLIENT_A)
        assert r.status_code == 200 and [i["kind"] for i in r.json()["items"]] == ["daily"]        # bản weekly chưa phát hành bị ẩn
        assert "released_only=1" in calls[-1][1]
        calls.clear()
        for bad in ("/v1/account-reports?account_id=mt5:2", "/v1/account-reports", "/v1/account-reports?account_id=",
                    "/v1/account-reports?account_id=mt5:1&account_id=mt5:2", "/v1/account-reports?account_id=mt5:2&account_id=mt5:1",
                    "/v1/account-reports?account_id=MT5:1", "/v1/account-reports?account_id=mt5:1%2F..%2Fmt5:2", "/v1/account-reports?account_id=mt5:3"):
            assert c.get(bad, headers=CLIENT_A).status_code == 403, bad
        assert c.get("/v1/account-reports?account_id=mt5:1", headers=CLIENT_NONE).status_code == 403
        assert not calls, calls                                         # không một request nào tới reporter
        assert c.get("/v1/account-reports?account_id=mt5:2", headers=CLIENT_B).status_code == 200


def test_client_file_idor_and_unreleased(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        ok = c.get("/v1/account-reports/mt5:1/2026-10-11/html", headers=CLIENT_A)
        assert ok.status_code == 200 and ok.text == "<html>hello</html>" and ok.headers["cache-control"] == "no-store"
        assert "default-src 'none'" in ok.headers["content-security-policy"] and "sandbox" in ok.headers["content-security-policy"]
        assert ok.headers["x-content-type-options"] == "nosniff"
        pdf = c.get("/v1/account-reports/mt5:1/2026-10-11/pdf", headers=CLIENT_A)
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and "attachment" in pdf.headers["content-disposition"]
        assert c.get("/v1/account-reports/mt5:1/2026-10-11/html?kind=daily", headers=CLIENT_A).status_code == 200
        # bản chưa phát hành (weekly) -> 404 với client, thấy được với master
        assert c.get("/v1/account-reports/mt5:1/2026-10-11/html?kind=weekly", headers=CLIENT_A).status_code == 404
        assert c.get("/v1/account-reports/mt5:1/2026-10-11/html?kind=weekly", headers=MASTER).status_code == 200
        calls.clear()
        for bad in ("/v1/account-reports/mt5:2/2026-10-11/html", "/v1/account-reports/mt5:2/2026-10-11/pdf", "/v1/account-reports/MT5:1/2026-10-11/html",
                    "/v1/account-reports/mt5:1%2F..%2Fmt5:2/2026-10-11/html", "/v1/account-reports/mt5:3/2026-10-11/html"):
            r = c.get(bad, headers=CLIENT_A)
            assert r.status_code in (403, 404), (bad, r.status_code)
        for bad in ("/v1/account-reports/mt5:2/2026-10-11/html", "/v1/account-reports/mt5:3/2026-10-11/pdf"):
            assert c.get(bad, headers=CLIENT_A).status_code == 403, bad
        assert not calls, calls
        for bad in ("/v1/account-reports/mt5:1/..%2f..%2fetc/html", "/v1/account-reports/mt5:1/2026-10-11/exe", "/v1/account-reports/mt5:1/2026-10-11/html?kind=../x",
                    "/v1/account-reports/mt5:1/2026-1-1/html"):
            assert c.get(bad, headers=CLIENT_A).status_code in (403, 404), bad
        assert not calls, calls


def test_client_cannot_write_or_read_schedules(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        h = csrf(c, CLIENT_A)
        body = {"account_id": "mt5:1", "kind": "daily"}
        assert c.post("/v1/account-reports/generate", json=body, headers=h).status_code == 403
        assert c.post("/v1/account-reports/release", json={"account_id": "mt5:1", "kind": "weekly", "period": "2026-10-11", "released": True}, headers=h).status_code == 403
        assert c.put("/v1/account-report-schedules", json={"schedules": []}, headers=h).status_code == 403
        assert c.get("/v1/account-report-schedules", headers=CLIENT_A).status_code == 403
        assert c.delete("/v1/account-reports/mt5:1/2026-10-11/html", headers=h).status_code in (403, 405)
        assert c.post("/v1/account-reports/mt5:1/2026-10-11/html", headers=h).status_code in (403, 404, 405)
        assert not calls, calls


def test_master_write_needs_csrf_and_filters_body(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        gen = {"account_id": "mt5:1", "kind": "daily", "release": True, "evil": "x"}
        assert c.post("/v1/account-reports/generate", json=gen, headers=MASTER).status_code == 403         # thiếu CSRF
        h = csrf(c, MASTER)
        r = c.post("/v1/account-reports/generate", json=gen, headers=h)
        assert r.status_code == 200 and r.json()["echo"] == {"account_id": "mt5:1", "kind": "daily", "release": True}   # tham số lạ bị bỏ
        assert c.post("/v1/account-reports/generate", content=b"x", headers={**h, "Content-Type": "text/plain"}).status_code == 415
        assert c.post("/v1/account-reports/generate", content=b"[1]", headers={**h, "Content-Type": "application/json"}).status_code == 400
        assert c.post("/v1/account-reports/generate", json=gen, headers={**h, "Origin": "https://evil.example", "Host": "x"}).status_code == 403
        assert c.post("/v1/account-reports/release", json={"account_id": "mt5:2", "kind": "daily", "period": "2026-10-11", "released": False}, headers=h).status_code == 200
        assert c.get("/v1/account-report-schedules", headers=MASTER).status_code == 200
        assert c.put("/v1/account-report-schedules", json={"schedules": [{"scope": {"type": "all"}, "kind": "daily", "hour": 7}]}, headers=h).status_code == 200
        assert c.put("/v1/account-report-schedules", json={"schedules": []}, headers=MASTER).status_code == 403
        assert c.get("/v1/account-reports?account_id=mt5:2", headers=MASTER).json()["items"][0]["account_id"] == "mt5:2"
        assert c.get("/v1/account-reports", headers=MASTER).status_code == 422
        assert "released_only=0" in [u for _, u, _ in calls if "released_only" in u][-1]


def test_service_key_can_write_without_csrf(monkeypatch):
    c, _ = setup(monkeypatch)
    with c:
        assert c.post("/v1/account-reports/generate", json={"account_id": "mt5:1", "kind": "weekly"}, headers=KEY).status_code == 200
        assert c.get("/v1/account-reports?account_id=mt5:1", headers=KEY).status_code == 200


def test_staff_scope_and_roles(monkeypatch):
    c, calls = setup(monkeypatch)
    with c:
        sup = c.get("/v1/account-reports?account_id=mt5:1", headers=SUP)
        assert sup.status_code == 200 and [i["kind"] for i in sup.json()["items"]] == ["daily"]      # support: chỉ bản đã phát hành
        ana = c.get("/v1/account-reports?account_id=mt5:1", headers=ANA)
        assert ana.status_code == 200 and len(ana.json()["items"]) == 2                              # analyst (report.read): thấy cả bản chưa phát hành
        assert c.get("/v1/account-reports/mt5:1/2026-10-11/html?kind=weekly", headers=ANA).status_code == 200
        assert c.get("/v1/account-reports/mt5:1/2026-10-11/html?kind=weekly", headers=SUP).status_code == 404
        for h in (SUP, ANA, AUD):
            assert c.get("/v1/account-reports?account_id=mt5:2", headers=h).status_code == 403
            assert c.post("/v1/account-reports/generate", json={"account_id": "mt5:1", "kind": "daily"}, headers={**h, "X-CSRF-Token": "x"}).status_code == 403
            assert c.get("/v1/account-report-schedules", headers=h).status_code == 403
        assert c.get("/v1/account-reports?account_id=mt5:1", headers=AUD).status_code == 403          # auditor không có dữ liệu tài khoản


def test_uniform_403_no_existence_oracle(monkeypatch):
    c, _ = setup(monkeypatch)
    with c:
        a = c.get("/v1/account-reports/mt5:2/2026-10-11/html", headers=CLIENT_A)            # tồn tại, của người khác
        b = c.get("/v1/account-reports/mt5:999/2099-01-01/html", headers=CLIENT_A)           # không tồn tại
        assert a.status_code == b.status_code == 403 and a.json() == b.json()


def test_upstream_down_is_502(monkeypatch):
    c, _ = setup(monkeypatch)

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(ar, "_call", boom)
    with c:
        assert c.get("/v1/account-reports?account_id=mt5:1", headers=CLIENT_A).status_code == 502
