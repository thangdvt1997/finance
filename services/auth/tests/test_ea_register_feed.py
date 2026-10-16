"""ea_register: 2 tai khoan cung (platform, login, may chu) - `mt5:L` (EA cu) va `mt5:L-feed` (EA market-feed) phan biet bang account_id."""
import asyncio

from auth import security as sec
from auth.config import AuthSettings
from auth.service import AuthService


class Store:
    def __init__(self):
        from datetime import datetime, timedelta, timezone
        exp = datetime.now(timezone.utc) + timedelta(days=1)
        mk = lambda aid, code: {"account_id": aid, "platform": "mt5", "login": 7, "server": "S", "status": "pending", "client_id": "c-" + aid,  # noqa: E731
                                "pairing_code_hash": sec.hash_code(code), "pairing_expires_at": exp, "ea_cred_pending_enc": None, "ea_remote_addr": None}
        self.rows = [mk("mt5:7", "AAAA-1111"), mk("mt5:7-feed", "BBBB-2222")]
        self.updated = []

    async def find_accounts(self, platform, login, server=None):
        return list(self.rows)

    async def update_account(self, aid, **kw):
        self.updated.append(aid)

    async def audit(self, *a, **k):
        pass


def svc():
    s = AuthService.__new__(AuthService)
    s.store, s.cfg = Store(), AuthSettings()
    s.fail_ip = type("B", (), {"blocked": lambda *a: False, "hit": lambda *a: None})()
    s.reg_fail = type("B", (), {"blocked": lambda *a: False, "hit": lambda *a: None, "reset": lambda *a: None})()
    s.vault = type("V", (), {"ok": True, "enc": lambda self, x: x, "dec": lambda self, x: x})()

    async def nb(aid):
        pass
    s.notify_bridge = nb
    return s


def reg(s, **kw):
    return asyncio.run(s.ea_register({"platform": "mt5", "login": 7, "server": "S", "pair_code": "", "remote_addr": "1.1.1.1", **kw}))[1]


def test_feed_pairing_by_account_id_and_old_ea_unaffected():
    s = svc()
    r = reg(s, pair_code="BBBB-2222", account_id="mt5:7-feed")
    assert r["status"] == "active" and r["account_id"] == "mt5:7-feed" and r["token"]
    s = svc()
    assert reg(s, pair_code="AAAA-1111")["account_id"] == "mt5:7"                      # EA cu khong khai account_id -> tai khoan chinh
    assert reg(svc(), pair_code="AAAA-1111", account_id="mt5:7-feed")["status"] == "rejected"   # ma cua tai khoan khac
