"""/v1/ai-trading/class/*: AI Training Class = master + vai expert; client/analyst/support/auditor/anon -> 403; CSRF/Origin; danh sách trắng đường dẫn; header danh tính do gateway đặt."""
import io
import json

from fastapi.testclient import TestClient

from api_gateway import class_routes
from api_gateway.app import create_app
from api_gateway.config import GatewaySettings
from api_gateway.repo import InMemoryRepo

KEY = {"X-API-Key": "tok1"}
SECRET = "trust-secret-xyz"
JH = {"Content-Type": "application/json"}
RID = "a" * 32


def hdr(role, uid="u1", accs=""):
    return {**KEY, "X-User-Id": uid, "X-Role": role, "X-Auth-Secret": SECRET, "X-Accounts": accs}


def client():
    return TestClient(create_app(GatewaySettings(api_tokens=("tok1",), auth_disabled=False, auth_trust_secret=SECRET), repo=InMemoryRepo(), redis=object()))


class FakeResp:
    def __init__(self, status=200, body=b"{}", ctype="application/json"):
        self.status, self.code = status, status
        self.headers = {"Content-Type": ctype}
        self.f = io.BytesIO(body)

    def read(self, n=-1):
        return self.f.read(n)

    def readline(self):
        return self.f.readline()

    def close(self):
        pass


def fake(seen, resp=None):
    def f(method, sub, qs, body, idh):
        seen.append((method, sub, qs, body, idh))
        return resp() if resp else FakeResp(200, json.dumps({"ok": True, "sub": sub}).encode())
    return f


def csrf(c, role="expert", uid="u1"):
    return {**hdr(role, uid), **JH, "X-CSRF-Token": c.get("/v1/user/csrf", headers=hdr(role, uid)).json()["token"]}


def _patch(monkeypatch, seen, resp=None):
    import api_gateway.class_routes as cr

    def fake_urlopen(req, timeout=0):
        seen.append(req)
        for k, v in req.header_items():
            v.encode('latin-1')      # như http.client: header non-ASCII sẽ lỗi
        for k, v in req.header_items():
            v.encode('latin-1')      # như http.client: header non-ASCII sẽ lỗi
        return resp() if resp else FakeResp(200, json.dumps({"ok": True}).encode())
    monkeypatch.setattr(cr.urllib.request, "urlopen", fake_urlopen)


def test_roles_denied(monkeypatch):
    seen = []
    c = client()
    _patch(monkeypatch, seen)
    for role in ("client", "analyst", "support", "auditor"):
        h = {**hdr(role, "u9", "mt5:1"), **JH}
        assert c.get("/v1/ai-trading/class/rooms", headers=h).status_code == 403
        assert c.post("/v1/ai-trading/class/rooms", content=b'{"title":"abc"}', headers=h).status_code == 403
    assert c.get("/v1/ai-trading/class/rooms").status_code in (401, 403)
    assert c.get("/v1/ai-trading/class/rooms", headers={**KEY, "X-User-Id": "u1", "X-Role": "expert"}).status_code == 403    # thiếu X-Auth-Secret = giả mạo
    assert not seen


def test_expert_proxy_identity_not_forgeable(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    r = c.get("/v1/ai-trading/class/rooms", headers={**hdr("expert", "exp-1"), "X-Class-Role": "master", "X-Class-User": "admin"})
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    h = {k.lower(): v for k, v in seen[-1].header_items()}
    assert h["x-class-role"] == "expert" and h["x-class-user"] == "exp-1"
    assert seen[-1].full_url.endswith("/class/rooms") and seen[-1].get_method() == "GET"
    r = c.get("/v1/ai-trading/class/rooms", headers=hdr("master", "adm"))
    assert {k.lower(): v for k, v in seen[-1].header_items()}["x-class-role"] == "master"
    # whitelist đường dẫn
    for bad in ("rooms/zzz", f"rooms/{RID}/../../x", "rooms/" + "A" * 32, f"rooms/{RID}/secret", "admin", f"rooms/{RID}/media/../../etc"):
        assert c.get("/v1/ai-trading/class/" + bad, headers=hdr("expert")).status_code in (403, 404), bad
    n = len(seen)
    assert c.get(f"/v1/ai-trading/class/rooms/{RID}", headers=hdr("expert")).status_code == 200 and len(seen) == n + 1


def test_expert_writes_csrf_origin_limits(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    e = {**hdr("expert"), **JH}
    u = f"/v1/ai-trading/class/rooms/{RID}/messages"
    assert c.post(u, content=b'{"text":"x"}', headers=e).status_code == 403                                  # thiếu CSRF
    h = csrf(c)
    assert c.post(u, content=b'{"text":"x"}', headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert c.post(u, content=b'{"text":"x"}', headers={**h, "Content-Type": "text/plain"}).status_code == 415
    assert c.post(u, content=b"[1]", headers=h).status_code == 400
    assert c.post(u, content=b'{"text":"' + b"a" * 9000 + b'"}', headers=h).status_code == 413
    assert c.post(f"/v1/ai-trading/class/rooms/{RID}/attachments", content=b'{"x":"' + b"a" * 2_900_000 + b'"}', headers=h).status_code == 413
    assert c.post(f"/v1/ai-trading/class/rooms/{RID}/zzz", content=b"{}", headers=h).status_code == 404
    assert not seen
    # CSRF token của vai khác (gắn danh tính) không dùng được
    tok_other = c.get("/v1/user/csrf", headers=hdr("expert", "other")).json()["token"]
    if tok_other != h["X-CSRF-Token"]:
        assert c.post(u, content=b'{"text":"x"}', headers={**e, "X-CSRF-Token": tok_other}).status_code == 403
    assert c.post(u, content=b'{"text":"x"}', headers=h).status_code == 200 and len(seen) == 1
    assert seen[0].get_method() == "POST" and json.loads(seen[0].data) == {"text": "x"}


def test_final_test_master_only_and_sse(monkeypatch):
    seen = []
    _patch(monkeypatch, seen, lambda: FakeResp(200, b'data: {"type":"user"}\n\ndata: {"type":"done"}\n\n', "text/event-stream"))
    c = client()
    h = csrf(c)
    r = c.post(f"/v1/ai-trading/class/rooms/{RID}/final-test", content=b'{"scenario_id":"CL-a","confirm":"CL-a"}', headers=h)
    assert r.status_code == 403 and not seen
    r = c.post(f"/v1/ai-trading/class/rooms/{RID}/messages", content=b'{"text":"hi"}', headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream") and r.headers["x-accel-buffering"] == "no"
    assert r.text.count("data: ") == 2


def test_upstream_errors_and_codes(monkeypatch):
    seen = []
    _patch(monkeypatch, seen, lambda: FakeResp(404, '{"detail":"không tìm thấy phòng"}'.encode()))
    c = client()
    assert c.get(f"/v1/ai-trading/class/rooms/{RID}", headers=hdr("expert")).status_code == 404
    _patch(monkeypatch, seen, lambda: FakeResp(500, b"Traceback: secret path /app/x.py"))
    r = c.get(f"/v1/ai-trading/class/rooms/{RID}", headers=hdr("expert"))
    assert r.status_code == 502 and "Traceback" not in r.text


def test_expert_scope_is_narrow(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    e = hdr("expert", "exp-1", "mt5:1")
    me = c.get("/v1/me", headers=e).json()
    assert me["role"] == "expert" and me["accounts"] == [] and me["all_accounts"] is False
    for path in ("/v1/accounts", "/v1/risk/accounts/mt5:1", "/v1/journal/mt5:1/deals", "/v1/user/rules", "/v1/user/prefs", "/v1/system", "/v1/alerts", "/v1/paper/overview",
                 "/v1/ai-trading/lab", "/v1/ai-trading/ledger.csv?strategy=KB-1", "/v1/ai-trading/jobs/" + "a" * 32, "/v1/ai-trading/guardrail"):
        r = c.get(path, headers=e)
        assert r.status_code in (403, 404) or (path == "/v1/accounts" and r.json() == []), path
    h = csrf(c)
    for path, body in (("/v1/ai-trading/jobs", b'{"type":"backtest","strategy_id":"CL-a"}'), ("/v1/ai-trading/scenarios", b'{"yaml":"x"}'),
                       ("/v1/ai-trading/guardrail/killswitch", b'{"on":true}'), ("/v1/user/rules", b"{}")):
        assert c.post(path, content=body, headers=h).status_code == 403, path
    assert not seen


def test_rate_limit(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    h = csrf(c, uid="rl1")
    codes = [c.post(f"/v1/ai-trading/class/rooms/{RID}/pins", content=b'{"message_id":"x"}', headers=h).status_code for _ in range(65)]
    assert codes[:60] == [200] * 60 and 429 in codes[60:]


def test_master_header_ascii(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    r = client().get("/v1/ai-trading/class/rooms", headers=hdr("master", "adm"))
    assert r.status_code == 200
    from urllib.parse import unquote
    assert unquote({k.lower(): v for k, v in seen[-1].header_items()}["x-class-name"]) == "Quản trị"


def test_new_routes_methods_roles_csrf(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    B = "/v1/ai-trading/class/"
    he, hm = csrf(c), csrf(c, "master", "adm")
    for role in ("client", "analyst", "support", "auditor"):
        h = {**hdr(role, "z"), **JH, "X-CSRF-Token": "x"}
        for m, u in (("GET", "memory"), ("GET", "methods"), ("GET", "templates"), ("DELETE", f"rooms/{RID}"), ("PATCH", "memory/m1"), ("PUT", "methods/m1/relations")):
            assert c.request(m, B + u, headers=h, content=b"{}" if m in ("PATCH", "PUT") else None).status_code == 403, (role, m, u)
    assert not seen
    # GET mới (expert)
    for u in ("rooms/trash", f"rooms/{RID}/canvas", "templates", "demo/script", "memory", "memory/stats", "memory/mem-1", "methods", "methods/m_1/canvas", "methods/m_1/plan/export?fmt=md", f"rooms/{RID}/memory/retrieve?q=a"):
        assert c.get(B + u, headers=hdr("expert")).status_code == 200, u
    # đường lạ / phương thức sai -> 404
    for m, u in (("GET", "methods/m1/zzz"), ("GET", "memory/a.b"), ("DELETE", "rooms/trash"), ("DELETE", "templates"), ("PATCH", f"rooms/{RID}"), ("PUT", "methods/m1"), ("POST", "templates"), ("GET", "rooms/xyz")):
        assert c.request(m, B + u, headers=he, content=b"{}" if m != "GET" else None).status_code in (403, 404), (m, u)
    # ghi cần CSRF
    assert c.delete(B + f"rooms/{RID}", headers={**hdr("expert"), **JH}).status_code == 403
    assert c.patch(B + "memory/m1", content=b'{"a":1}', headers={**hdr("expert"), **JH}).status_code == 403
    n = len(seen)
    assert c.delete(B + f"rooms/{RID}", headers=he).status_code == 200 and seen[-1].get_method() == "DELETE" and seen[-1].data is None
    assert c.patch(B + "memory/m1", content=b'{"a":1}', headers=he).status_code == 200 and seen[-1].get_method() == "PATCH"
    assert c.put(B + "methods/m1/relations", content=b'{"a":1}', headers=he).status_code == 200 and seen[-1].get_method() == "PUT"
    assert c.post(B + "rooms/bulk-delete", content=b'{"ids":[]}', headers=he).status_code == 200
    assert c.post(B + f"rooms/{RID}/canvas/k1/confirm", content=b"{}", headers=he).status_code == 200
    assert len(seen) == n + 5
    # purge: chỉ master
    assert c.delete(B + f"rooms/{RID}/purge", headers=he).status_code == 403
    assert c.delete(B + f"rooms/{RID}/purge", headers=hm).status_code == 200
    # body quá lớn
    assert c.post(B + "memory", content=b'{"t":"' + b"a" * 20000 + b'"}', headers=he).status_code == 413
    assert c.post(B + "memory/import", content=b'{"t":"' + b"a" * 20000 + b'"}', headers=he).status_code == 200


def test_method_messages_sse(monkeypatch):
    seen = []
    _patch(monkeypatch, seen, lambda: FakeResp(200, b'data: {"type":"done"}\n\n', "text/event-stream"))
    c = client()
    r = c.post("/v1/ai-trading/class/methods/m1/messages", content=b'{"text":"hi"}', headers=csrf(c))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream") and "done" in r.text


def test_method_extra_routes(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    B, he, hm = "/v1/ai-trading/class/", csrf(c), csrf(c, "master", "adm")
    assert c.get(B + "methods/m1/messages?limit=5", headers=hdr("expert")).status_code == 200
    assert c.patch(B + f"methods/m1/scenarios/{RID}", content=b'{"role":"x"}', headers=he).status_code == 200 and seen[-1].get_method() == "PATCH"
    for a in ("edit", "confirm"):
        assert c.post(B + f"methods/m1/canvas/k1/{a}", content=b"{}", headers=he).status_code == 200
    for a in ("evidence", "approve"):
        assert c.post(B + f"methods/m1/plan/{a}", content=b"{}", headers=he).status_code == 403     # expert: không
        assert c.post(B + f"methods/m1/plan/{a}", content=b"{}", headers=hm).status_code == 200
    assert c.post(B + "methods/m1/plan/evidence", content=b"{}", headers={**hdr("client", "z"), **JH, "X-CSRF-Token": "x"}).status_code == 403


def test_options_stats_and_memory_lock_revoke(monkeypatch):
    seen = []
    _patch(monkeypatch, seen)
    c = client()
    B, he, hm = "/v1/ai-trading/class/", csrf(c), csrf(c, "master", "adm")
    assert c.get(B + "options/stats", headers=hdr("expert")).status_code == 200
    for a in ("lock", "revoke"):
        assert c.post(B + f"memory/m_abc/{a}", content=b"{}", headers=he).status_code == 403   # expert: không
        assert c.post(B + f"memory/m_abc/{a}", content=b"{}", headers=hm).status_code == 200
