"""Vai trò phụ support/analyst/auditor (docs/FLEET_MGMT.md): MẶC ĐỊNH TỪ CHỐI, chỉ GET dữ liệu đọc trong phạm vi tài khoản được giao, không leo thang."""
from test_authz import CLIENT_A, KEY, MASTER, SECRET, hdr, make  # noqa: F401  (dùng lại dựng ứng dụng + header của bộ test authz)

SUP = hdr("support", "mt5:1", "us")
ANA = hdr("analyst", "mt5:2", "ua2")
AUD = hdr("auditor", "mt5:1,mt5:2", "uau")          # auditor: auth không cấp tài khoản, gateway cũng bỏ nếu có
NOSCOPE = hdr("support", "", "us0")


def ids(r):
    return sorted(a["account_id"] for a in r)


def test_staff_sees_only_scope(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert ids(c.get("/v1/accounts", headers=SUP).json()) == ["mt5:1"]
        assert ids(c.get("/v1/accounts", headers=ANA).json()) == ["mt5:2"]
        assert c.get("/v1/accounts", headers=NOSCOPE).json() == []                       # không nhóm nào => 0 tài khoản (mặc định từ chối)
        me = c.get("/v1/me", headers=SUP).json()
        assert me["role"] == "support" and me["accounts"] == ["mt5:1"] and me["all_accounts"] is False


def test_staff_idor_other_account_denied(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/equity-history", headers=SUP, params={"account_id": "mt5:2"}).status_code == 403
        assert c.get("/v1/risk/accounts/mt5:2", headers=SUP).status_code == 403
        assert c.get("/v1/risk/accounts/mt5:1", headers=SUP).status_code == 200
        assert c.get("/v1/journal/mt5:2/deals", headers=SUP).status_code == 403
        rows = c.get("/v1/risk/accounts", headers=SUP).json()["accounts"]
        assert [a["account_id"] for a in rows] == ["mt5:1"]


def test_staff_read_only_no_writes(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        for h in (SUP, ANA):
            assert c.put("/v1/journal/mt5:1/notes/1", headers=h, json={"note": "x"}).status_code == 403   # chỉ-đọc (khác client: không ghi nhật ký)
            assert c.delete("/v1/journal/mt5:1/notes/1", headers=h).status_code == 403
            assert c.post("/v1/user/rules", headers=h, json={}).status_code == 403
            assert c.get("/v1/user/rules", headers=h).status_code == 403                                  # không dùng cảnh báo cá nhân
            assert c.get("/v1/user/push", headers=h).status_code == 403
            assert c.get("/v1/system", headers=h).status_code == 403                                      # master-only
            assert c.get("/v1/alerts", headers=h).status_code == 403
            assert c.get("/v1/paper/accounts", headers=h).status_code == 403


def test_auditor_has_no_data(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/me", headers=AUD).json()["role"] == "auditor"
        for path in ("/v1/accounts", "/v1/overview", "/v1/risk/accounts", "/v1/quotes/latest", "/v1/news", "/v1/bars"):
            assert c.get(path, headers=AUD).status_code == 403, path
        assert c.get("/v1/risk/accounts/mt5:1", headers=AUD).status_code == 403


def test_staff_cannot_forge_or_escalate(monkeypatch):
    c, _ = make(monkeypatch)
    with c:
        assert c.get("/v1/me", headers={**KEY, "X-Role": "support", "X-Accounts": "mt5:1"}).status_code == 403   # thiếu secret
        assert c.get("/v1/me", headers=hdr("support", "mt5:1", secret="sai")).status_code == 403
        assert c.get("/v1/me", headers=hdr("superadmin", "*")).status_code == 403                            # vai trò lạ
        star = c.get("/v1/me", headers=hdr("support", "*,mt5:1")).json()
        assert star["accounts"] == ["mt5:1"]                                                                   # "*" không cấp quyền
        spoof = c.get("/v1/me", headers=hdr("client", "staff:support,mt5:1")).json()
        assert spoof["accounts"] == ["mt5:1"]                                                                  # ký hiệu nội bộ không thể giả bằng client
        assert c.get("/v1/accounts", headers=SUP).status_code == 200
