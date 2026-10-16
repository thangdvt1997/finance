"""Quản trị đội tài khoản: tham số luật, ma trận quyền (mặc định từ chối), xem trước CSV + bulk 2 bước (stub DB). docs/FLEET_MGMT.md."""
import pytest

from auth import fleet_rules as fr
from auth import roles as R
from auth.config import AuthSettings
from auth.fleet_service import FleetService, device_label
from auth.service import AuthError, Principal


# ------------------------------------------------------------------ tham số luật
def test_validate_params_defaults_and_ranges():
    p = fr.validate_params("daily_loss", {"limit_pct": 5})
    assert p["basis"] == "day_start_equity" and p["warn_usage_pct"] == 70 and p["tz"] == "UTC" and p["reset_hour"] == 0
    assert fr.validate_params("max_drawdown", {"limit_pct": 10, "mode": "trailing_eod", "tz": "Europe/Prague", "reset_hour": 17})["reset_hour"] == 17
    assert fr.validate_params("margin_level", {"min_level_pct": 150})["min_level_pct"] == 150
    assert fr.validate_params("max_trades_day", {"limit": 30})["limit"] == 30
    assert fr.validate_params("best_day", {"max_share_pct": 40})["min_total_profit"] == 0
    assert fr.validate_params("daily_loss", {"limit_pct": 3, "tz": "UTC+3"})["tz"] == "UTC+3"


@pytest.mark.parametrize("kind,params", [
    ("daily_loss", {}), ("daily_loss", {"limit_pct": 0}), ("daily_loss", {"limit_pct": 500}), ("daily_loss", {"limit_pct": "abc"}),
    ("daily_loss", {"limit_pct": 5, "basis": "x"}), ("daily_loss", {"limit_pct": 5, "reset_hour": 24}), ("daily_loss", {"limit_pct": 5, "tz": "../etc/passwd"}),
    ("daily_loss", {"limit_pct": 5, "tz": "a" * 50}), ("max_drawdown", {"limit_pct": 5, "mode": "magic"}), ("margin_level", {}), ("margin_level", {"min_level_pct": 1}),
    ("nope", {"limit_pct": 5}), ("daily_loss", {"limit_pct": float("nan")}), ("max_trades_day", {"limit": 0}),
])
def test_validate_params_rejects(kind, params):
    with pytest.raises(ValueError):
        fr.validate_params(kind, params)


def test_validate_params_drops_unknown_keys():
    p = fr.validate_params("margin_level", {"min_level_pct": 120, "evil": "x", "__proto__": 1})
    assert "evil" not in p and "__proto__" not in p


def test_presets_are_neutral_and_valid():
    for pr in fr.PRESETS:
        fr.validate_params(pr["kind"], pr["params"])
        assert not any(w in pr["name"].lower() for w in ("ftmo", "funded", "fundingpips", "the5ers", "topstep"))
    assert "KHÁC NHAU" in fr.DISCLAIMER


# ------------------------------------------------------------------ vai trò: mặc định từ chối
def test_role_matrix_default_deny():
    assert R.has_perm("master", "anything.at.all")
    assert R.has_perm("support", "incident.note") and not R.has_perm("support", "incident.ack") and not R.has_perm("support", "audit.read")
    assert R.has_perm("analyst", "compliance.read") and not R.has_perm("analyst", "incident.read") and not R.has_perm("analyst", "note.write")
    assert R.has_perm("auditor", "audit.read") and not R.has_perm("auditor", "fleet.read")
    assert R.has_perm("expert", "class.use") and not R.has_perm("expert", "fleet.read") and not R.has_perm("expert", "audit.read") and R.is_admin_role("expert")
    assert not R.has_perm("client", "fleet.read") and not R.has_perm("unknown", "fleet.read") and not R.has_perm("", "audit.read")
    assert R.is_admin_role("auditor") and not R.is_admin_role("client") and not R.is_admin_role("root")


def test_device_label():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    assert device_label(ua) == "Chrome · Windows"
    assert device_label("") == "không rõ"


# ------------------------------------------------------------------ stub DB cho FleetService
class FakeStore:
    def __init__(self):
        self.accounts = [{"account_id": "mt5:1", "platform": "mt5", "login": 1, "server": "S", "status": "active"}]
        self.audits = []
        self.pool = None

    async def list_accounts_full(self):
        return self.accounts

    async def audit(self, uid, label, action, target="", ip="", detail=None):
        self.audits.append((action, target, detail))

    async def get_user(self, uid):
        return None


class FakeFS:
    async def list_groups(self):
        return [{"id": "g1", "name": "Alpha"}]

    async def get_group(self, gid):
        return {"id": gid} if gid == "11111111-1111-1111-1111-111111111111" else None


class FakeSvc:
    def __init__(self, totp_required=True):
        self.store = FakeStore()
        self.cfg = AuthSettings(master_totp_required=totp_required)

    async def set_account_status(self, p, a, suspend, ip):
        self.store.audits.append(("suspend" if suspend else "activate", a, None))


def mk(totp_required=True):
    svc = FakeSvc(totp_required)
    f = FleetService.__new__(FleetService)
    f.svc, f.fs, f._pending, f._eaw = svc, FakeFS(), {}, {}
    return f, svc


MASTER_T = Principal("m1", "master", "master:t", "T", ["*"], totp_enabled=True)
MASTER_NT = Principal("m2", "master", "master:n", "N", ["*"], totp_enabled=False)
SUPPORT = Principal("s1", "support", "master:s", "S", ["mt5:1"])


async def test_totp_required_for_sensitive_ops():
    f, _ = mk()
    with pytest.raises(AuthError) as e:
        await f.bulk_prepare(MASTER_NT, "suspend", ["mt5:1"], {}, "1.1.1.1")
    assert e.value.status == 403 and e.value.extra.get("totp_required") is True
    f2, _ = mk(totp_required=False)
    r = await f2.bulk_prepare(MASTER_NT, "suspend", ["mt5:1"], {}, "1.1.1.1")
    assert r["summary"]["count"] == 1


async def test_subroles_cannot_bulk_or_import_or_staff():
    f, _ = mk()
    for coro in (f.bulk_prepare(SUPPORT, "suspend", ["mt5:1"], {}, "x"), f.import_preview(SUPPORT, "login\n1", "x"), f.staff(SUPPORT),
                 f.create_staff(SUPPORT, "x", "support", "", False, [], "x"), f.view_as(SUPPORT, "mt5:1", "lý do dài đủ", "x")):
        with pytest.raises(AuthError) as e:
            await coro
        assert e.value.status == 403


async def test_bulk_two_step_single_use_and_phrase():
    f, svc = mk()
    r = await f.bulk_prepare(MASTER_T, "suspend", ["mt5:1", "mt5:999", "mt5:1"], {}, "1.1.1.1")
    assert r["summary"]["count"] == 1 and r["summary"]["phrase"] == "XAC NHAN 1" and r["summary"]["skipped"][0]["account_id"] == "mt5:999"
    tok = r["confirm_token"]
    with pytest.raises(AuthError):                                           # sai cụm xác nhận -> token bị huỷ (không thử lại được)
        await f.bulk_execute(MASTER_T, tok, "XAC NHAN 2", "1.1.1.1")
    with pytest.raises(AuthError):
        await f.bulk_execute(MASTER_T, tok, "XAC NHAN 1", "1.1.1.1")
    r = await f.bulk_prepare(MASTER_T, "suspend", ["mt5:1"], {}, "1.1.1.1")
    other = Principal("m9", "master", "master:o", "O", ["*"], totp_enabled=True)
    with pytest.raises(AuthError):                                           # người khác không dùng được token
        await f.bulk_execute(other, r["confirm_token"], "XAC NHAN 1", "1.1.1.1")
    r = await f.bulk_prepare(MASTER_T, "suspend", ["mt5:1"], {}, "1.1.1.1")
    out = await f.bulk_execute(MASTER_T, r["confirm_token"], " xac nhan 1 ", "1.1.1.1")
    assert out["results"] == [{"account_id": "mt5:1", "ok": True}]
    with pytest.raises(AuthError):                                           # dùng lại token đã thực thi
        await f.bulk_execute(MASTER_T, r["confirm_token"], "XAC NHAN 1", "1.1.1.1")
    assert any(a[0] == "bulk_executed" for a in svc.store.audits)


async def test_bulk_validation():
    f, _ = mk()
    with pytest.raises(AuthError):
        await f.bulk_prepare(MASTER_T, "drop_tables", ["mt5:1"], {}, "x")
    with pytest.raises(AuthError):
        await f.bulk_prepare(MASTER_T, "suspend", [], {}, "x")
    with pytest.raises(AuthError):
        await f.bulk_prepare(MASTER_T, "suspend", [f"mt5:{i}" for i in range(201)], {}, "x")
    with pytest.raises(AuthError):
        await f.bulk_prepare(MASTER_T, "tag_add", ["mt5:1"], {"tag": "BAD TAG!"}, "x")
    with pytest.raises(AuthError):
        await f.bulk_prepare(MASTER_T, "group_add", ["mt5:1"], {"group_id": "khong-phai-uuid"}, "x")


async def test_import_preview_validation():
    f, svc = mk()
    csv_text = ("platform,login,server,label,group,tags,notes\n"
                "mt5,1001,Srv-A,Khach A,Alpha,vip;eu,ghi chu\n"
                "mt5,1001,Srv-A,Trung dong,Alpha,,\n"
                "mt9,1002,Srv,X,,,\n"
                "mt5,abc,Srv,X,,,\n"
                "mt5,1,S,Da co,,,\n"
                "mt5,1003,Srv,Moi,NhomMoi,TAG!BAD,\n")
    r = await f.import_preview(MASTER_T, csv_text, "1.1.1.1")
    rows = {x["line"]: x for x in r["rows"]}
    assert rows[2]["ok"] and rows[2]["tags"] == ["eu", "vip"] and not rows[2]["warnings"]
    assert "trùng dòng khác trong CSV" in rows[3]["errors"]
    assert any("platform" in e for e in rows[4]["errors"])
    assert any("login" in e for e in rows[5]["errors"])
    assert "tài khoản đã tồn tại" in rows[6]["errors"]
    assert any("tag" in e for e in rows[7]["errors"]) and any("sẽ được tạo" in w for w in rows[7]["warnings"])
    assert r["summary"] == {"total": 6, "ok": 1, "error": 5}
    with pytest.raises(AuthError):
        await f.import_preview(MASTER_T, "x" * 200_001, "x")
    with pytest.raises(AuthError):
        await f.import_preview(MASTER_T, "a,b\n1,2", "x")                    # thiếu cột login
    big = "login\n" + "\n".join(str(i) for i in range(1, 202))
    with pytest.raises(AuthError):
        await f.import_preview(MASTER_T, big, "x")


async def test_view_as_requires_reason():
    f, _ = mk()
    with pytest.raises(AuthError) as e:
        await f.view_as(MASTER_T, "mt5:1", "ngắn", "x")
    assert e.value.status == 422
